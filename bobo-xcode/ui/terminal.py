"""
Integrated terminal for BoboXcode.
Uses VTE 3.91 (the GTK4 build) when present; otherwise offers a button to
open the project in the external 'foot' terminal. (VTE 2.91 is GTK3 and would
conflict with the GTK4 process, so it is intentionally NOT used.)
"""
import os
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

HAVE_VTE = False
try:
    gi.require_version("Vte", "3.91")
    from gi.repository import Vte
    HAVE_VTE = True
except Exception:
    Vte = None


class TerminalPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_vexpand(True)
        self.cwd = os.path.expanduser("~")
        self.terminal = None
        if HAVE_VTE:
            self._build_vte()
        else:
            self._build_fallback()

    def _build_vte(self):
        self.terminal = Vte.Terminal()
        self.terminal.set_vexpand(True)
        self.terminal.set_hexpand(True)
        self._spawn(self.cwd)
        sw = Gtk.ScrolledWindow()
        sw.set_child(self.terminal)
        self.append(sw)

    def _spawn(self, cwd):
        shell = os.environ.get("SHELL", "/bin/bash")
        try:
            self.terminal.spawn_async(
                Vte.PtyFlags.DEFAULT, cwd, [shell], None,
                GLib.SpawnFlags.DEFAULT, None, None, -1, None, None, None)
        except Exception:
            pass

    def _build_fallback(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.append(Gtk.Label(
            label="VTE (GTK4) not available — using the external terminal.",
            xalign=0, wrap=True))
        btn = Gtk.Button(label="Open terminal here (foot)")
        btn.connect("clicked", lambda *a: self._open_external())
        box.append(btn)
        self.append(box)

    def _open_external(self):
        import subprocess
        try:
            subprocess.Popen(["foot", "--working-directory", self.cwd])
        except Exception:
            try:
                subprocess.Popen(["kitty", "--directory", self.cwd])
            except Exception:
                pass

    def set_cwd(self, path: str):
        """Point the terminal at the project directory."""
        if path and os.path.isdir(path):
            self.cwd = path
            if HAVE_VTE and self.terminal:
                self.terminal.feed_child(("cd '%s'\n" % path).encode())

    def run_command(self, command: str):
        """Type and execute a command in the embedded terminal."""
        if HAVE_VTE and self.terminal:
            self.terminal.feed_child((command + "\n").encode())
        else:
            import subprocess
            subprocess.Popen(["foot", "--working-directory", self.cwd, "-e",
                              "bash", "-c", command + "; read -p 'Enter...'"])
