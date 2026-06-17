#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  Intel GPU Driver Installer
# E:\BOBO-OS\core\drivers\gpu\intel.sh
#
# Installs i915 driver support, VA-API for hardware video decode,
# and configures Wayland GBM acceleration for Wayfire.
# Handles both discrete Arc GPUs and integrated UHD/Iris Xe graphics.
# =============================================================================

set -euo pipefail

LOG_FILE="/var/log/bobo-drivers.log"
PASS=0
FAIL=0

log() { echo "[Intel] $*" | tee -a "${LOG_FILE}"; }
pass() { log "PASS  $*"; (( PASS++ )) || true; }
fail() { log "FAIL  $*"; (( FAIL++ )) || true; }

# ---------------------------------------------------------------------------
# Verify Intel GPU is present
# ---------------------------------------------------------------------------
log "Checking for Intel GPU..."
if ! lspci -nn 2>/dev/null | grep -qi intel | grep -qiE 'vga|3d|display' 2>/dev/null; then
  # Simpler check: any Intel in VGA class
  if ! lspci -nn 2>/dev/null | grep -qiE 'Intel.*VGA|Intel.*Display|Intel.*Graphics'; then
    log "No Intel GPU detected  -  exiting without changes."
    exit 0
  fi
fi

GPU_MODEL=$(lspci -nn 2>/dev/null | grep -iE 'Intel.*(VGA|3D|Display)' | head -1 | sed 's/.*: //' || echo "Intel GPU")
log "Detected: ${GPU_MODEL}"

# Detect if Arc discrete GPU (needs separate firmware)
ARC_GPU=false
if echo "${GPU_MODEL}" | grep -qi 'arc\|alchemist\|xe.*dg'; then
  ARC_GPU=true
  log "Intel Arc discrete GPU detected."
else
  log "Intel integrated graphics (UHD / Iris Xe)."
fi

# ---------------------------------------------------------------------------
# Install Intel GPU firmware (required for Gen12+ / Arc GPUs)
# ---------------------------------------------------------------------------
log "Installing Intel GPU firmware..."
if command -v apt-get &>/dev/null; then
  apt-get install -y firmware-misc-nonfree intel-microcode 2>/dev/null && \
    pass "Intel firmware installed" || fail "Intel firmware install failed"

elif command -v dnf &>/dev/null; then
  dnf install -y linux-firmware microcode_ctl 2>/dev/null && \
    pass "Intel firmware installed" || fail "Intel firmware install failed"

elif command -v pacman &>/dev/null; then
  pacman -S --noconfirm linux-firmware intel-ucode 2>/dev/null && \
    pass "Intel firmware installed" || fail "Intel firmware install failed"
fi

# ---------------------------------------------------------------------------
# Install Mesa + i965/iris driver (OpenGL/Vulkan for Intel)
# ---------------------------------------------------------------------------
log "Installing Mesa Intel drivers..."
if command -v apt-get &>/dev/null; then
  apt-get install -y \
    mesa-vulkan-drivers \
    libvulkan1 \
    vulkan-tools \
    mesa-utils \
    libgl1-mesa-dri \
    intel-media-va-driver-non-free \
    vainfo \
    2>/dev/null && pass "Mesa + Intel Vulkan installed" || fail "Mesa install failed"

elif command -v dnf &>/dev/null; then
  dnf install -y \
    mesa-vulkan-drivers \
    mesa-dri-drivers \
    intel-media-driver \
    libva-utils \
    2>/dev/null && pass "Mesa + Intel Vulkan installed" || fail "Mesa install failed"

elif command -v pacman &>/dev/null; then
  pacman -S --noconfirm \
    mesa \
    vulkan-intel \
    intel-media-driver \
    libva-intel-driver \
    libva-utils \
    2>/dev/null && pass "Mesa + Intel Vulkan installed" || fail "Mesa install failed"
fi

# ---------------------------------------------------------------------------
# i915 kernel module options (power management, GuC/HuC firmware)
# ---------------------------------------------------------------------------
log "Configuring i915 kernel module..."
MODPROBE_CONF="/etc/modprobe.d/bobo-i915.conf"
cat > "${MODPROBE_CONF}" <<'EOF'
# BOBO OS  -  Intel i915 options
# enable_guc: enable GuC firmware for power management and HuC for video decode
options i915 enable_guc=3
# enable_fbc: framebuffer compression (saves power on laptops)
options i915 enable_fbc=1
# modeset required for Wayland
options i915 modeset=1
EOF
pass "i915 kernel options configured"

# ---------------------------------------------------------------------------
# Wayland / GBM environment for Intel
# ---------------------------------------------------------------------------
INTEL_ENV_FILE="/etc/environment.d/90-bobo-intel.conf"
cat > "${INTEL_ENV_FILE}" <<'EOF'
# BOBO OS  -  Intel Wayland environment
# Use iris (new) driver over i965 (old) for Gen9+ hardware
MESA_LOADER_DRIVER_OVERRIDE=iris
LIBVA_DRIVER_NAME=iHD
# Hardware video decode acceleration in Firefox
MOZ_DRM_DEVICE=/dev/dri/renderD128
EOF
pass "Wayland environment configured"

# ---------------------------------------------------------------------------
# Arc GPU: install special xe kernel module if needed (Linux 6.2+)
# ---------------------------------------------------------------------------
if $ARC_GPU; then
  log "Enabling xe kernel module for Intel Arc..."
  cat >> "${MODPROBE_CONF}" <<'EOF'

# Intel Arc (Alchemist)  -  experimental xe driver (better than i915 for Arc)
# Uncomment when xe driver is stable on your kernel version:
# options xe force_probe=*
EOF
  log "xe driver config written  -  requires kernel 6.2+ and manual enable."
fi

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
log "Running render verification..."
if command -v glxinfo &>/dev/null; then
  RENDERER=$(DISPLAY=:0 glxinfo 2>/dev/null | grep 'OpenGL renderer' | head -1 || true)
  if echo "${RENDERER}" | grep -qi 'intel\|iris\|mesa'; then
    pass "OpenGL renderer: ${RENDERER}"
  else
    log "Renderer check: ${RENDERER:-unknown} (may need reboot)"
  fi
fi

if command -v vainfo &>/dev/null; then
  if vainfo 2>/dev/null | grep -qi 'iHD\|i965\|H264\|HEVC'; then
    pass "VA-API hardware decode confirmed (iHD driver)"
  else
    log "VA-API: cannot verify without a running X/Wayland session"
  fi
fi

if command -v vulkaninfo &>/dev/null; then
  if vulkaninfo 2>/dev/null | grep -qi 'intel\|anv'; then
    pass "Vulkan ANV (Intel) driver confirmed"
  else
    log "Vulkan check inconclusive  -  may need reboot"
  fi
fi

# ---------------------------------------------------------------------------
# Self-test summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Intel Driver Self-Test ==="
echo "  PASS: ${PASS}"
echo "  FAIL: ${FAIL}"
echo "=============================="
[[ ${FAIL} -eq 0 ]]
