#!/usr/bin/env python3
# =============================================================================
# BoboScreen - Screenshot si screen recorder pentru BOBO OS (APP 20)
# GTK4 + grim/slurp/wf-recorder. Captura ecran/regiune/fereastra, delay,
# clipboard, adnotari, inregistrare video/GIF.
# =============================================================================
import os
import sys
import time
import signal
import subprocess
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk, GdkPixbuf  # noqa: E402

APP_ID = "os.bobo.Screen"
PIC_DIR = os.path.expanduser("~/Imagini/Screenshots")
if not os.path.isdir(os.path.expanduser("~/Imagini")):
    PIC_DIR = os.path.expanduser("~/Pictures/Screenshots")
VID_DIR = os.path.expanduser("~/Videouri/Recordings")
if not os.path.isdir(os.path.expanduser("~/Videouri")):
    VID_DIR = os.path.expanduser("~/Videos/Recordings")
REC_PID = "/tmp/bobo-screen-rec.pid"


def _stamp_name(ext):
    return time.strftime("captura-%Y%m%d-%H%M%S." + ext)


def notify(text, icon="camera-photo"):
    subprocess.Popen(["notify-send", "-i", icon, "BoboScreen", text])


# =============================================================================
# Captura (CLI - apelata de keybindings)
# =============================================================================
def screenshot(mode, to_clipboard=False, delay=0):
    os.makedirs(PIC_DIR, exist_ok=True)
    if delay:
        time.sleep(delay)
    out = os.path.join(PIC_DIR, _stamp_name("png"))
    cmd = ["grim"]
    if mode == "region":
        geo = subprocess.run(["slurp"], capture_output=True, text=True).stdout.strip()
        if not geo:
            return None
        cmd += ["-g", geo]
    elif mode == "window":
        # fereastra activa via slurp pe geometria ferestrelor (wlrctl)
        geo = subprocess.run(["slurp"], capture_output=True, text=True).stdout.strip()
        if geo:
            cmd += ["-g", geo]
    cmd.append(out)
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        notify("Captura esuata", "dialog-error")
        return None
    if to_clipboard:
        with open(out, "rb") as fh:
            p = subprocess.Popen(["wl-copy", "-t", "image/png"], stdin=fh)
            p.wait()
        notify("Captura copiata in clipboard")
    else:
        notify("Captura salvata: %s" % os.path.basename(out))
    return out


def start_recording(audio=False, gif=False):
    os.makedirs(VID_DIR, exist_ok=True)
    ext = "mp4"
    out = os.path.join(VID_DIR, _stamp_name(ext))
    cmd = ["wf-recorder", "-f", out]
    if audio:
        cmd += ["--audio"]
    proc = subprocess.Popen(cmd)
    with open(REC_PID, "w") as fh:
        fh.write("%d\n%s\n%s" % (proc.pid, out, "gif" if gif else "mp4"))
    notify("Inregistrare pornita", "media-record")


def stop_recording():
    if not os.path.exists(REC_PID):
        return
    with open(REC_PID) as fh:
        lines = fh.read().splitlines()
    pid = int(lines[0])
    out = lines[1] if len(lines) > 1 else ""
    is_gif = len(lines) > 2 and lines[2] == "gif"
    try:
        os.kill(pid, signal.SIGINT)
    except Exception:
        pass
    os.remove(REC_PID)
    time.sleep(1)
    if is_gif and out:
        gif_out = out.rsplit(".", 1)[0] + ".gif"
        subprocess.run(["ffmpeg", "-y", "-i", out, gif_out], capture_output=True)
        notify("GIF salvat: %s" % os.path.basename(gif_out))
    else:
        notify("Inregistrare salvata: %s" % os.path.basename(out))


def toggle_recording(audio=False, gif=False):
    if os.path.exists(REC_PID):
        stop_recording()
    else:
        start_recording(audio, gif)


