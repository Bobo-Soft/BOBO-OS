#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  Wine Wrapper (Phase 4.2)
# E:\BOBO-OS\core\novalayer\wine\wine-wrapper.sh
#
# Runs Windows .exe/.msi applications through Wine in an isolated prefix.
# - Creates a separate Wine prefix per application (in ~/.bobo/wine-prefixes/)
# - Installs winetricks dependencies on first run
# - Sets up DXVK for DirectX support
# - Shows GTK4 dialog on crash  -  never exposes terminal to user
# - Supports: wine-wrapper.sh <file.exe>
#             wine-wrapper.sh --uninstall <app-name>
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

# ---------------------------------------------------------------------------
# Paths  -  all from bobo-os.conf (or sensible defaults)
# ---------------------------------------------------------------------------
BOBO_CONFIG="/etc/bobo-os.conf"
[[ -f "${BOBO_CONFIG}" ]] && source "${BOBO_CONFIG}" || true

WINE_BIN="${WINE_BIN:-/usr/bin/wine64}"
WINE32_BIN="${WINE32_BIN:-/usr/bin/wine}"
DXVK_DIR="${DXVK_DIR:-/usr/local/lib/bobo/novalayer/wine/dxvk}"
PREFIXES_DIR="${WINE_PREFIXES_DIR:-${HOME}/.bobo/wine-prefixes}"
NOVALAYER_LOG="${NOVALAYER_LOG:-/var/log/novalayer.log}"
WINETRICKS_BIN="${WINETRICKS_BIN:-/usr/bin/winetricks}"

# Environment variables required by Wine
export WINEDEBUG="-all"           # Suppress Wine debug spam in logs
export WINEFSYNC=1                # FSSync (faster than esync on Linux 5.16+)
export WINEESYNC=1                # ESYnc fallback
export MESA_GL_VERSION_OVERRIDE=4.5  # Ensure OpenGL 4.5 is reported to apps

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "Usage: wine-wrapper.sh <application.exe|application.msi>"
  echo "       wine-wrapper.sh --uninstall <app-name>"
  exit 1
fi

if [[ "$1" == "--uninstall" ]]; then
  UNINSTALL_MODE=true
  APP_NAME="$2"
else
  UNINSTALL_MODE=false
  APP_PATH=$(realpath "$1")
  APP_FILENAME=$(basename "${APP_PATH}")
  APP_NAME="${APP_FILENAME%.*}"       # Strip extension for use as prefix name
  APP_EXT="${APP_PATH##*.}"
  APP_EXT="${APP_EXT,,}"              # Lowercase extension
fi

# Per-app Wine prefix directory
PREFIX_DIR="${PREFIXES_DIR}/${APP_NAME}"

# ---------------------------------------------------------------------------
# GTK4 error dialog (shown to user instead of terminal error output)
# ---------------------------------------------------------------------------
show_error_dialog() {
  local title="$1"
  local message="$2"
  python3 - "${title}" "${message}" <<'PYEOF' &
import gi, sys
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

title = sys.argv[1] if len(sys.argv) > 1 else "Error"
message = sys.argv[2] if len(sys.argv) > 2 else "An unknown error occurred."

class ErrorApp(Adw.Application):
    def do_activate(self):
        win = Adw.ApplicationWindow(application=self, title=title)
        win.set_default_size(420, 200)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(32); box.set_margin_bottom(24)
        box.set_margin_start(32); box.set_margin_end(32)

        icon = Gtk.Image.new_from_icon_name("dialog-error")
        icon.set_pixel_size(48)
        box.append(icon)

        lbl_title = Gtk.Label(label=f"<b>{title}</b>")
        lbl_title.set_use_markup(True)
        lbl_title.add_css_class("title-3")
        box.append(lbl_title)

        lbl_msg = Gtk.Label(label=message)
        lbl_msg.set_wrap(True)
        lbl_msg.set_halign(Gtk.Align.CENTER)
        box.append(lbl_msg)

        btn = Gtk.Button(label="OK")
        btn.add_css_class("suggested-action")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect("clicked", lambda *_: self.quit())
        box.append(btn)

        win.set_content(box)
        win.present()

ErrorApp(application_id="os.bobo.wine.error").run([])
PYEOF
}

