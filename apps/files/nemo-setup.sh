#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  Nemo File Manager Configuration (Phase 8.1)
# E:\BOBO-OS\apps\files\nemo-setup.sh
#
# Configures Nemo to match the BOBO OS experience:
# - BOBO OS theme (dark mode, accent colour)
# - Left sidebar with iCloud Drive / OneDrive / Google Drive bookmarks
# - NovaLayer integration (open .exe/.app/.ipa/.apk via double-click)
# - Preview pane enabled
# - "Open as Admin" right-click action via pkexec
# - Custom toolbar layout
# =============================================================================

set -euo pipefail

PASS=0; FAIL=0
log()  { echo "[Nemo Setup] $*"; }
ok()   { log "PASS  $*"; (( PASS++ )) || true; }
fail() { log "FAIL  $*"; (( FAIL++ )) || true; }
warn() { log "WARN  $*"; }

NEMO_CFG_DIR="${HOME}/.config/nemo"
NEMO_ACTIONS_DIR="${HOME}/.local/share/nemo/actions"
NEMO_SCRIPTS_DIR="${HOME}/.local/share/nemo/scripts"
BOOKMARKS_FILE="${HOME}/.config/gtk-3.0/bookmarks"
GSETTINGS_SCHEMA="org.nemo.preferences"

mkdir -p "${NEMO_CFG_DIR}" "${NEMO_ACTIONS_DIR}" "${NEMO_SCRIPTS_DIR}"
mkdir -p "$(dirname "${BOOKMARKS_FILE}")"

# ---------------------------------------------------------------------------
# Apply Nemo GSettings preferences
# ---------------------------------------------------------------------------
log "Applying Nemo preferences via GSettings..."

# Helper: apply a gsetting if the schema is available
gsset() {
  local schema="$1" key="$2" value="$3"
  if gsettings list-schemas 2>/dev/null | grep -q "^${schema}$"; then
    gsettings set "${schema}" "${key}" "${value}" 2>/dev/null && return 0 || return 1
  fi
  return 1
}

# Appearance
gsset "org.nemo.preferences"           show-hidden-files         false
gsset "org.nemo.preferences"           default-folder-viewer     "icon-view"
gsset "org.nemo.preferences"           icon-view-thumbnail-size  96
gsset "org.nemo.preferences"           show-full-path-in-title   true
gsset "org.nemo.preferences"           date-format              "iso"
gsset "org.nemo.preferences"           tooltip-on-desktop        false

# Preview pane
gsset "org.nemo.preferences"           show-sidebar              true
gsset "org.nemo.preferences"           sidebar-bookmark-breakout true

# Thumbnail settings
gsset "org.nemo.preferences"           show-image-thumbnails    "always"
gsset "org.nemo.preferences"           thumbnail-limit           10485760   # 10 MB

# Single-click vs double-click
gsset "org.nemo.preferences"           click-policy             "double"

# Sort
gsset "org.nemo.preferences"           default-sort-order       "name"
gsset "org.nemo.preferences"           default-sort-in-reverse-order false

# List view columns
gsset "org.nemo.list-view"             default-visible-columns  "['name','size','date_modified','type']"
gsset "org.nemo.list-view"             default-column-order     "['name','size','type','date_modified']"

# Window size/state
gsset "org.nemo.preferences"           start-with-status-bar    true
gsset "org.nemo.preferences"           start-with-toolbar       true
gsset "org.nemo.preferences"           start-with-sidebar       true

# Toolbar layout (home, up, refresh | search)
gsset "org.nemo.preferences"           toolbar-visible          true

# Disable desktop icons (BOBO OS uses Wayfire desktop)
gsset "org.nemo.desktop"               show-desktop-icons       false

ok "GSettings applied"

# ---------------------------------------------------------------------------
# Sidebar bookmarks (cloud drives + common locations)
# ---------------------------------------------------------------------------
log "Writing sidebar bookmarks..."

