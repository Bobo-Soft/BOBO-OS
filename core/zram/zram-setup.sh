#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  zram Compressed Swap Setup (Phase 4.5)
# E:\BOBO-OS\core\zram\zram-setup.sh
#
# Creates a zram block device at 50% of total RAM, configured for
# maximum speed using lz4 compression. Sets priority 100 (preferred
# over disk swap, priority 10).
#
# Called from: runit Stage 1 (before any user services start)
# Safe to re-run: exits cleanly if zram0 is already active.
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

PASS=0
FAIL=0

log() { echo "[zram] $*"; }
pass() { log "PASS  $*"; (( PASS++ )) || true; }
fail() { log "FAIL  $*"; (( FAIL++ )) || true; }

# ---------------------------------------------------------------------------
# Load bobo-os.conf for tunable parameters
# ---------------------------------------------------------------------------
BOBO_CONFIG="/etc/bobo-os.conf"
ZRAM_RATIO=0.5      # Use 50% of RAM for zram
ZRAM_ALGO="lz4"     # lz4: best speed/ratio for desktop swap
[[ -f "${BOBO_CONFIG}" ]] && source "${BOBO_CONFIG}" || true

log "Starting zram setup (ratio=${ZRAM_RATIO}, algo=${ZRAM_ALGO})..."

# ---------------------------------------------------------------------------
# Check if zram is already active  -  idempotent exit
# ---------------------------------------------------------------------------
if swapon --show | grep -q '/dev/zram0'; then
  log "zram0 is already active as swap  -  nothing to do."
  swapon --show
  exit 0
fi

# ---------------------------------------------------------------------------
# Load the zram kernel module
# ---------------------------------------------------------------------------
if ! modprobe zram num_devices=1 2>/dev/null; then
  # zram may already be loaded
  if ! lsmod | grep -q '^zram'; then
    fail "Failed to load zram kernel module."
    echo "  The kernel may not have CONFIG_ZRAM=y/m."
    echo "  Check: grep CONFIG_ZRAM /boot/config-$(uname -r)"
    exit 1
  fi
fi
pass "zram kernel module loaded"

# ---------------------------------------------------------------------------
# Detect total system RAM
# ---------------------------------------------------------------------------
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
TOTAL_RAM_MB=$(( TOTAL_RAM_KB / 1024 ))

# Calculate zram size (integer math  -  no bc required)
# ZRAM_RATIO is a decimal like 0.5; multiply KB by numerator / denominator
# We hardcode common ratios to avoid requiring floating-point bash
case "${ZRAM_RATIO}" in
  0.25) ZRAM_SIZE_KB=$(( TOTAL_RAM_KB / 4 ))  ;;
  0.50|0.5) ZRAM_SIZE_KB=$(( TOTAL_RAM_KB / 2 ))  ;;
  0.75) ZRAM_SIZE_KB=$(( TOTAL_RAM_KB * 3 / 4 )) ;;
  1.0|1)    ZRAM_SIZE_KB="${TOTAL_RAM_KB}" ;;
  *) ZRAM_SIZE_KB=$(( TOTAL_RAM_KB / 2 )) ;;  # Default: 50%
esac

ZRAM_SIZE_MB=$(( ZRAM_SIZE_KB / 1024 ))
log "Total RAM: ${TOTAL_RAM_MB} MB  ->  zram size: ${ZRAM_SIZE_MB} MB"

# ---------------------------------------------------------------------------
# Set compression algorithm on zram0
# ---------------------------------------------------------------------------
ZRAM_COMP_FILE="/sys/block/zram0/comp_algorithm"

if [[ ! -f "${ZRAM_COMP_FILE}" ]]; then
  fail "zram0 device not found at /sys/block/zram0  -  module may not be loaded."
  exit 1
fi

# Verify lz4 is available; fall back to lzo if not
AVAILABLE_ALGOS=$(cat "${ZRAM_COMP_FILE}")
if echo "${AVAILABLE_ALGOS}" | grep -q '\blz4\b'; then
  SELECTED_ALGO="lz4"
elif echo "${AVAILABLE_ALGOS}" | grep -q '\blzo\b'; then
  SELECTED_ALGO="lzo"
  log "lz4 not available  -  using lzo fallback."
