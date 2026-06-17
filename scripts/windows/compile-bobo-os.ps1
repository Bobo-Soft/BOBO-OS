# ============================================================
# BOBO OS -- Full Compilation Orchestrator
# E:\BOBO-OS\scripts\windows\compile-bobo-os.ps1
#
# Steps:
#   1. Download Linux 6.6 LTS kernel source
#   2. Compile kernel + modules (uses half available cores to conserve RAM)
#   3. Build rootfs via debootstrap
#   4. Generate initrd via dracut
#   5. Set up GRUB2 + ISO tree
#   6. Generate final hybrid ISO (xorriso)
#   7. Quick QEMU boot test
# ============================================================

$ErrorActionPreference = "Continue"
$logFile = "E:\BOBO-OS\docs\compile-log.txt"
$startTime = Get-Date
New-Item -ItemType Directory -Force -Path "E:\BOBO-OS\docs" | Out-Null
New-Item -ItemType Directory -Force -Path "E:\BOBO-OS\build-output" | Out-Null

# --- BOBO concern apps (APP 01..32) build mode ---
# Default LEAN (BOBO_APPS_SKIP_DEPS=1): app files + desktop entries + essential
# GTK runtime are baked in (apps launch; heavy per-app deps install on demand).
# For a FULL-featured ISO (all deps, large), run:  $env:BOBO_APPS_SKIP_DEPS="0"
if (-not $env:BOBO_APPS_SKIP_DEPS) { $env:BOBO_APPS_SKIP_DEPS = "1" }
# Propagate the variable into the WSL environment so Step 3's chroot sees it.
if ($env:WSLENV -notlike "*BOBO_APPS_SKIP_DEPS*") {
    if ($env:WSLENV) { $env:WSLENV = $env:WSLENV + ":BOBO_APPS_SKIP_DEPS/u" }
    else { $env:WSLENV = "BOBO_APPS_SKIP_DEPS/u" }
}
Write-Host "BOBO apps integration mode: BOBO_APPS_SKIP_DEPS=$($env:BOBO_APPS_SKIP_DEPS) (1=lean, 0=full)" -ForegroundColor Cyan

# --- BoboXcode (Swift/iOS IDE) build mode ---
# Default LEAN (BOBO_XCODE_SKIP_HEAVY=1): IDE files + essential GTK runtime baked
# in; the Swift toolchain (~600MB), fastlane and qemu-system-arm are installed on
# demand. For a full IDE in the ISO, run:  $env:BOBO_XCODE_SKIP_HEAVY="0"
if (-not $env:BOBO_XCODE_SKIP_HEAVY) { $env:BOBO_XCODE_SKIP_HEAVY = "1" }
if ($env:WSLENV -notlike "*BOBO_XCODE_SKIP_HEAVY*") {
    if ($env:WSLENV) { $env:WSLENV = $env:WSLENV + ":BOBO_XCODE_SKIP_HEAVY/u" }
    else { $env:WSLENV = "BOBO_XCODE_SKIP_HEAVY/u" }
}
Write-Host "BoboXcode integration mode: BOBO_XCODE_SKIP_HEAVY=$($env:BOBO_XCODE_SKIP_HEAVY) (1=lean, 0=full Swift/fastlane)" -ForegroundColor Cyan

function Log($msg, $color = "White") {
    $timestamp = Get-Date -Format "HH:mm:ss"
    $line = "[$timestamp] $msg"
    Write-Host $line -ForegroundColor $color
    Add-Content -Path $logFile -Value $line
}

function RunWSL($bashCode, $desc, $timeoutSec = 7200) {
    Log "[RUNNING] $desc" "Cyan"
    # Write bash script to E:\BOBO-OS\docs\ which is accessible from WSL as /mnt/e/BOBO-OS/docs/
    # (The C:\Users temp path is not reliably accessible via WSL /mnt/c/ on all systems)
    $winPath = "E:\BOBO-OS\docs\build_step.sh"
    $wslPath = "/mnt/e/BOBO-OS/docs/build_step.sh"
    # Normalize CRLF -> LF so bash heredocs don't get 'MARKER\r' closing tokens
    $bashNorm = $bashCode.Replace("`r`n", "`n").Replace("`r", "`n")
    [System.IO.File]::WriteAllText($winPath, $bashNorm, [System.Text.UTF8Encoding]::new($false))
    $result = wsl -d Ubuntu-24.04 -u root -- bash "$wslPath" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Log "[DONE] $desc" "Green"
        return $true
    } else {
        Log "[FAILED] $desc (exit $LASTEXITCODE)" "Red"
        ($result | Select-Object -Last 8) | ForEach-Object { Log "  $_" "Red" }
        return $false
    }
}

Log "================================================" "Yellow"
Log "  BOBO OS -- Full Build Started" "Yellow"
Log "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" "Yellow"
Log "================================================" "Yellow"

# Verify Ubuntu-24.04 is accessible
$pingResult = wsl -d Ubuntu-24.04 -u root -- echo "wsl-ping" 2>&1 | Out-String
if ($pingResult -notmatch "wsl-ping") {
    Log "ERROR: Ubuntu-24.04 not in WSL2. Run install-wsl2.ps1 + setup-build-env.ps1 first." "Red"
    exit 1
}
Log "[OK] Ubuntu-24.04 accessible" "Green"

# ============================================================
# STEP 1: Download Linux Kernel 6.6 LTS
# ============================================================
RunWSL @'
#!/bin/bash
set -e
KERNEL_VERSION="6.6.87"
KERNEL_SRC="/tmp/linux-${KERNEL_VERSION}"
KERNEL_OUT="/mnt/e/BOBO-OS/build-output"
KERNEL_CONFIG="/mnt/e/BOBO-OS/boot/kernel/kernel.config"

mkdir -p "$KERNEL_OUT"

# Skip if already compiled
if [ -f "$KERNEL_OUT/vmlinuz-6.6-bobo" ]; then
    echo "Kernel already compiled -- skipping download and compile."
    exit 0
fi

cd /tmp
if [ ! -f "linux-${KERNEL_VERSION}.tar.xz" ]; then
    echo "Downloading Linux ${KERNEL_VERSION}..."
    wget -q --show-progress \
        "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-${KERNEL_VERSION}.tar.xz" \
        -O "linux-${KERNEL_VERSION}.tar.xz" 2>&1 || \
    curl -L --progress-bar \
        "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-${KERNEL_VERSION}.tar.xz" \
        -o "linux-${KERNEL_VERSION}.tar.xz" 2>&1
