#!/usr/bin/env python3
"""
BoboTranslate — document / text translation for BOBO OS (GTK4).
Backends tried in order: LibreTranslate (local, offline if running) → DeepL
(if API key) → Google (deep-translator). 50+ languages. Translates pasted text
or whole documents (txt/md/docx/pdf) preserving paragraph structure.
"""
import os
import sys
import json
import threading
import urllib.request

sys.path.insert(0, "/usr/share/bobo-office")
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

from shared import file_formats

LANGS = ["auto", "ro", "en", "fr", "de", "es", "it", "pt", "nl", "pl", "ru", "uk",
         "tr", "ar", "zh", "ja", "ko", "hi", "el", "cs", "sv", "da", "fi", "no",
         "hu", "bg", "hr", "sk", "sl", "et", "lv", "lt", "he", "id", "th", "vi"]
LIBRE = os.environ.get("BOBO_LIBRETRANSLATE", "http://127.0.0.1:5000")
DEEPL_KEY = os.environ.get("DEEPL_API_KEY", "")


def translate(text, src, tgt):
    """Try LibreTranslate → DeepL → Google. Returns translated text."""
    if not text.strip():
        return ""
    # 1) LibreTranslate local
    try:
        data = json.dumps({"q": text, "source": src, "target": tgt, "format": "text"}).encode()
        req = urllib.request.Request(LIBRE + "/translate", data=data,
                                     headers={"Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=20).read())
        if r.get("translatedText"):
            return r["translatedText"]
    except Exception:
        pass
    # 2) DeepL
    if DEEPL_KEY:
        try:
            import requests
            r = requests.post("https://api-free.deepl.com/v2/translate",
                              data={"auth_key": DEEPL_KEY, "text": text, "target_lang": tgt.upper()}, timeout=30)
            if r.ok:
                return r.json()["translations"][0]["text"]
        except Exception:
            pass
    # 3) Google via deep-translator
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source=src, target=tgt).translate(text)
    except Exception as e:
        return "[Traducere indisponibilă: %s — pornește LibreTranslate sau conectează-te la internet]" % e


class BoboTranslateWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboTranslate")
        self.set_default_size(860, 560)

        header = Gtk.HeaderBar(); self.set_titlebar(header)
        doc = Gtk.Button(label="Traduce document…"); doc.connect("clicked", lambda *a: self._doc()); header.pack_start(doc)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8, margin_start=10, margin_end=10)
        row = Gtk.Box(spacing=8)
        self.src = Gtk.DropDown.new_from_strings(LANGS)
        self.tgt = Gtk.DropDown.new_from_strings(LANGS); self.tgt.set_selected(LANGS.index("en"))
        swap = Gtk.Button.new_from_icon_name("object-flip-horizontal-symbolic"); swap.connect("clicked", lambda *a: self._swap())
        go = Gtk.Button(label="Traduce"); go.add_css_class("suggested-action"); go.connect("clicked", lambda *a: self._go())
        for w in (Gtk.Label(label="Din:"), self.src, swap, Gtk.Label(label="În:"), self.tgt, go):
            row.append(w)
        box.append(row)
        panes = Gtk.Box(spacing=8, homogeneous=True); panes.set_vexpand(True)
        self.inp = Gtk.TextView(); self.inp.set_wrap_mode(Gtk.WrapMode.WORD)
        self.out = Gtk.TextView(); self.out.set_wrap_mode(Gtk.WrapMode.WORD); self.out.set_editable(False)
        for v in (self.inp, self.out):
            sw = Gtk.ScrolledWindow(); sw.set_child(v); sw.set_hexpand(True); panes.append(sw)
        box.append(panes)
        self.status = Gtk.Label(xalign=0); self.status.add_css_class("dim-label"); box.append(self.status)
        self.set_child(box)

    def _swap(self):
        s, t = self.src.get_selected(), self.tgt.get_selected()
        self.src.set_selected(t if LANGS[t] != "auto" else self.src.get_selected()); self.tgt.set_selected(s)

    def _text(self, view):
        b = view.get_buffer(); return b.get_text(b.get_start_iter(), b.get_end_iter(), True)

    def _go(self):
        text = self._text(self.inp)
        src, tgt = LANGS[self.src.get_selected()], LANGS[self.tgt.get_selected()]
        self.status.set_text("Traduc…")
        def work():
            res = translate(text, src, tgt)
            GLib.idle_add(self.out.get_buffer().set_text, res)
            GLib.idle_add(self.status.set_text, "Gata.")
        threading.Thread(target=work, daemon=True).start()

    def _doc(self):
        d = Gtk.FileDialog(); d.open(self, None, self._doc_done)

    def _doc_done(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if f:
            self.inp.get_buffer().set_text(file_formats.read_text(f.get_path()))
            self.status.set_text("Document încărcat — apasă Traduce.")


class BoboTranslateApp(Gtk.Application):
    def __init__(self):
        from gi.repository import Gio
        super().__init__(application_id="os.bobo.Translate", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboTranslateWindow(self)
        self.win.present()


def main():
    if "--version" in sys.argv:
        print("BoboTranslate 1.0.0 (BOBO OS)"); return 0
    return BoboTranslateApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
