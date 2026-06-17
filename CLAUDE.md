# BOBO OS — Project Memory for Claude Code

> This file is read automatically at the start of every Claude Code session.
> Keep it updated. It is the single source of truth for the project state.

---

## 🖥️ Project Identity

- **OS Name:** BOBO OS
- **Version:** 1.0.0
- **Description:** A modern, ultra-lightweight desktop OS with a Windows-style interface,
  compatible with Windows (.exe), Linux, macOS (.app/.dmg) and iOS (.ipa) software.
- **Root path:** `E:\BOBO-OS`
- **Programs & tools path:** `E:\Program Files`
- **Target RAM (idle):** < 500 MB
- **Target boot time:** < 10 seconds
- **Output ISO:** `E:\BOBO-OS\build-output\BOBO-OS-v1.0.iso`

---

## 📁 Canonical Directory Structure

```
E:\BOBO-OS\
├── CLAUDE.md                   ← THIS FILE — always keep updated
├── CHECKPOINT.md               ← Session progress — always keep updated
├── boot\
│   ├── grub\grub.cfg
│   ├── kernel\kernel.config
│   └── initrd\
├── core\
│   ├── init\                   # runit or dinit init system
│   ├── drivers\
│   │   ├── auto-detect.sh
│   │   └── gpu\
│   ├── novalayer\
│   │   ├── novalayer-daemon.py
│   │   ├── wine\wine-wrapper.sh
│   │   ├── darling\darling-wrapper.sh
│   │   ├── ios-runtime\ios-launcher.py
│   │   └── waydroid\
│   ├── zram\zram-setup.sh
│   └── security\
│       ├── firewall-setup.sh
│       ├── sandbox.py
│       └── encryption-setup.sh
├── desktop\
│   ├── window-manager\
│   ├── taskbar\
│   │   └── start-menu\
│   ├── notifications\
│   ├── settings\
│   ├── themes\bobo-default\
│   └── wallpapers\
├── novastore\
│   ├── backend\
│   └── frontend\
├── novasync\
│   ├── novasync-daemon.py
│   ├── icloud\
│   ├── onedrive\
│   └── googledrive\
├── apps\
│   ├── browser\
│   ├── office\
│   ├── files\
│   ├── media\
│   ├── mail\
│   ├── terminal\
│   └── antivirus\
├── ai-assistant\
├── config\
│   ├── bobo-os.conf
│   ├── performance.conf
│   └── security.conf
├── scripts\
│   ├── build.sh
│   ├── install.sh
│   ├── setup-tools.sh
│   └── create-iso.sh
├── docs\
└── build-output\
```

**All third-party tools and compilers install to:**
```
E:\Program Files\
├── gcc\        ├── llvm\       ├── python\     ├── nodejs\
├── cmake\      ├── wine-src\   ├── darling-src\ ├── waydroid\
├── grub2\      ├── xorriso\    ├── mkinitcpio\ ├── gtk4\
├── qt6\        └── ffmpeg\
```

---

## 🏗️ Phase Map & Status

> Update the STATUS column after each session. Valid values:
> `NOT STARTED` | `IN PROGRESS` | `DONE` | `BLOCKED`

