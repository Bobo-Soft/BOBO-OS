"""
First-run setup wizard for the BoboiOS Bridge.
Opens automatically on the first 'Publish' click if the Bridge is unconfigured.
Collects Mac cloud SSH credentials + Apple Developer info, tests the SSH link,
and stores everything encrypted via MacConnector.
"""
import threading
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

from bridge.mac_connector import MacConnector


class BridgeSetupDialog(Gtk.Window):
    def __init__(self, parent):
        super().__init__(title="Configure BoboiOS Bridge", transient_for=parent, modal=True)
        self.set_default_size(520, 640)
        self.mac = MacConnector()
        self._build_ui()

    def _build_ui(self):
        outer = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        outer.set_child(box)
        self.set_child(outer)

        title = Gtk.Label()
        title.set_markup("<b>BoboiOS Bridge — Setup</b>\n<small>Configure once, publish anywhere.</small>")
        title.set_halign(Gtk.Align.START)
        box.append(title)
        box.append(Gtk.Separator())

        # Section 1 — Mac cloud
        s1 = Gtk.Label()
        s1.set_markup("<b>1. Mac Cloud (MacStadium recommended)</b>")
        s1.set_halign(Gtk.Align.START)
        box.append(s1)
        h1 = Gtk.Label(label="Create an account on macstadium.com (pay-per-use). "
                             "Any Mac with SSH + Xcode works.")
        h1.add_css_class("dim-label")
        h1.set_halign(Gtk.Align.START)
        h1.set_wrap(True)
        box.append(h1)

        grid = Gtk.Grid(row_spacing=8, column_spacing=12)
        box.append(grid)
        grid.attach(Gtk.Label(label="Mac host:", xalign=0), 0, 0, 1, 1)
        self.host_entry = Gtk.Entry(hexpand=True)
        self.host_entry.set_placeholder_text("e.g. mac-mini.macstadium.com")
        grid.attach(self.host_entry, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="SSH port:", xalign=0), 0, 1, 1, 1)
        self.port_entry = Gtk.Entry()
        self.port_entry.set_text("22")
        grid.attach(self.port_entry, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label="Username:", xalign=0), 0, 2, 1, 1)
        self.user_entry = Gtk.Entry(hexpand=True)
        self.user_entry.set_placeholder_text("e.g. administrator")
        grid.attach(self.user_entry, 1, 2, 1, 1)
        grid.attach(Gtk.Label(label="Password:", xalign=0), 0, 3, 1, 1)
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        grid.attach(self.password_entry, 1, 3, 1, 1)

        test_btn = Gtk.Button(label="Test connection")
        test_btn.connect("clicked", self._on_test)
        box.append(test_btn)
        self.test_result = Gtk.Label(xalign=0, wrap=True)
        box.append(self.test_result)

        # Section 2 — Apple Developer
        box.append(Gtk.Separator())
        s2 = Gtk.Label()
        s2.set_markup("<b>2. Apple Developer Account</b>")
        s2.set_halign(Gtk.Align.START)
        box.append(s2)
        h2 = Gtk.Label(label="Requires Apple Developer Program. Use an app-specific "
                             "password from appleid.apple.com.")
        h2.add_css_class("dim-label")
        h2.set_halign(Gtk.Align.START)
        h2.set_wrap(True)
        box.append(h2)

        grid2 = Gtk.Grid(row_spacing=8, column_spacing=12)
        box.append(grid2)
        grid2.attach(Gtk.Label(label="Apple ID:", xalign=0), 0, 0, 1, 1)
        self.apple_id_entry = Gtk.Entry(hexpand=True)
        self.apple_id_entry.set_placeholder_text("developer@example.com")
        grid2.attach(self.apple_id_entry, 1, 0, 1, 1)
        grid2.attach(Gtk.Label(label="App-specific\npassword:", xalign=0), 0, 1, 1, 1)
        self.apple_pass_entry = Gtk.PasswordEntry()
        self.apple_pass_entry.set_show_peek_icon(True)
        grid2.attach(self.apple_pass_entry, 1, 1, 1, 1)

        box.append(Gtk.Separator())
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _: self.close())
        btn_box.append(cancel)
        save = Gtk.Button(label="Save & enable Bridge")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._on_save)
        btn_box.append(save)
        box.append(btn_box)

        if not self.mac.dependencies_ok():
            self.test_result.set_markup(
                "<span foreground='#ffb454'>Note: paramiko/cryptography not installed "
                "(lean ISO). Run a FULL build to enable live publishing.</span>")

    def _collect(self):
        try:
            port = int(self.port_entry.get_text() or 22)
        except ValueError:
            port = 22
        return {
            "mac_host": self.host_entry.get_text().strip(),
            "mac_port": port,
            "mac_user": self.user_entry.get_text().strip(),
            "mac_password": self.password_entry.get_text(),
            "apple_id": self.apple_id_entry.get_text().strip(),
            "apple_app_password": self.apple_pass_entry.get_text(),
        }

    def _on_test(self, btn):
        self.test_result.set_text("Testing connection...")
        cfg = self._collect()

        def work():
            try:
                self.mac.save_config(cfg)
                self.mac.connect()
                info = self.mac._exec("sw_vers -productName 2>/dev/null; "
                                      "xcodebuild -version 2>/dev/null | head -1")
                self.mac.disconnect()
                GLib.idle_add(self.test_result.set_markup,
                              "<span foreground='#6bcb77'>Connected: %s</span>" % info.strip().replace("\n", " "))
            except Exception as e:
                GLib.idle_add(self.test_result.set_markup,
                              "<span foreground='#ff6b6b'>Error: %s</span>" % e)
        threading.Thread(target=work, daemon=True).start()

    def _on_save(self, btn):
        cfg = self._collect()
        if not all([cfg["mac_host"], cfg["mac_user"], cfg["apple_id"], cfg["apple_app_password"]]):
            self.test_result.set_markup("<span foreground='#ff6b6b'>Fill in all fields.</span>")
            return
        self.mac.save_config(cfg)
        self.test_result.set_markup("<span foreground='#6bcb77'>Bridge configured. You can publish now.</span>")
        GLib.timeout_add(1500, self.close)
