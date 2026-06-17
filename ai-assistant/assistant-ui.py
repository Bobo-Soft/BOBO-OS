#!/usr/bin/env python3
# =============================================================================
# BOBO OS — AI Assistant GTK4 Panel (Phase 8.3 / assistant UI)
# E:\BOBO-OS\ai-assistant\assistant-ui.py
#
# Slides in from the right edge of the screen (Win+A or taskbar click).
# Sends messages to the assistant daemon via D-Bus (os.bobo.AIAssistant).
# Features:
#  - Persistent conversation history (scrollable)
#  - Markdown-style message rendering (bold, code)
#  - Proactive error suggestions surfaced from the daemon
#  - File drop: drop any file to ask about it
#  - Quick action chips ("What can you do?", "Open Settings", etc.)
#  - Does NOT steal focus from the active window
# =============================================================================

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk
try:
    from gi.repository import GtkLayerShell
    HAS_LAYER_SHELL = True
except Exception:
    HAS_LAYER_SHELL = False

import sys
import os
import json
import threading
import subprocess
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PANEL_WIDTH   = 400
DBUS_NAME     = "os.bobo.AIAssistant"
DBUS_PATH     = "/os/bobo/AIAssistant"
DBUS_IFACE    = "os.bobo.AIAssistant"
HISTORY_FILE  = Path.home() / ".cache" / "bobo-os" / "assistant-history.json"
MAX_HISTORY   = 60

QUICK_CHIPS = [
    "What can you do?",
    "Open Settings",
    "Check for updates",
    "How do I install an app?",
    "Show system info",
]

# ---------------------------------------------------------------------------
# D-Bus helper — talks to the assistant daemon
# ---------------------------------------------------------------------------

def _dbus_ask(message: str) -> str:
    """
    Send a message to the AI assistant daemon via D-Bus.
    Falls back to a local Ollama call if the daemon is not running.
    """
    try:
        result = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest",       DBUS_NAME,
             "--object-path", DBUS_PATH,
             "--method",     f"{DBUS_IFACE}.Ask",
             f"'{message.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            # gdbus returns ("reply",) — strip parens and quotes
            raw = result.stdout.strip()
            if raw.startswith("(") and raw.endswith(",)"):
                raw = raw[1:-2].strip()
            if raw.startswith("'") and raw.endswith("'"):
                raw = raw[1:-1]
            return raw.replace("\\'", "'")
    except Exception:
        pass

    # Daemon offline: direct Ollama fallback
    try:
        import urllib.request, json as _json
        payload = _json.dumps({
            "model": "llama3",
            "messages": [{"role": "user", "content": message}],
            "stream": False
        }).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = _json.loads(resp.read())
            return data["message"]["content"]
    except Exception as e:
        return f"I couldn't reach the AI backend. ({e})"


def _dbus_clear_history():
    subprocess.run(
        ["gdbus", "call", "--session",
         "--dest", DBUS_NAME, "--object-path", DBUS_PATH,
         "--method", f"{DBUS_IFACE}.ClearHistory"],
        capture_output=True, timeout=5
    )


def _dbus_get_status() -> str:
    try:
        result = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", DBUS_NAME, "--object-path", DBUS_PATH,
             "--method", f"{DBUS_IFACE}.GetStatus"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            raw = result.stdout.strip().strip("(,)").strip("'")
            return raw
    except Exception:
        pass
    return "offline"


# ---------------------------------------------------------------------------
# Message bubble widget
# ---------------------------------------------------------------------------

class MessageBubble(Gtk.Box):
    """A single chat message bubble — user or assistant."""

    def __init__(self, text: str, is_user: bool):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_halign(Gtk.Align.END if is_user else Gtk.Align.START)
        self.set_margin_start(8 if is_user else 4)
        self.set_margin_end(4 if is_user else 8)
        self.set_margin_top(4)
        self.set_margin_bottom(4)

        bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        bubble.add_css_class("message-bubble")
        bubble.add_css_class("user-bubble" if is_user else "assistant-bubble")
        bubble.set_margin_start(4)
        bubble.set_margin_end(4)

        lbl = Gtk.Label()
        lbl.set_wrap(True)
        lbl.set_wrap_mode(2)  # PANGO_WRAP_WORD_CHAR
        lbl.set_xalign(0)
        lbl.set_max_width_chars(38)
        lbl.set_selectable(True)

        # Simple markup: **bold** and `code`
        import re
        markup = GLib.markup_escape_text(text)
        markup = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', markup)
        markup = re.sub(r'`(.+?)`', r'<tt>\1</tt>', markup)
        lbl.set_markup(markup)

        bubble.set_margin_top(8)
        bubble.set_margin_bottom(8)
        bubble.set_margin_start(12)
        bubble.set_margin_end(12)
        bubble.append(lbl)
        self.append(bubble)