# ---------------------------------------------------------------------------
# GTK4 progress dialog for first-run setup
# ---------------------------------------------------------------------------
show_setup_progress() {
  python3 - <<'PYEOF' &
import gi, sys, os
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

PIPE = os.environ.get("SETUP_PIPE", "")

class SetupApp(Adw.Application):
    def do_activate(self):
        win = Adw.ApplicationWindow(application=self, title="Setting up app…")
        win.set_default_size(460, 180)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(28); box.set_margin_bottom(28)
        box.set_margin_start(32); box.set_margin_end(32)

        lbl = Gtk.Label(label="<b>Preparing to run Windows app…</b>")
        lbl.set_use_markup(True)
        box.append(lbl)

        self.task_lbl = Gtk.Label(label="Setting up compatibility layer…")
        box.append(self.task_lbl)

        self.pbar = Gtk.ProgressBar()
        self.pbar.set_pulse_step(0.04)
        box.append(self.pbar)

        win.set_content(box)
        win.present()

        GLib.timeout_add(80, lambda: (self.pbar.pulse(), True))

        if PIPE:
            import threading
            threading.Thread(target=self._read_pipe, daemon=True).start()

    def _read_pipe(self):
        import time
        try:
            with open(PIPE, "r") as f:
                for line in f:
                    line = line.strip()
                    if line == "DONE":
                        GLib.idle_add(self.quit)
                        return
                    GLib.idle_add(self.task_lbl.set_text, line)
        except Exception:
            GLib.idle_add(self.quit)

SetupApp(application_id="os.bobo.wine.setup").run([])
PYEOF
  SETUP_DIALOG_PID=$!
}

# ---------------------------------------------------------------------------
# Uninstall mode
# ---------------------------------------------------------------------------
if $UNINSTALL_MODE; then
  if [[ ! -d "${PREFIX_DIR}" ]]; then
    show_error_dialog "App not found" \
      "Could not find an installation for '${APP_NAME}'.\nIt may have already been removed."
    exit 1
  fi

  # Run the Wine uninstaller for this prefix
  WINEPREFIX="${PREFIX_DIR}" "${WINE_BIN}" uninstaller 2>/dev/null &
  wait $!

  # Remove the prefix directory
  rm -rf "${PREFIX_DIR}"
  echo "Uninstalled: ${APP_NAME}" >> "${NOVALAYER_LOG}"

  # Remove desktop shortcut if present
  rm -f "${HOME}/.local/share/applications/bobo-wine-${APP_NAME}.desktop" 2>/dev/null || true
  exit 0
fi

# ---------------------------------------------------------------------------
# First-run: set up Wine prefix with DXVK
# ---------------------------------------------------------------------------
FIRST_RUN=false
if [[ ! -d "${PREFIX_DIR}" ]]; then
  FIRST_RUN=true
  mkdir -p "${PREFIX_DIR}"
fi

log_msg() {
  echo "[$(date '+%H:%M:%S')] [Wine] $*" >> "${NOVALAYER_LOG}"
}

log_msg "Launching: ${APP_PATH}"

