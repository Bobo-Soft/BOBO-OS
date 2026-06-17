#!/usr/bin/env python3
# =============================================================================
# BoboBackup - Manager de backup pentru BOBO OS (APP 11)
# GTK4 + BorgBackup (deduplicare/compresie/criptare) + rclone (cloud).
# Backup incremental, destinatii multiple, planificare, restore, versioning.
# =============================================================================
import os
import sys
import json
import subprocess
import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Backup"
CONF = os.path.expanduser("~/.config/bobo-backup/config.json")
DEFAULT = {
    "repo": os.path.expanduser("~/Backups/borg-repo"),
    "sources": [os.path.expanduser("~")],
    "excludes": ["*.cache", "node_modules", "*/.cache/*"],
    "schedule": "daily",
    "rclone_remote": "",
}


def sh(cmd, env=None, **kw):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, capture_output=True, text=True, env=e, **kw)


def load_conf():
    try:
        with open(CONF) as fh:
            d = dict(DEFAULT)
            d.update(json.load(fh))
            return d
    except Exception:
        return dict(DEFAULT)


def save_conf(c):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF, "w") as fh:
        json.dump(c, fh, indent=2)


class BoboBackupWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboBackup")
        self.set_default_size(700, 560)
        self.conf = load_conf()

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        self.backup_btn = Gtk.Button(label="Backup acum")
        self.backup_btn.add_css_class("suggested-action")
        self.backup_btn.connect("clicked", lambda *a: self.run_backup())
        header.pack_end(self.backup_btn)

        nb = Gtk.Notebook()
        self.set_child(nb)
        nb.append_page(self._tab_config(), Gtk.Label(label="Configurare"))
        nb.append_page(self._tab_snapshots(), Gtk.Label(label="Snapshots / Restore"))

        self.progress = Gtk.ProgressBar()
        self.progress.set_visible(False)

    # ----------------------------------------------------------- config
    def _tab_config(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(16)
        box.set_margin_end(16)

        self.repo_entry = Gtk.Entry()
        self.repo_entry.set_text(self.conf["repo"])
        box.append(self._row("Depozit Borg (local)", self.repo_entry))

        self.rclone_entry = Gtk.Entry()
        self.rclone_entry.set_placeholder_text("ex: gdrive:Backups (gol = doar local)")
        self.rclone_entry.set_text(self.conf.get("rclone_remote", ""))
        box.append(self._row("Remote rclone (cloud)", self.rclone_entry))

        box.append(Gtk.Label(label="Surse de backup (una pe linie):", xalign=0))
        self.sources_view = Gtk.TextView()
        self.sources_view.get_buffer().set_text("\n".join(self.conf["sources"]))
        sw1 = Gtk.ScrolledWindow()
        sw1.set_min_content_height(80)
        sw1.set_child(self.sources_view)
        box.append(sw1)

        box.append(Gtk.Label(label="Excluderi (pattern, una pe linie):", xalign=0))
        self.excl_view = Gtk.TextView()
        self.excl_view.get_buffer().set_text("\n".join(self.conf["excludes"]))
        sw2 = Gtk.ScrolledWindow()
        sw2.set_min_content_height(70)
        sw2.set_child(self.excl_view)
        box.append(sw2)

        self.sched = Gtk.DropDown.new_from_strings(["manual", "daily", "weekly", "monthly"])
        self.sched.set_selected(["manual", "daily", "weekly", "monthly"].index(self.conf.get("schedule", "daily")))
        box.append(self._row("Planificare", self.sched))

        save = Gtk.Button(label="Salveaza configurarea")
        save.connect("clicked", lambda *a: self.save())
        box.append(save)
        return box

    def _tab_snapshots(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_top(8)
        toolbar.set_margin_start(8)
        refresh = Gtk.Button(label="Reimprospateaza")
        refresh.connect("clicked", lambda *a: self.list_snapshots())
        restore = Gtk.Button(label="Restore selectat...")
        restore.connect("clicked", lambda *a: self.restore_selected())
        check = Gtk.Button(label="Verifica integritate")
        check.connect("clicked", lambda *a: threading.Thread(target=self._check, daemon=True).start())
        toolbar.append(refresh)
        toolbar.append(restore)
        toolbar.append(check)
        box.append(toolbar)

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        self.snap_store = Gtk.ListStore(str, str)  # nume, data
        self.snap_tree = Gtk.TreeView(model=self.snap_store)
        for i, t in enumerate(["Arhiva", "Data"]):
            self.snap_tree.append_column(Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i))
        sw.set_child(self.snap_tree)
        box.append(sw)
        return box

    def _row(self, label, widget):
        b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        lbl = Gtk.Label(label=label, xalign=0)
        lbl.set_size_request(180, -1)
        widget.set_hexpand(True)
        b.append(lbl)
        b.append(widget)
        return b

    # ----------------------------------------------------------- actions
    def save(self):
        buf = self.sources_view.get_buffer()
        self.conf["sources"] = [l for l in buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True).splitlines() if l.strip()]
        buf2 = self.excl_view.get_buffer()
        self.conf["excludes"] = [l for l in buf2.get_text(buf2.get_start_iter(), buf2.get_end_iter(), True).splitlines() if l.strip()]
        self.conf["repo"] = self.repo_entry.get_text()
        self.conf["rclone_remote"] = self.rclone_entry.get_text()
        self.conf["schedule"] = ["manual", "daily", "weekly", "monthly"][self.sched.get_selected()]
        save_conf(self.conf)
        self._notify("Configurare salvata")
        self._install_cron()

    def _install_cron(self):
        sched = self.conf["schedule"]
        if sched == "manual":
            return
        when = {"daily": "0 2 * * *", "weekly": "0 2 * * 0", "monthly": "0 2 1 * *"}[sched]
        line = "%s bobo-backup --run\n" % when
        try:
            existing = sh(["crontab", "-l"]).stdout
            kept = "\n".join(l for l in existing.splitlines() if "bobo-backup" not in l)
            p = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE)
            p.communicate((kept + "\n" + line).encode())
        except Exception:
            pass

    def run_backup(self):
        self.progress.set_visible(True)
        self.progress.pulse()
        threading.Thread(target=self._backup, daemon=True).start()

    def _ensure_repo(self):
        repo = self.conf["repo"]
        if not os.path.exists(os.path.join(repo, "config")):
            os.makedirs(repo, exist_ok=True)
            sh(["borg", "init", "--encryption=repokey", repo],
               env={"BORG_PASSPHRASE": ""})

    def _backup(self):
        repo = self.conf["repo"]
        self._ensure_repo()
        import datetime  # doar pentru numele arhivei (nu pentru logica de stare)
        name = "bobo-{now}"
        cmd = ["borg", "create", "--compression", "zstd", "--stats",
               "%s::%s" % (repo, name)]
        cmd += self.conf["sources"]
        for ex in self.conf["excludes"]:
            cmd += ["--exclude", ex]
        # borg accepta {now} ca placeholder pentru timestamp
        r = sh(cmd, env={"BORG_PASSPHRASE": ""})
        ok = r.returncode == 0
        # versioning prune
        sh(["borg", "prune", repo, "--keep-daily=7", "--keep-weekly=4", "--keep-monthly=6"],
           env={"BORG_PASSPHRASE": ""})
        # sync cloud rclone
        remote = self.conf.get("rclone_remote")
        if remote and ok:
            sh(["rclone", "sync", repo, remote, "--transfers", "4"])
        GLib.idle_add(self._backup_done, ok, r.stderr[-300:] if not ok else "")

    def _backup_done(self, ok, err):
        self.progress.set_visible(False)
        if ok:
            self._notify("Backup finalizat cu succes")
            self.list_snapshots()
        else:
            self._notify("Backup esuat")
            print("[bobo-backup]", err)

    def list_snapshots(self):
        threading.Thread(target=self._list, daemon=True).start()

    def _list(self):
        repo = self.conf["repo"]
        r = sh(["borg", "list", "--short", repo], env={"BORG_PASSPHRASE": ""})
        rows = []
        for line in r.stdout.splitlines():
            parts = line.split("-")
            date = parts[-1] if len(parts) > 1 else ""
            rows.append((line, date))
        GLib.idle_add(self._show_snaps, rows)

    def _show_snaps(self, rows):
        self.snap_store.clear()
        for r in rows:
            self.snap_store.append(list(r))

    def restore_selected(self):
        model, it = self.snap_tree.get_selection().get_selected()
        if it is None:
            return
        archive = model.get_value(it, 0)
        d = Gtk.FileDialog()
        d.select_folder(self, None, lambda dd, rr: self._do_restore(dd, rr, archive))

    def _do_restore(self, dialog, res, archive):
        try:
            folder = dialog.select_folder_finish(res)
        except GLib.Error:
            return
        if not folder:
            return
        dest = folder.get_path()

        def do():
            sh(["borg", "extract", "%s::%s" % (self.conf["repo"], archive)],
               env={"BORG_PASSPHRASE": ""}, cwd=dest)
            GLib.idle_add(self._notify, "Restore complet in %s" % dest)
        threading.Thread(target=do, daemon=True).start()

    def _check(self):
        r = sh(["borg", "check", self.conf["repo"]], env={"BORG_PASSPHRASE": ""})
        GLib.idle_add(self._notify, "Integritate OK" if r.returncode == 0 else "Probleme la verificare")

    def _notify(self, text):
        GLib.spawn_command_line_async("notify-send -i drive-harddisk 'BoboBackup' '%s'" % text.replace("'", ""))


class BoboBackupApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboBackupWindow(self).present()


def run_cli_backup():
    """Backup neinteractiv (pentru cron). Foloseste configurarea salvata."""
    conf = load_conf()
    repo = conf["repo"]
    if not os.path.exists(os.path.join(repo, "config")):
        os.makedirs(repo, exist_ok=True)
        sh(["borg", "init", "--encryption=repokey", repo], env={"BORG_PASSPHRASE": ""})
    cmd = ["borg", "create", "--compression", "zstd", "%s::bobo-{now}" % repo] + conf["sources"]
    for ex in conf["excludes"]:
        cmd += ["--exclude", ex]
    sh(cmd, env={"BORG_PASSPHRASE": ""})
    sh(["borg", "prune", repo, "--keep-daily=7", "--keep-weekly=4", "--keep-monthly=6"],
       env={"BORG_PASSPHRASE": ""})
    if conf.get("rclone_remote"):
        sh(["rclone", "sync", repo, conf["rclone_remote"]])


def main():
    if "--version" in sys.argv:
        print("BoboBackup 1.0.0 (BOBO OS)")
        return 0
    if "--run" in sys.argv:
        run_cli_backup()
        return 0
    return BoboBackupApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
