"""
BoboAssist model manager (GTK4).
Lists / downloads / deletes Ollama models with progress, shows RAM, and lets
the user pick the active model. Default: phi3:mini.
"""
import os
import sys
import json
import threading
import urllib.request
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

sys.path.insert(0, "/usr/share/bobo-office")
try:
    from shared.ai_client import AIClient
except Exception:
    AIClient = None

RECOMMENDED = [
    ("phi3:mini", "3.8B - implicit, rapid, ~2.3 GB"),
    ("tinyllama", "1.1B - ultra-usor, ~640 MB"),
    ("gemma2:9b", "9B - calitate mai buna, ~5.4 GB"),
    ("codellama:7b", "7B - pentru cod, ~3.8 GB"),
]
CONF = os.path.expanduser("~/.config/bobo-assist/model.json")


def active_model() -> str:
    try:
        with open(CONF) as fh:
            return json.load(fh).get("model", "phi3:mini")
    except Exception:
        return "phi3:mini"


def set_active_model(name: str):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF, "w") as fh:
        json.dump({"model": name}, fh)


class ModelManagerWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="BoboAssist — Modele AI")
        if parent:
            self.set_transient_for(parent)
        self.set_default_size(480, 480)
        self.ai = AIClient() if AIClient else None

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.set_child(box)

        ram = self._ram_gb()
        box.append(Gtk.Label(label="RAM disponibil: %.1f GB    Ollama: %s"
                             % (ram, "online" if (self.ai and self.ai.available()) else "offline"),
                             xalign=0))

        self.status = Gtk.Label(xalign=0)
        self.status.add_css_class("dim-label")
        box.append(self.status)

        sw = Gtk.ScrolledWindow(); sw.set_vexpand(True)
        self.listbox = Gtk.ListBox()
        sw.set_child(self.listbox)
        box.append(sw)
        self.refresh()

    def _ram_gb(self):
        try:
            import psutil
            return psutil.virtual_memory().total / 1e9
        except Exception:
            try:
                with open("/proc/meminfo") as fh:
                    kb = int(fh.readline().split()[1])
                    return kb / 1e6
            except Exception:
                return 0.0

    def refresh(self):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling(); self.listbox.remove(child); child = nxt
        installed = self.ai.models() if self.ai else []
        cur = active_model()
        for name, desc in RECOMMENDED:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("card")
            tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); tb.set_hexpand(True)
            lbl = Gtk.Label(xalign=0)
            mark = " ✓ activ" if name == cur else ""
            have = any(m.split(":")[0] == name.split(":")[0] for m in installed)
            lbl.set_markup("<b>%s</b>%s" % (name, mark))
            sub = Gtk.Label(label=desc + ("  [instalat]" if have else ""), xalign=0)
            sub.add_css_class("dim-label")
            tb.append(lbl); tb.append(sub); row.append(tb)
            if have:
                use = Gtk.Button(label="Foloseste")
                use.connect("clicked", lambda b, n=name: (set_active_model(n), self.refresh()))
                row.append(use)
                dele = Gtk.Button.new_from_icon_name("user-trash-symbolic")
                dele.connect("clicked", lambda b, n=name: self._delete(n))
                row.append(dele)
            else:
                dl = Gtk.Button(label="Descarca")
                dl.add_css_class("suggested-action")
                dl.connect("clicked", lambda b, n=name: self._download(n))
                row.append(dl)
            r = Gtk.ListBoxRow(); r.set_child(row); self.listbox.append(r)

    def _download(self, name):
        if not self.ai:
            self.status.set_text("AIClient indisponibil"); return
        self.status.set_text("Descarc %s..." % name)
        def work():
            ok = self.ai.pull(name, on_progress=lambda s: GLib.idle_add(self.status.set_text, "%s: %s" % (name, s)))
            GLib.idle_add(self.status.set_text, "%s descarcat." % name if ok else "Descarcare esuata.")
            GLib.idle_add(self.refresh)
        threading.Thread(target=work, daemon=True).start()

    def _delete(self, name):
        try:
            req = urllib.request.Request(self.ai.base + "/api/delete",
                                         data=json.dumps({"name": name}).encode(), method="DELETE")
            urllib.request.urlopen(req, timeout=30)
        except Exception:
            pass
        self.refresh()
