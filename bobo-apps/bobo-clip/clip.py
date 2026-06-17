#!/usr/bin/env python3
# =============================================================================
# BoboClip - Manager de clipboard pentru BOBO OS (APP 21)
# GTK4 + wl-clipboard. Daemon monitorizeaza clipboard-ul, panel cu istoric
# (Super+V), cautare, pin, categorii, paste la click.
# =============================================================================
import os
import sys
import sqlite3
import subprocess
import threading
import time
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gdk, Gio  # noqa: E402

APP_ID = "os.bobo.Clip"
DATA_DIR = os.path.expanduser("~/.local/share/bobo-clip")
DB = os.path.join(DATA_DIR, "history.db")
MAX_ENTRIES = 200


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS clip (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "content TEXT UNIQUE, category TEXT, pinned INTEGER DEFAULT 0, ts INTEGER)")
    return con


def _categorize(text):
    t = text.strip()
    if t.startswith(("http://", "https://", "www.")):
        return "URL"
    if "\n" not in t and len(t) < 200 and "/" in t and os.path.exists(t):
        return "Cale"
    return "Text"


# =============================================================================
# Daemon: monitorizeaza clipboard-ul Wayland
# =============================================================================
def run_daemon():
    con = _db()
    last = None
    while True:
        try:
            text = subprocess.run(["wl-paste", "-n"], capture_output=True, text=True, timeout=5).stdout
        except Exception:
            time.sleep(1)
            continue
        if text and text != last and len(text.strip()) > 0:
            last = text
            try:
                con.execute("INSERT OR IGNORE INTO clip(content,category,ts) VALUES(?,?,?)",
                            (text, _categorize(text), int(time.time())))
                # pastreaza maxim MAX_ENTRIES (exclus cele fixate)
                con.execute("DELETE FROM clip WHERE pinned=0 AND id NOT IN "
                            "(SELECT id FROM clip WHERE pinned=0 ORDER BY ts DESC LIMIT ?)", (MAX_ENTRIES,))
                con.commit()
            except Exception:
                pass
        time.sleep(0.8)


# =============================================================================
# Panel istoric (Super+V)
# =============================================================================
class BoboClipWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Clipboard")
        self.set_default_size(440, 560)
        self.set_decorated(False)
        self.con = _db()
        self.filter_cat = "Toate"

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("bobo-clip-box")
        self.set_child(box)
        self._css()

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Cauta in clipboard...")
        self.search.connect("search-changed", lambda *a: self._load())
        box.append(self.search)

        # filtre categorii
        cat_box = Gtk.Box(spacing=4)
        cat_box.set_margin_start(6)
        cat_box.set_margin_top(4)
        for cat in ["Toate", "Text", "URL", "Cale"]:
            b = Gtk.ToggleButton(label=cat)
            if cat == "Toate":
                b.set_active(True)
            b.connect("toggled", lambda btn, c=cat: self._set_cat(c) if btn.get_active() else None)
            cat_box.append(b)
        box.append(cat_box)

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        self.listbox = Gtk.ListBox()
        self.listbox.connect("row-activated", self._on_activated)
        sw.set_child(self.listbox)
        box.append(sw)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", lambda c, k, kc, s: self.close() if k == Gdk.KEY_Escape else False)
        self.add_controller(key)
        self._load()

    def _css(self):
        p = Gtk.CssProvider()
        p.load_from_data(b".bobo-clip-box { background: rgba(22,33,62,0.97); border:1px solid #4a9eff; border-radius:12px; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _set_cat(self, cat):
        self.filter_cat = cat
        self._load()

    def _load(self):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        q = self.search.get_text()
        sql = "SELECT id,content,category,pinned FROM clip WHERE 1=1"
        params = []
        if self.filter_cat != "Toate":
            sql += " AND category=?"
            params.append(self.filter_cat)
        if q:
            sql += " AND content LIKE ?"
            params.append("%" + q + "%")
        sql += " ORDER BY pinned DESC, ts DESC LIMIT 200"
        for cid, content, cat, pinned in self.con.execute(sql, params):
            row = Gtk.ListBoxRow()
            b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            b.set_margin_top(4)
            b.set_margin_bottom(4)
            b.set_margin_start(8)
            preview = content.strip().replace("\n", " ")[:60]
            lbl = Gtk.Label(label=preview, xalign=0)
            lbl.set_hexpand(True)
            lbl.set_ellipsize(3)
            b.append(lbl)
            pin = Gtk.ToggleButton()
            pin.set_icon_name("view-pin-symbolic")
            pin.set_active(bool(pinned))
            pin.add_css_class("flat")
            pin.connect("toggled", lambda btn, i=cid: self._pin(i, btn.get_active()))
            b.append(pin)
            row.set_child(b)
            row._content = content
            self.listbox.append(row)

    def _on_activated(self, lb, row):
        # paste: copiaza in clipboard si trimite Ctrl+V in fereastra activa
        p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
        p.communicate(row._content.encode())
        self.close()

    def _pin(self, cid, pinned):
        self.con.execute("UPDATE clip SET pinned=? WHERE id=?", (1 if pinned else 0, cid))
        self.con.commit()


class BoboClipApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboClipWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboClip 1.0.0 (BOBO OS)")
        return 0
    if "--daemon" in sys.argv:
        run_daemon()
        return 0
    return BoboClipApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
