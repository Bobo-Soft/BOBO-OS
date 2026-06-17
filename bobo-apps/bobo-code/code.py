#!/usr/bin/env python3
# =============================================================================
# BoboCode - IDE usor pentru BOBO OS (APP 25)
# GTK4 + GtkSourceView 5 + VTE (terminal integrat) + Git. Explorator proiect,
# tab-uri, completare, diagnostics la salvare (LSP/lintere), terminal, Git UI.
# =============================================================================
import os
import sys
import subprocess
import threading
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
from gi.repository import Gtk, GtkSource, GLib, Gio, Gdk, Pango  # noqa: E402

# VTE pentru terminalul integrat (optional - fallback foot extern)
try:
    gi.require_version("Vte", "3.91")
    from gi.repository import Vte
    HAVE_VTE = True
except Exception:
    HAVE_VTE = False

APP_ID = "os.bobo.Code"

# LSP/lintere pe limbaj pentru diagnostics la salvare
LINTERS = {
    "python3": ["python3", "-m", "pyflakes"],
    "python": ["python3", "-m", "pyflakes"],
    "sh": ["bash", "-n"],
    "json": ["python3", "-m", "json.tool"],
}


class CodeTab(Gtk.ScrolledWindow):
    def __init__(self, path=None):
        super().__init__()
        self.path = path
        self.buffer = GtkSource.Buffer()
        scheme = GtkSource.StyleSchemeManager.get_default().get_scheme("oblivion")
        if scheme:
            self.buffer.set_style_scheme(scheme)
        self.view = GtkSource.View(buffer=self.buffer)
        self.view.set_show_line_numbers(True)
        self.view.set_highlight_current_line(True)
        self.view.set_auto_indent(True)
        self.view.set_insert_spaces_instead_of_tabs(True)
        self.view.set_tab_width(4)
        self.view.set_monospace(True)
        # completare pe cuvinte (built-in)
        try:
            comp = self.view.get_completion()
            words = GtkSource.CompletionWords.new("cuvinte")
            words.register(self.buffer)
            comp.add_provider(words)
        except Exception:
            pass
        self.set_child(self.view)
        self.set_vexpand(True)
        if path and os.path.isfile(path):
            self.load(path)

    def load(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                self.buffer.set_text(fh.read())
        except Exception:
            self.buffer.set_text("")
        self.path = path
        lang = GtkSource.LanguageManager.get_default().guess_language(path, None)
        if lang:
            self.buffer.set_language(lang)
        self.buffer.set_modified(False)

    def save(self):
        if not self.path:
            return False
        s, e = self.buffer.get_bounds()
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(self.buffer.get_text(s, e, True))
        self.buffer.set_modified(False)
        return True

    def lang_id(self):
        lang = self.buffer.get_language()
        return lang.get_id() if lang else ""


class BoboCodeWindow(Gtk.ApplicationWindow):
    def __init__(self, app, project=None):
        super().__init__(application=app, title="BoboCode")
        self.set_default_size(1100, 740)
        self.project = project or os.getcwd()

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        for icon, tip, cb in [
            ("folder-open-symbolic", "Deschide folder proiect", lambda *a: self.open_project()),
            ("document-save-symbolic", "Salveaza (Ctrl+S)", lambda *a: self.save_current()),
            ("system-run-symbolic", "Ruleaza fisierul", lambda *a: self.run_file()),
        ]:
            b = Gtk.Button.new_from_icon_name(icon)
            b.set_tooltip_text(tip)
            b.connect("clicked", cb)
            header.pack_start(b)
        find = Gtk.Button.new_from_icon_name("edit-find-symbolic")
        find.set_tooltip_text("Cauta in proiect (Ctrl+Shift+F)")
        find.connect("clicked", lambda *a: self.search_project())
        header.pack_end(find)

        # layout: explorer | (editor / git) ; jos terminal
        vsplit = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(vsplit)

        hsplit = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        vsplit.set_start_child(hsplit)
        vsplit.set_resize_start_child(True)

        # explorer
        exp_sw = Gtk.ScrolledWindow()
        exp_sw.set_size_request(220, -1)
        self.tree_store = Gtk.TreeStore(str, str)  # nume, cale
        self.tree = Gtk.TreeView(model=self.tree_store)
        self.tree.append_column(Gtk.TreeViewColumn("Proiect", Gtk.CellRendererText(), text=0))
        self.tree.connect("row-activated", self._on_tree_activated)
        exp_sw.set_child(self.tree)
        hsplit.set_start_child(exp_sw)
        hsplit.set_resize_start_child(False)

        # editor + git
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.notebook = Gtk.Notebook()
        self.notebook.set_vexpand(True)
        right.append(self.notebook)
        self.diag_label = Gtk.Label(xalign=0)
        self.diag_label.add_css_class("dim-label")
        right.append(self.diag_label)
        hsplit.set_end_child(right)

        # terminal jos
        if HAVE_VTE:
            self.terminal = Vte.Terminal()
            self.terminal.spawn_async(
                Vte.PtyFlags.DEFAULT, self.project, ["/bin/bash"], None,
                GLib.SpawnFlags.DEFAULT, None, None, -1, None, None, None)
            term_sw = Gtk.ScrolledWindow()
            term_sw.set_child(self.terminal)
            term_sw.set_size_request(-1, 180)
            vsplit.set_end_child(term_sw)
        else:
            git_panel = self._build_git_panel()
            vsplit.set_end_child(git_panel)
        vsplit.set_resize_end_child(False)

        self._install_shortcuts()
        self._load_tree()

    # ----------------------------------------------------------- explorer
    def _load_tree(self):
        self.tree_store.clear()
        self._add_dir(None, self.project)
        self.set_title("BoboCode - " + os.path.basename(self.project))

    def _add_dir(self, parent, path):
        try:
            entries = sorted(os.listdir(path), key=lambda n: (not os.path.isdir(os.path.join(path, n)), n))
        except Exception:
            return
        for name in entries:
            if name.startswith("."):
                continue
            full = os.path.join(path, name)
            it = self.tree_store.append(parent, [name, full])
            if os.path.isdir(full):
                # adauga un nod fictiv pentru expandare lenesa
                self.tree_store.append(it, ["...", ""])

    def _on_tree_activated(self, tree, path, col):
        it = self.tree_store.get_iter(path)
        full = self.tree_store.get_value(it, 1)
        if not full:
            return
        if os.path.isdir(full):
            if tree.row_expanded(path):
                tree.collapse_row(path)
            else:
                # populeaza lenes
                if self.tree_store.iter_n_children(it) == 1:
                    child = self.tree_store.iter_children(it)
                    if self.tree_store.get_value(child, 1) == "":
                        self.tree_store.remove(child)
                        self._add_dir(it, full)
                tree.expand_row(path, False)
        else:
            self.open_file(full)

    # ----------------------------------------------------------- tabs
    def open_file(self, path):
        # daca e deja deschis, comuta
        for i in range(self.notebook.get_n_pages()):
            tab = self.notebook.get_nth_page(i)
            if getattr(tab, "path", None) == path:
                self.notebook.set_current_page(i)
                return
        tab = CodeTab(path)
        label = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        title = Gtk.Label(label=os.path.basename(path))
        close = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close.add_css_class("flat")
        close.connect("clicked", lambda *a: self._close_tab(tab))
        label.append(title)
        label.append(close)
        idx = self.notebook.append_page(tab, label)
        self.notebook.set_current_page(idx)

    def _close_tab(self, tab):
        idx = self.notebook.page_num(tab)
        if idx >= 0:
            self.notebook.remove_page(idx)

    def current_tab(self):
        p = self.notebook.get_current_page()
        return self.notebook.get_nth_page(p) if p >= 0 else None

    def save_current(self):
        tab = self.current_tab()
        if tab and tab.save():
            self._run_diagnostics(tab)

    # ----------------------------------------------------------- diagnostics
    def _run_diagnostics(self, tab):
        linter = LINTERS.get(tab.lang_id())
        if not linter or not tab.path:
            self.diag_label.set_text("")
            return

        def run():
            r = subprocess.run(linter + [tab.path], capture_output=True, text=True)
            out = (r.stdout + r.stderr).strip()
            GLib.idle_add(self.diag_label.set_text, out[:300] or "✓ fara erori")
        threading.Thread(target=run, daemon=True).start()

    # ----------------------------------------------------------- run
    def run_file(self):
        tab = self.current_tab()
        if not tab or not tab.path:
            return
        ext = os.path.splitext(tab.path)[1]
        runner = {".py": "python3", ".sh": "bash", ".js": "node"}.get(ext)
        if not runner:
            return
        if HAVE_VTE:
            self.terminal.feed_child(("%s %s\n" % (runner, tab.path)).encode())
        else:
            subprocess.Popen(["foot", "-e", "bash", "-c", "%s '%s'; read" % (runner, tab.path)])

    # ----------------------------------------------------------- git
    def _build_git_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(-1, 180)
        toolbar = Gtk.Box(spacing=6)
        toolbar.set_margin_top(4)
        toolbar.set_margin_start(6)
        for label, args in [("Status", ["status", "-s"]), ("Stage all", ["add", "-A"]),
                            ("Commit", None), ("Push", ["push"]), ("Pull", ["pull"])]:
            b = Gtk.Button(label=label)
            if label == "Commit":
                b.connect("clicked", lambda *a: self._git_commit())
            else:
                b.connect("clicked", lambda x, ar=args: self._git(ar))
            toolbar.append(b)
        box.append(toolbar)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        self.git_view = Gtk.TextView()
        self.git_view.set_editable(False)
        self.git_view.set_monospace(True)
        sw.set_child(self.git_view)
        box.append(sw)
        return box

    def _git(self, args):
        r = subprocess.run(["git", "-C", self.project] + args, capture_output=True, text=True)
        if hasattr(self, "git_view"):
            self.git_view.get_buffer().set_text((r.stdout + r.stderr) or "OK")

    def _git_commit(self):
        win = Gtk.Window(title="Commit", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        entry = Gtk.Entry(placeholder_text="Mesaj commit")
        btn = Gtk.Button(label="Commit")
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda *a: (self._git(["commit", "-m", entry.get_text()]), win.close()))
        box.append(entry)
        box.append(btn)
        win.set_child(box)
        win.present()

    def search_project(self):
        win = Gtk.Window(title="Cauta in proiect", transient_for=self, modal=True)
        win.set_default_size(560, 400)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        entry = Gtk.SearchEntry()
        result = Gtk.TextView()
        result.set_editable(False)
        result.set_monospace(True)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(result)

        def do_search(*a):
            r = subprocess.run(["grep", "-rn", entry.get_text(), self.project],
                               capture_output=True, text=True)
            result.get_buffer().set_text(r.stdout[:5000] or "Niciun rezultat")
        entry.connect("activate", do_search)
        box.append(entry)
        box.append(sw)
        win.set_child(box)
        win.present()

    def open_project(self):
        d = Gtk.FileDialog()
        d.select_folder(self, None, self._project_chosen)

    def _project_chosen(self, dialog, res):
        try:
            f = dialog.select_folder_finish(res)
        except GLib.Error:
            return
        if f:
            self.project = f.get_path()
            self._load_tree()

    def _install_shortcuts(self):
        keymap = {
            "<Ctrl>s": lambda: self.save_current(),
            "<Ctrl><Shift>f": lambda: self.search_project(),
            "<F5>": lambda: self.run_file(),
        }
        ctrl = Gtk.ShortcutController()
        ctrl.set_scope(Gtk.ShortcutScope.GLOBAL)
        for accel, fn in keymap.items():
            t = Gtk.ShortcutTrigger.parse_string(accel)
            a = Gtk.CallbackAction.new(lambda w, ar, f=fn: (f(), True)[1])
            ctrl.add_shortcut(Gtk.Shortcut.new(t, a))
        self.add_controller(ctrl)


class BoboCodeApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboCodeWindow(self)
        self.win.present()

    def do_open(self, files, n, hint):
        path = files[0].get_path()
        proj = path if os.path.isdir(path) else os.path.dirname(path)
        self.win = BoboCodeWindow(self, project=proj)
        self.win.present()
        if os.path.isfile(path):
            self.win.open_file(path)


def main():
    if "--version" in sys.argv:
        print("BoboCode 1.0.0 (BOBO OS)")
        return 0
    return BoboCodeApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
