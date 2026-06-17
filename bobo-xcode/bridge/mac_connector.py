"""
SSH connection to a Mac cloud host (MacStadium, AWS EC2 Mac, or any Mac with
SSH enabled). Transparent to the user — surfaces as a local 'Publish' feature.
Credentials are stored encrypted (Fernet) at /etc/bobo-xcode/bridge.yaml.
"""
import os
import subprocess

try:
    import paramiko
    HAVE_PARAMIKO = True
except Exception:
    paramiko = None
    HAVE_PARAMIKO = False

try:
    import yaml
except Exception:
    yaml = None

try:
    from cryptography.fernet import Fernet
    HAVE_FERNET = True
except Exception:
    Fernet = None
    HAVE_FERNET = False

CONFIG_PATH = "/etc/bobo-xcode/bridge.yaml"
KEY_PATH = "/etc/bobo-xcode/.bridge_key"


class MacConnector:
    def __init__(self):
        self.ssh = None
        self.config = self._load_config()

    # ------------------------------------------------------------------ state
    def is_configured(self) -> bool:
        return bool(
            self.config
            and self.config.get("mac_host")
            and self.config.get("mac_user")
            and (self.config.get("mac_password") or self.config.get("mac_key_path"))
        )

    def dependencies_ok(self) -> bool:
        return HAVE_PARAMIKO and HAVE_FERNET and yaml is not None

    # ------------------------------------------------------------------ connect
    def connect(self) -> bool:
        if not HAVE_PARAMIKO:
            raise RuntimeError("paramiko not installed — run a FULL build or "
                               "install python3-paramiko to enable the Bridge.")
        if not self.is_configured():
            return False
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = {
            "hostname": self.config["mac_host"],
            "port": int(self.config.get("mac_port", 22)),
            "username": self.config["mac_user"],
            "timeout": 30,
        }
        if self.config.get("mac_key_path"):
            kwargs["key_filename"] = self.config["mac_key_path"]
        else:
            kwargs["password"] = self._decrypt(self.config["mac_password"])
        try:
            self.ssh.connect(**kwargs)
            return True
        except Exception as e:
            self.ssh = None
            raise ConnectionError("Cannot reach Mac cloud: %s\n"
                                  "Check credentials in Settings -> Bridge." % e)

    def disconnect(self):
        if self.ssh:
            try:
                self.ssh.close()
            except Exception:
                pass
            self.ssh = None

    # ------------------------------------------------------------------ transfer
    def upload_project(self, local_path: str, callback=None) -> str:
        if not self.ssh:
            self.connect()
        remote = "/tmp/bobo-xcode/%s" % os.path.basename(local_path.rstrip("/"))
        self._exec("mkdir -p %s" % remote)
        key_arg = ""
        if self.config.get("mac_key_path"):
            key_arg = "-i %s" % self.config["mac_key_path"]
        cmd = [
            "rsync", "-az", "--delete",
            "-e", "ssh -o StrictHostKeyChecking=no -p %s %s" % (self.config.get("mac_port", 22), key_arg),
            "--exclude", ".build", "--exclude", "DerivedData", "--exclude", ".git",
            "--exclude", "node_modules",
            "%s/" % local_path,
            "%s@%s:%s/" % (self.config["mac_user"], self.config["mac_host"], remote),
        ]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            if callback:
                callback("Transfer: %s" % line.strip())
        p.wait()
        if p.returncode != 0:
            raise RuntimeError("Project transfer failed (rsync exit %d)" % p.returncode)
        return remote

    def download_artifact(self, remote_path: str, local_path: str):
        if not self.ssh:
            self.connect()
        sftp = self.ssh.open_sftp()
        try:
            sftp.get(remote_path, local_path)
        finally:
            sftp.close()

    def _exec(self, command: str) -> str:
        if not self.ssh:
            self.connect()
        stdin, stdout, stderr = self.ssh.exec_command(command)
        stdout.channel.recv_exit_status()
        return stdout.read().decode(errors="replace")

    # ------------------------------------------------------------------ config
    def save_config(self, config: dict):
        os.makedirs("/etc/bobo-xcode", exist_ok=True)
        cfg = dict(config)
        if cfg.get("mac_password"):
            cfg["mac_password"] = self._encrypt(cfg["mac_password"])
        if yaml:
            with open(CONFIG_PATH, "w") as fh:
                yaml.safe_dump(cfg, fh)
            os.chmod(CONFIG_PATH, 0o600)
        self.config = self._load_config()

    def _load_config(self) -> dict:
        if os.path.exists(CONFIG_PATH) and yaml:
            try:
                with open(CONFIG_PATH) as fh:
                    return yaml.safe_load(fh) or {}
            except Exception:
                return {}
        return {}

    # ------------------------------------------------------------------ crypto
    def _encrypt(self, value: str) -> str:
        if not HAVE_FERNET:
            return value
        return Fernet(self._key()).encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        if not HAVE_FERNET:
            return value
        try:
            return Fernet(self._key()).decrypt(value.encode()).decode()
        except Exception:
            return value

    def _key(self) -> bytes:
        if os.path.exists(KEY_PATH):
            with open(KEY_PATH, "rb") as fh:
                return fh.read()
        key = Fernet.generate_key()
        os.makedirs("/etc/bobo-xcode", exist_ok=True)
        with open(KEY_PATH, "wb") as fh:
            fh.write(key)
        os.chmod(KEY_PATH, 0o600)
        return key
