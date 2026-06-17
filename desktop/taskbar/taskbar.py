#!/usr/bin/env python3
"""
BOBO OS — Taskbar (Phase 5.2)
E:\BOBO-OS\desktop\taskbar\taskbar.py

Full GTK4 taskbar anchored to the bottom of the screen.
- Left:   Start Menu button (BOBO OS logo)
- Center: Running apps (icon + name, click to focus/minimize, right-click menu)
- Right:  System tray (clock, volume, WiFi, battery, notification bell)

This process is standalone — crashes don't affect the desktop compositor.
"""

import os
import sys
import subprocess
import threading
import time
import json
from datetime import datetime
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GLib", "2.0")
from gi.repository import Gtk, Adw, GLib, Gdk, Gio

# ── Wayland-layer-shell (anchors taskbar to bottom edge) ─────────────────────
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    LAYER_SHELL = True
except (ImportError, ValueError):
    LAYER_SHELL = False

TASKBAR_H = 48       # design token: 48px
ACCENT     = "#4a9eff"
BG_DARK    = "#1a1a2e"
SURFACE    = "#252540"
TEXT       = "#ffffff"


# ─────────────────────────────────────────────────────────────────────────────
# Taskbar window
# ─────────────────────────────────────────────────────────────────────────────

class TaskbarWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app)
        self.set_title("BOBO OS Taskbar")
        self.set_decorated(False)
        self.set_resizable(False)

        # Track open app buttons: {wid: AppButton}
        self._app_buttons: dict[int, "AppButton"] = {}

        self._setup_layer_shell()
        self._build_ui()
        self._apply_css()

        # Poll clock and tray every second
        GLib.timeout_add_seconds(1, self._update_clock)
        # Poll running windows every 2 seconds (via wlr-foreign-toplevel or fallback)
        GLib.timeout_add(2000, self._refresh_windows)

    # ── Layer shell (anchors to bottom, excludes area) ────────────────────

    def _setup_layer_shell(self):
        if not LAYER_SHELL:
            return
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.BOTTOM)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_exclusive_zone(self, TASKBAR_H)

    # ── UI layout ─────────────────────────────────────────────────────────

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.set_size_request(-1, TASKBAR_H)
        root.set_name("taskbar-root")

        # ── LEFT: Start button ────────────────────────────────────────────
        self._start_btn = Gtk.Button()
        self._start_btn.set_name("start-button")
        self._start_btn.set_tooltip_text("Start")
        start_icon = Gtk.Image.new_from_icon_name("application-x-executable")
        start_icon.set_pixel_size(28)
        self._start_btn.set_child(start_icon)
        self._start_btn.connect("clicked", self._on_start_clicked)
        root.append(self._start_btn)

        # ── CENTER: App buttons ────────────────────────────────────────────
        self._apps_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._apps_box.set_hexpand(True)
        self._apps_box.set_halign(Gtk.Align.CENTER)
        root.append(self._apps_box)

        # ── RIGHT: System tray ────────────────────────────────────────────
        tray = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tray.set_margin_end(8)

        # Notification bell
        self._notif_btn = Gtk.Button()
        self._notif_btn.set_name("tray-btn")
        notif_icon = Gtk.Image.new_from_icon_name("notification-new")
        notif_icon.set_pixel_size(20)
        self._notif_btn.set_child(notif_icon)
        self._notif_btn.set_tooltip_text("Notifications")
        self._notif_btn.connect("clicked", self._on_notif_clicked)
        tray.append(self._notif_btn)

        # Battery
        self._battery_btn = self._make_tray_icon("battery-full", "Battery")
        self._battery_btn.connect("clicked", self._on_battery_clicked)
        tray.append(self._battery_btn)

        # WiFi
        self._wifi_btn = self._make_tray_icon("network-wireless", "Network")
        self._wifi_btn.connect("clicked", self._on_wifi_clicked)
        tray.append(self._wifi_btn)

        # Volume
        self._volume_btn = self._make_tray_icon("audio-volume-high", "Volume")
        self._volume_btn.connect("clicked", self._on_volume_clicked)
        tray.append(self._volume_btn)

        # Clock
        self._clock_label = Gtk.Label(label=self._current_time())
        self._clock_label.set_name("clock-label")
        clock_btn = Gtk.Button()
        clock_btn.set_name("tray-btn")
        clock_btn.set_child(self._clock_label)
        clock_btn.set_tooltip_text(datetime.now().strftime("%A, %B %d, %Y"))
        clock_btn.connect("clicked", self._on_clock_clicked)
        tray.append(clock_btn)

        root.append(tray)
        self.set_child(root)

    def _make_tray_icon(self, icon_name: str, tooltip: str) -> Gtk.Button:
        btn = Gtk.Button()
        btn.set_name("tray-btn")
        img = Gtk.Image.new_from_icon_name(icon_name)
        img.set_pixel_size(20)
        btn.set_child(img)
        btn.set_tooltip_text(tooltip)
        return btn

    # ── CSS ───────────────────────────────────────────────────────────────

    def _apply_css(self):
        css = f"""
        #taskbar-root {{
          background-color: rgba(26, 26, 46, 0.88);
          border-top: 1px solid {SURFACE};
        }}
        #start-button {{
          min-width:  48px;
          min-height: 48px;
          border-radius: 0;
          background: transparent;
          border: none;
        }}
        #start-button:hover {{
          background-color: rgba(74, 158, 255, 0.25);
        }}
        #start-button:active {{
          background-color: rgba(74, 158, 255, 0.45);
        }}
        #tray-btn {{
          min-width:  36px;
          min-height: 36px;
          border-radius: 6px;
          background: transparent;
          border: none;
          color: {TEXT};
        }}
        #tray-btn:hover {{ background-color: rgba(255,255,255,0.10); }}
        #clock-label {{
          color: {TEXT};
          font-size: 13px;
          font-weight: 500;
          padding: 0 6px;
        }}
        .app-button {{
          min-width:  120px;
          max-width:  160px;
          min-height: 40px;
          border-radius: 6px;
          background: rgba(255,255,255,0.07);
          border: none;
          color: {TEXT};
          font-size: 12px;
        }}
        .app-button:hover {{ background: rgba(255,255,255,0.14); }}
        .app-button.active {{
          background: rgba(74,158,255,0.25);
          border-bottom: 2px solid {ACCENT};
        }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── Clock ─────────────────────────────────────────────────────────────

    def _current_time(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _update_clock(self):
        self._clock_label.set_text(self._current_time())
        return True  # keep timer running

    # ── Window list (running apps) ─────────────────────────────────────────

    def _refresh_windows(self):
        """
        Query running Wayland windows via wlr-foreign-toplevel-management protocol.
        Falls back to listing /proc for X11 windows if Wayland protocol unavailable.
        """
        windows = self._get_wayland_windows()

        current_ids = set(windows.keys())
        existing_ids = set(self._app_buttons.keys())

        # Add buttons for new windows
        for wid, (title, app_id, focused) in windows.items():
            if wid not in self._app_buttons:
                btn = AppButton(wid, title, app_id)
                self._app_buttons[wid] = btn
                self._apps_box.append(btn)
            self._app_buttons[wid].update(title, focused)

        # Remove buttons for closed windows
        for wid in existing_ids - current_ids:
            btn = self._app_buttons.pop(wid)
            self._apps_box.remove(btn)

        return True  # keep timer running

    def _get_wayland_windows(self) -> dict:
        """
        Returns {wid: (title, app_id, focused)} for all open windows.
        Uses wlrctl or hyprctl if available; falls back to an empty dict.
        """
        try:
            result = subprocess.run(
                ["wlrctl", "toplevel", "list"],
                capture_output=True, text=True, timeout=1
            )
            windows = {}
            for i, line in enumerate(result.stdout.splitlines()):
                parts = line.split("|")
                if len(parts) >= 2:
                    title  = parts[0].strip() or "(untitled)"
                    app_id = parts[1].strip() if len(parts) > 1 else "unknown"
                    windows[i] = (title, app_id, False)
            return windows
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {}

    # ── Tray action handlers ───────────────────────────────────────────────

    def _on_start_clicked(self, _btn):
        subprocess.Popen(
            ["python3", "/usr/local/lib/bobo/desktop/taskbar/start-menu/start-menu.py"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def _on_notif_clicked(self, _btn):
        subprocess.Popen(
            ["python3", "/usr/local/lib/bobo/desktop/notifications/notifications.py", "--toggle"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def _on_volume_clicked(self, _btn):
        VolumePopover(self._volume_btn).popup()

    def _on_wifi_clicked(self, _btn):
        subprocess.Popen(["nm-connection-editor"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _on_battery_clicked(self, _btn):
        subprocess.Popen(["gnome-power-statistics"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _on_clock_clicked(self, _btn):
        # Open GNOME calendar or a simple date popup
        subprocess.Popen(["gnome-calendar"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ─────────────────────────────────────────────────────────────────────────────
# App button (center zone)
# ─────────────────────────────────────────────────────────────────────────────

class AppButton(Gtk.Box):
    """Button for one running window — shows icon + truncated title."""

    def __init__(self, wid: int, title: str, app_id: str):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._wid = wid

        self.add_css_class("app-button")

        # App icon (resolved from icon theme by app_id)
        self._icon = Gtk.Image.new_from_icon_name(app_id or "application-x-executable")
        self._icon.set_pixel_size(20)
        self.append(self._icon)

        # Title label (truncated)
        self._label = Gtk.Label(label=self._truncate(title))
        self._label.set_ellipsize(True)
        self.append(self._label)

        # Click = focus / minimize
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.add_controller(click)

        # Right-click context menu
        rclick = Gtk.GestureClick(button=3)
        rclick.connect("pressed", self._on_right_click)
        self.add_controller(rclick)

        # Hover = show thumbnail (stub: would use Wayland screencopy)
        hover = Gtk.EventControllerMotion()
        hover.connect("enter", self._on_hover_enter)
        hover.connect("leave", self._on_hover_leave)
        self.add_controller(hover)

    def update(self, title: str, focused: bool):
        self._label.set_text(self._truncate(title))
        if focused:
            self.add_css_class("active")
        else:
            self.remove_css_class("active")

    @staticmethod
    def _truncate(text: str, max_len: int = 18) -> str:
        return text[:max_len] + "…" if len(text) > max_len else text

    def _on_click(self, _gesture, _n, _x, _y):
        try:
            subprocess.Popen(
                ["wlrctl", "toplevel", "focus", f"id:{self._wid}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    def _on_right_click(self, _gesture, _n, _x, _y):
        menu = Gtk.PopoverMenu.new_from_model(self._build_context_menu())
        menu.set_parent(self)
        menu.popup()

    def _build_context_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append("Maximize", f"app.maximize-{self._wid}")
        menu.append("Move to other monitor", f"app.move-monitor-{self._wid}")
        menu.append("Close", f"app.close-{self._wid}")
        return menu

    def _on_hover_enter(self, _ctrl, _x, _y):
        # In production: show a window thumbnail preview overlay
        pass

    def _on_hover_leave(self, _ctrl):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Volume popover
# ─────────────────────────────────────────────────────────────────────────────

class VolumePopover(Gtk.Popover):
    def __init__(self, parent: Gtk.Widget):
        super().__init__()
        self.set_parent(parent)
        self.set_size_request(220, -1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(16); box.set_margin_end(16)

        lbl = Gtk.Label(label="Volume")
        lbl.add_css_class("title-4")
        box.append(lbl)

        slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        slider.set_value(self._get_volume())
        slider.set_draw_value(True)
        slider.connect("value-changed", self._on_volume_change)
        box.append(slider)

        self.set_child(box)

    def _get_volume(self) -> float:
        try:
            out = subprocess.check_output(
                ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                text=True, timeout=1
            )
            # Output: "Volume: 0.75"
            return float(out.split()[1]) * 100
        except Exception:
            return 50.0

    def _on_volume_change(self, scale):
        vol = scale.get_value() / 100
        subprocess.Popen(
            ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{vol:.2f}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Application class
# ─────────────────────────────────────────────────────────────────────────────

class TaskbarApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.Taskbar")

    def do_activate(self):
        win = TaskbarWindow(self)
        win.present()


def main():
    app = TaskbarApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
