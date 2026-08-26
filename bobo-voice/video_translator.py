"""
BoboVoice video translator.
For a media file: transcribe with Whisper (translate task) and write a Romanian
.ro.srt beside it. For live audio: monitor the default output, transcribe in
chunks and feed captions to a callback (used by the live captioner).
"""
import os
import threading
import time


class VideoTranslator:
    def __init__(self, model_size="base"):
        self.model_size = model_size
        self._model = None
        self._running = False

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    # ------------------------------------------------------------------ file mode
    def make_srt(self, media_path: str, target="ro") -> str:
        """Generate a translated .<target>.srt next to the media file."""
        try:
            model = self._load()
            task = "translate" if target == "en" else "transcribe"
            segs, info = model.transcribe(media_path, task=task)
            out = os.path.splitext(media_path)[0] + ".%s.srt" % target
            with open(out, "w", encoding="utf-8") as fh:
                for i, s in enumerate(segs, 1):
                    fh.write("%d\n%s --> %s\n%s\n\n" % (i, _ts(s.start), _ts(s.end), s.text.strip()))
            return out
        except Exception as e:
            return "[Traducere video indisponibilă: %s]" % e

    # ------------------------------------------------------------------ live mode
    def start_live(self, on_caption):
        """Monitor system audio; call on_caption(text) with rolling transcripts."""
        self._running = True
        threading.Thread(target=self._live_loop, args=(on_caption,), daemon=True).start()

    def stop_live(self):
        self._running = False

    def _live_loop(self, on_caption):
        try:
            import sounddevice as sd
            import numpy as np
            import tempfile, wave
            model = self._load()
            rate = 16000
            while self._running:
                buf = sd.rec(int(4 * rate), samplerate=rate, channels=1, dtype="int16")
                sd.wait()
                wav = tempfile.mktemp(suffix=".wav")
                with wave.open(wav, "wb") as wf:
                    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
                    wf.writeframes(buf.tobytes())
                segs, _ = model.transcribe(wav, vad_filter=True)
                text = " ".join(s.text for s in segs).strip()
                if text:
                    on_caption(text)
                os.remove(wav)
        except Exception as e:
            on_caption("[live indisponibil: %s]" % e)
            self._running = False


def _ts(sec):
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60); ms = int((sec - int(sec)) * 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)
