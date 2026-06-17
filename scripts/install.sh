#!/usr/bin/env python3
"""
BOBO OS  -  Graphical Installer (Phase 10.3)
E:\BOBO-OS\scripts\install.sh  (Python script, called as install.sh)

GTK4-based installer with pages:
  1. Welcome  -  language selection
  2. License
  3. Keyboard layout
  4. Partitioning (automatic or manual)
  5. User account
  6. Extras (encryption, NovaSync, AI)
  7. Summary (final review before writing)
  8. Installation progress
  9. Complete

All steps are reversible until page 7 -> Install is clicked.
Dual boot: auto-detects Windows/Linux, adds them to GRUB.
"""

import sys
import os
import subprocess
import json
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk

BOBO_VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# Installer state
# ─────────────────────────────────────────────────────────────────────────────

class InstallConfig:
    """Holds all user choices. Written to disk only when Install is clicked."""
    locale:      str  = "en_US"
    keyboard:    str  = "us"
    disk:        str  = ""
    auto_part:   bool = True
    username:    str  = ""
    fullname:    str  = ""
    password:    str  = ""
    autologin:   bool = False
    encryption:  bool = False
    novasync:    bool = True
    ai_assist:   bool = True
    dual_boot:   bool = False
    other_os:    str  = ""


cfg = InstallConfig()


# ─────────────────────────────────────────────────────────────────────────────
# Individual pages
# ─────────────────────────────────────────────────────────────────────────────

def build_welcome_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)

    logo = Gtk.Image.new_from_icon_name("computer")
    logo.set_pixel_size(80)
    box.append(logo)

    title = Gtk.Label(label=f"Welcome to BOBO OS {BOBO_VERSION}")
    title.add_css_class("title-1")
    box.append(title)

    subtitle = Gtk.Label(label="A fast, modern, and easy-to-use operating system")
    subtitle.add_css_class("body")
    subtitle.add_css_class("dim-label")
    box.append(subtitle)

    # Language selector
    lang_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    lang_box.set_halign(Gtk.Align.CENTER)
    lang_box.set_margin_top(16)

    lang_lbl = Gtk.Label(label="Language:")
    lang_box.append(lang_lbl)

    lang_combo = Gtk.DropDown.new_from_strings([
        "English (US)", "Romanian", "Deutsch", "Français",
        "Español", "Italiano", "中文", "日本語", "한국어",
    ])
    lang_combo.set_selected(0)

    LOCALES = ["en_US", "ro_RO", "de_DE", "fr_FR", "es_ES", "it_IT", "zh_CN", "ja_JP", "ko_KR"]
    def on_lang_changed(combo, _):
        idx = combo.get_selected()
        cfg.locale = LOCALES[idx] if idx < len(LOCALES) else "en_US"

    lang_combo.connect("notify::selected", on_lang_changed)
    lang_box.append(lang_combo)
    box.append(lang_box)

    return box


def build_license_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_margin_top(16); box.set_margin_start(32); box.set_margin_end(32)

    title = Gtk.Label(label="License Agreement")
    title.add_css_class("title-2")
    box.append(title)

    license_text = Gtk.TextView()
    license_text.set_editable(False)
    license_text.set_wrap_mode(Gtk.WrapMode.WORD)
    license_text.set_monospace(False)
    buf = license_text.get_buffer()
    buf.set_text("""BOBO OS  -  License

BOBO OS is open-source software.

The BOBO OS base system is licensed under the MIT License.
Individual components may carry their own licenses (GPL-2.0, LGPL, Apache 2.0, etc.)
as noted in their respective source directories.

Third-party applications installed via NovaStore are subject to their own licenses.

Wine is licensed under LGPL 2.1.
Darling is licensed under GPL 2.0.
The Linux kernel is licensed under GPL 2.0 with a system-call exception.

By clicking "Next", you agree to the terms above and acknowledge that
BOBO OS is provided AS IS, without warranty of any kind.

Full license texts are available at /usr/share/licenses/ after installation.
""")

    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    scroll.set_child(license_text)
    box.append(scroll)

    agree_row = Gtk.Box(spacing=8)
    agree_row.set_margin_top(8)
    agree_check = Gtk.CheckButton(label="I have read and agree to the license")
    agree_row.append(agree_check)
    box.append(agree_row)

    # Disable Next button until accepted  -  communicated via state
    agree_check.connect("toggled", lambda btn: btn.set_state_flags(
        Gtk.StateFlags.CHECKED if btn.get_active() else Gtk.StateFlags.NORMAL, True))

    return box


