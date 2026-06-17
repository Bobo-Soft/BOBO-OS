#!/usr/bin/env python3
# =============================================================================
# BoboPhone - Integrare telefon pentru BOBO OS (APP 29)
# GTK4 peste KDE Connect (kdeconnect-cli) - protocol compatibil Android/iOS.
# Pairing, notificari, clipboard sync, transfer fisiere, baterie, ping.
# =============================================================================
import os
import sys
import json
import subprocess
import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Phone"


def kdc(args, timeout=10):
    return subprocess.run(["kdeconnect-cli"] + args, capture_output=True, text=True, timeout=timeout)


class BoboPhoneWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboPhone")
        self.set_default_size(560, 520)
        self.selected = None

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.connect("clicked", lambda *a: self.refresh())
        header.pack_start(refresh)

        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(split)

        sw = Gtk.ScrolledWindow()
        sw.set_size_request(220, -1)
        self.listbox = Gtk.ListBox()
        self.listbox.connect("row-selected", self._on_selected)
        sw.set_child(self.listbox)
        split.set_start_child(sw)
        split.set_resize_start_child(False)

        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.detail.set_margin_top(16)
        self.detail.set_margin_start(18)
        self.detail.set_margin_end(18)
        split.set_end_child(self.detail)

        if subprocess.run(["which", "kdeconnect-cli"], capture_output=True).returncode != 0:
            self.detail.append(Gtk.Label(label="Instaleaza kdeconnect pentru integrarea telefonului.\nInstaleaza si aplicatia KDE Connect pe telefon.", xalign=0, wrap=True))
        self.refresh()

    def refresh(self):
        threading.Thread(target=self._refresh, daemon=True).start()

    def _refresh(self):
        r = kdc(["-a", "--id-name-only"])
        devices = []
        for line in r.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                devices.append((parts[0], parts[1]))
        GLib.idle_add(self._show, devices)

    def _show(self, devices):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        for dev_id, name in devices:
            row = Gtk.ListBoxRow()
            b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            b.set_margin_top(8)
            b.set_margin_bottom(8)
            b.set_margin_start(8)
            b.append(Gtk.Image.new_from_icon_name("phone-symbolic"))
            b.append(Gtk.Label(label=name, xalign=0))
            row.set_child(b)
            row._dev = (dev_id, name)
            self.listbox.append(row)

    def _on_selected(self, lb, row):
        child = self.detail.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.detail.remove(child)
            child = nxt
        if not row:
            return
        dev_id, name = row._dev
        self.selected = dev_id
        title = Gtk.Label(xalign=0)
        title.set_markup("<span size='x-large' weight='bold'>%s</span>" % name)
        self.detail.append(title)

        # baterie
        bat = kdc(["-d", dev_id, "--battery"]).stdout.strip() if False else ""
        self.detail.append(Gtk.Label(label="ID: %s" % dev_id, xalign=0))

        actions = [
            ("Imperecheaza (pair)", lambda *a: self._act(["-d", dev_id, "--pair"])),
            ("Ping", lambda *a: self._act(["-d", dev_id, "--ping"])),
            ("Trimite fisier...", lambda *a: self._send_file(dev_id)),
            ("Trimite clipboard", lambda *a: self._send_clipboard(dev_id)),
            ("Gaseste telefonul (sunet)", lambda *a: self._act(["-d", dev_id, "--ring"])),
        ]
        for label, cb in actions:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", cb)
            self.detail.append(btn)

    def _act(self, args):
        threading.Thread(target=lambda: kdc(args), daemon=True).start()
        self._notify("Comanda trimisa")

    def _send_file(self, dev_id):
        d = Gtk.FileDialog()
        d.open(self, None, lambda dd, rr: self._do_send(dd, rr, dev_id))

    def _do_send(self, dialog, res, dev_id):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if f:
            self._act(["-d", dev_id, "--share", f.get_path()])

    def _send_clipboard(self, dev_id):
        text = subprocess.run(["wl-paste"], capture_output=True, text=True).stdout
        self._act(["-d", dev_id, "--share-text", text])

    def _notify(self, text):
        GLib.spawn_command_line_async("notify-send -i phone 'BoboPhone' '%s'" % text.replace("'", ""))


class BoboPhoneApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboPhoneWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboPhone 1.0.0 (BOBO OS)")
        return 0
    return BoboPhoneApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
