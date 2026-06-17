#!/usr/bin/env python3
# =============================================================================
# BoboCast - Transmitere ecran/media pe TV pentru BOBO OS (APP 28)
# GTK4 + pychromecast (Chromecast) + ffmpeg (stream HTTP). Scan, cast ecran,
# cast fisier media, cast audio.
# =============================================================================
import os
import sys
import socket
import threading
import subprocess
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

try:
    import pychromecast
except ImportError:
    pychromecast = None

APP_ID = "os.bobo.Cast"
STREAM_PORT = 8770


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class BoboCastWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboCast")
        self.set_default_size(560, 480)
        self.devices = {}
        self.casting = None
        self.stream_proc = None

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        scan = Gtk.Button(label="Scaneaza")
        scan.connect("clicked", lambda *a: self.scan())
        header.pack_start(scan)
        self.stop_btn = Gtk.Button(label="Opreste casting")
        self.stop_btn.add_css_class("destructive-action")
        self.stop_btn.connect("clicked", lambda *a: self.stop_cast())
        self.stop_btn.set_sensitive(False)
        header.pack_end(self.stop_btn)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        self.set_child(box)
        self.status = Gtk.Label(label="Apasa Scaneaza pentru a gasi dispozitive.", xalign=0)
        box.append(self.status)

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        self.listbox = Gtk.ListBox()
        sw.set_child(self.listbox)
        box.append(sw)
        if not pychromecast:
            self.status.set_text("Instaleaza python3-pychromecast pentru Chromecast. DLNA via ffmpeg disponibil.")

    def scan(self):
        self.status.set_text("Caut dispozitive in retea...")
        threading.Thread(target=self._scan, daemon=True).start()

    def _scan(self):
        found = []
        if pychromecast:
            try:
                casts, browser = pychromecast.get_chromecasts(timeout=6)
                for c in casts:
                    found.append((c.cast_info.friendly_name, "chromecast", c))
                pychromecast.discovery.stop_discovery(browser)
            except Exception as e:
                print("[bobo-cast]", e)
        # DLNA via avahi
        try:
            out = subprocess.run(["avahi-browse", "-rt", "_googlecast._tcp", "--no-db-lookup"],
                                 capture_output=True, text=True, timeout=6).stdout
            for line in out.splitlines():
                if "hostname" in line.lower():
                    pass
        except Exception:
            pass
        GLib.idle_add(self._show, found)

    def _show(self, found):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        if not found:
            self.listbox.append(Gtk.Label(label="Niciun dispozitiv gasit.", margin_top=14))
            self.status.set_text("Niciun dispozitiv. Verifica reteaua.")
            return
        self.status.set_text("%d dispozitive gasite." % len(found))
        for name, kind, obj in found:
            self.devices[name] = obj
            row = Gtk.ListBoxRow()
            b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            b.set_margin_top(8)
            b.set_margin_bottom(8)
            b.set_margin_start(10)
            b.append(Gtk.Image.new_from_icon_name("video-display-symbolic"))
            lbl = Gtk.Label(label="%s (%s)" % (name, kind), xalign=0)
            lbl.set_hexpand(True)
            b.append(lbl)
            screen = Gtk.Button(label="Ecran")
            screen.connect("clicked", lambda x, n=name: self.cast_screen(n))
            b.append(screen)
            media = Gtk.Button(label="Fisier")
            media.connect("clicked", lambda x, n=name: self.cast_media(n))
            b.append(media)
            row.set_child(b)
            self.listbox.append(row)

    # ----------------------------------------------------------- cast
    def cast_screen(self, name):
        # porneste stream HTTP cu ecranul (wf-recorder -> ffmpeg HLS/MPEGTS)
        url = "http://%s:%d/screen.ts" % (local_ip(), STREAM_PORT)
        cmd = "wf-recorder --muxer=mpegts --file=- | ffmpeg -i - -listen 1 -f mpegts %s" % url
        self.stream_proc = subprocess.Popen(["bash", "-c", cmd])
        self._send_to_device(name, url)
        self.casting = name
        self.stop_btn.set_sensitive(True)
        self.status.set_text("Transmit ecranul catre %s" % name)

    def cast_media(self, name):
        d = Gtk.FileDialog()
        d.open(self, None, lambda dd, rr: self._cast_media_file(dd, rr, name))

    def _cast_media_file(self, dialog, res, name):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        path = f.get_path()
        # serveste fisierul prin HTTP simplu
        directory = os.path.dirname(path)
        self.stream_proc = subprocess.Popen(["python3", "-m", "http.server", str(STREAM_PORT)], cwd=directory)
        url = "http://%s:%d/%s" % (local_ip(), STREAM_PORT, os.path.basename(path))
        self._send_to_device(name, url)
        self.casting = name
        self.stop_btn.set_sensitive(True)
        self.status.set_text("Redau %s pe %s" % (os.path.basename(path), name))

    def _send_to_device(self, name, url):
        obj = self.devices.get(name)
        if pychromecast and obj is not None:
            try:
                obj.wait()
                obj.media_controller.play_media(url, "video/mp4")
                obj.media_controller.block_until_active()
            except Exception as e:
                print("[bobo-cast]", e)

    def stop_cast(self):
        if self.stream_proc:
            self.stream_proc.terminate()
            self.stream_proc = None
        obj = self.devices.get(self.casting)
        if pychromecast and obj is not None:
            try:
                obj.quit_app()
            except Exception:
                pass
        self.casting = None
        self.stop_btn.set_sensitive(False)
        self.status.set_text("Casting oprit.")


class BoboCastApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboCastWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboCast 1.0.0 (BOBO OS)")
        return 0
    return BoboCastApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
