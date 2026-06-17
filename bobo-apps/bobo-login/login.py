#!/usr/bin/env python3
# =============================================================================
# BoboLogin - Ecran de autentificare GTK4 pentru BOBO OS (APP 14)
# Autentificare PAM, lista utilizatori, ceas, butoane power, PIN, autologin.
# Lansat de display manager (sau standalone pentru testare cu --test-window).
# =============================================================================
import os
import sys
import pwd
import time
import subprocess
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gdk, Gio  # noqa: E402

try:
    import pam as pam_module
except ImportError:
    pam_module = None

APP_ID = "os.bobo.Login"
SESSION_CMD = ["dbus-run-session", "--", "wayfire"]


def list_users():
    """Utilizatori reali (UID >= 1000, exclus nobody)."""
    users = []
    for p in pwd.getpwall():
        if 1000 <= p.pw_uid < 65000 and p.pw_shell not in ("/usr/sbin/nologin", "/bin/false"):
            users.append((p.pw_name, p.pw_gecos.split(",")[0] or p.pw_name))
    return users or [(os.environ.get("USER", "bobo"), "BOBO User")]


class BoboLoginWindow(Gtk.ApplicationWindow):
    def __init__(self, app, testing=False):
        super().__init__(application=app, title="BOBO OS")
        self.testing = testing
        self.set_default_size(1280, 800)
        if not testing:
            self.fullscreen()

        overlay = Gtk.Overlay()
        self.set_child(overlay)

        # fundal cu gradient brand (CSS)
        bg = Gtk.Box()
        bg.add_css_class("bobo-login-bg")
        overlay.set_child(bg)
        self._apply_css()

        # card central
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card.add_css_class("bobo-login-card")
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)
        card.set_size_request(360, -1)
        overlay.add_overlay(card)

        logo = Gtk.Label()
        logo.set_markup("<span size='28000' weight='bold' color='#4a9eff'>BOBO OS</span>")
        card.append(logo)

        users = list_users()
        self.user_dd = Gtk.DropDown.new_from_strings([u[1] for u in users])
        self._users = users
        card.append(self.user_dd)

        self.pass_entry = Gtk.PasswordEntry()
        self.pass_entry.set_show_peek_icon(True)
        self.pass_entry.set_property("placeholder-text", "Parola")
        self.pass_entry.connect("activate", lambda *a: self._try_login())
        card.append(self.pass_entry)

        self.error_label = Gtk.Label()
        self.error_label.add_css_class("bobo-login-error")
        card.append(self.error_label)

        login_btn = Gtk.Button(label="Autentificare")
        login_btn.add_css_class("suggested-action")
        login_btn.connect("clicked", lambda *a: self._try_login())
        card.append(login_btn)

        # ceas (dreapta sus)
        self.clock = Gtk.Label()
        self.clock.add_css_class("bobo-login-clock")
        self.clock.set_halign(Gtk.Align.END)
        self.clock.set_valign(Gtk.Align.START)
        self.clock.set_margin_top(24)
        self.clock.set_margin_end(28)
        overlay.add_overlay(self.clock)
        self._tick()
        GLib.timeout_add_seconds(1, self._tick)

        # butoane power (dreapta jos)
        power = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        power.set_halign(Gtk.Align.END)
        power.set_valign(Gtk.Align.END)
        power.set_margin_bottom(24)
        power.set_margin_end(28)
        for icon, tip, cmd in [
            ("system-suspend-symbolic", "Suspend", ["systemctl", "suspend"]),
            ("system-reboot-symbolic", "Restart", ["systemctl", "reboot"]),
            ("system-shutdown-symbolic", "Oprire", ["systemctl", "poweroff"]),
        ]:
            b = Gtk.Button.new_from_icon_name(icon)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda x, c=cmd: subprocess.Popen(c))
            power.append(b)
        overlay.add_overlay(power)

        self.pass_entry.grab_focus()

    def _apply_css(self):
        css = Gtk.CssProvider()
        css.load_from_data(b"""
        .bobo-login-bg { background: linear-gradient(135deg, #1a1a2e, #0f3460); }
        .bobo-login-card { background: rgba(22,33,62,0.92); border-radius: 18px;
            padding: 36px; box-shadow: 0 8px 40px rgba(0,0,0,0.5); }
        .bobo-login-clock { color: #e8eaf6; font-size: 18px; }
        .bobo-login-error { color: #ff5d5d; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _tick(self):
        self.clock.set_markup("<b>%s</b>\n%s" % (time.strftime("%H:%M"), time.strftime("%A, %d %B %Y")))
        return True

    def _try_login(self):
        idx = self.user_dd.get_selected()
        username = self._users[idx][0]
        password = self.pass_entry.get_text()
        if pam_module is None:
            self.error_label.set_text("Modul PAM lipsa (python3-pam)")
            return
        p = pam_module.pam()
        if p.authenticate(username, password, service="login"):
            self._start_session(username)
        else:
            self.error_label.set_text("Parola incorecta")
            self.pass_entry.set_text("")
            # animatie simpla: tremura cardul
            self.pass_entry.add_css_class("error")

    def _start_session(self, username):
        if self.testing:
            self.error_label.set_text("OK (mod test) - sesiune ar porni pentru %s" % username)
            return
        # in productie greeter-ul preda controlul display managerului;
        # standalone lansam sesiunea Wayfire pentru utilizator
        self.close()
        try:
            subprocess.Popen(SESSION_CMD)
        except Exception as e:
            print("[bobo-login] start sesiune esuat:", e)


class BoboLoginApp(Gtk.Application):
    def __init__(self, testing=False):
        super().__init__(application_id=APP_ID)
        self.testing = testing

    def do_activate(self):
        BoboLoginWindow(self, testing=self.testing).present()


def main():
    if "--version" in sys.argv:
        print("BoboLogin 1.0.0 (BOBO OS)")
        return 0
    testing = "--test-window" in sys.argv
    return BoboLoginApp(testing=testing).run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
