#!/usr/bin/env python3
# =============================================================================
# BoboSettings - Centru de control BOBO OS (APP 03)
# GTK4. Sidebar cu categorii + panouri functionale care apeleaza uneltele
# de sistem (wpctl, nmcli, bluetoothctl, gsettings, timedatectl, brightnessctl).
# =============================================================================
import os
import sys
import subprocess
import platform
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk  # noqa: E402

APP_ID = "os.bobo.Settings"


def run(cmd, timeout=8):
    """Ruleaza o comanda si intoarce stdout (string), gol la eroare."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def run_async(cmd):
    try:
        GLib.spawn_async(cmd, flags=GLib.SpawnFlags.SEARCH_PATH)
    except Exception:
        try:
            subprocess.Popen(cmd)
        except Exception:
            pass


class BoboSettingsWindow(Gtk.ApplicationWindow):
    PANELS = [
        ("display", "Afisaj", "video-display-symbolic"),
        ("sound", "Sunet", "audio-speakers-symbolic"),
        ("network", "Retea", "network-wireless-symbolic"),
        ("bluetooth", "Bluetooth", "bluetooth-symbolic"),
        ("appearance", "Aspect", "preferences-desktop-theme-symbolic"),
        ("keyboard", "Tastatura", "input-keyboard-symbolic"),
        ("mouse", "Mouse", "input-mouse-symbolic"),
        ("power", "Energie", "battery-symbolic"),
        ("datetime", "Data si ora", "preferences-system-time-symbolic"),
        ("privacy", "Confidentialitate", "preferences-system-privacy-symbolic"),
        ("security", "Securitate", "security-high-symbolic"),
        ("about", "Despre", "help-about-symbolic"),
    ]

    def __init__(self, app):
        super().__init__(application=app, title="BoboSettings")
        self.set_default_size(880, 600)

        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(split)

        # ---- sidebar cu cautare ----
        sb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sb.set_size_request(220, -1)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Cauta in setari...")
        self.search.connect("search-changed", self._filter_sidebar)
        sb.append(self.search)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        self.listbox = Gtk.ListBox()
        self.listbox.add_css_class("navigation-sidebar")
        self.listbox.connect("row-selected", self._on_row_selected)
        sw.set_child(self.listbox)
        sb.append(sw)
        split.set_start_child(sb)
        split.set_resize_start_child(False)
        split.set_shrink_start_child(False)

        # ---- continut (stack) ----
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_hexpand(True)
        split.set_end_child(self.stack)

        for key, title, icon in self.PANELS:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(10)
            box.append(Gtk.Image.new_from_icon_name(icon))
            lbl = Gtk.Label(label=title, xalign=0)
            box.append(lbl)
            row.set_child(box)
            row._key = key
            row._title = title.lower()
            self.listbox.append(row)
            builder = getattr(self, "_panel_" + key)
            self.stack.add_named(self._scrolled(builder()), key)

        self.listbox.select_row(self.listbox.get_row_at_index(0))

    # ---------------------------------------------------------- helpers UI
    def _scrolled(self, widget):
        sw = Gtk.ScrolledWindow()
        sw.set_child(widget)
        return sw

    def _page(self, title):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(20)
        box.set_margin_end(20)
        h = Gtk.Label(xalign=0)
        h.set_markup("<span size='x-large' weight='bold'>%s</span>" % title)
        box.append(h)
        return box

    def _row(self, label, widget):
        r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        r.add_css_class("card")
        lbl = Gtk.Label(label=label, xalign=0)
        lbl.set_hexpand(True)
        r.append(lbl)
        r.append(widget)
        return r

    def _on_row_selected(self, lb, row):
        if row:
            self.stack.set_visible_child_name(row._key)

    def _filter_sidebar(self, entry):
        text = entry.get_text().lower()
        child = self.listbox.get_first_child()
        while child:
            child.set_visible(text in child._title)
            child = child.get_next_sibling()

    # ---------------------------------------------------------- panouri
    def _panel_display(self):
        box = self._page("Afisaj")
        modes = run(["wlr-randr"]) or "Informatii afisaj indisponibile (wlr-randr)."
        info = Gtk.Label(label=modes, xalign=0)
        info.set_selectable(True)
        box.append(self._row("Moduri detectate", Gtk.Label(label="vezi mai jos")))
        box.append(info)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1.0, 2.0, 0.25)
        scale.set_value(1.0)
        scale.set_size_request(180, -1)
        box.append(self._row("Scalare HiDPI", scale))
        night = Gtk.Switch()
        night.connect("state-set", lambda s, v: (run_async(["wlsunset", "-t", "3500"]) if v else run_async(["pkill", "wlsunset"]), False)[1])
        box.append(self._row("Mod noapte (wlsunset)", night))
        return box

    def _panel_sound(self):
        box = self._page("Sunet")
        vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        vol.set_size_request(220, -1)
        cur = run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        try:
            vol.set_value(float(cur.split()[1]) * 100)
        except Exception:
            vol.set_value(50)
        vol.connect("value-changed", lambda s: run_async(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "%d%%" % int(s.get_value())]))
        box.append(self._row("Volum iesire", vol))
        mute = Gtk.Button(label="Mut / Demut")
        mute.connect("clicked", lambda *a: run_async(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]))
        box.append(self._row("Mute", mute))
        test = Gtk.Button(label="Test sunet")
        test.connect("clicked", lambda *a: run_async(["pw-play", "/usr/share/sounds/alsa/Front_Center.wav"]))
        box.append(self._row("Test", test))
        devs = run(["wpctl", "status"]) or "PipeWire indisponibil."
        lbl = Gtk.Label(label=devs, xalign=0)
        lbl.set_selectable(True)
        box.append(lbl)
        return box

    def _panel_network(self):
        box = self._page("Retea")
        refresh = Gtk.Button(label="Scaneaza WiFi")
        wifi_list = Gtk.Label(xalign=0, label="(apasa Scaneaza)")
        wifi_list.set_selectable(True)
        refresh.connect("clicked", lambda *a: wifi_list.set_text(run(["nmcli", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"]) or "nmcli indisponibil"))
        box.append(self._row("Retele WiFi", refresh))
        box.append(wifi_list)
        editor = Gtk.Button(label="Editor conexiuni (nm-connection-editor)")
        editor.connect("clicked", lambda *a: run_async(["nm-connection-editor"]))
        box.append(self._row("Avansat", editor))
        return box

    def _panel_bluetooth(self):
        box = self._page("Bluetooth")
        toggle = Gtk.Switch()
        toggle.connect("state-set", lambda s, v: (run_async(["rfkill", "unblock" if v else "block", "bluetooth"]), False)[1])
        box.append(self._row("Bluetooth pornit", toggle))
        scan = Gtk.Button(label="Scaneaza dispozitive")
        out = Gtk.Label(xalign=0, label="(apasa Scaneaza)")
        out.set_selectable(True)
        scan.connect("clicked", lambda *a: out.set_text(run(["bluetoothctl", "devices"]) or "bluetoothctl indisponibil"))
        box.append(self._row("Dispozitive", scan))
        box.append(out)
        mgr = Gtk.Button(label="Manager (blueman)")
        mgr.connect("clicked", lambda *a: run_async(["blueman-manager"]))
        box.append(self._row("Avansat", mgr))
        return box

    def _panel_appearance(self):
        box = self._page("Aspect")
        dark = Gtk.Switch()
        dark.set_active(True)
        dark.connect("state-set", lambda s, v: (run_async(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", "prefer-dark" if v else "prefer-light"]), False)[1])
        box.append(self._row("Mod intunecat", dark))
        accents = ["#4a9eff", "#4ade80", "#ff5d5d", "#ffb454", "#bd93f9", "#8be9fd"]
        accent_box = Gtk.Box(spacing=6)
        for c in accents:
            b = Gtk.Button(label=" ")
            b.set_size_request(28, 28)
            prov = Gtk.CssProvider()
            prov.load_from_data(("button { background:%s; border-radius:14px; }" % c).encode())
            b.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            accent_box.append(b)
        box.append(self._row("Culoare accent", accent_box))
        wall = Gtk.Button(label="Alege wallpaper...")
        wall.connect("clicked", self._choose_wallpaper)
        box.append(self._row("Wallpaper", wall))
        return box

    def _choose_wallpaper(self, *a):
        dialog = Gtk.FileDialog()
        dialog.open(self, None, self._wallpaper_chosen)

    def _wallpaper_chosen(self, dialog, res):
        try:
            f = dialog.open_finish(res)
            if f:
                run_async(["pkill", "swaybg"])
                run_async(["swaybg", "-m", "fill", "-i", f.get_path()])
        except GLib.Error:
            pass

    def _panel_keyboard(self):
        box = self._page("Tastatura")
        layout = Gtk.Entry()
        layout.set_text(run(["setxkbmap", "-query"]).split("layout:")[-1].strip() if "layout" in run(["setxkbmap", "-query"]) else "us")
        apply_btn = Gtk.Button(label="Aplica layout")
        apply_btn.connect("clicked", lambda *a: run_async(["setxkbmap", layout.get_text()]))
        box.append(self._row("Layout tastatura", layout))
        box.append(self._row("", apply_btn))
        box.append(Gtk.Label(label="Scurtaturile Wayfire se afla in ~/.config/wayfire.ini", xalign=0))
        return box

    def _panel_mouse(self):
        box = self._page("Mouse")
        natural = Gtk.Switch()
        natural.connect("state-set", lambda s, v: (run_async(["gsettings", "set", "org.gnome.desktop.peripherals.touchpad", "natural-scroll", "true" if v else "false"]), False)[1])
        box.append(self._row("Scrollare naturala", natural))
        speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1, 1, 0.1)
        speed.set_size_request(180, -1)
        speed.connect("value-changed", lambda s: run_async(["gsettings", "set", "org.gnome.desktop.peripherals.mouse", "speed", str(s.get_value())]))
        box.append(self._row("Viteza cursor", speed))
        return box

    def _panel_power(self):
        box = self._page("Energie")
        bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 100, 1)
        bright.set_size_request(220, -1)
        bright.set_value(80)
        bright.connect("value-changed", lambda s: run_async(["brightnessctl", "s", "%d%%" % int(s.get_value())]))
        box.append(self._row("Luminozitate ecran", bright))
        bat = run(["cat", "/sys/class/power_supply/BAT0/capacity"]) or run(["cat", "/sys/class/power_supply/BAT1/capacity"])
        box.append(self._row("Nivel baterie", Gtk.Label(label=(bat + "%") if bat else "fara baterie")))
        return box

    def _panel_datetime(self):
        box = self._page("Data si ora")
        info = Gtk.Label(label=run(["timedatectl"]) or "timedatectl indisponibil", xalign=0)
        info.set_selectable(True)
        ntp = Gtk.Switch()
        ntp.set_active("yes" in run(["timedatectl", "show", "-p", "NTP", "--value"]).lower())
        ntp.connect("state-set", lambda s, v: (run_async(["pkexec", "timedatectl", "set-ntp", "true" if v else "false"]), False)[1])
        box.append(self._row("Sincronizare NTP", ntp))
        box.append(info)
        return box

    def _panel_privacy(self):
        box = self._page("Confidentialitate")
        for perm in ["Cameră", "Microfon", "Locație"]:
            sw = Gtk.Switch()
            sw.set_active(True)
            box.append(self._row("Permite acces: %s" % perm, sw))
        box.append(Gtk.Label(label="BOBO OS nu colecteaza telemetrie.", xalign=0))
        return box

    def _panel_security(self):
        box = self._page("Securitate")
        fw = Gtk.Label(label=run(["nft", "list", "ruleset"])[:1500] or "Firewall: nft indisponibil (ruleaza ca root)", xalign=0)
        fw.set_selectable(True)
        box.append(self._row("Profil firewall", Gtk.Label(label="home / work / public")))
        for prof in ["home", "work", "public"]:
            b = Gtk.Button(label="Aplica profil %s" % prof)
            b.connect("clicked", lambda x, p=prof: run_async(["pkexec", "/usr/local/lib/bobo/core/security/firewall-setup.sh", p]))
            box.append(b)
        box.append(fw)
        return box

    def _panel_about(self):
        box = self._page("Despre BOBO OS")
        uname = platform.uname()
        try:
            mem = int(run(["bash", "-c", "grep MemTotal /proc/meminfo | awk '{print $2}'"]) or 0) / 1e6
        except Exception:
            mem = 0
        rows = [
            ("Sistem", "BOBO OS 1.0.0"),
            ("Kernel", uname.release),
            ("Arhitectura", uname.machine),
            ("Procesor", run(["bash", "-c", "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2"]).strip() or uname.processor),
            ("Memorie RAM", "%.1f GB" % mem),
            ("Hostname", uname.node),
            ("Licenta", "Open Source (MIT / GPL / LGPL)"),
        ]
        for k, v in rows:
            box.append(self._row(k, Gtk.Label(label=v)))
        return box


class BoboSettingsApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboSettingsWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboSettings 1.0.0 (BOBO OS)")
        return 0
    return BoboSettingsApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
