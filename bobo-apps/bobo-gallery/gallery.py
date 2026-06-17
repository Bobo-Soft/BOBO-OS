#!/usr/bin/env python3
# =============================================================================
# BoboGallery - Vizualizator imagini pentru BOBO OS (APP 06)
# GTK4 + GdkPixbuf. Navigare director, zoom, rotire, slideshow, grid,
# EXIF (exiftool), set wallpaper, delete.
# =============================================================================
import os
import sys
import subprocess
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk, GdkPixbuf  # noqa: E402

APP_ID = "os.bobo.Gallery"
EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg", ".avif", ".heic")


class BoboGalleryWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboGallery")
        self.set_default_size(960, 720)
        self.files = []
        self.index = 0
        self.rotation = 0
        self.zoom = 1.0
        self.slideshow_id = 0
        self.exif_visible = False

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        open_btn = Gtk.Button.new_from_icon_name("document-open-symbolic")
        open_btn.connect("clicked", lambda *a: self.open_dialog())
        header.pack_start(open_btn)
        for icon, tip, cb in [
            ("go-previous-symbolic", "Anterior", lambda *a: self.navigate(-1)),
            ("go-next-symbolic", "Urmator", lambda *a: self.navigate(1)),
            ("object-rotate-right-symbolic", "Roteste", lambda *a: self.rotate(90)),
        ]:
            b = Gtk.Button.new_from_icon_name(icon)
            b.set_tooltip_text(tip)
            b.connect("clicked", cb)
            header.pack_start(b)

        grid_btn = Gtk.ToggleButton()
        grid_btn.set_icon_name("view-grid-symbolic")
        grid_btn.set_tooltip_text("Grila (Ctrl+G)")
        grid_btn.connect("toggled", self._toggle_grid)
        self.grid_btn = grid_btn
        header.pack_end(grid_btn)
        exif_btn = Gtk.ToggleButton()
        exif_btn.set_icon_name("dialog-information-symbolic")
        exif_btn.set_tooltip_text("Detalii EXIF")
        exif_btn.connect("toggled", self._toggle_exif)
        header.pack_end(exif_btn)
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(self._menu())
        header.pack_end(menu_btn)

        self._install_actions()

        self.stack = Gtk.Stack()
        self.set_child(self.stack)

        # vizualizare imagine + panou EXIF
        img_split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_hexpand(True)
        self.scroller.set_vexpand(True)
        self.picture = Gtk.Picture()
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.scroller.set_child(self.picture)
        img_split.set_start_child(self.scroller)
        img_split.set_resize_start_child(True)
        self.exif_panel = Gtk.ScrolledWindow()
        self.exif_panel.set_size_request(260, -1)
        self.exif_label = Gtk.Label(xalign=0, yalign=0)
        self.exif_label.set_selectable(True)
        self.exif_label.set_wrap(True)
        self.exif_panel.set_child(self.exif_label)
        self.exif_panel.set_visible(False)
        img_split.set_end_child(self.exif_panel)
        img_split.set_resize_end_child(False)
        self.stack.add_named(img_split, "image")

        # vizualizare grila
        grid_scroll = Gtk.ScrolledWindow()
        grid_scroll.set_vexpand(True)
        self.flow = Gtk.FlowBox()
        self.flow.set_valign(Gtk.Align.START)
        self.flow.set_max_children_per_line(6)
        self.flow.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flow.connect("child-activated", self._on_grid_activated)
        grid_scroll.set_child(self.flow)
        self.stack.add_named(grid_scroll, "grid")

        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._on_scroll)
        self.scroller.add_controller(scroll)
        self._install_shortcuts()

    def _menu(self):
        m = Gio.Menu()
        m.append("Slideshow (F5)", "gal.slideshow")
        m.append("Seteaza ca wallpaper", "gal.wallpaper")
        m.append("Sterge (la cos)", "gal.delete")
        return m

    def _install_actions(self):
        grp = Gio.SimpleActionGroup()
        for name, fn in [("slideshow", lambda *a: self.toggle_slideshow()),
                         ("wallpaper", lambda *a: self.set_wallpaper()),
                         ("delete", lambda *a: self.delete_current())]:
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", fn)
            grp.add_action(act)
        self.insert_action_group("gal", grp)

    # ----------------------------------------------------------- open
    def open_dialog(self):
        d = Gtk.FileDialog()
        d.open(self, None, self._open_finished)

    def _open_finished(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if f:
            self.open_file(f.get_path())

    def open_file(self, path):
        directory = os.path.dirname(path)
        self.files = sorted(
            os.path.join(directory, n) for n in os.listdir(directory)
            if n.lower().endswith(EXTS)
        )
        try:
            self.index = self.files.index(path)
        except ValueError:
            self.files = [path]
            self.index = 0
        self.show_current()
        self._populate_grid()

    # ----------------------------------------------------------- display
    def show_current(self):
        if not self.files:
            return
        self.index = max(0, min(self.index, len(self.files) - 1))
        path = self.files[self.index]
        self.rotation = 0
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            self.picture.set_pixbuf(pixbuf)
        except Exception as e:
            print("[bobo-gallery] %s: %s" % (path, e))
        self.set_title("BoboGallery - %s (%d/%d)" % (
            os.path.basename(path), self.index + 1, len(self.files)))
        if self.exif_visible:
            self._load_exif(path)

    def navigate(self, delta):
        self.index += delta
        if self.index < 0:
            self.index = len(self.files) - 1
        if self.index >= len(self.files):
            self.index = 0
        self.show_current()

    def rotate(self, deg):
        pix = self.picture.get_pixbuf() if hasattr(self.picture, "get_pixbuf") else None
        if not pix:
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file(self.files[self.index])
            except Exception:
                return
        rotated = pix.rotate_simple(GdkPixbuf.PixbufRotation.CLOCKWISE if deg == 90
                                    else GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE)
        self.picture.set_pixbuf(rotated)

    def _on_scroll(self, ctrl, dx, dy):
        state = ctrl.get_current_event_state()
        if state & Gdk.ModifierType.CONTROL_MASK:
            self.zoom = max(0.2, min(5.0, self.zoom + (-0.1 if dy > 0 else 0.1)))
            self.picture.set_size_request(int(800 * self.zoom), int(600 * self.zoom))
            return True
        else:
            self.navigate(1 if dy > 0 else -1)
            return True

    # ----------------------------------------------------------- grid
    def _populate_grid(self):
        child = self.flow.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.flow.remove(child)
            child = nxt
        for i, path in enumerate(self.files):
            try:
                thumb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 150, 150, True)
            except Exception:
                continue
            pic = Gtk.Picture.new_for_pixbuf(thumb)
            pic.set_size_request(150, 150)
            fc = Gtk.FlowBoxChild()
            fc.set_child(pic)
            fc._index = i
            self.flow.append(fc)

    def _toggle_grid(self, btn):
        if btn.get_active():
            self.stack.set_visible_child_name("grid")
        else:
            self.stack.set_visible_child_name("image")

    def _on_grid_activated(self, flow, child):
        self.index = child._index
        self.grid_btn.set_active(False)
        self.stack.set_visible_child_name("image")
        self.show_current()

    # ----------------------------------------------------------- EXIF
    def _toggle_exif(self, btn):
        self.exif_visible = btn.get_active()
        self.exif_panel.set_visible(self.exif_visible)
        if self.exif_visible and self.files:
            self._load_exif(self.files[self.index])

    def _load_exif(self, path):
        try:
            out = subprocess.run(["exiftool", path], capture_output=True, text=True, timeout=8).stdout
        except Exception:
            out = "exiftool indisponibil.\n" + self._basic_info(path)
        self.exif_label.set_text(out or self._basic_info(path))

    def _basic_info(self, path):
        try:
            st = os.stat(path)
            pix = GdkPixbuf.Pixbuf.new_from_file(path)
            return "Fisier: %s\nDimensiune: %d KB\nRezolutie: %dx%d" % (
                os.path.basename(path), st.st_size // 1024, pix.get_width(), pix.get_height())
        except Exception:
            return os.path.basename(path)

    # ----------------------------------------------------------- actions
    def toggle_slideshow(self):
        if self.slideshow_id:
            GLib.source_remove(self.slideshow_id)
            self.slideshow_id = 0
        else:
            self.slideshow_id = GLib.timeout_add_seconds(3, lambda: (self.navigate(1), True)[1])

    def set_wallpaper(self):
        if not self.files:
            return
        GLib.spawn_command_line_async("pkill swaybg")
        GLib.spawn_command_line_async("swaybg -m fill -i '%s'" % self.files[self.index])

    def delete_current(self):
        if not self.files:
            return
        path = self.files[self.index]
        try:
            subprocess.run(["gio", "trash", path], timeout=8)
        except Exception:
            try:
                os.remove(path)
            except Exception:
                return
        del self.files[self.index]
        if self.files:
            self.show_current()
            self._populate_grid()

    def _install_shortcuts(self):
        keymap = {
            "Right": lambda: self.navigate(1), "Left": lambda: self.navigate(-1),
            "r": lambda: self.rotate(90), "<Shift>r": lambda: self.rotate(-90),
            "F5": lambda: self.toggle_slideshow(),
            "<Ctrl>g": lambda: self.grid_btn.set_active(not self.grid_btn.get_active()),
            "Delete": lambda: self.delete_current(),
            "f": lambda: self.fullscreen() if not self.is_fullscreen() else self.unfullscreen(),
        }
        ctrl = Gtk.ShortcutController()
        ctrl.set_scope(Gtk.ShortcutScope.GLOBAL)
        for accel, fn in keymap.items():
            t = Gtk.ShortcutTrigger.parse_string(accel)
            a = Gtk.CallbackAction.new(lambda w, ar, f=fn: (f(), True)[1])
            ctrl.add_shortcut(Gtk.Shortcut.new(t, a))
        self.add_controller(ctrl)


class BoboGalleryApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboGalleryWindow(self)
        self.win.present()

    def do_open(self, files, n, hint):
        self.do_activate()
        for f in files:
            if f.get_path():
                self.win.open_file(f.get_path())
                break


def main():
    if "--version" in sys.argv:
        print("BoboGallery 1.0.0 (BOBO OS)")
        return 0
    return BoboGalleryApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
