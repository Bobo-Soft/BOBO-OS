#!/usr/bin/env python3
# =============================================================================
# BoboDev - Manager de containere pentru BOBO OS (APP 27)
# GTK4 + Podman. Containere (start/stop/remove/logs/exec), imagini (pull/build),
# volume, retele, compose, stats.
# =============================================================================
import os
import sys
import json
import subprocess
import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Dev"


def podman(args, timeout=30):
    return subprocess.run(["podman"] + args, capture_output=True, text=True, timeout=timeout)


class BoboDevWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboDev")
        self.set_default_size(820, 600)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        pull = Gtk.Button(label="Pull imagine")
        pull.connect("clicked", lambda *a: self.pull_dialog())
        header.pack_start(pull)
        build = Gtk.Button(label="Build")
        build.connect("clicked", lambda *a: self.build_dialog())
        header.pack_start(build)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.connect("clicked", lambda *a: self.refresh())
        header.pack_end(refresh)

        nb = Gtk.Notebook()
        self.set_child(nb)
        nb.append_page(self._tab_containers(), Gtk.Label(label="Containere"))
        nb.append_page(self._tab_images(), Gtk.Label(label="Imagini"))
        nb.append_page(self._tab_misc(), Gtk.Label(label="Volume / Retele"))
        self.refresh()

    def _tab_containers(self):
        sw = Gtk.ScrolledWindow()
        self.cont_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.cont_box.set_margin_top(6)
        self.cont_box.set_margin_start(6)
        self.cont_box.set_margin_end(6)
        sw.set_child(self.cont_box)
        return sw

    def _tab_images(self):
        sw = Gtk.ScrolledWindow()
        self.img_store = Gtk.ListStore(str, str, str)  # repo, tag, size
        self.img_tree = Gtk.TreeView(model=self.img_store)
        for i, t in enumerate(["Repository", "Tag", "Dimensiune"]):
            self.img_tree.append_column(Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i))
        sw.set_child(self.img_tree)
        return sw

    def _tab_misc(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        box.set_margin_start(8)
        compose = Gtk.Button(label="Ruleaza docker-compose.yml (up -d)...")
        compose.connect("clicked", lambda *a: self._compose())
        box.append(compose)
        self.misc_view = Gtk.TextView()
        self.misc_view.set_editable(False)
        self.misc_view.set_monospace(True)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(self.misc_view)
        box.append(sw)
        return box

    # ----------------------------------------------------------- refresh
    def refresh(self):
        threading.Thread(target=self._refresh, daemon=True).start()

    def _refresh(self):
        try:
            r = podman(["ps", "-a", "--format", "json"])
            containers = json.loads(r.stdout) if r.stdout.strip() else []
        except Exception:
            containers = []
        try:
            ri = podman(["images", "--format", "json"])
            images = json.loads(ri.stdout) if ri.stdout.strip() else []
        except Exception:
            images = []
        vols = podman(["volume", "ls"]).stdout
        nets = podman(["network", "ls"]).stdout
        GLib.idle_add(self._show, containers, images, vols + "\n" + nets)

    def _show(self, containers, images, misc):
        # containere
        child = self.cont_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.cont_box.remove(child)
            child = nxt
        if not containers:
            self.cont_box.append(Gtk.Label(label="Niciun container.", margin_top=14))
        for c in containers:
            cid = c.get("Id", "")[:12]
            names = ",".join(c.get("Names", [])) if isinstance(c.get("Names"), list) else c.get("Names", "")
            image = c.get("Image", "")
            state = c.get("State", "")
            running = state == "running"
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("card")
            dot = Gtk.Label(label="●")
            dot.add_css_class("bobo-accent" if running else "dim-label")
            row.append(dot)
            tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            tb.set_hexpand(True)
            tb.append(Gtk.Label(label=names, xalign=0))
            sub = Gtk.Label(label="%s  %s  %s" % (cid, image, state), xalign=0)
            sub.add_css_class("dim-label")
            tb.append(sub)
            row.append(tb)
            for icon, tip, args in (
                [("media-playback-stop-symbolic", "Stop", ["stop", cid])] if running else
                [("media-playback-start-symbolic", "Start", ["start", cid])]):
                b = Gtk.Button.new_from_icon_name(icon)
                b.set_tooltip_text(tip)
                b.connect("clicked", lambda x, ar=args: self._act(ar))
                row.append(b)
            logs = Gtk.Button.new_from_icon_name("text-x-generic-symbolic")
            logs.set_tooltip_text("Logs")
            logs.connect("clicked", lambda x, i=cid: self._logs(i))
            row.append(logs)
            shell = Gtk.Button.new_from_icon_name("utilities-terminal-symbolic")
            shell.set_tooltip_text("Shell")
            shell.connect("clicked", lambda x, i=cid: subprocess.Popen(["foot", "-e", "podman", "exec", "-it", i, "/bin/sh"]))
            row.append(shell)
            rm = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            rm.connect("clicked", lambda x, i=cid: self._act(["rm", "-f", i]))
            row.append(rm)
            self.cont_box.append(row)

        # imagini
        self.img_store.clear()
        for im in images:
            names = im.get("Names") or im.get("RepoTags") or ["<none>"]
            repo_tag = names[0] if names else "<none>"
            repo, _, tag = repo_tag.partition(":")
            size = im.get("Size", 0)
            self.img_store.append([repo, tag or "latest", "%.1f MB" % (size / 1e6) if isinstance(size, (int, float)) else str(size)])

        self.misc_view.get_buffer().set_text(misc)

    def _act(self, args):
        threading.Thread(target=lambda: (podman(args), GLib.idle_add(self.refresh)), daemon=True).start()

    def _logs(self, cid):
        win = Gtk.Window(title="Logs %s" % cid, transient_for=self)
        win.set_default_size(640, 480)
        tv = Gtk.TextView()
        tv.set_editable(False)
        tv.set_monospace(True)
        tv.get_buffer().set_text(podman(["logs", "--tail", "500", cid]).stdout)
        sw = Gtk.ScrolledWindow()
        sw.set_child(tv)
        win.set_child(sw)
        win.present()

    # ----------------------------------------------------------- pull/build
    def pull_dialog(self):
        win = Gtk.Window(title="Pull imagine", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        entry = Gtk.Entry(placeholder_text="ex: docker.io/library/nginx:latest")
        btn = Gtk.Button(label="Pull")
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda *a: (self._act(["pull", entry.get_text()]), win.close()))
        box.append(entry)
        box.append(btn)
        win.set_child(box)
        win.present()

    def build_dialog(self):
        d = Gtk.FileDialog()
        d.select_folder(self, None, self._do_build)

    def _do_build(self, dialog, res):
        try:
            f = dialog.select_folder_finish(res)
        except GLib.Error:
            return
        if f:
            ctx = f.get_path()
            tag = os.path.basename(ctx).lower()
            subprocess.Popen(["foot", "-e", "bash", "-c",
                              "podman build -t %s '%s'; read -p 'Enter...'" % (tag, ctx)])

    def _compose(self):
        d = Gtk.FileDialog()
        d.open(self, None, self._compose_run)

    def _compose_run(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if f:
            self._act(["compose", "-f", f.get_path(), "up", "-d"])


class BoboDevApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboDevWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboDev 1.0.0 (BOBO OS)")
        return 0
    return BoboDevApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
