#!/usr/bin/env python3
# =============================================================================
# BoboVPN - Client VPN pentru BOBO OS (APP 22)
# GTK4. WireGuard (wg-quick) + OpenVPN (nmcli/openvpn). Profiluri, kill switch
# (nftables), status (IP public, trafic).
# =============================================================================
import os
import sys
import json
import shutil
import threading
import subprocess
import urllib.request
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.VPN"
CONF_DIR = os.path.expanduser("~/.config/bobo-vpn")
PROFILES = os.path.join(CONF_DIR, "profiles.json")
WG_DIR = "/etc/wireguard"


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def load_profiles():
    try:
        with open(PROFILES) as fh:
            return json.load(fh)
    except Exception:
        return []


def save_profiles(p):
    os.makedirs(CONF_DIR, exist_ok=True)
    with open(PROFILES, "w") as fh:
        json.dump(p, fh, indent=2)


class BoboVPNWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboVPN")
        self.set_default_size(560, 520)
        self.profiles = load_profiles()
        self.active = None

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        imp = Gtk.Button(label="Importa config")
        imp.connect("clicked", lambda *a: self.import_dialog())
        header.pack_start(imp)
        self.kill_switch = Gtk.ToggleButton(label="Kill Switch")
        self.kill_switch.set_tooltip_text("Blocheaza tot traficul daca VPN cade")
        self.kill_switch.connect("toggled", self._toggle_killswitch)
        header.pack_end(self.kill_switch)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_child(box)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_margin_start(12)
        self.status_label.set_margin_top(8)
        box.append(self.status_label)

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        self.listbox = Gtk.ListBox()
        sw.set_child(self.listbox)
        box.append(sw)
        self._refresh()
        self._update_status()

    def _refresh(self):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        for prof in self.profiles:
            row = Gtk.ListBoxRow()
            b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            b.set_margin_top(8)
            b.set_margin_bottom(8)
            b.set_margin_start(10)
            icon = Gtk.Image.new_from_icon_name("network-vpn-symbolic")
            b.append(icon)
            tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            tb.set_hexpand(True)
            name = Gtk.Label(label=prof["name"], xalign=0)
            typ = Gtk.Label(label=prof["type"].upper(), xalign=0)
            typ.add_css_class("dim-label")
            tb.append(name)
            tb.append(typ)
            b.append(tb)
            connected = self.active == prof["name"]
            btn = Gtk.Button(label="Deconecteaza" if connected else "Conecteaza")
            if not connected:
                btn.add_css_class("suggested-action")
            btn.connect("clicked", lambda x, p=prof: self._toggle_connection(p))
            b.append(btn)
            row.set_child(b)
            self.listbox.append(row)

    # ----------------------------------------------------------- import
    def import_dialog(self):
        d = Gtk.FileDialog()
        d.open(self, None, self._import_finished)

    def _import_finished(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        path = f.get_path()
        name = os.path.splitext(os.path.basename(path))[0]
        if path.endswith(".conf"):
            # WireGuard: copiaza in /etc/wireguard
            sh(["pkexec", "cp", path, os.path.join(WG_DIR, name + ".conf")])
            self.profiles.append({"name": name, "type": "wireguard", "path": os.path.join(WG_DIR, name + ".conf")})
        elif path.endswith(".ovpn"):
            sh(["nmcli", "connection", "import", "type", "openvpn", "file", path])
            self.profiles.append({"name": name, "type": "openvpn", "path": path})
        save_profiles(self.profiles)
        self._refresh()

    # ----------------------------------------------------------- connect
    def _toggle_connection(self, prof):
        if self.active == prof["name"]:
            self._disconnect(prof)
        else:
            self._connect(prof)

    def _connect(self, prof):
        if prof["type"] == "wireguard":
            r = sh(["pkexec", "wg-quick", "up", prof["name"]])
        else:
            r = sh(["nmcli", "connection", "up", prof["name"]])
        if r.returncode == 0:
            self.active = prof["name"]
            self._notify("Conectat la %s" % prof["name"])
        else:
            self._notify("Conectare esuata: %s" % r.stderr[:120])
        self._refresh()
        self._update_status()

    def _disconnect(self, prof):
        if prof["type"] == "wireguard":
            sh(["pkexec", "wg-quick", "down", prof["name"]])
        else:
            sh(["nmcli", "connection", "down", prof["name"]])
        self.active = None
        self._refresh()
        self._update_status()

    # ----------------------------------------------------------- kill switch
    def _toggle_killswitch(self, btn):
        if btn.get_active():
            # permite doar loopback + interfata wg/tun
            rules = (
                "table inet bobo_vpn_ks { chain out { type filter hook output priority 0; policy drop; "
                "oifname \"lo\" accept; oifname \"wg*\" accept; oifname \"tun*\" accept; "
                "udp dport 51820 accept; ct state established,related accept; } }")
            sh(["pkexec", "nft", rules])
            self._notify("Kill switch ACTIV")
        else:
            sh(["pkexec", "nft", "delete", "table", "inet", "bobo_vpn_ks"])
            self._notify("Kill switch dezactivat")

    # ----------------------------------------------------------- status
    def _update_status(self):
        threading.Thread(target=self._fetch_status, daemon=True).start()

    def _fetch_status(self):
        try:
            ip = urllib.request.urlopen("https://api.ipify.org", timeout=5).read().decode()
        except Exception:
            ip = "indisponibil"
        state = "Conectat: %s" % self.active if self.active else "Deconectat"
        GLib.idle_add(self.status_label.set_markup,
                      "<b>%s</b>    IP public: <tt>%s</tt>" % (state, ip))

    def _notify(self, text):
        GLib.spawn_command_line_async("notify-send -i network-vpn 'BoboVPN' '%s'" % text.replace("'", ""))


class BoboVPNApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboVPNWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboVPN 1.0.0 (BOBO OS)")
        return 0
    return BoboVPNApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