cat > "${BOOKMARKS_FILE}" <<EOF
file://${HOME}/Desktop Desktop
file://${HOME}/Documents Documents
file://${HOME}/Downloads Downloads
file://${HOME}/Pictures Pictures
file://${HOME}/Music Music
file://${HOME}/Videos Videos
file://${HOME}/iCloud%20Drive iCloud Drive
file://${HOME}/iCloud%20Drive/Photos iCloud Photos
file://${HOME}/OneDrive OneDrive
file://${HOME}/Google%20Drive Google Drive
EOF

ok "Bookmarks written: ${BOOKMARKS_FILE}"

# Create cloud drive mount points (they may be empty until novasync runs)
for dir in \
  "${HOME}/iCloud Drive" \
  "${HOME}/iCloud Drive/Photos" \
  "${HOME}/OneDrive" \
  "${HOME}/Google Drive"; do
  mkdir -p "${dir}"
done
ok "Cloud drive directories created"

# ---------------------------------------------------------------------------
# NovaLayer file actions (.exe, .app, .ipa, .apk)
# ---------------------------------------------------------------------------
log "Installing NovaLayer file actions..."

cat > "${NEMO_ACTIONS_DIR}/novalayer-run.nemo_action" <<EOF
[Nemo Action]
Active=true
Name=Run with BOBO OS
Comment=Open this file with NovaLayer compatibility layer
Exec=/usr/local/lib/bobo/core/novalayer/novalayer-daemon.py --open %F
Icon-Name=application-x-executable
Selection=s
Extensions=exe;msi;bat;app;dmg;pkg;ipa;apk;xapk;deb;rpm;AppImage;flatpak;
Quote=double
EOF

cat > "${NEMO_ACTIONS_DIR}/novalayer-identify.nemo_action" <<EOF
[Nemo Action]
Active=true
Name=Identify App Type
Comment=Show which compatibility layer BOBO OS will use for this file
Exec=/usr/local/lib/bobo/core/novalayer/novalayer-daemon.py --identify %F
Icon-Name=dialog-information-symbolic
Selection=s
Extensions=exe;msi;app;dmg;pkg;ipa;apk;xapk;
Quote=double
EOF

ok "NovaLayer file actions installed"

# ---------------------------------------------------------------------------
# "Open as Administrator" right-click action
# ---------------------------------------------------------------------------
cat > "${NEMO_ACTIONS_DIR}/open-as-admin.nemo_action" <<EOF
[Nemo Action]
Active=true
Name=Open as Administrator
Comment=Open this folder with administrator privileges
Exec=pkexec env DISPLAY=${DISPLAY:-:0} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0} XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)} nemo %F
Icon-Name=dialog-password-symbolic
Selection=none
Mimetypes=inode/directory;
Quote=double
EOF

ok "Open as Administrator action installed"

# ---------------------------------------------------------------------------
# "Open in Terminal" right-click action
# ---------------------------------------------------------------------------
cat > "${NEMO_ACTIONS_DIR}/open-terminal.nemo_action" <<EOF
[Nemo Action]
Active=true
Name=Open Terminal Here
Comment=Open a terminal in this folder
Exec=foot --working-directory=%P
Icon-Name=utilities-terminal-symbolic
Selection=none
Mimetypes=inode/directory;
Quote=double
EOF

ok "Open Terminal Here action installed"

# ---------------------------------------------------------------------------
# "Copy Path" right-click script
# ---------------------------------------------------------------------------
cat > "${NEMO_SCRIPTS_DIR}/Copy Path" <<'SCRIPTEOF'
#!/usr/bin/env bash
# Copies the selected file or folder path to the Wayland clipboard.
printf '%s' "${NEMO_SCRIPT_SELECTED_FILE_PATHS}" | \
  wl-copy 2>/dev/null || \
  xclip -selection clipboard 2>/dev/null || \
  true
SCRIPTEOF
chmod +x "${NEMO_SCRIPTS_DIR}/Copy Path"
ok "Copy Path script installed"

