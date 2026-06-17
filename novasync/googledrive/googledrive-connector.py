#!/usr/bin/env python3
# =============================================================================
# BOBO OS — Google Drive Connector (Phase 7.4)
# E:\BOBO-OS\novasync\googledrive\googledrive-connector.py
#
# Syncs Google Drive to ~/Google Drive/ using the Google Drive API v3.
# Authentication: OAuth2 Device Flow (no browser redirect needed at install).
# Token stored in ~/.config/bobo-os/gdrive-token.json.
#
# Depends on: requests, google-auth, google-auth-httplib2, google-api-python-client
#   pip3 install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
#
# Falls back to rclone if the google-api libraries are not available.
# =============================================================================

import os
import sys
import json
import time
import shutil
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional, Generator

logger = logging.getLogger("bobo.gdrive")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
GDRIVE_ROOT  = Path.home() / "Google Drive"
CACHE_DIR    = Path.home() / ".cache" / "bobo-os" / "gdrive"
CONFIG_DIR   = Path.home() / ".config" / "bobo-os"
TOKEN_FILE   = CONFIG_DIR / "gdrive-token.json"

# Google OAuth2 credentials for the BOBO OS desktop client.
# Using the installed-app / device flow client type (no client secret needed
# for public OAuth2 clients; the client_id is intentionally public).
CLIENT_ID     = "bobo-os-gdrive-client"   # replaced at build time with real client ID
CLIENT_SECRET = ""                          # empty for device flow (PKCE only)
SCOPES        = ["https://www.googleapis.com/auth/drive.readonly",
                 "https://www.googleapis.com/auth/drive.file"]

RCLONE_REMOTE = "bobo-gdrive"


# ---------------------------------------------------------------------------
# OAuth2 Device Flow (GTK4 dialog)
# ---------------------------------------------------------------------------

def _show_device_code_dialog(user_code: str, verification_url: str, expires_in: int):
    """Show a GTK4 dialog with the device code and instructions."""
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Gtk, Adw, GLib, Gio, Gdk
    except ImportError:
        print(f"[Google Drive] Open {verification_url} and enter code: {user_code}")
        return

    def _run():
        adw_app = Adw.Application(
            application_id="os.bobo.GDriveAuth",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )

        def on_activate(application):
            win = Adw.ApplicationWindow(application=application)
            win.set_default_size(440, -1)
            win.set_title("Connect Google Drive")
            win.set_resizable(False)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            win.set_content(box)

            header = Adw.HeaderBar()
            header.set_show_end_title_buttons(False)
            box.append(header)

            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            content.set_margin_top(24)
            content.set_margin_bottom(24)
            content.set_margin_start(32)
            content.set_margin_end(32)
            box.append(content)

            icon = Gtk.Image.new_from_icon_name("folder-remote-symbolic")
            icon.set_pixel_size(48)
            content.append(icon)

            title = Gtk.Label(label="Connect to Google Drive")
            title.add_css_class("title-2")
            content.append(title)

            desc = Gtk.Label(
                label=f"Open the link below on any device and enter this code\n"
                      f"to grant BOBO OS access to your Google Drive."
            )
            desc.set_wrap(True)
            desc.set_justify(Gtk.Justification.CENTER)
            desc.add_css_class("dim-label")
            content.append(desc)

            # Code display
            code_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            code_box.set_halign(Gtk.Align.CENTER)
            code_box.add_css_class("card")
            code_lbl = Gtk.Label(label=user_code)
            code_lbl.add_css_class("title-1")
            code_lbl.add_css_class("monospace")
            code_lbl.set_margin_top(16)
            code_lbl.set_margin_bottom(16)
            code_lbl.set_margin_start(24)
            code_lbl.set_margin_end(12)
            code_lbl.set_selectable(True)
            code_box.append(code_lbl)

            copy_btn = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
            copy_btn.add_css_class("flat")
            copy_btn.set_valign(Gtk.Align.CENTER)
            copy_btn.set_margin_end(8)
            copy_btn.connect("clicked", lambda b: (
                win.get_clipboard().set(user_code),
                copy_btn.set_icon_name("emblem-ok-symbolic")
            ))
            code_box.append(copy_btn)
            content.append(code_box)

            # URL
            url_btn = Gtk.LinkButton.new_with_label(verification_url, verification_url)
            content.append(url_btn)

            # Countdown
            countdown_lbl = Gtk.Label()
            countdown_lbl.add_css_class("caption")
            countdown_lbl.add_css_class("dim-label")
            content.append(countdown_lbl)

            remaining = [expires_in]
            def _tick():
                remaining[0] -= 1
                if remaining[0] <= 0:
                    win.close()
                    application.quit()
                    return False
                countdown_lbl.set_text(f"Code expires in {remaining[0]}s")
                return True
            GLib.timeout_add(1000, _tick)

            close_btn = Gtk.Button(label="Done — I've entered the code")
            close_btn.add_css_class("suggested-action")
            close_btn.add_css_class("pill")
            close_btn.set_halign(Gtk.Align.CENTER)
            close_btn.connect("clicked", lambda b: (win.close(), application.quit()))
            content.append(close_btn)

            win.present()

        adw_app.connect("activate", on_activate)
        adw_app.run([])

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=expires_in + 10)