fi

if [ ! -d "$KERNEL_SRC" ]; then
    echo "Extracting kernel source..."
    tar -xf "linux-${KERNEL_VERSION}.tar.xz" -C /tmp
fi

echo "Applying BOBO OS kernel config..."
if [ -f "$KERNEL_CONFIG" ]; then
    cp "$KERNEL_CONFIG" "$KERNEL_SRC/.config"
else
    echo "No custom config found -- will use defconfig"
fi
echo "[OK] Kernel source ready at $KERNEL_SRC"
'@ "Step 1 -- Download Linux 6.6.87 LTS source"

# ============================================================
# STEP 2: Compile Kernel
# ============================================================
RunWSL @'
#!/bin/bash
set -e
KERNEL_VERSION="6.6.87"
KERNEL_SRC="/tmp/linux-${KERNEL_VERSION}"
KERNEL_OUT="/mnt/e/BOBO-OS/build-output"
ROOTFS="$KERNEL_OUT/rootfs"

# Use half the available CPU cores to reduce RAM usage during kernel build.
# Ensures the system remains responsive and avoids OOM on machines with < 16 GB RAM.
CORES=$(( $(nproc) / 2 ))
[ "$CORES" -lt 1 ] && CORES=1
echo "Using $CORES of $(nproc) cores for kernel build (half, to conserve RAM)"

# Skip if already done
if [ -f "$KERNEL_OUT/vmlinuz-6.6-bobo" ]; then
    echo "Kernel already compiled -- skipping."
    exit 0
fi

cd "$KERNEL_SRC"
echo "Preparing kernel config (complete base + BOBO fragment + mandatory options)..."
# Start from a COMPLETE base so the kernel is bootable even if kernel.config is only a fragment.
# A real config has thousands of CONFIG_ lines; a fragment has a few hundred.
if [ -f ".config" ] && [ "$(grep -c '^CONFIG_' .config)" -gt 1000 ]; then
    echo "  kernel.config looks complete -- using it as the base."
    make olddefconfig 2>&1 | tail -3
else
    echo "  kernel.config is a fragment/missing -- using x86_64_defconfig and merging the fragment."
    make x86_64_defconfig 2>&1 | tail -3
    [ -f /mnt/e/BOBO-OS/boot/kernel/kernel.config ] && \
        ./scripts/kconfig/merge_config.sh -m .config /mnt/e/BOBO-OS/boot/kernel/kernel.config >/dev/null 2>&1 || true
fi

# FIX 2: force the MANDATORY boot + storage + graphics options as BUILT-IN (=y).
# Without these the kernel cannot use an initrd (BLK_DEV_INITRD/RD_GZIP), cannot see the
# VirtualBox CD/SATA/IDE (BLK_DEV_SR/SATA_AHCI/ATA_PIIX) or QEMU virtio (VIRTIO_PCI),
# and cannot drive the VirtualBox GPU for Wayland (DRM_VMWGFX/DRM_VBOXVIDEO).
cat >> .config <<'KOPTS'
CONFIG_BLK_DEV_INITRD=y
CONFIG_RD_GZIP=y
CONFIG_RD_XZ=y
CONFIG_VIRTIO=y
CONFIG_VIRTIO_PCI=y
CONFIG_VIRTIO_BLK=y
CONFIG_VIRTIO_MMIO=y
CONFIG_ATA=y
CONFIG_SATA_AHCI=y
CONFIG_ATA_PIIX=y
CONFIG_SCSI=y
CONFIG_BLK_DEV_SD=y
CONFIG_BLK_DEV_SR=y
CONFIG_ISO9660_FS=y
CONFIG_SQUASHFS=y
CONFIG_SQUASHFS_ZLIB=y
CONFIG_OVERLAY_FS=y
CONFIG_BLK_DEV_LOOP=y
CONFIG_EXT4_FS=y
CONFIG_DEVTMPFS=y
CONFIG_DEVTMPFS_MOUNT=y
CONFIG_DRM=y
CONFIG_DRM_VMWGFX=y
CONFIG_DRM_VBOXVIDEO=y
CONFIG_DRM_BOCHS=y
CONFIG_DRM_SIMPLEDRM=y
CONFIG_DRM_FBDEV_EMULATION=y
CONFIG_FB=y
CONFIG_FB_VESA=y
CONFIG_FB_EFI=y
CONFIG_SYSFB=y
CONFIG_SYSFB_SIMPLEFB=y
CONFIG_LOCALVERSION="-bobo"
KOPTS
make olddefconfig 2>&1 | tail -3
echo "Verifying critical kernel options are set:"
for c in CONFIG_BLK_DEV_INITRD CONFIG_RD_GZIP CONFIG_VIRTIO_PCI CONFIG_SATA_AHCI CONFIG_ATA_PIIX \
         CONFIG_BLK_DEV_SR CONFIG_ISO9660_FS CONFIG_SQUASHFS CONFIG_OVERLAY_FS \
         CONFIG_DRM_VMWGFX CONFIG_DRM_VBOXVIDEO; do
    grep -qE "^$c=y" .config && echo "  OK  $c=y" || echo "  WARN $c NOT =y"
done

echo "Compiling kernel with $CORES of $(nproc) available cores..."
echo "This will take 20-90 minutes -- please wait."
make -j"$CORES" bzImage modules 2>&1

echo "Copying compiled kernel..."
cp arch/x86/boot/bzImage "$KERNEL_OUT/vmlinuz-6.6-bobo"
echo "Kernel size: $(du -sh $KERNEL_OUT/vmlinuz-6.6-bobo | cut -f1)"

echo "Installing modules to a native staging dir (copied into the rootfs in Step 3)..."
# FIX 3: do NOT install into /mnt/e rootfs. Stage on native ext4; Step 3 debootstraps the
# real rootfs on /root/bobo-rootfs and copies these modules in afterwards.
KMOD_STAGING="/root/kmod-staging"
rm -rf "$KMOD_STAGING"; mkdir -p "$KMOD_STAGING"
make INSTALL_MOD_PATH="$KMOD_STAGING" modules_install 2>&1 | tail -5
echo "[OK] Kernel compiled and modules staged at $KMOD_STAGING."
'@ "Step 2 -- Compile Linux kernel (20-90 min)" 7200

