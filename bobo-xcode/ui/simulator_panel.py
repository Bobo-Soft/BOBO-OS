"""
iOS simulator control panel for BoboXcode.
Device selector + start/stop + status. QEMU opens its own GTK display window;
this panel manages its lifecycle and (when running) a QMP touch bridge.
"""
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

from simulator.qemu_manager import QEMUSimulator
from simulator.device_profiles import list_devices
from simulator.touch_bridge import TouchBridge


class SimulatorPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_top(10)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.qemu = QEMUSimulator()
        self.touch = None

        # toolbar
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._devices = list_devices()
        self.device_dd = Gtk.DropDown.new_from_strings([d[1] for d in self._devices])
        bar.append(Gtk.Label(label="Device:"))
        bar.append(self.device_dd)
        self.start_btn = Gtk.Button(label="Start")
        self.start_btn.add_css_class("suggested-action")
        self.start_btn.connect("clicked", lambda *a: self.start_simulator(None))
        bar.append(self.start_btn)
        self.stop_btn = Gtk.Button(label="Stop")
        self.stop_btn.set_sensitive(False)
        self.stop_btn.connect("clicked", lambda *a: self.stop_simulator())
        bar.append(self.stop_btn)
        self.append(bar)

        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.set_text(self.qemu.status_text())
        self.append(self.status)

        hint = Gtk.Label(xalign=0, wrap=True)
        hint.add_css_class("dim-label")
        hint.set_text("Place an iOS .qcow2/.img in /var/lib/bobo-xcode/simulators/. "
                      "QEMU opens the device display in its own window; mouse acts as touch.")
        self.append(hint)

    def _selected_device_key(self):
        idx = self.device_dd.get_selected()
        return self._devices[idx][0] if 0 <= idx < len(self._devices) else "iphone15"

    def start_simulator(self, project_path):
        device = self._selected_device_key()
        ok = self.qemu.start(device=device)
        if ok:
            self.status.set_text("Simulator starting (%s)..." % device)
            self.start_btn.set_sensitive(False)
            self.stop_btn.set_sensitive(True)
            # connect the touch bridge shortly after QEMU exposes the QMP socket
            GLib.timeout_add_seconds(2, self._connect_touch)
        else:
            self.status.set_text(self.qemu.status_text())

    def _connect_touch(self):
        try:
            self.touch = TouchBridge(self.qemu.qmp_socket_path(), self._selected_device_key())
            if self.touch.connect():
                self.status.set_text("Simulator running — touch bridge active.")
            else:
                self.status.set_text("Simulator running.")
        except Exception:
            self.status.set_text("Simulator running.")
        return False

    def stop_simulator(self):
        if self.touch:
            self.touch.disconnect()
            self.touch = None
        self.qemu.stop()
        self.start_btn.set_sensitive(True)
        self.stop_btn.set_sensitive(False)
        self.status.set_text("Simulator stopped.")
