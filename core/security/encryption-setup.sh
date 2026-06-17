#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  LUKS2 Encryption Setup & Boot Unlock (Phase 9.3)
# E:\BOBO-OS\core\security\encryption-setup.sh
#
# Two modes:
#   setup    -  enroll an existing LUKS2 device: TPM2, recovery key, optional
#             fingerprint (fprintd).  Called once from the installer.
#   unlock   -  display a GTK4 passphrase dialog at boot and open the LUKS2
#             device before the root filesystem is mounted.  Called from the
#             initrd or early boot stage.
#
# Usage:
#   encryption-setup.sh setup   <device> [--tpm2] [--recovery] [--fprint]
#   encryption-setup.sh unlock  <device> <mapped-name>
#   encryption-setup.sh status  <device>
#   encryption-setup.sh --test
#
# Depends on: cryptsetup, clevis (TPM2), tpm2-tools, fprintd, Python3 + GTK4
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
# Globals
# ---------------------------------------------------------------------------
LOG_FILE="/var/log/bobo-encryption.log"
RECOVERY_KEY_DIR="/etc/bobo-os/recovery"
CLEVIS_PIN_TPM2="tpm2"
LUKS_KEYFILE_DIR="/etc/bobo-os/luks"
PASS=0; FAIL=0

log()  { echo "[$(date '+%H:%M:%S')] [Encryption] $*" | tee -a "${LOG_FILE}" 2>/dev/null || echo "$*"; }
ok()   { log "PASS  $*"; (( PASS++ )) || true; }
fail() { log "FAIL  $*"; (( FAIL++ )) || true; }
warn() { log "WARN  $*"; }

# ---------------------------------------------------------------------------
# GTK4 passphrase dialog (Python3 inline)
# Writes the passphrase to stdout; shows a graphical unlock prompt.
# ---------------------------------------------------------------------------
_show_passphrase_dialog() {
  local device_label="$1"
  local attempt="$2"      # 1, 2, or 3
  local msg="${3:-}"      # optional error message from previous attempt

  python3 - "$device_label" "$attempt" "$msg" <<'PYEOF'
import gi, sys
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio

device_label = sys.argv[1] if len(sys.argv) > 1 else "encrypted disk"
attempt      = sys.argv[2] if len(sys.argv) > 2 else "1"
error_msg    = sys.argv[3] if len(sys.argv) > 3 else ""

result = [None]

class UnlockApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.DiskUnlock",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self._on_activate)

    def _on_activate(self, app):
        win = Adw.ApplicationWindow(application=app)
        win.set_default_size(480, -1)
        win.set_resizable(False)
        win.set_title("BOBO OS  -  Disk Unlock")

        # Prevent closing without a decision
        win.connect("close-request", lambda w: True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        win.set_content(box)

        # No header bar at boot  -  full-screen feel
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_top(40)
        content.set_margin_bottom(32)
        content.set_margin_start(48)
        content.set_margin_end(48)
        box.append(content)

        # Lock icon
        icon = Gtk.Image.new_from_icon_name("changes-prevent-symbolic")
        icon.set_pixel_size(64)
        icon.add_css_class("accent")
        content.append(icon)

        # Title
        title = Gtk.Label(label="Unlock your disk")
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.CENTER)
        content.append(title)

        # Device label
        sub = Gtk.Label(label=f"Enter the passphrase for\n{device_label}")
        sub.add_css_class("body")
        sub.add_css_class("dim-label")
        sub.set_justify(Gtk.Justification.CENTER)
        sub.set_halign(Gtk.Align.CENTER)
        content.append(sub)

        # Error banner
        if error_msg:
            banner = Adw.Banner(title=error_msg)
            banner.set_revealed(True)
            content.append(banner)

        # Attempt indicator
        if int(attempt) > 1:
            attempt_lbl = Gtk.Label(label=f"Attempt {attempt} of 3")
            attempt_lbl.add_css_class("caption")
            attempt_lbl.add_css_class("warning")
            content.append(attempt_lbl)

        # Password entry inside a card
        entry_group = Adw.PreferencesGroup()
        passphrase_row = Adw.PasswordEntryRow(title="Passphrase")
        passphrase_row.set_show_apply_button(False)
        entry_group.add(passphrase_row)
        content.append(entry_group)

        # Unlock button
        unlock_btn = Gtk.Button(label="Unlock")
        unlock_btn.add_css_class("suggested-action")
        unlock_btn.add_css_class("pill")
        unlock_btn.set_halign(Gtk.Align.CENTER)
        unlock_btn.set_size_request(180, -1)
        content.append(unlock_btn)

        def _unlock(*_):
            pw = passphrase_row.get_text()
            if not pw:
                passphrase_row.add_css_class("error")
                return
            result[0] = pw
            win.close()
            app.quit()

        unlock_btn.connect("clicked", _unlock)
        passphrase_row.connect("apply", _unlock)

        # Enter key in entry triggers unlock
        key_ctrl = Gtk.EventControllerKey()
        def _key_press(ctrl, keyval, keycode, state):
            from gi.repository import Gdk
            if keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
                _unlock()
                return True
            return False
        key_ctrl.connect("key-pressed", _key_press)
        passphrase_row.add_controller(key_ctrl)

        win.present()
        passphrase_row.grab_focus()

app = UnlockApp()
app.run([])

if result[0] is not None:
    print(result[0], end="")
    sys.exit(0)
else:
    sys.exit(1)
PYEOF
}

