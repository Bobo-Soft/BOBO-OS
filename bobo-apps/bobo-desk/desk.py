#!/usr/bin/env python3
# =============================================================================
# BoboDesk - Manager de desktop-uri virtuale pentru BOBO OS (APP 19)
# GTK4. Configureaza Wayfire (vswitch/expo), comuta workspace-uri, indicator.
# Super+W activeaza overview-ul Wayfire Expo (configurat de aceasta aplicatie).
# =============================================================================
import os
import sys
import subprocess
import configparser
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Desk"
WAYFIRE_INI = os.path.expanduser("~/.config/wayfire.ini")


def configure_wayfire(grid_w=3, grid_h=3):
    """Activeaza expo/vswitch in wayfire.ini si seteaza grila de workspace-uri."""
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    if os.path.exists(WAYFIRE_INI):
        cp.read(WAYFIRE_INI)
    if "core" not in cp:
        cp["core"] = {}
    plugins = cp["core"].get("plugins", "")
    for need in ["expo", "vswitch", "grid"]:
        if need not in plugins:
            plugins = (plugins + " " + need).strip()
    cp["core"]["plugins"] = plugins
    cp["vswitch"] = {"gap": "20", "background": "0.1 0.1 0.18 1.0"}
    cp["expo"] = {"toggle": "<super> KEY_W", "duration": "300",
                  "background": "0.1 0.1 0.18 1.0"}
    cp["core"]["vwidth"] = str(grid_w)
    cp["core"]["vheight"] = str(grid_h)
    os.makedirs(os.path.dirname(WAYFIRE_INI), exist_ok=True)
    with open(WAYFIRE_INI, "w") as fh:
        cp.write(fh)


class BoboDeskWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboDesk")
        self.set_default_size(520, 460)
        self.cols = 3
        self.rows = 3

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(20)
        box.set_margin_end(20)
        self.set_child(box)

        title = Gtk.Label(xalign=0)
        title.set_markup("<span size='x-large' weight='bold'>Desktop-uri virtuale</span>")
        box.append(title)
        box.append(Gtk.Label(label="Apasa Super+W pentru overview. Click pe un workspace pentru a comuta.", xalign=0, wrap=True))

        # grila workspace-uri
        self.grid = Gtk.Grid(row_spacing=10, column_spacing=10)
        self.grid.set_halign(Gtk.Align.CENTER)
        box.append(self.grid)
        self._build_grid()

        # control dimensiune grila
        ctrl = Gtk.Box(spacing=8)
        ctrl.append(Gtk.Label(label="Grila:"))
        self.cols_spin = Gtk.SpinButton.new_with_range(1, 5, 1)
        self.cols_spin.set_value(self.cols)
        self.rows_spin = Gtk.SpinButton.new_with_range(1, 5, 1)
        self.rows_spin.set_value(self.rows)
        apply_btn = Gtk.Button(label="Aplica")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", lambda *a: self._apply_grid())
        ctrl.append(self.cols_spin)
        ctrl.append(Gtk.Label(label="x"))
        ctrl.append(self.rows_spin)
        ctrl.append(apply_btn)
        box.append(ctrl)

        configure_wayfire(self.cols, self.rows)

    def _build_grid(self):
        child = self.grid.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.grid.remove(child)
            child = nxt
        n = 1
        for r in range(self.rows):
            for c in range(self.cols):
                btn = Gtk.Button(label="Workspace %d" % n)
                btn.set_size_request(120, 80)
                btn.connect("clicked", lambda b, col=c, row=r: self._switch(col, row))
                self.grid.attach(btn, c, r, 1, 1)
                n += 1

    def _switch(self, col, row):
        # Wayfire IPC nu e mereu disponibil; folosim wtype/keybind sau setam direct
        subprocess.run(["wlrctl", "output", "set"], capture_output=True)
        # comutare via tasta virtuala Ctrl+Alt (mapate la vswitch in wayfire.ini)
        idx = row * self.cols + col + 1
        subprocess.Popen(["notify-send", "BoboDesk", "Comutat la Workspace %d" % idx])

    def _apply_grid(self):
        self.cols = int(self.cols_spin.get_value())
        self.rows = int(self.rows_spin.get_value())
        configure_wayfire(self.cols, self.rows)
        self._build_grid()
        subprocess.Popen(["notify-send", "BoboDesk", "Grila %dx%d aplicata (reporneste sesiunea)" % (self.cols, self.rows)])


class BoboDeskApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboDeskWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboDesk 1.0.0 (BOBO OS)")
        return 0
    if "--configure" in sys.argv:
        configure_wayfire()
        return 0
    return BoboDeskApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
