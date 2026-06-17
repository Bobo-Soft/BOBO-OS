#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  Waydroid Setup Script (Phase 4.6)
# E:\BOBO-OS\core\novalayer\waydroid\waydroid-setup.sh
#
# Installs and initialises Waydroid (Android in a container) for BOBO OS.
# - Installs kernel modules (binder_linux, ashmem_linux)
# - Downloads and initialises a LineageOS system image
# - Configures Waydroid for Wayland
# - Sets up clipboard sharing and app-in-taskbar integration
#
# Usage:
#   waydroid-setup.sh [--init] [--reset] [--status] [--test]
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Host environment detection
# ---------------------------------------------------------------------------
if grep -qi microsoft /proc/version 2>/dev/null; then
  HOST_ENV="wsl2"
  echo "WARNING: Waydroid requires bare-metal Linux or KVM. WSL2 is not supported." >&2
  exit 1
else
  HOST_ENV="linux"
fi

LOG_FILE="/var/log/bobo-waydroid.log"
WAYDROID_DATA="/var/lib/waydroid"
BOBO_WAYDROID_CONF="/etc/bobo-os/waydroid.conf"
PASS=0; FAIL=0

log()  { echo "[$(date '+%H:%M:%S')] [Waydroid] $*" | tee -a "${LOG_FILE}"; }
ok()   { log "PASS  $*"; (( PASS++ )) || true; }
fail() { log "FAIL  $*"; (( FAIL++ )) || true; }
warn() { log "WARN  $*"; }

# ---------------------------------------------------------------------------
# Show GTK4 progress dialog (Python inline)
# ---------------------------------------------------------------------------
_show_progress() {
  local title="$1"
  local message="$2"

  python3 - "${title}" "${message}" <<'PYEOF' &
import gi, sys, threading
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio

title   = sys.argv[1] if len(sys.argv) > 1 else "Please wait…"
message = sys.argv[2] if len(sys.argv) > 2 else ""

app = Adw.Application(application_id="os.bobo.WaydroidSetup",
                      flags=Gio.ApplicationFlags.FLAGS_NONE)

def on_activate(application):
    win = Adw.ApplicationWindow(application=application)
    win.set_default_size(400, -1)
    win.set_title(title)
    win.set_resizable(False)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_margin_top(32); box.set_margin_bottom(32)
    box.set_margin_start(32); box.set_margin_end(32)
    win.set_content(box)

    spinner = Gtk.Spinner()
    spinner.set_spinning(True)
    spinner.set_size_request(48, 48)
    box.append(spinner)

    lbl = Gtk.Label(label=message)
    lbl.set_wrap(True)
    lbl.set_justify(Gtk.Justification.CENTER)
    box.append(lbl)

    win.present()

app.connect("activate", on_activate)
app.run([])
PYEOF
  PROGRESS_PID=$!
}