# ---------------------------------------------------------------------------
# TPM2 enrollment via clevis
# ---------------------------------------------------------------------------
_enroll_tpm2() {
  local device="$1"
  log "Enrolling TPM2 via clevis..."

  if ! command -v clevis &>/dev/null; then
    warn "clevis not found  -  TPM2 enrollment skipped. Install: sudo apt install clevis clevis-tpm2 clevis-luks"
    return 1
  fi

  if ! command -v tpm2_pcrread &>/dev/null; then
    warn "tpm2-tools not found  -  PCR binding unavailable"
  fi

  # Use PCRs 0 (BIOS), 7 (Secure Boot state), 12 (grub) for binding
  local pcr_ids="0,7"
  command -v tpm2_pcrread &>/dev/null && pcr_ids="0,7,12"

  local clevis_cfg
  clevis_cfg=$(printf '{"pcr_ids":"%s"}' "${pcr_ids}")

  if clevis luks bind -d "${device}" "${CLEVIS_PIN_TPM2}" "${clevis_cfg}" 2>&1 | tee -a "${LOG_FILE}"; then
    ok "TPM2 enrolled for ${device} (PCRs: ${pcr_ids})"
    return 0
  else
    fail "TPM2 enrollment failed for ${device}"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Recovery key enrollment
# ---------------------------------------------------------------------------
_enroll_recovery_key() {
  local device="$1"
  log "Generating recovery key..."

  mkdir -p "${RECOVERY_KEY_DIR}"
  chmod 700 "${RECOVERY_KEY_DIR}"

  # 128-bit random recovery key displayed to user
  local recovery_key
  recovery_key=$(od -An -tx1 /dev/urandom | head -1 | tr -d ' \n' | cut -c1-32)
  # Format as groups of 4 for readability
  local display_key
  display_key=$(echo "${recovery_key}" | sed 's/.\{4\}/&-/g' | sed 's/-$//')

  # Write key to a keyfile for cryptsetup
  local keyfile="${RECOVERY_KEY_DIR}/recovery-$(basename "${device}").key"
  printf '%s' "${recovery_key}" > "${keyfile}"
  chmod 400 "${keyfile}"

  # Enroll the keyfile as a new LUKS key slot
  if cryptsetup luksAddKey "${device}" "${keyfile}" 2>&1 | tee -a "${LOG_FILE}"; then
    ok "Recovery key enrolled for ${device}"
    log "Recovery key stored at: ${keyfile}"

    # Display the recovery key to the user via GTK4
    python3 - "${display_key}" "${keyfile}" <<'PYEOF'
import gi, sys
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk

display_key = sys.argv[1] if len(sys.argv) > 1 else "????-????-????-????-????-????-????-????"
keyfile     = sys.argv[2] if len(sys.argv) > 2 else ""

class RecoveryApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.RecoveryKey",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self._on_activate)

    def _on_activate(self, app):
        win = Adw.ApplicationWindow(application=app)
        win.set_default_size(500, -1)
        win.set_title("Recovery Key")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        win.set_content(box)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(32)
        content.set_margin_end(32)
        box.append(content)

        icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        icon.set_pixel_size(48)
        content.append(icon)

        title = Gtk.Label(label="Save your recovery key")
        title.add_css_class("title-2")
        content.append(title)

        desc = Gtk.Label(
            label="If you forget your passphrase, you will need this key to access your data.\n"
                  "Store it somewhere safe  -  not on this computer."
        )
        desc.set_wrap(True)
        desc.set_justify(Gtk.Justification.CENTER)
        desc.add_css_class("dim-label")
        content.append(desc)

        # Recovery key display
        key_frame = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        key_frame.set_halign(Gtk.Align.CENTER)
        key_frame.add_css_class("card")
        key_frame.set_margin_top(8)
        key_frame.set_margin_bottom(8)

        key_lbl = Gtk.Label(label=display_key)
        key_lbl.add_css_class("monospace")
        key_lbl.add_css_class("title-4")
        key_lbl.set_margin_top(16)
        key_lbl.set_margin_bottom(16)
        key_lbl.set_margin_start(20)
        key_lbl.set_margin_end(12)
        key_lbl.set_selectable(True)
        key_frame.append(key_lbl)

        copy_btn = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
        copy_btn.add_css_class("flat")
        copy_btn.set_tooltip_text("Copy to clipboard")
        copy_btn.set_margin_end(8)
        copy_btn.set_valign(Gtk.Align.CENTER)
        def _copy(*_):
            win.get_clipboard().set(display_key)
            copy_btn.set_icon_name("emblem-ok-symbolic")
        copy_btn.connect("clicked", _copy)
        key_frame.append(copy_btn)
        content.append(key_frame)

        info = Gtk.Label(label=f"Also saved to: {keyfile}")
        info.add_css_class("caption")
        info.add_css_class("dim-label")
        content.append(info)

        done_btn = Gtk.Button(label="I have saved my recovery key")
        done_btn.add_css_class("suggested-action")
        done_btn.add_css_class("pill")
        done_btn.set_halign(Gtk.Align.CENTER)
        done_btn.connect("clicked", lambda b: (win.close(), app.quit()))
        content.append(done_btn)

        win.present()

app = RecoveryApp()
app.run([])
PYEOF
    return 0
  else
    fail "Recovery key enrollment failed"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Fingerprint enrollment (fprintd integration)
# ---------------------------------------------------------------------------
_enroll_fingerprint() {
  local device="$1"

  if ! command -v fprintd-enroll &>/dev/null; then
    warn "fprintd not found  -  fingerprint enrollment skipped."
    return 1
  fi

  log "Starting fingerprint enrollment (requires physical fingerprint scanner)..."

  # Enroll fingerprint for current user via fprintd
  if fprintd-enroll 2>&1 | tee -a "${LOG_FILE}"; then
    ok "Fingerprint enrolled"
    # Note: fprintd unlocks the desktop session; full disk encryption unlock
    # via biometrics requires TPM2 (fingerprint unlocks TPM2 which unlocks disk).
    # This integration is recorded in /etc/bobo-os/security.conf.
    mkdir -p /etc/bobo-os
    echo "FPRINT_ENABLED=true" >> /etc/bobo-os/security.conf
    return 0
  else
    fail "Fingerprint enrollment failed"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Mode: setup  -  called once at install time
# ---------------------------------------------------------------------------
cmd_setup() {
  local device="$1"
  shift
  local do_tpm2=false do_recovery=false do_fprint=false

  for arg in "$@"; do
    case "${arg}" in
      --tpm2)     do_tpm2=true ;;
      --recovery) do_recovery=true ;;
      --fprint)   do_fprint=true ;;
    esac
  done

  log "=== LUKS2 Encryption Setup: ${device} ==="

  # Verify device exists and is a LUKS2 container
  if [[ ! -b "${device}" ]]; then
    fail "Device ${device} not found or is not a block device"
    exit 1
  fi

  if ! cryptsetup isLuks "${device}" 2>/dev/null; then
    fail "${device} is not a LUKS device. Run installer first."
    exit 1
  fi

  local luks_version
  luks_version=$(cryptsetup luksDump "${device}" | grep "Version:" | awk '{print $2}')
  if [[ "${luks_version}" != "2" ]]; then
    warn "${device} is LUKS${luks_version}, not LUKS2. Some features unavailable."
  else
    ok "LUKS2 device confirmed: ${device}"
  fi

  # Show current key slots
  log "Active key slots:"
  cryptsetup luksDump "${device}" | grep -E "^Keyslots:" -A 999 | head -20 | tee -a "${LOG_FILE}"

  if [[ "${do_tpm2}" == true ]]; then
    _enroll_tpm2 "${device}" || warn "Continuing without TPM2."
  fi

  if [[ "${do_recovery}" == true ]]; then
    _enroll_recovery_key "${device}" || warn "Continuing without recovery key."
  fi

  if [[ "${do_fprint}" == true ]]; then
    _enroll_fingerprint "${device}" || warn "Continuing without fingerprint."
  fi

  # Configure initrd to call this script in unlock mode
  _write_initrd_hook "${device}"

  log "Setup complete. PASS: ${PASS}  FAIL: ${FAIL}"
}

