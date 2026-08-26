#!/usr/bin/env python3
"""
BOBO Shell — Ctrl+Alt+Del intermediate screen (Windows-like security screen).
Fullscreen overlay with: Lock, Sign out, Task Manager, Restart, Shut down, Cancel.
Bound to Ctrl+Alt+Del in Wayfire. `--lock` jumps straight to the lock screen.
"""
import sys
import shutil
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GtkLayerShell  # noqa: E402

import shell_common as sc

ACTIONS = [
    ("Lock",         "system-lock-screen", "lock"),
    ("Sign out",     "system-log-out",     "kill -TERM -1 2>/dev/null; loginctl terminate-user $USER"),
    ("Task Manager", "utilities-system-monitor", "bobo-monitor"),
    ("Restart",      "system-reboot",      "systemctl reboot"),
    ("Shut down",    "system-shutdown",    "systemctl poweroff"),
]


def do_lock():
    for tool in ("swaylock", "gtklock", "waylock"):
        if shutil.which(tool):
            sc.spawn([tool]); return True
    return False


class CAD(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.cfg = sc.load_config()
        sc.apply_css(self.cfg)
        self.get_style_context().add_class("bobo-cad")

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        for e in (GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT,
                  GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM):
            GtkLayerShell.set_anchor(self, e, True)
        GtkLayerShell.set_exclusive_zone(self, -1)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        GtkLayerShell.set_namespace(self, "bobo-cad")

        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        center.set_halign(Gtk.Align.CENTER)
        center.set_valign(Gtk.Align.CENTER)
        self.add(center)

        title = Gtk.Label(label="BOBO OS")
        title.get_style_context().add_class("cad-title")
        center.pack_start(title, False, False, 20)

        for label, icon, action in ACTIONS:
            b = Gtk.Button()
            b.get_style_context().add_class("cad-btn")
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            row.set_halign(Gtk.Align.START)
            img = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.DIALOG)
            img.set_pixel_size(28)
            row.pack_start(img, False, False, 0)
            row.pack_start(Gtk.Label(label=label), False, False, 0)
            b.add(row)
            b.connect("clicked", lambda _w, a=action: self._act(a))
            center.pack_start(b, False, False, 0)

        cancel = Gtk.Button(label="Cancel  (Esc)")
        cancel.get_style_context().add_class("cad-btn")
        cancel.connect("clicked", lambda *_: self._close())
        center.pack_start(cancel, False, False, 20)

        self.connect("key-press-event", self._on_key)
        self.show_all()

    def _act(self, action):
        if action == "lock":
            if not do_lock():
                return  # no locker available; stay on screen
            self._close()
        else:
            sc.spawn(action)
            self._close()

    def _on_key(self, _w, ev):
        from gi.repository import Gdk
        if ev.keyval == Gdk.KEY_Escape:
            self._close()
        return False

    def _close(self, *_):
        Gtk.main_quit()


def main():
    if "--lock" in sys.argv:
        if do_lock():
            return
    if not sc.singleton_or_toggle("cad"):
        return
    sc.wait_for_display()
    win = CAD()
    win.connect("destroy", Gtk.main_quit)
    import signal
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    Gtk.main()
    sc.clear_singleton("cad")


if __name__ == "__main__":
    main()
