#!/usr/bin/env python3
"""
BoboHub — central launcher for Bobo Office (GTK4).
A visual grid of the Office apps, recent files (shared recent registry), and a
BoboAssist toggle. Launched with Super+O.
"""
import os
import sys
import subprocess

sys.path.insert(0, "/usr/share/bobo-office")
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio  # noqa: E402

try:
    from shared.document_base import recent_files
except Exception:
    def recent_files():
        return []

APPS = [
    ("BoboWrite", "bobo-write", "Document text"),
    ("BoboCalc", "bobo-calc", "Foaie de calcul"),
    ("BoboPresent", "bobo-present", "Prezentări"),
    ("BoboChart", "bobo-chart", "Grafice"),
    ("BoboForm", "bobo-form", "Formulare"),
    ("BoboSign", "bobo-sign", "Semnătură"),
    ("BoboTranslate", "bobo-translate", "Traducere"),
    ("BoboMind", "bobo-mind", "Mind maps"),
    ("BoboAssist", "bobo-assist", "Asistent AI"),
]


class BoboHubWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboHub")
        self.set_default_size(720, 560)

        header = Gtk.HeaderBar(); self.set_titlebar(header)
        title = Gtk.Label(); title.set_markup("<b>BoboHub</b>  ·  Bobo Office"); header.set_title_widget(title)
        assist = Gtk.Button(label="🤖 BoboAssist"); assist.connect("clicked", lambda *a: self._launch("bobo-assist"))
        header.pack_end(assist)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=12, margin_bottom=12, margin_start=14, margin_end=14)
        root.append(self._section("Aplicații"))
        flow = Gtk.FlowBox(); flow.set_max_children_per_line(4); flow.set_selection_mode(Gtk.SelectionMode.NONE)
        for name, cmd, desc in APPS:
            flow.append(self._tile(name, cmd, desc))
        root.append(flow)

        root.append(self._section("Fișiere recente"))
        rsw = Gtk.ScrolledWindow(); rsw.set_vexpand(True)
        self.recent = Gtk.ListBox()
        rsw.set_child(self.recent); root.append(rsw)
        self._load_recent()
        self.set_child(root)

    def _section(self, text):
        l = Gtk.Label(xalign=0); l.set_markup("<b>%s</b>" % text); return l

    def _tile(self, name, cmd, desc):
        b = Gtk.Button(); b.set_size_request(150, 90)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        icon = Gtk.Image.new_from_icon_name(cmd if os.path.exists("/usr/share/icons/hicolor/scalable/apps/%s.svg" % cmd) else "application-x-executable")
        icon.set_pixel_size(40)
        nm = Gtk.Label(label=name); ds = Gtk.Label(label=desc); ds.add_css_class("dim-label")
        inner.append(icon); inner.append(nm); inner.append(ds)
        b.set_child(inner)
        b.connect("clicked", lambda x, c=cmd: self._launch(c))
        return b

    def _load_recent(self):
        for f in recent_files()[:20]:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label=os.path.basename(f), xalign=0, margin_top=4, margin_bottom=4, margin_start=6))
            row._path = f
            self.recent.append(row)
        self.recent.connect("row-activated", self._open_recent)
        if not recent_files():
            self.recent.append(Gtk.Label(label="(niciun fișier recent)", xalign=0, margin_top=8))

    def _open_recent(self, lb, row):
        p = getattr(row, "_path", None)
        if not p:
            return
        ext = os.path.splitext(p)[1].lower()
        cmd = {".bwrite": "bobo-write", ".bcalc": "bobo-calc", ".bpresent": "bobo-present",
               ".bform": "bobo-form"}.get(ext, "xdg-open")
        try:
            subprocess.Popen([cmd, p])
        except Exception:
            subprocess.Popen(["xdg-open", p])

    def _launch(self, cmd):
        try:
            subprocess.Popen([cmd])
        except Exception as e:
            print("[hub] %s" % e)


class BoboHubApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.Hub", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboHubWindow(self)
        self.win.present()


def main():
    if "--version" in sys.argv:
        print("BoboHub 1.0.0 (BOBO OS)"); return 0
    return BoboHubApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