| Phase | Description | Status |
|-------|-------------|--------|
| 1.1 | `setup-tools.sh` — install toolchain to `E:\Program Files` | DONE |
| 1.2 | `bobo-os.conf` — global config variables | DONE |
| 2.1 | `kernel.config` — Linux 6.6 LTS optimized config | DONE |
| 2.2 | `grub.cfg` — GRUB2 with BOBO OS theme | DONE |
| 2.3 | `core/init/` — runit/dinit service definitions | DONE |
| 3.1 | `auto-detect.sh` — hardware detection & driver install | DONE |
| 3.2 | `core/drivers/gpu/` — NVIDIA, AMD, Intel scripts | DONE |
| 4.1 | `novalayer-daemon.py` — file-type router daemon | DONE |
| 4.2 | `wine-wrapper.sh` — Windows app compatibility | DONE |
| 4.3 | `darling-wrapper.sh` — macOS app compatibility | DONE |
| 4.4 | `ios-launcher.py` — iOS app runtime | DONE |
| 4.5 | `zram-setup.sh` — compressed RAM config | DONE |
| 5.1 | `desktop/window-manager/` — WM config (Wayfire) | DONE |
| 5.2 | `desktop/taskbar/` — full taskbar GTK4 app | DONE |
| 5.3 | `desktop/taskbar/start-menu/` — Start Menu GTK4 | DONE |
| 5.4 | `desktop/notifications/` — notification center | DONE |
| 5.5 | `desktop/settings/` — Settings panel GTK4 | DONE |
| 5.6 | `desktop/themes/bobo-default/` — GTK4 + Qt6 theme | DONE |
| 6.1 | `novastore/backend/` — FastAPI app store server | DONE |
| 6.2 | `novastore/frontend/` — GTK4 store UI | DONE |
| 6.3 | `novastore/backend/auto-update.py` — update daemon | DONE |
| 7.1 | `novasync/novasync-daemon.py` — sync daemon | DONE |
| 7.2 | `novasync/icloud/` — iCloud connector | DONE |
| 7.3 | `novasync/onedrive/` — OneDrive connector | DONE |
| 8.1 | `apps/files/` — Nemo file manager config | DONE |
| 8.2 | `apps/browser/` — Firefox pre-configured (user.js) | DONE |
| 8.3 | `ai-assistant/` — integrated AI assistant | DONE |
| 9.1 | `core/security/firewall-setup.sh` — nftables firewall | DONE |
| 9.2 | `core/security/sandbox.py` — per-app sandbox | DONE |
| 9.3 | `core/security/encryption-setup.sh` — LUKS2 | DONE |
| 10.1 | `scripts/build.sh` — master build script | DONE |
| 10.2 | `scripts/create-iso.sh` — bootable ISO generator | DONE |
| 10.3 | `scripts/install.sh` — graphical installer | DONE |
| 11.1 | `config/performance.conf` — CPU/IO/memory tuning | DONE |
| 11.2 | `config/security.conf` — security policy master config | DONE |
| 11.3 | `novasync/googledrive/` — Google Drive connector (API v3 + rclone) | DONE |
| 11.4 | `apps/terminal/` — foot terminal config + setup script | DONE |
| 11.5 | `apps/antivirus/` — ClamAV setup + Nemo action | DONE |
| 11.6 | Module README.md files (novalayer, novastore, novasync, security, ai, desktop) | DONE |
| 12.1 | `bobo-apps/` — 32 concern applications (APP 01–32), GTK4, ~7,742 lines Python | DONE |
| 12.2 | `bobo-apps/build-bobo-apps.sh` — master installer (essential + full dep tiers) | DONE |
| 12.3 | `bobo-apps/shared/` — BOBO-Dark GTK4 theme + Wayfire keybindings | DONE |
| 12.4 | Pipeline integration — `compile-bobo-os.ps1` Step 3 bakes apps into squashfs | DONE |
| 13.1 | `bobo-xcode/` — IDE Swift/iOS + BoboiOS Bridge (26 .py, isolated; self-locating install.sh) | DONE |
| 13.2 | Step 3b in `compile-bobo-os.ps1` — installs BoboXcode in chroot | DONE |
| 13.3 | Super+X Wayfire shortcut (appended to `/etc/bobo-wayfire-defaults.ini`) | DONE |

---

## ⚙️ Coding Rules — Always Follow

1. **All absolute paths** use `E:\BOBO-OS` and `E:\Program Files` — never `/home`, `/usr` or other Linux paths for project files.
2. **All shell scripts** start with a host OS check: detect if running in WSL2/Linux before proceeding.
3. **All user-facing GUIs** use GTK4 or Qt6. Never expose a terminal to the end user.
4. **All error messages** shown to the user must be in plain language — no technical codes, no stack traces.
5. **Every module** must have its own `README.md` with clear usage instructions.
6. **Every script** must have inline comments in English for every logical block.
7. **Every phase** ends with a self-test: print what passed, what failed.
8. **NovaLayer routing:** `.exe/.msi` → Wine | `.app/.dmg/.pkg` → Darling | `.ipa` → ios-runtime | `.apk` → Waydroid.
9. **UI language** is auto-detected from system locale. All UI strings must be in string files (not hardcoded).
10. **Never ask the user** to open a terminal for routine operations.

