#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  Darling Wrapper (Phase 4.3)
# E:\BOBO-OS\core\novalayer\darling\darling-wrapper.sh
#
# Runs macOS .app bundles, mounts .dmg files, and installs .pkg packages
# using Darling (the macOS compatibility layer for Linux).
# Shows GTK4 dialogs for progress and errors  -  no terminal exposed to users.
# =============================================================================

set -euo pipefail

if grep -qi microsoft /proc/version 2>/dev/null; then
  HOST_ENV="wsl2"
else
  HOST_ENV="linux"
fi

DARLING_BIN="${DARLING_BIN:-/usr/local/darling/bin/darling}"
NOVALAYER_LOG="${NOVALAYER_LOG:-/var/log/novalayer.log}"
MOUNT_BASE="/tmp/bobo-dmg-mounts"

log_msg() { echo "[$(date '+%H:%M:%S')] [Darling] $*" >> "${NOVALAYER_LOG}"; }

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "Usage: darling-wrapper.sh <file.app|file.dmg|file.pkg>"
  exit 1
fi

FILE_PATH=$(realpath "$1")
FILE_NAME=$(basename "${FILE_PATH}")
FILE_EXT="${FILE_PATH##*.}"
FILE_EXT="${FILE_EXT,,}"

log_msg "Called with: ${FILE_PATH}"

# ---------------------------------------------------------------------------
# Helper: GTK4 error dialog
# ---------------------------------------------------------------------------
show_error_dialog() {
  local title="$1" msg="$2"
  python3 - "${title}" "${msg}" <<'PYEOF' &
import gi, sys
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")
from gi.repository import Gtk, Adw
class App(Adw.Application):
    def do_activate(self):
        win = Adw.ApplicationWindow(application=self, title=sys.argv[1])
        win.set_default_size(440,200)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(28);box.set_margin_bottom(24)
        box.set_margin_start(32);box.set_margin_end(32)
        ic = Gtk.Image.new_from_icon_name("dialog-warning")
        ic.set_pixel_size(48); box.append(ic)
        l1=Gtk.Label(label=f"<b>{sys.argv[1]}</b>"); l1.set_use_markup(True); box.append(l1)
        l2=Gtk.Label(label=sys.argv[2]); l2.set_wrap(True); l2.set_halign(Gtk.Align.CENTER); box.append(l2)
        btn=Gtk.Button(label="OK"); btn.add_css_class("suggested-action")
        btn.set_halign(Gtk.Align.CENTER); btn.connect("clicked", lambda *_: self.quit()); box.append(btn)
        win.set_content(box); win.present()
App(application_id="os.bobo.darling.error").run([])
PYEOF
}

# ---------------------------------------------------------------------------
# Helper: GTK4 progress dialog (for .pkg install)
# ---------------------------------------------------------------------------
show_progress_dialog() {
  local title="$1"
  python3 - "${title}" <<'PYEOF' &
import gi, sys, os, threading
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")
from gi.repository import Gtk, Adw, GLib
PIPE = os.environ.get("DARLING_PIPE","")
class App(Adw.Application):
    def do_activate(self):
        win = Adw.ApplicationWindow(application=self, title=sys.argv[1])
        win.set_default_size(460,160)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(28);box.set_margin_bottom(28)
        box.set_margin_start(32);box.set_margin_end(32)
        self.lbl = Gtk.Label(label="Starting installer…"); box.append(self.lbl)
        self.pb = Gtk.ProgressBar(); self.pb.set_pulse_step(0.03); box.append(self.pb)
        win.set_content(box); win.present()
        GLib.timeout_add(80, lambda: (self.pb.pulse(), True))
        if PIPE:
            threading.Thread(target=self._read, daemon=True).start()
    def _read(self):
        try:
            with open(PIPE,"r") as f:
                for line in f:
                    line=line.strip()
                    if line=="DONE": GLib.idle_add(self.quit); return
                    GLib.idle_add(self.lbl.set_text, line)
        except: GLib.idle_add(self.quit)
App(application_id="os.bobo.darling.progress").run([])
PYEOF
}

# ---------------------------------------------------------------------------
# Verify Darling is installed
# ---------------------------------------------------------------------------
if [[ ! -x "${DARLING_BIN}" ]] && ! command -v darling &>/dev/null; then
  show_error_dialog \
    "macOS compatibility not available" \
    "Darling is not installed on this system.\n\nYou can install it via NovaStore -> System Tools, or Settings -> About -> Install Darling."
  exit 1
fi

DARLING_CMD="${DARLING_BIN}"
command -v darling &>/dev/null && DARLING_CMD="darling"

# ---------------------------------------------------------------------------
# .DMG  -  mount and show contents in Nemo file manager
# ---------------------------------------------------------------------------
handle_dmg() {
  log_msg "Mounting DMG: ${FILE_PATH}"
  MOUNT_POINT="${MOUNT_BASE}/$(basename "${FILE_PATH}" .dmg)-$$"
  mkdir -p "${MOUNT_POINT}"

  # Darling can mount DMGs via its hdiutil emulation
  if "${DARLING_CMD}" shell hdiutil attach \
      "${FILE_PATH}" -mountpoint "${MOUNT_POINT}" -nobrowse 2>/dev/null; then
    log_msg "DMG mounted at ${MOUNT_POINT}"
    # Open the mount point in the file manager
    nemo "${MOUNT_POINT}" 2>/dev/null || xdg-open "${MOUNT_POINT}" 2>/dev/null || true
    # Register auto-unmount when the file manager closes (best-effort)
    nohup bash -c "sleep 300; ${DARLING_CMD} shell hdiutil detach '${MOUNT_POINT}' 2>/dev/null; rmdir '${MOUNT_POINT}' 2>/dev/null" &
  else
    # Fallback: try udisksctl + loop device (plain HFS+/APFS images)
    LOOP_DEV=$(udisksctl loop-setup -f "${FILE_PATH}" 2>/dev/null | grep -oP '/dev/loop\d+' || true)
    if [[ -n "${LOOP_DEV}" ]]; then
      udisksctl mount -b "${LOOP_DEV}" 2>/dev/null || true
      nemo "/run/media/${USER}/$(ls /run/media/${USER}/ | tail -1)" 2>/dev/null || true
    else
      show_error_dialog "Could not open DMG" \
        "BOBO OS could not open '${FILE_NAME}'.\n\nThe disk image may be encrypted or use an unsupported format."
    fi
  fi
}

