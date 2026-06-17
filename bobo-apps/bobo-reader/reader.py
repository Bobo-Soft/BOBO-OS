#!/usr/bin/env python3
# =============================================================================
# BoboReader - Vizualizator PDF / EPUB / CBZ pentru BOBO OS (APP 05)
# GTK4 + PyMuPDF (fitz). PDF render, EPUB, comic CBZ, cuprins, cautare,
# mod noapte, zoom, remember last page.
# =============================================================================
import os
import sys
import json
import zipfile
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk, GdkPixbuf  # noqa: E402

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

APP_ID = "os.bobo.Reader"
POS_FILE = os.path.expanduser("~/.local/share/bobo-reader/positions.json")


def _load_positions():
    try:
        with open(POS_FILE) as fh:
            return json.load(fh)
    except Exception:
        return {}


class BoboReaderWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboReader")
        self.set_default_size(820, 900)
        self.doc = None
        self.path = None
        self.page_num = 0
        self.zoom = 1.2
        self.night = False
        self.cbz_files = None
        self.positions = _load_positions()

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        open_btn = Gtk.Button.new_from_icon_name("document-open-symbolic")
        open_btn.connect("clicked", lambda *a: self.open_dialog())
        header.pack_start(open_btn)

        prev_btn = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        prev_btn.connect("clicked", lambda *a: self.go(-1))
        next_btn = Gtk.Button.new_from_icon_name("go-next-symbolic")
        next_btn.connect("clicked", lambda *a: self.go(1))
        header.pack_start(prev_btn)
        header.pack_start(next_btn)
        self.page_entry = Gtk.Entry()
        self.page_entry.set_width_chars(6)
        self.page_entry.connect("activate", self._on_page_entry)
        header.pack_start(self.page_entry)

        zin = Gtk.Button.new_from_icon_name("zoom-in-symbolic")
        zin.connect("clicked", lambda *a: self.set_zoom(self.zoom + 0.2))
        zout = Gtk.Button.new_from_icon_name("zoom-out-symbolic")
        zout.connect("clicked", lambda *a: self.set_zoom(self.zoom - 0.2))
        header.pack_end(zin)
        header.pack_end(zout)
        night_btn = Gtk.ToggleButton()
        night_btn.set_icon_name("weather-clear-night-symbolic")
        night_btn.set_tooltip_text("Mod noapte")
        night_btn.connect("toggled", self._on_night)
        header.pack_end(night_btn)
        toc_btn = Gtk.ToggleButton()
        toc_btn.set_icon_name("view-list-symbolic")
        toc_btn.set_tooltip_text("Cuprins")
        toc_btn.connect("toggled", lambda b: self.toc_panel.set_visible(b.get_active()))
        header.pack_end(toc_btn)
        find_btn = Gtk.Button.new_from_icon_name("edit-find-symbolic")
        find_btn.connect("clicked", lambda *a: self._find_dialog())
        header.pack_end(find_btn)

        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(split)
        # cuprins
        self.toc_panel = Gtk.ScrolledWindow()
        self.toc_panel.set_size_request(220, -1)
        self.toc_list = Gtk.ListBox()
        self.toc_list.connect("row-activated", self._on_toc_activated)
        self.toc_panel.set_child(self.toc_list)
        self.toc_panel.set_visible(False)
        split.set_start_child(self.toc_panel)
        split.set_resize_start_child(False)
        # pagina
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_hexpand(True)
        self.scroller.set_vexpand(True)
        self.picture = Gtk.Picture()
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.scroller.set_child(self.picture)
        split.set_end_child(self.scroller)

        # zoom cu Ctrl+scroll
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._on_scroll)
        self.scroller.add_controller(scroll)

        self._install_shortcuts()
        if not fitz:
            self._error("PyMuPDF (fitz) nu este instalat. Ruleaza: pip3 install pymupdf")

    # ----------------------------------------------------------- open
    def open_dialog(self):
        dialog = Gtk.FileDialog()
        dialog.open(self, None, self._open_finished)

    def _open_finished(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if f:
            self.open_file(f.get_path())

    def open_file(self, path):
        self.path = path
        ext = os.path.splitext(path)[1].lower()
        if ext in (".cbz", ".cbr"):
            self._open_cbz(path)
        else:
            if not fitz:
                self._error("PyMuPDF lipseste")
                return
            try:
                self.doc = fitz.open(path)
            except Exception as e:
                self._error("Nu pot deschide: %s" % e)
                return
            self.cbz_files = None
            self._build_toc()
        self.page_num = int(self.positions.get(path, 0))
        self.set_title("BoboReader - " + os.path.basename(path))
        self.render()

    def _open_cbz(self, path):
        try:
            zf = zipfile.ZipFile(path)
            self.cbz_files = sorted(
                [n for n in zf.namelist() if n.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
            )
            self._cbz_zip = zf
            self.doc = None
            self.toc_list.remove_all() if hasattr(self.toc_list, "remove_all") else None
        except Exception as e:
            self._error("CBZ invalid: %s" % e)

    # ----------------------------------------------------------- render
    def render(self):
        if self.cbz_files is not None:
            self._render_cbz()
            return
        if not self.doc:
            return
        total = self.doc.page_count
        self.page_num = max(0, min(self.page_num, total - 1))
        page = self.doc.load_page(self.page_num)
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        data = pix.samples
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            data, GdkPixbuf.Colorspace.RGB, False, 8, pix.width, pix.height, pix.stride
        )
        if self.night:
            pixbuf = self._invert(pixbuf)
        self.picture.set_pixbuf(pixbuf)
        self.page_entry.set_text("%d/%d" % (self.page_num + 1, total))
        if self.path:
            self.positions[self.path] = self.page_num

    def _render_cbz(self):
        total = len(self.cbz_files)
        self.page_num = max(0, min(self.page_num, total - 1))
        name = self.cbz_files[self.page_num]
        loader = GdkPixbuf.PixbufLoader()
        loader.write(self._cbz_zip.read(name))
        loader.close()
        pixbuf = loader.get_pixbuf()
        if self.night:
            pixbuf = self._invert(pixbuf)
        self.picture.set_pixbuf(pixbuf)
        self.page_entry.set_text("%d/%d" % (self.page_num + 1, total))
        if self.path:
            self.positions[self.path] = self.page_num

    def _invert(self, pixbuf):
        # Mod noapte: inverseaza culorile pixbuf-ului
        try:
            import numpy as np
            arr = np.frombuffer(pixbuf.get_pixels(), dtype=np.uint8).copy()
            arr = 255 - arr
            return GdkPixbuf.Pixbuf.new_from_data(
                arr.tobytes(), pixbuf.get_colorspace(), pixbuf.get_has_alpha(),
                pixbuf.get_bits_per_sample(), pixbuf.get_width(), pixbuf.get_height(),
                pixbuf.get_rowstride())
        except Exception:
            return pixbuf

    # ----------------------------------------------------------- nav
    def go(self, delta):
        self.page_num += delta
        self.render()

    def set_zoom(self, z):
        self.zoom = max(0.5, min(4.0, z))
        self.render()

    def _on_page_entry(self, entry):
        try:
            n = int(entry.get_text().split("/")[0]) - 1
            self.page_num = n
            self.render()
        except Exception:
            pass

    def _on_scroll(self, ctrl, dx, dy):
        state = ctrl.get_current_event_state()
        if state & Gdk.ModifierType.CONTROL_MASK:
            self.set_zoom(self.zoom - 0.1 if dy > 0 else self.zoom + 0.1)
            return True
        return False

    def _on_night(self, btn):
        self.night = btn.get_active()
        self.render()

    # ----------------------------------------------------------- TOC
    def _build_toc(self):
        child = self.toc_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.toc_list.remove(child)
            child = nxt
        if not self.doc:
            return
        try:
            toc = self.doc.get_toc()
        except Exception:
            toc = []
        for level, title, page in toc:
            row = Gtk.ListBoxRow()
            lbl = Gtk.Label(label=("  " * (level - 1)) + title, xalign=0)
            lbl.set_ellipsize(3)
            lbl.set_margin_top(4)
            lbl.set_margin_bottom(4)
            lbl.set_margin_start(6)
            row.set_child(lbl)
            row._page = page - 1
            self.toc_list.append(row)

    def _on_toc_activated(self, lb, row):
        if hasattr(row, "_page"):
            self.page_num = row._page
            self.render()

    def _find_dialog(self):
        if not self.doc:
            return
        dialog = Gtk.Window(title="Cauta in document", transient_for=self, modal=True)
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        entry = Gtk.SearchEntry()

        def do_find(*a):
            term = entry.get_text()
            for i in range(self.page_num + 1, self.doc.page_count):
                if self.doc.load_page(i).search_for(term):
                    self.page_num = i
                    self.render()
                    break
            dialog.close()
        entry.connect("activate", do_find)
        b.append(entry)
        find_btn = Gtk.Button(label="Cauta urmatorul")
        find_btn.connect("clicked", do_find)
        b.append(find_btn)
        dialog.set_child(b)
        dialog.present()

    def _install_shortcuts(self):
        keymap = {
            "Right": lambda: self.go(1), "Page_Down": lambda: self.go(1),
            "Left": lambda: self.go(-1), "Page_Up": lambda: self.go(-1),
            "<Ctrl>f": lambda: self._find_dialog(),
            "<Ctrl>p": lambda: self._print(),
        }
        ctrl = Gtk.ShortcutController()
        ctrl.set_scope(Gtk.ShortcutScope.GLOBAL)
        for accel, fn in keymap.items():
            t = Gtk.ShortcutTrigger.parse_string(accel)
            a = Gtk.CallbackAction.new(lambda w, ar, f=fn: (f(), True)[1])
            ctrl.add_shortcut(Gtk.Shortcut.new(t, a))
        self.add_controller(ctrl)

    def _print(self):
        if self.path:
            GLib.spawn_command_line_async("lp '%s'" % self.path)

    def _error(self, msg):
        d = Gtk.AlertDialog()
        d.set_message("BoboReader")
        d.set_detail(msg)
        d.show(self)

    def do_close_request(self):
        try:
            os.makedirs(os.path.dirname(POS_FILE), exist_ok=True)
            with open(POS_FILE, "w") as fh:
                json.dump(self.positions, fh)
        except Exception:
            pass
        return False


class BoboReaderApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboReaderWindow(self)
        self.win.present()

    def do_open(self, files, n, hint):
        self.do_activate()
        for f in files:
            if f.get_path():
                self.win.open_file(f.get_path())
                break


def main():
    if "--version" in sys.argv:
        print("BoboReader 1.0.0 (BOBO OS)")
        return 0
    return BoboReaderApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
