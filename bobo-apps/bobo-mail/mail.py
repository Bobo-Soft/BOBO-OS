#!/usr/bin/env python3
# =============================================================================
# BoboMail - Client de email pentru BOBO OS (APP 08)
# GTK4 + imaplib/smtplib (stdlib) + keyring. Multi-cont IMAP/SMTP, dosare,
# citire, compunere, raspuns, cautare. Parole in keyring sistem.
# =============================================================================
import os
import sys
import json
import email
import imaplib
import smtplib
import threading
from email.header import decode_header
from email.mime.text import MIMEText
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

try:
    import keyring
except ImportError:
    keyring = None

APP_ID = "os.bobo.Mail"
CONF_DIR = os.path.expanduser("~/.config/bobo-mail")
ACCOUNTS_FILE = os.path.join(CONF_DIR, "accounts.json")

# Detectie automata setari pentru provideri comuni
PROVIDERS = {
    "gmail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 587),
    "outlook.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "hotmail.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "yahoo.com": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587),
    "fastmail.com": ("imap.fastmail.com", 993, "smtp.fastmail.com", 465),
}


def load_accounts():
    try:
        with open(ACCOUNTS_FILE) as fh:
            return json.load(fh)
    except Exception:
        return []


def save_accounts(accs):
    os.makedirs(CONF_DIR, exist_ok=True)
    with open(ACCOUNTS_FILE, "w") as fh:
        json.dump(accs, fh, indent=2)


def get_password(email_addr):
    if keyring:
        try:
            return keyring.get_password("bobo-mail", email_addr)
        except Exception:
            return None
    return None


def set_password(email_addr, pw):
    if keyring:
        try:
            keyring.set_password("bobo-mail", email_addr, pw)
            return True
        except Exception:
            return False
    return False


def _decode(s):
    if not s:
        return ""
    parts = decode_header(s)
    out = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            out += text.decode(enc or "utf-8", errors="replace")
        else:
            out += text
    return out


class BoboMailWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboMail")
        self.set_default_size(1000, 660)
        self.accounts = load_accounts()
        self.imap = None
        self.current_account = None
        self.messages = []  # (uid, from, subject, date)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        self.account_combo = Gtk.DropDown.new_from_strings(
            [a["email"] for a in self.accounts] or ["(niciun cont)"])
        self.account_combo.connect("notify::selected", self._on_account_changed)
        header.pack_start(self.account_combo)
        add_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_btn.set_tooltip_text("Adauga cont")
        add_btn.connect("clicked", lambda *a: self.account_wizard())
        header.pack_start(add_btn)
        compose_btn = Gtk.Button(label="Compune")
        compose_btn.add_css_class("suggested-action")
        compose_btn.connect("clicked", lambda *a: self.compose())
        header.pack_end(compose_btn)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Cauta")
        self.search_entry.connect("activate", self._on_search)
        header.pack_end(self.search_entry)

        # layout: dosare | lista mesaje | continut
        split1 = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(split1)

        folders_sw = Gtk.ScrolledWindow()
        folders_sw.set_size_request(180, -1)
        self.folder_list = Gtk.ListBox()
        self.folder_list.connect("row-activated", self._on_folder_activated)
        folders_sw.set_child(self.folder_list)
        split1.set_start_child(folders_sw)
        split1.set_resize_start_child(False)

        split2 = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        split1.set_end_child(split2)

        msg_sw = Gtk.ScrolledWindow()
        msg_sw.set_size_request(320, -1)
        self.msg_store = Gtk.ListStore(str, str, str, str)  # from, subject, date, uid
        self.msg_tree = Gtk.TreeView(model=self.msg_store)
        for i, t in enumerate(["Expeditor", "Subiect", "Data"]):
            col = Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            self.msg_tree.append_column(col)
        self.msg_tree.connect("row-activated", self._on_msg_activated)
        msg_sw.set_child(self.msg_tree)
        split2.set_start_child(msg_sw)
        split2.set_resize_start_child(False)

        body_sw = Gtk.ScrolledWindow()
        body_sw.set_hexpand(True)
        self.body_view = Gtk.TextView()
        self.body_view.set_editable(False)
        self.body_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.body_view.set_left_margin(12)
        self.body_view.set_top_margin(12)
        body_sw.set_child(self.body_view)
        split2.set_end_child(body_sw)

        self.status = Gtk.Label(label="", xalign=0)
        if self.accounts:
            self.current_account = self.accounts[0]
            self._connect_async()
        else:
            self._set_body("Adauga un cont (butonul +) pentru a incepe.")

    # ----------------------------------------------------------- wizard cont
    def account_wizard(self):
        win = Gtk.Window(title="Adauga cont email", transient_for=self, modal=True)
        win.set_default_size(420, -1)
        grid = Gtk.Grid(row_spacing=8, column_spacing=8, margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        fields = {}
        rows = [("Email", "email"), ("Parola", "password"), ("IMAP host", "imap_host"),
                ("IMAP port", "imap_port"), ("SMTP host", "smtp_host"), ("SMTP port", "smtp_port")]
        for r, (label, key) in enumerate(rows):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, r, 1, 1)
            entry = Gtk.Entry()
            if key == "password":
                entry.set_visibility(False)
            grid.attach(entry, 1, r, 1, 1)
            fields[key] = entry

        def autodetect(*a):
            addr = fields["email"].get_text()
            domain = addr.split("@")[-1].lower()
            if domain in PROVIDERS:
                ih, ip, sh, sp = PROVIDERS[domain]
                fields["imap_host"].set_text(ih)
                fields["imap_port"].set_text(str(ip))
                fields["smtp_host"].set_text(sh)
                fields["smtp_port"].set_text(str(sp))
        fields["email"].connect("changed", autodetect)

        save_btn = Gtk.Button(label="Salveaza si conecteaza")
        save_btn.add_css_class("suggested-action")

        def do_save(*a):
            acc = {
                "email": fields["email"].get_text(),
                "imap_host": fields["imap_host"].get_text(),
                "imap_port": int(fields["imap_port"].get_text() or 993),
                "smtp_host": fields["smtp_host"].get_text(),
                "smtp_port": int(fields["smtp_port"].get_text() or 587),
            }
            pw = fields["password"].get_text()
            if not set_password(acc["email"], pw):
                acc["_password_plain"] = pw  # fallback daca lipseste keyring
            self.accounts.append(acc)
            save_accounts(self.accounts)
            self.account_combo.set_model(Gtk.StringList.new([a["email"] for a in self.accounts]))
            self.account_combo.set_selected(len(self.accounts) - 1)
            self.current_account = acc
            win.close()
            self._connect_async()
        save_btn.connect("clicked", do_save)
        grid.attach(save_btn, 0, len(rows), 2, 1)
        win.set_child(grid)
        win.present()

    # ----------------------------------------------------------- IMAP
    def _connect_async(self):
        if not self.current_account:
            return
        self._set_body("Conectare la %s ..." % self.current_account["email"])
        threading.Thread(target=self._connect, daemon=True).start()

    def _connect(self):
        acc = self.current_account
        pw = get_password(acc["email"]) or acc.get("_password_plain", "")
        try:
            self.imap = imaplib.IMAP4_SSL(acc["imap_host"], acc.get("imap_port", 993))
            self.imap.login(acc["email"], pw)
            typ, folders = self.imap.list()
            names = []
            for f in folders or []:
                line = f.decode(errors="replace")
                name = line.split(' "')[-1].strip('"') if '"' in line else line.split()[-1]
                names.append(name)
            GLib.idle_add(self._populate_folders, names)
            GLib.idle_add(self._load_folder, "INBOX")
        except Exception as e:
            GLib.idle_add(self._set_body, "Eroare conectare: %s" % e)

    def _populate_folders(self, names):
        child = self.folder_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.folder_list.remove(child)
            child = nxt
        for name in (names or ["INBOX"]):
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label=name, xalign=0, margin_top=6, margin_bottom=6, margin_start=8))
            row._folder = name
            self.folder_list.append(row)

    def _on_folder_activated(self, lb, row):
        if hasattr(row, "_folder"):
            threading.Thread(target=self._load_folder, args=(row._folder,), daemon=True).start()

    def _load_folder(self, folder):
        try:
            self.imap.select(folder, readonly=True)
            typ, data = self.imap.search(None, "ALL")
            ids = data[0].split()[-50:]  # ultimele 50
            rows = []
            for num in reversed(ids):
                typ, msg_data = self.imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                rows.append((_decode(msg.get("From")), _decode(msg.get("Subject")),
                             _decode(msg.get("Date"))[:25], num.decode()))
            GLib.idle_add(self._show_messages, rows)
        except Exception as e:
            GLib.idle_add(self._set_body, "Eroare dosar: %s" % e)

    def _show_messages(self, rows):
        self.msg_store.clear()
        for r in rows:
            self.msg_store.append(list(r))

    def _on_msg_activated(self, tree, path, col):
        it = self.msg_store.get_iter(path)
        uid = self.msg_store.get_value(it, 3)
        threading.Thread(target=self._load_message, args=(uid,), daemon=True).start()

    def _load_message(self, uid):
        try:
            typ, data = self.imap.fetch(uid.encode(), "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            body = self._extract_body(msg)
            header = "De la: %s\nSubiect: %s\nData: %s\n%s\n\n" % (
                _decode(msg.get("From")), _decode(msg.get("Subject")),
                _decode(msg.get("Date")), "-" * 50)
            GLib.idle_add(self._set_body, header + body)
        except Exception as e:
            GLib.idle_add(self._set_body, "Eroare mesaj: %s" % e)

    def _extract_body(self, msg):
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get("Content-Disposition"))
                if ctype == "text/plain" and "attachment" not in disp:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                    return self._strip_html(html)
            return "(continut indisponibil)"
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        return str(msg.get_payload())

    def _strip_html(self, html):
        try:
            import html2text
            return html2text.html2text(html)
        except Exception:
            import re
            return re.sub(r"<[^>]+>", "", html)

    def _on_search(self, entry):
        term = entry.get_text()
        if not self.imap or not term:
            return
        def do():
            try:
                typ, data = self.imap.search(None, "TEXT", '"%s"' % term)
                ids = data[0].split()[-50:]
                rows = []
                for num in reversed(ids):
                    typ, md = self.imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                    msg = email.message_from_bytes(md[0][1])
                    rows.append((_decode(msg.get("From")), _decode(msg.get("Subject")),
                                 _decode(msg.get("Date"))[:25], num.decode()))
                GLib.idle_add(self._show_messages, rows)
            except Exception as e:
                GLib.idle_add(self._set_body, "Cautare esuata: %s" % e)
        threading.Thread(target=do, daemon=True).start()

    # ----------------------------------------------------------- compose
    def compose(self, to="", subject="", body=""):
        if not self.current_account:
            self._set_body("Adauga un cont mai intai.")
            return
        win = Gtk.Window(title="Mesaj nou", transient_for=self, modal=True)
        win.set_default_size(560, 480)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
        to_entry = Gtk.Entry()
        to_entry.set_placeholder_text("Catre")
        to_entry.set_text(to)
        subj_entry = Gtk.Entry()
        subj_entry.set_placeholder_text("Subiect")
        subj_entry.set_text(subject)
        body_view = Gtk.TextView()
        body_view.set_wrap_mode(Gtk.WrapMode.WORD)
        body_view.get_buffer().set_text(body)
        body_sw = Gtk.ScrolledWindow()
        body_sw.set_vexpand(True)
        body_sw.set_child(body_view)
        send = Gtk.Button(label="Trimite")
        send.add_css_class("suggested-action")

        def do_send(*a):
            buf = body_view.get_buffer()
            text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
            threading.Thread(target=self._send_mail,
                             args=(to_entry.get_text(), subj_entry.get_text(), text), daemon=True).start()
            win.close()
        send.connect("clicked", do_send)
        box.append(to_entry)
        box.append(subj_entry)
        box.append(body_sw)
        box.append(send)
        win.set_child(box)
        win.present()

    def _send_mail(self, to, subject, body):
        acc = self.current_account
        pw = get_password(acc["email"]) or acc.get("_password_plain", "")
        msg = MIMEText(body)
        msg["From"] = acc["email"]
        msg["To"] = to
        msg["Subject"] = subject
        try:
            port = acc.get("smtp_port", 587)
            if port == 465:
                s = smtplib.SMTP_SSL(acc["smtp_host"], port)
            else:
                s = smtplib.SMTP(acc["smtp_host"], port)
                s.starttls()
            s.login(acc["email"], pw)
            s.send_message(msg)
            s.quit()
            GLib.idle_add(self._set_body, "Mesaj trimis catre %s" % to)
        except Exception as e:
            GLib.idle_add(self._set_body, "Trimitere esuata: %s" % e)

    # ----------------------------------------------------------- helpers
    def _on_account_changed(self, combo, _):
        idx = combo.get_selected()
        if 0 <= idx < len(self.accounts):
            self.current_account = self.accounts[idx]
            self._connect_async()

    def _set_body(self, text):
        self.body_view.get_buffer().set_text(text)


class BoboMailApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboMailWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboMail 1.0.0 (BOBO OS)")
        return 0
    return BoboMailApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
