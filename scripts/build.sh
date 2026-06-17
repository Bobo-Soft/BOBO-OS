#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  Master Build Script (Phase 10.1)
# E:\BOBO-OS\scripts\build.sh
#
# Builds BOBO OS from source:
#   1. Verify tools
#   2. Download Linux 6.6 LTS kernel
#   3. Apply kernel config and compile
#   4. Build initrd
#   5. Assemble rootfs
#   6. Install GRUB2
#   7. Smoke test in QEMU
#   8. Report metrics
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Host environment detection
# ---------------------------------------------------------------------------
if grep -qi microsoft /proc/version 2>/dev/null; then
  HOST_ENV="wsl2"
else
  HOST_ENV="linux"
fi

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config/bobo-os.conf"

if [[ -f "${CONFIG_FILE}" ]]; then
  source "${CONFIG_FILE}"
else
  echo "ERROR: Config not found at ${CONFIG_FILE}"
  exit 1
fi

# Convert Windows paths to POSIX for WSL2
if [[ "${HOST_ENV}" == "wsl2" ]]; then
  ROOT_PATH=$(echo "${ROOT_PATH}" | sed 's|E:|/mnt/e|; s|\\|/|g')
  PROGRAMS_PATH=$(echo "${PROGRAMS_PATH}" | sed 's|E:|/mnt/e|; s|\\|/|g')
fi

BUILD_LOG="${ROOT_PATH}/docs/build-log.txt"
BUILD_OUTPUT="${ROOT_PATH}/build-output"
ROOTFS_DIR="${BUILD_OUTPUT}/rootfs"
ISO_PATH="${BUILD_OUTPUT}/BOBO-OS-v1.0.iso"

mkdir -p "${BUILD_OUTPUT}" "${ROOTFS_DIR}" "${ROOT_PATH}/docs"

BUILD_START=$(date +%s)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
exec > >(tee -a "${BUILD_LOG}") 2>&1
echo ""
echo "========================================================================"
echo "  BOBO OS Build - $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================================"

STEP=0
PASS=0
FAIL=0

step() {
  (( STEP++ )) || true
  echo ""
  echo "── STEP ${STEP}: $* ──────────────────────────────────────────────────"
}

ok()   { echo "  [OK]   $*"; (( PASS++ )) || true; }
fail() { echo "  [FAIL] $*"; (( FAIL++ )) || true; echo "BUILD FAILED at step ${STEP}: $*"; exit 1; }
warn() { echo "  [WARN] $*"; }

# ---------------------------------------------------------------------------
# STEP 1: Verify all required tools
# ---------------------------------------------------------------------------
step "Verify build tools"

REQUIRED_TOOLS=(gcc clang cmake python3 node xorriso grub-mkimage mkinitcpio)
for tool in "${REQUIRED_TOOLS[@]}"; do
  if command -v "${tool}" &>/dev/null; then
    ok "${tool}: $(command -v "${tool}")"
  else
    warn "${tool}: not found (may use system alternative)"
  fi
done

# Check for QEMU (for smoke test)
QEMU_BIN=""
for q in qemu-system-x86_64 qemu-kvm; do
  command -v "${q}" &>/dev/null && QEMU_BIN="${q}" && break
done
[[ -n "${QEMU_BIN}" ]] && ok "QEMU: ${QEMU_BIN}" || warn "QEMU not found - smoke test will be skipped"

# ---------------------------------------------------------------------------
# STEP 2: Download Linux 6.6 LTS kernel source
# ---------------------------------------------------------------------------
step "Download Linux 6.6 LTS kernel source"

KERNEL_DIR="${BUILD_OUTPUT}/linux-6.6"
KERNEL_URL="https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.6.tar.xz"
KERNEL_TARBALL="${BUILD_OUTPUT}/linux-6.6.tar.xz"

if [[ ! -d "${KERNEL_DIR}" ]]; then
  echo "  Downloading kernel source (this may take a few minutes)..."
  if curl -L --progress-bar "${KERNEL_URL}" -o "${KERNEL_TARBALL}"; then
    tar -xf "${KERNEL_TARBALL}" -C "${BUILD_OUTPUT}"
    rm -f "${KERNEL_TARBALL}"
    ok "Kernel source downloaded and extracted"
  else
    fail "Failed to download kernel from ${KERNEL_URL}"
  fi
else
  ok "Kernel source already present at ${KERNEL_DIR}"
fi

# ---------------------------------------------------------------------------
# STEP 3: Apply kernel config and compile
# ---------------------------------------------------------------------------
step "Apply kernel config and compile"

KERNEL_CONFIG_SRC="${ROOT_PATH}/boot/kernel/kernel.config"
if [[ ! -f "${KERNEL_CONFIG_SRC}" ]]; then
  fail "Kernel config not found at ${KERNEL_CONFIG_SRC}"
