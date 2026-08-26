"""
BoboVoice document reader — reads PDF/DOCX/ODT/TXT/HTML/MD aloud with natural
paragraph splitting and voice navigation (next / previous / repeat / jump).
Reuses Bobo Office file_formats when present; otherwise extracts text directly.
"""
import os
import re
import sys

sys.path.insert(0, "/usr/share/bobo-office")


def _extract(path: str) -> str:
    try:
        from shared import file_formats
        return file_formats.read_text(path)
    except Exception:
        pass
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".html", ".htm"):
        return open(path, encoding="utf-8", errors="replace").read()
    if ext == ".pdf":
        try:
            import fitz
            return "\n".join(p.get_text() for p in fitz.open(path))
        except Exception:
            return ""
    if ext == ".docx":
        try:
            import docx
            return "\n".join(p.text for p in docx.Document(path).paragraphs)
        except Exception:
            return ""
    return ""


class DocumentReader:
    def __init__(self, tts):
        self.tts = tts
        self.paras = []
        self.idx = 0
        self.reading = False

    def load(self, path: str) -> bool:
        text = _extract(path)
        if "<" in text and ">" in text:
            text = re.sub(r"<[^>]+>", "", text)
        # natural paragraph split
        self.paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not self.paras:
            self.paras = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        self.idx = 0
        return bool(self.paras)

    def read_all(self):
        self.reading = True
        while self.reading and self.idx < len(self.paras):
            self.tts.speak(self.paras[self.idx], block=True)
            self.idx += 1

    def read_current(self):
        if 0 <= self.idx < len(self.paras):
            self.tts.speak(self.paras[self.idx])

    def next(self):
        self.idx = min(self.idx + 1, len(self.paras) - 1); self.read_current()

    def prev(self):
        self.idx = max(self.idx - 1, 0); self.read_current()

    def stop(self):
        self.reading = False
        self.tts.stop()

    def progress(self):
        return "Paragraful %d din %d" % (self.idx + 1, len(self.paras)) if self.paras else "Niciun document"
