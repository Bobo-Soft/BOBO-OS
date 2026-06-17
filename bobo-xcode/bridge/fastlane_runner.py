"""
Runs Fastlane on the Mac cloud to sign and upload to App Store Connect.
Fastlane is open-source and runs on macOS. The user needs an Apple Developer
account (the App Store membership is theirs; we only orchestrate).
"""
from bridge.mac_connector import MacConnector
from bridge.project_packager import ProjectPackager

FASTFILE_TEMPLATE = '''default_platform(:ios)

platform :ios do
  desc "Build and sign the app"
  lane :build_and_sign do
    automatic_code_signing(use_automatic_signing: true)
    gym(
      scheme: ENV["SCHEME"],
      export_method: "app-store",
      output_directory: "/tmp/bobo-output/",
      output_name: "app.ipa",
      clean: true
    )
  end

  desc "Upload to App Store Connect"
  lane :upload do
    deliver(
      ipa: "/tmp/bobo-output/app.ipa",
      skip_screenshots: true,
      skip_metadata: ENV["SKIP_METADATA"] == "true",
      submit_for_review: false,
      force: true
    )
  end

  desc "Full build + upload"
  lane :publish do
    build_and_sign
    upload
  end
end
'''


class FastlaneRunner:
    def __init__(self, project_path: str, mac_connector: MacConnector):
        self.project_path = project_path
        self.mac = mac_connector
        self.packager = ProjectPackager()

    def publish(self, apple_id: str, app_password: str, scheme: str = None,
                skip_metadata: bool = True, callback=None) -> dict:
        """Full publish pipeline. Returns {success, ipa_path, errors}."""
        def log(msg):
            if callback:
                callback(msg if msg.endswith("\n") else msg + "\n")

        try:
            log("Connecting to Mac cloud...")
            self.mac.connect()
            log("Connected.")

            log("Transferring project to Mac...")
            remote = self.mac.upload_project(self.project_path, callback=log)
            log("Project at %s" % remote)

            log("Configuring Fastlane...")
            fdir = "%s/fastlane" % remote
            self.mac._exec("mkdir -p %s" % fdir)
            # write Fastfile via base64 to avoid heredoc/quoting issues
            import base64
            b64 = base64.b64encode(FASTFILE_TEMPLATE.encode()).decode()
            self.mac._exec("echo %s | base64 -d > %s/Fastfile" % (b64, fdir))
            log("Fastlane configured.")

            scheme_arg = scheme or self.packager.detect_scheme(self.project_path)
            log("Build + signing on Mac (scheme=%s, 5-10 min)..." % scheme_arg)

            self.mac.connect()
            stdin, stdout, stderr = self.mac.ssh.exec_command(
                "cd %s && "
                "FASTLANE_USER='%s' "
                "FASTLANE_APPLE_APPLICATION_SPECIFIC_PASSWORD='%s' "
                "SCHEME='%s' SKIP_METADATA='%s' "
                "fastlane publish 2>&1"
                % (remote, apple_id, app_password, scheme_arg,
                   "true" if skip_metadata else "false"),
                timeout=1200)
            for line in stdout:
                log(line.rstrip())
            status = stdout.channel.recv_exit_status()
            if status != 0:
                raise RuntimeError("Fastlane failed (exit %d). Check Apple credentials." % status)

            log("Build + signing complete.")

            log("Downloading signed IPA...")
            import os
            os.makedirs("%s/build" % self.project_path, exist_ok=True)
            local_ipa = "%s/build/app.ipa" % self.project_path
            self.mac.download_artifact("/tmp/bobo-output/app.ipa", local_ipa)
            log("IPA saved to %s" % local_ipa)
            log("Published to App Store Connect. Check it for the review status.")

            return {"success": True, "ipa_path": local_ipa, "errors": ""}

        except Exception as e:
            log("ERROR: %s" % e)
            return {"success": False, "ipa_path": None, "errors": str(e)}
        finally:
            self.mac.disconnect()