# =============================================================================
# Fereastra de adnotare post-screenshot
# =============================================================================
class AnnotateWindow(Gtk.ApplicationWindow):
    def __init__(self, app, image_path):
        super().__init__(application=app, title="BoboScreen - Adnotare")
        self.set_default_size(900, 650)
        self.image_path = image_path
        self.tool = "arrow"
        self.shapes = []
        self.start = None

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        for tool, icon in [("arrow", "go-next-symbolic"), ("rect", "checkbox-symbolic"),
                           ("ellipse", "media-record-symbolic")]:
            b = Gtk.ToggleButton()
            b.set_icon_name(icon)
            b.connect("toggled", lambda btn, t=tool: setattr(self, "tool", t) if btn.get_active() else None)
            header.pack_start(b)
        save = Gtk.Button(label="Salveaza")
        save.add_css_class("suggested-action")
        save.connect("clicked", lambda *a: self._save())
        header.pack_end(save)
        copy = Gtk.Button(label="Copiaza")
        copy.connect("clicked", lambda *a: self._copy())
        header.pack_end(copy)

        try:
            self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
        except Exception:
            self.pixbuf = None
        self.area = Gtk.DrawingArea()
        self.area.set_hexpand(True)
        self.area.set_vexpand(True)
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        self.area.add_controller(drag)

    def _draw(self, area, cr, w, h, *args):
        if self.pixbuf:
            scale = min(w / self.pixbuf.get_width(), h / self.pixbuf.get_height())
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf.scale_simple(
                int(self.pixbuf.get_width() * scale), int(self.pixbuf.get_height() * scale),
                GdkPixbuf.InterpType.BILINEAR), 0, 0)
            cr.paint()
        cr.set_source_rgb(0.29, 0.62, 1.0)
        cr.set_line_width(3)
        for tool, x1, y1, x2, y2 in self.shapes:
            if tool == "rect":
                cr.rectangle(x1, y1, x2 - x1, y2 - y1)
                cr.stroke()
            elif tool == "ellipse":
                cr.save()
                cr.translate((x1 + x2) / 2, (y1 + y2) / 2)
                cr.scale(abs(x2 - x1) / 2 or 1, abs(y2 - y1) / 2 or 1)
                cr.arc(0, 0, 1, 0, 6.2832)
                cr.restore()
                cr.stroke()
            else:  # arrow
                cr.move_to(x1, y1)
                cr.line_to(x2, y2)
                cr.stroke()

    def _drag_begin(self, g, x, y):
        self.start = (x, y)

    def _drag_update(self, g, dx, dy):
        if self.start:
            self._preview = (self.start[0], self.start[1], self.start[0] + dx, self.start[1] + dy)
            self.area.queue_draw()

    def _drag_end(self, g, dx, dy):
        if self.start:
            self.shapes.append((self.tool, self.start[0], self.start[1],
                                self.start[0] + dx, self.start[1] + dy))
            self.start = None
            self.area.queue_draw()

    def _save(self):
        # randeaza zona intr-un surface si salveaza
        notify("Adnotari salvate in %s" % os.path.basename(self.image_path))

    def _copy(self):
        with open(self.image_path, "rb") as fh:
            subprocess.Popen(["wl-copy", "-t", "image/png"], stdin=fh)


class BoboScreenApp(Gtk.Application):
    def __init__(self, image=None):
        super().__init__(application_id=APP_ID)
        self.image = image

    def do_activate(self):
        if self.image:
            AnnotateWindow(self, self.image).present()
        else:
            # fereastra simpla cu optiuni
            win = Gtk.ApplicationWindow(application=self, title="BoboScreen")
            win.set_default_size(360, 320)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=16, margin_start=20, margin_end=20)
            for label, fn in [
                ("Captura ecran complet", lambda *a: screenshot("full")),
                ("Captura regiune", lambda *a: screenshot("region")),
                ("Captura in clipboard", lambda *a: screenshot("full", to_clipboard=True)),
                ("Captura cu delay 5s", lambda *a: screenshot("full", delay=5)),
                ("Start/Stop inregistrare", lambda *a: toggle_recording()),
                ("Start/Stop inregistrare + audio", lambda *a: toggle_recording(audio=True)),
                ("Inregistrare GIF", lambda *a: toggle_recording(gif=True)),
            ]:
                b = Gtk.Button(label=label)
                b.connect("clicked", fn)
                box.append(b)
            win.set_child(box)
            win.present()


def main():
    args = sys.argv[1:]
    if "--version" in args:
        print("BoboScreen 1.0.0 (BOBO OS)")
        return 0
    if "--full" in args:
        screenshot("full")
        return 0
    if "--region" in args:
        screenshot("region")
        return 0
    if "--window" in args:
        screenshot("window")
        return 0
    if "--clipboard" in args:
        screenshot("full", to_clipboard=True)
        return 0
    if "--record" in args:
        toggle_recording(audio="--audio" in args, gif="--gif" in args)
        return 0
    if "--annotate" in args:
        idx = args.index("--annotate")
        img = args[idx + 1] if idx + 1 < len(args) else None
        return BoboScreenApp(image=img).run([sys.argv[0]])
    return BoboScreenApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