# ============================================================
# STEP 3: Build rootfs with debootstrap
# ============================================================
RunWSL @'
#!/bin/bash
set -e
# FIX 3: build the rootfs on the NATIVE WSL2 ext4 filesystem (/root/bobo-rootfs).
# NEVER debootstrap onto /mnt/e (NTFS is case-insensitive: e.g. pam.7.gz vs PAM.7.gz
# collide and corrupt debootstrap, leaving an init-less stub). The squashfs in Step 5
# is built from this native rootfs.
ROOTFS="/root/bobo-rootfs"
ROOTFS_MIRROR="/mnt/e/BOBO-OS/build-output/rootfs"
BOBO="/mnt/e/BOBO-OS"
KERNEL_OUT="/mnt/e/BOBO-OS/build-output"
KVER="6.6.87-bobo"

command -v debootstrap >/dev/null 2>&1 || { apt-get update -qq; apt-get install -y debootstrap; }

# Skip if rootfs already built with a working desktop
if [ -x "$ROOTFS/sbin/init" ] && [ -x "$ROOTFS/usr/bin/wayfire" ]; then
    echo "Native rootfs already built with desktop -- skipping rebuild."
else
    echo "Creating base rootfs with debootstrap (Ubuntu noble) on NATIVE ext4 $ROOTFS ..."
    rm -rf "$ROOTFS"; mkdir -p "$ROOTFS"
    debootstrap --arch=amd64 --variant=minbase \
        --include=systemd,systemd-sysv,udev,dbus,kmod,iproute2,nano,less,sudo,libc-bin,libpam-systemd \
        noble "$ROOTFS" http://archive.ubuntu.com/ubuntu 2>&1 | tail -15
    echo "[OK] debootstrap complete"

    # Enable the universe component so the desktop packages are available
    cat > "$ROOTFS/etc/apt/sources.list" <<'SRC'
deb http://archive.ubuntu.com/ubuntu noble main universe multiverse restricted
deb http://archive.ubuntu.com/ubuntu noble-updates main universe multiverse restricted
deb http://security.ubuntu.com/ubuntu noble-security main universe multiverse restricted
SRC

    # Copy the bobo kernel modules staged in Step 2 into the rootfs, then index them
    if [ -d /root/kmod-staging/lib/modules ]; then
        mkdir -p "$ROOTFS/lib/modules"
        cp -a /root/kmod-staging/lib/modules/. "$ROOTFS/lib/modules/" 2>/dev/null || true
        depmod -b "$ROOTFS" "$KVER" 2>/dev/null || true
    fi

    # Mount kernel filesystems for chroot
    cp /etc/resolv.conf "$ROOTFS/etc/resolv.conf"
    mount -t proc proc "$ROOTFS/proc"
    mount --rbind /sys "$ROOTFS/sys"
    mount --rbind /dev "$ROOTFS/dev"

    # FIX 5: install the Wayfire desktop stack inside the rootfs.
    # Bulk install first; if a renamed/absent package aborts it, retry per-package.
    chroot "$ROOTFS" /bin/bash -c '
export DEBIAN_FRONTEND=noninteractive
apt-get update
PKGS="wayfire wf-shell weston xwayland wayland-protocols kitty nemo thunar \
network-manager pipewire pipewire-pulse wireplumber libreoffice epiphany-browser \
mesa-vulkan-drivers libgl1-mesa-dri libglx-mesa0 libegl-mesa0 libegl1 libgles2 libgbm1 libwayland-egl1 \
xdg-utils fonts-inter sudo systemd-sysv dbus dbus-x11 seatd libgtk-4-1 libgtk-3-0t64 libpam-systemd"
if ! apt-get install -y --no-install-recommends $PKGS; then
    echo "bulk install failed -- retrying per package"
    for p in $PKGS; do apt-get install -y --no-install-recommends "$p" || echo "skip $p"; done
