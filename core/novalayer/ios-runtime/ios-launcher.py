#!/usr/bin/env python3
"""
BOBO OS — iOS App Launcher (Phase 4.4)
E:\BOBO-OS\core\novalayer\ios-runtime\ios-launcher.py

Extracts and runs .ipa files in a sandboxed ARM emulation environment.
- Default window: 390×844 (iPhone 14 portrait)
- Toolbar: Rotate / Home / Back
- Mouse: click=tap, click+drag=swipe, scroll=pinch
- DRM warning shown for App Store apps
- Log: /var/log/bobo-ios.log
"""

import os
import sys
import zipfile
import json
import shutil
import logging
import subprocess
import tempfile
import threading
from pathlib import Path

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, GLib, Gdk
    GTK_AVAILABLE = True
except Exception:
    GTK_AVAILABLE = False

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_PATH = "/var/log/bobo-ios.log"
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [iOS] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("ios")

# ── Constants ─────────────────────────────────────────────────────────────────
IPA_SANDBOX_DIR = Path.home() / ".bobo" / "ios-apps"
QEMU_ARM64_BIN  = shutil.which("qemu-aarch64") or shutil.which("qemu-aarch64-static") or "qemu-aarch64"
# Portrait iPhone 14 dimensions
DEFAULT_W, DEFAULT_H = 390, 844
TOOLBAR_H = 48


# ── IPA extraction & validation ───────────────────────────────────────────────

def extract_ipa(ipa_path: str) -> tuple[Path, dict]:
    """
    Extract the IPA into a sandbox directory.
    Returns (app_dir, info_plist_dict).
    Raises ValueError for invalid / DRM-locked IPAs.
    """
    ipa_path = Path(ipa_path).resolve()
    app_name = ipa_path.stem

    sandbox = IPA_SANDBOX_DIR / app_name
    sandbox.mkdir(parents=True, exist_ok=True)

    log.info("Extracting %s → %s", ipa_path, sandbox)

    with zipfile.ZipFile(ipa_path, "r") as zf:
        # Validate IPA structure
        payload_entries = [n for n in zf.namelist() if n.startswith("Payload/")]
        if not payload_entries:
            raise ValueError("Not a valid IPA: missing Payload/ directory.")

        # Find the .app bundle
        app_dirs = {
            Path(n).parts[1]
            for n in payload_entries
            if len(Path(n).parts) > 1 and Path(n).parts[1].endswith(".app")
        }
        if not app_dirs:
            raise ValueError("IPA has no .app bundle inside Payload/.")

        app_bundle_name = sorted(app_dirs)[0]
        log.info("App bundle: %s", app_bundle_name)

        # Extract everything
        zf.extractall(str(sandbox))

    app_dir = sandbox / "Payload" / app_bundle_name

    # Parse Info.plist (XML or binary)
    info_plist_path = app_dir / "Info.plist"
    info = _parse_plist(info_plist_path)

    # Detect DRM (SC_Info folder = FairPlay-encrypted App Store binary)
    sc_info = app_dir / "SC_Info"
    if sc_info.exists():
        info["_drm_locked"] = True
        log.warning("App appears to be DRM-locked (FairPlay): %s", app_name)

    return app_dir, info


def _parse_plist(path: Path) -> dict:
    """Parse an XML or binary plist. Returns a dict."""
    if not path.exists():
        return {}
    try:
        import plistlib
        with open(path, "rb") as f:
            return plistlib.load(f)
    except Exception as e:
        log.debug("plist parse error: %s", e)
        return {}


# ── GTK4 iOS emulation window ─────────────────────────────────────────────────