# ---------------------------------------------------------------------------
# Write initrd hook (dracut or mkinitcpio)
# ---------------------------------------------------------------------------
_write_initrd_hook() {
  local device="$1"

  # mkinitcpio hook
  if [[ -d /etc/initcpio/install ]]; then
    local hook_dir="/etc/initcpio/hooks"
    local install_dir="/etc/initcpio/install"
    mkdir -p "${hook_dir}" "${install_dir}"

    cat > "${hook_dir}/bobo-unlock" <<HOOKEOF
#!/usr/bin/ash
run_hook() {
    msg ":: BOBO OS  -  unlocking encrypted root..."
    /usr/local/lib/bobo/core/security/encryption-setup.sh unlock ${device} root
}
HOOKEOF
    cat > "${install_dir}/bobo-unlock" <<INSTALLEOF
#!/bin/bash
build() {
    add_file /usr/local/lib/bobo/core/security/encryption-setup.sh
    add_binary cryptsetup
    add_binary python3
    add_module dm_crypt
}
help() {
    cat <<HELPEOF
Adds the BOBO OS graphical disk-unlock prompt to the initramfs.
HELPEOF
}
INSTALLEOF
    chmod +x "${hook_dir}/bobo-unlock" "${install_dir}/bobo-unlock"
    ok "mkinitcpio hook installed"

    # Add hook to mkinitcpio.conf
    if [[ -f /etc/mkinitcpio.conf ]]; then
      if ! grep -q 'bobo-unlock' /etc/mkinitcpio.conf; then
        sed -i 's/HOOKS=(\(.*\)encrypt\(.*\))/HOOKS=(\1bobo-unlock encrypt\2)/' /etc/mkinitcpio.conf || \
          sed -i 's/HOOKS=(\(.*filesystems\))/HOOKS=(\1 bobo-unlock)/' /etc/mkinitcpio.conf
        ok "mkinitcpio.conf updated"
      fi
    fi
  fi

  # dracut module
  if command -v dracut &>/dev/null; then
    local dracut_mod="/usr/lib/dracut/modules.d/90bobo-unlock"
    mkdir -p "${dracut_mod}"
    cat > "${dracut_mod}/module-setup.sh" <<DRACUTEOF
#!/bin/bash
check() { return 0; }
depends() { echo crypt; }
install() {
    inst_script "\$moddir/bobo-unlock.sh" /sbin/bobo-unlock
    inst_hook pre-mount 50 "\$moddir/bobo-unlock.sh"
}
DRACUTEOF
    cat > "${dracut_mod}/bobo-unlock.sh" <<DRACUTSH
#!/bin/bash
/usr/local/lib/bobo/core/security/encryption-setup.sh unlock ${device} root
DRACUTSH
    chmod +x "${dracut_mod}/module-setup.sh" "${dracut_mod}/bobo-unlock.sh"
    ok "dracut module installed"
  fi
}

