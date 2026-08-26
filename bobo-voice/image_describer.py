"""
BoboVoice image describer.
Describes an image with a local vision model (LLaVA via Ollama) when available,
falling back to Tesseract OCR (reads any text) and basic image facts. Can grab
the clipboard image or a fresh screenshot (grim) to describe the current screen.
"""
import os
import base64
import json
import subprocess
import tempfile
import urllib.request

OLLAMA = os.environ.get("BOBO_OLLAMA", "http://127.0.0.1:11434")


def _llava(path: str, prompt="Descrie pe scurt această imagine în română.") -> str:
    try:
        b64 = base64.b64encode(open(path, "rb").read()).decode()
        payload = {"model": "llava:7b", "prompt": prompt, "images": [b64], "stream": False}
        req = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=90).read()).get("response", "").strip()
    except Exception:
        return ""


def _ocr(path: str) -> str:
    try:
        r = subprocess.run(["tesseract", path, "stdout", "-l", "ron+eng"],
                           capture_output=True, text=True, timeout=40)
        return r.stdout.strip()
    except Exception:
        return ""


def describe_image_file(path: str) -> str:
    if not os.path.exists(path):
        return "Fișierul nu există."
    desc = _llava(path)
    if desc:
        return desc
    text = _ocr(path)
    if text:
        return "Nu am un model vizual, dar în imagine scrie: " + text[:400]
    try:
        from PIL import Image
        im = Image.open(path)
        return "Imagine %dx%d, format %s. (Instalează LLaVA pentru descriere detaliată.)" % (im.width, im.height, im.format)
    except Exception:
        return "Nu pot analiza imaginea."


def _grab_screen() -> str:
    out = tempfile.mktemp(suffix=".png")
    try:
        subprocess.run(["grim", out], timeout=10, check=True)
        return out
    except Exception:
        return ""


def _clipboard_image() -> str:
    out = tempfile.mktemp(suffix=".png")
    try:
        with open(out, "wb") as fh:
            p = subprocess.run(["wl-paste", "-t", "image/png"], stdout=fh, timeout=5)
        return out if os.path.getsize(out) > 100 else ""
    except Exception:
        return ""


def describe_clipboard_or_screen() -> str:
    path = _clipboard_image() or _grab_screen()
    if not path:
        return "Nu am putut prelua ecranul sau clipboard-ul."
    return describe_image_file(path)