---

## 🎨 Design Tokens

| Token | Value |
|-------|-------|
| Background (dark) | `#1a1a2e` |
| Accent color | `#4a9eff` |
| Text (dark mode) | `#ffffff` |
| Background (light) | `#f5f5f5` |
| Accent color (light) | `#0066cc` |
| Text (light mode) | `#1a1a1a` |
| Taskbar height | `48px` |
| Window corner radius | `8px` |
| Font | Inter, fallback Segoe UI, then system-ui |
| Icon set | Fluent Icons or Papirus |

---

## 🔧 Key Tech Choices

| Component | Technology |
|-----------|-----------|
| Kernel | Linux 6.6 LTS |
| Init system | runit (preferred) or dinit |
| Display server | Wayland + X11 fallback |
| Window manager | Wayfire (customized) |
| GUI toolkit | GTK4 primary, Qt6 secondary |
| Windows compat | Wine/Proton + DXVK |
| macOS compat | Darling |
| iOS compat | Custom ARM emulation runtime |
| Android compat | Waydroid |
| App store backend | Python FastAPI |
| App store frontend | GTK4 |
| Cloud sync | Python daemon (iCloud, OneDrive, GDrive) |
| Firewall | nftables |
| Disk encryption | LUKS2 |
| Memory compression | zram + lz4 |
| ISO creation | xorriso |
| Bootloader | GRUB2 (UEFI + BIOS) |

---

## 🛠️ Build Reproducibility — 8 CRITICAL FIXES (do NOT regress)

> These fixes are what make a clean rebuild produce a **bootable ISO that reaches the
> Wayfire desktop in VirtualBox**. They are coded into `scripts\windows\compile-bobo-os.ps1`
> (primary), `scripts\create-iso.sh`, `scripts\build.sh` and `boot\grub\grub.cfg`.
> Verified working: GRUB → kernel 6.6.87-bobo → live initrd → squashfs overlay → systemd
> → autologin `bobo` → Wayfire desktop (hardware GL via vmwgfx).

| # | Fix | Why | Where |
|---|-----|-----|-------|
| 1 | **bios.img = `cdboot.img` + `core.img`** (not bare core.img) | Bare core.img → SeaBIOS `int13_cdrom: function 42. Can't use 64bits lba`; ISO never boots | compile-bobo-os.ps1 Step 5; create-iso.sh |
| 2 | **Kernel built-in opts** `BLK_DEV_INITRD, RD_GZIP, VIRTIO_PCI, ATA, SATA_AHCI, ATA_PIIX, BLK_DEV_SR, ISO9660_FS, SQUASHFS, OVERLAY_FS, DRM_VMWGFX, DRM_VBOXVIDEO, DRM_SIMPLEDRM, FB_VESA, FB_EFI` (all `=y`) | Without them the kernel ignores the initrd and can't see the CD/SATA/GPU → unbootable / no display | compile-bobo-os.ps1 Step 2; build.sh |
| 3 | **Build rootfs on NATIVE ext4** (`/root/bobo-rootfs`), never `/mnt/e` | NTFS is case-insensitive (`pam.7.gz` vs `PAM.7.gz`) and corrupts debootstrap → init-less stub | compile-bobo-os.ps1 Step 3 (squashfs reads native rootfs) |
| 4 | **Non-root desktop user `bobo`** + autologin tty1 + Wayfire autostart | Wayfire/Weston **refuse to run as root** (`Unable to drop root`) | compile-bobo-os.ps1 Step 3 |
| 5 | **Install desktop stack** (wayfire, wf-shell, weston, xwayland, kitty, nemo, thunar, NetworkManager, pipewire, libreoffice, epiphany-browser, mesa GL/EGL/GBM, fonts-inter, …) | A minimal rootfs has no desktop | compile-bobo-os.ps1 Step 3 |
| 6 | **`mksquashfs … -mem 512M -processors 2`** | Without a memory cap, mksquashfs OOM-wedges the WSL2 distro on 2 GB+ rootfs | compile-bobo-os.ps1 Step 5 |
| 7 | **`noapic`** on every kernel cmdline | Kernel panics `IO-APIC + timer doesn't work!` under VirtualBox without it | boot\grub\grub.cfg; compile-bobo-os.ps1 Step 5 PRE (live grub.cfg) |
| 8 | **Live-init mounts CD at `/cdrom`** + separate top-level `/lower /upper /newroot` (NOT `/mnt/squashfs` `/mnt/rootfs` which are subdirs of the read-only iso9660) | Old init → `mkdir /mnt/rootfs: Read-only file system`, overlay + switch_root fail | compile-bobo-os.ps1 Step 4 (busybox init heredoc) |

