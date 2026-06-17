#!/usr/bin/env python3
"""
BOBO OS — AI Assistant Daemon (Phase 8.3)
E:\BOBO-OS\ai-assistant\assistant-daemon.py

Background service for the BOBO OS integrated AI assistant.
- D-Bus interface: os.bobo.AIAssistant (method: Ask(question) → answer)
- Connects to local Ollama or cloud API based on config
- Proactive: monitors system logs for errors, offers help automatically
- Responds in user's system locale
"""

import os
import sys
import json
import time
import logging
import subprocess
import threading
from pathlib import Path

try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

LOG_PATH = Path("/var/log/bobo-ai-assistant.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AIAssistant] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("ai")

# ── Config ────────────────────────────────────────────────────────────────────
BOBO_CONFIG = Path("/etc/bobo-os.conf")

def get_config(key: str, default: str = "") -> str:
    if BOBO_CONFIG.exists():
        for line in BOBO_CONFIG.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"\'')
    return default


AI_BACKEND   = get_config("AI_BACKEND", "ollama")
OLLAMA_MODEL = get_config("AI_OLLAMA_MODEL", "llama3")
CLOUD_MODEL  = get_config("AI_CLOUD_MODEL", "claude-haiku-4-5-20251001")
SYSTEM_LOCALE = os.environ.get("LANG", "en_US").split(".")[0].replace("_", "-")

# Conversation history (in-memory; cleared on daemon restart)
_conversation: list[dict] = []
_lock = threading.Lock()

SYSTEM_PROMPT = f"""You are the BOBO OS built-in assistant.
BOBO OS is a modern, ultra-lightweight Linux-based desktop operating system.
You help users with:
- Using BOBO OS settings and features
- Troubleshooting problems (translate technical errors to plain language)
- Installing and running apps via NovaStore
- Understanding how Windows, macOS, iOS, and Android apps work on BOBO OS
- General computer questions

Always respond in the user's language (detected locale: {SYSTEM_LOCALE}).
Keep answers concise and friendly. Never show terminal commands unless the user asks.
If you don't know something, say so and suggest where the user can get help."""


# ── Backend: Ollama (local LLM) ────────────────────────────────────────────────

def ask_ollama(question: str, history: list[dict]) -> str:
    if not HTTPX_AVAILABLE:
        return "AI assistant requires the httpx library. Install it with: pip3 install httpx"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-10:])  # last 10 turns for context
    messages.append({"role": "user", "content": question})

    try:
        resp = httpx.post(
            "http://127.0.0.1:11434/api/chat",
            json={
                "model":    OLLAMA_MODEL,
                "messages": messages,
                "stream":   False,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except httpx.ConnectError:
        return ("The local AI model is not running. "
                "Start it with: ollama serve\n"
                "Or switch to cloud AI in Settings → System → AI Assistant.")
    except Exception as e:
        log.error("Ollama error: %s", e)
        return f"Could not get a response from the AI: {e}"


# ── Backend: Claude API (cloud) ────────────────────────────────────────────────

def ask_claude(question: str, history: list[dict]) -> str:
    if not HTTPX_AVAILABLE:
        return "AI assistant requires the httpx library."

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ("Cloud AI requires an Anthropic API key. "
                "Set it in Settings → System → AI Assistant → Configure.")

    messages = list(history[-10:])
    messages.append({"role": "user", "content": question})

    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      CLOUD_MODEL,
                "max_tokens": 1024,
                "system":     SYSTEM_PROMPT,
                "messages":   messages,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
    except Exception as e:
        log.error("Claude API error: %s", e)
        return f"Could not reach the cloud AI service: {e}"


# ── Core ask function ─────────────────────────────────────────────────────────

def ask(question: str) -> str:
    """Ask the configured AI backend and return the response string."""
    with _lock:
        history = list(_conversation)

    if AI_BACKEND == "cloud":
        answer = ask_claude(question, history)
    else:
        answer = ask_ollama(question, history)

    with _lock:
        _conversation.append({"role": "user",      "content": question})
        _conversation.append({"role": "assistant",  "content": answer})
        # Keep last 20 turns to avoid unbounded growth
        if len(_conversation) > 40:
            del _conversation[:2]

    return answer


# ── Proactive error monitoring ────────────────────────────────────────────────

def _monitor_logs():
    """Watch system logs for errors and offer proactive help."""
    watch_logs = [
        "/var/log/novalayer.log",
        "/var/log/bobo-drivers.log",
        "/var/log/bobo-updates.log",
    ]

    seen_errors: set[str] = set()

    while True:
        time.sleep(30)
        for log_path in watch_logs:
            p = Path(log_path)
            if not p.exists():
                continue
            try:
                lines = p.read_text(errors="replace").splitlines()[-20:]
                for line in lines:
                    if "FAIL" in line or "ERROR" in line or "error" in line.lower():
                        if line not in seen_errors:
                            seen_errors.add(line)
                            _notify_error(line, log_path)
            except Exception:
                pass


def _notify_error(error_line: str, source_log: str):
    """Proactively send a notification offering AI help for an error."""
    component = Path(source_log).stem.replace("bobo-", "")
    try:
        subprocess.Popen([
            "notify-send",
            "--icon", "dialog-warning",
            "--app-name", "BOBO OS Assistant",
            f"Something went wrong with {component}",
            "The AI assistant can help. Press Win+A to get help.",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass

    log.info("Proactive alert triggered for: %s", error_line[:80])


# ── D-Bus service ─────────────────────────────────────────────────────────────

DBUS_BUS_NAME  = "os.bobo.AIAssistant"
DBUS_OBJ_PATH  = "/os/bobo/AIAssistant"
DBUS_INTERFACE = "os.bobo.AIAssistant"


class AIAssistant_DBusService(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(bus, DBUS_OBJ_PATH)

    @dbus.service.method(DBUS_INTERFACE, in_signature="s", out_signature="s")
    def Ask(self, question: str) -> str:
        log.info("D-Bus Ask: %s", question[:100])
        return ask(str(question))

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="")
    def ClearHistory(self):
        with _lock:
            _conversation.clear()
        log.info("Conversation history cleared.")

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="s")
    def GetStatus(self) -> str:
        return json.dumps({
            "backend": AI_BACKEND,
            "model": OLLAMA_MODEL if AI_BACKEND == "ollama" else CLOUD_MODEL,
            "history_turns": len(_conversation) // 2,
        })


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("AI Assistant daemon starting (backend=%s, model=%s).",
             AI_BACKEND, OLLAMA_MODEL if AI_BACKEND == "ollama" else CLOUD_MODEL)

    # Start proactive log monitor
    threading.Thread(target=_monitor_logs, daemon=True).start()

    if not DBUS_AVAILABLE:
        log.warning("D-Bus not available. Running in CLI mode.")
        for line in sys.stdin:
            q = line.strip()
            if q:
                print(ask(q))
        return

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    session_bus = dbus.SessionBus()
    dbus.service.BusName(DBUS_BUS_NAME, bus=session_bus)
    AIAssistant_DBusService(session_bus)

    log.info("D-Bus service registered: %s", DBUS_BUS_NAME)
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        log.info("AI Assistant daemon stopped.")


if __name__ == "__main__":
    main()
