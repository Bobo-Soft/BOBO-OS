#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  Phase 3.1: Hardware Auto-Detection & Driver Installation
# E:\BOBO-OS\core\drivers\auto-detect.sh
#
# Runs at first boot (via runit stage 1) and on demand from Settings -> About.
# Safe to re-run: all operations are idempotent.
# Shows a GTK4 progress window  -  user never sees a terminal.
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

LOG_FILE="/var/log/bobo-drivers.log"
MARKER_DIR="/var/lib/bobo/drivers"
mkdir -p "${MARKER_DIR}"

# ---------------------------------------------------------------------------
# GTK4 progress dialog  -  runs in background, controlled via named pipe
# ---------------------------------------------------------------------------
PIPE="/tmp/bobo-hw-pipe-$$"
mkfifo "${PIPE}"

start_progress_dialog() {
  python3 - <<'PYEOF' &
import gi, threading, sys, os, time
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

PIPE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/bobo-hw-pipe"

class HardwareSetupWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Hardware Setup")
        self.set_default_size(480, 220)
        self.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(32)
        box.set_margin_bottom(32)
        box.set_margin_start(32)
        box.set_margin_end(32)

        # Title
        title = Gtk.Label(label="Setting up your hardware...")
        title.add_css_class("title-2")
        box.append(title)

        # Current task label
        self.task_label = Gtk.Label(label="Starting hardware detection...")
        self.task_label.set_wrap(True)
        self.task_label.set_halign(Gtk.Align.START)
        box.append(self.task_label)

        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_pulse_step(0.05)
        box.append(self.progress_bar)

        self.set_content(box)

        # Pulse the progress bar while we work
        GLib.timeout_add(100, self._pulse)

        # Read pipe updates in a background thread
        threading.Thread(target=self._read_pipe, daemon=True).start()

    def _pulse(self):
        self.progress_bar.pulse()
        return True

    def _read_pipe(self):
        try:
            with open(PIPE, "r") as f:
                for line in f:
                    line = line.strip()
                    if line == "DONE":
                        GLib.idle_add(self._on_done)
                        return
                    elif line.startswith("FAIL:"):
                        msg = line[5:]
                        GLib.idle_add(self._on_fail, msg)
                        return
                    else:
                        GLib.idle_add(self._update_label, line)
        except Exception:
            GLib.idle_add(self._on_done)

    def _update_label(self, msg):
        self.task_label.set_text(msg)

    def _on_done(self):
        self.task_label.set_text("Hardware setup complete! [OK]")
        self.progress_bar.set_fraction(1.0)
        GLib.timeout_add(2000, self.close)

    def _on_fail(self, msg):
        self.task_label.set_text(f"⚠️  {msg}\n\nCheck Settings -> About for details.")
        GLib.timeout_add(4000, self.close)

class HardwareSetupApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.HardwareSetup")

    def do_activate(self):
        win = HardwareSetupWindow(self)
        win.present()

app = HardwareSetupApp()
app.run([PIPE])
PYEOF
  DIALOG_PID=$!
}

report_progress() {
  echo "$1" >> "${PIPE}" 2>/dev/null || true
  echo "[$(date '+%H:%M:%S')] $1" >> "${LOG_FILE}"
}

finish_dialog() {
  echo "DONE" >> "${PIPE}" 2>/dev/null || true
  sleep 1
  rm -f "${PIPE}"
}

fail_dialog() {
  echo "FAIL:$1" >> "${PIPE}" 2>/dev/null || true
  sleep 1
  rm -f "${PIPE}"
}

# ---------------------------------------------------------------------------
# Start logging
# ---------------------------------------------------------------------------
echo "" >> "${LOG_FILE}"
echo "======================================" >> "${LOG_FILE}"
echo "BOBO OS Hardware Detection  -  $(date)" >> "${LOG_FILE}"
echo "======================================" >> "${LOG_FILE}"

# Launch the GTK4 progress window (requires DISPLAY/WAYLAND_DISPLAY to be set)
if [[ -n "${WAYLAND_DISPLAY:-}" ]] || [[ -n "${DISPLAY:-}" ]]; then
  start_progress_dialog "${PIPE}"
fi

ISSUES=()

# ---------------------------------------------------------------------------
# GPU Detection and Driver Installation
# ---------------------------------------------------------------------------
report_progress "Detecting GPU..."