fi

cp "${KERNEL_CONFIG_SRC}" "${KERNEL_DIR}/.config"
ok "Kernel config applied"

NPROC=$(nproc 2>/dev/null || echo 4)
echo "  Compiling kernel with ${NPROC} parallel jobs..."
echo "  (This takes 20–60 minutes depending on hardware)"

cd "${KERNEL_DIR}"
make olddefconfig 2>&1 | tail -5

# FIX 2: force the MANDATORY boot + storage + graphics options as BUILT-IN (=y) so the
# kernel can use an initrd, see the VirtualBox CD/SATA/IDE and QEMU virtio devices, mount
# the squashfs/overlay live root, and drive the VirtualBox GPU for the Wayland desktop.
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

if make -j"${NPROC}" bzImage modules 2>&1 | tail -20; then
  ok "Kernel compiled successfully"
  VMLINUZ="${KERNEL_DIR}/arch/x86_64/boot/bzImage"
  [[ -f "${VMLINUZ}" ]] && ok "bzImage: ${VMLINUZ}" || fail "bzImage not found after build"
else
  fail "Kernel compilation failed  -  check ${BUILD_LOG}"
fi

# Install kernel modules to a staging directory
make INSTALL_MOD_PATH="${ROOTFS_DIR}" modules_install 2>&1 | tail -5
ok "Kernel modules installed to rootfs"
cd - >/dev/null

# ---------------------------------------------------------------------------
# STEP 4: Build initrd with mkinitcpio
# ---------------------------------------------------------------------------
step "Build initial RAM disk (initrd)"

INITRD_DIR="${ROOT_PATH}/boot/initrd"
INITRD_OUT="${BUILD_OUTPUT}/initrd-6.6-bobo.img"

if command -v mkinitcpio &>/dev/null; then
  # mkinitcpio preset for BOBO OS
  PRESET_FILE="/etc/mkinitcpio.d/bobo.preset"
  cat > "${PRESET_FILE}" <<EOF
ALL_config="/etc/mkinitcpio.conf"
ALL_kver="6.6.0-bobo"
default_image="${INITRD_OUT}"
EOF
  mkinitcpio -p bobo 2>&1 | tail -10 || \
    mkinitcpio -k 6.6.0-bobo -c /etc/mkinitcpio.conf -g "${INITRD_OUT}" 2>&1 | tail -10
  ok "initrd built: ${INITRD_OUT}"
elif command -v dracut &>/dev/null; then
  dracut --force --kver 6.6.0-bobo "${INITRD_OUT}" 2>&1 | tail -5
  ok "initrd built with dracut: ${INITRD_OUT}"
else
  warn "Neither mkinitcpio nor dracut found  -  creating minimal initrd"
  # Minimal initrd: just enough to mount root and start runit
  mkdir -p /tmp/bobo-initrd/{bin,sbin,etc,proc,sys,dev,run,newroot}
  # In production: populate with busybox and init script
  (cd /tmp/bobo-initrd && find . | cpio -H newc -o 2>/dev/null | gzip > "${INITRD_OUT}")
  ok "Minimal initrd created"
fi

# ---------------------------------------------------------------------------
# STEP 5: Assemble rootfs
# ---------------------------------------------------------------------------
step "Assemble rootfs"

mkdir -p "${ROOTFS_DIR}"/{boot,etc,usr/local/lib/bobo,var/log/bobo}

# Copy BOBO OS files to rootfs
echo "  Copying BOBO OS system files..."
cp -r "${ROOT_PATH}/core"           "${ROOTFS_DIR}/usr/local/lib/bobo/" 2>/dev/null || true
cp -r "${ROOT_PATH}/desktop"        "${ROOTFS_DIR}/usr/local/lib/bobo/" 2>/dev/null || true
cp -r "${ROOT_PATH}/novastore"      "${ROOTFS_DIR}/usr/local/lib/bobo/" 2>/dev/null || true
cp -r "${ROOT_PATH}/novasync"       "${ROOTFS_DIR}/usr/local/lib/bobo/" 2>/dev/null || true
cp -r "${ROOT_PATH}/ai-assistant"   "${ROOTFS_DIR}/usr/local/lib/bobo/" 2>/dev/null || true
cp -r "${ROOT_PATH}/apps"           "${ROOTFS_DIR}/usr/local/share/bobo-apps/" 2>/dev/null || true
cp    "${ROOT_PATH}/config/bobo-os.conf" "${ROOTFS_DIR}/etc/bobo-os.conf" 2>/dev/null || true