elif echo "${AVAILABLE_ALGOS}" | grep -q '\bzstd\b'; then
  SELECTED_ALGO="zstd"
  log "lz4/lzo not available  -  using zstd fallback (slower, better ratio)."
else
  SELECTED_ALGO=$(echo "${AVAILABLE_ALGOS}" | awk '{print $1}')
  log "Using first available algorithm: ${SELECTED_ALGO}"
fi

echo "${SELECTED_ALGO}" > "${ZRAM_COMP_FILE}"
pass "Compression algorithm set to ${SELECTED_ALGO}"

# ---------------------------------------------------------------------------
# Set zram device size
# ---------------------------------------------------------------------------
echo "${ZRAM_SIZE_KB}K" > /sys/block/zram0/disksize
pass "zram0 disk size set to ${ZRAM_SIZE_MB} MB"

# ---------------------------------------------------------------------------
# Format as swap and enable with high priority
# ---------------------------------------------------------------------------
mkswap /dev/zram0 --label bobo-zram0 2>/dev/null
pass "zram0 formatted as swap"

swapon --priority 100 /dev/zram0
pass "zram0 activated (priority 100)"

# ---------------------------------------------------------------------------
# Verify any disk swap exists and set it to lower priority (10)
# ---------------------------------------------------------------------------
for DISK_SWAP in $(swapon --show=NAME --noheadings | grep -v '/dev/zram'); do
  swapoff "${DISK_SWAP}" 2>/dev/null || true
  swapon --priority 10 "${DISK_SWAP}" 2>/dev/null && \
    log "Disk swap ${DISK_SWAP} re-enabled at priority 10." || true
done

# ---------------------------------------------------------------------------
# Tune swappiness  -  lower = kernel prefers RAM, higher = use swap sooner
# 60 is default; 80 is good for zram (fast swap, better memory pressure)
# ---------------------------------------------------------------------------
sysctl -w vm.swappiness=80 >/dev/null 2>&1 && pass "vm.swappiness=80" || true

# Make swappiness persistent
SYSCTL_CONF="/etc/sysctl.d/80-bobo-zram.conf"
cat > "${SYSCTL_CONF}" <<'EOF'
# BOBO OS  -  zram tuning
# Higher swappiness is safe with zram because swapping to compressed RAM
# is much faster than swapping to disk.
vm.swappiness = 80
vm.vfs_cache_pressure = 50
EOF
pass "sysctl zram tuning written to ${SYSCTL_CONF}"

# ---------------------------------------------------------------------------
# Display final status via zramctl
# ---------------------------------------------------------------------------
log ""
log "=== zram status ==="
zramctl 2>/dev/null || cat /proc/swaps
log ""
log "=== Swap table ==="
swapon --show
log "==================="

# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
echo ""
echo "=== zram Self-Test ==="

ZRAM0_ACTIVE=$(swapon --show | grep -c '/dev/zram0' || true)
[[ "${ZRAM0_ACTIVE}" -ge 1 ]] && pass "zram0 is active in swap table" || fail "zram0 NOT found in swap table"

ACTUAL_ALGO=$(cat /sys/block/zram0/comp_algorithm 2>/dev/null | grep -oP '\[\K[^\]]+' || echo "unknown")
[[ "${ACTUAL_ALGO}" == "${SELECTED_ALGO}" ]] && pass "Algorithm: ${ACTUAL_ALGO}" || fail "Algorithm mismatch (expected ${SELECTED_ALGO}, got ${ACTUAL_ALGO})"

ACTUAL_SIZE=$(cat /sys/block/zram0/disksize 2>/dev/null || echo 0)
EXPECTED_SIZE=$(( ZRAM_SIZE_KB * 1024 ))
[[ "${ACTUAL_SIZE}" -eq "${EXPECTED_SIZE}" ]] && pass "Size: ${ZRAM_SIZE_MB} MB" || fail "Size mismatch (${ACTUAL_SIZE} vs ${EXPECTED_SIZE})"

echo "  PASS: ${PASS}  FAIL: ${FAIL}"
echo "====================="
[[ "${FAIL}" -eq 0 ]]
