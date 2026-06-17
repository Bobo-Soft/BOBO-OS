#!/usr/bin/env python3
"""
BOBO OS — NovaLayer Daemon (Phase 4.1)
E:\BOBO-OS\core\novalayer\novalayer-daemon.py

Watches for file-open events via inotify and D-Bus file-manager signals,
identifies file type by extension AND magic bytes, then routes to the
correct runtime (Wine, Darling, iOS, Waydroid, native Linux).

D-Bus interface: os.bobo.NovaLayer  (method: OpenFile(path: string))
Log file:        /var/log/novalayer.log
"""

import os
import sys
import struct
import logging
import subprocess
import threading
import json
from pathlib import Path
from typing import Optional

# ── Third-party (installed on BOBO OS) ──────────────────────────────────────
try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False

try:
    import inotify_simple
    INOTIFY_AVAILABLE = True
except ImportError:
    INOTIFY_AVAILABLE = False

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, GLib as GLib2
    GTK_AVAILABLE = True
except Exception:
    GTK_AVAILABLE = False

# ── Logging setup ────────────────────────────────────────────────────────────
LOG_PATH = "/var/log/novalayer.log"
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [NovaLayer] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("novalayer")

# ── Config (loaded from bobo-os.conf) ───────────────────────────────────────
BOBO_ROOT = os.environ.get("BOBO_ROOT", "/usr/local/lib/bobo")
WINE_WRAPPER = os.path.join(BOBO_ROOT, "novalayer", "wine", "wine-wrapper.sh")
DARLING_WRAPPER = os.path.join(BOBO_ROOT, "novalayer", "darling", "darling-wrapper.sh")
IOS_LAUNCHER = os.path.join(BOBO_ROOT, "novalayer", "ios-runtime", "ios-launcher.py")
WAYDROID_BIN = "/usr/bin/waydroid"

# ── File type routing table ──────────────────────────────────────────────────
# Each entry: (description, handler_function)
EXTENSION_MAP: dict[str, str] = {
    # Windows
    ".exe":     "wine",
    ".msi":     "wine",
    ".bat":     "wine",
    ".cmd":     "wine",
    # macOS
    ".app":     "darling",
    ".dmg":     "darling",
    ".pkg":     "darling",
    # iOS
    ".ipa":     "ios",
    # Android
    ".apk":     "waydroid",
    ".xapk":    "waydroid",
    # Native Linux (handled by system, but we log them)
    ".deb":     "linux_deb",
    ".rpm":     "linux_rpm",
    ".flatpak": "linux_flatpak",
    ".appimage":"linux_appimage",
}

# Magic bytes for content-based detection (more reliable than extension alone)
MAGIC_SIGNATURES: list[tuple[bytes, int, str]] = [
    # offset, magic bytes, runtime
    (b"MZ",                     0, "wine"),        # PE executable (EXE/DLL)
    (b"\xD0\xCF\x11\xE0",      0, "wine"),        # MSI (Compound Document)
    (b"PK\x03\x04",            0, "ipa_check"),   # IPA/APK (ZIP-based — check further)
    (b"\x78\x61\x72\x21",      0, "darling"),     # XAR (macOS .pkg)
    (b"\x50\x4D\x4F\x43",      0, "darling"),     # PMOC (macOS DMG)
    (b"koly",                  -512, "darling"),   # DMG trailer
    (b"#!",                    0, "script"),       # Shebang — run natively
]

