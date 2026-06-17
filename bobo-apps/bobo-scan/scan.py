#!/usr/bin/env python3
# =============================================================================
# BoboScan - Scanner de securitate pentru BOBO OS (APP 31)
# GTK4. Antivirus ClamAV, rootkit (rkhunter/chkrootkit), audit Lynis,
# firewall status, porturi deschise, autentificari esuate, SUID neobisnuit.
# =============================================================================
import os
import sys
import subprocess
import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Scan"
QUARANTINE = os.path.expanduser("~/.local/share/bobo-scan/quarantine")


def sh(cmd, timeout=600):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        class R:
            stdout = ""
            stderr = str(e)
            returncode = 1
        return R()


class BoboScanWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboScan")
        self.set_default_size(820, 640)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        update = Gtk.Button(label="Update semnaturi")
        update.connect("clicked", lambda *a: self._run(["pkexec", "freshclam"], self.av_view))
        header.pack_start(update)

        nb = Gtk.Notebook()
        self.set_child(nb)
        nb.append_page(self._tab_av(), Gtk.Label(label="Antivirus"))
        nb.append_page(self._tab_rootkit(), Gtk.Label(label="Rootkit"))
        nb.append_page(self._tab_audit(), Gtk.Label(label="Audit"))
        nb.append_page(self._tab_network(), Gtk.Label(label="Retea / Porturi"))
        nb.append_page(self._tab_system(), Gtk.Label(label="Sistem"))

    def _view(self):
        tv = Gtk.TextView()
        tv.set_editable(False)
        tv.set_monospace(True)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(tv)
        return sw, tv

    def _tab_av(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        tb = Gtk.Box(spacing=6)
        tb.set_margin_top(6)
        tb.set_margin_start(6)
        for label, cb in [
            ("Scan Downloads + Desktop", lambda *a: self._clamscan([os.path.expanduser("~/Downloads"), os.path.expanduser("~/Desktop")])),
            ("Scan Home complet", lambda *a: self._clamscan([os.path.expanduser("~")])),
            ("Scan folder...", lambda *a: self._scan_folder()),
        ]:
            b = Gtk.Button(label=label)
            b.connect("clicked", cb)
            tb.append(b)
        box.append(tb)
        self.av_progress = Gtk.ProgressBar()
        self.av_progress.set_visible(False)
        box.append(self.av_progress)
        sw, self.av_view = self._view()
        box.append(sw)
        return box

    def _tab_rootkit(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        tb = Gtk.Box(spacing=6)
        tb.set_margin_top(6)
        tb.set_margin_start(6)
        rk = Gtk.Button(label="Ruleaza rkhunter")
        rk.connect("clicked", lambda *a: self._run(["pkexec", "rkhunter", "--check", "--sk", "--nocolors"], self.rk_view))
        ck = Gtk.Button(label="Ruleaza chkrootkit")
        ck.connect("clicked", lambda *a: self._run(["pkexec", "chkrootkit"], self.rk_view))
        tb.append(rk)
        tb.append(ck)
        box.append(tb)
        sw, self.rk_view = self._view()
        box.append(sw)
        return box

    def _tab_audit(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        b = Gtk.Button(label="Ruleaza audit Lynis (scor securitate)")
        b.set_margin_top(6)
        b.set_margin_start(6)
        b.connect("clicked", lambda *a: self._run(["pkexec", "lynis", "audit", "system", "--quick", "--nocolors"], self.audit_view))
        box.append(b)
        sw, self.audit_view = self._view()
        box.append(sw)
        return box

    def _tab_network(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        b = Gtk.Button(label="Reimprospateaza porturi + firewall")
        b.set_margin_top(6)
        b.set_margin_start(6)
        b.connect("clicked", lambda *a: self._net_info())
        box.append(b)
        sw, self.net_view = self._view()
        box.append(sw)
        GLib.idle_add(self._net_info)
        return box

    def _tab_system(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        b = Gtk.Button(label="Verifica SUID/SGID + autentificari esuate")
        b.set_margin_top(6)
        b.set_margin_start(6)
        b.connect("clicked", lambda *a: self._sys_info())
        box.append(b)
        sw, self.sys_view = self._view()
        box.append(sw)
        return box

    # ----------------------------------------------------------- ClamAV
    def _clamscan(self, paths):
        os.makedirs(QUARANTINE, exist_ok=True)
        self.av_progress.set_visible(True)
        self.av_progress.pulse()
        self.av_view.get_buffer().set_text("Scanare in curs...")

        def run():
            cmd = ["clamscan", "-r", "-i", "--move=" + QUARANTINE] + paths
            r = sh(cmd, timeout=3600)
            GLib.idle_add(self._av_done, r.stdout + r.stderr)
        threading.Thread(target=run, daemon=True).start()

    def _av_done(self, output):
        self.av_progress.set_visible(False)
        self.av_view.get_buffer().set_text(output)
        infected = [l for l in output.splitlines() if "FOUND" in l]
        if infected:
            GLib.spawn_command_line_async("notify-send -u critical 'BoboScan' 'Amenintari gasite: %d'" % len(infected))
        else:
            GLib.spawn_command_line_async("notify-send 'BoboScan' 'Niciun virus gasit'")

    def _scan_folder(self):
        d = Gtk.FileDialog()
        d.select_folder(self, None, self._folder_scan)

    def _folder_scan(self, dialog, res):
        try:
            f = dialog.select_folder_finish(res)
            if f:
                self._clamscan([f.get_path()])
        except GLib.Error:
            pass

    # ----------------------------------------------------------- generic run
    def _run(self, cmd, view):
        view.get_buffer().set_text("Rulez...")

        def run():
            r = sh(cmd, timeout=1800)
            GLib.idle_add(view.get_buffer().set_text, (r.stdout + r.stderr) or "Finalizat.")
        threading.Thread(target=run, daemon=True).start()

    def _net_info(self):
        def run():
            ports = sh(["ss", "-tulpn"]).stdout
            fw = sh(["nft", "list", "ruleset"]).stdout or "Firewall: ruleaza ca root pentru detalii"
            text = "=== PORTURI ASCULTATE ===\n%s\n\n=== FIREWALL (nftables) ===\n%s" % (ports, fw[:2000])
            GLib.idle_add(self.net_view.get_buffer().set_text, text)
        threading.Thread(target=run, daemon=True).start()

    def _sys_info(self):
        def run():
            suid = sh(["find", "/usr", "/bin", "/sbin", "-perm", "-4000", "-type", "f"]).stdout
            failed = sh(["journalctl", "-n", "50", "_COMM=sshd", "-g", "Failed"]).stdout or \
                sh(["bash", "-c", "lastb -n 20 2>/dev/null"]).stdout
            text = "=== Fisiere SUID ===\n%s\n\n=== Autentificari esuate (recente) ===\n%s" % (suid, failed)
            GLib.idle_add(self.sys_view.get_buffer().set_text, text)
        threading.Thread(target=run, daemon=True).start()


class BoboScanApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboScanWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboScan 1.0.0 (BOBO OS)")
        return 0
    return BoboScanApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
