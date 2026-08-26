"""
Base document model for all Bobo Office apps.
Native formats: .bwrite (word), .bcalc (sheet), .bpresent (slides) — JSON on disk.
Handles metadata, modified-tracking, autosave path, and recent-files registry.
"""
import os
import json
import time

RECENT_DIR = os.path.expanduser("~/.local/share/bobo-office")
COMPAT_FORMATS = {
    "write":   [".bwrite", ".docx", ".odt", ".pdf", ".html", ".md", ".txt", ".epub"],
    "calc":    [".bcalc", ".xlsx", ".ods", ".csv", ".json"],
    "present": [".bpresent", ".pptx", ".odp", ".pdf", ".html"],
}


class Document:
    """Generic Bobo Office document (subclassed conceptually by each app)."""

    NATIVE_EXT = ".bdoc"
    KIND = "generic"

    def __init__(self, path=None):
        self.path = path
        self.title = os.path.basename(path) if path else "Untitled"
        self.content = {}          # app-specific structured content
        self.meta = {"created": self._now(), "modified": self._now(), "kind": self.KIND}
        self._modified = False
        if path and os.path.exists(path) and path.endswith(self.NATIVE_EXT):
            self.load_native(path)

    def _now(self):
        return time.strftime("%Y-%m-%dT%H:%M:%S")

    # ------------------------------------------------------------------ state
    def mark_modified(self, flag=True):
        self._modified = flag
        if flag:
            self.meta["modified"] = self._now()

    def is_modified(self):
        return self._modified

    # ------------------------------------------------------------------ native IO
    def to_dict(self):
        return {"title": self.title, "meta": self.meta, "content": self.content}

    def save_native(self, path=None):
        target = path or self.path
        if not target:
            raise ValueError("no path")
        if not target.endswith(self.NATIVE_EXT):
            target += self.NATIVE_EXT
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
        self.path = target
        self.mark_modified(False)
        register_recent(target)
        return target

    def load_native(self, path):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.title = data.get("title", os.path.basename(path))
        self.meta = data.get("meta", self.meta)
        self.content = data.get("content", {})
        self.path = path
        self.mark_modified(False)
        register_recent(path)


def register_recent(path, limit=25):
    """Append a path to the shared recent-files list (deduplicated, newest first)."""
    os.makedirs(RECENT_DIR, exist_ok=True)
    f = os.path.join(RECENT_DIR, "recent.json")
    try:
        with open(f) as fh:
            items = json.load(fh)
    except Exception:
        items = []
    path = os.path.abspath(path)
    if path in items:
        items.remove(path)
    items.insert(0, path)
    items = items[:limit]
    with open(f, "w") as fh:
        json.dump(items, fh)


def recent_files():
    f = os.path.join(RECENT_DIR, "recent.json")
    try:
        with open(f) as fh:
            return [p for p in json.load(fh) if os.path.exists(p)]
    except Exception:
        return []
