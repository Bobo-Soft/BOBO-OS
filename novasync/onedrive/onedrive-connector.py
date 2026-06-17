#!/usr/bin/env python3
"""
BOBO OS — OneDrive Connector (Phase 7.3)
E:\BOBO-OS\novasync\onedrive\onedrive-connector.py

Microsoft OneDrive sync via Microsoft Graph API + OAuth2 browser flow.
Syncs OneDrive folder to ~/OneDrive/ using delta sync.
"""

import json
import os
import subprocess
import time
import webbrowser
import logging
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from threading import Thread

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

log = logging.getLogger("novasync.onedrive")

# ── Config ────────────────────────────────────────────────────────────────────
CLIENT_ID    = "YOUR_AZURE_APP_CLIENT_ID"   # Replace with a registered Azure app
REDIRECT_URI = "http://localhost:8749/callback"
SCOPES       = "Files.ReadWrite offline_access User.Read"
TOKEN_FILE   = Path.home() / ".config" / "bobo-os" / "onedrive-token.json"
SYNC_DIR     = Path.home() / "OneDrive"
DELTA_FILE   = Path.home() / ".cache" / "bobo-os" / "onedrive-delta.json"

AUTH_URL = (
    "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?"
    + urlencode({
        "client_id":     CLIENT_ID,
        "response_type": "code",
        "redirect_uri":  REDIRECT_URI,
        "scope":         SCOPES,
        "response_mode": "query",
    })
)
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


# ── OAuth2 local callback server ──────────────────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if "code" in qs:
            _CallbackHandler.code = qs["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>BOBO OS OneDrive: authentication complete. You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args): pass  # Silence access log


def _get_auth_code() -> str:
    """Open browser for OAuth2 consent and capture the auth code via local server."""
    server = HTTPServer(("127.0.0.1", 8749), _CallbackHandler)
    t = Thread(target=server.handle_request, daemon=True)
    t.start()
    webbrowser.open(AUTH_URL)
    t.join(timeout=120)
    server.server_close()
    if not _CallbackHandler.code:
        raise RuntimeError("OAuth2 consent not completed within 2 minutes.")
    return _CallbackHandler.code


def _exchange_code(code: str) -> dict:
    resp = httpx.post(TOKEN_URL, data={
        "client_id":    CLIENT_ID,
        "grant_type":   "authorization_code",
        "code":         code,
        "redirect_uri": REDIRECT_URI,
        "scope":        SCOPES,
    })
    resp.raise_for_status()
    return resp.json()


def _refresh_token(refresh_tok: str) -> dict:
    resp = httpx.post(TOKEN_URL, data={
        "client_id":    CLIENT_ID,
        "grant_type":   "refresh_token",
        "refresh_token": refresh_tok,
        "scope":        SCOPES,
    })
    resp.raise_for_status()
    return resp.json()


# ── Token management ──────────────────────────────────────────────────────────

def load_or_authenticate() -> dict:
    """Return a valid token dict, authenticating if needed."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

    if TOKEN_FILE.exists():
        tokens = json.loads(TOKEN_FILE.read_text())
        # Check expiry (refresh 5 minutes early)
        if tokens.get("expires_at", 0) > time.time() + 300:
            return tokens
        # Refresh
        try:
            new_tokens = _refresh_token(tokens["refresh_token"])
            new_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 3600) - 60
            TOKEN_FILE.write_text(json.dumps(new_tokens))
            return new_tokens
        except Exception as e:
            log.warning("Token refresh failed: %s — re-authenticating", e)

    # Full OAuth2 flow
    code   = _get_auth_code()
    tokens = _exchange_code(code)
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600) - 60
    TOKEN_FILE.write_text(json.dumps(tokens))
    return tokens


# ── Sync logic ────────────────────────────────────────────────────────────────

class OneDriveSync:
    def __init__(self):
        SYNC_DIR.mkdir(parents=True, exist_ok=True)
        DELTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._tokens: dict | None = None

    def _auth_headers(self) -> dict:
        if not self._tokens:
            self._tokens = load_or_authenticate()
        return {"Authorization": f"Bearer {self._tokens['access_token']}"}

    def run_sync(self):
        if not HTTPX_AVAILABLE:
            log.warning("httpx not installed — OneDrive sync disabled")
            return

        log.info("Starting OneDrive delta sync...")
        delta_link = self._get_delta_link()

        with httpx.Client(headers=self._auth_headers(), timeout=30) as client:
            url = delta_link or f"{GRAPH_BASE}/me/drive/root/delta"

            while url:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("value", []):
                    self._process_item(item, client)

                # Get next page or store the deltaLink for next run
                url = data.get("@odata.nextLink")
                if not url:
                    new_delta = data.get("@odata.deltaLink")
                    if new_delta:
                        DELTA_FILE.write_text(json.dumps({"deltaLink": new_delta}))

        log.info("OneDrive sync complete.")

    def _get_delta_link(self) -> str | None:
        if DELTA_FILE.exists():
            try:
                return json.loads(DELTA_FILE.read_text()).get("deltaLink")
            except Exception:
                pass
        return None

    def _process_item(self, item: dict, client: httpx.Client):
        rel_path = self._item_relative_path(item)
        local_path = SYNC_DIR / rel_path

        if "deleted" in item:
            # File was deleted remotely
            if local_path.exists():
                local_path.unlink(missing_ok=True)
                log.debug("Deleted: %s", local_path)
            return

        if "folder" in item:
            local_path.mkdir(parents=True, exist_ok=True)
            return

        if "file" not in item:
            return

        download_url = item.get("@microsoft.graph.downloadUrl")
        if not download_url:
            return

        # Skip if local file is newer (conflict resolution: newer-wins)
        remote_modified = item.get("lastModifiedDateTime", "")
        if local_path.exists():
            local_mtime = local_path.stat().st_mtime
            try:
                from datetime import datetime, timezone
                remote_ts = datetime.fromisoformat(
                    remote_modified.replace("Z", "+00:00")
                ).timestamp()
                if local_mtime >= remote_ts:
                    return  # Local is same or newer — skip
            except Exception:
                pass

        # Download the file
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with client.stream("GET", download_url) as resp:
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)
        log.debug("Synced: %s", local_path)

    @staticmethod
    def _item_relative_path(item: dict) -> Path:
        """Build a relative filesystem path from the item's parentReference + name."""
        parent = item.get("parentReference", {}).get("path", "/drive/root:")
        # Strip the "/drive/root:" prefix
        parent_rel = parent.replace("/drive/root:", "").lstrip("/")
        name = item.get("name", "unknown")
        return Path(parent_rel) / name


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    OneDriveSync().run_sync()
