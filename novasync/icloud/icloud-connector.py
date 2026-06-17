#!/usr/bin/env python3
# =============================================================================
# BOBO OS — iCloud Connector (Phase 7.2)
# E:\BOBO-OS\novasync\icloud\icloud-connector.py
#
# Syncs iCloud Drive, Photos, Contacts (CardDAV), Calendars (CalDAV),
# Notes, and Reminders to ~/iCloud Drive/.
#
# Authentication: Apple ID + password (stored in libsecret keyring).
# Two-factor: TOTP or SMS code via GTK4 dialog.
#
# Depends on: pyicloud, requests, vobject (CardDAV), caldav (CalDAV)
#             gi (GTK4 for 2FA dialog), libsecret (via secretstorage)
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
from typing import Optional, List, Dict, Any

logger = logging.getLogger("bobo.icloud")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ICLOUD_ROOT    = Path.home() / "iCloud Drive"
PHOTOS_DIR     = ICLOUD_ROOT / "Photos"
DRIVE_DIR      = ICLOUD_ROOT / "Drive"
CONTACTS_DIR   = ICLOUD_ROOT / "Contacts"
CALENDARS_DIR  = ICLOUD_ROOT / "Calendars"
NOTES_DIR      = ICLOUD_ROOT / "Notes"
CACHE_DIR      = Path.home() / ".cache" / "bobo-os" / "icloud"
CONFIG_DIR     = Path.home() / ".config" / "bobo-os"
TOKEN_FILE     = CONFIG_DIR / "icloud-token.json"
CREDENTIAL_KEY = "BOBO_OS_iCloud"

# ---------------------------------------------------------------------------
# Keyring helpers (libsecret via secretstorage)
# ---------------------------------------------------------------------------

def _keyring_store(apple_id: str, password: str):
    try:
        import secretstorage
        bus = secretstorage.dbus_init()
        coll = secretstorage.get_default_collection(bus)
        coll.create_item(
            f"BOBO OS iCloud: {apple_id}",
            {"application": "bobo-novasync", "apple_id": apple_id},
            password,
            replace=True
        )
    except Exception as e:
        logger.warning("Could not store credentials in keyring: %s", e)


def _keyring_load(apple_id: str) -> Optional[str]:
    try:
        import secretstorage
        bus = secretstorage.dbus_init()
        coll = secretstorage.get_default_collection(bus)
        for item in coll.get_all_items():
            attrs = item.get_attributes()
            if attrs.get("apple_id") == apple_id and \
               attrs.get("application") == "bobo-novasync":
                return item.get_secret().decode()
    except Exception as e:
        logger.warning("Could not load credentials from keyring: %s", e)
    return None


# ---------------------------------------------------------------------------
# Two-factor authentication dialog (GTK4)
# ---------------------------------------------------------------------------

