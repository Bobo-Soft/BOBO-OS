#!/usr/bin/env python3
"""
BOBO Shell — desktop icons. A transparent background layer over the wallpaper
holding a top-left column of double-clickable shortcuts (This PC, Files, Browser,
BoboHub, Recycle Bin). Any *.desktop dropped in ~/Desktop is added automatically.
"""
import os
from pathlib import Path
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, Gio, GtkLayerShell  # noqa: E402

import shell_common as sc

BUILTIN = [
    ("This PC",      "computer",            "nemo computer:///"),
    ("Files",        "user-home",           "nemo"),
    ("BOBO Browser", "web-browser",         "bobo-browser"),
    ("BoboHub",      "applications-office", "bobo-hub"),
    ("Recycle Bin",  "user-trash",          "nemo trash:///"),
]


class Desktop(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.cfg = sc.load_config()
        sc.apply_css(self.cfg)

        # transparency so the wallpaper shows through
        screen = self.get_screen()
        vis = screen.get_rgba_visual()
        if vis:
            self.set_visual(vis)
        self.set_app_paintable(True)
        self.connect("draw", self._clear)

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.BOTTOM)
        for e in (GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT,
                  GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM):
            GtkLayerShell.set_anchor(self, e, True)
        GtkLayerShell.set_exclusive_zone(self, -1)
        GtkLayerShell.set_namespace(self, "bobo-desktop")

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        col.set_halign(Gtk.Align.START)
        col.set_valign(Gtk.Align.START)
        col.set_margin_top(16); col.set_margin_start(16)
        self.add(col)

        for label, icon, cmd in BUILTIN:
            col.pack_start(self._icon(label, icon, cmd), False, False, 0)
        for label, icon, cmd in self._user_desktop():
            col.pack_start(self._icon(label, icon, cmd), False, False, 0)

        self.show_all()

    def _clear(self, _w, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)  # SOURCE
        cr.paint()
        return False

    def _user_desktop(self):
        out = []
        from gi.repository import GLib
        d = Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP)
                 or (Path.home() / "Desktop"))
        try:
            for f in sorted(d.glob("*.desktop")):
                info = Gio.DesktopAppInfo.new_from_filename(str(f))
                if info:
                    out.append((info.get_display_name(),
                                info.get_icon().to_string() if info.get_icon() else "application-x-executable",
                                None))  # None => launch via DesktopAppInfo below
                    out[-1] = (out[-1][0], out[-1][1], info)
        except Exception:
            pass
        return out

    def _icon(self, label, icon, cmd):
        b = Gtk.Button()
        b.get_style_context().add_class("bobo-desktop-icon")
        b.set_relief(Gtk.ReliefStyle.NONE)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        theme = Gtk.IconTheme.get_default()
        if isinstance(icon, str) and (theme.has_icon(icon) or "/" in icon):
            img = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.DIALOG)
        else:
            img = Gtk.Image.new_from_icon_name("application-x-executable",
                                               Gtk.IconSize.DIALOG)
        img.set_pixel_size(48)
        lbl = Gtk.Label(label=label)
        lbl.set_max_width_chars(12); lbl.set_line_wrap(True)
        lbl.set_justify(Gtk.Justification.CENTER)
        box.pack_start(img, False, False, 0)
        box.pack_start(lbl, False, False, 0)
        b.add(box)
        b.set_size_request(96, 92)
        # double-click launches (Windows-like)
        b.connect("button-press-event", self._on_press, cmd)
        b.connect("activate", lambda _w, c=cmd: self._launch(c))
        return b

    def _on_press(self, _w, ev, cmd):
        if ev.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self._launch(cmd)
        return False

    def _launch(self, cmd):
        if isinstance(cmd, Gio.DesktopAppInfo):
            sc.launch_app(cmd)
        else:
            sc.spawn(cmd)


def main():
    if not sc.ensure_single("desktop"):
        return
    sc.wait_for_display()
    win = Desktop()
    win.connect("destroy", Gtk.main_quit)
    import signal
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    Gtk.main()


if __name__ == "__main__":
    main()