# ---------------------------------------------------------------------------
# Mode: unlock  -  called at boot from initrd
# ---------------------------------------------------------------------------
cmd_unlock() {
  local device="$1"
  local mapped_name="${2:-root}"

  log "=== BOBO OS Disk Unlock: ${device} -> /dev/mapper/${mapped_name} ==="

  # Already unlocked?
  if [[ -b "/dev/mapper/${mapped_name}" ]]; then
    ok "${mapped_name} already open"
    return 0
  fi

  # Try TPM2 auto-unlock first (silent, no user interaction)
  if command -v clevis &>/dev/null; then
    log "Trying TPM2 auto-unlock..."
    if clevis luks unlock -d "${device}" -n "${mapped_name}" 2>/dev/null; then
      ok "TPM2 auto-unlock succeeded"
      return 0
    fi
    log "TPM2 unlock failed (PCR mismatch or not enrolled)  -  falling back to passphrase"
  fi

  # Try fingerprint (fprintd-verify) if enrolled  -  then use stored keyfile
  if command -v fprintd-verify &>/dev/null && \
     [[ -f /etc/bobo-os/security.conf ]] && \
     grep -q "FPRINT_ENABLED=true" /etc/bobo-os/security.conf; then
    log "Fingerprint enrolled  -  attempting biometric unlock..."
    if fprintd-verify 2>/dev/null; then
      # Fingerprint OK  -  use TPM-stored key (already tried above) or recovery key
      local keyfile="${RECOVERY_KEY_DIR}/recovery-$(basename "${device}").key"
      if [[ -f "${keyfile}" ]]; then
        if cryptsetup open "${device}" "${mapped_name}" --key-file "${keyfile}" 2>/dev/null; then
          ok "Biometric + key-file unlock succeeded"
          return 0
        fi
      fi
    fi
  fi

  # Passphrase prompt  -  up to 3 attempts
  local attempt=1
  local last_error=""

  while [[ "${attempt}" -le 3 ]]; do
    log "Passphrase attempt ${attempt}/3"

    # Show GTK4 dialog; get passphrase on stdout
    local passphrase
    if passphrase=$(_show_passphrase_dialog "${device}" "${attempt}" "${last_error}"); then
      if printf '%s' "${passphrase}" | \
           cryptsetup open "${device}" "${mapped_name}" --key-file=- 2>/dev/null; then
        ok "Passphrase unlock succeeded (attempt ${attempt})"
        return 0
      else
        last_error="Incorrect passphrase. Please try again."
        log "Passphrase incorrect"
      fi
    else
      log "Dialog cancelled or timed out"
      break
    fi
    (( attempt++ )) || true
  done

  fail "All unlock attempts exhausted. Booting into emergency shell."
  # Drop to a text shell so the user can manually unlock
  /bin/bash --login || true
  return 1
}

