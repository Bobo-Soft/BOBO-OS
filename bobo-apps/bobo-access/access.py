#!/usr/bin/env python3
# =============================================================================
# BoboAccess - Panou de accesibilitate pentru BOBO OS (APP 13)
# GTK4. Screen reader (Orca/espeak-ng), lupa, contrast, text mare,
# taste lipicioase/lente, mouse keys, TTS cursor, animatii reduse.
# =============================================================================
import os
import sys
import subprocess
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Access"
AUTOSTART = os.path.expanduser("~/.config/autostart")


def sh(cmd):
    try:
        subprocess.Popen(cmd)
    except Exception as e:
        print("[bobo-access]", e)


def gset(schema, key, value):
    sh(["gsettings", "set", schema, key, value])


class BoboAccessWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboAccess")
        self.set_default_size(560, 640)
        self._orca = None
        self._tts_proc = None

        sw = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(20)
        box.set_margin_end(20)
        sw.set_child(box)
        self.set_child(sw)

        title = Gtk.Label(xalign=0)
        title.set_markup("<span size='xx-large' weight='bold'>Accesibilitate</span>")
        box.append(title)

        # Screen reader
        sr = Gtk.Switch()
        sr.connect("state-set", self._on_screen_reader)
        box.append(self._row("Cititor de ecran (Orca + espeak-ng)", sr))

        # Lupa (magnifier)
        mag = Gtk.Switch()
        mag.connect("state-set", lambda s, v: (gset("org.gnome.desktop.a11y.magnifier", "mag-factor", "2.0"),
                                               gset("org.gnome.desktop.a11y.applications", "screen-magnifier-enabled", "true" if v else "false"), False)[2])
        box.append(self._row("Lupa ecran", mag))
        zoom = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1.0, 5.0, 0.5)
        zoom.set_value(2.0)
        zoom.set_size_request(200, -1)
        zoom.connect("value-changed", lambda s: gset("org.gnome.desktop.a11y.magnifier", "mag-factor", str(s.get_value())))
        box.append(self._row("Nivel zoom lupa", zoom))

        # Contrast ridicat
        hc = Gtk.Switch()
        hc.connect("state-set", lambda s, v: (gset("org.gnome.desktop.interface", "gtk-theme", "HighContrast" if v else "BOBO-Dark"), False)[1])
        box.append(self._row("Contrast ridicat", hc))

        # Text mare
        lt = Gtk.Switch()
        lt.connect("state-set", lambda s, v: (gset("org.gnome.desktop.interface", "text-scaling-factor", "1.4" if v else "1.0"), False)[1])
        box.append(self._row("Text mare", lt))
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1.0, 2.0, 0.1)
        scale.set_value(1.0)
        scale.set_size_request(200, -1)
        scale.connect("value-changed", lambda s: gset("org.gnome.desktop.interface", "text-scaling-factor", str(s.get_value())))
        box.append(self._row("Scalare text", scale))

        # Taste lipicioase / lente / mouse keys (via gsettings a11y keyboard)
        sticky = Gtk.Switch()
        sticky.connect("state-set", lambda s, v: (gset("org.gnome.desktop.a11y.keyboard", "stickykeys-enable", "true" if v else "false"), False)[1])
        box.append(self._row("Taste lipicioase (Sticky Keys)", sticky))
        slow = Gtk.Switch()
        slow.connect("state-set", lambda s, v: (gset("org.gnome.desktop.a11y.keyboard", "slowkeys-enable", "true" if v else "false"), False)[1])
        box.append(self._row("Taste lente (Slow Keys)", slow))
        mk = Gtk.Switch()
        mk.connect("state-set", lambda s, v: (gset("org.gnome.desktop.a11y.keyboard", "mousekeys-enable", "true" if v else "false"), False)[1])
        box.append(self._row("Control cursor cu tastatura (Mouse Keys)", mk))

        # TTS cursor (citeste textul selectat la cerere)
        tts = Gtk.Button(label="Citeste textul din clipboard")
        tts.connect("clicked", lambda *a: self._speak_clipboard())
        box.append(self._row("Text-to-Speech", tts))

        # Animatii reduse
        anim = Gtk.Switch()
        anim.connect("state-set", lambda s, v: (gset("org.gnome.desktop.interface", "enable-animations", "false" if v else "true"), False)[1])
        box.append(self._row("Animatii reduse", anim))

        # Pornire automata la login
        self.autostart_chk = Gtk.CheckButton(label="Porneste componentele selectate la autentificare")
        self.autostart_chk.connect("toggled", self._on_autostart)
        box.append(self.autostart_chk)

    def _row(self, label, widget):
        b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        b.add_css_class("card")
        b.set_margin_bottom(2)
        lbl = Gtk.Label(label=label, xalign=0)
        lbl.set_hexpand(True)
        widget.set_halign(Gtk.Align.END)
        b.append(lbl)
        b.append(widget)
        return b

    def _on_screen_reader(self, sw, active):
        if active:
            gset("org.gnome.desktop.a11y.applications", "screen-reader-enabled", "true")
            self._orca = subprocess.Popen(["orca", "--replace"])
        else:
            gset("org.gnome.desktop.a11y.applications", "screen-reader-enabled", "false")
            subprocess.run(["pkill", "orca"])
        return False

    def _speak_clipboard(self):
        try:
            text = subprocess.run(["wl-paste"], capture_output=True, text=True, timeout=5).stdout
        except Exception:
            text = ""
        if text:
            sh(["espeak-ng", "-v", "ro", text[:500]])

    def _on_autostart(self, chk):
        os.makedirs(AUTOSTART, exist_ok=True)
        path = os.path.join(AUTOSTART, "bobo-access-a11y.desktop")
        if chk.get_active():
            with open(path, "w") as fh:
                fh.write("[Desktop Entry]\nType=Application\nName=BOBO A11y\nExec=orca --replace\nX-GNOME-Autostart-enabled=true\n")
        else:
            try:
                os.remove(path)
            except Exception:
                pass


class BoboAccessApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboAccessWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboAccess 1.0.0 (BOBO OS)")
        return 0
    return BoboAccessApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
