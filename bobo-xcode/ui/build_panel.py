"""
Build output panel for BoboXcode.
A read-only monospace view that colorizes errors/warnings/success lines.
Thread-safe: callers should append via GLib.idle_add from worker threads.
"""
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


class BuildPanel(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()
        self.set_vexpand(True)
        self.view = Gtk.TextView()
        self.view.set_editable(False)
        self.view.set_monospace(True)
        self.view.set_cursor_visible(False)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.add_css_class("build-output")
        self.buffer = self.view.get_buffer()
        # color tags
        self.tag_error = self.buffer.create_tag("error", foreground="#ff6b6b")
        self.tag_warn = self.buffer.create_tag("warning", foreground="#ffd93d")
        self.tag_ok = self.buffer.create_tag("success", foreground="#6bcb77")
        self.set_child(self.view)

    def clear(self):
        self.buffer.set_text("")

    def append(self, line: str):
        end = self.buffer.get_end_iter()
        low = line.lower()
        if "error" in low or "❌" in line:
            self.buffer.insert_with_tags(end, line, self.tag_error)
        elif "warning" in low:
            self.buffer.insert_with_tags(end, line, self.tag_warn)
        elif "✅" in line or "complete" in low or "success" in low:
            self.buffer.insert_with_tags(end, line, self.tag_ok)
        else:
            self.buffer.insert(end, line)
        # autoscroll
        mark = self.buffer.create_mark(None, self.buffer.get_end_iter(), False)
        self.view.scroll_mark_onscreen(mark)
        return False
