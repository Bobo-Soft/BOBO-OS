"""
Code editor for BoboXcode based on GtkSourceView 5.
Swift / Objective-C / Dart / JS / JSON syntax highlight, line numbers,
auto-indent, and optional LSP completion (sourcekit-lsp) for .swift files.
"""
import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
from gi.repository import Gtk, GtkSource, GLib  # noqa: E402


class CodeEditor(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()
        self.set_vexpand(True)
        self.set_hexpand(True)
        self.path = None
        self.lsp = None  # set by the window when sourcekit-lsp is available

        self.buffer = GtkSource.Buffer()
        scheme = GtkSource.StyleSchemeManager.get_default().get_scheme("oblivion") \
            or GtkSource.StyleSchemeManager.get_default().get_scheme("classic-dark")
        if scheme:
            self.buffer.set_style_scheme(scheme)

        self.view = GtkSource.View(buffer=self.buffer)
        self.view.set_show_line_numbers(True)
        self.view.set_highlight_current_line(True)
        self.view.set_auto_indent(True)
        self.view.set_insert_spaces_instead_of_tabs(True)
        self.view.set_tab_width(4)
        self.view.set_monospace(True)
        self.view.set_smart_backspace(True)
        # word completion always; LSP completion wired on demand
        try:
            comp = self.view.get_completion()
            words = GtkSource.CompletionWords.new("words")
            words.register(self.buffer)
            comp.add_provider(words)
        except Exception:
            pass
        self.set_child(self.view)

        # save position / language on load
        self._lang_manager = GtkSource.LanguageManager.get_default()

    def open_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except Exception as e:
            text = "// cannot open %s: %s" % (path, e)
        self.buffer.set_text(text)
        self.path = path
        lang = self._lang_manager.guess_language(path, None)
        if not lang and path.endswith(".swift"):
            lang = self._lang_manager.get_language("swift")
        if lang:
            self.buffer.set_language(lang)
        self.buffer.set_modified(False)
        if self.lsp and path.endswith(".swift"):
            try:
                self.lsp.did_open(path, text)
            except Exception:
                pass

    def get_text(self) -> str:
        s, e = self.buffer.get_bounds()
        return self.buffer.get_text(s, e, True)

    def save(self) -> bool:
        if not self.path:
            return False
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                fh.write(self.get_text())
            self.buffer.set_modified(False)
            return True
        except Exception:
            return False

    def cursor_line_col(self):
        it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        return it.get_line(), it.get_line_offset()
