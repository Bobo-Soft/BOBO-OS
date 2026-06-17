"""
Touch bridge for the BoboXcode simulator.
Translates mouse events from the GTK simulator panel into absolute pointer
events injected into QEMU over its QMP socket (input-send-event).
"""
import json
import socket
import os
from simulator.device_profiles import get_profile


class TouchBridge:
    def __init__(self, qmp_socket_path: str, device: str = "iphone15"):
        self.qmp_path = qmp_socket_path
        self.device = device
        self.sock = None
        self._id = 0

    # ------------------------------------------------------------------ qmp
    def connect(self) -> bool:
        if not os.path.exists(self.qmp_path):
            return False
        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(3)
            self.sock.connect(self.qmp_path)
            # QMP greeting + capabilities negotiation
            self.sock.recv(4096)
            self._cmd("qmp_capabilities")
            return True
        except Exception:
            self.sock = None
            return False

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _cmd(self, execute: str, arguments: dict = None) -> dict:
        if not self.sock:
            return {}
        payload = {"execute": execute}
        if arguments:
            payload["arguments"] = arguments
        try:
            self.sock.sendall((json.dumps(payload) + "\r\n").encode())
            data = self.sock.recv(8192)
            return json.loads(data.decode(errors="replace").splitlines()[0]) if data else {}
        except Exception:
            return {}

    # ------------------------------------------------------------------ touch
    def _to_abs(self, x: int, y: int, widget_w: int, widget_h: int):
        """Map widget pixel coords to QEMU's 0..32767 absolute axis range."""
        profile = get_profile(self.device)
        fx = max(0.0, min(1.0, x / max(1, widget_w)))
        fy = max(0.0, min(1.0, y / max(1, widget_h)))
        return int(fx * 32767), int(fy * 32767)

    def tap(self, x: int, y: int, widget_w: int, widget_h: int):
        """Simulate a finger tap (down + up) at the given widget coordinates."""
        ax, ay = self._to_abs(x, y, widget_w, widget_h)
        self._move_abs(ax, ay)
        self._button(True)
        self._button(False)

    def touch_down(self, x, y, w, h):
        ax, ay = self._to_abs(x, y, w, h)
        self._move_abs(ax, ay)
        self._button(True)

    def touch_move(self, x, y, w, h):
        ax, ay = self._to_abs(x, y, w, h)
        self._move_abs(ax, ay)

    def touch_up(self, x, y, w, h):
        self._button(False)

    def _move_abs(self, ax, ay):
        self._cmd("input-send-event", {"events": [
            {"type": "abs", "data": {"axis": "x", "value": ax}},
            {"type": "abs", "data": {"axis": "y", "value": ay}},
        ]})

    def _button(self, down: bool):
        self._cmd("input-send-event", {"events": [
            {"type": "btn", "data": {"down": down, "button": "left"}}]})
