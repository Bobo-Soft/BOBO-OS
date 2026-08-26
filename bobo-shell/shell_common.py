#!/usr/bin/env python3
"""
BOBO Shell — shared helpers for the Windows-like desktop shell.

All shell components (taskbar, start menu, sidebar, desktop icons, Ctrl+Alt+Del,
personalization) import this module for:
  * config load/save         (~/.config/bobo-shell/config.json)
  * accent-colour + CSS       (design tokens from CLAUDE.md, live-reloadable)
  * .desktop application list  (parsed from the standard XDG dirs)
  * singleton/toggle helper    (so a launcher key toggles a window on/off)

Written for GTK3 + gtk-layer-shell (renders reliably everywhere, incl. VMs).
"""
import os
import json
import signal
import subprocess
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Gio, GLib  # noqa: E402

# ── Design tokens (CLAUDE.md) ────────────────────────────────────────────────
DEFAULTS = {
    "bg_dark":      "#1a1a2e",
    "accent":       "#4a9eff",
    "text_dark":    "#ffffff",
    "bg_light":     "#f5f5f5",
    "accent_light": "#0066cc",
    "text_light":   "#1a1a1a",
    "taskbar_h":    48,
    "corner":       8,
    "theme":        "dark",       # "dark" | "light"
    "autohide":     True,
}

CONFIG_DIR = Path(GLib.get_user_config_dir()) / "bobo-shell"
CONFIG_FILE = CONFIG_DIR / "config.json"
CSS_FILE = CONFIG_DIR / "shell.css"
# Presets the personalization tool offers for the accent colour.
ACCENT_PRESETS = ["#4a9eff", "#0066cc", "#22c55e", "#e11d48",
                  "#a855f7", "#f59e0b", "#14b8a6", "#64748b"]


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        if CONFIG_FILE.exists():
            cfg.update(json.loads(CONFIG_FILE.read_text()))
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a: str, b: str, t: float) -> str:
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    return "#%02x%02x%02x" % (
        int(ra + (rb - ra) * t), int(ga + (gb - ga) * t), int(ba + (bb - ba) * t))


def build_css(cfg: dict) -> str:
    """Generate the shell CSS from the current config (accent, theme)."""
    dark = cfg.get("theme", "dark") == "dark"
    accent = cfg["accent"] if dark else cfg.get("accent_light", cfg["accent"])
    bg = cfg["bg_dark"] if dark else cfg["bg_light"]
    fg = cfg["text_dark"] if dark else cfg["text_light"]
    panel = _mix(bg, "#000000", 0.15) if dark else _mix(bg, "#ffffff", 0.4)
    hover = _mix(panel, accent, 0.28)
    tpl = Path(__file__).with_name("style.css").read_text()
    for k, v in {
        "@ACCENT@": accent, "@BG@": bg, "@FG@": fg,
        "@PANEL@": panel, "@HOVER@": hover,
        "@ACCENT_SOFT@": _mix(panel, accent, 0.5),
        "@BORDER@": _mix(panel, fg, 0.18),
        "@CORNER@": str(cfg.get("corner", 8)),
    }.items():
        tpl = tpl.replace(k, v)
    return tpl


def apply_css(cfg: dict | None = None):
    """Install the generated CSS on the default screen (call once per process)."""
    cfg = cfg or load_config()
    provider = Gtk.CssProvider()
    provider.load_from_data(build_css(cfg).encode())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10)
    return provider


# ── Display readiness ────────────────────────────────────────────────────────
def wait_for_display(timeout: float = 25.0) -> bool:
    """
    Block until GTK can open the display, then return True. Wayfire spawns its
    [autostart] entries the moment it comes up, sometimes a beat before the
    Wayland socket accepts GTK clients — without this wait the shell dies with
    "Gtk couldn't be initialized". Retries gtk_init_check() until it succeeds.
    """
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ok, _ = Gtk.init_check()
            if ok and Gdk.Display.get_default() is not None:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    # last attempt (let the caller surface any real error)
    try:
        ok, _ = Gtk.init_check()
        return bool(ok)
    except Exception:
        return False


# ── Application list (.desktop) ──────────────────────────────────────────────
def list_apps():
    """Return visible desktop applications, sorted by name."""
    apps = []
    for info in Gio.AppInfo.get_all():
        try:
            if not info.should_show():
                continue
            name = info.get_display_name() or info.get_name()
            if not name:
                continue
            apps.append(info)
        except Exception:
            continue
    apps.sort(key=lambda a: (a.get_display_name() or "").lower())
    return apps


def launch_app(info):
    try:
        info.launch(None, None)
        return True
    except Exception:
        try:
            subprocess.Popen(["gtk-launch", info.get_id()])
            return True
        except Exception:
            return False


def spawn(cmd):
    """Fire-and-forget a shell command (list or string)."""
    try:
        if isinstance(cmd, str):
            cmd = ["bash", "-lc", cmd]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# ── Singleton / toggle ───────────────────────────────────────────────────────
def singleton_or_toggle(name: str) -> bool:
    """
    Ensure only one instance runs. If another instance is alive, signal it to
    quit (toggle-off) and return False (meaning: this process should exit).
    Returns True if this process should proceed to show the window.
    """
    run = Path(GLib.get_user_runtime_dir() or "/tmp") / f"bobo-{name}.pid"
    try:
        if run.exists():
            old = int(run.read_text().strip())
            try:
                os.kill(old, 0)          # alive?
                os.kill(old, signal.SIGTERM)  # toggle off
                run.unlink(missing_ok=True)
                return False
            except (ProcessLookupError, ValueError):
                pass
        run.write_text(str(os.getpid()))
    except Exception:
        pass
    return True


def ensure_single(name: str) -> bool:
    """
    For always-on surfaces (taskbar, desktop) that may be launched twice (wayfire
    [autostart] AND an /etc/xdg/autostart entry): run once, and if another instance
    is already alive just exit quietly. Unlike singleton_or_toggle it NEVER kills the
    existing instance (killing it is what left the taskbar invisible).
    """
    run = Path(GLib.get_user_runtime_dir() or "/tmp") / f"bobo-{name}.pid"
    try:
        if run.exists():
            old = int(run.read_text().strip())
            try:
                os.kill(old, 0)   # already running -> this instance should exit
                return False
            except (ProcessLookupError, ValueError):
                pass
        run.write_text(str(os.getpid()))
    except Exception:
        pass
    return True


def clear_singleton(name: str):
    run = Path(GLib.get_user_runtime_dir() or "/tmp") / f"bobo-{name}.pid"
    try:
        run.unlink(missing_ok=True)
    except Exception:
        pass