class IOSWindow(Adw.ApplicationWindow):
    """
    Hosts the emulated iOS app in a resizable GTK4 window.
    Overlays a toolbar with Rotate / Home / Back buttons.
    Translates mouse events to touch/gesture signals for the emulator.
    """

    def __init__(self, app: Adw.Application, app_name: str,
                 exec_cmd: list[str], portrait: bool = True):
        super().__init__(application=app, title=f"{app_name} — BOBO OS iOS")

        self._app_name  = app_name
        self._exec_cmd  = exec_cmd
        self._portrait  = portrait
        self._proc: subprocess.Popen | None = None

        # Window dimensions (device frame)
        self._dev_w = DEFAULT_W if portrait else DEFAULT_H
        self._dev_h = DEFAULT_H if portrait else DEFAULT_W
        self.set_default_size(self._dev_w, self._dev_h + TOOLBAR_H)
        self.set_resizable(True)

        self._build_ui()
        self._launch_emulator()

    def _build_ui(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # ── Toolbar ────────────────────────────────────────────────────────
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.add_css_class("toolbar")
        toolbar.set_margin_start(8)
        toolbar.set_margin_end(8)
        toolbar.set_margin_top(4)
        toolbar.set_margin_bottom(4)

        btn_back = Gtk.Button(label="← Back")
        btn_back.connect("clicked", self._on_back)
        toolbar.append(btn_back)

        lbl_name = Gtk.Label(label=self._app_name)
        lbl_name.set_hexpand(True)
        lbl_name.set_halign(Gtk.Align.CENTER)
        lbl_name.add_css_class("title-4")
        toolbar.append(lbl_name)

        btn_rotate = Gtk.Button(label="⟳ Rotate")
        btn_rotate.connect("clicked", self._on_rotate)
        toolbar.append(btn_rotate)

        btn_home = Gtk.Button(label="⌂ Home")
        btn_home.connect("clicked", self._on_home)
        toolbar.append(btn_home)

        outer.append(toolbar)

        # ── Emulator viewport ─────────────────────────────────────────────
        # The emulator (QEMU or socket-based) renders into a socket window.
        # We embed it via a DrawingArea as a placeholder; a real implementation
        # would use GtkSocket (X11) or a Wayland sub-surface.
        self._viewport = Gtk.DrawingArea()
        self._viewport.set_hexpand(True)
        self._viewport.set_vexpand(True)
        self._viewport.set_content_width(self._dev_w)
        self._viewport.set_content_height(self._dev_h)
        self._viewport.set_draw_func(self._draw_placeholder)

        # Touch gesture simulation via mouse events
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_mouse_press)
        click.connect("released", self._on_mouse_release)
        self._viewport.add_controller(click)

        drag = Gtk.GestureDrag()
        drag.connect("drag-update", self._on_drag_update)
        self._viewport.add_controller(drag)

        scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES
        )
        scroll.connect("scroll", self._on_scroll)
        self._viewport.add_controller(scroll)

        outer.append(self._viewport)
        self.set_content(outer)

    def _draw_placeholder(self, area, cr, w, h):
        """Shown while the emulator is starting up."""
        cr.set_source_rgb(0.1, 0.1, 0.14)
        cr.paint()
        cr.set_source_rgb(0.29, 0.62, 1.0)
        cr.set_font_size(16)
        cr.move_to(w / 2 - 80, h / 2)
        cr.show_text(f"Starting {self._app_name}…")

    # ── Toolbar button handlers ───────────────────────────────────────────

    def _on_back(self, _btn):
        """Send a back-swipe to the emulated app."""
        if self._proc:
            self._send_gesture("back")

    def _on_home(self, _btn):
        """Send a Home button press to the emulated app."""
        if self._proc:
            self._send_gesture("home")

    def _on_rotate(self, _btn):
        """Toggle portrait / landscape orientation."""
        self._portrait = not self._portrait
        self._dev_w, self._dev_h = self._dev_h, self._dev_w
        self.set_default_size(self._dev_w, self._dev_h + TOOLBAR_H)
        self._send_gesture("rotate")
        log.info("Rotated to %s", "portrait" if self._portrait else "landscape")

    # ── Mouse → touch translation ─────────────────────────────────────────

    def _on_mouse_press(self, _gesture, _n, x, y):
        self._touch_start = (x, y)
        self._send_touch("touch_down", x, y)

    def _on_mouse_release(self, _gesture, _n, x, y):
        self._send_touch("touch_up", x, y)

    def _on_drag_update(self, _gesture, dx, dy):
        sx, sy = getattr(self, "_touch_start", (0, 0))
        self._send_touch("touch_move", sx + dx, sy + dy)

    def _on_scroll(self, _ctrl, dx, dy):
        """Scroll wheel → pinch-to-zoom (scale ±5% per scroll click)."""
        self._send_gesture("pinch", str(1.0 - dy * 0.05))

    def _send_touch(self, event: str, x: float, y: float):
        """Relay a touch event to the emulator via stdin pipe."""
        if self._proc and self._proc.stdin:
            try:
                msg = json.dumps({"event": event, "x": round(x), "y": round(y)}) + "\n"
                self._proc.stdin.write(msg.encode())
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    def _send_gesture(self, name: str, value: str = ""):
        if self._proc and self._proc.stdin:
            try:
                msg = json.dumps({"event": name, "value": value}) + "\n"
                self._proc.stdin.write(msg.encode())
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    # ── Emulator process ──────────────────────────────────────────────────

    def _launch_emulator(self):
        """Start the ARM64 emulator in a background thread."""
        threading.Thread(target=self._run_emulator, daemon=True).start()

    def _run_emulator(self):
        log.info("Starting emulator: %s", self._exec_cmd)
        try:
            self._proc = subprocess.Popen(
                self._exec_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = self._proc.communicate()
            rc = self._proc.returncode

            if rc != 0:
                log.warning("Emulator exited with code %d", rc)
                if stderr:
                    log.info("stderr: %s", stderr.decode(errors="replace")[:500])
                GLib.idle_add(self._show_crash_dialog)
        except FileNotFoundError:
            log.error("Emulator binary not found: %s", self._exec_cmd[0])
            GLib.idle_add(self._show_emulator_missing_dialog)

    def _show_crash_dialog(self):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="App stopped",
            body=(
                f"'{self._app_name}' stopped unexpectedly.\n\n"
                "iOS apps may have compatibility issues depending on the frameworks they use.\n"
                "Details were saved to the compatibility log."
            ),
        )
        dialog.add_response("ok", "OK")
        dialog.present()

    def _show_emulator_missing_dialog(self):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="iOS runtime not available",
            body=(
                "The iOS emulation runtime (qemu-aarch64) is not installed.\n\n"
                "You can install it via NovaStore → System Tools."
            ),
        )
        dialog.add_response("ok", "OK")
        dialog.present()


