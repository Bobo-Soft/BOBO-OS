"""
BoboVoice speech-to-text — faster-whisper (base model, CPU int8).
Records from the mic until ~1.2s of silence (VAD-style energy gate), with a 30s
hard timeout, then transcribes. Auto-detects language. Degrades to a clear
message if the audio/ASR stack is missing.
"""
import time
import tempfile
import wave


class STTEngine:
    def __init__(self, model_size="base", language=None):
        self.model_size = model_size
        self.language = language
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    # ------------------------------------------------------------------ record
    def record(self, out_wav=None, rate=16000, silence_sec=1.2, timeout=30) -> str:
        """Record until silence; return the WAV path (or '' on failure)."""
        try:
            import sounddevice as sd
            import numpy as np
        except Exception:
            return ""
        out_wav = out_wav or tempfile.mktemp(suffix=".wav")
        frames = []
        chunk = 1600  # 0.1s
        silent = 0.0
        started = time.time()
        heard = False
        try:
            with sd.RawInputStream(samplerate=rate, blocksize=chunk, dtype="int16", channels=1) as st:
                while True:
                    data, _ = st.read(chunk)
                    arr = np.frombuffer(data, dtype="int16")
                    frames.append(data)
                    rms = float(np.sqrt(np.mean(arr.astype("float32") ** 2)))
                    if rms > 500:
                        heard = True
                        silent = 0.0
                    else:
                        silent += 0.1
                    if heard and silent >= silence_sec:
                        break
                    if time.time() - started > timeout:
                        break
        except Exception:
            return ""
        try:
            with wave.open(out_wav, "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
                wf.writeframes(b"".join(frames))
            return out_wav if heard else ""
        except Exception:
            return ""

    # ------------------------------------------------------------------ transcribe
    def transcribe(self, wav_path: str) -> str:
        if not wav_path:
            return ""
        try:
            model = self._load()
            segs, info = model.transcribe(wav_path, language=self.language, vad_filter=True)
            return " ".join(s.text for s in segs).strip()
        except Exception as e:
            return "[STT indisponibil: %s]" % e

    def listen(self) -> str:
        """Record then transcribe. Returns recognized text or ''."""
        return self.transcribe(self.record())
