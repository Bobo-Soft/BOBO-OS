#!/usr/bin/env python3
"""
BOBO Shell — Start menu. Anchored bottom-left above the taskbar.
Search box + scrollable app grid (from .desktop files) + user + power actions.
Launched (toggled) by the taskbar Start button or Super key.
"""
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GLib, GtkLayerShell  # noqa: E402

import getpass
import shell_common as sc

POWER = [
    ("Lock",       "system-lock-screen",  "bobo-cad --lock"),
    ("Sign out",   "system-log-out",      "wayland-logout || loginctl terminate-user $USER"),
    ("Restart",    "system-reboot",       "systemctl reboot"),
    ("Shut down",  "system-shutdown",     "systemctl poweroff"),
]


class StartMenu(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.cfg = sc.load_config()
        sc.apply_css(self.cfg)
        self.get_style_context().add_class("bobo-startmenu")

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM,
                                 int(self.cfg.get("taskbar_h", 48)) + 6)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, 6)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
        GtkLayerShell.set_namespace(self, "bobo-startmenu")

        self.set_size_request(520, 600)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)

        # Search
        self.search = Gtk.SearchEntry()
        self.search.get_style_context().add_class("sm-search")
        self.search.set_placeholder_text("Search apps…")
        self.search.connect("search-changed", lambda *_: self._populate())
        self.search.connect("activate", self._activate_first)
        outer.pack_start(self.search, False, False, 0)

        # App grid (scrollable)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.flow = Gtk.FlowBox()
        self.flow.set_valign(Gtk.Align.START)
        self.flow.set_max_children_per_line(4)
        self.flow.set_min_children_per_line(4)
        self.flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow.set_margin_start(8); self.flow.set_margin_end(8)
        scroller.add(self.flow)
        outer.pack_start(scroller, True, True, 0)

        # Footer: user + power
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        footer.get_style_context().add_class("sm-footer")
        user = Gtk.Label(label=getpass.getuser())
        user.get_style_context().add_class("sm-user")
        footer.pack_start(user, False, False, 0)
        footer.pack_start(Gtk.Box(), True, True, 0)
        for label, icon, cmd in POWER:
            b = Gtk.Button()
            b.get_style_context().add_class("sm-power")
            b.add(self._img(icon, 18))
            b.set_tooltip_text(label)
            b.connect("clicked", lambda _w, c=cmd: (sc.spawn(c), self._close()))
            footer.pack_start(b, False, False, 0)
        outer.pack_start(footer, False, False, 0)

        self.connect("key-press-event", self._on_key)
        self._apps = sc.list_apps()
        self._populate()
        self.show_all()
        self.search.grab_focus()

    def _img(self, name, size):
        theme = Gtk.IconTheme.get_default()
        use = name if theme.has_icon(name) else "application-x-executable"
        img = Gtk.Image.new_from_icon_name(use, Gtk.IconSize.BUTTON)
        img.set_pixel_size(size)
        return img

    def _populate(self):
        for c in self.flow.get_children():
            self.flow.remove(c)
        q = self.search.get_text().lower().strip()
        self._filtered = []
        for info in self._apps:
            name = (info.get_display_name() or "")
            if q and q not in name.lower():
                continue
            self._filtered.append(info)
            tile = Gtk.Button()
            tile.get_style_context().add_class("sm-tile")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            gicon = info.get_icon()
            if gicon:
                img = Gtk.Image.new_from_gicon(gicon, Gtk.IconSize.DIALOG)
            else:
                img = Gtk.Image.new_from_icon_name("application-x-executable",
                                                   Gtk.IconSize.DIALOG)
            img.set_pixel_size(40)
            lbl = Gtk.Label(label=name)
            lbl.set_ellipsize(3); lbl.set_max_width_chars(12); lbl.set_lines(2)
            lbl.set_justify(Gtk.Justification.CENTER)
            box.pack_start(img, False, False, 0)
            box.pack_start(lbl, False, False, 0)
            tile.add(box)
            tile.connect("clicked", lambda _w, i=info: (sc.launch_app(i), self._close()))
            self.flow.add(tile)
        self.flow.show_all()

    def _activate_first(self, *_):
        if getattr(self, "_filtered", None):
            sc.launch_app(self._filtered[0]); self._close()

    def _on_key(self, _w, ev):
        from gi.repository import Gdk
        if ev.keyval == Gdk.KEY_Escape:
            self._close()
        return False

    def _close(self, *_):
        Gtk.main_quit()


def main():
    if not sc.singleton_or_toggle("startmenu"):
        return
    sc.wait_for_display()
    win = StartMenu()
    win.connect("destroy", Gtk.main_quit)
    import signal
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    Gtk.main()
    sc.clear_singleton("startmenu")


if __name__ == "__main__":
    main()
