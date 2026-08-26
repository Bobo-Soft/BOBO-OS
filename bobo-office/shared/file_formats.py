"""
Import/export helpers for Bobo Office.
Reads/writes common office formats via python-docx, openpyxl, python-pptx,
PyMuPDF (fitz) and pandoc. Every function degrades gracefully if a backend
library is missing (returns a clear message instead of raising).
"""
import os
import subprocess
import csv


# ---------------------------------------------------------------- text / docs
def read_text(path: str) -> str:
    """Extract plain text from txt/md/html/docx/odt/pdf."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".markdown", ".html", ".htm", ".csv", ".json"):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    if ext == ".docx":
        try:
            import docx
            return "\n".join(p.text for p in docx.Document(path).paragraphs)
        except Exception as e:
            return "[docx read error: %s]" % e
    if ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(path)
            return "\n".join(page.get_text() for page in doc)
        except Exception as e:
            return "[pdf read error: %s]" % e
    if ext in (".odt", ".rtf", ".epub"):
        return _pandoc_to("markdown", path)
    return "[unsupported format: %s]" % ext


def write_docx(path: str, paragraphs) -> bool:
    try:
        import docx
        d = docx.Document()
        for p in paragraphs:
            d.add_paragraph(p)
        d.save(path)
        return True
    except Exception as e:
        print("[write_docx] %s" % e)
        return False


def write_pdf_from_text(path: str, text: str) -> bool:
    """Render plain text to a PDF via reportlab (fallback: pandoc)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
        c = canvas.Canvas(path, pagesize=A4)
        w, h = A4
        y = h - 2 * cm
        for line in text.split("\n"):
            if y < 2 * cm:
                c.showPage(); y = h - 2 * cm
            c.drawString(2 * cm, y, line[:110])
            y -= 14
        c.save()
        return True
    except Exception:
        return _pandoc_from_text(text, path)


def export_via_pandoc(src_text: str, out_path: str, fmt: str = None) -> bool:
    return _pandoc_from_text(src_text, out_path, fmt)


def _pandoc_to(fmt: str, path: str) -> str:
    try:
        r = subprocess.run(["pandoc", "-t", fmt, path], capture_output=True, text=True, timeout=60)
        return r.stdout or ("[pandoc: %s]" % r.stderr[:200])
    except Exception as e:
        return "[pandoc unavailable: %s]" % e


def _pandoc_from_text(text: str, out_path: str, fmt: str = None) -> bool:
    try:
        cmd = ["pandoc", "-f", "markdown", "-o", out_path]
        p = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=120)
        return p.returncode == 0 and os.path.exists(out_path)
    except Exception:
        return False


# ---------------------------------------------------------------- spreadsheets
def read_xlsx(path: str):
    """Return list-of-rows for the active sheet."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        return [[c.value for c in row] for row in ws.iter_rows()]
    except Exception as e:
        return [["[xlsx read error: %s]" % e]]


def write_xlsx(path: str, rows) -> bool:
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        for r in rows:
            ws.append(list(r))
        wb.save(path)
        return True
    except Exception as e:
        print("[write_xlsx] %s" % e)
        return False


def read_csv(path: str):
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.reader(fh))


def write_csv(path: str, rows) -> bool:
    try:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(rows)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- presentations
def read_pptx_texts(path: str):
    """Return list of slide texts."""
    try:
        from pptx import Presentation
        prs = Presentation(path)
        slides = []
        for s in prs.slides:
            parts = [sh.text for sh in s.shapes if sh.has_text_frame]
            slides.append("\n".join(parts))
        return slides
    except Exception as e:
        return ["[pptx read error: %s]" % e]


def write_pptx(path: str, slides) -> bool:
    """slides = list of (title, body) tuples."""
    try:
        from pptx import Presentation
        from pptx.util import Inches
        prs = Presentation()
        layout = prs.slide_layouts[1]
        for title, body in slides:
            s = prs.slides.add_slide(layout)
            s.shapes.title.text = title
            if len(s.placeholders) > 1:
                s.placeholders[1].text = body
        prs.save(path)
        return True
    except Exception as e:
        print("[write_pptx] %s" % e)
        return False
