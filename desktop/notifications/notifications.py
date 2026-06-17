#!/usr/bin/env python3
"""
BOBO OS — Notification Center (Phase 5.4)
E:\BOBO-OS\desktop\notifications\notifications.py

GTK4 side panel that slides in from the right edge.
- Notifications grouped by app (with dismiss buttons)
- Quick Settings tiles: WiFi, Bluetooth, Brightness, Volume, Night Mode, DnD, Airplane
- Opened by: bell icon in taskbar, Win+N shortcut
- Call with --toggle to show/hide
"""

import os
import sys
import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    LAYER_SHELL = True
except (ImportError, ValueError):
    LAYER_SHELL = False

# ── In-memory notification store (persisted to disk) ─────────────────────────
NOTIF_STORE = Path.home() / ".cache" / "bobo-os" / "notifications.json"
PANEL_W = 380


# ─────────────────────────────────────────────────────────────────────────────
# Notification store
# ─────────────────────────────────────────────────────────────────────────────

class NotificationStore:
    def __init__(self):
        NOTIF_STORE.parent.mkdir(parents=True, exist_ok=True)
        self._notifications: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if NOTIF_STORE.exists():
            try:
                return json.loads(NOTIF_STORE.read_text())
            except json.JSONDecodeError:
                pass
        return []

    def _save(self):
        NOTIF_STORE.write_text(json.dumps(self._notifications, indent=2))

    def add(self, app_name: str, icon: str, title: str, body: str):
        self._notifications.insert(0, {
            "id":       id(title),
            "app":      app_name,
            "icon":     icon,
            "title":    title,
            "body":     body,
            "time":     datetime.now().isoformat(timespec="minutes"),
        })
        self._save()

    def dismiss(self, notif_id: int):
        self._notifications = [n for n in self._notifications if n["id"] != notif_id]
        self._save()

    def clear_all(self):
        self._notifications.clear()
        self._save()

    def get_all(self) -> list[dict]:
        return list(self._notifications)


store = NotificationStore()


# ─────────────────────────────────────────────────────────────────────────────
# Notification Center panel
# ─────────────────────────────────────────────────────────────────────────────

