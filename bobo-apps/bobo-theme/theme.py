#!/usr/bin/env python3
# =============================================================================
# BoboTheme - Manager de teme pentru BOBO OS (APP 18)
# GTK4. Teme Dark/Light/AMOLED, accent, iconite, fonturi, wallpaper,
# preview live, export/import .bobotheme.
# =============================================================================
import os
import sys
import json
import zipfile
import subprocess
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk  # noqa: E402

APP_ID = "os.bobo.Theme"
CONF = os.path.expanduser("~/.config/bobo-theme/current.json")
THEME_DIR = os.path.expanduser("~/.local/share/themes")

THEMES = {
    "BOBO Dark": {"bg": "#1a1a2e", "fg": "#e8eaf6", "scheme": "prefer-dark"},
    "BOBO Light": {"bg": "#f5f5f5", "fg": "#1a1a1a", "scheme": "prefer-light"},
    "BOBO AMOLED": {"bg": "#000000", "fg": "#ffffff", "scheme": "prefer-dark"},
}
ACCENTS = ["#4a9eff", "#4ade80", "#ff5d5d", "#ffb454", "#bd93f9", "#8be9fd",
           "#ff79c6", "#50fa7b", "#f1fa8c", "#ff5555", "#6272a4", "#ffffff"]


def gset(schema, key, val):
    subprocess.run(["gsettings", "set", schema, key, val], capture_output=True)


def load_conf():
    try:
        with open(CONF) as fh:
            return json.load(fh)
    except Exception:
        return {"theme": "BOBO Dark", "accent": "#4a9eff", "icons": "Papirus-Dark", "font": "Inter 10"}


def save_conf(c):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF, "w") as fh:
        json.dump(c, fh, indent=2)


class BoboThemeWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboTheme")
        self.set_default_size(560, 640)
        self.conf = load_conf()

        sw = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(20)
        box.set_margin_end(20)
        sw.set_child(box)
        self.set_child(sw)

        box.append(self._title("Tema"))
        theme_box = Gtk.Box(spacing=10)
        self.theme_buttons = {}
        for name, data in THEMES.items():
            b = Gtk.ToggleButton(label=name)
            b.connect("toggled", self._on_theme, name)
            if name == self.conf["theme"]:
                b.set_active(True)
            self.theme_buttons[name] = b
            theme_box.append(b)
        box.append(theme_box)

        box.append(self._title("Culoare accent"))
        accent_grid = Gtk.FlowBox()
        accent_grid.set_max_children_per_line(6)
        accent_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        for c in ACCENTS:
            btn = Gtk.Button()
            btn.set_size_request(36, 36)
            prov = Gtk.CssProvider()
            prov.load_from_data(("button { background:%s; border-radius:18px; min-width:0; }" % c).encode())
            btn.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            btn.connect("clicked", lambda b, col=c: self._on_accent(col))
            accent_grid.append(btn)
        box.append(accent_grid)
        custom = Gtk.ColorButton()
        custom.connect("color-set", self._on_custom_accent)
        box.append(self._row("Accent personalizat", custom))

        box.append(self._title("Iconite"))
        self.icon_dd = Gtk.DropDown.new_from_strings(self._installed_icon_themes())
        self.icon_dd.connect("notify::selected", self._on_icons)
        box.append(self.icon_dd)

        box.append(self._title("Font interfata"))
        self.font_btn = Gtk.FontButton()
        self.font_btn.set_font(self.conf.get("font", "Inter 10"))
        self.font_btn.connect("font-set", self._on_font)
        box.append(self.font_btn)

        box.append(self._title("Wallpaper"))
        wall = Gtk.Button(label="Alege wallpaper...")
        wall.connect("clicked", lambda *a: self._choose_wallpaper())
        box.append(wall)
        slideshow = Gtk.Switch()
        slideshow.set_halign(Gtk.Align.START)
        box.append(self._row("Slideshow wallpaper (folder Pictures)", slideshow))
        self.slideshow_sw = slideshow

        box.append(self._title("Pachet tema"))
        io_box = Gtk.Box(spacing=8)
        exp = Gtk.Button(label="Exporta .bobotheme")
        exp.connect("clicked", lambda *a: self._export())
        imp = Gtk.Button(label="Importa .bobotheme")
        imp.connect("clicked", lambda *a: self._import())
        io_box.append(exp)
        io_box.append(imp)
        box.append(io_box)

    def _title(self, text):
        l = Gtk.Label(xalign=0)
        l.set_markup("<b>%s</b>" % text)
        return l

    def _row(self, label, widget):
        b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        lbl = Gtk.Label(label=label, xalign=0)
        lbl.set_hexpand(True)
        b.append(lbl)
        b.append(widget)
        return b

    def _installed_icon_themes(self):
        themes = set()
        for d in ["/usr/share/icons", os.path.expanduser("~/.local/share/icons")]:
            if os.path.isdir(d):
                for name in os.listdir(d):
                    if os.path.isdir(os.path.join(d, name, "scalable")) or \
                       os.path.exists(os.path.join(d, name, "index.theme")):
                        themes.add(name)
        return sorted(themes) or ["Adwaita"]

    # ----------------------------------------------------------- handlers
    def _on_theme(self, btn, name):
        if not btn.get_active():
            return
        for n, b in self.theme_buttons.items():
            if n != name:
                b.set_active(False)
        data = THEMES[name]
        gset("org.gnome.desktop.interface", "color-scheme", data["scheme"])
        self.conf["theme"] = name
        self._apply_live(data["bg"], data["fg"], self.conf["accent"])
        save_conf(self.conf)

    def _on_accent(self, color):
        self.conf["accent"] = color
        data = THEMES[self.conf["theme"]]
        self._apply_live(data["bg"], data["fg"], color)
        gset("org.gnome.desktop.interface", "accent-color", color)
        save_conf(self.conf)

    def _on_custom_accent(self, btn):
        rgba = btn.get_rgba()
        color = "#%02x%02x%02x" % (int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255))
        self._on_accent(color)

    def _on_icons(self, dd, _):
        name = self.icon_dd.get_selected_item().get_string()
        gset("org.gnome.desktop.interface", "icon-theme", name)
        self.conf["icons"] = name
        save_conf(self.conf)

    def _on_font(self, btn):
        font = btn.get_font()
        gset("org.gnome.desktop.interface", "font-name", font)
        self.conf["font"] = font
        save_conf(self.conf)

    def _apply_live(self, bg, fg, accent):
        """Scrie tema GTK4 personalizata si o aplica imediat."""
        gtk_dir = os.path.join(THEME_DIR, "BOBO-Live", "gtk-4.0")
        os.makedirs(gtk_dir, exist_ok=True)
        css = ("@define-color window_bg_color %s;\n@define-color window_fg_color %s;\n"
               "@define-color accent_color %s;\n@define-color accent_bg_color %s;\n") % (bg, fg, accent, accent)
        with open(os.path.join(gtk_dir, "gtk.css"), "w") as fh:
            fh.write(css)
        # aplica si in sesiunea curenta
        prov = Gtk.CssProvider()
        prov.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def _choose_wallpaper(self):
        d = Gtk.FileDialog()
        d.open(self, None, self._wallpaper_set)

    def _wallpaper_set(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if f:
            subprocess.run(["pkill", "swaybg"], capture_output=True)
            subprocess.Popen(["swaybg", "-m", "fill", "-i", f.get_path()])
            self.conf["wallpaper"] = f.get_path()
            save_conf(self.conf)

    def _export(self):
        d = Gtk.FileDialog()
        d.set_initial_name("tema.bobotheme")
        d.save(self, None, self._do_export)

    def _do_export(self, dialog, res):
        try:
            f = dialog.save_finish(res)
        except GLib.Error:
            return
        if f:
            with zipfile.ZipFile(f.get_path(), "w") as z:
                z.writestr("theme.json", json.dumps(self.conf, indent=2))
                live = os.path.join(THEME_DIR, "BOBO-Live", "gtk-4.0", "gtk.css")
                if os.path.exists(live):
                    z.write(live, "gtk.css")

    def _import(self):
        d = Gtk.FileDialog()
        d.open(self, None, self._do_import)

    def _do_import(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if f:
            with zipfile.ZipFile(f.get_path()) as z:
                self.conf = json.loads(z.read("theme.json"))
            save_conf(self.conf)
            data = THEMES.get(self.conf["theme"], THEMES["BOBO Dark"])
            self._apply_live(data["bg"], data["fg"], self.conf["accent"])


class BoboThemeApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboThemeWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboTheme 1.0.0 (BOBO OS)")
        return 0
    return BoboThemeApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
