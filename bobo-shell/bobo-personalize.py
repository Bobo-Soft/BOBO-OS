#!/usr/bin/env python3
"""
BOBO Shell — Personalization. Change accent colour (presets or custom), light/dark
theme and taskbar auto-hide. Applying saves the config and restarts the shell
surfaces so the new colours take effect immediately.
"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk  # noqa: E402

import shell_common as sc


class Personalize(Gtk.Window):
    def __init__(self):
        super().__init__(title="Personalization — BOBO OS")
        self.cfg = sc.load_config()
        sc.apply_css(self.cfg)
        self.set_default_size(460, 460)
        self.set_border_width(0)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(18); box.set_margin_bottom(18)
        box.set_margin_start(18); box.set_margin_end(18)
        self.add(box)

        head = Gtk.Label()
        head.set_markup("<span size='x-large' weight='bold'>Colours &amp; theme</span>")
        head.set_xalign(0)
        box.pack_start(head, False, False, 0)

        # Accent presets
        box.pack_start(self._label("Accent colour"), False, False, 0)
        flow = Gtk.FlowBox()
        flow.set_max_children_per_line(8); flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._accent = self.cfg.get("accent", "#4a9eff")
        for hexv in sc.ACCENT_PRESETS:
            sw = Gtk.Button()
            sw.set_size_request(40, 40)
            css = Gtk.CssProvider()
            css.load_from_data(
                f"button{{background:{hexv};border-radius:20px;border:2px solid #0000;}}"
                f"button:hover{{border-color:#ffffff;}}".encode())
            sw.get_style_context().add_provider(css, 800)
            sw.connect("clicked", lambda _w, h=hexv: self._pick(h))
            flow.add(sw)
        box.pack_start(flow, False, False, 0)

        # Custom colour
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.pack_start(Gtk.Label(label="Custom:"), False, False, 0)
        self.color_btn = Gtk.ColorButton()
        rgba = Gdk.RGBA(); rgba.parse(self._accent); self.color_btn.set_rgba(rgba)
        self.color_btn.connect("color-set", self._on_custom)
        row.pack_start(self.color_btn, False, False, 0)
        self.preview = Gtk.Label(label=self._accent)
        row.pack_start(self.preview, False, False, 0)
        box.pack_start(row, False, False, 0)

        # Theme
        box.pack_start(self._label("Theme"), False, False, 0)
        trow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.rb_dark = Gtk.RadioButton.new_with_label_from_widget(None, "Dark")
        self.rb_light = Gtk.RadioButton.new_with_label_from_widget(self.rb_dark, "Light")
        (self.rb_dark if self.cfg.get("theme", "dark") == "dark"
         else self.rb_light).set_active(True)
        trow.pack_start(self.rb_dark, False, False, 0)
        trow.pack_start(self.rb_light, False, False, 0)
        box.pack_start(trow, False, False, 0)

        # Auto-hide taskbar
        self.chk_autohide = Gtk.CheckButton(label="Auto-hide the taskbar")
        self.chk_autohide.set_active(bool(self.cfg.get("autohide", True)))
        box.pack_start(self.chk_autohide, False, False, 0)

        box.pack_start(Gtk.Box(), True, True, 0)

        # Apply / Close
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btns.pack_start(Gtk.Box(), True, True, 0)
        close = Gtk.Button(label="Close")
        close.connect("clicked", lambda *_: self.destroy())
        apply_b = Gtk.Button(label="Apply")
        apply_b.get_style_context().add_class("bobo-accent")
        apply_b.get_style_context().add_class("suggested-action")
        apply_b.connect("clicked", self._apply)
        btns.pack_start(close, False, False, 0)
        btns.pack_start(apply_b, False, False, 0)
        box.pack_start(btns, False, False, 0)

        self.connect("destroy", Gtk.main_quit)
        self.show_all()

    def _label(self, text):
        l = Gtk.Label(); l.set_markup(f"<b>{text}</b>"); l.set_xalign(0); return l

    def _pick(self, hexv):
        self._accent = hexv
        self.preview.set_text(hexv)
        rgba = Gdk.RGBA(); rgba.parse(hexv); self.color_btn.set_rgba(rgba)

    def _on_custom(self, btn):
        rgba = btn.get_rgba()
        self._accent = "#%02x%02x%02x" % (int(rgba.red * 255),
                                          int(rgba.green * 255), int(rgba.blue * 255))
        self.preview.set_text(self._accent)

    def _apply(self, *_):
        self.cfg["accent"] = self._accent
        self.cfg["theme"] = "dark" if self.rb_dark.get_active() else "light"
        self.cfg["autohide"] = self.chk_autohide.get_active()
        sc.save_config(self.cfg)
        # restart shell surfaces so colours/geometry refresh
        for name, cmd in [("taskbar", "bobo-taskbar"), ("sidebar", "bobo-sidebar"),
                          ("desktop", "bobo-desktop")]:
            sc.spawn(f"pkill -f {cmd} 2>/dev/null; sleep 0.3; "
                     f"({cmd} &) >/dev/null 2>&1")
        # re-theme this window too
        sc.apply_css(self.cfg)


def main():
    sc.wait_for_display()
    Personalize()
    Gtk.main()


if __name__ == "__main__":
    main()
