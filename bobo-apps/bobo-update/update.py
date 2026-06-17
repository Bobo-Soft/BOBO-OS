#!/usr/bin/env python3
# =============================================================================
# BoboUpdate - Manager de actualizari pentru BOBO OS (APP 10)
# GTK4 + apt. Verifica/aplica actualizari, snapshot rsync inainte, rollback.
# Mod daemon (--daemon): verifica la 6h si notifica.
# =============================================================================
import os
import sys
import time
import subprocess
import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Update"
SNAP_DIR = "/var/lib/bobo-snapshots"
CHECK_INTERVAL = 6 * 3600  # 6 ore


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def list_upgradable():
    """Intoarce lista (pachet, versiune_noua) de actualizari disponibile."""
    sh(["pkexec", "apt-get", "update"]) if os.geteuid() != 0 else sh(["apt-get", "update"])
    out = sh(["apt", "list", "--upgradable"]).stdout
    pkgs = []
    for line in out.splitlines():
        if "/" in line and "[upgradable" in line:
            name = line.split("/")[0]
            ver = line.split()[1] if len(line.split()) > 1 else "?"
            pkgs.append((name, ver))
    return pkgs


class BoboUpdateWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboUpdate")
        self.set_default_size(640, 540)
        self.updates = []

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.set_tooltip_text("Verifica actualizari")
        refresh.connect("clicked", lambda *a: self.check())
        header.pack_start(refresh)
        self.install_btn = Gtk.Button(label="Instaleaza tot")
        self.install_btn.add_css_class("suggested-action")
        self.install_btn.set_sensitive(False)
        self.install_btn.connect("clicked", lambda *a: self.install())
        header.pack_end(self.install_btn)
        rollback = Gtk.Button(label="Rollback")
        rollback.connect("clicked", lambda *a: self.rollback())
        header.pack_end(rollback)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_child(box)
        self.status = Gtk.Label(label="Apasa Verifica pentru a cauta actualizari.", xalign=0)
        self.status.set_margin_start(10)
        self.status.set_margin_top(8)
        box.append(self.status)
        self.progress = Gtk.ProgressBar()
        self.progress.set_visible(False)
        box.append(self.progress)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        self.listbox = Gtk.ListBox()
        scroller.set_child(self.listbox)
        box.append(scroller)

        # setari
        settings = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        settings.set_margin_start(10)
        settings.set_margin_bottom(8)
        self.auto_sw = Gtk.Switch()
        settings.append(Gtk.Label(label="Actualizare automata noaptea"))
        settings.append(self.auto_sw)
        self.channel = Gtk.DropDown.new_from_strings(["stable", "beta"])
        settings.append(Gtk.Label(label="Canal:"))
        settings.append(self.channel)
        box.append(settings)

    def check(self):
        self.status.set_text("Verific actualizari...")
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        pkgs = list_upgradable()
        GLib.idle_add(self._show_updates, pkgs)

    def _show_updates(self, pkgs):
        self.updates = pkgs
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        for name, ver in pkgs:
            row = Gtk.ListBoxRow()
            b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            b.set_margin_top(6)
            b.set_margin_bottom(6)
            b.set_margin_start(10)
            lbl = Gtk.Label(label=name, xalign=0)
            lbl.set_hexpand(True)
            verl = Gtk.Label(label=ver)
            verl.add_css_class("dim-label")
            b.append(lbl)
            b.append(verl)
            row.set_child(b)
            self.listbox.append(row)
        n = len(pkgs)
        self.status.set_text("%d actualizari disponibile." % n if n else "Sistemul este la zi.")
        self.install_btn.set_sensitive(n > 0)

    def install(self):
        self.progress.set_visible(True)
        self.progress.pulse()
        self.status.set_text("Creez snapshot si instalez...")
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        # 1. snapshot rsync inainte de update
        stamp = time.strftime("pre-update-%Y%m%d-%H%M%S")
        snap = os.path.join(SNAP_DIR, stamp)
        sh(["pkexec", "mkdir", "-p", snap])
        sh(["pkexec", "rsync", "-aHAX", "--exclude=/proc", "--exclude=/sys",
            "--exclude=/dev", "--exclude=/run", "--exclude=" + SNAP_DIR, "/etc", snap + "/"])
        # 2. aplica update
        r = sh(["pkexec", "apt-get", "-y", "dist-upgrade"])
        ok = r.returncode == 0
        GLib.idle_add(self._install_done, ok, r.stderr[-300:] if not ok else "")

    def _install_done(self, ok, err):
        self.progress.set_visible(False)
        if ok:
            self.status.set_text("Actualizari instalate cu succes.")
            self._notify("Actualizari instalate cu succes")
            self.check()
        else:
            self.status.set_text("Eroare la actualizare. Poti folosi Rollback.\n" + err)
            self._notify("Actualizare esuata - vezi BoboUpdate")

    def rollback(self):
        try:
            snaps = sorted(os.listdir(SNAP_DIR), reverse=True)
        except Exception:
            snaps = []
        if not snaps:
            self.status.set_text("Niciun snapshot disponibil.")
            return
        latest = os.path.join(SNAP_DIR, snaps[0])
        sh(["pkexec", "rsync", "-aHAX", latest + "/etc/", "/etc/"])
        self.status.set_text("Revenit la snapshot: %s" % snaps[0])
        self._notify("Sistem revenit la snapshot anterior")

    def _notify(self, text):
        GLib.spawn_command_line_async("notify-send -i system-software-update 'BoboUpdate' '%s'" % text.replace("'", ""))


def run_daemon():
    """Verifica periodic si notifica daca exista actualizari."""
    while True:
        try:
            pkgs = list_upgradable()
            if pkgs:
                subprocess.run(["notify-send", "-i", "system-software-update",
                                "BoboUpdate", "%d actualizari disponibile" % len(pkgs)])
        except Exception:
            pass
        time.sleep(CHECK_INTERVAL)


class BoboUpdateApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboUpdateWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboUpdate 1.0.0 (BOBO OS)")
        return 0
    if "--daemon" in sys.argv:
        run_daemon()
        return 0
    return BoboUpdateApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