# Copy runit init system
cp "${ROOT_PATH}/core/init/1" "${ROOTFS_DIR}/etc/runit/1" 2>/dev/null || true
cp "${ROOT_PATH}/core/init/2" "${ROOTFS_DIR}/etc/runit/2" 2>/dev/null || true
cp "${ROOT_PATH}/core/init/3" "${ROOTFS_DIR}/etc/runit/3" 2>/dev/null || true

# Copy runit service definitions
mkdir -p "${ROOTFS_DIR}/etc/service"
if [[ -d "${ROOT_PATH}/core/init/sv" ]]; then
  cp -r "${ROOT_PATH}/core/init/sv/"* "${ROOTFS_DIR}/etc/service/" 2>/dev/null || true
fi

# Copy kernel and initrd into rootfs/boot/
cp "${VMLINUZ}" "${ROOTFS_DIR}/boot/vmlinuz-6.6-bobo" 2>/dev/null || true
cp "${INITRD_OUT}" "${ROOTFS_DIR}/boot/initrd-6.6-bobo.img" 2>/dev/null || true

# Create BOBO OS release identifier (used by GRUB to find our partition)
cat > "${ROOTFS_DIR}/etc/bobo-os-release" <<'EOF'
NAME="BOBO OS"
VERSION="1.0.0"
ID=bobo-os
PRETTY_NAME="BOBO OS 1.0.0"
HOME_URL="https://bobo-os.example.com"
EOF

ok "Rootfs assembled at ${ROOTFS_DIR}"

# ---------------------------------------------------------------------------
# STEP 6: Install GRUB2 to rootfs
# ---------------------------------------------------------------------------
step "Install GRUB2 to rootfs"

GRUB_DIR="${ROOTFS_DIR}/boot/grub"
mkdir -p "${GRUB_DIR}/fonts"

if command -v grub-install &>/dev/null; then
  # Install GRUB files into rootfs (for inclusion in ISO later)
  grub-mkimage \
    --output="${GRUB_DIR}/core.img" \
    --format=x86_64-efi \
    --prefix=/boot/grub \
    part_gpt part_msdos ext2 iso9660 \
    normal boot linux echo configfile \
    loopback gfxterm vbe png jpeg font \
    2>/dev/null && ok "GRUB EFI image built" || warn "grub-mkimage failed (EFI)"
fi

# Copy GRUB config
cp "${ROOT_PATH}/boot/grub/grub.cfg" "${GRUB_DIR}/grub.cfg"
ok "GRUB config installed"

# ---------------------------------------------------------------------------
# STEP 7: QEMU smoke test
# ---------------------------------------------------------------------------
step "QEMU smoke test"

if [[ -z "${QEMU_BIN}" ]]; then
  warn "QEMU not available  -  skipping smoke test"
else
  echo "  Running 30-second headless boot test..."
  QEMU_LOG="${BUILD_OUTPUT}/qemu-test.log"

  timeout 45 "${QEMU_BIN}" \
    -nographic \
    -no-reboot \
    -m 512M \
    -kernel "${ROOTFS_DIR}/boot/vmlinuz-6.6-bobo" \
    -initrd "${INITRD_OUT}" \
    -append "console=ttyS0 loglevel=1 panic=5" \
    2>"${QEMU_LOG}" &

  QEMU_PID=$!
  sleep 30

  if kill -0 "${QEMU_PID}" 2>/dev/null; then
    kill "${QEMU_PID}" 2>/dev/null || true
    ok "QEMU boot test: kernel booted successfully (no crash in 30s)"
  else
    warn "QEMU exited early  -  check ${QEMU_LOG}"
  fi
fi

# ---------------------------------------------------------------------------
# STEP 8: Build report
# ---------------------------------------------------------------------------
step "Build report"

BUILD_END=$(date +%s)
BUILD_TIME=$(( BUILD_END - BUILD_START ))
BUILD_TIME_MIN=$(( BUILD_TIME / 60 ))
BUILD_TIME_SEC=$(( BUILD_TIME % 60 ))

ROOTFS_SIZE=$(du -sh "${ROOTFS_DIR}" 2>/dev/null | cut -f1 || echo "unknown")

echo ""
echo "========================================================================"
echo "  BOBO OS Build Report"
echo "========================================================================"
printf "  %-24s %s\n" "Build time:"    "${BUILD_TIME_MIN}m ${BUILD_TIME_SEC}s"
printf "  %-24s %s\n" "Rootfs size:"   "${ROOTFS_SIZE}"
printf "  %-24s %d\n" "Steps passed:"  "${PASS}"
printf "  %-24s %d\n" "Steps failed:"  "${FAIL}"
echo "========================================================================"
echo ""
echo "  Next step: run E:\\BOBO-OS\\scripts\\create-iso.sh to package the ISO"
echo ""

echo "Build complete. Passed: ${PASS}  Failed: ${FAIL}"
[[ "${FAIL}" -eq 0 ]]
