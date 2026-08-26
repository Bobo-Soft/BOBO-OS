"""
BoboPresent slide model + rendering/export.
SlideDeck holds slides (title, body, theme); render_png() rasterizes a slide with
Pillow; exporters produce PDF/PPTX/HTML/MP4. 20 built-in themes + BOBO brand.
"""
import os
import sys

sys.path.insert(0, "/usr/share/bobo-office")

THEMES = {
    "BOBO":       {"bg": (26, 26, 46), "fg": (232, 234, 246), "accent": (74, 158, 255)},
    "Light":      {"bg": (245, 245, 245), "fg": (26, 26, 26), "accent": (0, 102, 204)},
    "Midnight":   {"bg": (10, 10, 20), "fg": (220, 220, 235), "accent": (120, 100, 255)},
    "Forest":     {"bg": (20, 40, 30), "fg": (230, 240, 230), "accent": (80, 200, 120)},
    "Sunset":     {"bg": (40, 20, 30), "fg": (250, 240, 235), "accent": (255, 140, 90)},
    "Ocean":      {"bg": (10, 30, 50), "fg": (225, 240, 250), "accent": (60, 180, 230)},
    "Mono":       {"bg": (24, 24, 24), "fg": (235, 235, 235), "accent": (180, 180, 180)},
    "Paper":      {"bg": (250, 248, 240), "fg": (40, 35, 30), "accent": (190, 120, 60)},
    "Grape":      {"bg": (35, 20, 45), "fg": (240, 230, 250), "accent": (190, 130, 250)},
    "Slate":      {"bg": (30, 34, 42), "fg": (225, 230, 238), "accent": (120, 170, 220)},
    "Coral":      {"bg": (45, 25, 25), "fg": (250, 235, 235), "accent": (255, 110, 110)},
    "Mint":       {"bg": (22, 40, 38), "fg": (228, 245, 242), "accent": (90, 220, 190)},
    "Gold":       {"bg": (35, 30, 15), "fg": (245, 240, 220), "accent": (230, 190, 80)},
    "Steel":      {"bg": (40, 44, 50), "fg": (220, 226, 234), "accent": (150, 165, 180)},
    "Rose":       {"bg": (45, 25, 35), "fg": (250, 235, 242), "accent": (240, 120, 170)},
    "Cyber":      {"bg": (12, 14, 24), "fg": (200, 255, 245), "accent": (0, 230, 200)},
    "Sand":       {"bg": (48, 42, 32), "fg": (245, 238, 225), "accent": (215, 170, 110)},
    "Ink":        {"bg": (18, 22, 30), "fg": (225, 232, 240), "accent": (90, 150, 250)},
    "Berry":      {"bg": (38, 18, 30), "fg": (248, 232, 240), "accent": (220, 90, 140)},
    "Aqua":       {"bg": (16, 36, 42), "fg": (224, 245, 248), "accent": (70, 200, 210)},
}


class Slide:
    def __init__(self, title="Titlu", body="", theme="BOBO"):
        self.title = title
        self.body = body
        self.theme = theme

    def to_dict(self):
        return {"title": self.title, "body": self.body, "theme": self.theme}


class SlideDeck:
    def __init__(self):
        self.slides = [Slide("Prezentare BOBO OS", "Subtitlu")]

    def add(self, after=None):
        s = Slide()
        if after is None:
            self.slides.append(s)
        else:
            self.slides.insert(after + 1, s)
        return s

    def remove(self, idx):
        if 0 <= idx < len(self.slides) and len(self.slides) > 1:
            del self.slides[idx]

    def move(self, idx, delta):
        j = idx + delta
        if 0 <= j < len(self.slides):
            self.slides[idx], self.slides[j] = self.slides[j], self.slides[idx]
            return j
        return idx

    # ------------------------------------------------------------------ render
    def render_png(self, slide, out_path, size=(1280, 720)) -> bool:
        try:
            from PIL import Image, ImageDraw, ImageFont
            th = THEMES.get(slide.theme, THEMES["BOBO"])
            img = Image.new("RGB", size, th["bg"])
            d = ImageDraw.Draw(img)
            try:
                ft = ImageFont.truetype("/usr/share/fonts/truetype/inter/Inter-Bold.ttf", 60)
                fb = ImageFont.truetype("/usr/share/fonts/truetype/inter/Inter-Regular.ttf", 34)
            except Exception:
                ft = ImageFont.load_default(); fb = ImageFont.load_default()
            d.rectangle([0, 0, size[0], 12], fill=th["accent"])
            d.text((80, 120), slide.title, font=ft, fill=th["accent"])
            y = 240
            for line in slide.body.split("\n"):
                d.text((90, y), line, font=fb, fill=th["fg"]); y += 46
            img.save(out_path)
            return True
        except Exception as e:
            print("[render_png] %s" % e); return False

    def render_all_png(self, tmpdir):
        os.makedirs(tmpdir, exist_ok=True)
        paths = []
        for i, s in enumerate(self.slides):
            p = os.path.join(tmpdir, "slide_%03d.png" % i)
            if self.render_png(s, p):
                paths.append(p)
        return paths

    # ------------------------------------------------------------------ export
    def export_pptx(self, out_path) -> bool:
        from shared import file_formats
        return file_formats.write_pptx(out_path, [(s.title, s.body) for s in self.slides])

    def export_pdf(self, out_path) -> bool:
        try:
            from PIL import Image
            tmp = os.path.join(os.path.dirname(out_path) or ".", "_bobo_pres_tmp")
            paths = self.render_all_png(tmp)
            if not paths:
                return False
            imgs = [Image.open(p).convert("RGB") for p in paths]
            imgs[0].save(out_path, save_all=True, append_images=imgs[1:])
            return True
        except Exception as e:
            print("[export_pdf] %s" % e); return False

    def export_html(self, out_path) -> bool:
        try:
            parts = ["<html><head><meta charset='utf-8'><style>",
                     "body{margin:0;font-family:Inter,sans-serif}",
                     ".s{width:100vw;height:100vh;display:flex;flex-direction:column;",
                     "justify-content:center;padding:6vw;box-sizing:border-box;page-break-after:always}",
                     "h1{font-size:3vw}</style></head><body>"]
            for s in self.slides:
                th = THEMES.get(s.theme, THEMES["BOBO"])
                bg = "rgb%s" % (th["bg"],); fg = "rgb%s" % (th["fg"],); ac = "rgb%s" % (th["accent"],)
                body_html = s.body.replace("\n", "<br>")
                parts.append("<div class='s' style='background:%s;color:%s'>"
                             "<h1 style='color:%s'>%s</h1><div>%s</div></div>"
                             % (bg, fg, ac, s.title, body_html))
            parts.append("</body></html>")
            open(out_path, "w", encoding="utf-8").write("".join(parts))
            return True
        except Exception:
            return False

    def export_mp4(self, out_path, seconds=4, transition="fade") -> bool:
        from present import video_exporter
        tmp = os.path.join(os.path.dirname(out_path) or ".", "_bobo_pres_tmp")
        paths = self.render_all_png(tmp)
        return video_exporter.export(paths, out_path, seconds_per_slide=seconds, transition=transition)
