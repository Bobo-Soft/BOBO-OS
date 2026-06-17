#!/usr/bin/env python3
# =============================================================================
# BoboVM - Manager de masini virtuale pentru BOBO OS (APP 26)
# GTK4 + libvirt (virsh/virt-install). Listeaza/creeaza/porneste VM-uri,
# consola (virt-viewer), snapshots.
# =============================================================================
import os
import sys
import subprocess
import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.VM"
IMG_DIR = os.path.expanduser("~/VirtualMachines")
PRESETS = {
    "Ubuntu": {"ram": 4096, "cpu": 2, "disk": 25},
    "Fedora": {"ram": 4096, "cpu": 2, "disk": 25},
    "Windows 11": {"ram": 8192, "cpu": 4, "disk": 64},
    "Debian": {"ram": 2048, "cpu": 2, "disk": 20},
}


def virsh(args):
    return subprocess.run(["virsh", "-c", "qemu:///session"] + args, capture_output=True, text=True)


class BoboVMWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboVM")
        self.set_default_size(720, 560)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        new = Gtk.Button(label="Masina noua")
        new.add_css_class("suggested-action")
        new.connect("clicked", lambda *a: self.create_dialog())
        header.pack_start(new)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.connect("clicked", lambda *a: self.refresh())
        header.pack_start(refresh)

        sw = Gtk.ScrolledWindow()
        self.listbox = Gtk.ListBox()
        self.listbox.set_vexpand(True)
        sw.set_child(self.listbox)
        self.set_child(sw)
        self.refresh()

    def refresh(self):
        threading.Thread(target=self._refresh, daemon=True).start()

    def _refresh(self):
        r = virsh(["list", "--all", "--name"])
        names = [n for n in r.stdout.split() if n]
        states = {}
        for n in names:
            st = virsh(["domstate", n]).stdout.strip()
            states[n] = st
        GLib.idle_add(self._show, states)

    def _show(self, states):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        if not states:
            self.listbox.append(Gtk.Label(label="Nicio masina virtuala. Apasa 'Masina noua'.", margin_top=20))
            return
        for name, state in states.items():
            row = Gtk.ListBoxRow()
            b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            b.set_margin_top(8)
            b.set_margin_bottom(8)
            b.set_margin_start(10)
            running = "running" in state
            icon = Gtk.Image.new_from_icon_name("computer-symbolic")
            b.append(icon)
            tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            tb.set_hexpand(True)
            nm = Gtk.Label(label=name, xalign=0)
            stl = Gtk.Label(label=state, xalign=0)
            stl.add_css_class("dim-label")
            tb.append(nm)
            tb.append(stl)
            b.append(tb)
            if running:
                view = Gtk.Button(label="Consola")
                view.connect("clicked", lambda x, n=name: subprocess.Popen(["virt-viewer", "-c", "qemu:///session", n]))
                b.append(view)
                stop = Gtk.Button(label="Opreste")
                stop.connect("clicked", lambda x, n=name: self._act(["shutdown", n]))
                b.append(stop)
            else:
                start = Gtk.Button(label="Porneste")
                start.add_css_class("suggested-action")
                start.connect("clicked", lambda x, n=name: self._act(["start", n]))
                b.append(start)
            snap = Gtk.Button.new_from_icon_name("camera-photo-symbolic")
            snap.set_tooltip_text("Snapshot")
            snap.connect("clicked", lambda x, n=name: self._snapshot(n))
            b.append(snap)
            row.set_child(b)
            self.listbox.append(row)

    def _act(self, args):
        virsh(args)
        self.refresh()

    def _snapshot(self, name):
        virsh(["snapshot-create-as", name, "snap"])
        self._notify("Snapshot creat pentru %s" % name)

    # ----------------------------------------------------------- create
    def create_dialog(self):
        win = Gtk.Window(title="Masina virtuala noua", transient_for=self, modal=True)
        win.set_default_size(440, -1)
        grid = Gtk.Grid(row_spacing=8, column_spacing=8, margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        name_e = Gtk.Entry(placeholder_text="Nume VM")
        preset_dd = Gtk.DropDown.new_from_strings(list(PRESETS.keys()))
        ram = Gtk.SpinButton.new_with_range(512, 32768, 512)
        ram.set_value(4096)
        cpu = Gtk.SpinButton.new_with_range(1, 16, 1)
        cpu.set_value(2)
        disk = Gtk.SpinButton.new_with_range(8, 500, 1)
        disk.set_value(25)
        iso_btn = Gtk.Button(label="Alege ISO...")
        self._iso = None
        iso_btn.connect("clicked", lambda *a: self._pick_iso(iso_btn))

        def apply_preset(dd, _):
            p = PRESETS[list(PRESETS.keys())[dd.get_selected()]]
            ram.set_value(p["ram"])
            cpu.set_value(p["cpu"])
            disk.set_value(p["disk"])
        preset_dd.connect("notify::selected", apply_preset)

        rows = [("Nume", name_e), ("Preset", preset_dd), ("RAM (MB)", ram),
                ("vCPU", cpu), ("Disc (GB)", disk), ("ISO", iso_btn)]
        for r, (lbl, w) in enumerate(rows):
            grid.attach(Gtk.Label(label=lbl, xalign=0), 0, r, 1, 1)
            w.set_hexpand(True)
            grid.attach(w, 1, r, 1, 1)
        create = Gtk.Button(label="Creeaza si porneste")
        create.add_css_class("suggested-action")
        create.connect("clicked", lambda *a: self._do_create(
            name_e.get_text(), int(ram.get_value()), int(cpu.get_value()), int(disk.get_value()), win))
        grid.attach(create, 0, len(rows), 2, 1)
        win.set_child(grid)
        win.present()

    def _pick_iso(self, btn):
        d = Gtk.FileDialog()
        d.open(self, None, lambda dd, rr: self._iso_set(dd, rr, btn))

    def _iso_set(self, dialog, res, btn):
        try:
            f = dialog.open_finish(res)
            if f:
                self._iso = f.get_path()
                btn.set_label(os.path.basename(self._iso))
        except GLib.Error:
            pass

    def _do_create(self, name, ram, cpu, disk, win):
        os.makedirs(IMG_DIR, exist_ok=True)
        disk_path = os.path.join(IMG_DIR, name + ".qcow2")
        subprocess.run(["qemu-img", "create", "-f", "qcow2", disk_path, "%dG" % disk], capture_output=True)
        cmd = ["virt-install", "--connect", "qemu:///session", "--name", name,
               "--memory", str(ram), "--vcpus", str(cpu),
               "--disk", "path=%s,format=qcow2" % disk_path,
               "--osinfo", "detect=on,require=off", "--graphics", "spice", "--noautoconsole"]
        if self._iso:
            cmd += ["--cdrom", self._iso]
        else:
            cmd += ["--pxe"]
        threading.Thread(target=lambda: (subprocess.run(cmd, capture_output=True), GLib.idle_add(self.refresh)), daemon=True).start()
        win.close()
        self._notify("Creez VM %s..." % name)

    def _notify(self, text):
        GLib.spawn_command_line_async("notify-send -i computer 'BoboVM' '%s'" % text.replace("'", ""))


class BoboVMApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboVMWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboVM 1.0.0 (BOBO OS)")
        return 0
    return BoboVMApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