def _ask_2fa_code_gui(apple_id: str, method: str = "TOTP") -> Optional[str]:
    """
    Show a GTK4 dialog asking for the 2FA code.
    Returns the code string, or None if cancelled.
    """
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Gtk, Adw, GLib, Gio
    except ImportError:
        code = input(f"[iCloud 2FA] Enter verification code for {apple_id}: ")
        return code.strip() or None

    result = [None]

    def _run_app():
        adw_app = Adw.Application(
            application_id="os.bobo.ICloud2FA",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )

        def on_activate(application):
            win = Adw.ApplicationWindow(application=application)
            win.set_default_size(400, -1)
            win.set_title("iCloud Verification")
            win.connect("close-request", lambda w: True)

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

            icon = Gtk.Image.new_from_icon_name("dialog-password-symbolic")
            icon.set_pixel_size(48)
            content.append(icon)

            title = Gtk.Label(label="Two-Factor Authentication")
            title.add_css_class("title-2")
            content.append(title)

            desc_text = (
                f"A verification code has been sent to your\n"
                f"trusted devices for <b>{GLib.markup_escape_text(apple_id)}</b>.\n"
                f"Enter it below to continue."
                if method != "TOTP" else
                f"Enter the verification code from your\nAuthenticator app for "
                f"<b>{GLib.markup_escape_text(apple_id)}</b>."
            )
            desc = Gtk.Label()
            desc.set_markup(desc_text)
            desc.set_justify(Gtk.Justification.CENTER)
            desc.set_wrap(True)
            content.append(desc)

            # 6-digit code entry
            group = Adw.PreferencesGroup()
            code_row = Adw.EntryRow(title="Verification Code")
            code_row.set_input_purpose(Gtk.InputPurpose.DIGITS)
            code_row.set_max_width_chars(8)
            group.add(code_row)
            content.append(group)

            btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            btn_row.set_homogeneous(True)

            cancel_btn = Gtk.Button(label="Cancel")
            cancel_btn.connect("clicked", lambda b: (win.close(), application.quit()))

            verify_btn = Gtk.Button(label="Verify")
            verify_btn.add_css_class("suggested-action")

            def _verify(*_):
                code = code_row.get_text().strip()
                if len(code) < 4:
                    code_row.add_css_class("error")
                    return
                result[0] = code
                win.close()
                application.quit()

            verify_btn.connect("clicked", _verify)
            code_row.connect("apply", _verify)

            btn_row.append(cancel_btn)
            btn_row.append(verify_btn)
            content.append(btn_row)

            win.present()
            code_row.grab_focus()

        adw_app.connect("activate", on_activate)
        adw_app.run([])

    t = threading.Thread(target=_run_app, daemon=True)
    t.start()
    t.join(timeout=300)
    return result[0]


# ---------------------------------------------------------------------------
# Apple ID credential dialog (GTK4)
# ---------------------------------------------------------------------------

def _ask_credentials_gui() -> tuple:
    """
    Show Apple ID + password dialog.
    Returns (apple_id, password) or ("", "") if cancelled.
    """
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Gtk, Adw, GLib, Gio
    except ImportError:
        apple_id = input("Apple ID: ").strip()
        import getpass
        password = getpass.getpass("Password: ")
        return apple_id, password

    result = [("", "")]

    def _run_app():
        adw_app = Adw.Application(
            application_id="os.bobo.ICloudLogin",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )

        def on_activate(application):
            win = Adw.ApplicationWindow(application=application)
            win.set_default_size(420, -1)
            win.set_title("Sign in to iCloud")
            win.connect("close-request", lambda w: True)

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

            icon = Gtk.Image.new_from_icon_name("network-server-symbolic")
            icon.set_pixel_size(48)
            content.append(icon)

            title = Gtk.Label(label="Sign in to iCloud")
            title.add_css_class("title-2")
            content.append(title)

            group = Adw.PreferencesGroup()
            id_row  = Adw.EntryRow(title="Apple ID (email)")
            id_row.set_input_purpose(Gtk.InputPurpose.EMAIL)
            pw_row  = Adw.PasswordEntryRow(title="Password")
            group.add(id_row)
            group.add(pw_row)
            content.append(group)

            remember_row = Adw.SwitchRow(title="Remember credentials",
                                          subtitle="Stored securely in keyring")
            remember_row.set_active(True)
            group.add(remember_row)

            btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            btn_row.set_homogeneous(True)

            cancel_btn = Gtk.Button(label="Cancel")
            cancel_btn.connect("clicked", lambda b: (win.close(), application.quit()))

            signin_btn = Gtk.Button(label="Sign In")
            signin_btn.add_css_class("suggested-action")

            def _sign_in(*_):
                aid = id_row.get_text().strip()
                pw  = pw_row.get_text()
                if not aid or not pw:
                    return
                result[0] = (aid, pw, remember_row.get_active())
                win.close()
                application.quit()

            signin_btn.connect("clicked", _sign_in)
            btn_row.append(cancel_btn)
            btn_row.append(signin_btn)
            content.append(btn_row)

            win.present()
            id_row.grab_focus()

        adw_app.connect("activate", on_activate)
        adw_app.run([])

    t = threading.Thread(target=_run_app, daemon=True)
    t.start()
    t.join(timeout=300)
    r = result[0]
    if len(r) == 3:
        return r[0], r[1], r[2]
    return "", "", False