class TypingIndicator(Gtk.Box):
    """Animated dots shown while the assistant is thinking."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.set_halign(Gtk.Align.START)
        self.set_margin_start(16)
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.add_css_class("assistant-bubble")
        self.add_css_class("message-bubble")

        self._dots = []
        for i in range(3):
            dot = Gtk.Label(label="●")
            dot.add_css_class("dim-label")
            dot.set_margin_start(2)
            dot.set_margin_end(2)
            dot.set_margin_top(8)
            dot.set_margin_bottom(8)
            self._dots.append(dot)
            self.append(dot)

        self._step = 0
        self._timer = GLib.timeout_add(400, self._animate)

    def _animate(self):
        for i, dot in enumerate(self._dots):
            if i == self._step % 3:
                dot.remove_css_class("dim-label")
                dot.add_css_class("accent")
            else:
                dot.remove_css_class("accent")
                dot.add_css_class("dim-label")
        self._step += 1
        return True

    def stop(self):
        GLib.source_remove(self._timer)


# ---------------------------------------------------------------------------
# Main assistant panel window
# ---------------------------------------------------------------------------

class AssistantPanel(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("BOBO Assistant")
        self.set_default_size(PANEL_WIDTH, -1)
        self.set_size_request(PANEL_WIDTH, 400)

        self._history: list = []
        self._thinking = False
        self._load_history()

        self._build_ui()
        self._setup_layer_shell()

        # Check if daemon is online and show status
        GLib.idle_add(self._update_status)

    # -----------------------------------------------------------------------
    # Layer shell setup (anchors panel to right edge without stealing focus)
    # -----------------------------------------------------------------------

    def _setup_layer_shell(self):
        if not HAS_LAYER_SHELL:
            # Fallback: regular window on the right
            self.set_decorated(True)
            return

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, 48)  # above taskbar
        GtkLayerShell.set_exclusive_zone(self, -1)
        # Do NOT set keyboard interactivity exclusive — user keeps focus elsewhere
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self):
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # ── Header bar ───────────────────────────────────────────────────
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title="BOBO Assistant",
            subtitle="AI-powered help"
        ))
        toolbar_view.add_top_bar(header)

        # Status dot
        self._status_btn = Gtk.Button()
        self._status_btn.add_css_class("flat")
        self._status_btn.set_icon_name("media-record-symbolic")
        self._status_btn.set_tooltip_text("AI backend status")
        header.pack_start(self._status_btn)

        # Clear history button
        clear_btn = Gtk.Button.new_from_icon_name("edit-clear-all-symbolic")
        clear_btn.set_tooltip_text("Clear conversation")
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", self._on_clear)
        header.pack_end(clear_btn)

        # ── Messages scroll area ──────────────────────────────────────────
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_vexpand(True)
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        toolbar_view.set_content(self._scroll)

        self._messages_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._messages_box.set_margin_top(8)
        self._messages_box.set_margin_bottom(8)
        self._scroll.set_child(self._messages_box)

        # Restore previous conversation
        for msg in self._history:
            bubble = MessageBubble(msg["text"], msg["is_user"])
            self._messages_box.append(bubble)

        # Welcome message if empty
        if not self._history:
            self._add_assistant_message(
                "Hi! I'm your BOBO OS assistant. I can help you install apps, "
                "troubleshoot issues, configure settings, and more. What do you need?"
            )

        # ── Quick action chips ────────────────────────────────────────────
        chips_scroll = Gtk.ScrolledWindow()
        chips_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        chips_scroll.set_margin_top(4)

        chips_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        chips_box.set_margin_start(8)
        chips_box.set_margin_end(8)
        chips_box.set_margin_bottom(4)

        for chip_text in QUICK_CHIPS:
            chip = Gtk.Button(label=chip_text)
            chip.add_css_class("chip")
            chip.add_css_class("flat")
            chip.connect("clicked", lambda b, t=chip_text: self._send_message(t))
            chips_box.append(chip)

        chips_scroll.set_child(chips_box)
        toolbar_view.add_bottom_bar(chips_scroll)

        # ── Input row ─────────────────────────────────────────────────────
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_box.set_margin_top(8)
        input_box.set_margin_bottom(12)
        input_box.set_margin_start(12)
        input_box.set_margin_end(12)

        self._entry = Gtk.Entry()
        self._entry.set_hexpand(True)
        self._entry.set_placeholder_text("Ask anything…")
        self._entry.connect("activate", self._on_send)
        input_box.append(self._entry)

        send_btn = Gtk.Button.new_from_icon_name("paper-plane-symbolic")
        send_btn.add_css_class("suggested-action")
        send_btn.connect("clicked", self._on_send)
        input_box.append(send_btn)

        toolbar_view.add_bottom_bar(input_box)

        # ── CSS ───────────────────────────────────────────────────────────
        self._apply_css()

        # ── File drag-and-drop ────────────────────────────────────────────
        drop_target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_file_drop)
        self.add_controller(drop_target)

    def _apply_css(self):
        css = b"""
        .message-bubble {
            border-radius: 16px;
            max-width: 320px;
        }
        .user-bubble {
            background-color: @accent_bg_color;
            color: @accent_fg_color;
        }
        .assistant-bubble {
            background-color: @card_bg_color;
            color: @card_fg_color;
        }
        .chip {
            border-radius: 999px;
            padding: 2px 12px;
            font-size: 12px;
            border: 1px solid alpha(@accent_color, 0.4);
        }
        .chip:hover {
            background-color: alpha(@accent_color, 0.15);
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # -----------------------------------------------------------------------
    # History persistence
    # -----------------------------------------------------------------------

    def _load_history(self):
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if HISTORY_FILE.exists():
            try:
                self._history = json.loads(HISTORY_FILE.read_text())[-MAX_HISTORY:]
            except Exception:
                self._history = []

    def _save_history(self):
        HISTORY_FILE.write_text(
            json.dumps(self._history[-MAX_HISTORY:], ensure_ascii=False, indent=2)
        )

    # -----------------------------------------------------------------------
    # Message management
    # -----------------------------------------------------------------------

    def _add_user_message(self, text: str):
        bubble = MessageBubble(text, is_user=True)
        self._messages_box.append(bubble)
        self._history.append({"text": text, "is_user": True})
        self._save_history()
        self._scroll_to_bottom()

    def _add_assistant_message(self, text: str):
        bubble = MessageBubble(text, is_user=False)
        self._messages_box.append(bubble)
        self._history.append({"text": text, "is_user": False})
        self._save_history()
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        adj = self._scroll.get_vadjustment()
        GLib.idle_add(lambda: adj.set_value(adj.get_upper() - adj.get_page_size()))

    # -----------------------------------------------------------------------
    # Sending / receiving
    # -----------------------------------------------------------------------

    def _on_send(self, *_):
        text = self._entry.get_text().strip()
        if not text or self._thinking:
            return
        self._entry.set_text("")
        self._send_message(text)

    def _send_message(self, text: str):
        self._add_user_message(text)
        self._thinking = True

        # Show typing indicator
        self._typing = TypingIndicator()
        self._messages_box.append(self._typing)
        self._scroll_to_bottom()

        # Handle quick system commands locally
        lower = text.lower()
        if any(kw in lower for kw in ("open settings", "settings")):
            self._typing.stop()
            self._messages_box.remove(self._typing)
            self._add_assistant_message(
                "Opening **Settings** now."
            )
            self._thinking = False
            subprocess.Popen(["python3", "/usr/local/lib/bobo/desktop/settings/settings.py"])
            return

        if "system info" in lower or "sysinfo" in lower:
            self._typing.stop()
            self._messages_box.remove(self._typing)
            info = self._get_sysinfo()
            self._add_assistant_message(info)
            self._thinking = False
            return

        # Send to AI daemon in background
        threading.Thread(
            target=self._bg_ask,
            args=(text,),
            daemon=True
        ).start()

    def _bg_ask(self, message: str):
        reply = _dbus_ask(message)
        GLib.idle_add(self._on_reply, reply)

    def _on_reply(self, reply: str):
        self._typing.stop()
        self._messages_box.remove(self._typing)
        self._add_assistant_message(reply)
        self._thinking = False

    # -----------------------------------------------------------------------
    # File drag-and-drop — ask about the dropped file
    # -----------------------------------------------------------------------

    def _on_file_drop(self, target, value, x, y):
        if isinstance(value, Gio.File):
            path = value.get_path() or ""
            name = Path(path).name
            question = f"I dropped a file called `{name}`. What is it and how do I open it?"
            self._entry.set_text("")
            self._send_message(question)
            return True
        return False

    # -----------------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------------

    def _on_clear(self, *_):
        # Clear UI
        while True:
            child = self._messages_box.get_first_child()
            if child is None:
                break
            self._messages_box.remove(child)

        self._history = []
        self._save_history()
        _dbus_clear_history()

        self._add_assistant_message(
            "Conversation cleared. How can I help you?"
        )

    def _update_status(self):
        status = _dbus_get_status()
        if "running" in status or "ready" in status or "ollama" in status.lower():
            self._status_btn.set_icon_name("media-record-symbolic")
            self._status_btn.add_css_class("success")
            self._status_btn.set_tooltip_text(f"AI backend: {status}")
        else:
            self._status_btn.set_icon_name("media-record-symbolic")
            self._status_btn.add_css_class("dim-label")
            self._status_btn.set_tooltip_text("AI backend: offline")

    def _get_sysinfo(self) -> str:
        lines = []
        try:
            import platform
            lines.append(f"**OS:** BOBO OS 1.0.0")
            lines.append(f"**Kernel:** {platform.release()}")
            # RAM
            mem = Path("/proc/meminfo")
            if mem.exists():
                meminfo = {l.split(":")[0]: l.split(":")[1].strip()
                           for l in mem.read_text().splitlines() if ":" in l}
                total = int(meminfo.get("MemTotal", "0 kB").split()[0]) // 1024
                avail = int(meminfo.get("MemAvailable", "0 kB").split()[0]) // 1024
                lines.append(f"**RAM:** {avail} MB free / {total} MB total")
            # CPU
            cpuinfo = Path("/proc/cpuinfo")
            if cpuinfo.exists():
                for line in cpuinfo.read_text().splitlines():
                    if line.startswith("model name"):
                        cpu = line.split(":", 1)[1].strip()
                        lines.append(f"**CPU:** {cpu}")
                        break
            # Disk
            result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
            if result.returncode == 0:
                parts = result.stdout.strip().splitlines()[-1].split()
                lines.append(f"**Disk:** {parts[3]} free / {parts[1]} total ({parts[4]} used)")
        except Exception as e:
            lines.append(f"(Could not read full system info: {e})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Slide-in animation helper
# ---------------------------------------------------------------------------

class AssistantApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.AIAssistantUI",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self._win: Optional[AssistantPanel] = None
        self.connect("activate", self._on_activate)

    def _on_activate(self, app):
        if self._win is None:
            self._win = AssistantPanel(application=app)
            self._win.connect("close-request", self._on_close_request)
            self._win.set_opacity(0)
            self._win.present()
            self._animate_in()
        else:
            # Toggle visibility
            if self._win.is_visible():
                self._animate_out()
            else:
                self._win.present()
                self._animate_in()

    def _animate_in(self):
        self._opacity = 0.0
        self._anim_id = GLib.timeout_add(8, self._step_in)

    def _step_in(self):
        self._opacity = min(1.0, self._opacity + 0.06)
        if self._win:
            self._win.set_opacity(self._opacity)
        if self._opacity >= 1.0:
            return False
        return True

    def _animate_out(self):
        self._opacity = 1.0
        self._anim_id = GLib.timeout_add(8, self._step_out)

    def _step_out(self):
        self._opacity = max(0.0, self._opacity - 0.08)
        if self._win:
            self._win.set_opacity(self._opacity)
        if self._opacity <= 0.0:
            self._win.hide()
            return False
        return True

    def _on_close_request(self, win):
        self._animate_out()
        return True  # prevent destroy


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _run_self_test():
    print("=== AI Assistant UI Self-Test ===")
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

    # GTK4 importable
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        ok("GTK4 importable")
    except Exception as e:
        fail(f"GTK4 not importable: {e}")

    # Layer shell importable
    try:
        from gi.repository import GtkLayerShell
        ok("GtkLayerShell importable")
    except Exception:
        print("  WARN  GtkLayerShell not available — will use regular window")

    # D-Bus status call (non-crashing)
    try:
        status = _dbus_get_status()
        ok(f"_dbus_get_status() returned: '{status}'")
    except Exception as e:
        fail(f"_dbus_get_status() raised: {e}")

    # History file creation
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        test_history = [{"text": "test", "is_user": True}]
        HISTORY_FILE.write_text(json.dumps(test_history))
        loaded = json.loads(HISTORY_FILE.read_text())
        assert loaded == test_history
        ok("History file read/write works")
        HISTORY_FILE.unlink()
    except Exception as e:
        fail(f"History file I/O failed: {e}")

    # QUICK_CHIPS list
    if len(QUICK_CHIPS) >= 3 and all(isinstance(c, str) for c in QUICK_CHIPS):
        ok(f"QUICK_CHIPS list has {len(QUICK_CHIPS)} entries")
    else:
        fail("QUICK_CHIPS list malformed")

    print(f"  PASS: {pass_count}  FAIL: {fail_count}")
    print("=================================")
    return fail_count == 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(0 if _run_self_test() else 1)

    app = AssistantApp()
    sys.exit(app.run(sys.argv))
