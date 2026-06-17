#!/usr/bin/env python3
# =============================================================================
# BoboText - Editor de text cu syntax highlighting pentru BOBO OS (APP 04)
# GTK4 + GtkSourceView 5. Tab-uri, find/replace regex, go-to-line, comment,
# numere linii, session restore, auto-detect limbaj.
# =============================================================================
import os
import sys
import json
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
from gi.repository import Gtk, GtkSource, GLib, Gio, Gdk, Pango  # noqa: E402

APP_ID = "os.bobo.Text"
SESSION_FILE = os.path.expanduser("~/.local/share/bobo-text/session.json")


class EditorTab(Gtk.Box):
    """O fila = buffer SourceView + scroll. Tine minte calea fisierului."""

    def __init__(self, path=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.path = path
        self.lang_manager = GtkSource.LanguageManager.get_default()
        self.style_manager = GtkSource.StyleSchemeManager.get_default()

        self.buffer = GtkSource.Buffer()
        scheme = self.style_manager.get_scheme("oblivion") or self.style_manager.get_scheme("classic-dark")
        if scheme:
            self.buffer.set_style_scheme(scheme)
        self.view = GtkSource.View(buffer=self.buffer)
        self.view.set_show_line_numbers(True)
        self.view.set_highlight_current_line(True)
        self.view.set_auto_indent(True)
        self.view.set_insert_spaces_instead_of_tabs(True)
        self.view.set_tab_width(4)
        self.view.set_monospace(True)
        self.view.set_show_line_marks(False)
        self.view.set_smart_backspace(True)

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(self.view)
        self.append(sw)

        if path and os.path.isfile(path):
            self.load(path)

    def load(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except Exception as e:
            text = "// Eroare la deschidere: %s" % e
        self.buffer.set_text(text)
        self.path = path
        lang = self.lang_manager.guess_language(path, None)
        if lang:
            self.buffer.set_language(lang)
        self.buffer.set_modified(False)

    def save(self, path=None):
        target = path or self.path
        if not target:
            return False
        start, end = self.buffer.get_bounds()
        text = self.buffer.get_text(start, end, True)
        try:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(text)
            self.path = target
            self.buffer.set_modified(False)
            lang = self.lang_manager.guess_language(target, None)
            if lang:
                self.buffer.set_language(lang)
            return True
        except Exception as e:
            print("[bobo-text] salvare esuata: %s" % e, file=sys.stderr)
            return False

    def title(self):
        name = os.path.basename(self.path) if self.path else "Nou"
        return ("*" if self.buffer.get_modified() else "") + name


class BoboTextWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboText")
        self.set_default_size(900, 640)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        for icon, tip, cb in [
            ("document-new-symbolic", "Tab nou (Ctrl+T)", lambda *a: self.new_tab()),
            ("document-open-symbolic", "Deschide (Ctrl+O)", lambda *a: self.open_dialog()),
            ("document-save-symbolic", "Salveaza (Ctrl+S)", lambda *a: self.save_current()),
        ]:
            b = Gtk.Button.new_from_icon_name(icon)
            b.set_tooltip_text(tip)
            b.connect("clicked", cb)
            header.pack_start(b)

        find_btn = Gtk.Button.new_from_icon_name("edit-find-replace-symbolic")
        find_btn.set_tooltip_text("Cauta/Inlocuieste (Ctrl+H)")
        find_btn.connect("clicked", lambda *a: self.toggle_find())
        header.pack_end(find_btn)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        # bara find/replace (ascunsa initial)
        self.find_bar = self._build_find_bar()
        self.find_revealer = Gtk.Revealer()
        self.find_revealer.set_child(self.find_bar)
        root.append(self.find_revealer)

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.set_vexpand(True)
        root.append(self.notebook)

        self._install_shortcuts()
        if not self._restore_session():
            self.new_tab()

    # --------------------------------------------------------- tab mgmt
    def new_tab(self, path=None):
        tab = EditorTab(path)
        label = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        title = Gtk.Label(label=tab.title())
        close = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close.add_css_class("flat")
        close.connect("clicked", lambda *a: self.close_tab(tab))
        label.append(title)
        label.append(close)
        tab._title_label = title
        tab.buffer.connect("modified-changed", lambda *a: title.set_text(tab.title()))
        idx = self.notebook.append_page(tab, label)
        self.notebook.set_current_page(idx)
        self.notebook.set_tab_reorderable(tab, True)
        return tab

    def current_tab(self):
        page = self.notebook.get_current_page()
        return self.notebook.get_nth_page(page) if page >= 0 else None

    def close_tab(self, tab):
        idx = self.notebook.page_num(tab)
        if idx >= 0:
            self.notebook.remove_page(idx)
        if self.notebook.get_n_pages() == 0:
            self.new_tab()

    # --------------------------------------------------------- file ops
    def open_dialog(self):
        dialog = Gtk.FileDialog()
        dialog.open_multiple(self, None, self._open_finished)

    def _open_finished(self, dialog, res):
        try:
            files = dialog.open_multiple_finish(res)
        except GLib.Error:
            return
        for i in range(files.get_n_items()):
            p = files.get_item(i).get_path()
            if p:
                self.new_tab(p)

    def save_current(self):
        tab = self.current_tab()
        if not tab:
            return
        if tab.path:
            tab.save()
        else:
            dialog = Gtk.FileDialog()
            dialog.save(self, None, lambda d, r: self._save_as_finished(d, r, tab))

    def _save_as_finished(self, dialog, res, tab):
        try:
            f = dialog.save_finish(res)
            if f:
                tab.save(f.get_path())
                tab._title_label.set_text(tab.title())
        except GLib.Error:
            pass

    # --------------------------------------------------------- find/replace
    def _build_find_bar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.set_margin_top(4)
        bar.set_margin_bottom(4)
        bar.set_margin_start(6)
        bar.set_margin_end(6)
        self.find_entry = Gtk.SearchEntry()
        self.find_entry.set_placeholder_text("Cauta")
        self.find_entry.connect("activate", lambda *a: self.find_next())
        self.replace_entry = Gtk.Entry()
        self.replace_entry.set_placeholder_text("Inlocuieste cu")
        self.regex_check = Gtk.CheckButton(label="Regex")
        self.case_check = Gtk.CheckButton(label="Case")
        next_btn = Gtk.Button(label="Urmator")
        next_btn.connect("clicked", lambda *a: self.find_next())
        repl_btn = Gtk.Button(label="Inlocuieste")
        repl_btn.connect("clicked", lambda *a: self.replace_one())
        repl_all = Gtk.Button(label="Toate")
        repl_all.connect("clicked", lambda *a: self.replace_all())
        for w in [self.find_entry, next_btn, self.replace_entry, repl_btn, repl_all, self.regex_check, self.case_check]:
            bar.append(w)
        return bar

    def toggle_find(self):
        self.find_revealer.set_reveal_child(not self.find_revealer.get_reveal_child())
        if self.find_revealer.get_reveal_child():
            self.find_entry.grab_focus()

    def _search_settings(self):
        ctx_settings = GtkSource.SearchSettings()
        ctx_settings.set_search_text(self.find_entry.get_text())
        ctx_settings.set_regex_enabled(self.regex_check.get_active())
        ctx_settings.set_case_sensitive(self.case_check.get_active())
        ctx_settings.set_wrap_around(True)
        return ctx_settings

    def find_next(self):
        tab = self.current_tab()
        if not tab:
            return
        ctx = GtkSource.SearchContext.new(tab.buffer, self._search_settings())
        ins = tab.buffer.get_iter_at_mark(tab.buffer.get_insert())
        found, ms, me, wrapped = ctx.forward(ins)
        if found:
            tab.buffer.select_range(ms, me)
            tab.view.scroll_to_iter(ms, 0.1, False, 0, 0)

    def replace_one(self):
        tab = self.current_tab()
        if not tab:
            return
        ctx = GtkSource.SearchContext.new(tab.buffer, self._search_settings())
        ins = tab.buffer.get_iter_at_mark(tab.buffer.get_insert())
        found, ms, me, wrapped = ctx.forward(ins)
        if found:
            repl = self.replace_entry.get_text()
            ctx.replace(ms, me, repl, -1)
            self.find_next()

    def replace_all(self):
        tab = self.current_tab()
        if not tab:
            return
        ctx = GtkSource.SearchContext.new(tab.buffer, self._search_settings())
        try:
            ctx.replace_all(self.replace_entry.get_text(), -1)
        except GLib.Error as e:
            print("[bobo-text] replace_all: %s" % e)

    # --------------------------------------------------------- edit helpers
    def goto_line(self):
        tab = self.current_tab()
        if not tab:
            return
        dialog = Gtk.Window(title="Salt la linie", transient_for=self, modal=True)
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        spin = Gtk.SpinButton.new_with_range(1, tab.buffer.get_line_count(), 1)
        go = Gtk.Button(label="Du-te")

        def do_go(*a):
            line = int(spin.get_value()) - 1
            it = tab.buffer.get_iter_at_line(line)[1]
            tab.buffer.place_cursor(it)
            tab.view.scroll_to_iter(it, 0.1, False, 0, 0)
            dialog.close()
        go.connect("clicked", do_go)
        b.append(spin)
        b.append(go)
        dialog.set_child(b)
        dialog.present()

    def toggle_comment(self):
        tab = self.current_tab()
        if not tab:
            return
        buf = tab.buffer
        if not buf.get_has_selection():
            start = buf.get_iter_at_mark(buf.get_insert())
            start.set_line_offset(0)
            end = start.copy()
            end.forward_to_line_end()
        else:
            start, end = buf.get_selection_bounds()
        lang = buf.get_language()
        prefix = "# "
        if lang and lang.get_id() in ("c", "cpp", "js", "json", "css", "java", "rust"):
            prefix = "// "
        text = buf.get_text(start, end, True)
        lines = text.split("\n")
        commented = all(l.strip().startswith(prefix.strip()) for l in lines if l.strip())
        new_lines = []
        for l in lines:
            if commented:
                idx = l.find(prefix.strip())
                new_lines.append(l[:idx] + l[idx + len(prefix):] if idx >= 0 else l)
            else:
                new_lines.append(prefix + l if l.strip() else l)
        buf.delete(start, end)
        buf.insert(start, "\n".join(new_lines))

    def duplicate_line(self):
        tab = self.current_tab()
        if not tab:
            return
        buf = tab.buffer
        cur = buf.get_iter_at_mark(buf.get_insert())
        start = cur.copy()
        start.set_line_offset(0)
        end = cur.copy()
        end.forward_to_line_end()
        line = buf.get_text(start, end, True)
        buf.insert(end, "\n" + line)

    # --------------------------------------------------------- shortcuts
    def _install_shortcuts(self):
        keymap = {
            "<Ctrl>t": lambda: self.new_tab(),
            "<Ctrl>o": lambda: self.open_dialog(),
            "<Ctrl>s": lambda: self.save_current(),
            "<Ctrl>w": lambda: self.close_tab(self.current_tab()),
            "<Ctrl>h": lambda: self.toggle_find(),
            "<Ctrl>f": lambda: self.toggle_find(),
            "<Ctrl>g": lambda: self.goto_line(),
            "<Ctrl>slash": lambda: self.toggle_comment(),
            "<Ctrl>d": lambda: self.duplicate_line(),
            "<Ctrl>Page_Down": lambda: self.notebook.next_page(),
            "<Ctrl>Page_Up": lambda: self.notebook.prev_page(),
        }
        ctrl = Gtk.ShortcutController()
        ctrl.set_scope(Gtk.ShortcutScope.GLOBAL)
        for accel, fn in keymap.items():
            trig = Gtk.ShortcutTrigger.parse_string(accel)
            act = Gtk.CallbackAction.new(lambda w, a, f=fn: (f(), True)[1])
            ctrl.add_shortcut(Gtk.Shortcut.new(trig, act))
        self.add_controller(ctrl)

    # --------------------------------------------------------- session
    def _restore_session(self):
        data = []
        try:
            with open(SESSION_FILE) as fh:
                data = json.load(fh)
        except Exception:
            return False
        opened = False
        for p in data:
            if os.path.isfile(p):
                self.new_tab(p)
                opened = True
        return opened

    def _save_session(self):
        paths = []
        for i in range(self.notebook.get_n_pages()):
            tab = self.notebook.get_nth_page(i)
            if getattr(tab, "path", None):
                paths.append(tab.path)
        try:
            os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
            with open(SESSION_FILE, "w") as fh:
                json.dump(paths, fh)
        except Exception:
            pass

    def do_close_request(self):
        self._save_session()
        return False


class BoboTextApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboTextWindow(self)
        self.win.present()

    def do_open(self, files, n, hint):
        self.do_activate()
        for f in files:
            if f.get_path():
                self.win.new_tab(f.get_path())


def main():
    if "--version" in sys.argv:
        print("BoboText 1.0.0 (BOBO OS)")
        return 0
    return BoboTextApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
