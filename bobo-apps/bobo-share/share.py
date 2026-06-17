#!/usr/bin/env python3
# =============================================================================
# BoboShare - Transfer de fisiere in retea locala pentru BOBO OS (APP 23)
# GTK4 + Zeroconf (descoperire) + HTTP (transfer). Trimite/primeste fisiere,
# QR code pentru descarcare de pe telefon.
# =============================================================================
import os
import sys
import socket
import threading
import http.server
import socketserver
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, GdkPixbuf  # noqa: E402

try:
    from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser
except ImportError:
    Zeroconf = None

try:
    import qrcode
except ImportError:
    qrcode = None

APP_ID = "os.bobo.Share"
SERVICE_TYPE = "_boboshare._tcp.local."
PORT = 8769
RECV_DIR = os.path.expanduser("~/Downloads/BoboShare")


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ShareHandler(http.server.SimpleHTTPRequestHandler):
    """Serveste fisierul partajat curent; accepta upload prin POST."""
    shared_file = None

    def do_GET(self):
        if self.shared_file and os.path.exists(self.shared_file):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition",
                             'attachment; filename="%s"' % os.path.basename(self.shared_file))
            self.end_headers()
            with open(self.shared_file, "rb") as fh:
                self.wfile.write(fh.read())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        os.makedirs(RECV_DIR, exist_ok=True)
        length = int(self.headers.get("Content-Length", 0))
        name = self.headers.get("X-Filename", "fisier-primit")
        dest = os.path.join(RECV_DIR, os.path.basename(name))
        with open(dest, "wb") as fh:
            fh.write(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


class BoboShareWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboShare")
        self.set_default_size(560, 540)
        self.peers = {}
        self.httpd = None

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        send = Gtk.Button(label="Trimite fisier")
        send.add_css_class("suggested-action")
        send.connect("clicked", lambda *a: self.send_dialog())
        header.pack_start(send)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        self.set_child(box)

        self.info = Gtk.Label(xalign=0)
        self.info.set_markup("Acest dispozitiv: <b>%s</b> (%s)" % (socket.gethostname(), local_ip()))
        box.append(self.info)
        box.append(Gtk.Label(label="Dispozitive descoperite in retea:", xalign=0))

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        self.listbox = Gtk.ListBox()
        sw.set_child(self.listbox)
        box.append(sw)

        # QR pentru descarcare de pe telefon
        self.qr_image = Gtk.Image()
        self.qr_image.set_pixel_size(180)
        box.append(self.qr_image)
        self.qr_label = Gtk.Label(xalign=0)
        box.append(self.qr_label)

        self._start_receiver()
        self._start_discovery()

    # ----------------------------------------------------------- receiver
    def _start_receiver(self):
        def serve():
            try:
                self.httpd = socketserver.TCPServer(("0.0.0.0", PORT), ShareHandler)
                self.httpd.serve_forever()
            except Exception as e:
                print("[bobo-share] server:", e)
        threading.Thread(target=serve, daemon=True).start()
        # inregistreaza serviciul Zeroconf
        if Zeroconf:
            try:
                self.zc = Zeroconf()
                info = ServiceInfo(
                    SERVICE_TYPE, "%s.%s" % (socket.gethostname(), SERVICE_TYPE),
                    addresses=[socket.inet_aton(local_ip())], port=PORT,
                    properties={"host": socket.gethostname()})
                self.zc.register_service(info)
            except Exception as e:
                print("[bobo-share] zeroconf:", e)

    # ----------------------------------------------------------- discovery
    def _start_discovery(self):
        if not Zeroconf:
            self.qr_label.set_text("Instaleaza python3-zeroconf pentru descoperire automata.")
            return

        class Listener:
            def __init__(self, win):
                self.win = win

            def add_service(self, zc, type_, name):
                info = zc.get_service_info(type_, name)
                if info and info.addresses:
                    ip = socket.inet_ntoa(info.addresses[0])
                    host = name.split(".")[0]
                    if ip != local_ip():
                        GLib.idle_add(self.win._add_peer, host, ip)

            def remove_service(self, zc, type_, name):
                pass

            def update_service(self, zc, type_, name):
                pass

        ServiceBrowser(self.zc, SERVICE_TYPE, Listener(self))

    def _add_peer(self, host, ip):
        if ip in self.peers:
            return
        self.peers[ip] = host
        row = Gtk.ListBoxRow()
        b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        b.set_margin_top(6)
        b.set_margin_bottom(6)
        b.set_margin_start(8)
        b.append(Gtk.Image.new_from_icon_name("computer-symbolic"))
        lbl = Gtk.Label(label="%s (%s)" % (host, ip), xalign=0)
        lbl.set_hexpand(True)
        b.append(lbl)
        send = Gtk.Button(label="Trimite")
        send.connect("clicked", lambda x, target=ip: self.send_to(target))
        b.append(send)
        row.set_child(b)
        self.listbox.append(row)

    # ----------------------------------------------------------- send
    def send_dialog(self):
        d = Gtk.FileDialog()
        d.open(self, None, self._send_pick)

    def _send_pick(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if f:
            ShareHandler.shared_file = f.get_path()
            self._show_qr(f.get_path())

    def send_to(self, ip):
        d = Gtk.FileDialog()
        d.open(self, None, lambda dd, rr: self._do_send(dd, rr, ip))

    def _do_send(self, dialog, res, ip):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        path = f.get_path()

        def upload():
            try:
                import urllib.request
                with open(path, "rb") as fh:
                    req = urllib.request.Request("http://%s:%d/" % (ip, PORT), data=fh.read(),
                                                 headers={"X-Filename": os.path.basename(path)})
                    urllib.request.urlopen(req, timeout=60)
                GLib.idle_add(self._notify, "Trimis catre %s" % ip)
            except Exception as e:
                GLib.idle_add(self._notify, "Trimitere esuata: %s" % e)
        threading.Thread(target=upload, daemon=True).start()

    def _show_qr(self, path):
        url = "http://%s:%d/" % (local_ip(), PORT)
        self.qr_label.set_markup("Descarca de pe telefon: <tt>%s</tt>\nFisier: %s" % (url, os.path.basename(path)))
        if qrcode:
            qr_path = "/tmp/bobo-share-qr.png"
            img = qrcode.make(url)
            img.save(qr_path)
            self.qr_image.set_from_file(qr_path)

    def _notify(self, text):
        GLib.spawn_command_line_async("notify-send 'BoboShare' '%s'" % text.replace("'", ""))


class BoboShareApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboShareWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboShare 1.0.0 (BOBO OS)")
        return 0
    return BoboShareApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
