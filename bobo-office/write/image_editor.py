"""
BoboWrite image tools — local processing with Pillow + ImageMagick + Tesseract.
Crop, resize, rotate, filters, OCR, and simple matplotlib chart generation.
All offline.
"""
import os
import subprocess


def _pil():
    from PIL import Image, ImageFilter, ImageOps
    return Image, ImageFilter, ImageOps


def resize(path: str, out: str, width: int, height: int) -> bool:
    try:
        Image, _, _ = _pil()
        Image.open(path).resize((width, height)).save(out)
        return True
    except Exception as e:
        print("[resize] %s" % e); return False


def crop(path: str, out: str, box) -> bool:
    try:
        Image, _, _ = _pil()
        Image.open(path).crop(tuple(box)).save(out)
        return True
    except Exception:
        return False


def rotate(path: str, out: str, degrees: int) -> bool:
    try:
        Image, _, _ = _pil()
        Image.open(path).rotate(-degrees, expand=True).save(out)
        return True
    except Exception:
        return False


def apply_filter(path: str, out: str, name: str) -> bool:
    """name in {grayscale, blur, sharpen, contour, invert}."""
    try:
        Image, ImageFilter, ImageOps = _pil()
        im = Image.open(path).convert("RGB")
        if name == "grayscale":
            im = ImageOps.grayscale(im)
        elif name == "blur":
            im = im.filter(ImageFilter.GaussianBlur(3))
        elif name == "sharpen":
            im = im.filter(ImageFilter.SHARPEN)
        elif name == "contour":
            im = im.filter(ImageFilter.CONTOUR)
        elif name == "invert":
            im = ImageOps.invert(im)
        im.save(out)
        return True
    except Exception as e:
        print("[filter] %s" % e); return False


def ocr(path: str, lang: str = "ron+eng") -> str:
    """Extract text from an image via Tesseract (pytesseract, else CLI)."""
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(path), lang=lang)
    except Exception:
        try:
            r = subprocess.run(["tesseract", path, "stdout", "-l", lang],
                               capture_output=True, text=True, timeout=60)
            return r.stdout
        except Exception as e:
            return "[OCR indisponibil: %s]" % e


def make_chart(kind: str, labels, values, out: str) -> bool:
    """Generate a simple chart (bar/line/pie) to a PNG via matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 4))
        if kind == "pie":
            ax.pie(values, labels=labels, autopct="%1.0f%%")
        elif kind == "line":
            ax.plot(labels, values, marker="o", color="#4a9eff")
        else:
            ax.bar(labels, values, color="#4a9eff")
        fig.tight_layout(); fig.savefig(out, dpi=110); plt.close(fig)
        return True
    except Exception as e:
        print("[chart] %s" % e); return False
