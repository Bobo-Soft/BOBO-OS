#!/usr/bin/env python3
# =============================================================================
# BoboArchive - Manager de arhive pentru BOBO OS (APP 07)
# GTK4. Listeaza/extrage/creeaza ZIP, 7z, RAR, TAR.* prin 7z/unzip/tar.
# =============================================================================
import os
import sys
import subprocess
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Archive"


def have(cmd):
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0


class BoboArchiveWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboArchive")
        self.set_default_size(760, 560)
        self.archive_path = None
        self.entries = []

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        open_btn = Gtk.Button.new_from_icon_name("document-open-symbolic")
        open_btn.set_tooltip_text("Deschide arhiva")
        open_btn.connect("clicked", lambda *a: self.open_dialog())
        header.pack_start(open_btn)
        new_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        new_btn.set_tooltip_text("Creeaza arhiva noua")
        new_btn.connect("clicked", lambda *a: self.create_dialog())
        header.pack_start(new_btn)

        self.extract_btn = Gtk.Button(label="Extrage tot...")
        self.extract_btn.add_css_class("suggested-action")
        self.extract_btn.connect("clicked", lambda *a: self.extract_all())
        self.extract_btn.set_sensitive(False)
        header.pack_end(self.extract_btn)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(box)
        self.info_label = Gtk.Label(label="Deschide o arhiva pentru a-i vedea continutul.", xalign=0)
        self.info_label.set_margin_start(8)
        self.info_label.set_margin_top(6)
        box.append(self.info_label)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        self.store = Gtk.ListStore(str, str, str)  # nume, dimensiune, tip
        self.tree = Gtk.TreeView(model=self.store)
        for i, t in enumerate(["Nume", "Dimensiune", "Tip"]):
            col = Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            col.set_sort_column_id(i)
            self.tree.append_column(col)
        self.tree.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        scroller.set_child(self.tree)
        box.append(scroller)

        # drag & drop fisiere -> creeaza arhiva
        drop = Gtk.DropTarget.new(Gdk_file_type(), Gdk_copy())
        drop.connect("drop", self._on_drop)
        self.tree.add_controller(drop)

    # ----------------------------------------------------------- open/list
    def open_dialog(self):
        d = Gtk.FileDialog()
        d.open(self, None, self._open_finished)

    def _open_finished(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if f:
            self.open_archive(f.get_path())

    def open_archive(self, path):
        self.archive_path = path
        self.store.clear()
        entries = self._list_contents(path)
        self.entries = entries
        for name, size in entries:
            ext = os.path.splitext(name)[1] or "dir" if name.endswith("/") else os.path.splitext(name)[1]
            self.store.append([name, self._human(size), ext or "-"])
        self.info_label.set_text("%s  -  %d intrari" % (os.path.basename(path), len(entries)))
        self.extract_btn.set_sensitive(True)
        self.set_title("BoboArchive - " + os.path.basename(path))

    def _list_contents(self, path):
        ext = path.lower()
        out = []
        try:
            if ext.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
                r = subprocess.run(["tar", "-tvf", path], capture_output=True, text=True, timeout=30).stdout
                for line in r.splitlines():
                    parts = line.split()
                    if len(parts) >= 6:
                        out.append((parts[-1], int(parts[2]) if parts[2].isdigit() else 0))
            elif ext.endswith(".zip") and have("unzip"):
                r = subprocess.run(["unzip", "-l", path], capture_output=True, text=True, timeout=30).stdout
                for line in r.splitlines()[3:]:
                    parts = line.split()
                    if len(parts) >= 4 and parts[0].isdigit():
                        out.append((" ".join(parts[3:]), int(parts[0])))
            elif have("7z"):
                r = subprocess.run(["7z", "l", "-slt", path], capture_output=True, text=True, timeout=30).stdout
                name = None
                size = 0
                for line in r.splitlines():
                    if line.startswith("Path = "):
                        name = line[7:]
                    elif line.startswith("Size = "):
                        try:
                            size = int(line[7:])
                        except ValueError:
                            size = 0
                    elif line.strip() == "" and name and name != path:
                        out.append((name, size))
                        name = None
                        size = 0
        except Exception as e:
            self.info_label.set_text("Eroare la citire: %s" % e)
        return out

    # ----------------------------------------------------------- extract
    def extract_all(self):
        if not self.archive_path:
            return
        d = Gtk.FileDialog()
        d.select_folder(self, None, self._extract_to)

    def _extract_to(self, dialog, res):
        try:
            folder = dialog.select_folder_finish(res)
        except GLib.Error:
            return
        if not folder:
            return
        dest = folder.get_path()
        path = self.archive_path
        try:
            if path.lower().endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
                cmd = ["tar", "-xf", path, "-C", dest]
            elif path.lower().endswith(".zip") and have("unzip"):
                cmd = ["unzip", "-o", path, "-d", dest]
            else:
                cmd = ["7z", "x", "-y", "-o" + dest, path]
            subprocess.Popen(cmd)
            self._notify("Extragere in %s" % dest)
        except Exception as e:
            self._notify("Extragere esuata: %s" % e)

    # ----------------------------------------------------------- create
    def create_dialog(self):
        d = Gtk.FileDialog()
        d.open_multiple(self, None, self._create_pick_files)

    def _create_pick_files(self, dialog, res):
        try:
            files = dialog.open_multiple_finish(res)
        except GLib.Error:
            return
        paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
        paths = [p for p in paths if p]
        if not paths:
            return
        save = Gtk.FileDialog()
        save.set_initial_name("arhiva.zip")
        save.save(self, None, lambda dd, rr: self._do_create(dd, rr, paths))

    def _do_create(self, dialog, res, paths):
        try:
            f = dialog.save_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        out = f.get_path()
        # alege unealta dupa extensie
        if out.lower().endswith(".7z"):
            cmd = ["7z", "a", out] + paths
        elif out.lower().endswith((".tar.gz", ".tgz")):
            cmd = ["tar", "-czf", out] + paths
        elif out.lower().endswith((".tar.xz",)):
            cmd = ["tar", "-cJf", out] + paths
        else:
            cmd = ["zip", "-r", out] + paths
        try:
            subprocess.Popen(cmd)
            self._notify("Creez arhiva %s" % os.path.basename(out))
        except Exception as e:
            self._notify("Creare esuata: %s" % e)

    def _on_drop(self, target, value, x, y):
        if value and value.get_path():
            save = Gtk.FileDialog()
            save.set_initial_name("arhiva.zip")
            save.save(self, None, lambda d, r: self._do_create(d, r, [value.get_path()]))
            return True
        return False

    # ----------------------------------------------------------- helpers
    def _human(self, size):
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return "%.0f %s" % (size, unit)
            size /= 1024
        return "%.1f TB" % size

    def _notify(self, text):
        self.info_label.set_text(text)
        GLib.spawn_command_line_async("notify-send -a BoboArchive 'BoboArchive' '%s'" % text.replace("'", ""))


# Helperi pentru DropTarget (evita importul timpuriu Gdk in semnaturi)
def Gdk_file_type():
    return Gio.File


def Gdk_copy():
    from gi.repository import Gdk
    return Gdk.DragAction.COPY


class BoboArchiveApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboArchiveWindow(self)
        self.win.present()

    def do_open(self, files, n, hint):
        self.do_activate()
        for f in files:
            if f.get_path():
                self.win.open_archive(f.get_path())
                break


def main():
    if "--version" in sys.argv:
        print("BoboArchive 1.0.0 (BOBO OS)")
        return 0
    return BoboArchiveApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
