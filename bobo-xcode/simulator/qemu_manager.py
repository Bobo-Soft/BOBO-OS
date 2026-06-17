"""
iOS simulator via QEMU (aarch64) for BoboXcode.
The user supplies the iOS image (we do not distribute it, for legal reasons).
Exposes a QMP socket so touch_bridge can inject pointer events.
"""
import subprocess
import os
import shutil
import socket
import time
from simulator.device_profiles import get_profile

QMP_SOCK = "/tmp/bobo-xcode-qmp.sock"
SEARCH_PATHS = [
    "/var/lib/bobo-xcode/simulators/",
    os.path.expanduser("~/iOS-Simulators/"),
]


class QEMUSimulator:
    def __init__(self):
        self.process = None
        self.device = "iphone15"

    def qemu_available(self) -> bool:
        return shutil.which("qemu-system-aarch64") is not None

    def start(self, device: str = "iphone15", ios_image_path: str = None) -> bool:
        """Start QEMU for the given device. Returns False if image/qemu missing."""
        if self.is_running():
            return True
        if not self.qemu_available():
            return False
        self.device = device
        profile = get_profile(device)
        image = ios_image_path or self._find_ios_image()
        if not image or not os.path.exists(image):
            return False

        cmd = [
            "qemu-system-aarch64",
            "-M", "virt", "-cpu", "max",
            "-m", str(profile["ram_mb"]),
            "-smp", str(profile["cores"]),
            "-drive", "file=%s,format=qcow2,if=virtio" % image,
            "-device", "virtio-gpu-pci",
            "-display", "gtk",
            "-device", "usb-ehci", "-device", "usb-tablet", "-device", "usb-kbd",
            "-netdev", "user,id=net0", "-device", "virtio-net-pci,netdev=net0",
            "-qmp", "unix:%s,server,nowait" % QMP_SOCK,
        ]
        try:
            self.process = subprocess.Popen(cmd)
            return True
        except Exception:
            self.process = None
            return False

    def stop(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        try:
            if os.path.exists(QMP_SOCK):
                os.remove(QMP_SOCK)
        except Exception:
            pass

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def qmp_socket_path(self) -> str:
        return QMP_SOCK

    def _find_ios_image(self):
        for path in SEARCH_PATHS:
            if os.path.isdir(path):
                for f in sorted(os.listdir(path)):
                    if f.endswith((".qcow2", ".img")):
                        return os.path.join(path, f)
        return None

    def status_text(self) -> str:
        if not self.qemu_available():
            return "QEMU not installed (run a FULL build or install qemu-system-arm)."
        if not self._find_ios_image():
            return ("No iOS image found. Place a .qcow2/.img in "
                    "/var/lib/bobo-xcode/simulators/ to enable the simulator.")
        return "Simulator running." if self.is_running() else "Ready to start."