**Notes for any future kernel work:** the working full kernel config (1875 options, all 7
fixes baked in) is saved at `boot\kernel\kernel.config`. The desktop runs as user `bobo`
(password `bobo`), root is on tty2 for rescue. `firefox-esr` is NOT in Ubuntu →
`epiphany-browser` is the shipped browser. VM needs ≥ 3 GB RAM + VMSVGA + 3D for the desktop.

---

## 📋 Session Protocol — MANDATORY

### 🤖 AUTONOMOUS EXECUTION RULES (active permanently, all sessions)
These rules override any default "ask before acting" behaviour for this project:

- **Never ask for confirmation** — make decisions and execute immediately.
- Multiple valid approaches → choose the best one and proceed.
- Missing tool / dependency / file → install or create it autonomously.
- A command fails → try the next logical alternative silently; only stop if ALL alternatives are exhausted.
- Tech choice needed → follow CLAUDE.md recommendations, else pick the most stable/popular option.
- Unknown minor detail (port, timeout, size) → use the most reasonable value and document it in code.
- **Only stop and report** when: (1) everything has failed with no remaining alternatives, OR (2) an action would permanently delete existing user data.

### At the START of every session:
1. Read this `CLAUDE.md` file fully.
2. Read `E:\BOBO-OS\CHECKPOINT.md` if it exists.
3. Announce: *"BOBO OS session started. Last completed phase: [X.Y]. Resuming at phase [X.Z]."*
4. Do NOT re-do work already marked `DONE` in the phase table above.

### At the END of every session:
1. Update the STATUS column in the phase table above for all phases touched this session.
2. Generate / overwrite `E:\BOBO-OS\CHECKPOINT.md` with the template below.
3. Announce: *"Session complete. CHECKPOINT.md updated. Next session starts at phase [X.Y]."*

### CHECKPOINT.md template to fill at end of session:
```
# BOBO OS — Checkpoint
Generated: [DATE TIME]

## Last completed phase: [X.Y — Description]
## Next phase to start: [X.Z — Description]

## Files created this session:
- E:\BOBO-OS\path\to\file1
- E:\BOBO-OS\path\to\file2

## Files modified this session:
- E:\BOBO-OS\CLAUDE.md (phase table updated)

## Test results:
- [Phase X.Y] ✅ Passed / ⚠️ Warning: [detail] / ❌ Failed: [detail]

## Known issues / blockers:
- [None] or [description]

## Notes for next session:
- [Any important context the next session needs to know]

## Exact prompt to resume:
"Read CLAUDE.md and CHECKPOINT.md, then continue BOBO OS development
 starting from phase [X.Z] — [description]."
```

---

## 🚨 If Something Fails

- Try alternative approaches autonomously (see Autonomous Execution Rules above).
- Log the failure attempt in CHECKPOINT.md only if ALL alternatives also fail.
- Only block and report to the user when every reasonable path is exhausted.

---

## 🧩 BOBO Concern Applications (`E:\BOBO-OS\bobo-apps\`)

32 fully-functional GTK4 apps (APP 01–32), each with launcher + `.desktop` + SVG icon.
All Python files pass `py_compile`; ~7,742 lines of real (no-placeholder) code.

| # | App | # | App | # | App | # | App |
|---|-----|---|-----|---|-----|---|-----|
| 01 | bobo-player | 09 | bobo-installer | 17 | bobo-notif | 25 | bobo-code |
| 02 | bobo-monitor | 10 | bobo-update | 18 | bobo-theme | 26 | bobo-vm |
| 03 | bobo-settings | 11 | bobo-backup | 19 | bobo-desk | 27 | bobo-dev |
| 04 | bobo-text | 12 | bobo-printer | 20 | bobo-screen | 28 | bobo-cast |
| 05 | bobo-reader | 13 | bobo-access | 21 | bobo-clip | 29 | bobo-phone |
| 06 | bobo-gallery | 14 | bobo-login | 22 | bobo-vpn | 30 | bobo-ai-local |
| 07 | bobo-archive | 15 | bobo-users | 23 | bobo-share | 31 | bobo-scan |
| 08 | bobo-mail | 16 | bobo-search | 24 | bobo-remote | 32 | bobo-coin |