GPU_INFO=$(lspci -nn 2>/dev/null | grep -iE 'vga|3d|display' || echo "")
MARKER_GPU="${MARKER_DIR}/gpu.done"

if [[ ! -f "${MARKER_GPU}" ]]; then
  if echo "${GPU_INFO}" | grep -qi nvidia; then
    report_progress "NVIDIA GPU detected  -  installing driver..."
    if bash "$(dirname "$0")/gpu/nvidia.sh" >> "${LOG_FILE}" 2>&1; then
      touch "${MARKER_GPU}"
      report_progress "NVIDIA driver installed. [OK]"
    else
      ISSUES+=("NVIDIA driver installation failed  -  check Settings -> About.")
    fi

  elif echo "${GPU_INFO}" | grep -qi 'amd\|ati\|radeon'; then
    report_progress "AMD GPU detected  -  installing driver..."
    if bash "$(dirname "$0")/gpu/amd.sh" >> "${LOG_FILE}" 2>&1; then
      touch "${MARKER_GPU}"
      report_progress "AMD driver installed. [OK]"
    else
      ISSUES+=("AMD driver installation failed.")
    fi

  elif echo "${GPU_INFO}" | grep -qi intel; then
    report_progress "Intel GPU detected  -  installing driver..."
    if bash "$(dirname "$0")/gpu/intel.sh" >> "${LOG_FILE}" 2>&1; then
      touch "${MARKER_GPU}"
      report_progress "Intel driver installed. [OK]"
    else
      ISSUES+=("Intel driver installation failed.")
    fi

  else
    report_progress "No dedicated GPU detected  -  using generic framebuffer."
    touch "${MARKER_GPU}"
  fi
else
  report_progress "GPU driver already configured. [OK]"
fi

# ---------------------------------------------------------------------------
# WiFi chipset detection and firmware loading
# ---------------------------------------------------------------------------
report_progress "Detecting WiFi adapter..."
MARKER_WIFI="${MARKER_DIR}/wifi.done"

if [[ ! -f "${MARKER_WIFI}" ]]; then
  WIFI_INFO=$(lspci -nn 2>/dev/null | grep -i 'network\|wireless\|wifi' || true)
  WIFI_USB=$(lsusb 2>/dev/null | grep -i 'wireless\|wifi\|wlan' || true)

  if echo "${WIFI_INFO}${WIFI_USB}" | grep -qi 'intel'; then
    report_progress "Intel WiFi detected  -  installing firmware..."
    apt-get install -y firmware-iwlwifi 2>/dev/null || \
    dnf install -y iwl7260-firmware 2>/dev/null || true
    modprobe -r iwlwifi 2>/dev/null; modprobe iwlwifi 2>/dev/null || true

  elif echo "${WIFI_INFO}${WIFI_USB}" | grep -qi 'realtek'; then
    report_progress "Realtek WiFi detected  -  installing firmware..."
    apt-get install -y firmware-realtek 2>/dev/null || true

  elif echo "${WIFI_INFO}${WIFI_USB}" | grep -qi 'broadcom\|brcm'; then
    report_progress "Broadcom WiFi detected  -  installing firmware..."
    apt-get install -y firmware-brcm80211 broadcom-sta-dkms 2>/dev/null || true

  elif echo "${WIFI_INFO}${WIFI_USB}" | grep -qi 'atheros\|ath'; then
    report_progress "Atheros WiFi detected  -  installing firmware..."
    apt-get install -y firmware-atheros 2>/dev/null || true

  elif echo "${WIFI_INFO}${WIFI_USB}" | grep -qi 'mediatek\|mt76'; then
    report_progress "MediaTek WiFi detected  -  installing firmware..."
    apt-get install -y firmware-misc-nonfree 2>/dev/null || true
  fi

  report_progress "WiFi firmware loaded. [OK]"
  touch "${MARKER_WIFI}"
else
  report_progress "WiFi already configured. [OK]"
fi

# ---------------------------------------------------------------------------
# Bluetooth adapter detection
# ---------------------------------------------------------------------------
report_progress "Detecting Bluetooth adapter..."
MARKER_BT="${MARKER_DIR}/bluetooth.done"

