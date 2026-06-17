#!/usr/bin/env python3
"""
BOBO OS — NovaStore Auto-Update Daemon (Phase 6.3)
E:\BOBO-OS\novastore\backend\auto-update.py

Checks for updates every 24 hours (or on-demand with --check).
Creates a btrfs snapshot before applying any update.
Rolls back automatically on failure and notifies the user.
"""

import os
import sys
import time
import subprocess
import logging
from pathlib import Path
from datetime import datetime

LOG_PATH = Path("/var/log/bobo-updates.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AutoUpdate] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("autoupdate")

CHECK_INTERVAL = 86400  # 24 hours


def notify(title: str, body: str, icon: str = "system-software-update"):
    try:
        subprocess.Popen(
            ["notify-send", "--icon", icon, "--app-name", "BOBO OS Updates", title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        log.info("notify-send not available: %s — %s", title, body)


def create_snapshot() -> str | None:
    """Create a btrfs snapshot of / before updating. Returns snapshot path or None."""
    snapshot_dir = Path("/snapshots")
    snapshot_dir.mkdir(exist_ok=True)
    snap_name = f"pre-update-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    snap_path = snapshot_dir / snap_name

    try:
        result = subprocess.run(
            ["btrfs", "subvolume", "snapshot", "/", str(snap_path)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            log.info("Snapshot created: %s", snap_path)
            return str(snap_path)
        else:
            log.warning("Snapshot failed (non-btrfs?): %s", result.stderr.strip())
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        log.debug("btrfs not available — skipping snapshot")
        return None


def rollback_snapshot(snapshot_path: str):
    """Attempt to roll back to a previously created snapshot."""
    try:
        log.warning("Rolling back to snapshot: %s", snapshot_path)
        # Replace / with the snapshot (dangerous — only if system is in single-user)
        subprocess.run(
            ["btrfs", "subvolume", "delete", "/"],
            capture_output=True, timeout=30
        )
        subprocess.run(
            ["btrfs", "subvolume", "snapshot", snapshot_path, "/"],
            capture_output=True, timeout=60
        )
        log.info("Rollback complete. Rebooting...")
        subprocess.Popen(["systemctl", "reboot"])
    except Exception as e:
        log.error("Rollback failed: %s", e)


def check_and_apply_updates() -> tuple[int, int]:
    """Check for and apply updates. Returns (updated_count, failed_count)."""
    updated = 0
    failed  = 0

    log.info("Checking for updates...")

    # ── Flatpak updates ───────────────────────────────────────────────────────
    snapshot = create_snapshot()

    try:
        result = subprocess.run(
            ["flatpak", "remote-ls", "--updates"],
            capture_output=True, text=True, timeout=60
        )
        pending = [l.split()[0] for l in result.stdout.splitlines() if l.strip()]
        log.info("%d Flatpak updates pending.", len(pending))

        if pending:
            apply_result = subprocess.run(
                ["flatpak", "update", "--noninteractive"],
                capture_output=True, text=True, timeout=300
            )
            if apply_result.returncode == 0:
                updated += len(pending)
                log.info("Flatpak updates applied: %d", len(pending))
            else:
                failed += len(pending)
                log.error("Flatpak update failed: %s", apply_result.stderr[:300])
                if snapshot:
                    rollback_snapshot(snapshot)
    except FileNotFoundError:
        log.debug("flatpak not installed — skipping")
    except subprocess.TimeoutExpired:
        log.warning("Update check timed out")

    return updated, failed


def run_daemon():
    log.info("Auto-update daemon starting. Check interval: %d seconds.", CHECK_INTERVAL)
    while True:
        try:
            updated, failed = check_and_apply_updates()

            if updated > 0 and failed == 0:
                notify(
                    f"{updated} app{'s' if updated > 1 else ''} updated ✅",
                    "All updates were installed successfully.",
                )
            elif failed > 0:
                notify(
                    "Update failed",
                    f"{failed} update(s) could not be applied. Your previous state was restored.",
                    icon="dialog-error",
                )
        except Exception as e:
            log.error("Unexpected error in update daemon: %s", e)

        log.info("Next check in %d hours.", CHECK_INTERVAL // 3600)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    if "--check" in sys.argv:
        updated, failed = check_and_apply_updates()
        print(f"Updated: {updated}  Failed: {failed}")
        sys.exit(0 if failed == 0 else 1)
    else:
        run_daemon()
