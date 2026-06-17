"""
App Store Connect upload + status monitoring for BoboXcode.
Uploads an already-signed IPA via `xcrun altool` on the Mac, and polls
processing/review status. Used when publishing a prebuilt IPA directly.
"""
import time
from bridge.mac_connector import MacConnector


class AppStoreUploader:
    def __init__(self, mac_connector: MacConnector):
        self.mac = mac_connector

    def upload_ipa(self, remote_ipa: str, apple_id: str, app_password: str,
                   callback=None) -> dict:
        """Upload a signed IPA with altool. Returns {success, output}."""
        def log(m):
            if callback:
                callback(m if m.endswith("\n") else m + "\n")
        if not self.mac.ssh:
            self.mac.connect()
        log("Validating IPA...")
        validate = self.mac._exec(
            "xcrun altool --validate-app -f %s -t ios "
            "-u '%s' -p '%s' 2>&1" % (remote_ipa, apple_id, app_password))
        log(validate)
        if "No errors" not in validate and "successful" not in validate.lower():
            return {"success": False, "output": validate}
        log("Uploading to App Store Connect...")
        upload = self.mac._exec(
            "xcrun altool --upload-app -f %s -t ios "
            "-u '%s' -p '%s' 2>&1" % (remote_ipa, apple_id, app_password))
        log(upload)
        success = "No errors" in upload or "successfully" in upload.lower()
        return {"success": success, "output": upload}

    def poll_status(self, bundle_id: str, apple_id: str, app_password: str,
                    attempts: int = 5, interval: int = 30, callback=None) -> str:
        """Poll App Store Connect processing status a few times."""
        def log(m):
            if callback:
                callback(m if m.endswith("\n") else m + "\n")
        if not self.mac.ssh:
            self.mac.connect()
        last = ""
        for i in range(attempts):
            out = self.mac._exec(
                "xcrun altool --list-apps -u '%s' -p '%s' 2>&1 | grep -i '%s' || true"
                % (apple_id, app_password, bundle_id))
            last = out.strip() or "Processing (build not yet visible)..."
            log("[%d/%d] %s" % (i + 1, attempts, last))
            if "READY" in out.upper() or "ACCEPTED" in out.upper():
                break
            time.sleep(interval)
        return last
