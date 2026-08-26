"""
BoboVoice action executor — maps recognized intents to real system actions.
System (volume/brightness/power/lock/screenshot), apps, windows, reading, web,
accessibility, content (describe/translate/explain), media, and documents.
Wayland-native (wpctl/brightnessctl/playerctl/wtype/grim); returns a spoken reply.
"""
import os
import sys
import subprocess

sys.path.insert(0, "/usr/share/bobo-voice")

BOBO_APPS = {
    "player": "bobo-player", "monitor": "bobo-monitor", "setări": "bobo-settings",
    "setari": "bobo-settings", "text": "bobo-text", "fișiere": "nemo", "fisiere": "nemo",
    "browser": "epiphany", "terminal": "kitty", "write": "bobo-write", "scriere": "bobo-write",
    "calc": "bobo-calc", "calcul": "bobo-calc", "prezentare": "bobo-present",
    "grafic": "bobo-chart", "formular": "bobo-form", "hub": "bobo-hub",
    "traducere": "bobo-translate", "hartă": "bobo-mind", "asistent": "bobo-assist",
    "cod": "bobo-code", "xcode": "bobo-xcode",
}


def _run(cmd):
    try:
        subprocess.Popen(cmd)
        return True
    except Exception:
        return False


def _wtype_key(keys):
    """Send a key chord via wtype, e.g. ['-M','ctrl','s','-m','ctrl']."""
    try:
        subprocess.run(["wtype"] + keys, timeout=5)
        return True
    except Exception:
        return False


class ActionExecutor:
    def __init__(self, tts=None, doc_reader=None, describer=None, ai=None, profile=None):
        self.tts = tts
        self.doc_reader = doc_reader
        self.describer = describer
        self.ai = ai
        self.profile = profile

    # ------------------------------------------------------------------ system
    def volume(self, direction):
        d = {"up": "5%+", "down": "5%-"}.get(direction, "5%+")
        _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", d])
        return "Am reglat volumul."

    def mute(self):
        _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]); return "Sunet comutat."

    def brightness(self, direction):
        d = {"up": "10%+", "down": "10%-"}.get(direction, "10%+")
        _run(["brightnessctl", "s", d]); return "Am reglat luminozitatea."

    def power(self, what):
        cmd = {"shutdown": ["systemctl", "poweroff"], "oprire": ["systemctl", "poweroff"],
               "restart": ["systemctl", "reboot"], "repornire": ["systemctl", "reboot"],
               "suspend": ["systemctl", "suspend"], "somn": ["systemctl", "suspend"]}.get(what)
        if cmd:
            _run(cmd); return "În regulă."
        return "Nu am înțeles comanda de alimentare."

    def lock(self):
        _run(["swaylock", "-f", "-c", "1a1a2e"]); return "Ecran blocat."

    def screenshot(self):
        _run(["bobo-screen", "--full"]) or _run(["grim", os.path.expanduser("~/Imagini/captura.png")])
        return "Am făcut o captură de ecran."

    # ------------------------------------------------------------------ apps / windows
    def open_app(self, name):
        cmd = BOBO_APPS.get(name.lower().strip())
        if not cmd:
            for k, v in BOBO_APPS.items():
                if k in name.lower():
                    cmd = v; break
        if cmd and _run([cmd]):
            return "Deschid %s." % name
        return "Nu am găsit aplicația %s." % name

    def list_apps(self):
        return "Aplicații disponibile: " + ", ".join(sorted(set(BOBO_APPS.keys())))

    def help_apps(self):
        return ("Spune de exemplu: deschide scriere, deschide calcul, mărește volumul, "
                "citește documentul, descrie ecranul, sau caută pe web.")

    def window(self, action):
        keys = {"close": ["-M", "alt", "-k", "F4", "-m", "alt"],
                "maximize": ["-M", "super", "-k", "Up", "-m", "super"],
                "minimize": ["-M", "super", "-k", "Down", "-m", "super"]}.get(action)
        if keys:
            _wtype_key(keys); return "În regulă."
        return "Nu am înțeles comanda de fereastră."

    # ------------------------------------------------------------------ reading
    def read_document(self, path=None):
        if self.doc_reader and path and self.doc_reader.load(path):
            import threading
            threading.Thread(target=self.doc_reader.read_all, daemon=True).start()
            return "Încep să citesc documentul."
        return "Nu am un document de citit. Deschide unul întâi."

    def read_screen(self):
        if self.describer:
            text = self.describer.describe_clipboard_or_screen()
            if self.tts:
                self.tts.speak(text)
            return text
        return "Nu pot citi ecranul."

    def stop_reading(self):
        if self.doc_reader:
            self.doc_reader.stop()
        if self.tts:
            self.tts.stop()
        return "M-am oprit."

    # ------------------------------------------------------------------ web
    def web_search(self, query):
        _run(["xdg-open", "https://duckduckgo.com/?q=" + query.replace(" ", "+")])
        return "Caut %s pe web." % query

    def open_website(self, url):
        if not url.startswith("http"):
            url = "https://" + url
        _run(["xdg-open", url]); return "Deschid site-ul."

    def scroll(self, direction):
        key = "Page_Down" if direction != "up" else "Page_Up"
        _wtype_key(["-k", key]); return "Derulez."

    def nav(self, direction):
        keys = ["-M", "alt", "-k", "Left" if direction == "back" else "Right", "-m", "alt"]
        _wtype_key(keys); return "În regulă."

    # ------------------------------------------------------------------ accessibility
    def text_size(self, bigger=True):
        try:
            cur = float(subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "text-scaling-factor"],
                                       capture_output=True, text=True).stdout.strip() or "1.0")
        except Exception:
            cur = 1.0
        cur = min(2.0, cur + 0.15) if bigger else max(0.7, cur - 0.15)
        _run(["gsettings", "set", "org.gnome.desktop.interface", "text-scaling-factor", str(cur)])
        return "Text %s." % ("mărit" if bigger else "micșorat")

    def contrast(self):
        _run(["gsettings", "set", "org.gnome.desktop.a11y.interface", "high-contrast", "true"])
        return "Contrast ridicat activat."

    def speech_rate(self, faster=True):
        if self.tts:
            self.tts.set_rate(self.tts.rate + (25 if faster else -25))
        return "Vorbesc mai %s." % ("repede" if faster else "rar")

    # ------------------------------------------------------------------ content (AI)
    def describe_image(self, path):
        if self.describer:
            return self.describer.describe_image_file(path)
        return "Nu pot descrie imaginea."

    def translate(self, text, target="en"):
        try:
            sys.path.insert(0, "/usr/share/bobo-office")
            from translate.translate import translate as tr
            return tr(text, "auto", target)
        except Exception:
            return "Traducere indisponibilă."

    def explain(self, topic):
        if self.ai and self.ai.available():
            return self.ai.ask("Explică pe scurt, simplu, în română: %s" % topic)
        return "Am nevoie de un model AI local pornit pentru a explica."

    # ------------------------------------------------------------------ media / docs
    def media(self, action):
        m = {"play": "play-pause", "pause": "play-pause", "next": "next",
             "prev": "previous", "următor": "next", "anterior": "previous"}.get(action, "play-pause")
        _run(["playerctl", m]); return "În regulă."

    def save_doc(self):
        _wtype_key(["-M", "ctrl", "s", "-m", "ctrl"]); return "Am salvat."

    def print_doc(self):
        _wtype_key(["-M", "ctrl", "p", "-m", "ctrl"]); return "Deschid dialogul de tipărire."