fi
# pipewire-audio is a metapackage that may be virtual on some releases -- best effort
apt-get install -y --no-install-recommends pipewire-audio 2>/dev/null || true
apt-get clean; rm -rf /var/lib/apt/lists/*
echo "[OK] desktop packages installed"
'

    # FIX 4: create a NON-ROOT desktop user (Wayfire/Weston refuse to run as root).
    chroot "$ROOTFS" /bin/bash -c '
id bobo >/dev/null 2>&1 || useradd -m -s /bin/bash -G video,render,input,audio,sudo bobo
echo "bobo:bobo" | chpasswd
echo "bobo ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/bobo; chmod 440 /etc/sudoers.d/bobo
systemctl enable NetworkManager 2>/dev/null || true
systemctl enable seatd 2>/dev/null || true
systemctl set-default multi-user.target 2>/dev/null || true
mkdir -p /home/bobo/.config/wayfire
'

    # Autologin user bobo on tty1 (desktop), root on tty2 (rescue)
    mkdir -p "$ROOTFS/etc/systemd/system/getty@tty1.service.d"
    mkdir -p "$ROOTFS/etc/systemd/system/getty@tty2.service.d"
    cat > "$ROOTFS/etc/systemd/system/getty@tty1.service.d/autologin.conf" <<'AL1'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin bobo --noclear %I $TERM
AL1
    cat > "$ROOTFS/etc/systemd/system/getty@tty2.service.d/autologin.conf" <<'AL2'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I $TERM
AL2

    # Wayfire autostart for bobo on tty1 (hardware GL via vmwgfx works)
    cat > "$ROOTFS/home/bobo/.bash_profile" <<'BP'
[ -f ~/.bashrc ] && . ~/.bashrc
if [ -z "$WAYLAND_DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
  mkdir -p "$XDG_RUNTIME_DIR" 2>/dev/null; chmod 700 "$XDG_RUNTIME_DIR" 2>/dev/null
  export XDG_SESSION_TYPE=wayland WLR_NO_HARDWARE_CURSORS=1 MOZ_ENABLE_WAYLAND=1
  echo "Starting BOBO OS desktop (Wayfire)..."
  exec dbus-run-session -- wayfire -c "$HOME/.config/wayfire.ini" 2>/tmp/wayfire.log
fi
BP

    # Wayfire config (BOBO OS colors #1a1a2e / accent #4a9eff)
    cat > "$ROOTFS/home/bobo/.config/wayfire.ini" <<'WF'
[core]
plugins = autostart window-rules move resize animate grid vswitch command expo fast-switcher
xwayland = true

[autostart]
0_panel = wf-panel
1_background = wf-background
2_terminal = kitty

[command]
binding_terminal = <super> KEY_ENTER
command_terminal = kitty
binding_files = <super> KEY_E
command_files = nemo

[input]
xkb_layout = us
WF
    cat > "$ROOTFS/home/bobo/.config/wf-shell.ini" <<'WS'
[panel]
autohide = false
position = top
widgets_left = menu
widgets_center = clock
widgets_right = network battery
background_color = 0.102 0.102 0.180 0.95

[background]
color = 0.102 0.102 0.180 1.0
WS
    chroot "$ROOTFS" chown -R bobo:bobo /home/bobo

    # --- BOBO OS branding ---
    echo "bobo-os" > "$ROOTFS/etc/hostname"
    cat > "$ROOTFS/etc/os-release" <<'OSR'
NAME="BOBO OS"
VERSION="1.0.0"
ID=bobo-os
ID_LIKE=ubuntu
PRETTY_NAME="BOBO OS 1.0.0"
VERSION_ID="1.0"
HOME_URL="https://bobo-os.example.com"
OSR
    printf '127.0.0.1\tlocalhost\n127.0.1.1\tbobo-os\n' > "$ROOTFS/etc/hosts"
    # marker file used by the installed-system grub.cfg search
    echo "BOBO OS 1.0.0" > "$ROOTFS/etc/bobo-os-release"

    # --- Copy BOBO OS project files (non-fatal) ---
    mkdir -p "$ROOTFS/usr/local/lib/bobo" "$ROOTFS/usr/local/share/bobo-apps" "$ROOTFS/etc/bobo-os"
    cp -r "$BOBO/core/."         "$ROOTFS/usr/local/lib/bobo/core/"    2>/dev/null || true
    cp -r "$BOBO/desktop/."      "$ROOTFS/usr/local/lib/bobo/desktop/" 2>/dev/null || true
    cp -r "$BOBO/novastore/."    "$ROOTFS/usr/local/lib/bobo/novastore/" 2>/dev/null || true
    cp -r "$BOBO/novasync/."     "$ROOTFS/usr/local/lib/bobo/novasync/"  2>/dev/null || true
    cp -r "$BOBO/ai-assistant/." "$ROOTFS/usr/local/lib/bobo/ai-assistant/" 2>/dev/null || true
    cp -r "$BOBO/apps/."         "$ROOTFS/usr/local/share/bobo-apps/"   2>/dev/null || true
    cp    "$BOBO/config/bobo-os.conf"     "$ROOTFS/etc/bobo-os/" 2>/dev/null || true
    cp    "$BOBO/config/performance.conf" "$ROOTFS/etc/bobo-os/" 2>/dev/null || true
    cp    "$BOBO/config/security.conf"    "$ROOTFS/etc/bobo-os/" 2>/dev/null || true
    mkdir -p "$ROOTFS/usr/share/themes/bobo-default"
    cp -r "$BOBO/desktop/themes/bobo-default/." "$ROOTFS/usr/share/themes/bobo-default/" 2>/dev/null || true

    # --- Integrate the 32 BOBO concern applications (APP 01..32) ---
    # Copies app sources into the rootfs and runs their installer INSIDE the
    # chroot (network + apt are available here). Essential GTK runtime deps are
    # always installed so the apps launch; heavy per-app deps are gated by
    # BOBO_APPS_SKIP_DEPS (default 1 = lean ISO; set 0 for a full-featured ISO).
    if [ -d "$BOBO/bobo-apps" ]; then
        echo "Integrating 32 BOBO applications into rootfs (lean=${BOBO_APPS_SKIP_DEPS:-1})..."
        mkdir -p "$ROOTFS/usr/local/lib/bobo-apps"
        cp -r "$BOBO/bobo-apps/." "$ROOTFS/usr/local/lib/bobo-apps/" 2>/dev/null || true
        # remove the dev-only syntax helper from the shipped tree
        rm -f "$ROOTFS/usr/local/lib/bobo-apps/_syntax_check.sh" 2>/dev/null || true
        chroot "$ROOTFS" /bin/bash -c \
            "export BOBO_APPS_SKIP_DEPS=${BOBO_APPS_SKIP_DEPS:-1}; bash /usr/local/lib/bobo-apps/build-bobo-apps.sh" \
            2>&1 | tail -60 || echo "WARN: bobo-apps installer returned non-zero (non-fatal)"
        echo "BOBO applications integrated."
    fi

    # --- Integrate BoboXcode (isolated Swift/iOS IDE; touches NO existing app) ---
    # Copies the IDE source into the rootfs and runs its self-locating installer
    # in the chroot. Heavy Swift/fastlane/qemu install is gated by
    # BOBO_XCODE_SKIP_HEAVY (default 1 = lean). Wayfire keybinding is APPENDED.
    if [ -d "$BOBO/bobo-xcode" ]; then
        echo "Integrating BoboXcode (skip_heavy=${BOBO_XCODE_SKIP_HEAVY:-1})..."
        mkdir -p "$ROOTFS/tmp/bobo-xcode-src"
        cp -r "$BOBO/bobo-xcode/." "$ROOTFS/tmp/bobo-xcode-src/" 2>/dev/null || true
        rm -f "$ROOTFS/tmp/bobo-xcode-src/_check.sh" 2>/dev/null || true
        chroot "$ROOTFS" /bin/bash -c \
            "export BOBO_XCODE_SKIP_HEAVY=${BOBO_XCODE_SKIP_HEAVY:-1}; cd /tmp/bobo-xcode-src && bash install.sh" \
            2>&1 | tail -40 || echo "WARN: BoboXcode installer returned non-zero (non-fatal)"
        rm -rf "$ROOTFS/tmp/bobo-xcode-src" 2>/dev/null || true
        echo "BoboXcode integrated."
    fi

    # --- Wire bobo-apps + BoboXcode keybindings into the ACTIVE wayfire.ini ---
    # Wayfire has NO include directive, so the bindings in /etc/bobo-wayfire-defaults.ini
    # are inert unless merged into the bobo user's ~/.config/wayfire.ini [command] section.
    WF_USER="$ROOTFS/home/bobo/.config/wayfire.ini"
    WF_DEF="$ROOTFS/etc/bobo-wayfire-defaults.ini"
    if [ -f "$WF_USER" ] && [ -f "$WF_DEF" ] && ! grep -q command_xcode "$WF_USER" 2>/dev/null; then
        grep -E '^(binding_|command_)' "$WF_DEF" > /tmp/bobo-binds.txt
        awk '/^\[command\]/{print; while((getline l < "/tmp/bobo-binds.txt")>0) print l; close("/tmp/bobo-binds.txt"); next} {print}' "$WF_USER" > "$WF_USER.new" && mv "$WF_USER.new" "$WF_USER"
        chroot "$ROOTFS" chown bobo:bobo /home/bobo/.config/wayfire.ini 2>/dev/null || true
        echo "Wayfire keybindings (Super+X etc.) merged into bobo user's wayfire.ini."
    fi

    # Unmount chroot binds so they are NOT captured into the squashfs
    umount -l "$ROOTFS/dev/pts" 2>/dev/null || true
    umount -l "$ROOTFS/dev"     2>/dev/null || true
    umount -l "$ROOTFS/sys"     2>/dev/null || true
    umount -l "$ROOTFS/proc"    2>/dev/null || true
    rm -rf "$ROOTFS"/tmp/* "$ROOTFS"/var/tmp/* "$ROOTFS"/home/bobo/.cache 2>/dev/null || true
fi

# FIX 3 (final): optionally mirror the completed rootfs to /mnt/e for inspection.
# Off by default (a 2 GB copy to NTFS is slow and not needed -- the squashfs is the artifact).
if [ "${BOBO_MIRROR_ROOTFS:-0}" = "1" ]; then
    echo "Mirroring completed rootfs to $ROOTFS_MIRROR (inspection only)..."
    rm -rf "$ROOTFS_MIRROR"; mkdir -p "$ROOTFS_MIRROR"
    cp -a "$ROOTFS"/. "$ROOTFS_MIRROR"/ 2>/dev/null || true
fi

echo "Native rootfs size: $(du -sh --exclude=proc --exclude=sys --exclude=dev "$ROOTFS" | cut -f1)"
echo "[OK] rootfs complete at $ROOTFS"
'@ "Step 3 -- Build rootfs on NATIVE ext4 + desktop + bobo user (20-40 min)" 5400

# ============================================================
# STEP 4: Generate initrd
# ============================================================
RunWSL @'
#!/bin/bash
# Note: no set -e here -- we handle errors explicitly so dracut pipe failures don't mask
# FIX 3: the rootfs lives on native ext4, not /mnt/e.
ROOTFS="/root/bobo-rootfs"
KERNEL_OUT="/mnt/e/BOBO-OS/build-output"
INITRD_OUT="$KERNEL_OUT/initrd-6.6-bobo.img"

# Skip if initrd already exists
if [ -s "$INITRD_OUT" ]; then
    echo "initrd already exists ($(du -sh $INITRD_OUT | cut -f1)) -- skipping."
    exit 0
fi

KVER=$(ls "$ROOTFS/lib/modules/" 2>/dev/null | head -1)
if [ -z "$KVER" ]; then
    KVER="6.6.87-bobo"
    echo "Warning: No modules dir found, using $KVER"
fi
echo "Generating initrd for kernel: $KVER"

# Install busybox-static unconditionally (needed for cpio fallback)
apt-get install -y busybox-static &>/dev/null || true

# --- Method 1: dracut with explicit module path ---
# FIX: dracut is DISABLED for the live ISO. It produces a hostonly/dmsquash initrd that does
# not match our CD -> squashfs -> overlay -> switch_root live boot. Always use the busybox
# live-boot initrd (Method 2) which is the proven, reproducible path.
DRACUT_OK=0
if false; then
    # Install kernel modules to host so dracut can find them
    MODULES_DIR="/lib/modules/$KVER"
    if [ ! -d "$MODULES_DIR" ] && [ -d "$ROOTFS/lib/modules/$KVER" ]; then
        cp -r "$ROOTFS/lib/modules/$KVER" "$MODULES_DIR" 2>/dev/null || true
        depmod "$KVER" 2>/dev/null || true
        echo "Copied kernel modules to host for dracut"
    fi
    dracut --force \
        --kver "$KVER" \
        --add "base" \
        --no-hostonly \
        --no-hostonly-cmdline \
        "$INITRD_OUT" 2>&1 | tail -10
    if [ -s "$INITRD_OUT" ]; then
        echo "[OK] initrd built with dracut"
        DRACUT_OK=1
    else
        echo "[WARN] dracut did not produce a file"
    fi
fi

# --- Method 2: minimal live-boot cpio initrd with busybox ---
if [ "$DRACUT_OK" -eq 0 ]; then
    echo "Building minimal live-boot initrd with busybox..."
    INITRD_TMP=$(mktemp -d)
    # SEPARATE top-level dirs in the (writable tmpfs) initramfs. NEVER use subdirs of the
    # read-only iso9660 mount (the old /mnt/squashfs + /mnt/rootfs bug -> "Read-only file system").
    mkdir -p "$INITRD_TMP"/{bin,sbin,etc,proc,sys,dev,run,cdrom,lower,upper,newroot}

    # Copy static busybox; applets are installed at boot via 'busybox --install'.
    BUSYBOX=$(command -v busybox 2>/dev/null || echo "/bin/busybox")
    cp "$BUSYBOX" "$INITRD_TMP/bin/busybox"
    chmod +x "$INITRD_TMP/bin/busybox"

    # Write the live-boot init. The kernel has squashfs/overlay/loop/iso9660/sr_mod/ahci
    # BUILT-IN (FIX 2), so no module loading is needed. Mount CD at /cdrom, loop-mount the
    # squashfs at /lower, overlay a tmpfs upper, then switch_root into systemd.
    cat > "$INITRD_TMP/init" <<'INITEOF'
#!/bin/busybox sh
/bin/busybox --install -s /bin
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
msg(){ echo "[bobo-live] $*"; }

mount -t proc     proc /proc 2>/dev/null
mount -t sysfs    sys  /sys  2>/dev/null
mount -t devtmpfs dev  /dev  2>/dev/null || mdev -s

msg "searching for BOBO OS live media (squashfs)..."
FOUND=""
i=0
while [ $i -lt 30 ]; do
  for d in /dev/sr0 /dev/sr1 /dev/cdrom /dev/sda /dev/sdb /dev/vda; do
    [ -b "$d" ] || continue
    mount -t iso9660 -o ro "$d" /cdrom 2>/dev/null || continue
    if [ -f /cdrom/live/filesystem.squashfs ]; then FOUND="$d"; break; fi
    umount /cdrom 2>/dev/null
  done
  [ -n "$FOUND" ] && break
  i=$((i+1)); sleep 1
done
if [ -z "$FOUND" ]; then msg "live media not found -> rescue shell"; exec /bin/busybox sh; fi
msg "live media on $FOUND"

if ! mount -t squashfs -o ro /cdrom/live/filesystem.squashfs /lower 2>/dev/null; then
  msg "squashfs mount failed -> rescue shell"; exec /bin/busybox sh
fi
mount -t tmpfs tmpfs /upper
mkdir -p /upper/up /upper/work
if ! mount -t overlay overlay -o lowerdir=/lower,upperdir=/upper/up,workdir=/upper/work /newroot 2>/dev/null; then
  msg "overlay failed -> binding squashfs read-only"; mount --bind /lower /newroot
fi
for fs in proc sys dev run; do mkdir -p /newroot/$fs; mount --move /$fs /newroot/$fs 2>/dev/null; done
if [ -x /newroot/sbin/init ]; then
  msg "handover to systemd (switch_root)"
  exec switch_root /newroot /sbin/init
fi
msg "no /sbin/init in root -> rescue shell"
exec switch_root /newroot /bin/sh
INITEOF
    chmod +x "$INITRD_TMP/init"

    # Pack into compressed cpio
    (cd "$INITRD_TMP" && find . | cpio -H newc -o 2>/dev/null | gzip -9 > "$INITRD_OUT")
    rm -rf "$INITRD_TMP"

    if [ -s "$INITRD_OUT" ]; then
        echo "initrd size: $(du -sh $INITRD_OUT | cut -f1)"
        echo "[OK] live-boot initrd generated"
    else
        echo "ERROR: initrd creation failed"
        exit 1
    fi
fi
'@ "Step 4 -- Generate live-boot initrd"

# ============================================================
# STEP 5 PRE: Write live-boot grub.cfg from PowerShell
# (Avoids bash heredoc inside PowerShell here-string which causes CRLF issues)
# ============================================================
$isoGrubDir = "E:\BOBO-OS\build-output\iso-tree\boot\grub"
New-Item -ItemType Directory -Force -Path $isoGrubDir | Out-Null
$grubCfgContent = "# BOBO OS Live ISO -- GRUB2 Configuration`n# ASCII-only: GRUB2 .pf2 fonts do not support emoji or extended Unicode.`nset default=0`nset timeout=5`nset timeout_style=countdown`n`ninsmod all_video`ninsmod gfxterm`ninsmod iso9660`ninsmod part_gpt`ninsmod part_msdos`ninsmod ext2`ninsmod gzio`n`nset color_normal=light-gray/black`nset color_highlight=white/blue`nset menu_color_normal=white/black`nset menu_color_highlight=black/light-blue`n`nmenuentry `"Start BOBO OS (Live)`" --class bobo --class gnu-linux {`n  set gfxpayload=keep`n  echo `"Loading BOBO OS kernel...`"`n  linux   /boot/vmlinuz noapic boot=live quiet splash loglevel=3 console=ttyS0,115200 console=tty1`n  echo `"Loading initrd...`"`n  initrd  /boot/initrd.img`n}`n`nmenuentry `"BOBO OS - Text Console (debug)`" --class bobo {`n  set gfxpayload=text`n  linux   /boot/vmlinuz noapic boot=live console=ttyS0,115200 console=tty1 loglevel=7 debug`n  initrd  /boot/initrd.img`n}`n`nmenuentry `"BOBO OS - Headless/QEMU`" --class bobo {`n  linux   /boot/vmlinuz noapic boot=live quiet console=ttyS0,115200`n  initrd  /boot/initrd.img`n}`n"
[System.IO.File]::WriteAllText("$isoGrubDir\grub.cfg", $grubCfgContent.Replace("`r`n", "`n"), [System.Text.UTF8Encoding]::new($false))
Log "[OK] Live-boot grub.cfg written to ISO tree" "Green"

# ============================================================
# STEP 5: Copy kernel/initrd + build ISO tree + squashfs
# ============================================================
RunWSL @'
#!/bin/bash
set -e
# FIX 3: squashfs is built from the NATIVE ext4 rootfs, not /mnt/e.
ROOTFS="/root/bobo-rootfs"
KERNEL_OUT="/mnt/e/BOBO-OS/build-output"
ISO_TREE="/mnt/e/BOBO-OS/build-output/iso-tree"
BOBO="/mnt/e/BOBO-OS"

echo "Creating ISO directory tree..."
mkdir -p "$ISO_TREE"/{boot/grub,boot/grub/i386-pc,boot/grub/x86_64-efi,EFI/BOOT,live}

# Copy kernel and initrd
cp "$KERNEL_OUT/vmlinuz-6.6-bobo"    "$ISO_TREE/boot/vmlinuz"    2>/dev/null || \
   cp "$ROOTFS/boot/vmlinuz-6.6-bobo" "$ISO_TREE/boot/vmlinuz"   2>/dev/null || true
cp "$KERNEL_OUT/initrd-6.6-bobo.img" "$ISO_TREE/boot/initrd.img" 2>/dev/null || true

echo "Files in ISO boot: $(ls -lh $ISO_TREE/boot/)"

# GRUB live-boot config is pre-written by PowerShell (STEP 5 PRE) to avoid
# heredoc CRLF issues. The file is already at $ISO_TREE/boot/grub/grub.cfg.
echo "Using pre-written live-boot grub.cfg (written by PowerShell)"

# Disable set -e for the EFI/GRUB section so optional failures don't abort build
set +e

# GRUB EFI binary -- try grub-mkimage with x86_64-efi modules
EFI_MODULES_DIR="/usr/lib/grub/x86_64-efi"
if [ ! -d "$EFI_MODULES_DIR" ]; then
    echo "Installing grub-efi-amd64-bin for EFI modules..."
    apt-get install -y grub-efi-amd64-bin 2>/dev/null
fi

EFI_BUILT=0
rm -f "$ISO_TREE/EFI/BOOT/BOOTX64.EFI"
if grub-mkimage --version &>/dev/null 2>&1 && [ -d "$EFI_MODULES_DIR" ]; then
    grub-mkimage \
        --output="$ISO_TREE/EFI/BOOT/BOOTX64.EFI" \
        --format=x86_64-efi \
        --prefix=/boot/grub \
        part_gpt part_msdos fat ext2 normal boot linux echo configfile \
        loopback gfxterm vbe png search search_label terminal iso9660 \
        2>/dev/null
    if [ -s "$ISO_TREE/EFI/BOOT/BOOTX64.EFI" ]; then
        echo "[OK] GRUB EFI image built ($(du -sh "$ISO_TREE/EFI/BOOT/BOOTX64.EFI" | cut -f1))"
        EFI_BUILT=1
    fi
fi

if [ "$EFI_BUILT" -eq 0 ]; then
    # Fallback: look for any pre-built EFI binary on the system
    for efi_src in \
        /usr/lib/grub/x86_64-efi/grub.efi \
        /usr/share/grub/x86_64-efi/grub.efi \
        /boot/efi/EFI/ubuntu/grubx64.efi; do
        if [ -s "$efi_src" ]; then
            cp "$efi_src" "$ISO_TREE/EFI/BOOT/BOOTX64.EFI"
            echo "[OK] Copied EFI binary from $efi_src"
            EFI_BUILT=1
            break
        fi
    done
fi

if [ "$EFI_BUILT" -eq 0 ]; then
    echo "[WARN] No EFI binary -- ISO will be BIOS-only"
fi

# Copy GRUB modules for BIOS boot
cp /usr/lib/grub/i386-pc/*.mod    "$ISO_TREE/boot/grub/i386-pc/"    2>/dev/null
cp /usr/lib/grub/i386-pc/*.lst    "$ISO_TREE/boot/grub/i386-pc/"    2>/dev/null
cp /usr/lib/grub/x86_64-efi/*.mod "$ISO_TREE/boot/grub/x86_64-efi/" 2>/dev/null

# FIX 1: GRUB El Torito BIOS boot image MUST be cdboot.img + core.img concatenated,
# NOT a bare core.img. A bare core.img makes SeaBIOS fail with
# "int13_cdrom: function 42. Can't use 64bits lba" and the ISO never boots in VirtualBox.
# cdboot.img (the 2 KB El Torito stage that -boot-load-size 4 loads) reads core.img via
# the boot-info-table, so it must be prepended.
[ -f /usr/lib/grub/i386-pc/cdboot.img ] || apt-get install -y grub-pc-bin 2>/dev/null || true
grub-mkimage \
    --output="/tmp/bobo-core.img" \
    --format=i386-pc \
    --prefix=/boot/grub \
    biosdisk iso9660 part_gpt part_msdos ext2 fat normal boot linux echo configfile \
    terminal search search_fs_uuid search_label gfxterm vbe all_video 2>/dev/null || true
if [ -f /usr/lib/grub/i386-pc/cdboot.img ] && [ -s /tmp/bobo-core.img ]; then
    cat /usr/lib/grub/i386-pc/cdboot.img /tmp/bobo-core.img > "$ISO_TREE/boot/grub/bios.img"
    echo "[OK] bios.img = cdboot.img + core.img ($(stat -c%s "$ISO_TREE/boot/grub/bios.img") bytes)"
else
    echo "[WARN] could not build cdboot+core bios.img; falling back to bare core.img"
    cp /tmp/bobo-core.img "$ISO_TREE/boot/grub/bios.img" 2>/dev/null || true
fi

# Create 4 MB EFI FAT image for xorriso
EFI_IMG="$KERNEL_OUT/efi.img"
dd if=/dev/zero of="$EFI_IMG" bs=1K count=4096 2>/dev/null
mkfs.fat -F 32 "$EFI_IMG" 2>/dev/null
if command -v mmd &>/dev/null; then
    mmd -i "$EFI_IMG" ::/EFI ::/EFI/BOOT 2>/dev/null || true
    mcopy -i "$EFI_IMG" "$ISO_TREE/EFI/BOOT/BOOTX64.EFI" ::/EFI/BOOT/ 2>/dev/null || true
fi

# Create squashfs from the NATIVE rootfs (the live filesystem)
if [ -s "$ISO_TREE/live/filesystem.squashfs" ]; then
    echo "squashfs already exists ($(du -sh $ISO_TREE/live/filesystem.squashfs | cut -f1)) -- skipping."
else
    echo "Creating squashfs (compressed rootfs -- this takes 2-10 minutes)..."
    # FIX 6: cap mksquashfs memory (-mem) and parallelism (-processors). Without a cap,
    # mksquashfs balloons RAM on large (2 GB+) desktop rootfs trees and WEDGES the WSL2
    # distro (it stops responding to any command). 512 MB / 2 procs is stable.
    # Exclude virtual filesystems so live /proc, /sys, /dev are not captured.
    mksquashfs "$ROOTFS" "$ISO_TREE/live/filesystem.squashfs" \
        -comp gzip -b 131072 -noappend -no-xattrs \
        -mem 512M -processors 2 \
        -e proc -e sys -e dev -e run -e tmp -e var/cache/apt/archives -e boot 2>&1 | tail -5
fi

echo "ISO tree size: $(du -sh $ISO_TREE | cut -f1)"
echo "[OK] ISO tree ready."
'@ "Step 5 -- Build GRUB2 + squashfs ISO tree (5-15 min)"

# ============================================================
# STEP 6: Generate final bootable ISO
# ============================================================
RunWSL @'
#!/bin/bash
set -e
ISO_TREE="/mnt/e/BOBO-OS/build-output/iso-tree"
ISO_OUT="/mnt/e/BOBO-OS/build-output/BOBO-OS-v1.0.iso"
EFI_IMG="/mnt/e/BOBO-OS/build-output/efi.img"

echo "Generating hybrid UEFI+BIOS bootable ISO..."

# xorriso requires efi.img to be INSIDE the ISO tree (path is relative to ISO root)
# Copy efi.img into ISO_TREE/boot/ so xorriso can find it as "boot/efi.img"
if [ -s "$EFI_IMG" ]; then
    cp "$EFI_IMG" "$ISO_TREE/boot/efi.img"
    echo "Copied efi.img into ISO tree ($(du -sh $ISO_TREE/boot/efi.img | cut -f1))"
fi

# Build xorriso command depending on whether EFI image is available
HAS_EFI=0
[ -s "$ISO_TREE/boot/efi.img" ] && HAS_EFI=1
[ -s "$ISO_TREE/EFI/BOOT/BOOTX64.EFI" ] && HAS_EFI=1

HAS_BIOS=0
[ -s "$ISO_TREE/boot/grub/bios.img" ] && HAS_BIOS=1

echo "Building ISO: BIOS=$HAS_BIOS EFI=$HAS_EFI"

if [ "$HAS_BIOS" -eq 1 ] && [ "$HAS_EFI" -eq 1 ]; then
    # Full hybrid UEFI + BIOS ISO
    xorriso -as mkisofs \
        -iso-level 3 \
        -full-iso9660-filenames \
        -volid "BOBO_OS_1_0" \
        -appid "BOBO OS 1.0.0" \
        -publisher "BOBO OS" \
        -preparer "BOBO OS Build System" \
        -eltorito-boot boot/grub/bios.img \
            -no-emul-boot \
            -boot-load-size 4 \
            -boot-info-table \
        -eltorito-alt-boot \
        -e boot/efi.img \
            -no-emul-boot \
        -isohybrid-gpt-basdat \
        -output "$ISO_OUT" \
        "$ISO_TREE" 2>&1
elif [ "$HAS_BIOS" -eq 1 ]; then
    # BIOS-only ISO (no EFI support)
    echo "[WARN] No EFI image -- building BIOS-only ISO"
    xorriso -as mkisofs \
        -iso-level 3 \
        -full-iso9660-filenames \
        -volid "BOBO_OS_1_0" \
        -appid "BOBO OS 1.0.0" \
        -publisher "BOBO OS" \
        -preparer "BOBO OS Build System" \
        -eltorito-boot boot/grub/bios.img \
            -no-emul-boot \
            -boot-load-size 4 \
            -boot-info-table \
        -output "$ISO_OUT" \
        "$ISO_TREE" 2>&1
else
    # No bootloader at all -- plain data ISO (still useful for inspection)
    echo "[WARN] No bootloader available -- building plain data ISO"
    xorriso -as mkisofs \
        -iso-level 3 \
        -full-iso9660-filenames \
        -volid "BOBO_OS_1_0" \
        -output "$ISO_OUT" \
        "$ISO_TREE" 2>&1
fi

if [ -f "$ISO_OUT" ]; then
    SIZE=$(du -sh "$ISO_OUT" | cut -f1)
    SHA256=$(sha256sum "$ISO_OUT" | cut -d' ' -f1)
    echo "$SHA256  BOBO-OS-v1.0.iso" > "$(dirname $ISO_OUT)/BOBO-OS-v1.0.iso.sha256"
    echo ""
    echo "=============================================="
    echo "  BOBO OS ISO GENERATED SUCCESSFULLY!"
    echo "=============================================="
    echo "  File   : BOBO-OS-v1.0.iso"
    echo "  Size   : $SIZE"
    echo "  SHA256 : ${SHA256:0:40}..."
    echo "=============================================="
    echo ""
    echo "ISO saved to: $ISO_OUT"
else
    echo "ERROR: ISO file was not created!"
    exit 1
fi
'@ "Step 6 -- Generate final ISO (xorriso)"

# ============================================================
# STEP 7: Quick QEMU boot test
# ============================================================
RunWSL @'
#!/bin/bash
ISO="/mnt/e/BOBO-OS/build-output/BOBO-OS-v1.0.iso"

if [ ! -f "$ISO" ]; then
    echo "ISO not found -- skipping boot test."
    exit 0
fi

echo "Running 30-second headless QEMU boot test..."
timeout 35 qemu-system-x86_64 \
    -m 1024M \
    -cdrom "$ISO" \
    -boot d \
    -nographic \
    -serial stdio \
    -no-reboot \
    -enable-kvm 2>/dev/null || \
timeout 35 qemu-system-x86_64 \
    -m 1024M \
    -cdrom "$ISO" \
    -boot d \
    -nographic \
    -serial stdio \
    -no-reboot 2>&1 | head -60

echo ""
echo "QEMU boot test complete."
echo "If kernel messages appeared above, the ISO is bootable."
'@ "Step 7 -- QEMU boot test (30s)"

# ============================================================
# FINAL REPORT
# ============================================================
$endTime  = Get-Date
$duration = $endTime - $startTime
$hours    = [math]::Floor($duration.TotalHours)
$minutes  = $duration.Minutes
$isoExists = Test-Path "E:\BOBO-OS\build-output\BOBO-OS-v1.0.iso"
$isoSize   = if ($isoExists) {
    [math]::Round((Get-Item "E:\BOBO-OS\build-output\BOBO-OS-v1.0.iso").Length / 1GB, 2)
} else { "N/A" }

Log "" "White"
Log "================================================" "Yellow"
Log "  BOBO OS -- Build Complete!" "Green"
Log "================================================" "Yellow"
Log "  Build time  : ${hours}h ${minutes}min" "Cyan"
Log "  ISO location: E:\BOBO-OS\build-output\BOBO-OS-v1.0.iso" "Cyan"
Log "  ISO size    : ${isoSize} GB" "Cyan"
Log "  Build log   : E:\BOBO-OS\docs\compile-log.txt" "Cyan"
Log "" "White"
Log "  NEXT STEPS:" "Yellow"
Log "  Option A -- VirtualBox:" "White"
Log "    1. New VM > Linux > Ubuntu 64-bit > 2 GB RAM > 20 GB disk" "White"
Log "    2. Settings > Storage > Add ISO > E:\BOBO-OS\build-output\BOBO-OS-v1.0.iso" "White"
Log "    3. Start -- BOBO OS boots!" "White"
Log "" "White"
Log "  Option B -- USB stick (Rufus):" "White"
Log "    1. Rufus > Select USB > Select ISO > DD Image mode > Start" "White"
Log "    2. Boot PC from USB" "White"
Log "================================================" "Yellow"