# ---------------------------------------------------------------------------
# iCloud API wrapper (uses pyicloud)
# ---------------------------------------------------------------------------

class ICloudConnector:
    """
    Wraps pyicloud.PyiCloudService with BOBO OS integration:
    - GTK4 dialogs for login and 2FA
    - Credential storage in libsecret keyring
    - Sync methods for each iCloud service
    """

    def __init__(self):
        self._api = None
        self._apple_id: Optional[str] = None
        self._syncing = False
        self._status = "disconnected"
        self._error: Optional[str] = None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def status(self) -> str:
        return self._status

    @property
    def error(self) -> Optional[str]:
        return self._error

    # -----------------------------------------------------------------------
    # Authentication
    # -----------------------------------------------------------------------

    def _load_apple_id(self) -> Optional[str]:
        """Load stored Apple ID from config."""
        cfg = CONFIG_DIR / "icloud-account.json"
        if cfg.exists():
            try:
                data = json.loads(cfg.read_text())
                return data.get("apple_id")
            except Exception:
                pass
        return None

    def _save_apple_id(self, apple_id: str):
        cfg = CONFIG_DIR / "icloud-account.json"
        cfg.write_text(json.dumps({"apple_id": apple_id}))

    def login(self, apple_id: str = "", password: str = "") -> bool:
        """
        Authenticate with iCloud.  If credentials are not provided,
        load from keyring or prompt the user via GTK4 dialog.
        """
        try:
            import pyicloud
        except ImportError:
            self._error = "pyicloud not installed. Run: pip3 install pyicloud"
            self._status = "error"
            logger.error(self._error)
            return False

        # Resolve Apple ID
        if not apple_id:
            apple_id = self._load_apple_id() or ""
        if not password and apple_id:
            password = _keyring_load(apple_id) or ""

        # Prompt if still missing
        if not apple_id or not password:
            result = _ask_credentials_gui()
            apple_id, password = result[0], result[1]
            remember = result[2] if len(result) > 2 else True
            if not apple_id:
                self._status = "cancelled"
                return False
            if remember:
                _keyring_store(apple_id, password)
                self._save_apple_id(apple_id)

        self._apple_id = apple_id
        self._status = "connecting"
        logger.info("Connecting to iCloud as %s", apple_id)

        try:
            self._api = pyicloud.PyiCloudService(
                apple_id, password,
                cookie_directory=str(CACHE_DIR / "cookies")
            )
        except pyicloud.exceptions.PyiCloudFailedLoginException as e:
            self._error = f"Login failed: incorrect Apple ID or password."
            self._status = "error"
            logger.error(self._error)
            return False
        except Exception as e:
            self._error = f"Could not connect to iCloud: {e}"
            self._status = "error"
            logger.error(self._error)
            return False

        # Handle 2FA
        if self._api.requires_2fa:
            logger.info("Two-factor authentication required")
            code = _ask_2fa_code_gui(apple_id, "TOTP")
            if not code:
                self._status = "cancelled"
                return False
            result = self._api.validate_2fa_code(code)
            if not result:
                self._error = "Two-factor code was incorrect."
                self._status = "error"
                return False
            # Trust this session
            if not self._api.is_trusted_session:
                self._api.trust_session()

        elif self._api.requires_2sa:
            logger.info("Two-step authentication required")
            devices = self._api.trusted_devices
            device = devices[0] if devices else None
            if device:
                self._api.send_verification_code(device)
            code = _ask_2fa_code_gui(apple_id, "SMS")
            if not code:
                self._status = "cancelled"
                return False
            if not self._api.validate_verification_code(device, code):
                self._error = "Verification code was incorrect."
                self._status = "error"
                return False

        self._status = "connected"
        logger.info("Authenticated with iCloud successfully")
        return True

    # -----------------------------------------------------------------------
    # iCloud Drive sync
    # -----------------------------------------------------------------------

    def sync_drive(self):
        """Sync iCloud Drive files to ~/iCloud Drive/Drive/"""
        if not self._api:
            return
        DRIVE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Syncing iCloud Drive…")
        self._status = "syncing"

        try:
            drive = self._api.drive
            self._sync_drive_folder(drive.root, DRIVE_DIR)
            logger.info("iCloud Drive sync complete")
        except Exception as e:
            logger.error("iCloud Drive sync error: %s", e)
            self._error = str(e)
        finally:
            self._status = "connected"

    def _sync_drive_folder(self, folder, local_path: Path, depth: int = 0):
        """Recursively download iCloud Drive folder."""
        if depth > 20:
            return
        local_path.mkdir(parents=True, exist_ok=True)

        try:
            items = folder.dir()
        except Exception as e:
            logger.warning("Cannot list %s: %s", local_path, e)
            return

        for item_name in items:
            try:
                item = folder[item_name]
                item_path = local_path / item_name

                if item.type == "folder":
                    self._sync_drive_folder(item, item_path, depth + 1)
                else:
                    # Download only if newer than local copy
                    remote_mtime = item.date_modified
                    if item_path.exists() and remote_mtime:
                        local_mtime = item_path.stat().st_mtime
                        if local_mtime >= remote_mtime.timestamp():
                            continue

                    logger.debug("Downloading: %s", item_path)
                    with item.open(stream=True) as resp:
                        with open(item_path, "wb") as f:
                            shutil.copyfileobj(resp.raw, f)

                    # Preserve remote modification time
                    if remote_mtime:
                        ts = remote_mtime.timestamp()
                        os.utime(item_path, (ts, ts))

            except Exception as e:
                logger.warning("Skipping %s: %s", item_name, e)

    # -----------------------------------------------------------------------
    # Photos sync
    # -----------------------------------------------------------------------

    def sync_photos(self, max_photos: int = 5000):
        """Sync iCloud Photos library to ~/iCloud Drive/Photos/"""
        if not self._api:
            return
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Syncing iCloud Photos…")

        try:
            photos = self._api.photos
            count = 0
            for album in photos.albums.values():
                album_dir = PHOTOS_DIR / album.title
                album_dir.mkdir(parents=True, exist_ok=True)
                for asset in album:
                    if count >= max_photos:
                        break
                    filename = asset.filename
                    dest = album_dir / filename
                    if dest.exists():
                        continue
                    try:
                        with asset.open(stream=True) as resp:
                            with open(dest, "wb") as f:
                                shutil.copyfileobj(resp.raw, f)
                        count += 1
                    except Exception as e:
                        logger.warning("Photo download failed (%s): %s", filename, e)
            logger.info("Photos sync complete: %d assets", count)
        except Exception as e:
            logger.error("Photos sync error: %s", e)
            self._error = str(e)

    # -----------------------------------------------------------------------
    # Contacts sync (CardDAV)
    # -----------------------------------------------------------------------

    def sync_contacts(self):
        """Sync iCloud Contacts via CardDAV to ~/iCloud Drive/Contacts/*.vcf"""
        CONTACTS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Syncing iCloud Contacts via CardDAV…")

        try:
            import requests
            # pyicloud exposes contacts natively
            if self._api and hasattr(self._api, "contacts"):
                contacts = self._api.contacts.all()
                count = 0
                for contact in contacts:
                    first = contact.get("firstName", "")
                    last  = contact.get("lastName", "")
                    name  = f"{first}_{last}".strip("_") or f"contact_{count}"
                    vcf_path = CONTACTS_DIR / f"{name}.vcf"
                    vcf_data = self._contact_to_vcf(contact)
                    vcf_path.write_text(vcf_data)
                    count += 1
                logger.info("Contacts sync complete: %d contacts", count)
            else:
                logger.warning("Contacts service not available via pyicloud")
        except Exception as e:
            logger.error("Contacts sync error: %s", e)
            self._error = str(e)

    def _contact_to_vcf(self, contact: dict) -> str:
        lines = ["BEGIN:VCARD", "VERSION:3.0"]
        first = contact.get("firstName", "")
        last  = contact.get("lastName", "")
        lines.append(f"N:{last};{first};;;")
        lines.append(f"FN:{first} {last}".strip())

        for phone in contact.get("phones", []):
            label = phone.get("label", "voice").upper()
            num   = phone.get("field", "")
            lines.append(f"TEL;TYPE={label}:{num}")

        for email in contact.get("emails", []):
            label = email.get("label", "internet").upper()
            addr  = email.get("field", "")
            lines.append(f"EMAIL;TYPE={label}:{addr}")

        lines.append("END:VCARD")
        return "\r\n".join(lines) + "\r\n"

    # -----------------------------------------------------------------------
    # Calendars sync (CalDAV via caldav library)
    # -----------------------------------------------------------------------

    def sync_calendars(self):
        """Sync iCloud Calendars via CalDAV to ~/iCloud Drive/Calendars/*.ics"""
        CALENDARS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Syncing iCloud Calendars via CalDAV…")

        try:
            import caldav
        except ImportError:
            logger.warning("caldav not installed — skipping calendar sync. Run: pip3 install caldav")
            return

        if not self._apple_id:
            return

        password = _keyring_load(self._apple_id) or ""
        if not password:
            logger.warning("No password for CalDAV; skipping calendars")
            return

        try:
            caldav_url = f"https://caldav.icloud.com/"
            client = caldav.DAVClient(
                url=caldav_url,
                username=self._apple_id,
                password=password
            )
            principal = client.principal()
            calendars = principal.calendars()
            count = 0
            for cal in calendars:
                cal_name = cal.name or f"calendar_{count}"
                cal_dir  = CALENDARS_DIR / cal_name
                cal_dir.mkdir(parents=True, exist_ok=True)
                for event in cal.events():
                    try:
                        ics_data = event.data
                        # Use UID as filename
                        uid_line = next(
                            (l for l in ics_data.splitlines() if l.startswith("UID:")),
                            f"UID:event_{count}"
                        )
                        uid = uid_line.split(":", 1)[1].strip()
                        ics_path = cal_dir / f"{uid}.ics"
                        ics_path.write_text(ics_data)
                        count += 1
                    except Exception as e:
                        logger.warning("Event download error: %s", e)
            logger.info("Calendars sync complete: %d events", count)
        except Exception as e:
            logger.error("CalDAV sync error: %s", e)
            self._error = str(e)

    # -----------------------------------------------------------------------
    # Notes sync
    # -----------------------------------------------------------------------

    def sync_notes(self):
        """Sync iCloud Notes to ~/iCloud Drive/Notes/*.txt"""
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Syncing iCloud Notes…")

        try:
            if not self._api or not hasattr(self._api, "notes"):
                logger.warning("Notes service not available via pyicloud")
                return

            notes_svc = self._api.notes
            count = 0
            for note in notes_svc.notebooks[0].notes:
                title   = (note.title or f"note_{count}").replace("/", "_")[:80]
                content = note.text or ""
                note_path = NOTES_DIR / f"{title}.txt"
                note_path.write_text(content, encoding="utf-8")
                count += 1
            logger.info("Notes sync complete: %d notes", count)
        except Exception as e:
            logger.error("Notes sync error: %s", e)
            self._error = str(e)

    # -----------------------------------------------------------------------
    # Full sync
    # -----------------------------------------------------------------------

    def sync_all(self) -> bool:
        """Run a full sync of all enabled iCloud services."""
        if self._syncing:
            logger.info("Sync already in progress — skipping")
            return False

        if self._api is None:
            if not self.login():
                return False

        self._syncing = True
        self._error   = None

        try:
            # Read enabled services from bobo-os.conf
            enabled = self._read_enabled_services()

            if enabled.get("drive",    True): self.sync_drive()
            if enabled.get("photos",   True): self.sync_photos()
            if enabled.get("contacts", True): self.sync_contacts()
            if enabled.get("calendars",True): self.sync_calendars()
            if enabled.get("notes",    True): self.sync_notes()

            # Save last-sync timestamp
            ts_file = CACHE_DIR / "last-sync.json"
            ts_file.write_text(json.dumps({
                "timestamp": time.time(),
                "apple_id":  self._apple_id or ""
            }))
            logger.info("iCloud full sync complete")
            return True

        except Exception as e:
            self._error = str(e)
            logger.error("Sync error: %s", e)
            return False
        finally:
            self._syncing = False

    def _read_enabled_services(self) -> dict:
        conf = CONFIG_DIR.parent.parent / "config" / "bobo-os.conf"
        enabled = {
            "drive": True, "photos": True,
            "contacts": True, "calendars": True, "notes": True
        }
        if conf.exists():
            for line in conf.read_text().splitlines():
                line = line.strip()
                if line.startswith("ICLOUD_DRIVE="):
                    enabled["drive"] = line.split("=", 1)[1].lower() in ("true", "1", "yes")
                elif line.startswith("ICLOUD_PHOTOS="):
                    enabled["photos"] = line.split("=", 1)[1].lower() in ("true", "1", "yes")
        return enabled

    def get_status_dict(self) -> dict:
        last_sync = None
        ts_file = CACHE_DIR / "last-sync.json"
        if ts_file.exists():
            try:
                data = json.loads(ts_file.read_text())
                last_sync = data.get("timestamp")
            except Exception:
                pass
        return {
            "status":    self._status,
            "apple_id":  self._apple_id,
            "error":     self._error,
            "syncing":   self._syncing,
            "last_sync": last_sync,
        }