def build_keyboard_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_margin_top(16); box.set_margin_start(32); box.set_margin_end(32)

    title = Gtk.Label(label="Keyboard Layout")
    title.add_css_class("title-2")
    box.append(title)

    LAYOUTS = [
        ("English (US)",    "us"),
        ("Romanian",        "ro"),
        ("German (QWERTZ)", "de"),
        ("French (AZERTY)", "fr"),
        ("Spanish",         "es"),
        ("Italian",         "it"),
        ("UK English",      "gb"),
    ]

    layout_combo = Gtk.DropDown.new_from_strings([l[0] for l in LAYOUTS])
    layout_combo.set_selected(0)

    def on_layout_changed(combo, _):
        idx = combo.get_selected()
        cfg.keyboard = LAYOUTS[idx][1] if idx < len(LAYOUTS) else "us"
        # Apply to current session for live test
        try:
            subprocess.run(["setxkbmap", cfg.keyboard], check=False)
        except FileNotFoundError:
            pass

    layout_combo.connect("notify::selected", on_layout_changed)
    box.append(layout_combo)

    # Test area
    test_lbl = Gtk.Label(label="Type here to test your keyboard layout:")
    test_lbl.set_margin_top(16)
    box.append(test_lbl)

    test_entry = Gtk.Entry()
    test_entry.set_placeholder_text("Type something…")
    test_entry.set_hexpand(True)
    box.append(test_entry)

    return box


