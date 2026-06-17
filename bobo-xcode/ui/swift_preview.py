"""
SwiftUI preview panel for BoboXcode.
Full visual SwiftUI rendering requires Apple frameworks (macOS only); on Linux
we provide a 'logic preview': build & run the package and show its output, plus
a parsed list of the SwiftUI View structs found in the project for quick nav.
"""
import os
import re
import threading
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

from engines.swift_engine import SwiftEngine


class SwiftUIPreview(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.project_path = None
        self.engine = SwiftEngine()

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_margin_top(8)
        bar.set_margin_start(8)
        self.refresh_btn = Gtk.Button(label="Refresh preview (build & run)")
        self.refresh_btn.add_css_class("suggested-action")
        self.refresh_btn.connect("clicked", lambda *a: self.refresh())
        bar.append(self.refresh_btn)
        self.views_label = Gtk.Label(xalign=0)
        self.views_label.add_css_class("dim-label")
        bar.append(self.views_label)
        self.append(bar)

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        self.output = Gtk.TextView()
        self.output.set_editable(False)
        self.output.set_monospace(True)
        sw.set_child(self.output)
        self.append(sw)
        self._set_text("Open a Swift project and press Refresh to preview output.")

    def set_project(self, path: str):
        self.project_path = path
        self._scan_views()

    def _scan_views(self):
        if not self.project_path:
            return
        names = []
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in (".build", ".git")]
            for f in files:
                if f.endswith(".swift"):
                    try:
                        with open(os.path.join(root, f), "r", encoding="utf-8", errors="replace") as fh:
                            names += re.findall(r"struct\s+(\w+)\s*:\s*View", fh.read())
                    except Exception:
                        pass
        self.views_label.set_text(("Views: " + ", ".join(names[:8])) if names else "No SwiftUI views found")

    def refresh(self):
        if not self.project_path:
            self._set_text("No project open.")
            return
        self._scan_views()
        if not self.engine.is_available():
            self._set_text("Swift toolchain not installed. Run a FULL build to enable preview.")
            return
        self._set_text("Building and running...\n")
        threading.Thread(target=self._run_thread, daemon=True).start()

    def _run_thread(self):
        result = self.engine.run_binary(
            self.project_path,
            callback=lambda line: GLib.idle_add(self._append, line))
        GLib.idle_add(self._append,
                      "\n--- preview finished (exit %s) ---\n" % ("ok" if result.success else "error"))

    def _set_text(self, text):
        self.output.get_buffer().set_text(text)

    def _append(self, line):
        buf = self.output.get_buffer()
        buf.insert(buf.get_end_iter(), line)
        return False
