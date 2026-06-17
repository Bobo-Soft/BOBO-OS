# BOBO OS Security Layer

Three security components protect every aspect of BOBO OS.

## Components

### firewall-setup.sh — nftables Firewall
Three network profiles applied via a single command:

```bash
# Apply a profile
sudo firewall-setup.sh home    # Default: allows mDNS, blocks inbound
sudo firewall-setup.sh work    # Strict: blocks BitTorrent outbound
sudo firewall-setup.sh public  # Maximum: HTTPS/DNS/DHCP only outbound

# Self-test
sudo firewall-setup.sh --test  # (use 'home' arg to test; script auto-selects)
```

Auto-switches profile based on Wi-Fi SSID using `/etc/bobo-os/home-networks.conf`.  
Per-app outbound blocking by UID via `/etc/bobo-os/blocked-apps.conf`.

### sandbox.py — Per-App Sandbox
Launches apps in Linux user/mount/pid/ipc/net namespaces via bubblewrap.  
Applies a seccomp BPF allowlist inside the namespace.  
GTK4 permission dialog for first-time capability requests.

```bash
# Launch an app in sandbox
python3 sandbox.py "MyApp" /usr/bin/myapp --arg1

# Manage permissions
python3 sandbox.py --grant  MyApp network
python3 sandbox.py --revoke MyApp camera
python3 sandbox.py --list   MyApp
python3 sandbox.py --query  MyApp network   # exits 0 if granted

# Self-test (no GUI needed)
python3 sandbox.py --test
```

Permission files: `~/.bobo/permissions/<app-name>.json`

### encryption-setup.sh — LUKS2 Full-Disk Encryption
Manages LUKS2 disk encryption unlock at boot and key enrollment.

```bash
# Enroll additional unlock methods (run once after install)
sudo encryption-setup.sh setup /dev/sda2 --tpm2 --recovery --fprint

# Boot-time passphrase unlock (called from initrd)
encryption-setup.sh unlock /dev/sda2 root

# Check status
encryption-setup.sh status /dev/sda2

# Self-test
encryption-setup.sh --test
```

Unlock order: **TPM2 (auto)** → **Fingerprint** → **GTK4 passphrase dialog** (3 attempts).

## Security policy

Global settings are in [`/config/security.conf`](../../config/security.conf).  
Key defaults:

| Setting | Value |
|---------|-------|
| Firewall default | `home` profile |
| Sandbox backend | `bwrap` (bubblewrap) |
| Seccomp BPF | enabled |
| LUKS2 KDF | `argon2id` |
| AppArmor | enabled |
| ClamAV | enabled |
| Auto-lock | 5 minutes |
