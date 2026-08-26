#!/usr/bin/env python3
"""
BoboAssist main entry (GTK4).
Opens the side panel. The model is lazy-loaded on the first prompt (handled by
Ollama) and Ollama itself unloads it after its keep-alive window; we additionally
request a short keep-alive so RAM is released ~5 min after the last use.
--version answers before importing GI so headless checks work.
"""
import sys
import os

sys.path.insert(0, "/usr/share/bobo-assist")
sys.path.insert(0, "/usr/share/bobo-office")


def main():
    if "--version" in sys.argv:
        print("BoboAssist 1.0.0 (BOBO OS)")
        return 0

    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk, Gio
    from ui.panel import AssistPanel

    class BoboAssistApp(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="os.bobo.Assist",
                             flags=Gio.ApplicationFlags.FLAGS_NONE)
            self.win = None

        def do_activate(self):
            if not self.win:
                self.win = AssistPanel(self)
            self.win.present()

    return BoboAssistApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
