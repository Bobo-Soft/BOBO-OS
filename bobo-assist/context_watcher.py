"""
BoboAssist context watcher.
Tracks the active Wayland window (via wlrctl / foreign-toplevel) and, when it
is a Bobo Office app, exposes the current document path/title so the assistant
can send relevant context to the model.
"""
import subprocess
import os
import json

STATE = os.path.expanduser("~/.cache/bobo-assist/context.json")


class ContextWatcher:
    def __init__(self):
        os.makedirs(os.path.dirname(STATE), exist_ok=True)

    def active_window(self) -> str:
        """Return the title of the currently focused toplevel (best-effort)."""
        for cmd in (["wlrctl", "toplevel", "find", "state:active"],
                    ["wlrctl", "toplevel", "list"]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout.strip()
                if out:
                    return out.splitlines()[0]
            except Exception:
                continue
        return ""

    def active_app(self) -> str:
        """Map the active window to a Bobo Office app id, or '' if none."""
        title = self.active_window().lower()
        for app in ("write", "calc", "present", "chart", "form", "sign",
                    "translate", "mind", "hub"):
            if "bobo" + app in title or ("bobo" in title and app in title):
                return app
        return ""

    def publish_context(self, app: str, doc_path: str = "", excerpt: str = ""):
        """Store the current editing context for the assistant to read."""
        data = {"app": app, "doc": doc_path, "excerpt": excerpt[:4000]}
        try:
            with open(STATE, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        except Exception:
            pass

    def read_context(self) -> dict:
        try:
            with open(STATE, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {"app": self.active_app(), "doc": "", "excerpt": ""}