if $FIRST_RUN; then
  log_msg "First run  -  initialising Wine prefix at ${PREFIX_DIR}"

  # Create a named pipe for progress reporting to GTK dialog
  SETUP_PIPE="/tmp/bobo-wine-setup-$$"
  mkfifo "${SETUP_PIPE}"
  export SETUP_PIPE
  show_setup_progress

  report_setup() {
    echo "$1" > "${SETUP_PIPE}" 2>/dev/null || true
    log_msg "$1"
  }

  # Initialise the Wine prefix (64-bit)
  report_setup "Initialising Wine environment…"
  WINEPREFIX="${PREFIX_DIR}" WINEARCH=win64 "${WINE_BIN}" wineboot --init 2>/dev/null || true

  # Install common winetricks dependencies for broad compatibility
  report_setup "Installing runtime libraries (vcrun2022, corefonts)…"
  if command -v winetricks &>/dev/null; then
    WINEPREFIX="${PREFIX_DIR}" winetricks -q \
      vcrun2022 \
      corefonts \
      dxvk \
      2>/dev/null || true
  fi

  # Install DXVK manually if winetricks didn't do it
  if [[ -d "${DXVK_DIR}" ]]; then
    report_setup "Installing DXVK (DirectX compatibility layer)…"
    DXVK_SETUP="${DXVK_DIR}/setup_dxvk.sh"
    if [[ -x "${DXVK_SETUP}" ]]; then
      WINEPREFIX="${PREFIX_DIR}" bash "${DXVK_SETUP}" install 2>/dev/null || true
    else
      # Manual DLL copy fallback
      for dll_dir in "${DXVK_DIR}/x64" "${DXVK_DIR}/x32"; do
        [[ -d "${dll_dir}" ]] || continue
        TARGET="${PREFIX_DIR}/drive_c/windows/$(basename "${dll_dir}" | sed 's/x64/system32/;s/x32/syswow64/')"
        mkdir -p "${TARGET}"
        cp "${dll_dir}"/*.dll "${TARGET}/" 2>/dev/null || true
        # Register each DLL override
        for dll in d3d9 d3d10 d3d10_1 d3d10core d3d11 dxgi; do
          WINEPREFIX="${PREFIX_DIR}" "${WINE_BIN}" reg add \
            'HKCU\Software\Wine\DllOverrides' \
            /v "${dll}" /t REG_SZ /d native /f 2>/dev/null || true
        done
      done
    fi
  fi

  report_setup "Ready!"
  echo "DONE" > "${SETUP_PIPE}" 2>/dev/null || true
  sleep 0.5
  rm -f "${SETUP_PIPE}"
fi

# ---------------------------------------------------------------------------
# Run the application
# ---------------------------------------------------------------------------
export WINEPREFIX="${PREFIX_DIR}"

if [[ "${APP_EXT}" == "msi" ]]; then
  # MSI installer: use msiexec
  CMD=("${WINE_BIN}" msiexec /i "${APP_PATH}")
else
  CMD=("${WINE_BIN}" "${APP_PATH}")
fi

log_msg "Executing: ${CMD[*]}"

# Run and capture exit code; show dialog on failure
if ! "${CMD[@]}" 2>>/tmp/bobo-wine-$$.log; then
  EXIT_CODE=$?
  WINE_LOG_SNIPPET=$(tail -5 /tmp/bobo-wine-$$.log 2>/dev/null || true)
  rm -f /tmp/bobo-wine-$$.log

  log_msg "App crashed (exit ${EXIT_CODE}): ${APP_FILENAME}"
  show_error_dialog \
    "App stopped unexpectedly" \
    "The Windows app '${APP_FILENAME}' stopped unexpectedly.\n\nThis may be due to missing dependencies or incompatibility.\nBOBO OS logged the details for you.\n\nTry opening the app again, or check if a Linux version is available in NovaStore."
fi

rm -f /tmp/bobo-wine-$$.log

# ---------------------------------------------------------------------------
# Self-test block
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--self-test" ]]; then
  echo "=== Wine Wrapper Self-Test ==="
  command -v wine64 &>/dev/null || command -v wine &>/dev/null && echo "  PASS  Wine binary found" || echo "  FAIL  Wine binary not found"
  [[ -d "${PREFIXES_DIR}" ]] || mkdir -p "${PREFIXES_DIR}" && echo "  PASS  Prefixes directory exists"
  [[ -d "${DXVK_DIR}" ]] && echo "  PASS  DXVK directory found" || echo "  WARN  DXVK directory missing (install via setup-tools.sh)"
  echo "=============================="
fi
