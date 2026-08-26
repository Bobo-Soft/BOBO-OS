#!/usr/bin/env python3
"""
BOBO Shell — bottom taskbar (Windows-like), auto-hide, GTK3 + gtk-layer-shell.

Layout:  [Start] [quick-launch pinned apps ...............]  [sys icons] [clock/date]
Auto-hide: the bar slides down leaving a 2 px reveal strip; hovering it slides it up.
"""
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell  # noqa: E402

import shell_common as sc

PINNED = [
    # (label, icon-name, command)
    ("Start Menu", "start-here",        "bobo-startmenu"),
    ("Files",      "system-file-manager", "nemo"),
    ("BOBO Browser", "web-browser",     "bobo-browser"),
    ("Terminal",   "utilities-terminal", "kitty"),
    ("BoboHub",    "applications-office", "bobo-hub"),
    ("Settings",   "preferences-system", "bobo-settings"),
]


class Taskbar(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.cfg = sc.load_config()
        self.h = int(self.cfg.get("taskbar_h", 48))
        self.autohide = bool(self.cfg.get("autohide", True))
        self._hidden = False
        self._hide_src = 0
        sc.apply_css(self.cfg)

        self.get_style_context().add_class("bobo-taskbar")
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP)
        for e in (GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT,
                  GtkLayerShell.Edge.BOTTOM):
            GtkLayerShell.set_anchor(self, e, True)
        GtkLayerShell.set_namespace(self, "bobo-taskbar")
        GtkLayerShell.set_exclusive_zone(self, 0 if self.autohide else self.h)

        self.set_size_request(-1, self.h)
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.set_size_request(-1, self.h)
        self.add(root)

        # Start button (BOBO logo)
        start = Gtk.Button()
        start.get_style_context().add_class("tb-start")
        start.add(self._icon("start-here", 26, fallback="applications-system"))
        start.set_tooltip_text("Start")
        start.connect("clicked", lambda *_: sc.spawn(["bobo-startmenu"]))
        root.pack_start(start, False, False, 0)

        # Quick-launch pinned apps
        for label, icon, cmd in PINNED[1:]:
            b = Gtk.Button()
            b.get_style_context().add_class("tb-item")
            b.add(self._icon(icon, 22))
            b.set_tooltip_text(label)
            b.connect("clicked", lambda _w, c=cmd: sc.spawn([c]))
            root.pack_start(b, False, False, 0)

        # Spacer
        root.pack_start(Gtk.Box(), True, True, 0)

        # System icons: sidebar / network / volume
        for icon, tip, action in [
            ("network-wireless", "Network", "sidebar"),
            ("audio-volume-high", "Volume", "sidebar"),
            ("preferences-system", "Quick settings", "sidebar"),
        ]:
            b = Gtk.Button()
            b.get_style_context().add_class("tb-sys")
            b.add(self._icon(icon, 18))
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda *_: sc.spawn(["bobo-sidebar"]))
            root.pack_start(b, False, False, 0)

        # Clock + date
        self.clock = Gtk.Button()
        self.clock.get_style_context().add_class("tb-clock")
        cb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.lbl_time = Gtk.Label(); self.lbl_time.get_style_context().add_class("time")
        self.lbl_date = Gtk.Label(); self.lbl_date.get_style_context().add_class("date")
        cb.pack_start(self.lbl_time, False, False, 0)
        cb.pack_start(self.lbl_date, False, False, 0)
        self.clock.add(cb)
        self.clock.connect("clicked", lambda *_: sc.spawn(["bobo-sidebar"]))
        root.pack_start(self.clock, False, False, 0)
        self._tick()
        GLib.timeout_add_seconds(1, self._tick)

        # Auto-hide wiring
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)
        self.connect("realize", self._on_realize)
        self.show_all()

    def _on_realize(self, *_):
        # Start visible (discoverable + a screenshot can see it); if auto-hide is
        # enabled, slide it away after a few seconds. Hovering the 2 px strip re-reveals.
        self._apply_hidden(False)
        if self.autohide and not self._hide_src:
            self._hide_src = GLib.timeout_add(8000, self._do_hide)

    def _icon(self, name, size, fallback="application-x-executable"):
        theme = Gtk.IconTheme.get_default()
        use = name if theme.has_icon(name) else fallback
        img = Gtk.Image.new_from_icon_name(use, Gtk.IconSize.BUTTON)
        img.set_pixel_size(size)
        return img

    def _tick(self):
        now = GLib.DateTime.new_now_local()
        self.lbl_time.set_text(now.format("%H:%M"))
        self.lbl_date.set_text(now.format("%d/%m/%Y"))
        return True

    # ── auto-hide ────────────────────────────────────────────────────────────
    def _apply_hidden(self, hide):
        if not self.autohide:
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, 0)
            return
        self._hidden = hide
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM,
                                 -(self.h - 2) if hide else 0)

    def _on_enter(self, *_):
        if self._hide_src:
            GLib.source_remove(self._hide_src); self._hide_src = 0
        if self._hidden:
            self._apply_hidden(False)
        return False

    def _on_leave(self, _w, ev):
        # ignore leave events caused by moving onto child widgets
        if ev.detail == Gdk.NotifyType.INFERIOR:
            return False
        if self.autohide and not self._hide_src:
            self._hide_src = GLib.timeout_add(600, self._do_hide)
        return False

    def _do_hide(self):
        self._hide_src = 0
        self._apply_hidden(True)
        return False


def main():
    if not sc.ensure_single("taskbar"):
        return
    sc.wait_for_display()
    win = Taskbar()
    win.connect("destroy", Gtk.main_quit)
    import signal
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    Gtk.main()
    sc.clear_singleton("taskbar")


if __name__ == "__main__":
    main()