# ---------------------------------------------------------------------------
# Google Drive API connector
# ---------------------------------------------------------------------------

class GoogleDriveConnector:
    def __init__(self):
        self._creds  = None
        self._service = None
        self._syncing = False
        self._status  = "disconnected"
        self._error: Optional[str] = None
        GDRIVE_ROOT.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def status(self) -> str:
        return self._status

    # -----------------------------------------------------------------------
    # Authentication
    # -----------------------------------------------------------------------

    def _load_token(self) -> bool:
        if not TOKEN_FILE.exists():
            return False
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request

            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                TOKEN_FILE.write_text(creds.to_json())
            self._creds = creds
            return creds.valid
        except Exception as e:
            logger.warning("Token load failed: %s", e)
            return False

    def _device_flow_auth(self) -> bool:
        """Authenticate via OAuth2 Device Authorization Grant."""
        try:
            import requests as req
        except ImportError:
            logger.error("requests library not installed: pip3 install requests")
            return False

        # Step 1: request device code
        resp = req.post(
            "https://oauth2.googleapis.com/device/code",
            data={
                "client_id":  CLIENT_ID,
                "scope":      " ".join(SCOPES),
            },
            timeout=10
        )
        if resp.status_code != 200:
            self._error = f"Device code request failed: {resp.text}"
            return False

        data = resp.json()
        device_code      = data["device_code"]
        user_code        = data["user_code"]
        verification_url = data["verification_url"]
        interval         = data.get("interval", 5)
        expires_in       = data.get("expires_in", 1800)

        # Step 2: show dialog with the code
        _show_device_code_dialog(user_code, verification_url, expires_in)

        # Step 3: poll for token
        deadline = time.time() + expires_in
        while time.time() < deadline:
            time.sleep(interval)
            token_resp = req.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id":   CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "device_code": device_code,
                    "grant_type":  "urn:ietf:params:oauth:grant-type:device_code",
                },
                timeout=10
            )
            token_data = token_resp.json()
            if "access_token" in token_data:
                # Save token
                token_file_data = {
                    "token":         token_data["access_token"],
                    "refresh_token": token_data.get("refresh_token", ""),
                    "token_uri":     "https://oauth2.googleapis.com/token",
                    "client_id":     CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "scopes":        SCOPES,
                }
                TOKEN_FILE.write_text(json.dumps(token_file_data))
                TOKEN_FILE.chmod(0o600)
                return self._load_token()

            error = token_data.get("error", "")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            if error in ("access_denied", "expired_token"):
                self._error = f"Authentication failed: {error}"
                return False

        self._error = "Device code expired before authentication."
        return False

    def login(self) -> bool:
        try:
            from googleapiclient.discovery import build
        except ImportError:
            logger.warning(
                "google-api-python-client not installed — falling back to rclone. "
                "Run: pip3 install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )
            return self._rclone_fallback_auth()

        if self._load_token():
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            self._service = build("drive", "v3", credentials=self._creds)
            self._status = "connected"
            return True

        if self._device_flow_auth():
            from googleapiclient.discovery import build
            self._service = build("drive", "v3", credentials=self._creds)
            self._status = "connected"
            return True

        return False

    # -----------------------------------------------------------------------
    # rclone fallback
    # -----------------------------------------------------------------------

    def _rclone_fallback_auth(self) -> bool:
        if not shutil.which("rclone"):
            self._error = "rclone not installed. Run: sudo apt install rclone"
            return False

        # Check if remote already configured
        result = subprocess.run(
            ["rclone", "listremotes"], capture_output=True, text=True
        )
        if f"{RCLONE_REMOTE}:" in result.stdout:
            self._status = "connected_rclone"
            return True

        # Configure rclone remote (runs rclone config — requires terminal)
        logger.warning("rclone remote '%s' not configured. Run: rclone config", RCLONE_REMOTE)
        self._error = (
            f"Google Drive (rclone) is not configured. "
            f"Open a terminal and run: rclone config "
            f"— then name the remote '{RCLONE_REMOTE}' and choose Google Drive."
        )
        return False

    # -----------------------------------------------------------------------
    # File sync
    # -----------------------------------------------------------------------

    def _list_all_files(self) -> Generator[dict, None, None]:
        """Yield all files from Google Drive using page tokens."""
        page_token = None
        while True:
            kwargs = {
                "pageSize": 1000,
                "fields":   "nextPageToken, files(id, name, mimeType, modifiedTime, parents, size, trashed)",
            }
            if page_token:
                kwargs["pageToken"] = page_token

            response = self._service.files().list(**kwargs).execute()
            for f in response.get("files", []):
                if not f.get("trashed", False):
                    yield f

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    def _get_local_path(self, file_meta: dict, id_to_path: dict) -> Path:
        """Compute the local path for a remote file based on its parent chain."""
        parents = file_meta.get("parents", [])
        if parents and parents[0] in id_to_path:
            parent_path = id_to_path[parents[0]]
        else:
            parent_path = GDRIVE_ROOT
        return parent_path / file_meta["name"]

    def sync_drive(self):
        """Download/update all Google Drive files to ~/Google Drive/."""
        if not self._service:
            if not self.login():
                return

        # rclone fallback
        if self._status == "connected_rclone":
            self._rclone_sync()
            return

        logger.info("Syncing Google Drive via API…")
        self._status = "syncing"

        try:
            # Build id→path map first pass (folders)
            id_to_path: dict = {}
            all_files = list(self._list_all_files())

            # Index folders
            for f in all_files:
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    parents = f.get("parents", [])
                    if parents and parents[0] in id_to_path:
                        local = id_to_path[parents[0]] / f["name"]
                    else:
                        local = GDRIVE_ROOT / f["name"]
                    local.mkdir(parents=True, exist_ok=True)
                    id_to_path[f["id"]] = local

            # Download files
            count = 0
            for f in all_files:
                mime = f["mimeType"]
                if mime == "application/vnd.google-apps.folder":
                    continue

                local_path = self._get_local_path(f, id_to_path)

                # Skip if local copy is up to date
                if local_path.exists():
                    remote_mtime = f.get("modifiedTime", "")
                    if remote_mtime:
                        import datetime
                        dt = datetime.datetime.fromisoformat(
                            remote_mtime.replace("Z", "+00:00")
                        )
                        if local_path.stat().st_mtime >= dt.timestamp():
                            continue

                # Google Docs → export as Office formats
                export_mime = self._get_export_mime(mime)
                try:
                    if export_mime:
                        ext = self._export_extension(mime)
                        local_path = local_path.with_suffix(ext)
                        request = self._service.files().export_media(
                            fileId=f["id"], mimeType=export_mime
                        )
                    else:
                        request = self._service.files().get_media(fileId=f["id"])

                    with open(local_path, "wb") as fh:
                        import io
                        from googleapiclient.http import MediaIoBaseDownload
                        downloader = MediaIoBaseDownload(fh, request)
                        done = False
                        while not done:
                            _, done = downloader.next_chunk()

                    count += 1
                except Exception as e:
                    logger.warning("Skipping %s: %s", f["name"], e)

            logger.info("Google Drive sync complete: %d files", count)

        except Exception as e:
            logger.error("Google Drive sync error: %s", e)
            self._error = str(e)
        finally:
            self._status = "connected"

    def _rclone_sync(self):
        logger.info("Syncing Google Drive via rclone…")
        self._status = "syncing"
        try:
            subprocess.run(
                ["rclone", "sync", f"{RCLONE_REMOTE}:", str(GDRIVE_ROOT),
                 "--progress", "--transfers", "4", "--checkers", "8"],
                check=True, timeout=3600
            )
            logger.info("rclone sync complete")
        except subprocess.CalledProcessError as e:
            logger.error("rclone sync failed: %s", e)
            self._error = str(e)
        finally:
            self._status = "connected_rclone"

    @staticmethod
    def _get_export_mime(google_mime: str) -> Optional[str]:
        export_map = {
            "application/vnd.google-apps.document":     "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.google-apps.spreadsheet":  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.google-apps.drawing":      "image/svg+xml",
            "application/vnd.google-apps.script":       "application/vnd.google-apps.script+json",
        }
        return export_map.get(google_mime)

    @staticmethod
    def _export_extension(google_mime: str) -> str:
        ext_map = {
            "application/vnd.google-apps.document":     ".docx",
            "application/vnd.google-apps.spreadsheet":  ".xlsx",
            "application/vnd.google-apps.presentation": ".pptx",
            "application/vnd.google-apps.drawing":      ".svg",
            "application/vnd.google-apps.script":       ".json",
        }
        return ext_map.get(google_mime, "")

    def sync_all(self) -> bool:
        if self._syncing:
            return False
        self._syncing = True
        try:
            self.sync_drive()
            # Save last sync timestamp
            ts_file = CACHE_DIR / "last-sync.json"
            ts_file.write_text(json.dumps({"timestamp": time.time()}))
            return True
        finally:
            self._syncing = False

    def get_status_dict(self) -> dict:
        last_sync = None
        ts_file = CACHE_DIR / "last-sync.json"
        if ts_file.exists():
            try:
                last_sync = json.loads(ts_file.read_text()).get("timestamp")
            except Exception:
                pass
        return {
            "status":    self._status,
            "error":     self._error,
            "syncing":   self._syncing,
            "last_sync": last_sync,
        }


# ---------------------------------------------------------------------------
# novasync integration entry point
# ---------------------------------------------------------------------------

_connector: Optional[GoogleDriveConnector] = None


def get_connector() -> GoogleDriveConnector:
    global _connector
    if _connector is None:
        _connector = GoogleDriveConnector()
    return _connector


def sync() -> bool:
    return get_connector().sync_all()


def get_status() -> dict:
    return get_connector().get_status_dict()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _run_self_test():
    print("=== Google Drive Connector Self-Test ===")
    pass_count = 0
    fail_count = 0

    def ok(msg):
        nonlocal pass_count
        print(f"  PASS  {msg}")
        pass_count += 1

    def fail(msg):
        nonlocal fail_count
        print(f"  FAIL  {msg}")
        fail_count += 1

    # Test API library available
    try:
        from googleapiclient.discovery import build
        ok("google-api-python-client importable")
    except ImportError:
        print("  WARN  google-api-python-client not installed (rclone fallback will be used)")

    # Test rclone fallback
    if shutil.which("rclone"):
        ok("rclone binary found")
    else:
        print("  WARN  rclone not found — install: sudo apt install rclone")

    # Test connector instantiation
    try:
        conn = GoogleDriveConnector()
        assert conn.status == "disconnected"
        ok("GoogleDriveConnector instantiated")
    except Exception as e:
        fail(f"Instantiation failed: {e}")

    # Test export mime mapping
    try:
        mime = GoogleDriveConnector._get_export_mime(
            "application/vnd.google-apps.document"
        )
        assert "wordprocessingml" in mime
        ok("_get_export_mime correct for Docs → docx")
    except Exception as e:
        fail(f"_get_export_mime failed: {e}")

    # Test directory creation
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ok(f"Cache dir ready: {CACHE_DIR}")
    except Exception as e:
        fail(f"Cache dir creation failed: {e}")

    print(f"  PASS: {pass_count}  FAIL: {fail_count}")
    print("========================================")
    return fail_count == 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="[%(levelname)s] %(name)s: %(message)s")

    if "--test" in sys.argv:
        sys.exit(0 if _run_self_test() else 1)
    if "--sync" in sys.argv:
        sys.exit(0 if sync() else 1)
    if "--status" in sys.argv:
        print(json.dumps(get_status(), indent=2, default=str))
        sys.exit(0)

    print("Usage: googledrive-connector.py [--sync | --status | --test]")
    sys.exit(1)
