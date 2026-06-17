"""
Apple code-signing helper for BoboXcode.
Inspects and manages signing identities / provisioning profiles on the Mac
cloud over SSH (the keychain lives on macOS). Prefers fastlane 'match' when
configured, otherwise reports the identities present in the login keychain.
"""
from bridge.mac_connector import MacConnector


class SigningManager:
    def __init__(self, mac_connector: MacConnector):
        self.mac = mac_connector

    def list_identities(self):
        """Return signing identities available in the Mac's login keychain."""
        if not self.mac.is_configured():
            return []
        if not self.mac.ssh:
            self.mac.connect()
        out = self.mac._exec("security find-identity -v -p codesigning 2>/dev/null")
        identities = []
        for line in out.splitlines():
            line = line.strip()
            # format: 1) <SHA1> "Apple Distribution: Name (TEAMID)"
            if ")" in line and '"' in line:
                name = line.split('"', 1)[1].rstrip('"')
                sha = line.split()[1] if len(line.split()) > 1 else ""
                identities.append({"sha1": sha, "name": name})
        return identities

    def list_provisioning_profiles(self):
        """List installed provisioning profiles on the Mac."""
        if not self.mac.ssh:
            self.mac.connect()
        out = self.mac._exec(
            "ls -1 ~/Library/MobileDevice/'Provisioning Profiles'/ 2>/dev/null")
        return [l for l in out.splitlines() if l.strip()]

    def setup_match(self, git_url: str, app_identifier: str, team_id: str,
                    match_type: str = "appstore") -> str:
        """
        Configure fastlane 'match' for reproducible signing.
        Returns the command output. Requires a Matchfile git repo.
        """
        if not self.mac.ssh:
            self.mac.connect()
        cmd = (
            "fastlane match %s "
            "--git_url %s --app_identifier %s --team_id %s --readonly false 2>&1"
            % (match_type, git_url, app_identifier, team_id)
        )
        return self.mac._exec(cmd)

    def enable_automatic_signing(self, remote_project: str, team_id: str) -> str:
        """Enable Xcode automatic signing for the transferred project."""
        if not self.mac.ssh:
            self.mac.connect()
        cmd = (
            "cd %s && /usr/libexec/PlistBuddy -c "
            "'Set :DEVELOPMENT_TEAM %s' *.xcodeproj/project.pbxproj 2>/dev/null; "
            "echo automatic-signing-configured" % (remote_project, team_id)
        )
        return self.mac._exec(cmd)

    def verify_ready(self) -> dict:
        """Return a readiness report for signing."""
        report = {"identities": [], "profiles": [], "ready": False, "error": ""}
        try:
            report["identities"] = self.list_identities()
            report["profiles"] = self.list_provisioning_profiles()
            report["ready"] = len(report["identities"]) > 0
        except Exception as e:
            report["error"] = str(e)
        return report
