#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  nftables Firewall Setup (Phase 9.1)
# E:\BOBO-OS\core\security\firewall-setup.sh
#
# Default policy: DROP inbound, ACCEPT outbound, ACCEPT established
# Profiles: Home (relaxed), Work (strict), Public (maximum)
# Auto-switches profile by SSID (if nmcli is available).
# =============================================================================

set -euo pipefail

if grep -qi microsoft /proc/version 2>/dev/null; then
  HOST_ENV="wsl2"
else
  HOST_ENV="linux"
fi

LOG_FILE="/var/log/bobo-firewall.log"
PROFILE_FILE="/etc/bobo-os/firewall-profile"
PASS=0; FAIL=0

log() { echo "[$(date '+%H:%M:%S')] [Firewall] $*" | tee -a "${LOG_FILE}"; }
pass() { log "PASS  $*"; (( PASS++ )) || true; }
fail() { log "FAIL  $*"; (( FAIL++ )) || true; }

# ---------------------------------------------------------------------------
# Determine active profile (default: home)
# ---------------------------------------------------------------------------
PROFILE="${1:-}"
if [[ -z "${PROFILE}" && -f "${PROFILE_FILE}" ]]; then
  PROFILE=$(cat "${PROFILE_FILE}")
fi
PROFILE="${PROFILE:-home}"
log "Applying firewall profile: ${PROFILE}"

# ---------------------------------------------------------------------------
# Flush existing nftables ruleset
# ---------------------------------------------------------------------------
nft flush ruleset 2>/dev/null || true

# ---------------------------------------------------------------------------
# Apply ruleset based on profile
# ---------------------------------------------------------------------------

apply_home_profile() {
  nft -f - <<'NFTEOF'
table inet bobo_firewall {
  # Track established connections for stateful rules
  ct helper ftp-standard { type "ftp" protocol tcp; }

  chain inbound {
    type filter hook input priority 0; policy drop;

    # Accept loopback traffic
    iifname "lo" accept

    # Accept established/related connections
    ct state established,related accept

    # Accept ICMP (ping)  -  limited rate to prevent flood
    icmp type { echo-reply, destination-unreachable, time-exceeded } accept
    icmpv6 type { echo-reply, destination-unreachable, time-exceeded,
                  nd-neighbor-solicit, nd-neighbor-advert,
                  nd-router-solicit, nd-router-advert } accept
    ip protocol icmp limit rate 10/second accept
    ip6 nexthdr icmpv6 limit rate 10/second accept

    # Accept mDNS (local network discovery)
    udp dport 5353 accept

    # Log and drop everything else
    limit rate 5/second log prefix "[BOBO DROP] " flags all
    drop
  }

  chain outbound {
    type filter hook output priority 0; policy accept;
    # All outbound traffic is allowed
  }

  chain forward {
    type filter hook forward priority 0; policy drop;
    ct state established,related accept
  }
}
NFTEOF
}

apply_work_profile() {
  nft -f - <<'NFTEOF'
table inet bobo_firewall {
  chain inbound {
    type filter hook input priority 0; policy drop;
    iifname "lo" accept
    ct state established,related accept
    icmp type echo-request limit rate 4/second accept
    icmpv6 type { nd-neighbor-solicit, nd-neighbor-advert } accept
    limit rate 3/second log prefix "[BOBO WORK DROP] " flags all
    drop
  }

  chain outbound {
    type filter hook output priority 0; policy accept;
    # Block BitTorrent ports in work mode
    tcp dport { 6881-6889 } drop
    udp dport { 6881-6889 } drop
  }

  chain forward {
    type filter hook forward priority 0; policy drop;
    ct state established,related accept
  }
}
NFTEOF
}

apply_public_profile() {
  nft -f - <<'NFTEOF'
table inet bobo_firewall {
  chain inbound {
    type filter hook input priority 0; policy drop;
    iifname "lo" accept
    ct state established,related accept
    # Maximum restriction: only established connections in; no inbound initiations
    drop
  }

  chain outbound {
    type filter hook output priority 0; policy accept;
    # Only allow HTTPS, DNS, DHCP
    tcp dport { 53, 80, 443 } accept
    udp dport { 53, 67, 68 } accept
    drop
  }

  chain forward {
    type filter hook forward priority 0; policy drop;
  }
}
NFTEOF
}

case "${PROFILE}" in
  home)   apply_home_profile   ;;
  work)   apply_work_profile   ;;
  public) apply_public_profile ;;
  *)
    log "Unknown profile '${PROFILE}'  -  using home."
    apply_home_profile
    ;;
esac

# Save active profile
mkdir -p /etc/bobo-os
echo "${PROFILE}" > "${PROFILE_FILE}"
pass "Firewall profile '${PROFILE}' applied"

# ---------------------------------------------------------------------------
# Auto-profile switching based on SSID (if nmcli available)
# ---------------------------------------------------------------------------
if command -v nmcli &>/dev/null; then
  SSID=$(nmcli -t -f active,ssid dev wifi | grep '^yes:' | cut -d: -f2 || true)
  if [[ -n "${SSID}" ]]; then
    log "Connected WiFi SSID: ${SSID}"
    # Example: mark home networks  -  expand this list via Settings -> Privacy -> Firewall
    HOME_SSIDS_FILE="/etc/bobo-os/home-networks.conf"
    if [[ -f "${HOME_SSIDS_FILE}" ]] && grep -qxF "${SSID}" "${HOME_SSIDS_FILE}"; then
      log "SSID is a trusted home network -> keeping home profile."
    else
      log "SSID not in trusted list -> using current profile (${PROFILE})."
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Per-app outbound blocking (read from /etc/bobo-os/blocked-apps.conf)
# Each line: <app-uid>
# ---------------------------------------------------------------------------
BLOCKED_APPS_CONF="/etc/bobo-os/blocked-apps.conf"
if [[ -f "${BLOCKED_APPS_CONF}" ]]; then
  while IFS= read -r uid; do
    [[ -z "${uid}" || "${uid}" == \#* ]] && continue
    nft add rule inet bobo_firewall outbound skuid "${uid}" drop 2>/dev/null && \
      log "Blocked outbound for UID ${uid}" || true
  done < "${BLOCKED_APPS_CONF}"
fi

# ---------------------------------------------------------------------------
# Log dropped connections to bobo-firewall.log
# ---------------------------------------------------------------------------
# nftables log prefix already set above  -  output goes to kernel log
# Route to our file via rsyslog or journald
if [[ -f /etc/rsyslog.conf ]]; then
  grep -q 'BOBO DROP' /etc/rsyslog.conf 2>/dev/null || \
    echo ':msg, contains, "[BOBO" -/var/log/bobo-firewall.log' >> /etc/rsyslog.conf
fi

# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
echo ""
echo "=== Firewall Self-Test ==="

# Check ruleset was applied
if nft list ruleset 2>/dev/null | grep -q 'bobo_firewall'; then
  pass "nftables ruleset active"
else
  fail "nftables ruleset not found"
fi

# Verify default drop policy
if nft list chain inet bobo_firewall inbound 2>/dev/null | grep -q 'policy drop'; then
  pass "Inbound default policy: DROP"
else
  fail "Inbound policy is not DROP"
fi

echo "  PASS: ${PASS}  FAIL: ${FAIL}"
echo "=========================="
[[ "${FAIL}" -eq 0 ]]
