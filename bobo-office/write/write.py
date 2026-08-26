#!/usr/bin/env python3
"""
BoboWrite — word processor for BOBO OS (GTK4).
Rich text (bold/italic/underline, H1–H3, lists), multi-document tabs,
Find&Replace (regex), spell check (gspell if available), AI actions via
BoboAssist, image insert, and export to DOCX/PDF/ODT/HTML/Markdown/TXT/EPUB.
"""
import os
import re
import sys
import threading

sys.path.insert(0, "/usr/share/bobo-office")
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Pango, Gdk  # noqa: E402

from shared import file_formats
from write.ai_writer import AIWriter
from write.history_learner import HistoryLearner

try:
    gi.require_version("Gspell", "1")
    from gi.repository import Gspell
    HAVE_SPELL = True
except Exception:
    HAVE_SPELL = False


class WriteTab(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()
        self.set_vexpand(True)
        self.path = None
        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.view.set_left_margin(24); self.view.set_right_margin(24)
        self.view.set_top_margin(16); self.view.set_monospace(False)
        self.buffer = self.view.get_buffer()
        self._make_tags()
        self.set_child(self.view)
        if HAVE_SPELL:
            try:
                checker = Gspell.Checker.new(Gspell.language_get_default())
                Gspell.TextBuffer.get_from_gtk_text_buffer(self.buffer).set_spell_checker(checker)
                Gspell.TextView.get_from_gtk_text_view(self.view).set_inline_spell_checking(True)
            except Exception:
                pass

    def _make_tags(self):
        t = self.buffer
        t.create_tag("bold", weight=Pango.Weight.BOLD)
        t.create_tag("italic", style=Pango.Style.ITALIC)
        t.create_tag("underline", underline=Pango.Underline.SINGLE)
        t.create_tag("h1", weight=Pango.Weight.BOLD, scale=1.8)
        t.create_tag("h2", weight=Pango.Weight.BOLD, scale=1.5)
        t.create_tag("h3", weight=Pango.Weight.BOLD, scale=1.25)

    def apply(self, tag):
        b = self.buffer
        if b.get_has_selection():
            s, e = b.get_selection_bounds()
            b.apply_tag_by_name(tag, s, e)

    def get_text(self):
        s, e = self.buffer.get_bounds()
        return self.buffer.get_text(s, e, True)

    def set_text(self, text):
        self.buffer.set_text(text)


class BoboWriteWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboWrite")
        self.set_default_size(1000, 760)
        self.ai = AIWriter()
        self.learner = HistoryLearner()

        header = Gtk.HeaderBar(); self.set_titlebar(header)
        for icon, tip, cb in [
            ("document-new-symbolic", "Nou (Ctrl+T)", lambda *a: self.new_tab()),
            ("document-open-symbolic", "Deschide (Ctrl+O)", lambda *a: self.open_dialog()),
            ("document-save-symbolic", "Salvează (Ctrl+S)", lambda *a: self.save()),
        ]:
            b = Gtk.Button.new_from_icon_name(icon); b.set_tooltip_text(tip); b.connect("clicked", cb)
            header.pack_start(b)
        exp = Gtk.MenuButton(label="Export"); exp.set_menu_model(self._export_menu()); header.pack_end(exp)
        aibtn = Gtk.MenuButton(icon_name="starred-symbolic"); aibtn.set_tooltip_text("AI")
        aibtn.set_menu_model(self._ai_menu()); header.pack_end(aibtn)
        self._install_actions()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(self._toolbar())
        self.find_rev = Gtk.Revealer(); self.find_rev.set_child(self._find_bar()); root.append(self.find_rev)
        self.notebook = Gtk.Notebook(); self.notebook.set_vexpand(True); root.append(self.notebook)
        self.status = Gtk.Label(xalign=0); self.status.add_css_class("dim-label"); root.append(self.status)
        self.set_child(root)
        self._install_shortcuts()
        self.new_tab()

    # ------------------------------------------------------------------ UI bits
    def _toolbar(self):
        bar = Gtk.Box(spacing=4, margin_top=4, margin_start=6, margin_end=6)
        for label, tag in [("B", "bold"), ("I", "italic"), ("U", "underline"),
                           ("H1", "h1"), ("H2", "h2"), ("H3", "h3")]:
            b = Gtk.Button(label=label); b.connect("clicked", lambda x, t=tag: self.cur().apply(t))
            bar.append(b)
        bullet = Gtk.Button(label="• Listă"); bullet.connect("clicked", lambda *a: self._insert("• "))
        bar.append(bullet)
        img = Gtk.Button(label="🖼 Imagine"); img.connect("clicked", lambda *a: self._insert_image())
        bar.append(img)
        return bar

    def _find_bar(self):
        bar = Gtk.Box(spacing=6, margin_top=4, margin_start=6, margin_end=6, margin_bottom=4)
        self.find_e = Gtk.SearchEntry(); self.find_e.set_placeholder_text("Caută (regex)")
        self.repl_e = Gtk.Entry(); self.repl_e.set_placeholder_text("Înlocuiește")
        self.regex_c = Gtk.CheckButton(label="regex")
        nb = Gtk.Button(label="Următor"); nb.connect("clicked", lambda *a: self.find_next())
        rb = Gtk.Button(label="Înlocuiește tot"); rb.connect("clicked", lambda *a: self.replace_all())
        for w in (self.find_e, nb, self.repl_e, rb, self.regex_c):
            bar.append(w)
        return bar

    def _export_menu(self):
        m = Gio.Menu()
        for fmt in ["docx", "pdf", "odt", "html", "md", "txt", "epub"]:
            m.append(fmt.upper(), "win.export::" + fmt)
        return m

    def _ai_menu(self):
        m = Gio.Menu()
        for label, act in [("Continuă", "continue"), ("Rescrie formal", "formal"),
                          ("Concis", "concise"), ("Rezumat", "summary"),
                          ("Corectează", "fix"), ("Traduce EN", "translate_en")]:
            m.append(label, "win.ai::" + act)
        return m

    def _install_actions(self):
        exp = Gio.SimpleAction.new("export", GLib.VariantType.new("s"))
        exp.connect("activate", lambda a, p: self.export(p.get_string()))
        self.add_action(exp)
        ai = Gio.SimpleAction.new("ai", GLib.VariantType.new("s"))
        ai.connect("activate", lambda a, p: self.ai_action(p.get_string()))
        self.add_action(ai)

    # ------------------------------------------------------------------ tabs
    def new_tab(self, path=None):
        tab = WriteTab()
        name = os.path.basename(path) if path else "Document"
        label = Gtk.Label(label=name)
        idx = self.notebook.append_page(tab, label)
        self.notebook.set_current_page(idx)
        if path:
            tab.path = path
            tab.set_text(file_formats.read_text(path) if not path.endswith(".bwrite") else self._read_native(path))
        return tab

    def cur(self):
        p = self.notebook.get_current_page()
        return self.notebook.get_nth_page(p)

    def _read_native(self, path):
        import json
        try:
            with open(path) as fh:
                return json.load(fh).get("content", {}).get("text", "")
        except Exception:
            return ""

    # ------------------------------------------------------------------ file IO
    def open_dialog(self):
        d = Gtk.FileDialog(); d.open_multiple(self, None, self._open_done)

    def _open_done(self, dialog, res):
        try:
            files = dialog.open_multiple_finish(res)
        except GLib.Error:
            return
        for i in range(files.get_n_items()):
            p = files.get_item(i).get_path()
            if p:
                self.new_tab(p)

    def save(self):
        tab = self.cur()
        if not tab:
            return
        if tab.path and tab.path.endswith(".bwrite"):
            self._save_native(tab)
        else:
            d = Gtk.FileDialog(); d.set_initial_name((os.path.basename(tab.path) if tab.path else "document") + ".bwrite")
            d.save(self, None, lambda dd, r: self._save_as(dd, r, tab))

    def _save_as(self, dialog, res, tab):
        try:
            f = dialog.save_finish(res)
        except GLib.Error:
            return
        if f:
            tab.path = f.get_path()
            self._save_native(tab)

    def _save_native(self, tab):
        import json
        text = tab.get_text()
        self.learner.learn_text(text)
        data = {"title": os.path.basename(tab.path), "content": {"text": text}}
        with open(tab.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        self.status.set_text("Salvat: %s" % tab.path)

    def export(self, fmt):
        tab = self.cur()
        if not tab:
            return
        d = Gtk.FileDialog(); d.set_initial_name("export." + fmt)
        d.save(self, None, lambda dd, r: self._do_export(dd, r, tab, fmt))

    def _do_export(self, dialog, res, tab, fmt):
        try:
            f = dialog.save_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        out = f.get_path(); text = tab.get_text(); ok = False
        if fmt == "txt":
            open(out, "w", encoding="utf-8").write(text); ok = True
        elif fmt == "md":
            open(out, "w", encoding="utf-8").write(text); ok = True
        elif fmt == "docx":
            ok = file_formats.write_docx(out, text.split("\n"))
        elif fmt == "pdf":
            ok = file_formats.write_pdf_from_text(out, text)
        else:  # odt/html/epub via pandoc
            ok = file_formats.export_via_pandoc(text, out)
        self.status.set_text(("Exportat %s: %s" % (fmt, out)) if ok else "Export eșuat (lipsă backend?)")

    # ------------------------------------------------------------------ find/replace
    def find_next(self):
        tab = self.cur()
        if not tab:
            return
        text = tab.get_text(); term = self.find_e.get_text()
        if not term:
            return
        flags = 0 if self.regex_c.get_active() else re.escape(term)
        pattern = term if self.regex_c.get_active() else re.escape(term)
        m = re.search(pattern, text)
        if m:
            b = tab.buffer
            s = b.get_iter_at_offset(m.start()); e = b.get_iter_at_offset(m.end())
            b.select_range(s, e); tab.view.scroll_to_iter(s, 0.1, False, 0, 0)

    def replace_all(self):
        tab = self.cur()
        if not tab:
            return
        text = tab.get_text(); term = self.find_e.get_text(); repl = self.repl_e.get_text()
        try:
            pattern = term if self.regex_c.get_active() else re.escape(term)
            new = re.sub(pattern, repl, text)
            tab.set_text(new)
            self.status.set_text("Înlocuit tot.")
        except re.error as e:
            self.status.set_text("Regex invalid: %s" % e)

    # ------------------------------------------------------------------ AI
    def ai_action(self, action):
        tab = self.cur()
        if not tab:
            return
        self.status.set_text("AI (%s)…" % action)
        doc = tab.get_text()
        def work():
            result = self.ai.run(action, doc)
            GLib.idle_add(self._ai_result, tab, action, result)
        threading.Thread(target=work, daemon=True).start()

    def _ai_result(self, tab, action, result):
        b = tab.buffer
        if action in ("continue",):
            b.insert(b.get_end_iter(), "\n" + result)
        else:
            b.insert(b.get_iter_at_mark(b.get_insert()), "\n\n[AI %s]\n%s\n" % (action, result))
        self.status.set_text("AI gata.")

    # ------------------------------------------------------------------ misc
    def _insert(self, s):
        tab = self.cur()
        if tab:
            tab.buffer.insert_at_cursor(s)

    def _insert_image(self):
        d = Gtk.FileDialog()
        d.open(self, None, self._img_done)

    def _img_done(self, dialog, res):
        try:
            f = dialog.open_finish(res)
            if f:
                self._insert("[imagine: %s]\n" % f.get_path())
        except GLib.Error:
            pass

    def _install_shortcuts(self):
        km = {"<Ctrl>t": self.new_tab, "<Ctrl>o": self.open_dialog, "<Ctrl>s": self.save,
              "<Ctrl>f": lambda: self.find_rev.set_reveal_child(not self.find_rev.get_reveal_child()),
              "<Ctrl>h": lambda: self.find_rev.set_reveal_child(True),
              "<Ctrl>b": lambda: self.cur().apply("bold"),
              "<Ctrl>i": lambda: self.cur().apply("italic")}
        ctl = Gtk.ShortcutController(); ctl.set_scope(Gtk.ShortcutScope.GLOBAL)
        for accel, fn in km.items():
            t = Gtk.ShortcutTrigger.parse_string(accel)
            a = Gtk.CallbackAction.new(lambda w, ar, f=fn: (f(), True)[1])
            ctl.add_shortcut(Gtk.Shortcut.new(t, a))
        self.add_controller(ctl)


class BoboWriteApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.Write", flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboWriteWindow(self)
        self.win.present()

    def do_open(self, files, n, hint):
        self.do_activate()
        for f in files:
            if f.get_path():
                self.win.new_tab(f.get_path())


def main():
    if "--version" in sys.argv:
        print("BoboWrite 1.0.0 (BOBO OS)"); return 0
    return BoboWriteApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
