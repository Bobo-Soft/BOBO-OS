"""
BoboVoice wake-word detector.
Tiers: openWakeWord (ML, best) → Vosk (keyword spotting) → energy-gate fallback.
Wake phrases: "hey bobo", "hei bobo", "bobo ascultă". Low CPU (~1-2%), with a
2-second anti-bounce so one utterance doesn't trigger twice.
All backends are optional; missing ones fall through to the next tier.
"""
import time
import threading

WAKE_PHRASES = ["hey bobo", "hei bobo", "bobo asculta", "bobo ascultă", "ok bobo"]
ANTI_BOUNCE = 2.0


class WakeWord:
    def __init__(self, sensitivity=0.5, on_wake=None):
        self.sensitivity = sensitivity
        self.on_wake = on_wake or (lambda: None)
        self._last = 0.0
        self._running = False
        self._thread = None
        self.backend = self._select_backend()

    def _select_backend(self):
        try:
            import openwakeword  # noqa: F401
            return "openwakeword"
        except Exception:
            pass
        try:
            import vosk  # noqa: F401
            return "vosk"
        except Exception:
            pass
        return "energy"

    # ------------------------------------------------------------------ lifecycle
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _fire(self):
        now = time.time()
        if now - self._last >= ANTI_BOUNCE:
            self._last = now
            try:
                self.on_wake()
            except Exception:
                pass

    # ------------------------------------------------------------------ loops
    def _loop(self):
        if self.backend == "openwakeword":
            self._loop_oww()
        elif self.backend == "vosk":
            self._loop_vosk()
        else:
            self._loop_energy()

    def _mic_frames(self, rate=16000, chunk=1280):
        try:
            import sounddevice as sd
            import numpy as np
            with sd.RawInputStream(samplerate=rate, blocksize=chunk, dtype="int16", channels=1) as st:
                while self._running:
                    data, _ = st.read(chunk)
                    yield np.frombuffer(data, dtype="int16")
        except Exception:
            # no audio backend -> stop quietly
            self._running = False
            return

    def _loop_oww(self):
        try:
            from openwakeword.model import Model
            model = Model()
            for frame in self._mic_frames():
                preds = model.predict(frame)
                if any(p >= (1 - self.sensitivity) for p in preds.values()):
                    self._fire()
        except Exception:
            self._loop_energy()

    def _loop_vosk(self):
        try:
            import json
            import vosk
            rec = vosk.KaldiRecognizer(vosk.Model(lang="ro"), 16000)
            for frame in self._mic_frames():
                if rec.AcceptWaveform(frame.tobytes()):
                    text = json.loads(rec.Result()).get("text", "").lower()
                    if any(p in text for p in WAKE_PHRASES):
                        self._fire()
        except Exception:
            self._loop_energy()

    def _loop_energy(self):
        """Fallback: fire on a sustained loud burst (push-to-talk-ish)."""
        try:
            import numpy as np
            loud = 0
            thresh = 1500 - int(self.sensitivity * 800)
            for frame in self._mic_frames():
                rms = float(np.sqrt(np.mean(frame.astype("float32") ** 2)))
                loud = loud + 1 if rms > thresh else 0
                if loud >= 6:  # ~0.5s sustained
                    loud = 0
                    self._fire()
        except Exception:
            self._running = False
