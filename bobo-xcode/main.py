#!/usr/bin/env python3
"""
BoboXcode — Swift/iOS IDE for BOBO OS. GTK4 application entry point.
(--version is handled before importing GI so it works headless.)
"""
import sys
import os

sys.path.insert(0, "/usr/share/bobo-xcode")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    if "--version" in sys.argv:
        print("BoboXcode 1.0.0 (BOBO OS)")
        return 0
    if "--install-swift" in sys.argv:
        print("Run a FULL build, or:  BOBO_XCODE_SKIP_HEAVY=0 bash /usr/share/bobo-xcode/install.sh")
        return 0

    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("GtkSource", "5")
    from gi.repository import Gtk, Gio
    from ui.window import BoboXcodeWindow

    class BoboXcodeApp(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="com.bobosoft.bobo-xcode",
                             flags=Gio.ApplicationFlags.HANDLES_OPEN)

        def do_activate(self):
            BoboXcodeWindow(application=self).present()

        def do_open(self, files, n_files, hint):
            win = BoboXcodeWindow(application=self)
            if files and files[0].get_path():
                win.open_project(files[0].get_path())
            win.present()

    return BoboXcodeApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