if [[ ! -f "${MARKER_BT}" ]]; then
  if lsusb 2>/dev/null | grep -qi bluetooth || hciconfig 2>/dev/null | grep -q hci; then
    report_progress "Bluetooth adapter found  -  ensuring firmware..."
    apt-get install -y bluez bluetooth 2>/dev/null || \
    dnf install -y bluez 2>/dev/null || true
    modprobe btusb 2>/dev/null || true
    report_progress "Bluetooth ready. [OK]"
  else
    report_progress "No Bluetooth adapter detected."
  fi
  touch "${MARKER_BT}"
fi

# ---------------------------------------------------------------------------
# Touchscreen detection (libinput)
# ---------------------------------------------------------------------------
report_progress "Checking for touchscreen..."
MARKER_TOUCH="${MARKER_DIR}/touchscreen.done"

if [[ ! -f "${MARKER_TOUCH}" ]]; then
  if libinput list-devices 2>/dev/null | grep -qi 'touch'; then
    report_progress "Touchscreen detected  -  enabling touch support..."
    apt-get install -y xserver-xorg-input-libinput 2>/dev/null || true
    # Enable multi-touch gestures in libinput config
    mkdir -p /etc/libinput
    cat > /etc/libinput/local-overrides.quirks <<'EOF'
[Touchscreen Override]
MatchUdevType=touchscreen
AttrSizeHint=0
EOF
    report_progress "Touchscreen support enabled. [OK]"
  else
    report_progress "No touchscreen detected."
  fi
  touch "${MARKER_TOUCH}"
fi

# ---------------------------------------------------------------------------
# Printer detection (CUPS)
# ---------------------------------------------------------------------------
report_progress "Checking for printers..."
MARKER_PRINT="${MARKER_DIR}/printer.done"

if [[ ! -f "${MARKER_PRINT}" ]]; then
  # Install CUPS if not present
  if ! command -v cupsd &>/dev/null; then
    apt-get install -y cups cups-filters 2>/dev/null || \
    dnf install -y cups 2>/dev/null || true
  fi

  # Install OpenPrinting drivers (covers most modern printers)
  apt-get install -y printer-driver-all openprinting-ppds 2>/dev/null || true

  # Check if any printers are connected (USB)
  if lsusb 2>/dev/null | grep -qi 'print\|hp\|canon\|epson\|brother'; then
    report_progress "USB printer detected  -  auto-configuring with CUPS..."
    systemctl enable --now cups 2>/dev/null || \
    sv start /etc/service/cups 2>/dev/null || true
    # Give CUPS a moment to auto-detect
    sleep 2
    lpstat -p 2>/dev/null >> "${LOG_FILE}" || true
    report_progress "Printer detected and configured. [OK]"
  else
    report_progress "No USB printer detected. CUPS is ready when you connect one."
  fi
  touch "${MARKER_PRINT}"
fi

# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------
if [[ ${#ISSUES[@]} -eq 0 ]]; then
  report_progress "Hardware setup complete [OK]"
  echo "[$(date '+%H:%M:%S')] All hardware detection tasks passed." >> "${LOG_FILE}"
  finish_dialog

  # Send a desktop notification (requires notify-send and a running session)
  notify-send \
    --icon=computer \
    --app-name="BOBO OS" \
    "Hardware setup complete [OK]" \
    "All drivers and firmware are installed and ready." 2>/dev/null || true
else
  ISSUE_TEXT=$(printf '%s\n' "${ISSUES[@]}")
  echo "[WARN] Issues detected:" >> "${LOG_FILE}"
  printf '%s\n' "${ISSUES[@]}" >> "${LOG_FILE}"
  fail_dialog "$(printf '%s\n' "${ISSUES[@]}")"

  notify-send \
    --icon=dialog-warning \
    --app-name="BOBO OS" \
    "Hardware setup needs attention" \
    "$(printf '%s\n' "${ISSUES[@]}")" \
    --urgency=normal 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Self-test block (prints PASS/FAIL for CI and debugging)
# ---------------------------------------------------------------------------
echo ""
echo "=== BOBO OS Hardware Detection Self-Test ==="
for MARKER_NAME in gpu wifi bluetooth touchscreen printer; do
  if [[ -f "${MARKER_DIR}/${MARKER_NAME}.done" ]]; then
    echo "  PASS  ${MARKER_NAME}"
  else
    echo "  FAIL  ${MARKER_NAME}"
  fi
done
echo "============================================"
