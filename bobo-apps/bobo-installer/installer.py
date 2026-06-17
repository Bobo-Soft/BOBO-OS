#!/usr/bin/env python3
# =============================================================================
# BoboInstaller - Instalator pe disc pentru BOBO OS (APP 09)
# GTK4 wizard: limba, partitionare (auto/manual), criptare LUKS2, utilizator,
# timezone, sumar, instalare (rsync + GRUB), finalizare.
# Ruleaza in mediul live. Operatiile privilegiate cer root/pkexec.
# =============================================================================
import os
import sys
import json
import subprocess
import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Installer"


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


class Config:
    def __init__(self):
        self.lang = "ro_RO"
        self.disk = ""
        self.auto_part = True
        self.encrypt = False
        self.luks_pass = ""
        self.username = "bobo"
        self.fullname = ""
        self.password = ""
        self.hostname = "bobo-os"
        self.autologin = True
        self.timezone = "Europe/Bucharest"


class BoboInstallerWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Instalare BOBO OS")
        self.set_default_size(720, 520)
        self.cfg = Config()
        self.page = 0

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(self.stack)

        # bara de navigare jos
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nav.set_margin_top(8)
        nav.set_margin_bottom(10)
        nav.set_margin_start(12)
        nav.set_margin_end(12)
        self.back_btn = Gtk.Button(label="Inapoi")
        self.back_btn.connect("clicked", lambda *a: self.go(-1))
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.next_btn = Gtk.Button(label="Inainte")
        self.next_btn.add_css_class("suggested-action")
        self.next_btn.connect("clicked", lambda *a: self.go(1))
        nav.append(self.back_btn)
        nav.append(spacer)
        nav.append(self.next_btn)
        outer.append(nav)
        self.set_child(outer)

        self.pages = [
            ("welcome", self._page_welcome),
            ("partition", self._page_partition),
            ("encrypt", self._page_encrypt),
            ("user", self._page_user),
            ("timezone", self._page_timezone),
            ("summary", self._page_summary),
            ("install", self._page_install),
            ("done", self._page_done),
        ]
        for name, builder in self.pages:
            self.stack.add_named(builder(), name)
        self._update_nav()

    # ----------------------------------------------------------- navigare
    def go(self, delta):
        new = self.page + delta
        if new < 0 or new >= len(self.pages):
            return
        # validari minime
        if self.pages[self.page][0] == "partition" and not self.cfg.disk:
            return
        self.page = new
        name = self.pages[self.page][0]
        self.stack.set_visible_child_name(name)
        if name == "summary":
            self._refresh_summary()
        if name == "install":
            self._start_install()
        self._update_nav()

    def _update_nav(self):
        name = self.pages[self.page][0]
        self.back_btn.set_sensitive(self.page > 0 and name not in ("install", "done"))
        if name == "summary":
            self.next_btn.set_label("Instaleaza")
            self.next_btn.remove_css_class("suggested-action")
            self.next_btn.add_css_class("destructive-action")
        elif name in ("install", "done"):
            self.next_btn.set_visible(False)
            self.back_btn.set_visible(False)
        else:
            self.next_btn.set_label("Inainte")
            self.next_btn.add_css_class("suggested-action")

    def _frame(self, title, subtitle=""):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(28)
        box.set_margin_end(28)
        h = Gtk.Label(xalign=0)
        h.set_markup("<span size='xx-large' weight='bold'>%s</span>" % title)
        box.append(h)
        if subtitle:
            s = Gtk.Label(label=subtitle, xalign=0, wrap=True)
            box.append(s)
        return box

    # ----------------------------------------------------------- pagini
    def _page_welcome(self):
        box = self._frame("Bun venit la BOBO OS", "Acest asistent va instala BOBO OS pe acest calculator.")
        box.append(Gtk.Label(label="Selecteaza limba instalarii:", xalign=0))
        langs = ["ro_RO", "en_US", "de_DE", "fr_FR", "es_ES", "it_IT"]
        dd = Gtk.DropDown.new_from_strings(langs)
        dd.connect("notify::selected", lambda d, _: setattr(self.cfg, "lang", langs[d.get_selected()]))
        box.append(dd)
        return box

    def _page_partition(self):
        box = self._frame("Partitionare", "Alege discul si modul de partitionare.")
        disks = self._list_disks()
        self.disk_dd = Gtk.DropDown.new_from_strings([d[0] + "  (" + d[1] + ")" for d in disks] or ["(niciun disc)"])
        self._disk_paths = [d[0] for d in disks]
        if self._disk_paths:
            self.cfg.disk = self._disk_paths[0]
        self.disk_dd.connect("notify::selected", self._on_disk_changed)
        box.append(Gtk.Label(label="Disc tinta:", xalign=0))
        box.append(self.disk_dd)

        self.auto_radio = Gtk.CheckButton(label="Automat (sterge tot discul si creeaza EFI + root + swap)")
        self.auto_radio.set_active(True)
        manual_radio = Gtk.CheckButton(label="Manual (deschide GParted)")
        manual_radio.set_group(self.auto_radio)
        self.auto_radio.connect("toggled", lambda b: setattr(self.cfg, "auto_part", b.get_active()))
        gparted_btn = Gtk.Button(label="Deschide GParted")
        gparted_btn.connect("clicked", lambda *a: subprocess.Popen(["gparted"]))
        box.append(self.auto_radio)
        box.append(manual_radio)
        box.append(gparted_btn)
        # detectie dual-boot
        other = sh(["os-prober"]).stdout.strip()
        if other:
            box.append(Gtk.Label(label="Sistem detectat (dual-boot posibil):\n" + other, xalign=0))
        return box

    def _page_encrypt(self):
        box = self._frame("Criptare disc", "Optional: cripteaza intregul disc cu LUKS2 (Argon2id).")
        sw = Gtk.Switch()
        sw.set_halign(Gtk.Align.START)
        self.luks_entry = Gtk.PasswordEntry()
        self.luks_entry.set_show_peek_icon(True)
        self.luks_entry.set_sensitive(False)
        sw.connect("state-set", lambda s, v: (self.luks_entry.set_sensitive(v), setattr(self.cfg, "encrypt", v), False)[2])
        box.append(self._labeled("Activeaza criptarea LUKS2", sw))
        box.append(Gtk.Label(label="Parola de criptare:", xalign=0))
        box.append(self.luks_entry)
        return box

    def _page_user(self):
        box = self._frame("Cont utilizator")
        self.full_e = Gtk.Entry(placeholder_text="Nume complet")
        self.user_e = Gtk.Entry(placeholder_text="Nume utilizator")
        self.user_e.set_text("bobo")
        self.pass_e = Gtk.PasswordEntry()
        self.pass_e.set_show_peek_icon(True)
        self.host_e = Gtk.Entry(placeholder_text="Hostname")
        self.host_e.set_text("bobo-os")
        self.autologin_sw = Gtk.Switch()
        self.autologin_sw.set_active(True)
        self.autologin_sw.set_halign(Gtk.Align.START)
        for lbl, w in [("Nume complet", self.full_e), ("Utilizator", self.user_e),
                       ("Parola", self.pass_e), ("Hostname", self.host_e),
                       ("Autentificare automata", self.autologin_sw)]:
            box.append(self._labeled(lbl, w))
        return box

    def _page_timezone(self):
        box = self._frame("Fus orar")
        zones = sh(["timedatectl", "list-timezones"]).stdout.split() or ["Europe/Bucharest", "UTC"]
        self.tz_dd = Gtk.DropDown.new_from_strings(zones)
        try:
            self.tz_dd.set_selected(zones.index("Europe/Bucharest"))
        except ValueError:
            pass
        self._zones = zones
        self.tz_dd.connect("notify::selected", lambda d, _: setattr(self.cfg, "timezone", self._zones[d.get_selected()]))
        box.append(self.tz_dd)
        return box

    def _page_summary(self):
        box = self._frame("Sumar instalare", "Verifica setarile inainte de instalare.")
        self.summary_label = Gtk.Label(xalign=0)
        self.summary_label.set_selectable(True)
        box.append(self.summary_label)
        box.append(Gtk.Label(label="ATENTIE: discul selectat va fi formatat!", xalign=0))
        return box

    def _page_install(self):
        box = self._frame("Instalare in curs...")
        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.task_label = Gtk.Label(label="", xalign=0)
        box.append(self.progress)
        box.append(self.task_label)
        return box

    def _page_done(self):
        box = self._frame("Instalare finalizata!", "BOBO OS a fost instalat cu succes.")
        reboot = Gtk.Button(label="Reporneste acum")
        reboot.add_css_class("suggested-action")
        reboot.connect("clicked", lambda *a: subprocess.Popen(["systemctl", "reboot"]))
        stay = Gtk.Button(label="Ramai in modul Live")
        stay.connect("clicked", lambda *a: self.close())
        box.append(reboot)
        box.append(stay)
        return box

    # ----------------------------------------------------------- helpers
    def _labeled(self, label, widget):
        b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        lbl = Gtk.Label(label=label, xalign=0)
        lbl.set_size_request(160, -1)
        b.append(lbl)
        b.append(widget)
        return b

    def _list_disks(self):
        out = sh(["lsblk", "-d", "-n", "-o", "NAME,SIZE,MODEL", "-e", "7,11"]).stdout
        disks = []
        for line in out.splitlines():
            parts = line.split(None, 2)
            if parts:
                disks.append(("/dev/" + parts[0], " ".join(parts[1:])))
        return disks

    def _on_disk_changed(self, dd, _):
        idx = dd.get_selected()
        if 0 <= idx < len(self._disk_paths):
            self.cfg.disk = self._disk_paths[idx]

    def _refresh_summary(self):
        # preia valorile din formular
        self.cfg.fullname = self.full_e.get_text()
        self.cfg.username = self.user_e.get_text()
        self.cfg.password = self.pass_e.get_text()
        self.cfg.hostname = self.host_e.get_text()
        self.cfg.autologin = self.autologin_sw.get_active()
        self.cfg.luks_pass = self.luks_entry.get_text()
        self.summary_label.set_markup(
            "<tt>Disc:        %s\nPartitionare:%s\nCriptare:    %s\nUtilizator:  %s\nHostname:    %s\nAutologin:   %s\nFus orar:    %s\nLimba:       %s</tt>" % (
                self.cfg.disk, "automat" if self.cfg.auto_part else "manual",
                "DA (LUKS2)" if self.cfg.encrypt else "nu", self.cfg.username,
                self.cfg.hostname, "da" if self.cfg.autologin else "nu",
                self.cfg.timezone, self.cfg.lang))

    # ----------------------------------------------------------- instalare
    def _start_install(self):
        threading.Thread(target=self._do_install, daemon=True).start()

    def _set_progress(self, frac, text):
        self.progress.set_fraction(frac)
        self.task_label.set_text(text)
        if frac >= 1.0:
            self.page = len(self.pages) - 1
            self.stack.set_visible_child_name("done")
            self._update_nav()
        return False

    def _do_install(self):
        c = self.cfg
        steps = [
            (0.10, "Partitionare disc...", self._partition),
            (0.25, "Formatare partitii...", self._format),
            (0.55, "Copiere fisiere sistem...", self._copy_rootfs),
            (0.75, "Instalare bootloader...", self._install_grub),
            (0.88, "Configurare utilizator...", self._setup_user),
            (0.97, "Aplicare configuratie...", self._apply_config),
            (1.00, "Finalizat!", lambda: True),
        ]
        for frac, text, fn in steps:
            GLib.idle_add(self._set_progress, frac if frac < 1 else 0.99, text)
            try:
                fn()
            except Exception as e:
                GLib.idle_add(self.task_label.set_text, "Eroare: %s" % e)
                return
        GLib.idle_add(self._set_progress, 1.0, "Finalizat!")

    def _partition(self):
        c = self.cfg
        if not c.auto_part:
            return
        sh(["sgdisk", "--zap-all", c.disk])
        sh(["sgdisk", "--new=1:0:+512M", "--typecode=1:ef00",
            "--new=2:0:0", "--typecode=2:8300", c.disk])

    def _part(self, n):
        # nvme0n1p1 vs sda1
        return self.cfg.disk + ("p%d" % n if "nvme" in self.cfg.disk or "mmcblk" in self.cfg.disk else str(n))

    def _format(self):
        c = self.cfg
        esp, root = self._part(1), self._part(2)
        sh(["mkfs.fat", "-F32", "-n", "BOBO-EFI", esp])
        if c.encrypt and c.luks_pass:
            p = subprocess.Popen(["cryptsetup", "luksFormat", "--type", "luks2", "--pbkdf", "argon2id", root],
                                 stdin=subprocess.PIPE)
            p.communicate(("%s\n" % c.luks_pass).encode())
            p2 = subprocess.Popen(["cryptsetup", "open", root, "bobo_crypt"], stdin=subprocess.PIPE)
            p2.communicate(("%s\n" % c.luks_pass).encode())
            root = "/dev/mapper/bobo_crypt"
        sh(["mkfs.ext4", "-F", "-L", "BOBO-OS-ROOT", root])
        self._root_dev = root

    def _copy_rootfs(self):
        target = "/mnt/bobo-target"
        os.makedirs(target, exist_ok=True)
        sh(["mount", self._root_dev, target])
        sh(["rsync", "-aHAX", "--exclude=/proc", "--exclude=/sys", "--exclude=/dev",
            "--exclude=/run", "--exclude=/mnt", "--exclude=/tmp", "/", target + "/"])
        self._target = target

    def _install_grub(self):
        t = self._target
        for fs in ["proc", "sys", "dev"]:
            sh(["mount", "--bind", "/" + fs, t + "/" + fs])
        os.makedirs(t + "/boot/efi", exist_ok=True)
        sh(["mount", self._part(1), t + "/boot/efi"])
        sh(["chroot", t, "grub-install", "--target=x86_64-efi", "--efi-directory=/boot/efi", "--removable"])
        sh(["chroot", t, "grub-install", "--target=i386-pc", self.cfg.disk])
        sh(["chroot", t, "grub-mkconfig", "-o", "/boot/grub/grub.cfg"])

    def _setup_user(self):
        c = self.cfg
        t = self._target
        sh(["chroot", t, "useradd", "-m", "-s", "/bin/bash", "-G", "sudo,audio,video,plugdev,input,render", c.username])
        p = subprocess.Popen(["chroot", t, "chpasswd"], stdin=subprocess.PIPE)
        p.communicate(("%s:%s\n" % (c.username, c.password)).encode())

    def _apply_config(self):
        c = self.cfg
        t = self._target
        with open(t + "/etc/hostname", "w") as fh:
            fh.write(c.hostname + "\n")
        with open(t + "/etc/locale.conf", "w") as fh:
            fh.write("LANG=%s.UTF-8\n" % c.lang)
        sh(["chroot", t, "ln", "-sf", "/usr/share/zoneinfo/" + c.timezone, "/etc/localtime"])
        if c.autologin:
            d = t + "/etc/systemd/system/getty@tty1.service.d"
            os.makedirs(d, exist_ok=True)
            with open(d + "/autologin.conf", "w") as fh:
                fh.write("[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin %s --noclear %%I $TERM\n" % c.username)


class BoboInstallerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboInstallerWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboInstaller 1.0.0 (BOBO OS)")
        return 0
    return BoboInstallerApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