class NotificationCenter(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Notification Center")
        self.set_decorated(False)
        self.set_default_size(PANEL_W, -1)

        self._setup_layer_shell()
        self._build_ui()
        self._apply_css()

    def _setup_layer_shell(self):
        if not LAYER_SHELL:
            return
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, 48)  # above taskbar
        GtkLayerShell.set_exclusive_zone(self, PANEL_W)

    def _build_ui(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_name("notif-root")

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        inner.set_margin_top(16); inner.set_margin_bottom(16)
        inner.set_margin_start(16); inner.set_margin_end(16)

        # ── Notifications header ────────────────────────────────────────
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        lbl = Gtk.Label(label="Notifications")
        lbl.add_css_class("title-3")
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.START)
        hdr.append(lbl)
        clear_btn = Gtk.Button(label="Clear all")
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", self._on_clear_all)
        hdr.append(clear_btn)
        inner.append(hdr)

        # ── Notification list ────────────────────────────────────────────
        self._notif_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._refresh_notifications()
        inner.append(self._notif_box)

        # ── Quick Settings ───────────────────────────────────────────────
        qs_lbl = Gtk.Label(label="Quick Settings")
        qs_lbl.add_css_class("title-4")
        qs_lbl.set_halign(Gtk.Align.START)
        qs_lbl.set_margin_top(8)
        inner.append(qs_lbl)

        tiles_grid = Gtk.FlowBox()
        tiles_grid.set_max_children_per_line(2)
        tiles_grid.set_min_children_per_line(2)
        tiles_grid.set_homogeneous(True)
        tiles_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        tiles_grid.set_row_spacing(8)
        tiles_grid.set_column_spacing(8)

        for tile in self._make_quick_tiles():
            tiles_grid.append(tile)
        inner.append(tiles_grid)

        # ── Sliders ─────────────────────────────────────────────────────
        inner.append(self._make_slider("Brightness", "display-brightness-symbolic",
                                       self._get_brightness, self._set_brightness))
        inner.append(self._make_slider("Volume", "audio-volume-high-symbolic",
                                       self._get_volume, self._set_volume))

        scroll.set_child(inner)
        outer.append(scroll)
        self.set_child(outer)

    # ── Notification cards ─────────────────────────────────────────────────

    def _refresh_notifications(self):
        while child := self._notif_box.get_first_child():
            self._notif_box.remove(child)

        notifications = store.get_all()
        if not notifications:
            empty = Gtk.Label(label="No notifications")
            empty.add_css_class("dim-label")
            self._notif_box.append(empty)
            return

        # Group by app
        grouped: dict[str, list[dict]] = {}
        for n in notifications:
            grouped.setdefault(n["app"], []).append(n)

        for app_name, notifs in grouped.items():
            group_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            group_box.set_name("notif-group")

            app_lbl = Gtk.Label(label=app_name)
            app_lbl.add_css_class("caption")
            app_lbl.set_halign(Gtk.Align.START)
            group_box.append(app_lbl)

            for n in notifs:
                card = self._make_notif_card(n)
                group_box.append(card)

            self._notif_box.append(group_box)

    def _make_notif_card(self, n: dict) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.set_name("notif-card")
        card.set_margin_bottom(4)

        hdr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        icon = Gtk.Image.new_from_icon_name(n.get("icon", "dialog-information"))
        icon.set_pixel_size(20)
        hdr_row.append(icon)

        title_lbl = Gtk.Label(label=n["title"])
        title_lbl.add_css_class("body")
        title_lbl.set_hexpand(True)
        title_lbl.set_halign(Gtk.Align.START)
        title_lbl.set_ellipsize(True)
        hdr_row.append(title_lbl)

        time_lbl = Gtk.Label(label=n.get("time", ""))
        time_lbl.add_css_class("caption")
        time_lbl.add_css_class("dim-label")
        hdr_row.append(time_lbl)

        dismiss_btn = Gtk.Button(label="×")
        dismiss_btn.add_css_class("flat")
        dismiss_btn.set_valign(Gtk.Align.CENTER)
        notif_id = n["id"]
        dismiss_btn.connect("clicked", lambda _, nid=notif_id: self._dismiss(nid))
        hdr_row.append(dismiss_btn)

        card.append(hdr_row)

        if n.get("body"):
            body_lbl = Gtk.Label(label=n["body"])
            body_lbl.add_css_class("caption")
            body_lbl.set_halign(Gtk.Align.START)
            body_lbl.set_wrap(True)
            body_lbl.set_margin_start(28)
            card.append(body_lbl)

        return card

    def _dismiss(self, notif_id: int):
        store.dismiss(notif_id)
        self._refresh_notifications()

    def _on_clear_all(self, _btn):
        store.clear_all()
        self._refresh_notifications()

    # ── Quick Settings tiles ───────────────────────────────────────────────

    def _make_quick_tiles(self) -> list[Gtk.Widget]:
        tiles = [
            self._make_toggle_tile("WiFi",       "network-wireless-symbolic",   self._toggle_wifi),
            self._make_toggle_tile("Bluetooth",   "bluetooth-symbolic",          self._toggle_bt),
            self._make_toggle_tile("Night Mode",  "night-light-symbolic",        self._toggle_nightmode),
            self._make_toggle_tile("Do Not Disturb","notifications-disabled-symbolic", self._toggle_dnd),
            self._make_toggle_tile("Airplane",    "airplane-mode-symbolic",      self._toggle_airplane),
        ]
        return tiles

    def _make_toggle_tile(self, label: str, icon: str, callback) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_name("qs-tile")
        box.set_halign(Gtk.Align.CENTER)
        box.set_size_request(150, 70)

        img = Gtk.Image.new_from_icon_name(icon)
        img.set_pixel_size(28)
        box.append(img)

        lbl = Gtk.Label(label=label)
        lbl.add_css_class("caption")
        box.append(lbl)

        click = Gtk.GestureClick()
        click.connect("pressed", lambda *_: callback())
        box.add_controller(click)

        return box

    def _make_slider(self, label: str, icon: str, getter, setter) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        img = Gtk.Image.new_from_icon_name(icon)
        img.set_pixel_size(20)
        row.append(img)

        lbl = Gtk.Label(label=label)
        lbl.set_size_request(80, -1)
        row.append(lbl)

        slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        slider.set_value(getter())
        slider.set_hexpand(True)
        slider.set_draw_value(False)
        slider.connect("value-changed", lambda s, fn=setter: fn(s.get_value()))
        row.append(slider)

        return row

    # ── System controls ────────────────────────────────────────────────────

    def _get_brightness(self) -> float:
        try:
            result = subprocess.check_output(
                ["brightnessctl", "g"], text=True, timeout=1)
            max_b = subprocess.check_output(
                ["brightnessctl", "m"], text=True, timeout=1)
            return float(result.strip()) / float(max_b.strip()) * 100
        except Exception:
            return 70.0

    def _set_brightness(self, value: float):
        subprocess.Popen(["brightnessctl", "s", f"{int(value)}%"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _get_volume(self) -> float:
        try:
            out = subprocess.check_output(["wpctl","get-volume","@DEFAULT_AUDIO_SINK@"],
                                          text=True, timeout=1)
            return float(out.split()[1]) * 100
        except Exception:
            return 50.0

    def _set_volume(self, value: float):
        subprocess.Popen(["wpctl","set-volume","@DEFAULT_AUDIO_SINK@", f"{value/100:.2f}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _toggle_wifi(self):
        subprocess.Popen(["nmcli","radio","wifi","toggle"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _toggle_bt(self):
        subprocess.Popen(["rfkill","toggle","bluetooth"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _toggle_nightmode(self):
        subprocess.Popen(["wlsunset","-t","3000","-T","4500"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _toggle_dnd(self):
        # Toggle a DND flag file; notifications daemon checks this
        dnd_flag = Path.home() / ".cache" / "bobo-os" / "dnd.flag"
        if dnd_flag.exists():
            dnd_flag.unlink()
        else:
            dnd_flag.touch()

    def _toggle_airplane(self):
        subprocess.Popen(["rfkill","toggle","all"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ── CSS ────────────────────────────────────────────────────────────────

    def _apply_css(self):
        css = """
        #notif-root {
          background-color: rgba(26, 26, 46, 0.97);
          border-left: 1px solid #3a3a5c;
        }
        #notif-card {
          background-color: rgba(37, 37, 64, 0.9);
          border-radius: 8px;
          padding: 10px 12px;
          border: 1px solid #3a3a5c;
        }
        #notif-group {
          padding: 4px 0;
        }
        #qs-tile {
          background-color: rgba(255,255,255,0.07);
          border-radius: 10px;
          padding: 12px 8px;
        }
        #qs-tile:hover {
          background-color: rgba(74,158,255,0.20);
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


class NotifApp(Adw.Application):
    _instance: "NotificationCenter | None" = None

    def __init__(self):
        super().__init__(application_id="os.bobo.Notifications",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        if self._instance is None:
            self.__class__._instance = NotificationCenter(self)
            self._instance.present()
        else:
            if "--toggle" in sys.argv:
                if self._instance.get_visible():
                    self._instance.hide()
                else:
                    self._instance.present()
            else:
                self._instance.present()


if __name__ == "__main__":
    NotifApp().run(sys.argv)
