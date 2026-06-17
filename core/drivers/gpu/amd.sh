#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  AMD GPU Driver Installer
# E:\BOBO-OS\core\drivers\gpu\amd.sh
#
# Installs AMDGPU open-source driver + optional ROCm for GPU compute.
# AMD GPUs work out-of-the-box on Linux with amdgpu kernel module,
# but we ensure firmware, Mesa, and VA-API are all properly configured.
# =============================================================================

set -euo pipefail

LOG_FILE="/var/log/bobo-drivers.log"
PASS=0
FAIL=0

log() { echo "[AMD]  $*" | tee -a "${LOG_FILE}"; }
pass() { log "PASS  $*"; (( PASS++ )) || true; }
fail() { log "FAIL  $*"; (( FAIL++ )) || true; }

# ---------------------------------------------------------------------------
# Verify AMD GPU is present
# ---------------------------------------------------------------------------
log "Checking for AMD/ATI GPU..."
if ! lspci -nn 2>/dev/null | grep -qiE 'amd|ati|radeon'; then
  log "No AMD GPU detected  -  exiting without changes."
  exit 0
fi

GPU_MODEL=$(lspci -nn 2>/dev/null | grep -iE 'amd|ati|radeon' | grep -iE 'vga|3d|display' | head -1 | sed 's/.*: //')
log "Detected: ${GPU_MODEL}"

# Distinguish discrete from integrated (APU)
INTEGRATED=false
if lspci -nn 2>/dev/null | grep -iE 'amd.*vga' | grep -qi 'integrated\|renoir\|cezanne\|raphael\|phoenix\|vangogh'; then
  INTEGRATED=true
fi
log "GPU type: $(${INTEGRATED} && echo 'Integrated (APU)' || echo 'Discrete')"

# ---------------------------------------------------------------------------
# Install AMD GPU firmware (critical for newer GPUs: RDNA2, RDNA3)
# ---------------------------------------------------------------------------
log "Installing AMD GPU firmware..."
if command -v apt-get &>/dev/null; then
  if apt-get install -y firmware-amd-graphics 2>/dev/null; then
    pass "AMD firmware installed"
  else
    fail "AMD firmware package not found  -  GPU may have reduced functionality"
  fi

elif command -v dnf &>/dev/null; then
  dnf install -y linux-firmware 2>/dev/null && pass "AMD firmware (linux-firmware)" || fail "firmware install failed"

elif command -v pacman &>/dev/null; then
  pacman -S --noconfirm linux-firmware 2>/dev/null && pass "AMD firmware" || fail "firmware install failed"
fi

# ---------------------------------------------------------------------------
# Install Mesa (OpenGL/Vulkan for AMDGPU)
# ---------------------------------------------------------------------------
log "Installing Mesa (OpenGL/Vulkan)..."
if command -v apt-get &>/dev/null; then
  apt-get install -y \
    mesa-vulkan-drivers \
    libvulkan1 \
    vulkan-tools \
    mesa-utils \
    libgl1-mesa-dri \
    xserver-xorg-video-amdgpu \
    2>/dev/null && pass "Mesa + Vulkan installed" || fail "Mesa install failed"

elif command -v dnf &>/dev/null; then
  dnf install -y mesa-vulkan-drivers mesa-dri-drivers vulkan-tools 2>/dev/null \
    && pass "Mesa + Vulkan installed" || fail "Mesa install failed"

elif command -v pacman &>/dev/null; then
  pacman -S --noconfirm mesa vulkan-radeon libva-mesa-driver mesa-vdpau 2>/dev/null \
    && pass "Mesa + Vulkan installed" || fail "Mesa install failed"
fi

# ---------------------------------------------------------------------------
# VA-API hardware video decode (for Firefox, VLC, etc.)
# ---------------------------------------------------------------------------
log "Installing VA-API support..."
if command -v apt-get &>/dev/null; then
  apt-get install -y mesa-va-drivers vainfo 2>/dev/null && pass "VA-API installed" || fail "VA-API install failed"
