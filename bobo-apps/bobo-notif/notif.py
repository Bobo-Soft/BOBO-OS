#!/usr/bin/env python3
# =============================================================================
# BoboNotif - Centru de notificari pentru BOBO OS (APP 17)
# Implementeaza serverul D-Bus org.freedesktop.Notifications + popup-uri +
# centru de notificari (panel) + istoric SQLite + Do Not Disturb.
# Mod: --daemon = server D-Bus; implicit = deschide centrul; --toggle la fel.
# =============================================================================
import os
import sys
import sqlite3
import time
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk  # noqa: E402

APP_ID = "os.bobo.Notif"
DATA_DIR = os.path.expanduser("~/.local/share/bobo-notif")
DB = os.path.join(DATA_DIR, "history.db")
DND_FLAG = os.path.expanduser("~/.cache/bobo-os/dnd.flag")

NODE_XML = """
<node>
  <interface name="org.freedesktop.Notifications">
    <method name="Notify">
      <arg type="s" direction="in"/>
      <arg type="u" direction="in"/>
      <arg type="s" direction="in"/>
      <arg type="s" direction="in"/>
      <arg type="s" direction="in"/>
      <arg type="as" direction="in"/>
      <arg type="a{sv}" direction="in"/>
      <arg type="i" direction="in"/>
      <arg type="u" direction="out"/>
    </method>
    <method name="CloseNotification"><arg type="u" direction="in"/></method>
    <method name="GetCapabilities"><arg type="as" direction="out"/></method>
    <method name="GetServerInformation">
      <arg type="s" direction="out"/>
      <arg type="s" direction="out"/>
      <arg type="s" direction="out"/>
      <arg type="s" direction="out"/>
    </method>
    <signal name="NotificationClosed"><arg type="u"/><arg type="u"/></signal>
    <signal name="ActionInvoked"><arg type="u"/><arg type="s"/></signal>
  </interface>
</node>
"""


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS notif (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "app TEXT, icon TEXT, summary TEXT, body TEXT, ts INTEGER)")
    return con


def dnd_active():
    return os.path.exists(DND_FLAG)


# =============================================================================
# Serverul D-Bus (daemon)
# =============================================================================
class NotificationServer:
    def __init__(self):
        self.next_id = 1
        self.con = _db()
        self.popups = []
        self.reg_id = None
        node = Gio.DBusNodeInfo.new_for_xml(NODE_XML)
        self.iface = node.interfaces[0]
        Gio.bus_own_name(Gio.BusType.SESSION, "org.freedesktop.Notifications",
                         Gio.BusNameOwnerFlags.REPLACE, self._on_bus_acquired, None, None)

    def _on_bus_acquired(self, conn, name):
        conn.register_object("/org/freedesktop/Notifications", self.iface, self._handle, None, None)

    def _handle(self, conn, sender, path, iface, method, params, invocation):
        if method == "Notify":
            app, replaces, icon, summary, body, actions, hints, timeout = params.unpack()
            nid = replaces or self.next_id
            if not replaces:
                self.next_id += 1
            self.con.execute("INSERT INTO notif(app,icon,summary,body,ts) VALUES(?,?,?,?,?)",
                             (app, icon, summary, body, int(time.time())))
            self.con.commit()
            if not dnd_active():
                self._show_popup(app, icon, summary, body)
            invocation.return_value(GLib.Variant("(u)", (nid,)))
        elif method == "CloseNotification":
            invocation.return_value(None)
        elif method == "GetCapabilities":
            invocation.return_value(GLib.Variant("(as)", (["body", "actions", "icon-static"],)))
        elif method == "GetServerInformation":
            invocation.return_value(GLib.Variant("(ssss)", ("BoboNotif", "BOBO OS", "1.0", "1.2")))
        else:
            invocation.return_value(None)

    def _show_popup(self, app, icon, summary, body):
        win = Gtk.Window()
        win.set_decorated(False)
        win.set_default_size(360, -1)
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        card.add_css_class("bobo-notif-popup")
        card.set_margin_top(8)
        card.set_margin_bottom(8)
        card.set_margin_start(10)
        card.set_margin_end(10)
        card.append(Gtk.Image.new_from_icon_name(icon or "dialog-information-symbolic"))
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        s = Gtk.Label(label=summary, xalign=0)
        s.add_css_class("title-4")
        bd = Gtk.Label(label=body, xalign=0, wrap=True)
        tb.append(s)
        tb.append(bd)
        card.append(tb)
        win.set_child(card)
        self._css(win)
        win.present()
        GLib.timeout_add_seconds(5, lambda: (win.close(), False)[1])


