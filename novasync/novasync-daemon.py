#!/usr/bin/env python3
"""
BOBO OS — NovaSync Daemon (Phase 7.1)
E:\BOBO-OS\novasync\novasync-daemon.py

Manages cloud sync for all connectors.
D-Bus interface for tray status updates.
Rate-limits syncing; pauses on low battery.
"""

import os
import sys
import time
import threading
import logging
import json
from pathlib import Path
from enum import Enum

try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False

LOG_PATH = Path("/var/log/novasync.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [NovaSync] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("novasync")

SYNC_INTERVAL = 300   # 5 minutes between sync passes
BATTERY_PAUSE_THRESHOLD = 20  # % — pause sync below this level

BOBO_CONFIG = Path("/etc/bobo-os.conf")


class SyncStatus(str, Enum):
    SYNCED    = "synced"
    SYNCING   = "syncing"
    CONFLICT  = "conflict"
    ERROR     = "error"
    PAUSED    = "paused"


STATUS_ICONS = {
    SyncStatus.SYNCED:   "✅",
    SyncStatus.SYNCING:  "↺",
    SyncStatus.CONFLICT: "⚠️",
    SyncStatus.ERROR:    "❌",
    SyncStatus.PAUSED:   "⏸",
}


# ── Connector base class ──────────────────────────────────────────────────────

class SyncConnector:
    """Base class for all cloud sync connectors."""

    name: str = "base"
    enabled_config_key: str = "NOVASYNC_BASE"

    def __init__(self):
        self.status = SyncStatus.SYNCED
        self.last_sync: float = 0
        self.error_msg: str = ""

    def is_enabled(self) -> bool:
        if not BOBO_CONFIG.exists():
            return False
        for line in BOBO_CONFIG.read_text().splitlines():
            if line.startswith(self.enabled_config_key + "="):
                return line.split("=", 1)[1].strip().lower() in ("true", "1", "yes")
        return False

    def sync(self) -> SyncStatus:
        raise NotImplementedError

    def get_status(self) -> dict:
        return {
            "name":      self.name,
            "status":    self.status.value,
            "icon":      STATUS_ICONS[self.status],
            "last_sync": self.last_sync,
            "error":     self.error_msg,
        }


# ── iCloud connector ──────────────────────────────────────────────────────────

class ICloudConnector(SyncConnector):
    name = "iCloud"
    enabled_config_key = "NOVASYNC_ICLOUD"

    def sync(self) -> SyncStatus:
        try:
            from novasync.icloud.icloud_connector import ICloudSync
            syncer = ICloudSync()
            syncer.run_sync()
            self.status = SyncStatus.SYNCED
            self.last_sync = time.time()
        except ImportError:
            log.debug("iCloud connector module not loaded")
            self.status = SyncStatus.SYNCED  # Treat as no-op
        except Exception as e:
            self.error_msg = str(e)
            self.status = SyncStatus.ERROR
            log.error("iCloud sync failed: %s", e)
        return self.status


# ── OneDrive connector ────────────────────────────────────────────────────────

class OneDriveConnector(SyncConnector):
    name = "OneDrive"
    enabled_config_key = "NOVASYNC_ONEDRIVE"

    def sync(self) -> SyncStatus:
        try:
            from novasync.onedrive.onedrive_connector import OneDriveSync
            syncer = OneDriveSync()
            syncer.run_sync()
            self.status = SyncStatus.SYNCED
            self.last_sync = time.time()
        except ImportError:
            self.status = SyncStatus.SYNCED
        except Exception as e:
            self.error_msg = str(e)
            self.status = SyncStatus.ERROR
            log.error("OneDrive sync failed: %s", e)
        return self.status


# ── Google Drive connector ────────────────────────────────────────────────────

class GoogleDriveConnector(SyncConnector):
    name = "Google Drive"
    enabled_config_key = "NOVASYNC_GOOGLEDRIVE"

    def sync(self) -> SyncStatus:
        # Prefer the native API connector; fall back to rclone
        try:
            from novasync.googledrive.googledrive_connector import sync as gd_sync
            ok = gd_sync()
            self.status = SyncStatus.SYNCED if ok else SyncStatus.ERROR
            if ok:
                self.last_sync = time.time()
            return self.status
        except ImportError:
            pass

        # rclone fallback
        try:
            import subprocess
            result = subprocess.run(
                ["rclone", "sync", "bobo-gdrive:", str(Path.home() / "Google Drive"),
                 "--transfers", "4", "--checkers", "8", "--quiet"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                self.status = SyncStatus.SYNCED
                self.last_sync = time.time()
            else:
                self.error_msg = result.stderr[:200]
                self.status = SyncStatus.ERROR
        except Exception as e:
            self.error_msg = str(e)
            self.status = SyncStatus.ERROR
        return self.status


# ── Battery check ─────────────────────────────────────────────────────────────

def get_battery_percent() -> int:
    """Returns current battery percentage, or 100 if no battery detected."""
    try:
        bat_dir = Path("/sys/class/power_supply")
        for entry in bat_dir.iterdir():
            if entry.name.startswith("BAT"):
                capacity = (entry / "capacity").read_text().strip()
                return int(capacity)
    except Exception:
        pass
    return 100  # Desktop / no battery


def is_on_battery() -> bool:
    try:
        bat_dir = Path("/sys/class/power_supply")
        for entry in bat_dir.iterdir():
            if entry.name.startswith("AC"):
                status = (entry / "online").read_text().strip()
                return status == "0"
    except Exception:
        pass
    return False


# ── D-Bus service ─────────────────────────────────────────────────────────────

DBUS_BUS_NAME  = "os.bobo.NovaSync"
DBUS_OBJ_PATH  = "/os/bobo/NovaSync"
DBUS_INTERFACE = "os.bobo.NovaSync"


class NovaSync_DBusService(dbus.service.Object):
    def __init__(self, bus, daemon: "NovaSync_Daemon"):
        super().__init__(bus, DBUS_OBJ_PATH)
        self._daemon = daemon

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="s")
    def GetStatus(self) -> str:
        statuses = [c.get_status() for c in self._daemon.connectors]
        return json.dumps(statuses)

    @dbus.service.method(DBUS_INTERFACE, in_signature="", out_signature="b")
    def TriggerSync(self) -> bool:
        threading.Thread(target=self._daemon.run_sync_pass, daemon=True).start()
        return True

    @dbus.service.method(DBUS_INTERFACE, in_signature="b", out_signature="")
    def SetPaused(self, paused: bool):
        self._daemon.paused = paused
        log.info("NovaSync %s by D-Bus request.", "paused" if paused else "resumed")


# ── Main daemon ───────────────────────────────────────────────────────────────

class NovaSync_Daemon:
    def __init__(self):
        self.connectors: list[SyncConnector] = [
            ICloudConnector(),
            OneDriveConnector(),
            GoogleDriveConnector(),
        ]
        self.paused = False

    def run_sync_pass(self):
        """Run one sync pass across all enabled connectors."""
        if self.paused:
            log.info("Sync paused — skipping.")
            return

        # Pause on low battery
        if is_on_battery() and get_battery_percent() < BATTERY_PAUSE_THRESHOLD:
            log.info("Battery at %d%% on battery — pausing sync.", get_battery_percent())
            return

        for connector in self.connectors:
            if not connector.is_enabled():
                continue
            connector.status = SyncStatus.SYNCING
            log.info("Syncing %s...", connector.name)
            status = connector.sync()
            log.info("%s sync complete: %s", connector.name, status.value)

    def start(self):
        log.info("NovaSync daemon starting.")

        if DBUS_AVAILABLE:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            session_bus = dbus.SessionBus()
            dbus.service.BusName(DBUS_BUS_NAME, bus=session_bus)
            NovaSync_DBusService(session_bus, self)
            log.info("D-Bus service registered: %s", DBUS_BUS_NAME)

        # Background sync loop
        def sync_loop():
            while True:
                self.run_sync_pass()
                time.sleep(SYNC_INTERVAL)

        sync_thread = threading.Thread(target=sync_loop, daemon=True)
        sync_thread.start()

        if DBUS_AVAILABLE:
            loop = GLib.MainLoop()
            try:
                loop.run()
            except KeyboardInterrupt:
                log.info("NovaSync daemon stopped.")
        else:
            sync_thread.join()


if __name__ == "__main__":
    NovaSync_Daemon().start()