elif command -v pacman &>/dev/null; then
  pacman -S --noconfirm libva-mesa-driver 2>/dev/null && pass "VA-API installed" || fail "VA-API install failed"
fi

# ---------------------------------------------------------------------------
# Enable amdgpu kernel module + KMS (should already be on, but be explicit)
# ---------------------------------------------------------------------------
log "Ensuring amdgpu KMS is enabled..."
MODPROBE_CONF="/etc/modprobe.d/bobo-amdgpu.conf"
cat > "${MODPROBE_CONF}" <<'EOF'
# BOBO OS  -  AMDGPU configuration
# ppfeaturemask: enable overdrive for advanced power management (optional)
options amdgpu ppfeaturemask=0xffffffff
options amdgpu dpm=1
options amdgpu si_support=1
options amdgpu cik_support=1
EOF
pass "amdgpu KMS options set"

# Wayland-specific environment
AMDGPU_ENV_FILE="/etc/environment.d/90-bobo-amdgpu.conf"
cat > "${AMDGPU_ENV_FILE}" <<'EOF'
# BOBO OS  -  AMDGPU Wayland environment
LIBVA_DRIVER_NAME=radeonsi
MESA_LOADER_DRIVER_OVERRIDE=radeonsi
VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.x86_64.json
EOF
pass "Wayland environment configured"

# ---------------------------------------------------------------------------
# Optional: ROCm for GPU compute (AI, video encoding, etc.)
# Only install on discrete GPUs with >= 4 GB VRAM
# ---------------------------------------------------------------------------
VRAM_MB=0
if command -v rocm-smi &>/dev/null; then
  VRAM_MB=$(rocm-smi --showmeminfo vram 2>/dev/null | grep 'Total Memory' | awk '{print $NF}' || echo 0)
fi

if ! ${INTEGRATED} && (( VRAM_MB > 4000 || VRAM_MB == 0 )); then
  log "Attempting ROCm install for GPU compute support..."
  if command -v apt-get &>/dev/null; then
    curl -s https://repo.radeon.com/amdgpu-install/latest/ubuntu/focal/amdgpu-install \
      -o /tmp/amdgpu-install 2>/dev/null && \
    bash /tmp/amdgpu-install --usecase=rocm --no-dkms 2>/dev/null && \
    pass "ROCm installed" || log "ROCm not available on this system (optional feature)"
  fi
else
  log "Skipping ROCm (integrated GPU or low VRAM)."
fi

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
log "Running render verification..."
if command -v glxinfo &>/dev/null; then
  RENDERER=$(DISPLAY=:0 glxinfo 2>/dev/null | grep 'OpenGL renderer' | head -1 || true)
  if echo "${RENDERER}" | grep -qi 'amd\|radeon\|llvm'; then
    pass "OpenGL renderer: ${RENDERER}"
  else
    log "glxinfo: ${RENDERER} (may need reboot to load new firmware)"
  fi
fi

if command -v vulkaninfo &>/dev/null; then
  if vulkaninfo 2>/dev/null | grep -qi 'radv\|amd'; then
    pass "Vulkan AMD driver (RADV) confirmed"
  else
    log "Vulkan check inconclusive  -  may need reboot"
  fi
fi

if command -v vainfo &>/dev/null; then
  if vainfo 2>/dev/null | grep -qi 'radeonsi\|AMD'; then
    pass "VA-API hardware decode confirmed"
  else
    log "VA-API: could not verify (may need reboot)"
  fi
fi

# ---------------------------------------------------------------------------
# Self-test summary
# ---------------------------------------------------------------------------
echo ""
echo "=== AMD Driver Self-Test ==="
echo "  PASS: ${PASS}"
echo "  FAIL: ${FAIL}"
echo "============================"
[[ ${FAIL} -eq 0 ]]
