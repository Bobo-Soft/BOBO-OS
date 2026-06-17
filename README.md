# BOBO OS

> A modern, ultra-lightweight Linux desktop OS with a Windows-style interface that runs
> **Windows, Linux, macOS, iOS and Android** applications through a universal compatibility
> layer (NovaLayer). Built on Linux 6.6 LTS + Wayland/Wayfire + GTK4.

![version](https://img.shields.io/badge/version-1.0.0-4a9eff)
![kernel](https://img.shields.io/badge/kernel-6.6.87--bobo-1a1a2e)
![license](https://img.shields.io/badge/license-MIT%20%2F%20GPL%20%2F%20LGPL-green)

---

## ✨ What is BOBO OS?

BOBO OS is a custom Linux distribution whose defining feature is **universal application
compatibility**: open any app file and the system routes it to the right runtime.

| File type | Runtime | Engine |
|-----------|---------|--------|
| `.exe` `.msi` | Windows apps | Wine 8.0 + DXVK 2.3 |
| `.app` `.dmg` `.pkg` | macOS apps | Darling |
| `.ipa` | iOS apps | QEMU aarch64 user-mode |
| `.apk` `.xapk` | Android apps | Waydroid |
| `.deb` `.rpm` `.flatpak` `.AppImage` | Linux apps | native / pkexec / flatpak |

It ships a full GTK4 desktop, **32 first-party "BOBO" applications**, an app store
(NovaStore), cloud sync (NovaSync), an integrated AI assistant, and **BoboXcode** — a
Swift/iOS IDE with one-click App Store publishing via a Mac-cloud bridge.

- **Targets:** < 500 MB RAM idle · < 10 s boot
- **Design tokens:** background `#1a1a2e` · accent `#4a9eff` · font Inter
- **Verified:** boots to the Wayfire desktop in VirtualBox (BIOS, VMSVGA + 3D)

---

## 🏗️ Architecture

```
┌─ Desktop (GTK4 / Wayland) ────────────────────────────────────────────┐
│  Wayfire compositor · Taskbar · Start Menu · Notifications · Settings  │
└───────────────┬───────────────────────────────────────────────────────┘
   NovaLayer    │   NovaStore        NovaSync          AI Assistant
   (file router)│   (FastAPI store)  (iCloud/OneDrive  (Ollama / Claude)
   Wine/Darling │                     /GoogleDrive)
   QEMU/Waydroid│
┌───────────────▼───────────────────────────────────────────────────────┐
│  Security: nftables · bubblewrap+seccomp · LUKS2 · ClamAV · AppArmor    │
│  Drivers (NVIDIA/AMD/Intel) · zram (lz4) · PipeWire                     │
└───────────────┬───────────────────────────────────────────────────────┘
┌───────────────▼───────────────────────────────────────────────────────┐
│  Linux 6.6.87-bobo (virtio, AHCI, squashfs, overlay, DRM, zram)         │
└────────────────────────────────────────────────────────────────────────┘
```

### Boot chain
`GRUB2 (BIOS/UEFI)` → `kernel 6.6.87-bobo` → `busybox live-init` → mount squashfs RO +
tmpfs overlay → `switch_root` → `systemd` → autologin user `bobo` → `Wayfire desktop`.

---

## 📁 Repository layout

| Path | Contents |
|------|----------|
| `boot/` | GRUB config + kernel `.config` (1875 options, 8 boot fixes baked in) |
| `core/` | init, drivers (GPU auto-detect), **NovaLayer** (Wine/Darling/iOS/Waydroid), zram, security |
| `desktop/` | Wayfire config, taskbar, Start Menu, notifications, settings, BOBO-Dark theme |
| `novastore/` | FastAPI app-store backend (`:8740`) + GTK4 frontend + auto-update daemon |
| `novasync/` | Cloud-sync daemon + iCloud / OneDrive / Google Drive connectors |
| `ai-assistant/` | D-Bus AI daemon + GTK4 panel (Ollama local / Claude cloud) |
| `apps/` | Pre-configured browser, file manager (Nemo), terminal (foot), antivirus (ClamAV) |
| `config/` | `bobo-os.conf`, `performance.conf`, `security.conf` |
| `bobo-apps/` | **32 first-party GTK4 applications** + installer + shared theme/keybindings |
| `bobo-xcode/` | **BoboXcode** — Swift/iOS IDE + BoboiOS App-Store bridge (isolated) |
| `scripts/` | Build pipeline (`build.sh`, `create-iso.sh`, installer) + Windows/WSL2 orchestrators |
| `docs/` | Full project documentation (`BOBO-OS-DOCUMENTATIE-COMPLETA.md`) |

> **Not in this repo** (separate products / build artifacts, see `.gitignore`):
> `build-output/` (ISO/squashfs binaries), and the unrelated `bobo-ai/`, `bobostudio/`,
> `terra-antiqua/` projects.

---

## 🧩 The 32 BOBO applications (`bobo-apps/`)

GTK4, BOBO-Dark theme, ~7,742 lines of Python. Each has a launcher, `.desktop` entry and SVG icon.

| | | | |
|---|---|---|---|
| 01 bobo-player (media) | 09 bobo-installer | 17 bobo-notif | 25 bobo-code (IDE-lite) |
| 02 bobo-monitor (task mgr) | 10 bobo-update | 18 bobo-theme | 26 bobo-vm (QEMU/libvirt) |
| 03 bobo-settings | 11 bobo-backup (borg) | 19 bobo-desk | 27 bobo-dev (Podman) |
| 04 bobo-text | 12 bobo-printer (CUPS) | 20 bobo-screen | 28 bobo-cast |
| 05 bobo-reader (PDF) | 13 bobo-access | 21 bobo-clip | 29 bobo-phone (KDE Connect) |
| 06 bobo-gallery | 14 bobo-login | 22 bobo-vpn (WireGuard) | 30 bobo-ai-local (Ollama) |
| 07 bobo-archive | 15 bobo-users | 23 bobo-share (Zeroconf) | 31 bobo-scan (ClamAV) |
| 08 bobo-mail (IMAP/SMTP) | 16 bobo-search | 24 bobo-remote (RDP/VNC/SSH) | 32 bobo-coin (BTC/ETH) |

## 🍏 BoboXcode (`bobo-xcode/`)

A self-contained Swift/iOS IDE: local Swift (Apple's Linux toolchain), Flutter, React Native,
sourcekit-lsp completion, a QEMU iOS simulator — plus the **BoboiOS Bridge**, which SSHes to a
Mac cloud and runs fastlane to **sign and publish to the App Store in one click**. Launch with
**Super+X**.

---

## 🚀 Build the ISO (Windows + WSL2)

> The build runs in WSL2 Ubuntu-24.04 and is orchestrated from PowerShell.

```powershell
# 1. (once) provision WSL2 + build deps
powershell -File scripts\windows\install-wsl2.ps1
powershell -File scripts\windows\setup-build-env.ps1

# 2. build a LEAN ISO (apps launch; heavy deps install on demand) — default
powershell -File scripts\windows\compile-bobo-os.ps1

# 2b. or a FULL ISO (all app deps + Swift toolchain baked in, ~2 GB)
$env:BOBO_APPS_SKIP_DEPS = "0"
$env:BOBO_XCODE_SKIP_HEAVY = "0"
powershell -File scripts\windows\compile-bobo-os.ps1
```

Pipeline steps: **(1)** download Linux 6.6.87 · **(2)** compile kernel · **(3)** debootstrap
rootfs + desktop + 32 apps · **(3b)** BoboXcode · **(4)** live-boot initrd · **(5)** squashfs +
GRUB ISO tree · **(6)** xorriso hybrid ISO · **(7)** QEMU smoke test. Output:
`build-output/BOBO-OS-v1.0.iso`.

### 8 critical build fixes (do not regress)
El-Torito `cdboot.img+core.img` · kernel built-ins (virtio/AHCI/sr/squashfs/overlay/DRM) ·
native-ext4 rootfs (not NTFS) · non-root `bobo` user + autologin · full desktop stack ·
`mksquashfs -mem 512M` · `noapic` cmdline · busybox live-init mounting CD at `/cdrom`.

---

## 🖥️ Run in VirtualBox

1. **New VM** → Linux / Ubuntu (64-bit) → **RAM ≥ 3 GB** (4 GB for the full ISO)
2. **System** → enable **IO-APIC**
3. **Display** → Graphics Controller **VMSVGA**, **3D Acceleration on**, Video RAM ≥ 128 MB
4. **Storage** → attach `build-output/BOBO-OS-v1.0.iso` to the IDE/SATA optical drive
5. **Start** → GRUB → *Start BOBO OS (Live)* → autologin `bobo` (password `bobo`) → Wayfire desktop

Keyboard shortcuts: `Super+X` BoboXcode · `Super+V` player · `Super+I` settings ·
`Super+Space` search · `Super+E` files · `Super+Enter` terminal.

---

## 🔧 Tech stack

Kernel **Linux 6.6.87 LTS** · init **systemd** · **Wayland + Wayfire** · **GTK4**/Qt6 ·
Wine+DXVK · Darling · QEMU · Waydroid · FastAPI · nftables · LUKS2 · zram+lz4 · GRUB2 · xorriso.

## 📜 License

Open source. Base system MIT; Linux kernel & Darling GPL-2.0; Wine LGPL-2.1. Bundled
third-party components retain their own licenses.

---

*Full documentation: [`docs/BOBO-OS-DOCUMENTATIE-COMPLETA.md`](docs/BOBO-OS-DOCUMENTATIE-COMPLETA.md)*