# =============================================================================
# Centrul de notificari (panel)
# =============================================================================
class NotifCenter(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Notificari")
        self.set_default_size(380, 640)
        self.con = _db()

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        self.dnd_btn = Gtk.ToggleButton()
        self.dnd_btn.set_icon_name("notifications-disabled-symbolic")
        self.dnd_btn.set_active(dnd_active())
        self.dnd_btn.set_tooltip_text("Do Not Disturb")
        self.dnd_btn.connect("toggled", self._toggle_dnd)
        header.pack_start(self.dnd_btn)
        clear = Gtk.Button(label="Sterge toate")
        clear.connect("clicked", lambda *a: self._clear_all())
        header.pack_end(clear)

        sw = Gtk.ScrolledWindow()
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.box.set_margin_top(8)
        self.box.set_margin_start(8)
        self.box.set_margin_end(8)
        sw.set_child(self.box)
        self.set_child(sw)
        self._load()

    def _load(self):
        child = self.box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.box.remove(child)
            child = nxt
        rows = self.con.execute("SELECT id,app,icon,summary,body,ts FROM notif ORDER BY ts DESC LIMIT 50").fetchall()
        if not rows:
            self.box.append(Gtk.Label(label="Nicio notificare", xalign=0))
            return
        # grupare pe aplicatie
        groups = {}
        for r in rows:
            groups.setdefault(r[1] or "Sistem", []).append(r)
        for app, items in groups.items():
            hdr = Gtk.Label(xalign=0)
            hdr.set_markup("<b>%s</b>" % app)
            self.box.append(hdr)
            for nid, _app, icon, summary, body, ts in items:
                card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                card.add_css_class("card")
                card.append(Gtk.Image.new_from_icon_name(icon or "dialog-information-symbolic"))
                tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                tb.set_hexpand(True)
                s = Gtk.Label(label=summary, xalign=0)
                s.add_css_class("title-4")
                bd = Gtk.Label(label=body, xalign=0, wrap=True)
                tm = Gtk.Label(label=time.strftime("%H:%M", time.localtime(ts)), xalign=0)
                tm.add_css_class("dim-label")
                tb.append(s)
                tb.append(bd)
                tb.append(tm)
                card.append(tb)
                x = Gtk.Button.new_from_icon_name("window-close-symbolic")
                x.add_css_class("flat")
                x.connect("clicked", lambda b, i=nid: self._dismiss(i))
                card.append(x)
                self.box.append(card)

    def _dismiss(self, nid):
        self.con.execute("DELETE FROM notif WHERE id=?", (nid,))
        self.con.commit()
        self._load()

    def _clear_all(self):
        self.con.execute("DELETE FROM notif")
        self.con.commit()
        self._load()

    def _toggle_dnd(self, btn):
        os.makedirs(os.path.dirname(DND_FLAG), exist_ok=True)
        if btn.get_active():
            open(DND_FLAG, "w").close()
        else:
            try:
                os.remove(DND_FLAG)
            except Exception:
                pass


def _apply_css():
    css = Gtk.CssProvider()
    css.load_from_data(b"""
    .bobo-notif-popup { background: rgba(22,33,62,0.97); border-radius: 12px;
        border: 1px solid #4a9eff; }
    """)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


# atasam helper CSS si la server
NotificationServer._css = lambda self, win: _apply_css()


class BoboNotifApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        _apply_css()
        NotifCenter(self).present()


def run_daemon():
    _apply_css() if Gdk.Display.get_default() else None
    NotificationServer()
    GLib.MainLoop().run()


def main():
    if "--version" in sys.argv:
        print("BoboNotif 1.0.0 (BOBO OS)")
        return 0
    if "--daemon" in sys.argv:
        run_daemon()
        return 0
    return BoboNotifApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
