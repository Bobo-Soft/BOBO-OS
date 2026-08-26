#!/usr/bin/env python3
"""
BoboForm — form builder for BOBO OS (GTK4).
Build forms from fields (text/number/choice/checkbox/date), reorder, save the
definition as JSON, switch to Fill mode to collect responses into a local SQLite
DB, and view an automatic response summary. Offline; data stays local.
"""
import os
import sys
import json
import sqlite3

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

DATA = os.path.expanduser("~/.local/share/bobo-form")
FIELD_TYPES = ["text", "number", "choice", "checkbox", "date"]


class BoboFormWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboForm")
        self.set_default_size(760, 640)
        os.makedirs(DATA, exist_ok=True)
        self.fields = []           # [{label,type,options}]
        self.form_path = None

        header = Gtk.HeaderBar(); self.set_titlebar(header)
        for lbl, cb in [("Nou", lambda *a: self._new()), ("Deschide", lambda *a: self._open()),
                       ("Salvează", lambda *a: self._save())]:
            b = Gtk.Button(label=lbl); b.connect("clicked", cb); header.pack_start(b)
        fill = Gtk.Button(label="▶ Completează"); fill.add_css_class("suggested-action"); fill.connect("clicked", lambda *a: self._fill_mode()); header.pack_end(fill)
        resp = Gtk.Button(label="📊 Răspunsuri"); resp.connect("clicked", lambda *a: self._responses()); header.pack_end(resp)

        self.stack = Gtk.Stack(); self.set_child(self.stack)
        self.stack.add_named(self._builder(), "build")

    # ------------------------------------------------------------------ builder
    def _builder(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=10, margin_start=12, margin_end=12)
        self.title_e = Gtk.Entry(); self.title_e.set_placeholder_text("Titlul formularului")
        box.append(self.title_e)
        addrow = Gtk.Box(spacing=6)
        self.f_label = Gtk.Entry(); self.f_label.set_placeholder_text("Etichetă câmp"); self.f_label.set_hexpand(True)
        self.f_type = Gtk.DropDown.new_from_strings(FIELD_TYPES)
        self.f_opts = Gtk.Entry(); self.f_opts.set_placeholder_text("opțiuni (pt choice, virgulă)")
        add = Gtk.Button(label="+ Adaugă"); add.connect("clicked", lambda *a: self._add_field())
        for w in (self.f_label, self.f_type, self.f_opts, add):
            addrow.append(w)
        box.append(addrow)
        sw = Gtk.ScrolledWindow(); sw.set_vexpand(True)
        self.flist = Gtk.ListBox(); sw.set_child(self.flist); box.append(sw)
        return box

    def _add_field(self):
        lbl = self.f_label.get_text().strip()
        if not lbl:
            return
        self.fields.append({"label": lbl, "type": FIELD_TYPES[self.f_type.get_selected()],
                            "options": [o.strip() for o in self.f_opts.get_text().split(",") if o.strip()]})
        self.f_label.set_text(""); self.f_opts.set_text("")
        self._refresh_fields()

    def _refresh_fields(self):
        child = self.flist.get_first_child()
        while child:
            nxt = child.get_next_sibling(); self.flist.remove(child); child = nxt
        for i, f in enumerate(self.fields):
            row = Gtk.Box(spacing=8, margin_top=4, margin_bottom=4, margin_start=6)
            row.append(Gtk.Label(label="%s  [%s]" % (f["label"], f["type"]), xalign=0, hexpand=True))
            up = Gtk.Button.new_from_icon_name("go-up-symbolic"); up.connect("clicked", lambda b, i=i: self._move(i, -1)); row.append(up)
            dn = Gtk.Button.new_from_icon_name("go-down-symbolic"); dn.connect("clicked", lambda b, i=i: self._move(i, 1)); row.append(dn)
            rm = Gtk.Button.new_from_icon_name("user-trash-symbolic"); rm.connect("clicked", lambda b, i=i: self._rm(i)); row.append(rm)
            r = Gtk.ListBoxRow(); r.set_child(row); self.flist.append(r)

    def _move(self, i, d):
        j = i + d
        if 0 <= j < len(self.fields):
            self.fields[i], self.fields[j] = self.fields[j], self.fields[i]; self._refresh_fields()

    def _rm(self, i):
        del self.fields[i]; self._refresh_fields()

    def _new(self):
        self.fields = []; self.form_path = None; self.title_e.set_text(""); self._refresh_fields()

    # ------------------------------------------------------------------ IO
    def _save(self):
        d = Gtk.FileDialog(); d.set_initial_name((self.title_e.get_text() or "formular") + ".bform")
        d.save(self, None, self._save_done)

    def _save_done(self, dialog, res):
        try:
            f = dialog.save_finish(res)
        except GLib.Error:
            return
        if f:
            self.form_path = f.get_path()
            json.dump({"title": self.title_e.get_text(), "fields": self.fields},
                      open(self.form_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    def _open(self):
        d = Gtk.FileDialog(); d.open(self, None, self._open_done)

    def _open_done(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if f:
            data = json.load(open(f.get_path(), encoding="utf-8"))
            self.title_e.set_text(data.get("title", "")); self.fields = data.get("fields", [])
            self.form_path = f.get_path(); self._refresh_fields()

    def _db(self):
        name = os.path.splitext(os.path.basename(self.form_path or "form"))[0]
        con = sqlite3.connect(os.path.join(DATA, name + ".db"))
        cols = ", ".join('"%s" TEXT' % f["label"] for f in self.fields) or "dummy TEXT"
        con.execute("CREATE TABLE IF NOT EXISTS responses (id INTEGER PRIMARY KEY, %s)" % cols)
        return con

    # ------------------------------------------------------------------ fill
    def _fill_mode(self):
        if not self.fields:
            return
        win = Gtk.Window(title="Completează: %s" % self.title_e.get_text(), transient_for=self, modal=True)
        win.set_default_size(460, 520)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        widgets = {}
        for f in self.fields:
            box.append(Gtk.Label(label=f["label"], xalign=0))
            if f["type"] == "choice" and f["options"]:
                w = Gtk.DropDown.new_from_strings(f["options"])
            elif f["type"] == "checkbox":
                w = Gtk.CheckButton()
            else:
                w = Gtk.Entry()
            widgets[f["label"]] = (w, f["type"]); box.append(w)
        submit = Gtk.Button(label="Trimite"); submit.add_css_class("suggested-action")

        def do_submit(*a):
            vals = {}
            for lab, (w, typ) in widgets.items():
                if typ == "choice":
                    it = w.get_selected_item(); vals[lab] = it.get_string() if it else ""
                elif typ == "checkbox":
                    vals[lab] = "da" if w.get_active() else "nu"
                else:
                    vals[lab] = w.get_text()
            con = self._db()
            cols = ",".join('"%s"' % k for k in vals)
            ph = ",".join("?" for _ in vals)
            con.execute("INSERT INTO responses (%s) VALUES (%s)" % (cols, ph), list(vals.values()))
            con.commit(); con.close()
            win.close()
            GLib.spawn_command_line_async("notify-send BoboForm 'Răspuns înregistrat'")
        submit.connect("clicked", do_submit)
        box.append(submit)
        sw = Gtk.ScrolledWindow(); sw.set_child(box); win.set_child(sw); win.present()

    def _responses(self):
        if not self.fields:
            return
        con = self._db()
        rows = con.execute("SELECT * FROM responses").fetchall()
        con.close()
        win = Gtk.Window(title="Răspunsuri (%d)" % len(rows), transient_for=self)
        win.set_default_size(560, 400)
        tv = Gtk.TextView(); tv.set_editable(False); tv.set_monospace(True)
        summary = "Total răspunsuri: %d\n\n" % len(rows)
        # simple per-field frequency for choice/checkbox
        for i, f in enumerate(self.fields):
            if f["type"] in ("choice", "checkbox"):
                freq = {}
                for r in rows:
                    v = r[i + 1] if i + 1 < len(r) else ""
                    freq[v] = freq.get(v, 0) + 1
                summary += "%s: %s\n" % (f["label"], ", ".join("%s=%d" % kv for kv in freq.items()))
        tv.get_buffer().set_text(summary or "(fără răspunsuri)")
        sw = Gtk.ScrolledWindow(); sw.set_child(tv); win.set_child(sw); win.present()


class BoboFormApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.Form", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboFormWindow(self)
        self.win.present()


def main():
    if "--version" in sys.argv:
        print("BoboForm 1.0.0 (BOBO OS)"); return 0
    return BoboFormApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