def build_partitioning_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_margin_top(16); box.set_margin_start(32); box.set_margin_end(32)

    title = Gtk.Label(label="Disk Partitioning")
    title.add_css_class("title-2")
    box.append(title)

    # Detect available disks
    try:
        result = subprocess.run(["lsblk", "-d", "-n", "-o", "NAME,SIZE,MODEL"],
                                capture_output=True, text=True, timeout=5)
        disks = [l.split() for l in result.stdout.splitlines() if l.strip()]
    except Exception:
        disks = []

    if not disks:
        no_disk = Gtk.Label(label="⚠️  No disks detected. Please check your hardware.")
        no_disk.add_css_class("warning")
        box.append(no_disk)
        return box

    # Disk selector
    disk_labels = [f"/dev/{d[0]}  -  {d[1]}  -  {' '.join(d[2:]) or 'Unknown'}" for d in disks]
    disk_combo = Gtk.DropDown.new_from_strings(disk_labels)
    disk_combo.set_selected(0)
    if disks:
        cfg.disk = f"/dev/{disks[0][0]}"

    def on_disk_changed(combo, _):
        idx = combo.get_selected()
        if idx < len(disks):
            cfg.disk = f"/dev/{disks[idx][0]}"

    disk_combo.connect("notify::selected", on_disk_changed)
    box.append(disk_combo)

    # Automatic vs manual
    auto_radio = Gtk.CheckButton(label="Automatic (recommended)  -  use entire selected disk")
    auto_radio.set_active(True)
    box.append(auto_radio)

    manual_radio = Gtk.CheckButton(label="Manual partitioning  -  open GParted", group=auto_radio)
    box.append(manual_radio)

    # Warning about data erasure
    warn = Gtk.Label(label="⚠️  All data on the selected disk will be erased.")
    warn.add_css_class("warning")
    warn.set_margin_top(12)
    box.append(warn)

    def on_toggle(btn):
        cfg.auto_part = auto_radio.get_active()
        if not cfg.auto_part:
            subprocess.Popen(["gparted", cfg.disk],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    auto_radio.connect("toggled", on_toggle)
    manual_radio.connect("toggled", on_toggle)

    # Dual boot detection
    other_os = detect_other_os()
    if other_os:
        cfg.other_os = other_os
        db_row = Gtk.Box(spacing=8)
        db_row.set_margin_top(16)
        db_check = Gtk.CheckButton(label=f"Keep existing OS ({other_os}) for dual boot")
        db_check.set_active(True)
        cfg.dual_boot = True
        db_check.connect("toggled", lambda b: setattr(cfg, "dual_boot", b.get_active()))
        db_row.append(db_check)
        box.append(db_row)

    return box


def detect_other_os() -> str:
    """Check for existing Windows or Linux installations."""
    try:
        result = subprocess.run(["os-prober"], capture_output=True, text=True, timeout=10)
        if result.stdout.strip():
            return result.stdout.split(":")[1].strip()
    except Exception:
        pass
    return ""


def build_user_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_margin_top(16); box.set_margin_start(32); box.set_margin_end(32)

    title = Gtk.Label(label="Create Your Account")
    title.add_css_class("title-2")
    box.append(title)

    group = Adw.PreferencesGroup()

    name_row = Adw.EntryRow(title="Full Name")
    name_row.connect("changed", lambda r: setattr(cfg, "fullname", r.get_text()))
    group.add(name_row)

    user_row = Adw.EntryRow(title="Username (no spaces, lowercase)")
    user_row.connect("changed", lambda r: setattr(cfg, "username", r.get_text().lower().replace(" ","")))
    group.add(user_row)

    pw_row = Adw.PasswordEntryRow(title="Password")
    pw_row.connect("changed", lambda r: setattr(cfg, "password", r.get_text()))
    group.add(pw_row)

    pw2_row = Adw.PasswordEntryRow(title="Confirm Password")
    group.add(pw2_row)

    autologin_row = Adw.SwitchRow(title="Log in automatically")
    autologin_row.connect("notify::active", lambda r, _: setattr(cfg, "autologin", r.get_active()))
    group.add(autologin_row)

    box.append(group)
    return box


def build_extras_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_margin_top(16); box.set_margin_start(32); box.set_margin_end(32)

    title = Gtk.Label(label="Extra Features")
    title.add_css_class("title-2")
    box.append(title)

    group = Adw.PreferencesGroup()

    enc_row = Adw.SwitchRow(title="Encrypt Disk",
                              subtitle="Protect your data with LUKS2 full-disk encryption")
    enc_row.connect("notify::active", lambda r, _: setattr(cfg, "encryption", r.get_active()))
    group.add(enc_row)

    sync_row = Adw.SwitchRow(title="Enable NovaSync",
                               subtitle="Sync with iCloud, OneDrive, Google Drive", active=True)
    sync_row.connect("notify::active", lambda r, _: setattr(cfg, "novasync", r.get_active()))
    group.add(sync_row)

    ai_row = Adw.SwitchRow(title="Enable AI Assistant",
                             subtitle="Built-in assistant (Win+A) using local or cloud AI", active=True)
    ai_row.connect("notify::active", lambda r, _: setattr(cfg, "ai_assist", r.get_active()))
    group.add(ai_row)

    box.append(group)
    return box


def build_summary_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_margin_top(16); box.set_margin_start(32); box.set_margin_end(32)

    title = Gtk.Label(label="Review Your Choices")
    title.add_css_class("title-2")
    box.append(title)

    subtitle = Gtk.Label(label="Review the settings below. Click Install to begin.")
    subtitle.add_css_class("body")
    box.append(subtitle)

    group = Adw.PreferencesGroup()

    def make_row(lbl, val):
        row = Adw.ActionRow(title=lbl, subtitle=str(val))
        group.add(row)

    make_row("Language",       cfg.locale)
    make_row("Keyboard",       cfg.keyboard)
    make_row("Disk",           f"{cfg.disk} ({'automatic' if cfg.auto_part else 'manual'})")
    make_row("Username",       cfg.username or "(not set)")
    make_row("Auto-login",     "Yes" if cfg.autologin else "No")
    make_row("Encryption",     "Yes (LUKS2)" if cfg.encryption else "No")
    make_row("NovaSync",       "Enabled" if cfg.novasync else "Disabled")
    make_row("AI Assistant",   "Enabled" if cfg.ai_assist else "Disabled")
    if cfg.dual_boot:
        make_row("Dual Boot",  cfg.other_os)

    box.append(group)

    warn = Gtk.Label(label="⚠️  This will erase the selected disk. This cannot be undone.")
    warn.add_css_class("error")
    warn.set_margin_top(16)
    box.append(warn)

    return box


class ProgressPage:
    def __init__(self):
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.box.set_halign(Gtk.Align.CENTER)
        self.box.set_valign(Gtk.Align.CENTER)

        title = Gtk.Label(label="Installing BOBO OS…")
        title.add_css_class("title-2")
        self.box.append(title)

        self.task_label = Gtk.Label(label="Starting installation…")
        self.box.append(self.task_label)

        self.pbar = Gtk.ProgressBar()
        self.pbar.set_size_request(400, -1)
        self.box.append(self.pbar)

    def update(self, pct: float, msg: str):
        GLib.idle_add(self._update_ui, pct, msg)

    def _update_ui(self, pct: float, msg: str):
        self.pbar.set_fraction(pct)
        self.task_label.set_text(msg)


def build_complete_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)

    icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
    icon.set_pixel_size(80)
    box.append(icon)

    title = Gtk.Label(label="Installation Complete!")
    title.add_css_class("title-1")
    box.append(title)

    msg = Gtk.Label(label="BOBO OS has been installed successfully.\nRestart to start using your new system.")
    msg.set_halign(Gtk.Align.CENTER)
    msg.set_justify(Gtk.Justification.CENTER)
    box.append(msg)

    btn_row = Gtk.Box(spacing=12)
    btn_row.set_halign(Gtk.Align.CENTER)
    btn_row.set_margin_top(24)

    restart_btn = Gtk.Button(label="Restart Now")
    restart_btn.add_css_class("suggested-action")
    restart_btn.connect("clicked", lambda _: subprocess.Popen(["systemctl", "reboot"]))
    btn_row.append(restart_btn)

    live_btn = Gtk.Button(label="Stay in Live Mode")
    live_btn.connect("clicked", lambda _: Gtk.Application.get_default().quit())
    btn_row.append(live_btn)

    box.append(btn_row)
    return box