# ---------------------------------------------------------------------------
# Mode: status
# ---------------------------------------------------------------------------
cmd_status() {
  local device="$1"
  echo ""
  echo "=== LUKS2 Status: ${device} ==="

  if [[ ! -b "${device}" ]]; then
    echo "  NOT FOUND (${device} is not a block device)"
    return 1
  fi

  if ! cryptsetup isLuks "${device}" 2>/dev/null; then
    echo "  NOT LUKS (device exists but is not a LUKS container)"
    return 1
  fi

  cryptsetup luksDump "${device}" | grep -E "^(Version|UUID|Cipher|Cipher mode|Hash spec|Keyslots):" || true
  echo ""

  # Check if open
  local mapped
  for mapped in /dev/mapper/*; do
    if cryptsetup status "$(basename "${mapped}")" 2>/dev/null | grep -q "${device}"; then
      echo "  STATUS: OPEN -> ${mapped}"
      return 0
    fi
  done
  echo "  STATUS: LOCKED"

  # Check for clevis binding
  if command -v clevis &>/dev/null; then
    local tokens
    tokens=$(clevis luks list -d "${device}" 2>/dev/null || echo "none")
    echo "  Clevis tokens: ${tokens}"
  fi
}

# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
_run_self_test() {
  echo ""
  echo "=== Encryption Setup Self-Test ==="

  # Test 1: cryptsetup available
  if command -v cryptsetup &>/dev/null; then
    ok "cryptsetup: $(cryptsetup --version)"
  else
    fail "cryptsetup not found  -  install: sudo apt install cryptsetup"
  fi

  # Test 2: Python3 available (for GTK4 dialogs)
  if command -v python3 &>/dev/null; then
    ok "python3: $(python3 --version)"
  else
    fail "python3 not found"
  fi

  # Test 3: GTK4 importable
  if python3 -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk" 2>/dev/null; then
    ok "GTK4 importable"
  else
    warn "GTK4 not importable  -  passphrase dialog will not work (OK in initrd)"
  fi

  # Test 4: clevis (TPM2)
  if command -v clevis &>/dev/null; then
    ok "clevis: $(clevis --version 2>&1 | head -1)"
  else
    warn "clevis not found  -  TPM2 auto-unlock unavailable (install: sudo apt install clevis clevis-tpm2 clevis-luks)"
  fi

  # Test 5: tpm2-tools
  if command -v tpm2_pcrread &>/dev/null; then
    ok "tpm2-tools: available"
  else
    warn "tpm2-tools not found  -  install: sudo apt install tpm2-tools"
  fi

  # Test 6: fprintd
  if command -v fprintd-enroll &>/dev/null; then
    ok "fprintd: available"
  else
    warn "fprintd not found (fingerprint unlock unavailable)  -  install: sudo apt install fprintd"
  fi

  # Test 7: dm_crypt kernel module
  if modinfo dm_crypt &>/dev/null 2>&1; then
    ok "dm_crypt kernel module available"
  elif [[ -d /sys/module/dm_crypt ]]; then
    ok "dm_crypt module loaded"
  else
    warn "dm_crypt module not found  -  encryption may not work"
  fi

  # Test 8: /dev/mapper exists
  if [[ -d /dev/mapper ]]; then
    ok "/dev/mapper present"
  else
    fail "/dev/mapper not found  -  device mapper not available"
  fi

  # Test 9: Recovery key dir writeable
  mkdir -p "${RECOVERY_KEY_DIR}" 2>/dev/null || true
  if [[ -d "${RECOVERY_KEY_DIR}" ]]; then
    ok "Recovery key directory: ${RECOVERY_KEY_DIR}"
  else
    fail "Cannot create recovery key directory: ${RECOVERY_KEY_DIR}"
  fi

  # Test 10: Log file writeable
  touch "${LOG_FILE}" 2>/dev/null && ok "Log file: ${LOG_FILE}" || \
    warn "Cannot write to ${LOG_FILE} (expected in initrd environment)"

  echo ""
  echo "  PASS: ${PASS}  FAIL: ${FAIL}"
  echo "=================================="
  [[ "${FAIL}" -eq 0 ]]
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
case "${1:-}" in
  setup)
    shift
    if [[ -z "${1:-}" ]]; then
      echo "Usage: $0 setup <device> [--tpm2] [--recovery] [--fprint]" >&2
      exit 1
    fi
    cmd_setup "$@"
    ;;

  unlock)
    if [[ -z "${2:-}" ]]; then
      echo "Usage: $0 unlock <device> <mapped-name>" >&2
      exit 1
    fi
    cmd_unlock "${2}" "${3:-root}"
    ;;

  status)
    if [[ -z "${2:-}" ]]; then
      echo "Usage: $0 status <device>" >&2
      exit 1
    fi
    cmd_status "${2}"
    ;;

  --test)
    _run_self_test
    ;;

  *)
    echo "Usage: $0 {setup|unlock|status|--test}" >&2
    echo ""
    echo "  setup   <device> [--tpm2] [--recovery] [--fprint]"
    echo "  unlock  <device> <mapped-name>"
    echo "  status  <device>"
    echo "  --test"
    exit 1
    ;;
esac
