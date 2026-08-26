"""
BoboVoice text-to-speech.
Tiers: Coqui TTS (RO, best quality if installed) → espeak-ng (fast, offline) →
pyttsx3. Text is preprocessed (expand common RO abbreviations, add pauses at
punctuation). Exposes speak(), stop(), set_rate(), set_volume().
"""
import subprocess
import threading
import tempfile
import re

ABBREV = {
    r"\bdr\.": "doctor", r"\bnr\.": "numărul", r"\betc\.": "et cetera",
    r"\bex\.": "de exemplu", r"\bapprox\.": "aproximativ", r"\bstr\.": "strada",
}


def preprocess(text: str) -> str:
    for pat, rep in ABBREV.items():
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    text = text.replace("...", ", ").replace(";", ", ")
    return text.strip()


class TTSEngine:
    def __init__(self, rate=165, volume=1.0, lang="ro"):
        self.rate = rate
        self.volume = volume
        self.lang = lang
        self._proc = None
        self.backend = self._select()

    def _select(self):
        try:
            import TTS  # noqa: F401
            return "coqui"
        except Exception:
            pass
        if subprocess.run(["which", "espeak-ng"], capture_output=True).returncode == 0:
            return "espeak"
        try:
            import pyttsx3  # noqa: F401
            return "pyttsx3"
        except Exception:
            return "none"

    def set_rate(self, rate):
        self.rate = rate

    def set_volume(self, vol):
        self.volume = max(0.0, min(1.0, vol))

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self._proc = None

    def speak(self, text: str, block=False):
        text = preprocess(text)
        if not text:
            return
        if block:
            self._speak_now(text)
        else:
            threading.Thread(target=self._speak_now, args=(text,), daemon=True).start()

    def _speak_now(self, text):
        self.stop()
        if self.backend == "espeak":
            speed = str(int(self.rate * 1.0))
            amp = str(int(self.volume * 200))
            self._proc = subprocess.Popen(["espeak-ng", "-v", self.lang, "-s", speed, "-a", amp, text])
            self._proc.wait()
        elif self.backend == "coqui":
            try:
                from TTS.api import TTS as CoquiTTS
                wav = tempfile.mktemp(suffix=".wav")
                model = "tts_models/ro/cv/vits" if self.lang == "ro" else "tts_models/en/ljspeech/tacotron2-DDC"
                CoquiTTS(model).tts_to_file(text=text, file_path=wav)
                self._proc = subprocess.Popen(["aplay", wav]); self._proc.wait()
            except Exception:
                self.backend = "espeak"; self._speak_now(text)
        elif self.backend == "pyttsx3":
            try:
                import pyttsx3
                e = pyttsx3.init()
                e.setProperty("rate", self.rate); e.setProperty("volume", self.volume)
                e.say(text); e.runAndWait()
            except Exception:
                pass
