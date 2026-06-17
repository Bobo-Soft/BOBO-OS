#!/usr/bin/env python3
# =============================================================================
# BoboPrinter - Manager de imprimante pentru BOBO OS (APP 12)
# GTK4 + CUPS (lpstat/lpadmin/lp/cancel). Detectie, adaugare, coada de job-uri.
# =============================================================================
import os
import sys
import subprocess
import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Printer"


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


class BoboPrinterWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboPrinter")
        self.set_default_size(680, 560)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.connect("clicked", lambda *a: self.refresh())
        header.pack_start(refresh)
        add_btn = Gtk.Button(label="Adauga imprimanta")
        add_btn.connect("clicked", lambda *a: self.add_dialog())
        header.pack_start(add_btn)
        print_btn = Gtk.Button(label="Tipareste fisier...")
        print_btn.add_css_class("suggested-action")
        print_btn.connect("clicked", lambda *a: self.print_file())
        header.pack_end(print_btn)

        nb = Gtk.Notebook()
        self.set_child(nb)
        nb.append_page(self._tab_printers(), Gtk.Label(label="Imprimante"))
        nb.append_page(self._tab_jobs(), Gtk.Label(label="Coada job-uri"))
        self.refresh()

    def _tab_printers(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        self.printer_store = Gtk.ListStore(str, str, str)  # nume, status, locatie
        self.printer_tree = Gtk.TreeView(model=self.printer_store)
        for i, t in enumerate(["Imprimanta", "Status", "Detalii"]):
            col = Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            self.printer_tree.append_column(col)
        sw.set_child(self.printer_tree)
        box.append(sw)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_top(6)
        toolbar.set_margin_start(6)
        toolbar.set_margin_bottom(6)
        test = Gtk.Button(label="Pagina test")
        test.connect("clicked", lambda *a: self._test_page())
        default = Gtk.Button(label="Seteaza implicita")
        default.connect("clicked", lambda *a: self._set_default())
        remove = Gtk.Button(label="Sterge")
        remove.add_css_class("destructive-action")
        remove.connect("clicked", lambda *a: self._remove())
        for b in (test, default, remove):
            toolbar.append(b)
        box.append(toolbar)
        return box

    def _tab_jobs(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        self.job_store = Gtk.ListStore(str, str, str)  # job-id, imprimanta, fisier
        self.job_tree = Gtk.TreeView(model=self.job_store)
        for i, t in enumerate(["Job", "Imprimanta", "Fisier"]):
            self.job_tree.append_column(Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i))
        sw.set_child(self.job_tree)
        box.append(sw)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_top(6)
        toolbar.set_margin_start(6)
        cancel = Gtk.Button(label="Anuleaza job")
        cancel.connect("clicked", lambda *a: self._cancel_job())
        toolbar.append(cancel)
        box.append(toolbar)
        return box

    # ----------------------------------------------------------- refresh
    def refresh(self):
        threading.Thread(target=self._refresh, daemon=True).start()

    def _refresh(self):
        printers = []
        out = sh(["lpstat", "-p"]).stdout
        for line in out.splitlines():
            if line.startswith("printer"):
                parts = line.split()
                name = parts[1] if len(parts) > 1 else "?"
                status = "activa" if "enabled" in line or "idle" in line else " ".join(parts[2:])
                loc = sh(["lpstat", "-l", "-p", name]).stdout.strip()[:60]
                printers.append((name, status, loc))
        jobs = []
        for line in sh(["lpstat", "-o"]).stdout.splitlines():
            parts = line.split()
            if parts:
                jid = parts[0]
                pr = jid.rsplit("-", 1)[0]
                jobs.append((jid, pr, " ".join(parts[1:3])))
        GLib.idle_add(self._show, printers, jobs)

    def _show(self, printers, jobs):
        self.printer_store.clear()
        for p in printers:
            self.printer_store.append(list(p))
        self.job_store.clear()
        for j in jobs:
            self.job_store.append(list(j))

    # ----------------------------------------------------------- add
    def add_dialog(self):
        win = Gtk.Window(title="Adauga imprimanta", transient_for=self, modal=True)
        win.set_default_size(440, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        box.append(Gtk.Label(label="Imprimante detectate:", xalign=0))
        detected = Gtk.DropDown.new_from_strings(self._detect() or ["(niciuna detectata)"])
        box.append(detected)
        name_e = Gtk.Entry(placeholder_text="Nume imprimanta (ex: BiroPrinter)")
        uri_e = Gtk.Entry(placeholder_text="URI (ex: ipp://192.168.1.50)")
        box.append(name_e)
        box.append(uri_e)
        add = Gtk.Button(label="Adauga")
        add.add_css_class("suggested-action")

        def do_add(*a):
            name = name_e.get_text() or "BoboPrinter"
            uri = uri_e.get_text()
            if not uri:
                dl = self._detect_uris()
                idx = detected.get_selected()
                uri = dl[idx] if idx < len(dl) else "ipp://localhost"
            sh(["pkexec", "lpadmin", "-p", name, "-E", "-v", uri, "-m", "everywhere"])
            win.close()
            self.refresh()
        add.connect("clicked", do_add)
        box.append(add)
        win.set_child(box)
        win.present()

    def _detect(self):
        names = []
        for line in sh(["lpinfo", "-v"]).stdout.splitlines():
            if "network" in line or "direct" in line or "usb" in line:
                names.append(line.strip())
        return names

    def _detect_uris(self):
        uris = []
        for line in sh(["lpinfo", "-v"]).stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                uris.append(parts[1])
        return uris

    # ----------------------------------------------------------- actions
    def _selected_printer(self):
        model, it = self.printer_tree.get_selection().get_selected()
        return model.get_value(it, 0) if it else None

    def _test_page(self):
        p = self._selected_printer()
        if p:
            sh(["lp", "-d", p, "/usr/share/cups/data/testprint"])
            self.refresh()

    def _set_default(self):
        p = self._selected_printer()
        if p:
            sh(["lpadmin", "-d", p])
            self._notify("%s setata ca implicita" % p)

    def _remove(self):
        p = self._selected_printer()
        if p:
            sh(["pkexec", "lpadmin", "-x", p])
            self.refresh()

    def _cancel_job(self):
        model, it = self.job_tree.get_selection().get_selected()
        if it:
            jid = model.get_value(it, 0)
            sh(["cancel", jid])
            self.refresh()

    def print_file(self):
        d = Gtk.FileDialog()
        d.open(self, None, self._print_finished)

    def _print_finished(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        p = self._selected_printer()
        cmd = ["lp"]
        if p:
            cmd += ["-d", p]
        cmd.append(f.get_path())
        sh(cmd)
        self._notify("Trimis la tiparire: %s" % os.path.basename(f.get_path()))
        self.refresh()

    def _notify(self, text):
        GLib.spawn_command_line_async("notify-send -i printer 'BoboPrinter' '%s'" % text.replace("'", ""))


class BoboPrinterApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboPrinterWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboPrinter 1.0.0 (BOBO OS)")
        return 0
    return BoboPrinterApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
