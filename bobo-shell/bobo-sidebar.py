#!/usr/bin/env python3
"""
BOBO Shell — right vertical bar / action center (GTK3 + gtk-layer-shell).
Clock, quick-toggle tiles (Wi-Fi, Bluetooth, Do-Not-Disturb, Night light),
volume + brightness sliders, and a Personalize shortcut. Toggled from the taskbar.
"""
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GLib, GtkLayerShell  # noqa: E402

import shutil
import subprocess
import shell_common as sc


class Sidebar(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.cfg = sc.load_config()
        sc.apply_css(self.cfg)
        self.get_style_context().add_class("bobo-sidebar")

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        for e in (GtkLayerShell.Edge.RIGHT, GtkLayerShell.Edge.TOP,
                  GtkLayerShell.Edge.BOTTOM):
            GtkLayerShell.set_anchor(self, e, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM,
                                 int(self.cfg.get("taskbar_h", 48)))
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
        GtkLayerShell.set_namespace(self, "bobo-sidebar")

        self.set_size_request(340, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(10); box.set_margin_bottom(10)
        box.set_margin_start(10); box.set_margin_end(10)
        self.add(box)

        # Clock
        title = Gtk.Label()
        title.get_style_context().add_class("sb-title")
        now = GLib.DateTime.new_now_local()
        title.set_markup(f"<b>{now.format('%H:%M')}</b>  {now.format('%A, %d %B %Y')}")
        title.set_xalign(0)
        box.pack_start(title, False, False, 0)

        # Quick toggles (2-col grid)
        grid = Gtk.FlowBox()
        grid.set_max_children_per_line(2); grid.set_min_children_per_line(2)
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        for label, icon, cb in [
            ("Wi-Fi",        "network-wireless",   self._toggle_wifi),
            ("Bluetooth",    "bluetooth",          self._toggle_bt),
            ("Do Not Disturb", "notifications-disabled", self._toggle_dnd),
            ("Night light",  "night-light",        self._toggle_night),
        ]:
            grid.add(self._tile(label, icon, cb))
        box.pack_start(grid, False, False, 0)

        # Volume
        box.pack_start(self._slider("Volume", "audio-volume-high",
                                    self._get_volume(), self._set_volume), False, False, 0)
        # Brightness (only if brightnessctl present)
        if shutil.which("brightnessctl"):
            box.pack_start(self._slider("Brightness", "display-brightness",
                                        self._get_bright(), self._set_bright),
                           False, False, 0)

        box.pack_start(Gtk.Box(), True, True, 0)

        # Personalize + Settings
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for label, cmd in [("Personalize", "bobo-personalize"),
                           ("All settings", "bobo-settings")]:
            b = Gtk.Button(label=label)
            b.get_style_context().add_class("sb-tile")
            b.connect("clicked", lambda _w, c=cmd: (sc.spawn([c]), self._close()))
            row.pack_start(b, True, True, 0)
        box.pack_start(row, False, False, 0)

        self.connect("key-press-event", self._on_key)
        self.show_all()

    def _tile(self, label, icon, cb):
        b = Gtk.Button()
        b.get_style_context().add_class("sb-tile")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        theme = Gtk.IconTheme.get_default()
        use = icon if theme.has_icon(icon) else "emblem-system"
        img = Gtk.Image.new_from_icon_name(use, Gtk.IconSize.BUTTON)
        img.set_pixel_size(20)
        inner.pack_start(img, False, False, 0)
        inner.pack_start(Gtk.Label(label=label), False, False, 0)
        b.add(inner)
        b.connect("clicked", lambda w, f=cb: self._flip(w, f))
        return b

    def _flip(self, widget, fn):
        ctx = widget.get_style_context()
        if ctx.has_class("active"):
            ctx.remove_class("active")
        else:
            ctx.add_class("active")
        fn()

    def _slider(self, label, icon, value, on_change):
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        wrap.get_style_context().add_class("sb-tile")
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        img = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
        img.set_pixel_size(18)
        head.pack_start(img, False, False, 0)
        head.pack_start(Gtk.Label(label=label), False, False, 0)
        wrap.pack_start(head, False, False, 0)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_draw_value(False)
        scale.set_value(value)
        scale.connect("value-changed", lambda s: on_change(int(s.get_value())))
        wrap.pack_start(scale, False, False, 0)
        return wrap

    # ── system actions (best-effort; silent if tool missing) ──────────────────
    def _run(self, *a):
        try:
            return subprocess.run(a, capture_output=True, text=True, timeout=4)
        except Exception:
            return None

    def _toggle_wifi(self):
        st = self._run("nmcli", "radio", "wifi")
        on = st and "enabled" in (st.stdout or "")
        self._run("nmcli", "radio", "wifi", "off" if on else "on")

    def _toggle_bt(self):
        if shutil.which("rfkill"):
            self._run("rfkill", "toggle", "bluetooth")

    def _toggle_dnd(self):
        if shutil.which("makoctl"):
            self._run("makoctl", "mode", "-t", "dnd")

    def _toggle_night(self):
        # gammastep / wlsunset if present
        for tool in ("wlsunset", "gammastep"):
            if shutil.which(tool):
                sc.spawn([tool]); return

    def _get_volume(self):
        st = self._run("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@")
        try:
            return int(float(st.stdout.split()[1]) * 100)
        except Exception:
            return 60

    def _set_volume(self, v):
        if shutil.which("wpctl"):
            self._run("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{v/100:.2f}")

    def _get_bright(self):
        st = self._run("brightnessctl", "-m", "i")
        try:
            return int(st.stdout.split(",")[3].rstrip("%"))
        except Exception:
            return 80

    def _set_bright(self, v):
        self._run("brightnessctl", "set", f"{v}%")

    def _on_key(self, _w, ev):
        from gi.repository import Gdk
        if ev.keyval == Gdk.KEY_Escape:
            self._close()
        return False

    def _close(self, *_):
        Gtk.main_quit()


def main():
    if not sc.singleton_or_toggle("sidebar"):
        return
    sc.wait_for_display()
    win = Sidebar()
    win.connect("destroy", Gtk.main_quit)
    import signal
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    Gtk.main()
    sc.clear_singleton("sidebar")


if __name__ == "__main__":
    main()
