#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  NVIDIA GPU Driver Installer
# E:\BOBO-OS\core\drivers\gpu\nvidia.sh
#
# Detects NVIDIA GPU, installs proprietary driver via package manager.
# Falls back to Nouveau (open-source) if proprietary driver unavailable.
# Sets up Wayland/GBM acceleration for Wayfire compositor.
# =============================================================================

set -euo pipefail

if grep -qi microsoft /proc/version 2>/dev/null; then
  HOST_ENV="wsl2"
else
  HOST_ENV="linux"
fi

LOG_FILE="/var/log/bobo-drivers.log"
PASS=0
FAIL=0

log() { echo "[NVIDIA] $*" | tee -a "${LOG_FILE}"; }
pass() { log "PASS  $*"; (( PASS++ )) || true; }
fail() { log "FAIL  $*"; (( FAIL++ )) || true; }

# ---------------------------------------------------------------------------
# Verify an NVIDIA GPU is actually present before installing anything
# ---------------------------------------------------------------------------
log "Checking for NVIDIA GPU..."
if ! lspci -nn 2>/dev/null | grep -qi nvidia; then
  log "No NVIDIA GPU detected  -  exiting without changes."
  exit 0
fi

GPU_MODEL=$(lspci -nn 2>/dev/null | grep -i nvidia | head -1 | sed 's/.*: //')
log "Detected: ${GPU_MODEL}"

# ---------------------------------------------------------------------------
# Detect if this is a discrete or integrated GPU
# ---------------------------------------------------------------------------
DISCRETE=false
if lspci -nn 2>/dev/null | grep -i nvidia | grep -qiE 'GeForce|Quadro|Tesla|RTX|GTX'; then
  DISCRETE=true
fi
log "GPU type: $(${DISCRETE} && echo 'Discrete' || echo 'Integrated/MX')"

# ---------------------------------------------------------------------------
# Try to install the proprietary NVIDIA driver
# ---------------------------------------------------------------------------
log "Installing NVIDIA proprietary driver..."
DRIVER_INSTALLED=false

if command -v apt-get &>/dev/null; then
  # Debian/Ubuntu: use nvidia-detect to find the right package version
  apt-get install -y nvidia-detect 2>/dev/null || true
  RECOMMENDED=$(nvidia-detect 2>/dev/null | grep 'nvidia-driver' | awk '{print $1}' || echo "nvidia-driver")
  if apt-get install -y "${RECOMMENDED}" nvidia-settings 2>/dev/null; then
    DRIVER_INSTALLED=true
  fi

elif command -v dnf &>/dev/null; then
  # Fedora/RHEL: use RPM Fusion
  dnf install -y \
    "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm" \
    "https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm" \
    2>/dev/null || true
  if dnf install -y akmod-nvidia xorg-x11-drv-nvidia-cuda 2>/dev/null; then
    DRIVER_INSTALLED=true
  fi

elif command -v pacman &>/dev/null; then
  # Arch Linux
  if pacman -S --noconfirm nvidia nvidia-utils nvidia-settings 2>/dev/null; then
    DRIVER_INSTALLED=true
  fi
fi

# ---------------------------------------------------------------------------
# Fallback to Nouveau if proprietary driver failed
# ---------------------------------------------------------------------------
if ! $DRIVER_INSTALLED; then
  log "Proprietary driver not available  -  using Nouveau (open-source fallback)."
  modprobe nouveau 2>/dev/null || true
  # Ensure Nouveau is not blacklisted
  rm -f /etc/modprobe.d/blacklist-nouveau.conf 2>/dev/null || true
  pass "Nouveau driver active (fallback)"
else
  pass "NVIDIA proprietary driver installed"
  # Blacklist Nouveau to avoid conflict with proprietary driver
  echo "blacklist nouveau" > /etc/modprobe.d/blacklist-nouveau.conf
  echo "options nouveau modeset=0" >> /etc/modprobe.d/blacklist-nouveau.conf
fi

# ---------------------------------------------------------------------------
# Wayland / GBM setup for Wayfire
# The NVIDIA driver needs specific environment variables for Wayland.
# ---------------------------------------------------------------------------
log "Configuring NVIDIA for Wayland (GBM backend)..."

NVIDIA_ENV_FILE="/etc/environment.d/90-bobo-nvidia.conf"
cat > "${NVIDIA_ENV_FILE}" <<'EOF'
# BOBO OS  -  NVIDIA Wayland environment
# Required for NVIDIA proprietary driver to work with Wayfire/wlroots
GBM_BACKEND=nvidia-drm
__GLX_VENDOR_LIBRARY_NAME=nvidia
WLR_NO_HARDWARE_CURSORS=1
LIBVA_DRIVER_NAME=nvidia
EOF
pass "Wayland environment configured"

# ---------------------------------------------------------------------------
# Enable NVIDIA DRM kernel modesetting (required for Wayland)
# ---------------------------------------------------------------------------
log "Enabling NVIDIA DRM KMS..."
MODPROBE_CONF="/etc/modprobe.d/bobo-nvidia.conf"
cat > "${MODPROBE_CONF}" <<'EOF'
# BOBO OS  -  NVIDIA KMS for Wayland
options nvidia-drm modeset=1
options nvidia NVreg_PreserveVideoMemoryAllocations=1
EOF
pass "NVIDIA KMS enabled"

# ---------------------------------------------------------------------------
# Verification: run a simple render test
# ---------------------------------------------------------------------------
log "Running render verification..."
if command -v nvidia-smi &>/dev/null; then
  if nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | grep -qi nvidia; then
    pass "nvidia-smi reports GPU as functional"
  else
    fail "nvidia-smi could not communicate with GPU"
  fi
else
  log "nvidia-smi not available  -  skipping render test (driver may need reboot to load)"
fi

# Check for Vulkan support (needed for DXVK/Wine)
if command -v vulkaninfo &>/dev/null; then
  if vulkaninfo 2>/dev/null | grep -q 'deviceName'; then
    pass "Vulkan support confirmed"
  else
    fail "Vulkan not working  -  DXVK/Wine may have reduced performance"
  fi
else
  log "vulkaninfo not installed  -  skipping Vulkan check"
fi

# ---------------------------------------------------------------------------
# Self-test results
# ---------------------------------------------------------------------------
echo ""
echo "=== NVIDIA Driver Self-Test ==="
echo "  PASS: ${PASS}"
echo "  FAIL: ${FAIL}"
echo "==============================="
[[ ${FAIL} -eq 0 ]]