# ---------------------------------------------------------------------------
# "Share via NovaSync" right-click script
# ---------------------------------------------------------------------------
cat > "${NEMO_SCRIPTS_DIR}/Upload to Cloud" <<'SCRIPTEOF'
#!/usr/bin/env bash
# Copies selected files into the NovaSync upload queue.
UPLOAD_DIR="${HOME}/iCloud Drive"
for f in ${NEMO_SCRIPT_SELECTED_FILE_PATHS}; do
  cp -r "$f" "${UPLOAD_DIR}/" && \
    notify-send "BOBO OS" "Uploading: $(basename "$f")" -i "cloud-upload" || true
done
SCRIPTEOF
chmod +x "${NEMO_SCRIPTS_DIR}/Upload to Cloud"
ok "Upload to Cloud script installed"

# ---------------------------------------------------------------------------
# Custom CSS for Nemo (inherits BOBO OS GTK4 theme via GTK3 fallback)
# ---------------------------------------------------------------------------
NEMO_CSS="${NEMO_CFG_DIR}/nemo.css"
cat > "${NEMO_CSS}" <<'CSSEOF'
/* BOBO OS Nemo stylesheet  -  applied via GTK3 */

/* Sidebar navigation */
.sidebar .view {
  background-color: alpha(#1a1a2e, 0.95);
}

.sidebar row {
  border-radius: 6px;
  margin: 2px 4px;
  padding: 4px 8px;
}

.sidebar row:selected,
.sidebar row:selected:hover {
  background-color: #4a9eff;
  color: #ffffff;
}

/* Toolbar */
.toolbar {
  background-color: #1e1e30;
  border-bottom: 1px solid alpha(#ffffff, 0.08);
}

/* Path bar */
.path-bar button {
  border-radius: 6px;
}

/* File items */
.nemo-canvas-item {
  border-radius: 8px;
}

.nemo-canvas-item:selected {
  background-color: alpha(#4a9eff, 0.25);
  outline: 2px solid #4a9eff;
}
CSSEOF

# Apply the CSS via GTK3 settings
GTK3_SETTINGS="${HOME}/.config/gtk-3.0/settings.ini"
mkdir -p "$(dirname "${GTK3_SETTINGS}")"
if [[ ! -f "${GTK3_SETTINGS}" ]]; then
  cat > "${GTK3_SETTINGS}" <<EOF
[Settings]
gtk-application-prefer-dark-theme=1
gtk-theme-name=Adwaita-dark
gtk-icon-theme-name=Papirus-Dark
gtk-font-name=Inter 10
EOF
  ok "GTK3 settings written"
else
  ok "GTK3 settings already exist (not overwritten)"
fi

# ---------------------------------------------------------------------------
# Nemo extension: thumbnail providers for additional types
# ---------------------------------------------------------------------------
log "Checking for Nemo extensions..."

for ext_pkg in "nemo-fileroller" "nemo-preview" "nemo-share"; do
  if dpkg -l "${ext_pkg}" &>/dev/null 2>&1 || \
     pacman -Q "${ext_pkg}" &>/dev/null 2>&1 || \
     rpm -q "${ext_pkg}" &>/dev/null 2>&1; then
    ok "Extension installed: ${ext_pkg}"
  else
    warn "Optional extension not installed: ${ext_pkg}"
  fi
done

# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
echo ""
echo "=== Nemo Setup Self-Test ==="

command -v nemo &>/dev/null && ok "nemo binary found" || \
  fail "nemo not installed  -  install: sudo apt install nemo"

[[ -f "${BOOKMARKS_FILE}" ]] && ok "Bookmarks file present" || \
  fail "Bookmarks file missing"

[[ -f "${NEMO_ACTIONS_DIR}/novalayer-run.nemo_action" ]] && \
  ok "NovaLayer action installed" || \
  fail "NovaLayer action missing"

[[ -f "${NEMO_ACTIONS_DIR}/open-as-admin.nemo_action" ]] && \
  ok "Open as Admin action installed" || \
  fail "Open as Admin action missing"

[[ -f "${NEMO_SCRIPTS_DIR}/Copy Path" ]] && \
  ok "Copy Path script installed" || \
  fail "Copy Path script missing"

echo "  PASS: ${PASS}  FAIL: ${FAIL}"
echo "============================="
[[ "${FAIL}" -eq 0 ]]
