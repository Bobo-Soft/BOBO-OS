#!/usr/bin/env python3
# =============================================================================
# BOBO OS — Waydroid GTK4 Launcher (Phase 4.6)
# E:\BOBO-OS\core\novalayer\waydroid\waydroid-launcher.py
#
# Provides a GTK4 interface for:
#  - Starting/stopping the Waydroid session
#  - Installing APK files (drag-and-drop or file picker)
#  - Showing installed Android apps as a grid
#  - Launching individual Android apps
#
# Called by NovaLayer when a .apk or .xapk file is opened.
# Usage:
#   waydroid-launcher.py               → open the app grid
#   waydroid-launcher.py --install <apk>
#   waydroid-launcher.py --launch  <package>
#   waydroid-launcher.py --test
# =============================================================================

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk

import os
import sys
import json
import subprocess
import threading
from pathlib import Path
from typing import Optional, List

# ---------------------------------------------------------------------------
# Waydroid helpers
# ---------------------------------------------------------------------------

def _waydroid_running() -> bool:
    try:
        result = subprocess.run(
            ["waydroid", "status"],
            capture_output=True, text=True, timeout=3
        )
        return "RUNNING" in result.stdout or "running" in result.stdout.lower()
    except Exception:
        return False


def _waydroid_start() -> bool:
    try:
        subprocess.run(["waydroid", "session", "start"],
                       timeout=30, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _waydroid_stop():
    subprocess.run(["waydroid", "session", "stop"],
                   timeout=10, capture_output=True)


def _list_android_apps() -> List[dict]:
    """Return list of installed Android app dicts: {name, package, icon}"""
    try:
        result = subprocess.run(
            ["waydroid", "app", "list"],
            capture_output=True, text=True, timeout=10
        )
        apps = []
        for line in result.stdout.strip().splitlines():
            if not line.strip() or line.startswith("Installed"):
                continue
            parts = line.split(":", 1)
            if len(parts) == 2:
                package = parts[0].strip()
                name    = parts[1].strip() or package.split(".")[-1].capitalize()
                apps.append({"package": package, "name": name})
        return apps
    except Exception:
        return []


def _install_apk(apk_path: str) -> subprocess.Popen:
    return subprocess.Popen(
        ["waydroid", "app", "install", apk_path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True
    )


def _launch_app(package: str):
    subprocess.Popen(
        ["waydroid", "app", "launch", package],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


# ---------------------------------------------------------------------------
# Install progress dialog
# ---------------------------------------------------------------------------

class ApkInstallDialog(Adw.Dialog):
    def __init__(self, parent, apk_path: str):
        super().__init__()
        self.set_title("Installing APK…")
        self.set_content_width(420)
        self.set_can_close(False)
        self._apk_path = apk_path

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        self._icon = Gtk.Image.new_from_icon_name("android-linux-symbolic")
        self._icon.set_pixel_size(48)
        box.append(self._icon)

        self._title_lbl = Gtk.Label(label=f"Installing {Path(apk_path).name}")
        self._title_lbl.add_css_class("heading")
        self._title_lbl.set_wrap(True)
        self._title_lbl.set_justify(Gtk.Justification.CENTER)
        box.append(self._title_lbl)

        self._progress = Gtk.ProgressBar()
        self._progress.set_pulse_step(0.05)
        box.append(self._progress)

        self._log = Gtk.Label(label="")
        self._log.add_css_class("caption")
        self._log.add_css_class("dim-label")
        self._log.set_wrap(True)
        self._log.set_max_width_chars(48)
        box.append(self._log)

        self.set_child(box)
        self._pulse_id = GLib.timeout_add(80, self._pulse)
        threading.Thread(target=self._run_install, daemon=True).start()

    def _pulse(self):
        self._progress.pulse()
        return True

    def _run_install(self):
        # First ensure waydroid is running
        if not _waydroid_running():
            GLib.idle_add(self._log.set_text, "Starting Waydroid session…")
            if not _waydroid_start():
                GLib.idle_add(self._on_error, "Could not start Waydroid. Check that it is installed.")
                return

        proc = _install_apk(self._apk_path)
        output_lines = []
        for line in proc.stdout:
            output_lines.append(line.strip())
            GLib.idle_add(self._log.set_text, line.strip()[:60])

        proc.wait()
        if proc.returncode == 0:
            GLib.idle_add(self._on_success)
        else:
            GLib.idle_add(self._on_error,
                          "\n".join(output_lines[-3:]) or "Installation failed.")

    def _on_success(self):
        GLib.source_remove(self._pulse_id)
        self._progress.set_fraction(1.0)
        self._title_lbl.set_text("Installed successfully!")
        self._icon.set_from_icon_name("emblem-ok-symbolic")
        self.set_can_close(True)

        btn = Gtk.Button(label="Done")
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda b: self.close())
        self.get_child().append(btn)

    def _on_error(self, msg: str):
        GLib.source_remove(self._pulse_id)
        self._progress.set_fraction(0.0)
        self._title_lbl.set_text("Installation failed")
        self._log.set_text(msg)
        self._icon.set_from_icon_name("dialog-error-symbolic")
        self.set_can_close(True)

        btn = Gtk.Button(label="Close")
        btn.add_css_class("destructive-action")
        btn.connect("clicked", lambda b: self.close())
        self.get_child().append(btn)


# ---------------------------------------------------------------------------
# Android app card
# ---------------------------------------------------------------------------

class AndroidAppCard(Gtk.Box):
    def __init__(self, app_data: dict, on_launch):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_size_request(140, 160)
        self.add_css_class("card")
        self.set_margin_start(4)
        self.set_margin_end(4)
        self.set_margin_top(4)
        self.set_margin_bottom(4)

        icon = Gtk.Image.new_from_icon_name("android-linux-symbolic")
        icon.set_pixel_size(56)
        icon.set_margin_top(16)
        self.append(icon)

        name_lbl = Gtk.Label(label=app_data.get("name", "App"))
        name_lbl.set_max_width_chars(16)
        name_lbl.set_ellipsize(3)
        name_lbl.add_css_class("heading")
        name_lbl.set_margin_bottom(12)
        self.append(name_lbl)

        pkg_lbl = Gtk.Label(label=app_data.get("package", "")[:28])
        pkg_lbl.set_ellipsize(3)
        pkg_lbl.add_css_class("caption")
        pkg_lbl.add_css_class("dim-label")
        pkg_lbl.set_margin_bottom(12)
        self.append(pkg_lbl)

        gesture = Gtk.GestureClick()
        gesture.connect("released", lambda g, n, x, y: on_launch(app_data))
        self.add_controller(gesture)

        # Right-click menu
        ctx_gesture = Gtk.GestureClick(button=3)
        ctx_gesture.connect("pressed", lambda g, n, x, y: self._show_context(x, y, on_launch, app_data))
        self.add_controller(ctx_gesture)

    def _show_context(self, x, y, on_launch, app_data):
        menu = Gio.Menu()
        menu.append("Launch", f"app.launch::{app_data['package']}")
        menu.append("Uninstall", f"app.uninstall::{app_data['package']}")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(self)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        popover.popup()


# ---------------------------------------------------------------------------
# Main Waydroid launcher window
# ---------------------------------------------------------------------------

class WaydroidLauncherWindow(Adw.ApplicationWindow):
    def __init__(self, initial_apk: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Android Apps — BOBO OS")
        self.set_default_size(800, 600)

        self._initial_apk = initial_apk
        self._apps: List[dict] = []

        self._build_ui()

        if initial_apk:
            GLib.idle_add(self._install_apk_now, initial_apk)
        else:
            GLib.idle_add(self._check_waydroid_and_load)

    def _build_ui(self):
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title="Android Apps",
            subtitle="Powered by Waydroid"
        ))

        # Install APK button
        install_btn = Gtk.Button.new_with_label("Install APK…")
        install_btn.set_icon_name("list-add-symbolic")
        install_btn.connect("clicked", self._on_install_apk_clicked)
        header.pack_end(install_btn)

        # Waydroid power toggle
        self._power_btn = Gtk.ToggleButton()
        self._power_btn.set_icon_name("media-playback-start-symbolic")
        self._power_btn.set_tooltip_text("Start/Stop Waydroid")
        self._power_btn.connect("toggled", self._on_power_toggled)
        header.pack_start(self._power_btn)

        toolbar_view.add_top_bar(header)

        # Status banner
        self._banner = Adw.Banner()
        self._banner.set_revealed(False)
        toolbar_view.add_top_bar(self._banner)

        # Stack
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(150)
        toolbar_view.set_content(self._stack)

        # Loading page
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        spinner = Gtk.Spinner()
        spinner.set_spinning(True)
        spinner.set_size_request(48, 48)
        loading_box.append(spinner)
        loading_box.append(Gtk.Label(label="Starting Waydroid…"))
        self._stack.add_named(loading_box, "loading")

        # App grid page
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._flow = Gtk.FlowBox()
        self._flow.set_valign(Gtk.Align.START)
        self._flow.set_max_children_per_line(5)
        self._flow.set_min_children_per_line(2)
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_homogeneous(True)
        self._flow.set_margin_top(12)
        self._flow.set_margin_bottom(12)
        self._flow.set_margin_start(12)
        self._flow.set_margin_end(12)
        scroll.set_child(self._flow)
        self._stack.add_named(scroll, "grid")

        # Empty/offline page
        self._status_page = Adw.StatusPage()
        self._status_page.set_icon_name("android-linux-symbolic")
        self._status_page.set_title("Android Support")
        self._status_page.set_description(
            "Waydroid lets you run Android apps on BOBO OS.\n"
            "Click the play button to start."
        )
        start_btn = Gtk.Button(label="Start Android")
        start_btn.add_css_class("suggested-action")
        start_btn.add_css_class("pill")
        start_btn.set_halign(Gtk.Align.CENTER)
        start_btn.connect("clicked", lambda b: self._start_waydroid())
        self._status_page.set_child(start_btn)
        self._stack.add_named(self._status_page, "offline")

        self._stack.set_visible_child_name("offline")

        # Drag-and-drop for APK files
        drop_target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_drop)
        self.add_controller(drop_target)

    # -----------------------------------------------------------------------
    # Waydroid state management
    # -----------------------------------------------------------------------

    def _check_waydroid_and_load(self):
        self._stack.set_visible_child_name("loading")
        threading.Thread(target=self._bg_check_and_load, daemon=True).start()

    def _bg_check_and_load(self):
        running = _waydroid_running()
        GLib.idle_add(self._power_btn.set_active, running)
        if running:
            GLib.idle_add(self._load_apps)
        else:
            GLib.idle_add(self._stack.set_visible_child_name, "offline")

    def _start_waydroid(self):
        self._stack.set_visible_child_name("loading")
        threading.Thread(target=self._bg_start_waydroid, daemon=True).start()

    def _bg_start_waydroid(self):
        ok = _waydroid_start()
        if ok:
            GLib.idle_add(self._load_apps)
        else:
            GLib.idle_add(self._on_waydroid_error,
                          "Could not start Waydroid. Check that it is installed and binder is loaded.")

    def _load_apps(self):
        threading.Thread(target=self._bg_load_apps, daemon=True).start()

    def _bg_load_apps(self):
        apps = _list_android_apps()
        GLib.idle_add(self._render_apps, apps)

    def _render_apps(self, apps: List[dict]):
        while True:
            child = self._flow.get_first_child()
            if child is None:
                break
            self._flow.remove(child)

        self._apps = apps
        for app in apps:
            card = AndroidAppCard(app, self._on_app_launch)
            self._flow.append(card)

        if apps:
            self._stack.set_visible_child_name("grid")
        else:
            self._status_page.set_title("No Android apps installed")
            self._status_page.set_description(
                "Install APK files to add Android apps.\n"
                "Drag an APK file here or click 'Install APK…'."
            )
            self._stack.set_visible_child_name("offline")

    def _on_waydroid_error(self, msg: str):
        self._banner.set_title(msg)
        self._banner.set_revealed(True)
        self._stack.set_visible_child_name("offline")

    # -----------------------------------------------------------------------
    # Event handlers
    # -----------------------------------------------------------------------

    def _on_power_toggled(self, btn):
        if btn.get_active():
            self._start_waydroid()
        else:
            threading.Thread(target=_waydroid_stop, daemon=True).start()
            self._stack.set_visible_child_name("offline")

    def _on_install_apk_clicked(self, btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Select APK File")
        filter_ = Gtk.FileFilter()
        filter_.set_name("Android Package (*.apk, *.xapk)")
        filter_.add_pattern("*.apk")
        filter_.add_pattern("*.xapk")
        dialog.set_default_filter(filter_)
        dialog.open(self, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                self._install_apk_now(file.get_path())
        except Exception:
            pass

    def _install_apk_now(self, apk_path: str):
        install_dialog = ApkInstallDialog(self, apk_path)
        install_dialog.connect("closed", lambda d: GLib.idle_add(self._load_apps))
        install_dialog.present(self)

    def _on_drop(self, target, value, x, y):
        if isinstance(value, Gio.File):
            path = value.get_path()
            if path and (path.endswith(".apk") or path.endswith(".xapk")):
                self._install_apk_now(path)
                return True
        return False

    def _on_app_launch(self, app_data: dict):
        package = app_data.get("package", "")
        if not package:
            return
        threading.Thread(
            target=_launch_app, args=(package,), daemon=True
        ).start()


# ---------------------------------------------------------------------------
# Application class
# ---------------------------------------------------------------------------

class WaydroidApp(Adw.Application):
    def __init__(self, initial_apk: Optional[str] = None):
        super().__init__(application_id="os.bobo.WaydroidLauncher",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self._initial_apk = initial_apk
        self.connect("activate", self._on_activate)

        # Actions for context menus
        launch_action = Gio.SimpleAction.new("launch", GLib.VariantType.new("s"))
        launch_action.connect("activate", lambda a, p: _launch_app(p.get_string()))
        self.add_action(launch_action)

        uninstall_action = Gio.SimpleAction.new("uninstall", GLib.VariantType.new("s"))
        uninstall_action.connect("activate", self._on_uninstall)
        self.add_action(uninstall_action)

    def _on_activate(self, app):
        win = WaydroidLauncherWindow(
            initial_apk=self._initial_apk,
            application=app
        )
        win.present()

    def _on_uninstall(self, action, param):
        package = param.get_string()
        threading.Thread(
            target=lambda: subprocess.run(
                ["waydroid", "app", "remove", package],
                capture_output=True
            ),
            daemon=True
        ).start()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _run_self_test():
    print("=== Waydroid Launcher Self-Test ===")
    pass_count = 0
    fail_count = 0

    def ok(msg):
        nonlocal pass_count
        print(f"  PASS  {msg}")
        pass_count += 1

    def fail(msg):
        nonlocal fail_count
        print(f"  FAIL  {msg}")
        fail_count += 1

    # waydroid binary present?
    import shutil
    if shutil.which("waydroid"):
        ok("waydroid binary found")
    else:
        fail("waydroid not installed — run waydroid-setup.sh --init")

    # GTK4
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        ok("GTK4 importable")
    except Exception as e:
        fail(f"GTK4 not importable: {e}")

    # Test _waydroid_running (non-crashing)
    try:
        result = _waydroid_running()
        ok(f"_waydroid_running() returned: {result}")
    except Exception as e:
        fail(f"_waydroid_running() raised: {e}")

    # Test _list_android_apps (non-crashing, may return empty)
    try:
        apps = _list_android_apps()
        ok(f"_list_android_apps() returned {len(apps)} apps (may be 0 if offline)")
    except Exception as e:
        fail(f"_list_android_apps() raised: {e}")

    print(f"  PASS: {pass_count}  FAIL: {fail_count}")
    print("===================================")
    return fail_count == 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(0 if _run_self_test() else 1)

    initial_apk = None
    if "--install" in sys.argv:
        idx = sys.argv.index("--install")
        if idx + 1 < len(sys.argv):
            initial_apk = sys.argv[idx + 1]

    if "--launch" in sys.argv:
        idx = sys.argv.index("--launch")
        if idx + 1 < len(sys.argv):
            package = sys.argv[idx + 1]
            if not _waydroid_running():
                _waydroid_start()
            _launch_app(package)
            sys.exit(0)

    app = WaydroidApp(initial_apk=initial_apk)
    sys.exit(app.run([]))