# ---------------------------------------------------------------------------
# .APP bundle  -  run directly via Darling shell
# ---------------------------------------------------------------------------
handle_app() {
  log_msg "Running .app bundle: ${FILE_PATH}"

  # Check if the app is ARM-only (no x86_64 slice)
  if "${DARLING_CMD}" shell lipo -info "${FILE_PATH}/Contents/MacOS/"* 2>/dev/null \
      | grep -q 'arm64' && \
     ! "${DARLING_CMD}" shell lipo -info "${FILE_PATH}/Contents/MacOS/"* 2>/dev/null \
      | grep -q 'x86_64'; then
    show_error_dialog \
      "App not compatible" \
      "'${FILE_NAME}' is designed for Apple Silicon (ARM) only.\n\nBOBO OS can only run macOS apps built for Intel (x86_64).\n\nCheck if the developer offers an Intel version."
    log_msg "ARM-only app rejected: ${FILE_PATH}"
    exit 1
  fi

  # Extract the main executable name
  MAIN_EXEC=$(defaults read "${FILE_PATH}/Contents/Info.plist" CFBundleExecutable 2>/dev/null \
    || ls "${FILE_PATH}/Contents/MacOS/" | head -1)

  log_msg "Executing: ${FILE_PATH}/Contents/MacOS/${MAIN_EXEC}"
  "${DARLING_CMD}" shell \
    exec "${FILE_PATH}/Contents/MacOS/${MAIN_EXEC}" \
    2>>/tmp/bobo-darling-$$.log &

  DARLING_PID=$!
  wait "${DARLING_PID}" || EXIT_CODE=$?

  if [[ "${EXIT_CODE:-0}" -ne 0 ]]; then
    log_msg "App exited with code ${EXIT_CODE}: ${FILE_NAME}"
    show_error_dialog \
      "App stopped unexpectedly" \
      "'${FILE_NAME}' stopped unexpectedly.\n\nThis may be due to missing macOS frameworks or incompatibility.\nBOBO OS logged the details."
  fi
  rm -f /tmp/bobo-darling-$$.log
}

# ---------------------------------------------------------------------------
# .PKG  -  graphical installation via Darling's installer command
# ---------------------------------------------------------------------------
handle_pkg() {
  log_msg "Installing PKG: ${FILE_PATH}"

  DARLING_PIPE="/tmp/bobo-darling-pkg-$$"
  mkfifo "${DARLING_PIPE}"
  export DARLING_PIPE
  show_progress_dialog "Installing ${FILE_NAME}…"

  report() {
    echo "$1" > "${DARLING_PIPE}" 2>/dev/null || true
    log_msg "$1"
  }

  report "Preparing installer…"

  # Run the macOS installer tool via Darling
  if "${DARLING_CMD}" shell installer \
      -pkg "${FILE_PATH}" \
      -target / \
      2>/tmp/bobo-darling-pkg-$$.log; then

    report "Installation complete! Creating shortcut…"

    # Create a .desktop shortcut for any .app installed to /Applications
    INSTALLED_APP=$(find "${DARLING_CMD}" -path "*/Applications/*.app" -maxdepth 3 2>/dev/null | head -1 || true)
    if [[ -n "${INSTALLED_APP}" ]]; then
      APP_DISPLAY=$(basename "${INSTALLED_APP}" .app)
      DESKTOP_FILE="${HOME}/.local/share/applications/bobo-darling-${APP_DISPLAY// /-}.desktop"
      cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=${APP_DISPLAY}
Exec=bash $(realpath "$0") "${INSTALLED_APP}"
Icon=application-x-apple
Categories=Application;
Comment=macOS app running via BOBO OS NovaLayer
EOF
      chmod +x "${DESKTOP_FILE}"
      log_msg "Desktop shortcut created: ${DESKTOP_FILE}"
    fi

    report "DONE"
  else
    log_msg "PKG install failed for ${FILE_PATH}"
    report "DONE"
    show_error_dialog \
      "Installation failed" \
      "'${FILE_NAME}' could not be installed.\n\nThe package may require macOS-specific system components that are not available.\nBOBO OS logged the details."
  fi

  rm -f "${DARLING_PIPE}" /tmp/bobo-darling-pkg-$$.log
}

# ---------------------------------------------------------------------------
# Route by file extension
# ---------------------------------------------------------------------------
case "${FILE_EXT}" in
  dmg) handle_dmg ;;
  app) handle_app ;;
  pkg) handle_pkg ;;
  *)
    show_error_dialog \
      "Unsupported file type" \
      "BOBO OS doesn't know how to open '${FILE_NAME}' with Darling.\n\nSupported types: .app  .dmg  .pkg"
    exit 1
    ;;
esac

# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--self-test" ]]; then
  echo "=== Darling Wrapper Self-Test ==="
  command -v darling &>/dev/null || [[ -x "${DARLING_BIN}" ]] \
    && echo "  PASS  Darling binary found" \
    || echo "  WARN  Darling not installed (macOS app support unavailable)"
  echo "================================="
fi
