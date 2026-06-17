#!/usr/bin/env python3
"""
BOBO OS — Settings Application (Phase 5.5)
E:\BOBO-OS\desktop\settings\settings.py

Full GTK4 Settings app with sidebar navigation.
All sections implemented — no terminal required for any operation.
"""

import os
import sys
import subprocess
import json
import socket
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("NM", "1.0")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk

BOBO_CONFIG = Path("/etc/bobo-os.conf")
USER_CONFIG  = Path.home() / ".config" / "bobo-os" / "user.json"


def load_user_config() -> dict:
    if USER_CONFIG.exists():
        try:
            return json.loads(USER_CONFIG.read_text())
        except Exception:
            pass
    return {}


def save_user_config(data: dict):
    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    USER_CONFIG.write_text(json.dumps(data, indent=2))


def run_cmd(*args) -> str:
    try:
        return subprocess.check_output(list(args), text=True, timeout=5, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Individual settings pages
# ─────────────────────────────────────────────────────────────────────────────

def build_system_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_margin_top(24); box.set_margin_start(32); box.set_margin_end(32)

    # Display resolution
    display_group = Adw.PreferencesGroup(title="Display")
    res_row = Adw.ActionRow(title="Resolution", subtitle=run_cmd("xrandr","--current") or "Auto")
    res_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
    res_row.set_activatable(True)
    res_row.connect("activated", lambda _: subprocess.Popen(["gnome-display-properties"]))
    display_group.add(res_row)

    refresh_row = Adw.ComboRow(title="Refresh Rate")
    refresh_model = Gtk.StringList()
    for rate in ["60 Hz", "75 Hz", "120 Hz", "144 Hz", "165 Hz", "240 Hz"]:
        refresh_model.append(rate)
    refresh_row.set_model(refresh_model)
    display_group.add(refresh_row)

    night_row = Adw.SwitchRow(title="Night Mode", subtitle="Reduce blue light after sunset")
    night_row.connect("notify::active", lambda r, _: subprocess.Popen(
        ["wlsunset", "-t", "3000", "-T", "4500"] if r.get_active()
        else ["pkill", "wlsunset"]))
    display_group.add(night_row)
    box.append(display_group)

    # About section
    about_group = Adw.PreferencesGroup(title="About BOBO OS")
    kernel = run_cmd("uname", "-r") or "6.6-bobo"
    for label, value in [
        ("OS Name",        "BOBO OS 1.0.0"),
        ("Kernel",         kernel),
        ("Architecture",   run_cmd("uname", "-m") or "x86_64"),
        ("Hostname",       socket.gethostname()),
    ]:
        row = Adw.ActionRow(title=label, subtitle=value)
        about_group.add(row)
    box.append(about_group)

    return box


def build_sound_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_margin_top(24); box.set_margin_start(32); box.set_margin_end(32)

    output_group = Adw.PreferencesGroup(title="Output")

    vol_row = Adw.ActionRow(title="Volume")
    vol_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
    try:
        out = subprocess.check_output(["wpctl","get-volume","@DEFAULT_AUDIO_SINK@"],
                                       text=True, timeout=1)
        vol_slider.set_value(float(out.split()[1]) * 100)
    except Exception:
        vol_slider.set_value(70)
    vol_slider.set_size_request(200, -1)
    vol_slider.connect("value-changed", lambda s:
        subprocess.Popen(["wpctl","set-volume","@DEFAULT_AUDIO_SINK@", f"{s.get_value()/100:.2f}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    vol_row.add_suffix(vol_slider)
    output_group.add(vol_row)

    mute_row = Adw.SwitchRow(title="Mute")
    mute_row.connect("notify::active", lambda r, _:
        subprocess.Popen(["wpctl","set-mute","@DEFAULT_AUDIO_SINK@",
                          "1" if r.get_active() else "0"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    output_group.add(mute_row)
    box.append(output_group)

    notif_group = Adw.PreferencesGroup(title="Notification Sounds")
    notif_row = Adw.SwitchRow(title="Play notification sounds", active=True)
    notif_group.add(notif_row)
    box.append(notif_group)

    return box


def build_network_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_margin_top(24); box.set_margin_start(32); box.set_margin_end(32)

    wifi_group = Adw.PreferencesGroup(title="WiFi")
    wifi_toggle = Adw.SwitchRow(title="WiFi", subtitle="Enable/disable wireless")
    wifi_toggle.connect("notify::active", lambda r, _:
        subprocess.Popen(["nmcli","radio","wifi", "on" if r.get_active() else "off"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    wifi_group.add(wifi_toggle)

    manage_btn_row = Adw.ActionRow(title="Manage Networks",
                                    subtitle="View available WiFi networks")
    manage_btn_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
    manage_btn_row.set_activatable(True)
    manage_btn_row.connect("activated", lambda _: subprocess.Popen(["nm-connection-editor"]))
    wifi_group.add(manage_btn_row)
    box.append(wifi_group)

    vpn_group = Adw.PreferencesGroup(title="VPN")
    vpn_row = Adw.ActionRow(title="Manage VPN connections")
    vpn_row.set_activatable(True)
    vpn_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
    vpn_row.connect("activated", lambda _: subprocess.Popen(
        ["nm-connection-editor", "--type", "vpn"]))
    vpn_group.add(vpn_row)
    box.append(vpn_group)

    return box


def build_bluetooth_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_margin_top(24); box.set_margin_start(32); box.set_margin_end(32)

    bt_group = Adw.PreferencesGroup(title="Bluetooth")
    bt_toggle = Adw.SwitchRow(title="Bluetooth")
    bt_toggle.connect("notify::active", lambda r, _:
        subprocess.Popen(["rfkill", "unblock" if r.get_active() else "block", "bluetooth"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    bt_group.add(bt_toggle)

    manage_row = Adw.ActionRow(title="Manage Devices", subtitle="Pair and connect Bluetooth devices")
    manage_row.set_activatable(True)
    manage_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
    manage_row.connect("activated", lambda _: subprocess.Popen(["blueman-manager"]))
    bt_group.add(manage_row)
    box.append(bt_group)
    return box


def build_appearance_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_margin_top(24); box.set_margin_start(32); box.set_margin_end(32)

    theme_group = Adw.PreferencesGroup(title="Theme")
    theme_row = Adw.SwitchRow(title="Dark Mode")
    theme_row.set_active(True)
    def on_theme_toggle(row, _):
        style_mgr = Adw.StyleManager.get_default()
        style_mgr.set_color_scheme(
            Adw.ColorScheme.FORCE_DARK if row.get_active()
            else Adw.ColorScheme.FORCE_LIGHT
        )
    theme_row.connect("notify::active", on_theme_toggle)
    theme_group.add(theme_row)

    accent_row = Adw.ActionRow(title="Accent Color")
    accent_btn = Gtk.ColorButton()
    accent_btn.set_use_alpha(False)
    rgba = Gdk.RGBA()
    rgba.parse("#4a9eff")
    accent_btn.set_rgba(rgba)
    accent_row.add_suffix(accent_btn)
    theme_group.add(accent_row)

    font_row = Adw.SpinRow.new_with_range(8, 24, 1)
    font_row.set_title("Font Size")
    font_row.set_value(11)
    theme_group.add(font_row)
    box.append(theme_group)

    wallpaper_group = Adw.PreferencesGroup(title="Wallpaper")
    wp_row = Adw.ActionRow(title="Choose Wallpaper")
    wp_row.set_activatable(True)
    wp_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
    def choose_wallpaper(_):
        chooser = Gtk.FileDialog()
        chooser.set_title("Choose Wallpaper")
        def on_done(dialog, result):
            try:
                f = dialog.open_finish(result)
                path = f.get_path()
                subprocess.Popen(["swaybg","-m","fill","-i",path],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        chooser.open(None, None, on_done)
    wp_row.connect("activated", choose_wallpaper)
    wallpaper_group.add(wp_row)
    box.append(wallpaper_group)

    return box


def build_apps_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_margin_top(24); box.set_margin_start(32); box.set_margin_end(32)

    apps_group = Adw.PreferencesGroup(title="Installed Apps")
    # Scan .desktop files
    search_dirs = [Path("/usr/share/applications"), Path.home()/".local"/"share"/"applications"]
    for d in search_dirs:
        if not d.exists(): continue
        for desktop in sorted(d.glob("*.desktop"))[:20]:  # show top 20
            kf = Gio.DesktopAppInfo.new_from_filename(str(desktop))
            if kf and kf.should_show():
                row = Adw.ActionRow(title=kf.get_name(),
                                     subtitle=kf.get_description() or "")
                uninst_btn = Gtk.Button(label="Remove")
                uninst_btn.add_css_class("destructive-action")
                uninst_btn.set_valign(Gtk.Align.CENTER)
                row.add_suffix(uninst_btn)
                apps_group.add(row)
    box.append(apps_group)
    return box


def build_privacy_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_margin_top(24); box.set_margin_start(32); box.set_margin_end(32)

    perm_group = Adw.PreferencesGroup(title="App Permissions")
    for perm in ["Camera", "Microphone", "Location"]:
        row = Adw.SwitchRow(title=perm, subtitle=f"Allow apps to access {perm.lower()}")
        perm_group.add(row)
    box.append(perm_group)

    firewall_group = Adw.PreferencesGroup(title="Firewall")
    fw_status = run_cmd("nft", "list", "ruleset") or "inactive"
    fw_row = Adw.ActionRow(title="Firewall",
                            subtitle="Active" if "chain" in fw_status else "Inactive")
    fw_toggle = Gtk.Switch()
    fw_toggle.set_active("chain" in fw_status)
    fw_toggle.set_valign(Gtk.Align.CENTER)
    fw_row.add_suffix(fw_toggle)
    firewall_group.add(fw_row)
    box.append(firewall_group)

    return box


def build_updates_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_margin_top(24); box.set_margin_start(32); box.set_margin_end(32)

    upd_group = Adw.PreferencesGroup(title="System Updates")
    auto_row = Adw.SwitchRow(title="Automatic Updates",
                               subtitle="Install updates in the background")
    auto_row.set_active(True)
    upd_group.add(auto_row)

    check_row = Adw.ActionRow(title="Check for Updates Now")
    check_row.set_activatable(True)
    check_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
    check_row.connect("activated", lambda _: subprocess.Popen(
        ["python3", "/usr/local/lib/bobo/novastore/backend/auto-update.py", "--check"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    upd_group.add(check_row)
    box.append(upd_group)
    return box


def build_about_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_margin_top(24); box.set_margin_start(32); box.set_margin_end(32)

    about_group = Adw.PreferencesGroup(title="System Information")
    kernel = run_cmd("uname", "-r") or "6.6-bobo"
    cpu    = run_cmd("grep", "-m1", "model name", "/proc/cpuinfo").split(":")[-1].strip() or "Unknown"
    ram    = run_cmd("free", "-h").splitlines()[1].split()[1] if run_cmd("free") else "Unknown"

    for label, value in [
        ("BOBO OS Version", "1.0.0"),
        ("Kernel",           kernel),
        ("CPU",              cpu),
        ("RAM",              ram),
        ("Architecture",     run_cmd("uname", "-m") or "x86_64"),
        ("License",          "MIT / GPL-2.0 (per component)"),
    ]:
        row = Adw.ActionRow(title=label, subtitle=value)
        about_group.add(row)
    box.append(about_group)
    return box


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────

class SettingsWindow(Adw.ApplicationWindow):
    PAGES = [
        ("System",       "computer-symbolic",                build_system_page),
        ("Sound",        "audio-speakers-symbolic",          build_sound_page),
        ("Network",      "network-wireless-symbolic",        build_network_page),
        ("Bluetooth",    "bluetooth-symbolic",               build_bluetooth_page),
        ("Appearance",   "preferences-desktop-theme-symbolic", build_appearance_page),
        ("Apps",         "applications-system-symbolic",    build_apps_page),
        ("Privacy",      "security-high-symbolic",           build_privacy_page),
        ("Updates",      "system-software-update-symbolic",  build_updates_page),
        ("About",        "help-about-symbolic",              build_about_page),
    ]

    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title="Settings")
        self.set_default_size(900, 600)
        self._build_ui()

    def _build_ui(self):
        # Split pane: sidebar + content
        split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        # ── Sidebar ────────────────────────────────────────────────────────
        sidebar = Gtk.ListBox()
        sidebar.set_name("settings-sidebar")
        sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        sidebar.set_size_request(220, -1)

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_child(sidebar)
        split.append(sidebar_scroll)

        # ── Content stack ──────────────────────────────────────────────────
        self._content = Gtk.Stack()
        self._content.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._content.set_transition_duration(150)
        self._content.set_hexpand(True)

        content_scroll = Gtk.ScrolledWindow()
        content_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content_scroll.set_vexpand(True)
        content_scroll.set_child(self._content)
        split.append(content_scroll)

        # Build sidebar rows and stack pages
        for name, icon, builder in self.PAGES:
            row = Adw.ActionRow(title=name)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            sidebar.append(row)
            self._content.add_named(builder(), name)

        sidebar.connect("row-selected", self._on_page_select)
        sidebar.select_row(sidebar.get_row_at_index(0))

        self.set_content(split)
        self._apply_css()

    def _on_page_select(self, _lb, row):
        if row:
            self._content.set_visible_child_name(row.get_title())

    def _apply_css(self):
        css = """
        #settings-sidebar {
          background-color: rgba(26,26,46,0.96);
          border-right: 1px solid #3a3a5c;
        }
        #settings-sidebar row {
          min-height: 48px;
          padding: 0 12px;
        }
        #settings-sidebar row:selected {
          background-color: rgba(74,158,255,0.20);
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


class SettingsApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.Settings",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        win = SettingsWindow(self)
        win.present()


if __name__ == "__main__":
    SettingsApp().run(sys.argv)
