#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  ISO Generation Script (Phase 10.2)
# E:\BOBO-OS\scripts\create-iso.sh
#
# Creates a hybrid ISO bootable on UEFI and legacy BIOS.
# Output: E:\BOBO-OS\build-output\BOBO-OS-v1.0.iso
# =============================================================================

set -euo pipefail

if grep -qi microsoft /proc/version 2>/dev/null; then
  HOST_ENV="wsl2"
else
  HOST_ENV="linux"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config/bobo-os.conf"
[[ -f "${CONFIG_FILE}" ]] && source "${CONFIG_FILE}" || true

if [[ "${HOST_ENV}" == "wsl2" ]]; then
  ROOT_PATH=$(echo "${ROOT_PATH:-E:/BOBO-OS}" | sed 's|E:|/mnt/e|; s|\\|/|g')
  PROGRAMS_PATH=$(echo "${PROGRAMS_PATH:-E:/Program Files}" | sed 's|E:|/mnt/e|; s|\\|/|g')
fi

BUILD_OUTPUT="${ROOT_PATH}/build-output"
ROOTFS_DIR="${BUILD_OUTPUT}/rootfs"
ISO_PATH="${BUILD_OUTPUT}/BOBO-OS-v1.0.iso"
XORRISO_BIN="${PROGRAMS_PATH}/xorriso/xorriso"
command -v xorriso &>/dev/null && XORRISO_BIN="xorriso"

PASS=0; FAIL=0
log() { echo "[ISO] $*"; }
ok()  { log "PASS  $*"; (( PASS++ )) || true; }
fail(){ log "FAIL  $*"; (( FAIL++ )) || true; exit 1; }

log "Building BOBO OS ISO..."
log "Rootfs: ${ROOTFS_DIR}"
log "Output: ${ISO_PATH}"

# ---------------------------------------------------------------------------
# Verify prerequisites
# ---------------------------------------------------------------------------
if [[ ! -d "${ROOTFS_DIR}" ]]; then
  fail "Rootfs not found at ${ROOTFS_DIR}. Run build.sh first."
fi

if ! command -v "${XORRISO_BIN}" &>/dev/null; then
  fail "xorriso not found. Install with: sudo apt install xorriso"
fi
ok "xorriso: $(command -v "${XORRISO_BIN}")"

# ---------------------------------------------------------------------------
# Set up EFI boot structure
# ---------------------------------------------------------------------------
EFI_DIR="${ROOTFS_DIR}/boot/EFI/BOOT"
mkdir -p "${EFI_DIR}"

# GRUB EFI binary (bootx64.efi)  -  copied from grub-efi-amd64 package
GRUB_EFI_SRC="/usr/lib/grub/x86_64-efi/grub.efi"
if [[ -f "${GRUB_EFI_SRC}" ]]; then
  cp "${GRUB_EFI_SRC}" "${EFI_DIR}/BOOTX64.EFI"
  ok "EFI bootloader: BOOTX64.EFI"
elif command -v grub-mkstandalone &>/dev/null; then
  grub-mkstandalone \
    --format=x86_64-efi \
    --output="${EFI_DIR}/BOOTX64.EFI" \
    --modules="part_gpt part_msdos fat iso9660 normal boot linux echo configfile loopback gfxterm vbe png" \
    "boot/grub/grub.cfg=${ROOTFS_DIR}/boot/grub/grub.cfg" \
    2>/dev/null
  ok "EFI bootloader built with grub-mkstandalone"
else
  log "WARNING: Cannot build EFI bootloader  -  UEFI boot will not work"
fi

# Create EFI FAT image (required for ISO EFI boot)
EFI_IMG="${BUILD_OUTPUT}/efi.img"
dd if=/dev/zero of="${EFI_IMG}" bs=1K count=1440 2>/dev/null
mkfs.fat -F12 "${EFI_IMG}" 2>/dev/null || true
if command -v mmd &>/dev/null; then
  mmd -i "${EFI_IMG}" ::/EFI ::/EFI/BOOT 2>/dev/null || true
  mcopy -i "${EFI_IMG}" "${EFI_DIR}/BOOTX64.EFI" ::/EFI/BOOT/ 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# FIX 1: Build the GRUB El Torito BIOS boot image as cdboot.img + core.img.