# ---------------------------------------------------------------------------
# novasync integration entry point
# ---------------------------------------------------------------------------

_connector: Optional[ICloudConnector] = None


def get_connector() -> ICloudConnector:
    global _connector
    if _connector is None:
        _connector = ICloudConnector()
    return _connector


def sync() -> bool:
    return get_connector().sync_all()


def get_status() -> dict:
    return get_connector().get_status_dict()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _run_self_test():
    print("=== iCloud Connector Self-Test ===")
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

    # Test pyicloud importable
    try:
        import pyicloud
        ok(f"pyicloud importable (version {getattr(pyicloud, '__version__', 'unknown')})")
    except ImportError:
        fail("pyicloud not installed — run: pip3 install pyicloud")

    # Test GTK4 importable
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        ok("GTK4 importable")
    except Exception:
        fail("GTK4 not importable")

    # Test secretstorage importable
    try:
        import secretstorage
        ok("secretstorage importable")
    except ImportError:
        print("  WARN  secretstorage not installed (credentials won't be saved to keyring)")

    # Test caldav importable
    try:
        import caldav
        ok("caldav importable")
    except ImportError:
        print("  WARN  caldav not installed — calendar sync unavailable (pip3 install caldav)")

    # Test directory creation
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ok(f"Cache directory ready: {CACHE_DIR}")
    except Exception as e:
        fail(f"Cannot create cache directory: {e}")

    # Test ICloudConnector instantiation
    try:
        conn = ICloudConnector()
        assert conn.status == "disconnected"
        ok("ICloudConnector instantiated, status=disconnected")
    except Exception as e:
        fail(f"ICloudConnector init failed: {e}")

    # Test VCF generation
    try:
        conn2 = ICloudConnector()
        vcf = conn2._contact_to_vcf({
            "firstName": "Tim",
            "lastName":  "Apple",
            "phones":    [{"label": "mobile", "field": "+1-555-0100"}],
            "emails":    [{"label": "work",   "field": "tim@apple.com"}],
        })
        assert "BEGIN:VCARD" in vcf
        assert "Tim" in vcf
        assert "+1-555-0100" in vcf
        ok("VCF generation correct")
    except Exception as e:
        fail(f"VCF generation failed: {e}")

    # Test get_status_dict
    try:
        status = get_connector().get_status_dict()
        assert "status" in status and "apple_id" in status
        ok("get_status_dict returns expected keys")
    except Exception as e:
        fail(f"get_status_dict failed: {e}")

    print(f"  PASS: {pass_count}  FAIL: {fail_count}")
    print("==================================")
    return fail_count == 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="[%(levelname)s] %(name)s: %(message)s")

    if "--test" in sys.argv:
        sys.exit(0 if _run_self_test() else 1)

    if "--sync" in sys.argv:
        ok = sync()
        sys.exit(0 if ok else 1)

    if "--status" in sys.argv:
        s = get_status()
        print(json.dumps(s, indent=2, default=str))
        sys.exit(0)

    print("Usage: icloud-connector.py [--sync | --status | --test]")
    sys.exit(1)