# Directories to watch for file-open activity (user home + tmp)
WATCH_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path("/tmp"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Magic-byte file type detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_by_magic(path: str) -> Optional[str]:
    """Read the first and last 512 bytes and check against known magic bytes."""
    try:
        with open(path, "rb") as f:
            header = f.read(512)
            try:
                f.seek(-512, 2)
                trailer = f.read(512)
            except OSError:
                trailer = b""
    except (OSError, PermissionError):
        return None

    for magic, offset, runtime in MAGIC_SIGNATURES:
        if offset >= 0:
            chunk = header
            pos = offset
        else:
            chunk = trailer
            pos = len(trailer) + offset

        if pos >= 0 and chunk[pos:pos + len(magic)] == magic:
            if runtime == "ipa_check":
                return _distinguish_ipa_apk(path, header)
            return runtime
    return None


def _distinguish_ipa_apk(path: str, header: bytes) -> str:
    """IPA and APK are both ZIP files — look inside to tell them apart."""
    try:
        import zipfile
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
        # IPA contains Payload/<AppName>.app/
        if any(n.startswith("Payload/") and n.endswith(".app/") for n in names):
            return "ios"
        # APK contains AndroidManifest.xml
        if "AndroidManifest.xml" in names:
            return "waydroid"
    except Exception:
        pass
    # Fallback: guess by extension
    ext = Path(path).suffix.lower()
    return "ios" if ext == ".ipa" else "waydroid"


def identify_file(path: str) -> Optional[str]:
    """Return the runtime key for this file, or None if it should open natively."""
    ext = Path(path).suffix.lower()

    # Extension-based routing (fast path)
    if ext in EXTENSION_MAP:
        runtime = EXTENSION_MAP[ext]
        # Verify with magic bytes for executables where it matters
        if runtime in ("wine", "darling", "ios", "waydroid"):
            magic_runtime = detect_by_magic(path)
            if magic_runtime and magic_runtime != runtime:
                log.warning(
                    "Extension says %s but magic says %s for %s — trusting magic.",
                    runtime, magic_runtime, path
                )
                return magic_runtime
        return runtime

    # No matching extension — try magic bytes only
    return detect_by_magic(path)


# ─────────────────────────────────────────────────────────────────────────────
# Runtime launchers
# ─────────────────────────────────────────────────────────────────────────────

def show_toast(message: str) -> None:
    """Show a GTK4 toast notification without blocking."""
    if not GTK_AVAILABLE:
        log.info("Toast (no GTK): %s", message)
        return

    def _show():
        try:
            app = Adw.Application(application_id="os.bobo.novalayer.toast")

            def on_activate(application):
                win = Adw.ApplicationWindow(application=application)
                win.set_default_size(1, 1)
                overlay = Adw.ToastOverlay()
                toast = Adw.Toast(title=message, timeout=3)
                overlay.add_toast(toast)
                win.set_content(overlay)
                win.present()
                GLib2.timeout_add(3500, application.quit)

            app.connect("activate", on_activate)
            app.run([])
        except Exception as e:
            log.debug("Toast error: %s", e)

    threading.Thread(target=_show, daemon=True).start()


def launch_wine(path: str) -> None:
    log.info("Routing to Wine: %s", path)
    show_toast(f"Opening Windows app with NovaLayer…")
    subprocess.Popen(
        ["bash", WINE_WRAPPER, path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def launch_darling(path: str) -> None:
    log.info("Routing to Darling: %s", path)
    show_toast(f"Opening macOS app with NovaLayer…")
    subprocess.Popen(
        ["bash", DARLING_WRAPPER, path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def launch_ios(path: str) -> None:
    log.info("Routing to iOS runtime: %s", path)
    show_toast("Opening iOS app with NovaLayer…")
    subprocess.Popen(
        [sys.executable, IOS_LAUNCHER, path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def launch_waydroid(path: str) -> None:
    log.info("Routing to Waydroid: %s", path)
    show_toast("Installing Android app with Waydroid…")
    subprocess.Popen(
        [WAYDROID_BIN, "app", "install", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def launch_linux_package(path: str, runtime: str) -> None:
    log.info("Installing native Linux package (%s): %s", runtime, path)
    show_toast(f"Installing package…")
    cmds = {
        "linux_deb":      ["pkexec", "apt", "install", "-y", path],
        "linux_rpm":      ["pkexec", "dnf", "install", "-y", path],
        "linux_flatpak":  ["flatpak", "install", "--noninteractive", path],
        "linux_appimage": [path],  # AppImage: just run it
    }
    cmd = cmds.get(runtime, [path])
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


RUNTIME_DISPATCH = {
    "wine":           launch_wine,
    "darling":        launch_darling,
    "ios":            launch_ios,
    "waydroid":       launch_waydroid,
    "linux_deb":      lambda p: launch_linux_package(p, "linux_deb"),
    "linux_rpm":      lambda p: launch_linux_package(p, "linux_rpm"),
    "linux_flatpak":  lambda p: launch_linux_package(p, "linux_flatpak"),
    "linux_appimage": lambda p: launch_linux_package(p, "linux_appimage"),
}


def open_file(path: str) -> None:
    """Top-level entry point: identify and dispatch a file to its runtime."""
    if not os.path.isfile(path):
        log.warning("open_file called with non-existent path: %s", path)
        return

    runtime = identify_file(path)
    if runtime is None or runtime == "script":
        log.info("No NovaLayer handler for %s — passing to system xdg-open.", path)
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    handler = RUNTIME_DISPATCH.get(runtime)
    if handler:
        log.info("Dispatching %s → %s", path, runtime)
        handler(path)
    else:
        log.warning("Unknown runtime '%s' for %s", runtime, path)


# ─────────────────────────────────────────────────────────────────────────────
# D-Bus service (file managers call OpenFile directly)
# ─────────────────────────────────────────────────────────────────────────────

DBUS_BUS_NAME   = "os.bobo.NovaLayer"
DBUS_OBJ_PATH   = "/os/bobo/NovaLayer"
DBUS_INTERFACE  = "os.bobo.NovaLayer"


class NovaLayerDBusService(dbus.service.Object):
    """D-Bus object that exposes the OpenFile method to file managers and apps."""

    def __init__(self, bus):
        super().__init__(bus, DBUS_OBJ_PATH)

    @dbus.service.method(DBUS_INTERFACE, in_signature="s", out_signature="s")
    def OpenFile(self, path: str) -> str:
        log.info("D-Bus OpenFile(%s)", path)
        threading.Thread(target=open_file, args=(str(path),), daemon=True).start()
        return "ok"

    @dbus.service.method(DBUS_INTERFACE, in_signature="s", out_signature="s")
    def IdentifyFile(self, path: str) -> str:
        runtime = identify_file(str(path))
        return runtime or "native"


# ─────────────────────────────────────────────────────────────────────────────
# inotify watcher — watches Downloads and Desktop for new files
# ─────────────────────────────────────────────────────────────────────────────

def inotify_watcher() -> None:
    """Watch configured directories; dispatch new files that appear."""
    if not INOTIFY_AVAILABLE:
        log.info("inotify_simple not available — skipping filesystem watcher.")
        return

    inotify = inotify_simple.INotify()
    flags = inotify_simple.flags.CLOSE_WRITE | inotify_simple.flags.MOVED_TO

    wd_to_dir: dict[int, Path] = {}
    for d in WATCH_DIRS:
        if d.exists():
            wd = inotify.add_watch(str(d), flags)
            wd_to_dir[wd] = d
            log.info("Watching directory: %s", d)

    while True:
        try:
            events = inotify.read(timeout=5000)
            for event in events:
                if event.name:
                    parent = wd_to_dir.get(event.wd, Path("/tmp"))
                    full_path = str(parent / event.name)
                    runtime = identify_file(full_path)
                    if runtime:
                        log.info("inotify: new file detected %s (runtime=%s)", full_path, runtime)
                        # Only auto-open if it's an application file (not a document)
                        if runtime in ("wine", "darling", "ios", "waydroid"):
                            open_file(full_path)
        except Exception as e:
            log.debug("inotify read error: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Main entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("NovaLayer daemon starting (pid %d).", os.getpid())

    # Start inotify watcher in a background thread
    threading.Thread(target=inotify_watcher, daemon=True).start()

    if not DBUS_AVAILABLE:
        log.warning("python-dbus not available — D-Bus interface disabled. "
                    "File manager integration will not work.")
        # Keep alive via a simple loop
        import time
        while True:
            time.sleep(60)

    # Register D-Bus service on the session bus
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    session_bus = dbus.SessionBus()

    bus_name = dbus.service.BusName(DBUS_BUS_NAME, bus=session_bus)
    service = NovaLayerDBusService(session_bus)

    log.info("D-Bus service registered: %s", DBUS_BUS_NAME)
    log.info("NovaLayer daemon ready.")

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        log.info("NovaLayer daemon stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# Self-test (run with: python3 novalayer-daemon.py --test)
# ─────────────────────────────────────────────────────────────────────────────

def self_test() -> None:
    import tempfile

    print("=== NovaLayer Self-Test ===")
    results = []

    # Test 1: Extension routing
    cases = [
        ("/tmp/app.exe",     "wine"),
        ("/tmp/app.msi",     "wine"),
        ("/tmp/app.dmg",     "darling"),
        ("/tmp/app.pkg",     "darling"),
        ("/tmp/app.ipa",     "ios"),
        ("/tmp/app.apk",     "waydroid"),
        ("/tmp/app.deb",     "linux_deb"),
        ("/tmp/app.flatpak", "linux_flatpak"),
    ]
    for path, expected in cases:
        # Create a tiny dummy file so identify_file doesn't bail out
        with tempfile.NamedTemporaryFile(suffix=Path(path).suffix, delete=False) as f:
            f.write(b"\x00" * 16)
            tmp = f.name
        result = identify_file(tmp)
        ok = result == expected
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {Path(path).suffix} → {result} (expected {expected})")
        os.unlink(tmp)

    # Test 2: PE magic byte detection
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(b"MZ" + b"\x00" * 62)
        tmp_pe = f.name
    result = detect_by_magic(tmp_pe)
    ok = result == "wine"
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  PE magic → {result} (expected wine)")
    os.unlink(tmp_pe)

    passed = sum(results)
    total = len(results)
    print(f"\n  {passed}/{total} tests passed.")
    print("===========================")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        self_test()
    else:
        main()
