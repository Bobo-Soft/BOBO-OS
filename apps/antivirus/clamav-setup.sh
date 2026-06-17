#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  ClamAV Antivirus Setup (apps/antivirus)
# E:\BOBO-OS\apps\antivirus\clamav-setup.sh
#
# Installs and configures ClamAV for BOBO OS:
# - On-access scanning of Downloads, Desktop, /tmp
# - Daily signature updates via freshclam
# - GTK4 scan result notifications via notify-send
# - Right-click "Scan with ClamAV" Nemo action
# =============================================================================

set -euo pipefail

PASS=0; FAIL=0
log()  { echo "[ClamAV] $*"; }
ok()   { log "PASS  $*"; (( PASS++ )) || true; }
fail() { log "FAIL  $*"; (( FAIL++ )) || true; }
warn() { log "WARN  $*"; }

CLAMD_CONF="/etc/clamav/clamd.conf"
FRESHCLAM_CONF="/etc/clamav/freshclam.conf"
NEMO_ACTIONS="${HOME}/.local/share/nemo/actions"
BOBO_SCAN_SCRIPT="/usr/local/lib/bobo/apps/antivirus/scan.sh"

# ---------------------------------------------------------------------------
# Install ClamAV
# ---------------------------------------------------------------------------
if command -v clamscan &>/dev/null; then
  ok "clamav already installed: $(clamscan --version 2>/dev/null | head -1)"
else
  log "Installing ClamAV..."
  if command -v apt-get &>/dev/null; then
    apt-get install -y clamav clamav-daemon clamav-freshclam 2>/dev/null && \
      ok "ClamAV installed via apt" || fail "ClamAV installation failed"
  elif command -v pacman &>/dev/null; then
    pacman -S --noconfirm clamav 2>/dev/null && ok "ClamAV installed via pacman" || \
      fail "ClamAV installation failed"
  elif command -v dnf &>/dev/null; then
    dnf install -y clamav clamd clamav-update 2>/dev/null && ok "ClamAV installed via dnf" || \
      fail "ClamAV installation failed"
  fi
fi

# ---------------------------------------------------------------------------
# Configure clamd.conf (on-access daemon)
# ---------------------------------------------------------------------------
if [[ -f "${CLAMD_CONF}" ]]; then
  # Enable on-access scanning
  sed -i 's/^#\?OnAccessIncludePath.*//' "${CLAMD_CONF}" 2>/dev/null || true
  {
    echo ""
    echo "# BOBO OS on-access scanning"
    echo "OnAccessIncludePath ${HOME}/Downloads"
    echo "OnAccessIncludePath ${HOME}/Desktop"
    echo "OnAccessIncludePath /tmp"
    echo "OnAccessPrevention yes"
    echo "OnAccessExcludeUname clamav"
    echo "MaxThreads 4"
    echo "MaxFileSize 50M"
    echo "MaxScanSize 100M"
  } >> "${CLAMD_CONF}"
  ok "clamd.conf configured"
else
  warn "clamd.conf not found at ${CLAMD_CONF}  -  skipping daemon config"
fi

# ---------------------------------------------------------------------------
# Configure freshclam.conf (signature updates)
# ---------------------------------------------------------------------------
if [[ -f "${FRESHCLAM_CONF}" ]]; then
  # Uncomment UpdateLogFile and set to BOBO OS log path
  sed -i 's|^#\?UpdateLogFile.*|UpdateLogFile /var/log/bobo-clamav-update.log|' \
    "${FRESHCLAM_CONF}" 2>/dev/null || true
  # Daily checks
  sed -i 's/^#\?Checks.*/Checks 1/' "${FRESHCLAM_CONF}" 2>/dev/null || true
  ok "freshclam.conf configured (daily updates)"
fi

# Update signatures now
log "Updating ClamAV signature database..."
if freshclam 2>/dev/null; then
  ok "ClamAV signatures updated"
else
  warn "freshclam update failed (will retry on next boot via service)"
fi