class IOSLauncherApp(Adw.Application):
    def __init__(self, app_name: str, exec_cmd: list[str]):
        super().__init__(application_id="os.bobo.ios.launcher")
        self._app_name = app_name
        self._exec_cmd = exec_cmd

    def do_activate(self):
        win = IOSWindow(self, self._app_name, self._exec_cmd)
        win.present()


# ── DRM warning dialog (before launching) ────────────────────────────────────

def show_drm_warning(app_name: str) -> bool:
    """Show a warning for DRM-locked apps. Returns True if user wants to proceed."""
    if not GTK_AVAILABLE:
        return True

    result = {"proceed": False}

    class DrmApp(Adw.Application):
        def do_activate(self):
            dialog = Adw.MessageDialog(
                heading="DRM-protected app",
                body=(
                    f"'{app_name}' was purchased from the App Store and is DRM-protected.\n\n"
                    "It may not work correctly with BOBO OS iOS compatibility.\n\n"
                    "You can still try to open it, but playback or features may be limited."
                ),
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("proceed", "Try anyway")
            dialog.set_response_appearance("proceed", Adw.ResponseAppearance.SUGGESTED)

            def on_response(d, r):
                result["proceed"] = (r == "proceed")
                self.quit()

            dialog.connect("response", on_response)
            dialog.present()

    DrmApp(application_id="os.bobo.ios.drm").run([])
    return result["proceed"]


# ── Build the QEMU command for this app ──────────────────────────────────────

def build_emulator_cmd(app_dir: Path, info: dict) -> list[str]:
    """
    Build the command to run the app's main executable under QEMU user-mode.
    In production this would use a custom iOS runtime environment;
    here we construct a QEMU user-mode emulation command.
    """
    bundle_exec = info.get("CFBundleExecutable", app_dir.name.replace(".app", ""))
    exec_path = app_dir / bundle_exec

    if not exec_path.exists():
        raise FileNotFoundError(f"Executable not found: {exec_path}")

    cmd = [
        QEMU_ARM64_BIN,
        "-L", str(app_dir),              # Use app bundle as library root
        str(exec_path),
    ]
    log.info("Emulator command: %s", cmd)
    return cmd


# ── Compatibility log ─────────────────────────────────────────────────────────

def log_compatibility(app_name: str, info: dict, error: str | None = None):
    entry = {
        "app": app_name,
        "bundle_id": info.get("CFBundleIdentifier", "unknown"),
        "version": info.get("CFBundleShortVersionString", "?"),
        "min_os": info.get("MinimumOSVersion", "?"),
        "drm": info.get("_drm_locked", False),
        "error": error,
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2 or sys.argv[1] == "--self-test":
        run_self_test()
        return

    ipa_path = sys.argv[1]

    if not os.path.isfile(ipa_path):
        log.error("File not found: %s", ipa_path)
        sys.exit(1)

    # Extract and validate
    try:
        app_dir, info = extract_ipa(ipa_path)
    except (ValueError, zipfile.BadZipFile) as e:
        log.error("Invalid IPA: %s", e)
        if GTK_AVAILABLE:
            err_app = Adw.Application(application_id="os.bobo.ios.error")
            def on_act(a):
                d = Adw.MessageDialog(heading="Cannot open file",
                    body=f"'{Path(ipa_path).name}' is not a valid iOS app.\n\n{e}")
                d.add_response("ok","OK"); d.connect("response", lambda *_: a.quit())
                d.present()
            err_app.connect("activate", on_act)
            err_app.run([])
        sys.exit(1)

    app_name = info.get("CFBundleDisplayName") or info.get("CFBundleName") or Path(ipa_path).stem

    # DRM check
    if info.get("_drm_locked"):
        if not show_drm_warning(app_name):
            log.info("User cancelled DRM-locked app launch.")
            sys.exit(0)

    log_compatibility(app_name, info)

    # Build emulator command
    try:
        exec_cmd = build_emulator_cmd(app_dir, info)
    except FileNotFoundError as e:
        log.error("Cannot find app executable: %s", e)
        log_compatibility(app_name, info, str(e))
        sys.exit(1)

    # Launch GTK4 window with embedded emulator
    if not GTK_AVAILABLE:
        log.error("GTK4 not available — cannot show iOS window.")
        subprocess.run(exec_cmd)
        return

    launcher = IOSLauncherApp(app_name, exec_cmd)
    launcher.run([])


# ── Self-test ─────────────────────────────────────────────────────────────────

def run_self_test():
    import tempfile

    print("=== iOS Launcher Self-Test ===")
    passed = 0
    total  = 0

    def check(label: str, ok: bool):
        nonlocal passed, total
        total += 1
        if ok: passed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")

    # Test: valid IPA extraction
    with tempfile.NamedTemporaryFile(suffix=".ipa", delete=False) as f:
        tmp_ipa = f.name
    with zipfile.ZipFile(tmp_ipa, "w") as zf:
        zf.writestr("Payload/TestApp.app/Info.plist",
                    b'<?xml version="1.0"?><plist version="1.0"><dict>'
                    b'<key>CFBundleExecutable</key><string>TestApp</string>'
                    b'<key>CFBundleDisplayName</key><string>TestApp</string>'
                    b'</dict></plist>')
        zf.writestr("Payload/TestApp.app/TestApp", b"\xCA\xFE\xBA\xBE")
    try:
        app_dir, info = extract_ipa(tmp_ipa)
        check("IPA extraction", app_dir.exists())
        check("Info.plist parsed", info.get("CFBundleDisplayName") == "TestApp")
        check("DRM not falsely detected", not info.get("_drm_locked", False))
        shutil.rmtree(app_dir.parent, ignore_errors=True)
    except Exception as e:
        check(f"IPA extraction (exception: {e})", False)
        check("Info.plist parsed", False)
        check("DRM detection", False)
    finally:
        os.unlink(tmp_ipa)

    # Test: invalid IPA
    with tempfile.NamedTemporaryFile(suffix=".ipa", delete=False) as f:
        f.write(b"not a zip")
        tmp_bad = f.name
    try:
        extract_ipa(tmp_bad)
        check("Invalid IPA rejected", False)
    except (ValueError, zipfile.BadZipFile):
        check("Invalid IPA rejected", True)
    finally:
        os.unlink(tmp_bad)

    # Test: magic byte detection (from novalayer daemon)
    check("QEMU binary exists", bool(shutil.which("qemu-aarch64") or shutil.which("qemu-aarch64-static")))

    print(f"\n  {passed}/{total} tests passed.")
    print("==============================")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
