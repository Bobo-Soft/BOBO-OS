#!/usr/bin/env python3
# =============================================================================
# BoboUsers - Manager de utilizatori pentru BOBO OS (APP 15)
# GTK4. Listeaza/creeaza/sterge conturi, schimba parola, admin, blocare, grupuri.
# Operatiile privilegiate ruleaza prin pkexec.
# =============================================================================
import os
import sys
import pwd
import grp
import subprocess
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

APP_ID = "os.bobo.Users"


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def real_users():
    out = []
    for p in pwd.getpwall():
        if 1000 <= p.pw_uid < 65000 and p.pw_shell not in ("/usr/sbin/nologin", "/bin/false"):
            out.append(p)
    return out


def is_admin(username):
    try:
        return username in grp.getgrnam("sudo").gr_mem
    except KeyError:
        try:
            return username in grp.getgrnam("wheel").gr_mem
        except KeyError:
            return False


class BoboUsersWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboUsers")
        self.set_default_size(720, 520)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        add_btn = Gtk.Button(label="Utilizator nou")
        add_btn.add_css_class("suggested-action")
        add_btn.connect("clicked", lambda *a: self.create_dialog())
        header.pack_start(add_btn)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.connect("clicked", lambda *a: self.refresh())
        header.pack_start(refresh)

        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(split)

        sw = Gtk.ScrolledWindow()
        sw.set_size_request(260, -1)
        self.listbox = Gtk.ListBox()
        self.listbox.connect("row-selected", self._on_selected)
        sw.set_child(self.listbox)
        split.set_start_child(sw)
        split.set_resize_start_child(False)

        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.detail.set_margin_top(16)
        self.detail.set_margin_start(18)
        self.detail.set_margin_end(18)
        split.set_end_child(self.detail)

        self.refresh()

    def refresh(self):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        for u in real_users():
            row = Gtk.ListBoxRow()
            b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            b.set_margin_top(6)
            b.set_margin_bottom(6)
            b.set_margin_start(8)
            b.append(Gtk.Image.new_from_icon_name("avatar-default-symbolic"))
            name = u.pw_gecos.split(",")[0] or u.pw_name
            lbl = Gtk.Label(label=name, xalign=0)
            b.append(lbl)
            if is_admin(u.pw_name):
                badge = Gtk.Label(label="admin")
                badge.add_css_class("dim-label")
                b.append(badge)
            row.set_child(b)
            row._user = u.pw_name
            self.listbox.append(row)

    def _on_selected(self, lb, row):
        child = self.detail.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.detail.remove(child)
            child = nxt
        if not row:
            return
        username = row._user
        u = pwd.getpwnam(username)
        groups = [g.gr_name for g in grp.getgrall() if username in g.gr_mem]

        title = Gtk.Label(xalign=0)
        title.set_markup("<span size='x-large' weight='bold'>%s</span>" % username)
        self.detail.append(title)
        self.detail.append(Gtk.Label(label="UID: %d   Home: %s" % (u.pw_uid, u.pw_dir), xalign=0))
        self.detail.append(Gtk.Label(label="Grupuri: %s" % ", ".join(groups), xalign=0))

        # admin toggle
        admin_sw = Gtk.Switch()
        admin_sw.set_active(is_admin(username))
        admin_sw.set_halign(Gtk.Align.START)
        admin_sw.connect("state-set", lambda s, v: (self._set_admin(username, v), False)[1])
        self.detail.append(self._row("Administrator (sudo)", admin_sw))

        # actiuni
        pw_btn = Gtk.Button(label="Schimba parola")
        pw_btn.connect("clicked", lambda *a: self._change_password(username))
        self.detail.append(pw_btn)
        avatar_btn = Gtk.Button(label="Schimba avatar")
        avatar_btn.connect("clicked", lambda *a: self._change_avatar(username))
        self.detail.append(avatar_btn)
        lock_btn = Gtk.Button(label="Blocheaza cont")
        lock_btn.connect("clicked", lambda *a: self._lock(username))
        self.detail.append(lock_btn)
        del_btn = Gtk.Button(label="Sterge utilizator")
        del_btn.add_css_class("destructive-action")
        del_btn.connect("clicked", lambda *a: self._delete(username))
        self.detail.append(del_btn)

    def _row(self, label, widget):
        b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        lbl = Gtk.Label(label=label, xalign=0)
        lbl.set_hexpand(True)
        b.append(lbl)
        b.append(widget)
        return b

    # ----------------------------------------------------------- actions
    def create_dialog(self):
        win = Gtk.Window(title="Utilizator nou", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        full = Gtk.Entry(placeholder_text="Nume complet")
        user = Gtk.Entry(placeholder_text="Nume utilizator")
        pw = Gtk.PasswordEntry()
        pw.set_show_peek_icon(True)
        admin = Gtk.CheckButton(label="Cont de administrator")
        for w in (full, user, pw, admin):
            box.append(w)
        btn = Gtk.Button(label="Creeaza")
        btn.add_css_class("suggested-action")

        def do_create(*a):
            uname = user.get_text()
            groups = "sudo,audio,video,plugdev,input,render" if admin.get_active() else "audio,video,plugdev"
            sh(["pkexec", "useradd", "-m", "-s", "/bin/bash", "-c", full.get_text(), "-G", groups, uname])
            p = subprocess.Popen(["pkexec", "chpasswd"], stdin=subprocess.PIPE)
            p.communicate(("%s:%s\n" % (uname, pw.get_text())).encode())
            win.close()
            self.refresh()
        btn.connect("clicked", do_create)
        box.append(btn)
        win.set_child(box)
        win.present()

    def _set_admin(self, username, make_admin):
        if make_admin:
            sh(["pkexec", "gpasswd", "-a", username, "sudo"])
        else:
            sh(["pkexec", "gpasswd", "-d", username, "sudo"])

    def _change_password(self, username):
        win = Gtk.Window(title="Parola noua: %s" % username, transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        pw = Gtk.PasswordEntry()
        pw.set_show_peek_icon(True)
        btn = Gtk.Button(label="Aplica")
        btn.add_css_class("suggested-action")

        def do(*a):
            p = subprocess.Popen(["pkexec", "chpasswd"], stdin=subprocess.PIPE)
            p.communicate(("%s:%s\n" % (username, pw.get_text())).encode())
            win.close()
        btn.connect("clicked", do)
        box.append(pw)
        box.append(btn)
        win.set_child(box)
        win.present()

    def _change_avatar(self, username):
        d = Gtk.FileDialog()
        d.open(self, None, lambda dd, rr: self._avatar_set(dd, rr, username))

    def _avatar_set(self, dialog, res, username):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if f:
            sh(["pkexec", "cp", f.get_path(), "/var/lib/AccountsService/icons/" + username])

    def _lock(self, username):
        sh(["pkexec", "passwd", "-l", username])
        self._notify("Cont blocat: %s" % username)

    def _delete(self, username):
        dialog = Gtk.AlertDialog()
        dialog.set_message("Stergi utilizatorul %s?" % username)
        dialog.set_buttons(["Anuleaza", "Sterge (pastreaza home)", "Sterge tot"])
        dialog.set_cancel_button(0)
        dialog.choose(self, None, lambda d, r: self._do_delete(d, r, username))

    def _do_delete(self, dialog, res, username):
        try:
            choice = dialog.choose_finish(res)
        except GLib.Error:
            return
        if choice == 1:
            sh(["pkexec", "userdel", username])
        elif choice == 2:
            sh(["pkexec", "userdel", "-r", username])
        self.refresh()

    def _notify(self, text):
        GLib.spawn_command_line_async("notify-send 'BoboUsers' '%s'" % text.replace("'", ""))


class BoboUsersApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboUsersWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboUsers 1.0.0 (BOBO OS)")
        return 0
    return BoboUsersApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