# ---------------------------------------------------------------------------
# Scan script (used by Nemo action and runit service)
# ---------------------------------------------------------------------------
mkdir -p "$(dirname "${BOBO_SCAN_SCRIPT}")"
cat > "${BOBO_SCAN_SCRIPT}" <<'SCANEOF'
#!/usr/bin/env bash
# BOBO OS  -  ClamAV scan wrapper
# Usage: scan.sh [path...]  Default: ~/Downloads ~/Desktop
set -euo pipefail

SCAN_PATHS=("${@:-${HOME}/Downloads ${HOME}/Desktop}")
LOG_FILE="/var/log/bobo-clamav-scan.log"
THREATS_FOUND=0

notify() {
  notify-send -a "BOBO OS Antivirus" -i "security-high" "$@" 2>/dev/null || true
}

notify "Scanning for threats…" "ClamAV is checking your files."

for path in "${SCAN_PATHS[@]}"; do
  [[ -e "${path}" ]] || continue
  result=$(clamscan --recursive --infected --no-summary "${path}" 2>/dev/null || true)
  if [[ -n "${result}" ]]; then
    echo "${result}" >> "${LOG_FILE}"
    THREATS_FOUND=$(( THREATS_FOUND + $(echo "${result}" | wc -l) ))
    notify -u critical "Threat detected!" \
      "$(echo "${result}" | head -5 | tr '\n' ' ')"
  fi
done

if [[ "${THREATS_FOUND}" -eq 0 ]]; then
  notify "Scan complete" "No threats found."
else
  notify -u critical "Scan complete" \
    "${THREATS_FOUND} threat(s) found. Check /var/log/bobo-clamav-scan.log"
fi
SCANEOF
chmod +x "${BOBO_SCAN_SCRIPT}"
ok "Scan script: ${BOBO_SCAN_SCRIPT}"

# ---------------------------------------------------------------------------
# Nemo right-click action
# ---------------------------------------------------------------------------
mkdir -p "${NEMO_ACTIONS}"
cat > "${NEMO_ACTIONS}/clamav-scan.nemo_action" <<EOF
[Nemo Action]
Active=true
Name=Scan with ClamAV
Comment=Scan this file or folder for viruses
Exec=${BOBO_SCAN_SCRIPT} %F
Icon-Name=security-high-symbolic
Selection=any
Extensions=any;
Quote=double
EOF
ok "Nemo ClamAV action installed"

# ---------------------------------------------------------------------------
# Daily cron / systemd timer for freshclam
# ---------------------------------------------------------------------------
if command -v systemctl &>/dev/null; then
  systemctl enable --now clamav-freshclam 2>/dev/null && \
    ok "clamav-freshclam service enabled" || \
    warn "clamav-freshclam service not available (using cron fallback)"
fi

# Cron fallback: daily at 3am
CRON_LINE="0 3 * * * ${BOBO_SCAN_SCRIPT} > /dev/null 2>&1"
( crontab -l 2>/dev/null | grep -v 'bobo.*scan\|clamav.*scan'; echo "${CRON_LINE}" ) | \
  crontab - 2>/dev/null && ok "Daily scan cron job installed" || \
  warn "Could not install cron job"

# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
echo ""
echo "=== ClamAV Setup Self-Test ==="
command -v clamscan &>/dev/null && ok "clamscan present" || fail "clamscan not found"
command -v clamd    &>/dev/null && ok "clamd present" || warn "clamd not found"
command -v freshclam &>/dev/null && ok "freshclam present" || fail "freshclam not found"
[[ -f "${BOBO_SCAN_SCRIPT}" ]] && ok "scan.sh present" || fail "scan.sh missing"
[[ -f "${NEMO_ACTIONS}/clamav-scan.nemo_action" ]] && ok "Nemo action installed" || \
  warn "Nemo action not installed"
# Test scan of /dev/null (always clean)
clamscan /dev/null &>/dev/null && ok "clamscan basic execution works" || \
  fail "clamscan failed basic test"
echo "  PASS: ${PASS}  FAIL: ${FAIL}"
echo "=============================="
[[ "${FAIL}" -eq 0 ]]