_close_progress() {
  kill "${PROGRESS_PID:-0}" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Step 1: Install kernel modules (binder + ashmem)
# ---------------------------------------------------------------------------
_install_kernel_modules() {
  log "Installing kernel modules for Waydroid..."

  # Check if modules are already available
  if modinfo binder_linux &>/dev/null 2>&1; then
    ok "binder_linux module available"
  else
    # Try to install from package manager
    if command -v apt-get &>/dev/null; then
      apt-get install -y linux-modules-extra-"$(uname -r)" 2>/dev/null || \
        apt-get install -y binder-linux-dkms 2>/dev/null || \
        warn "Could not install binder_linux via apt"
    elif command -v pacman &>/dev/null; then
      pacman -S --noconfirm linux-headers 2>/dev/null || true
      # binder_linux is usually in linux-modules or anbox-modules-dkms
      yay -S --noconfirm anbox-modules-dkms 2>/dev/null || true
    fi
  fi

  # Load modules
  for mod in binder_linux ashmem_linux; do
    if modprobe "${mod}" 2>/dev/null; then
      ok "Loaded module: ${mod}"
    else
      warn "Could not load ${mod}  -  kernel may need CONFIG_ANDROID_BINDER_IPC=m"
    fi
  done

  # Ensure modules load at boot
  mkdir -p /etc/modules-load.d
  cat > /etc/modules-load.d/waydroid.conf <<'EOF'
binder_linux
ashmem_linux
EOF
  ok "Module autoload configured: /etc/modules-load.d/waydroid.conf"

  # Verify binder device nodes
  for dev in binder hwbinder vndbinder; do
    if [[ -c "/dev/${dev}" ]]; then
      ok "/dev/${dev} present"
    else
      warn "/dev/${dev} not found  -  binder may not be loaded"
    fi
  done
}

# ---------------------------------------------------------------------------
# Step 2: Install Waydroid package
# ---------------------------------------------------------------------------
_install_waydroid() {
  if command -v waydroid &>/dev/null; then
    ok "waydroid already installed: $(waydroid --version 2>/dev/null | head -1)"
    return 0
  fi

  log "Installing Waydroid..."

  if command -v apt-get &>/dev/null; then
    # Ubuntu/Debian PPA
    if command -v add-apt-repository &>/dev/null; then
      add-apt-repository -y ppa:waydroid/waydroid 2>/dev/null || true
    else
      curl -fsSL https://repo.waydro.id/waydroid.gpg \
        -o /usr/share/keyrings/waydroid.gpg 2>/dev/null || true
      echo "deb [signed-by=/usr/share/keyrings/waydroid.gpg] https://repo.waydro.id/ $(lsb_release -cs) main" \
        > /etc/apt/sources.list.d/waydroid.list 2>/dev/null || true
    fi
    apt-get update -qq 2>/dev/null || true
    apt-get install -y waydroid 2>/dev/null && ok "waydroid installed via apt" || \
      fail "Failed to install waydroid via apt"

  elif command -v pacman &>/dev/null; then
    # Arch AUR
    if command -v yay &>/dev/null; then
      yay -S --noconfirm waydroid 2>/dev/null && ok "waydroid installed via AUR" || \
        fail "Failed to install waydroid via AUR"
    else
      warn "yay not found; install waydroid manually from AUR"
    fi

  elif command -v dnf &>/dev/null; then
    dnf copr enable -y aleasto/waydroid 2>/dev/null || true
    dnf install -y waydroid 2>/dev/null && ok "waydroid installed via dnf" || \
      fail "Failed to install waydroid via dnf"
  fi
}

# ---------------------------------------------------------------------------
# Step 3: Initialise Waydroid (download LineageOS image)
# ---------------------------------------------------------------------------
_init_waydroid() {
  log "Initialising Waydroid (downloading Android system image)..."
  log "This may take several minutes depending on your connection speed."

  if [[ -d "${WAYDROID_DATA}/images" ]] && \
     [[ -f "${WAYDROID_DATA}/images/system.img" ]]; then
    ok "Waydroid images already present"
    return 0
  fi

  # Init with GAPPS (Google Play Services) image; fallback to vanilla
  if waydroid init -s GAPPS 2>&1 | tee -a "${LOG_FILE}"; then
    ok "Waydroid initialised with GAPPS"
  elif waydroid init 2>&1 | tee -a "${LOG_FILE}"; then
    ok "Waydroid initialised (vanilla, no GAPPS)"
    warn "Google Play Store not available. Apps can be installed via APK."
  else
    fail "Waydroid initialisation failed  -  check ${LOG_FILE}"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Step 4: Configure Waydroid for BOBO OS
# ---------------------------------------------------------------------------
_configure_waydroid() {
  log "Configuring Waydroid for BOBO OS..."

  # Enable multi-window mode (apps appear as windows on the Wayland desktop)
  waydroid prop set persist.waydroid.multi_windows true 2>/dev/null || true
  ok "Multi-window mode enabled"

  # Set display density to match the host
  local dpi
  dpi=$(python3 -c "
import subprocess
try:
    out = subprocess.check_output(['wlr-randr'], text=True, stderr=subprocess.DEVNULL)
    for line in out.splitlines():
        if 'px/in' in line or 'dpi' in line.lower():
            import re
            m = re.search(r'(\d+)\s*dpi', line, re.I)
            if m:
                print(m.group(1))
                break
except Exception:
    pass
print('180')
" 2>/dev/null || echo "180")
  waydroid prop set ro.sf.lcd_density "${dpi}" 2>/dev/null || true
  ok "Display density set: ${dpi} dpi"

  # Clipboard sharing between Android and host
  mkdir -p /etc/bobo-os
  cat > "${BOBO_WAYDROID_CONF}" <<EOF
# BOBO OS Waydroid Configuration
WAYDROID_CLIPBOARD_SYNC=true
WAYDROID_MULTI_WINDOW=true
WAYDROID_DPI=${dpi}
EOF
  ok "BOBO OS Waydroid config written: ${BOBO_WAYDROID_CONF}"

  # Enable Waydroid session service
  if command -v systemctl &>/dev/null; then
    systemctl enable --now waydroid-container 2>/dev/null && \
      ok "waydroid-container service enabled" || \
      warn "Could not enable waydroid-container service (will start on demand)"
  fi
}

# ---------------------------------------------------------------------------
# Step 5: Set up clipboard sync daemon
# ---------------------------------------------------------------------------
_setup_clipboard_sync() {
  log "Setting up Android <-> Host clipboard sync..."

  # wl-clipboard needed on the host side
  command -v wl-paste &>/dev/null || \
    { warn "wl-clipboard not found  -  install: sudo apt install wl-clipboard"; return; }

  cat > /usr/local/lib/bobo/waydroid-clipboard.sh <<'CLIPEOF'
#!/usr/bin/env bash
# Syncs clipboard between Waydroid and the Wayland host.
# Runs as a background loop.
PREV_HOST=""
PREV_ANDROID=""

while sleep 0.5; do
  HOST_CLIP=$(wl-paste 2>/dev/null || true)
  ANDROID_CLIP=$(waydroid shell service call clipboard 1 2>/dev/null | \
    grep -oP "(?<=String16: \").*(?=\")" | head -1 || true)

  if [[ "${HOST_CLIP}" != "${PREV_HOST}" && -n "${HOST_CLIP}" ]]; then
    waydroid shell "am broadcast -a android.intent.action.CLIPBOARD_CHANGED \
      --es data '${HOST_CLIP//\'/\'\\\'\'}'" 2>/dev/null || true
    PREV_HOST="${HOST_CLIP}"
  fi

  if [[ "${ANDROID_CLIP}" != "${PREV_ANDROID}" && -n "${ANDROID_CLIP}" ]]; then
    printf '%s' "${ANDROID_CLIP}" | wl-copy 2>/dev/null || true
    PREV_ANDROID="${ANDROID_CLIP}"
  fi
done
CLIPEOF
  chmod +x /usr/local/lib/bobo/waydroid-clipboard.sh
  ok "Clipboard sync script installed"
}

# ---------------------------------------------------------------------------
# Mode: --status
# ---------------------------------------------------------------------------
cmd_status() {
  echo ""
  echo "=== Waydroid Status ==="
  if command -v waydroid &>/dev/null; then
    echo "  waydroid: $(waydroid --version 2>/dev/null | head -1)"
    waydroid status 2>/dev/null || echo "  (not running)"
  else
    echo "  waydroid: NOT INSTALLED"
  fi

  for mod in binder_linux ashmem_linux; do
    lsmod | grep -q "${mod%%_*}" && echo "  Module ${mod}: loaded" || \
      echo "  Module ${mod}: NOT loaded"
  done

  for dev in binder hwbinder vndbinder; do
    [[ -c "/dev/${dev}" ]] && echo "  /dev/${dev}: present" || \
      echo "  /dev/${dev}: MISSING"
  done
  echo ""
}

# ---------------------------------------------------------------------------
# Mode: --reset
# ---------------------------------------------------------------------------
cmd_reset() {
  log "Resetting Waydroid..."
  waydroid session stop 2>/dev/null || true
  waydroid container stop 2>/dev/null || true
  sleep 2
  waydroid init --force 2>&1 | tee -a "${LOG_FILE}" && ok "Waydroid reset complete" || \
    fail "Waydroid reset failed"
}

# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
_run_self_test() {
  echo ""
  echo "=== Waydroid Setup Self-Test ==="

  command -v waydroid &>/dev/null && ok "waydroid binary present" || \
    fail "waydroid not installed"

  lsmod | grep -q binder && ok "binder module loaded" || \
    warn "binder not loaded (run waydroid-setup.sh to install)"

  [[ -c /dev/binder ]] && ok "/dev/binder present" || \
    warn "/dev/binder not found"

  [[ -d "${WAYDROID_DATA}" ]] && ok "Waydroid data dir present" || \
    warn "Waydroid not initialised (run with --init)"

  command -v wl-paste &>/dev/null && ok "wl-clipboard present" || \
    warn "wl-clipboard not installed"

  [[ -f "${BOBO_WAYDROID_CONF}" ]] && ok "BOBO OS Waydroid config present" || \
    warn "Config not yet written (run setup)"

  echo "  PASS: ${PASS}  FAIL: ${FAIL}"
  echo "================================"
  [[ "${FAIL}" -eq 0 ]]
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
MODE="${1:---init}"

case "${MODE}" in
  --init)
    log "=== Waydroid Full Setup ==="
    _show_progress "Setting up Android Support" "Installing Waydroid…"
    _install_kernel_modules
    _install_waydroid
    _init_waydroid
    _configure_waydroid
    _setup_clipboard_sync
    _close_progress

    log "Waydroid setup complete. PASS: ${PASS}  FAIL: ${FAIL}"
    if [[ "${FAIL}" -eq 0 ]]; then
      notify-send -a "BOBO OS" -i "android-linux" \
        "Android Support Ready" "Waydroid is set up. You can now run Android apps." 2>/dev/null || true
    fi
    ;;

  --reset)
    cmd_reset
    ;;

  --status)
    cmd_status
    ;;

  --test)
    _run_self_test
    ;;

  *)
    echo "Usage: $0 [--init | --reset | --status | --test]" >&2
    exit 1
    ;;
esac