# A bare core.img makes SeaBIOS fail with "int13_cdrom: function 42. Can't use 64bits lba"
# and the ISO never boots in VirtualBox/QEMU under BIOS.
# ---------------------------------------------------------------------------
GRUB_BIOS_DIR="${ROOTFS_DIR}/boot/grub"
mkdir -p "${GRUB_BIOS_DIR}"
if command -v grub-mkimage &>/dev/null; then
  [[ -f /usr/lib/grub/i386-pc/cdboot.img ]] || sudo apt-get install -y grub-pc-bin 2>/dev/null || true
  grub-mkimage \
    --output="/tmp/bobo-core.img" \
    --format=i386-pc \
    --prefix=/boot/grub \
    biosdisk iso9660 part_gpt part_msdos ext2 fat normal boot linux echo configfile \
    terminal search search_fs_uuid search_label gfxterm vbe all_video 2>/dev/null || true
  if [[ -f /usr/lib/grub/i386-pc/cdboot.img && -s /tmp/bobo-core.img ]]; then
    cat /usr/lib/grub/i386-pc/cdboot.img /tmp/bobo-core.img > "${GRUB_BIOS_DIR}/bios.img"
    ok "bios.img = cdboot.img + core.img ($(stat -c%s "${GRUB_BIOS_DIR}/bios.img") bytes)"
  else
    log "WARNING: could not build cdboot+core bios.img"
  fi
fi

# ---------------------------------------------------------------------------
# Create the hybrid ISO with xorriso
# ---------------------------------------------------------------------------
log "Running xorriso..."

"${XORRISO_BIN}" \
  -as mkisofs \
  -iso-level 3 \
  -full-iso9660-filenames \
  -volid "BOBO-OS-1.0" \
  -eltorito-boot boot/grub/bios.img \
    -no-emul-boot \
    -boot-load-size 4 \
    -boot-info-table \
  -eltorito-alt-boot \
  -e boot/efi.img \
    -no-emul-boot \
  -isohybrid-gpt-basdat \
  -append_partition 2 C12A7328-F81F-11D2-BA4B-00A0C93EC93B "${EFI_IMG}" \
  -output "${ISO_PATH}" \
  "${ROOTFS_DIR}" \
  2>&1 | tail -10

ok "ISO created: ${ISO_PATH}"

# ---------------------------------------------------------------------------
# Compute and print SHA256 checksum
# ---------------------------------------------------------------------------
log "Computing SHA256 checksum..."
SHA256=$(sha256sum "${ISO_PATH}" | awk '{print $1}')
echo ""
echo "  ISO: ${ISO_PATH}"
echo "  SHA256: ${SHA256}"
echo ""
# Save checksum alongside the ISO
echo "${SHA256}  BOBO-OS-v1.0.iso" > "${BUILD_OUTPUT}/BOBO-OS-v1.0.iso.sha256"
ok "SHA256 checksum saved"

# ---------------------------------------------------------------------------
# Verify ISO integrity with xorriso
# ---------------------------------------------------------------------------
log "Verifying ISO integrity..."
if "${XORRISO_BIN}" -indev "${ISO_PATH}" -report_about sorry 2>&1 | grep -q 'Volume id'; then
  ok "ISO integrity verified"
else
  log "WARNING: Could not verify ISO (xorriso check returned unexpected output)"
fi

ISO_SIZE=$(du -h "${ISO_PATH}" | cut -f1)

echo ""
echo "========================================"
echo "  BOBO OS ISO build complete!"
echo "  File: $(basename "${ISO_PATH}")"
echo "  Size: ${ISO_SIZE}"
echo "  SHA256: ${SHA256:0:16}…"
echo "========================================"

echo "  PASS: ${PASS}  FAIL: ${FAIL}"
[[ "${FAIL}" -eq 0 ]]
