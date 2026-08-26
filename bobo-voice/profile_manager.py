"""
BoboVoice profile manager — per-user accessibility & voice settings.
Stored in ~/.config/bobo-voice/profile.json. Controls wake sensitivity, TTS
voice/rate/volume, language, and accessibility toggles (captions, verbose).
"""
import os
import json

CONF = os.path.expanduser("~/.config/bobo-voice/profile.json")
DEFAULT = {
    "language": "ro",
    "wake_sensitivity": 0.5,
    "tts_rate": 165,
    "tts_volume": 1.0,
    "tts_voice": "auto",
    "captions": False,
    "verbose": True,
    "welcome": True,
}


class ProfileManager:
    def __init__(self):
        self.data = dict(DEFAULT)
        self.load()

    def load(self):
        try:
            with open(CONF) as fh:
                self.data.update(json.load(fh))
        except Exception:
            pass
        return self.data

    def save(self):
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        with open(CONF, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.data.get(key, DEFAULT.get(key, default))

    def set(self, key, value):
        self.data[key] = value
        self.save()