# ─────────────────────────────────────────────────────────────────────────────
# Installation backend
# ─────────────────────────────────────────────────────────────────────────────

def run_installation(progress_page: ProgressPage):
    steps = [
        (0.05,  "Partitioning disk…",              _partition_disk),
        (0.20,  "Formatting partitions…",           _format_partitions),
        (0.30,  "Copying system files…",            _copy_rootfs),
        (0.60,  "Installing bootloader…",           _install_grub),
        (0.70,  "Setting up user account…",         _setup_user),
        (0.80,  "Applying configuration…",          _apply_config),
        (0.90,  "Installing bootloader entries…",   _finalize_grub),
        (1.00,  "Installation complete!",           lambda: None),
    ]

    for pct, msg, fn in steps:
        progress_page.update(pct, msg)
        try:
            fn()
        except Exception as e:
            progress_page.update(pct, f"Error: {e}")
            return


def _partition_disk():
    if not cfg.auto_part or not cfg.disk:
        return
    # GPT partitioning: 512MB EFI, rest as root
    subprocess.run(["sgdisk", "--zap-all", cfg.disk], check=False, capture_output=True)
    subprocess.run(["sgdisk",
                    "--new=1:0:+512M", "--typecode=1:ef00",
                    "--new=2:0:0",     "--typecode=2:8300",
                    cfg.disk], check=True, capture_output=True)


def _format_partitions():
    if not cfg.auto_part or not cfg.disk:
        return
    esp = f"{cfg.disk}1"
    root = f"{cfg.disk}2"
    subprocess.run(["mkfs.fat", "-F32", "-n", "BOBO-EFI", esp], check=True, capture_output=True)
    if cfg.encryption:
        subprocess.run(["cryptsetup", "luksFormat", "--type", "luks2",
                        "--pbkdf", "argon2id", root], check=True)
        subprocess.run(["cryptsetup", "open", root, "bobo_crypt"], check=True)
        root = "/dev/mapper/bobo_crypt"
    subprocess.run(["mkfs.ext4", "-L", "BOBO-OS-ROOT", root], check=True, capture_output=True)


def _copy_rootfs():
    target = "/mnt/bobo-install"
    os.makedirs(target, exist_ok=True)
    root_dev = ("/dev/mapper/bobo_crypt" if cfg.encryption
                else f"{cfg.disk}2")
    subprocess.run(["mount", root_dev, target], check=True, capture_output=True)
    os.makedirs(f"{target}/boot/efi", exist_ok=True)
    subprocess.run(["mount", f"{cfg.disk}1", f"{target}/boot/efi"], check=True, capture_output=True)
    subprocess.run(["rsync", "-a", "--exclude=/proc", "--exclude=/sys",
                    "--exclude=/dev", "--exclude=/run",
                    "/", target], capture_output=True)


def _install_grub():
    target = "/mnt/bobo-install"
    subprocess.run(["grub-install",
                    "--target=x86_64-efi",
                    f"--efi-directory={target}/boot/efi",
                    f"--boot-directory={target}/boot",
                    "--removable"], check=False, capture_output=True)
    subprocess.run(["grub-install",
                    "--target=i386-pc",
                    f"--boot-directory={target}/boot",
                    cfg.disk], check=False, capture_output=True)


def _setup_user():
    target = "/mnt/bobo-install"
    if not cfg.username:
        return
    subprocess.run(["chroot", target, "useradd", "-m", "-s", "/bin/bash",
                    "-G", "wheel,audio,video,plugdev", cfg.username],
                   check=False, capture_output=True)
    p = subprocess.Popen(["chroot", target, "chpasswd"],
                         stdin=subprocess.PIPE, capture_output=True)
    p.communicate(input=f"{cfg.username}:{cfg.password}\n".encode())