- **Installer:** `bobo-apps/build-bobo-apps.sh` — installs deps (apt+pip), copies to
  `/usr/bin`, `/usr/share/<app>`, `.desktop`, icons; runs post-install; verifies `--version`.
  - `ESSENTIAL_DEPS` always installed (apps launch). Heavy per-app deps gated by
    `BOBO_APPS_SKIP_DEPS` (1 = lean, 0 = full).
- **Theme:** `bobo-apps/shared/BOBO-Dark-gtk.css` → `/usr/share/themes/BOBO-Dark/`.
- **Keybindings:** `bobo-apps/shared/bobo-wayfire-defaults.ini` → `/etc/bobo-wayfire-defaults.ini`.
- **Build integration:** `compile-bobo-os.ps1` Step 3 copies `bobo-apps` into the rootfs and
  runs the installer in the chroot (lean by default). Set `$env:BOBO_APPS_SKIP_DEPS="0"`
  before the build for a full-featured (large) ISO.

---

## 🍏 BoboXcode — Swift/iOS IDE (`E:\BOBO-OS\bobo-xcode\`)

Standalone Swift/iOS IDE + "BoboiOS Bridge" (App Store publish via a Mac cloud over SSH).
Fully ISOLATED — touches NO existing `bobo-*` app. 26 Python files (~1,982 lines), all pass
`py_compile`. Lives only in `/usr/share/bobo-xcode/` + `/usr/bin/bobo-xcode` + own XDG entries.

- **Layers:** (1) local dev — Swift (official Apple Linux toolchain), Flutter, React Native,
  SPM, sourcekit-lsp completion, QEMU iOS simulator with QMP touch bridge; (2) Bridge —
  paramiko SSH to a Mac cloud, fastlane signing + App Store upload (one-click Publish).
- **Structure:** `engines/` (swift/flutter/react_native/package_manager/lsp_server),
  `simulator/` (qemu_manager/device_profiles/touch_bridge), `bridge/` (mac_connector +
  Fernet-encrypted creds, signing_manager, fastlane_runner, project_packager, appstore_uploader),
  `ui/` (window/editor/file_tree/terminal[VTE 3.91]/build_panel/simulator_panel/swift_preview/
  settings_dialog/style.css), `templates/` (ios_app, swiftui_app, flutter_app, react_native_app).
- **Isolation:** Python **venv** at `/usr/share/bobo-xcode/venv` (launcher prefers it, falls
  back to system libs). Wayfire keybinding **APPENDED** (`<super> KEY_X` → `command_xcode`).
  Inherits the BOBO-Dark theme; only adds `.bobo-publish-btn` etc.
- **Installer:** `bobo-xcode/install.sh` (self-locating, `bash -n` clean). Essential GTK deps
  always installed; heavy toolchain (Swift ~600MB, fastlane, qemu-system-arm, clang) gated by
  `BOBO_XCODE_SKIP_HEAVY` (1 = lean default, 0 = full).
- **Build integration:** `compile-bobo-os.ps1` **Step 3b** copies `bobo-xcode` into the rootfs
  and runs `install.sh` in the chroot (lean by default). Set `$env:BOBO_XCODE_SKIP_HEAVY="0"`
  before the build to bake the full Swift/fastlane toolchain into the ISO.

---

*Last updated by: Claude Code — 2026-06-10 (Session 11 — BoboXcode Swift/iOS IDE + BoboiOS Bridge built in `bobo-xcode/` (isolated) and integrated via Step 3b; see "BoboXcode".)*
*Previous: Session 10 — 32 BOBO concern apps in `bobo-apps/` + pipeline Step 3. Session 9 — full doc. Session 8 — reproducible bootable ISO (8 CRITICAL FIXES).*
*BOBO OS v1.0.0 — E:\BOBO-OS*
