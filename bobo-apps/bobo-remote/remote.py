#!/usr/bin/env python3
# =============================================================================
# BoboRemote - Acces la calculatoare la distanta pentru BOBO OS (APP 24)
# GTK4. RDP (xfreerdp), VNC (vncviewer), SSH (terminal), SFTP (Nemo).
# Salveaza conexiuni cu nickname.
# =============================================================================
import os
import sys
import json
import subprocess
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Remote"
CONF = os.path.expanduser("~/.config/bobo-remote/connections.json")


def load_conns():
    try:
        with open(CONF) as fh:
            return json.load(fh)
    except Exception:
        return []


def save_conns(c):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF, "w") as fh:
        json.dump(c, fh, indent=2)


class BoboRemoteWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboRemote")
        self.set_default_size(620, 540)
        self.conns = load_conns()

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        add = Gtk.Button(label="Conexiune noua")
        add.add_css_class("suggested-action")
        add.connect("clicked", lambda *a: self.new_dialog())
        header.pack_start(add)

        sw = Gtk.ScrolledWindow()
        self.listbox = Gtk.ListBox()
        self.listbox.set_vexpand(True)
        sw.set_child(self.listbox)
        self.set_child(sw)
        self._refresh()

    def _refresh(self):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        if not self.conns:
            self.listbox.append(Gtk.Label(label="Nicio conexiune salvata. Apasa 'Conexiune noua'.", margin_top=20))
            return
        icons = {"RDP": "preferences-desktop-remote-desktop-symbolic", "VNC": "computer-symbolic",
                 "SSH": "utilities-terminal-symbolic", "SFTP": "folder-remote-symbolic"}
        for i, conn in enumerate(self.conns):
            row = Gtk.ListBoxRow()
            b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            b.set_margin_top(8)
            b.set_margin_bottom(8)
            b.set_margin_start(10)
            b.append(Gtk.Image.new_from_icon_name(icons.get(conn["type"], "network-server-symbolic")))
            tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            tb.set_hexpand(True)
            nm = Gtk.Label(label=conn["name"], xalign=0)
            det = Gtk.Label(label="%s  %s@%s:%s" % (conn["type"], conn.get("user", ""), conn["host"], conn.get("port", "")), xalign=0)
            det.add_css_class("dim-label")
            tb.append(nm)
            tb.append(det)
            b.append(tb)
            conn_btn = Gtk.Button(label="Conecteaza")
            conn_btn.add_css_class("suggested-action")
            conn_btn.connect("clicked", lambda x, c=conn: self.connect_to(c))
            b.append(conn_btn)
            dele = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            dele.connect("clicked", lambda x, idx=i: self._delete(idx))
            b.append(dele)
            row.set_child(b)
            self.listbox.append(row)

    def _delete(self, idx):
        del self.conns[idx]
        save_conns(self.conns)
        self._refresh()

    # ----------------------------------------------------------- new
    def new_dialog(self):
        win = Gtk.Window(title="Conexiune noua", transient_for=self, modal=True)
        win.set_default_size(420, -1)
        grid = Gtk.Grid(row_spacing=8, column_spacing=8, margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        type_dd = Gtk.DropDown.new_from_strings(["RDP", "VNC", "SSH", "SFTP"])
        name_e = Gtk.Entry(placeholder_text="Nume (nickname)")
        host_e = Gtk.Entry(placeholder_text="Host / IP")
        port_e = Gtk.Entry(placeholder_text="Port (optional)")
        user_e = Gtk.Entry(placeholder_text="Utilizator")
        pass_e = Gtk.PasswordEntry()
        rows = [("Tip", type_dd), ("Nume", name_e), ("Host", host_e),
                ("Port", port_e), ("Utilizator", user_e), ("Parola", pass_e)]
        for r, (lbl, w) in enumerate(rows):
            grid.attach(Gtk.Label(label=lbl, xalign=0), 0, r, 1, 1)
            w.set_hexpand(True)
            grid.attach(w, 1, r, 1, 1)
        save = Gtk.Button(label="Salveaza")
        save.add_css_class("suggested-action")

        def do_save(*a):
            self.conns.append({
                "type": ["RDP", "VNC", "SSH", "SFTP"][type_dd.get_selected()],
                "name": name_e.get_text() or host_e.get_text(),
                "host": host_e.get_text(),
                "port": port_e.get_text(),
                "user": user_e.get_text(),
                "password": pass_e.get_text(),
            })
            save_conns(self.conns)
            win.close()
            self._refresh()
        save.connect("clicked", do_save)
        grid.attach(save, 0, len(rows), 2, 1)
        win.set_child(grid)
        win.present()

    # ----------------------------------------------------------- connect
    def connect_to(self, conn):
        t = conn["type"]
        host = conn["host"]
        user = conn.get("user", "")
        port = conn.get("port", "")
        pw = conn.get("password", "")
        try:
            if t == "RDP":
                cmd = ["xfreerdp", "/v:%s%s" % (host, ":" + port if port else ""),
                       "/u:%s" % user, "/cert:ignore", "+clipboard", "/sound", "/dynamic-resolution"]
                if pw:
                    cmd.append("/p:%s" % pw)
                subprocess.Popen(cmd)
            elif t == "VNC":
                target = "%s:%s" % (host, port or "5900")
                subprocess.Popen(["vncviewer", target])
            elif t == "SSH":
                ssh = "ssh %s@%s%s" % (user, host, " -p " + port if port else "")
                subprocess.Popen(["foot", "-e", "bash", "-c", ssh + "; read -p 'Apasa Enter...'"])
            elif t == "SFTP":
                url = "sftp://%s@%s%s" % (user, host, ":" + port if port else "")
                subprocess.Popen(["nemo", url])
            self._notify("Conectare %s la %s" % (t, host))
        except Exception as e:
            self._notify("Eroare: %s" % e)

    def _notify(self, text):
        GLib.spawn_command_line_async("notify-send 'BoboRemote' '%s'" % text.replace("'", ""))


class BoboRemoteApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboRemoteWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboRemote 1.0.0 (BOBO OS)")
        return 0
    return BoboRemoteApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