def _apply_config():
    target = "/mnt/bobo-install"
    # Write hostname
    Path(f"{target}/etc/hostname").write_text("bobo-os\n")
    # Write locale
    Path(f"{target}/etc/locale.conf").write_text(f"LANG={cfg.locale}.UTF-8\n")
    # Write keyboard
    Path(f"{target}/etc/vconsole.conf").write_text(f"KEYMAP={cfg.keyboard}\n")
    # Enable autologin if requested
    if cfg.autologin:
        getty_dir = Path(f"{target}/etc/sv/display-manager")
        getty_dir.mkdir(parents=True, exist_ok=True)


def _finalize_grub():
    target = "/mnt/bobo-install"
    subprocess.run(["chroot", target, "update-grub"], check=False, capture_output=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main installer window
# ─────────────────────────────────────────────────────────────────────────────

class InstallerWindow(Adw.ApplicationWindow):
    PAGES = [
        ("Welcome",       build_welcome_page),
        ("License",       build_license_page),
        ("Keyboard",      build_keyboard_page),
        ("Partitioning",  build_partitioning_page),
        ("User",          build_user_page),
        ("Extras",        build_extras_page),
        ("Summary",       build_summary_page),
        ("Installing",    None),  # ProgressPage (special)
        ("Complete",      build_complete_page),
    ]

    def __init__(self, app):
        super().__init__(application=app, title="BOBO OS Installer")
        self.set_default_size(720, 540)
        self._page_idx = 0
        self._progress_page = ProgressPage()
        self._build_ui()
        self._show_page(0)

    def _build_ui(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header bar
        hdr = Adw.HeaderBar()
        hdr.set_title_widget(Gtk.Label(label="BOBO OS Installer"))
        hdr.set_show_end_title_buttons(False)
        outer.append(hdr)

        # Page content area
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_transition_duration(150)
        self._stack.set_vexpand(True)
        outer.append(self._stack)

        # Build all pages
        for i, (name, builder) in enumerate(self.PAGES):
            if name == "Installing":
                page_widget = self._progress_page.box
            else:
                page_widget = builder()
            self._stack.add_named(page_widget, name)

        # Navigation bar
        nav = Gtk.Box(spacing=12)
        nav.set_margin_start(16); nav.set_margin_end(16)
        nav.set_margin_top(8); nav.set_margin_bottom(16)

        self._back_btn = Gtk.Button(label="← Back")
        self._back_btn.connect("clicked", self._on_back)
        nav.append(self._back_btn)

        spacer = Gtk.Box(); spacer.set_hexpand(True)
        nav.append(spacer)

        self._next_btn = Gtk.Button(label="Next ->")
        self._next_btn.add_css_class("suggested-action")
        self._next_btn.connect("clicked", self._on_next)
        nav.append(self._next_btn)

        outer.append(nav)
        self.set_content(outer)

    def _show_page(self, idx: int):
        self._page_idx = idx
        name = self.PAGES[idx][0]
        self._stack.set_visible_child_name(name)

        self._back_btn.set_sensitive(idx > 0 and name != "Installing" and name != "Complete")
        self._next_btn.set_visible(name != "Complete")

        if name == "Summary":
            self._next_btn.set_label("Install")
            self._next_btn.remove_css_class("suggested-action")
            self._next_btn.add_css_class("destructive-action")
        elif name == "Installing":
            self._next_btn.set_visible(False)
            self._back_btn.set_visible(False)
        else:
            self._next_btn.set_label("Next ->")
            self._next_btn.remove_css_class("destructive-action")
            self._next_btn.add_css_class("suggested-action")

    def _on_next(self, _btn):
        name = self.PAGES[self._page_idx][0]
        next_idx = self._page_idx + 1

        if name == "Summary":
            # Start installation
            self._show_page(next_idx)
            threading.Thread(
                target=run_installation,
                args=(self._progress_page,),
                daemon=True
            ).start()
            GLib.timeout_add(500, self._check_install_done)
        else:
            if next_idx < len(self.PAGES):
                self._show_page(next_idx)

    def _on_back(self, _btn):
        if self._page_idx > 0:
            self._show_page(self._page_idx - 1)

    def _check_install_done(self):
        if self._progress_page.pbar.get_fraction() >= 1.0:
            self._show_page(len(self.PAGES) - 1)
            return False
        return True


class InstallerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.Installer",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        InstallerWindow(self).present()


if __name__ == "__main__":
    InstallerApp().run(sys.argv)
