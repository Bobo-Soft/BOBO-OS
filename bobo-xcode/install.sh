#!/bin/bash
# =============================================================================
# BoboXcode installer — runs in the BOBO OS rootfs (chroot or live).
# Self-locating; installs ONLY into /usr/share/bobo-xcode + /usr/bin/bobo-xcode
# + XDG entries. Touches NO existing bobo-* app. Wayfire config is APPENDED.
#
# Heavy toolchains (Swift ~600MB, fastlane gem, clang/llvm, qemu-system-arm)
# are gated behind BOBO_XCODE_SKIP_HEAVY (default 1 = lean). Set 0 for full.
# =============================================================================
set -u
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="/usr/share/bobo-xcode"
SKIP_HEAVY="${BOBO_XCODE_SKIP_HEAVY:-1}"

log()  { echo -e "\033[1;34m[bobo-xcode]\033[0m $*"; }
ok()   { echo -e "  \033[1;32mOK\033[0m   $*"; }
warn() { echo -e "  \033[1;33mWARN\033[0m $*"; }

log "=== BoboXcode Installer (skip_heavy=$SKIP_HEAVY) ==="

# --- Guard: confirm existing BOBO apps are present and will NOT be touched ---
for app in bobo-player bobo-monitor bobo-settings bobo-text; do
    [ -f "/usr/bin/$app" ] && ok "$app present — left untouched"
done

# --- Essential deps (always; small, non-conflicting — apps import these) -----
ESSENTIAL="python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-gtksource-5 \
python3-yaml python3-paramiko python3-cryptography python3-watchdog \
python3-pygments python3-venv openssh-client rsync"
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq 2>/dev/null || true
    log "Installing essential deps..."
    apt-get install -y --no-install-recommends --no-upgrade $ESSENTIAL 2>/dev/null || \
        for p in $ESSENTIAL; do apt-get install -y --no-install-recommends "$p" 2>/dev/null || echo "  skip $p"; done
    # GTK4 VTE terminal widget (best-effort; terminal falls back to foot if absent)
    apt-get install -y --no-install-recommends gir1.2-vte-3.91 2>/dev/null && ok "gir1.2-vte-3.91" || warn "gir1.2-vte-3.91 absent (terminal uses external foot)"
fi

# --- Heavy toolchains (gated) ------------------------------------------------
if [ "$SKIP_HEAVY" != "1" ] && command -v apt-get >/dev/null 2>&1; then
    log "Installing heavy toolchain deps (full mode)..."
    HEAVY="clang llvm lld binutils qemu-system-arm qemu-system-x86 qemu-utils \
git curl wget unzip nodejs npm ruby ruby-dev build-essential sshpass"
    apt-get install -y --no-install-recommends $HEAVY 2>/dev/null || \
        for p in $HEAVY; do apt-get install -y --no-install-recommends "$p" 2>/dev/null || echo "  skip $p"; done

    # Fastlane (App Store automation) — runs locally only as a thin client; the
    # actual signing happens on the Mac cloud. Installed if ruby/gem present.
    if command -v gem >/dev/null 2>&1 && ! command -v fastlane >/dev/null 2>&1; then
        log "Installing fastlane gem..."
        gem install fastlane --no-document --quiet 2>/dev/null && ok "fastlane" || warn "fastlane gem failed (Publish still works once installed)"
    fi

    # Swift toolchain (official Apple build for Linux, ~600MB)
    if ! command -v swift >/dev/null 2>&1; then
        log "Downloading Swift toolchain (~600MB)..."
        SWIFT_VERSION="swift-5.10.1-RELEASE"
        SWIFT_URL="https://download.swift.org/swift-5.10.1-release/ubuntu2204/${SWIFT_VERSION}/${SWIFT_VERSION}-ubuntu22.04.tar.gz"
        if wget -q "$SWIFT_URL" -O /tmp/swift.tar.gz 2>/dev/null; then
            tar xzf /tmp/swift.tar.gz -C /opt/ 2>/dev/null && \
            ln -sf "/opt/${SWIFT_VERSION}-ubuntu22.04/usr/bin/swift"  /usr/local/bin/swift && \
            ln -sf "/opt/${SWIFT_VERSION}-ubuntu22.04/usr/bin/swiftc" /usr/local/bin/swiftc && \
            ln -sf "/opt/${SWIFT_VERSION}-ubuntu22.04/usr/bin/sourcekit-lsp" /usr/local/bin/sourcekit-lsp 2>/dev/null
            rm -f /tmp/swift.tar.gz
            command -v swift >/dev/null 2>&1 && ok "Swift toolchain" || warn "Swift link failed"
        else
            warn "Swift download failed (install later: bobo-xcode --install-swift)"
        fi
    fi
else
    log "Lean mode: skipping Swift/fastlane/qemu/clang. Install on demand with"
    log "  BOBO_XCODE_SKIP_HEAVY=0 bash $DEST/install.sh   (or per-tool later)."
fi

# --- Copy BoboXcode payload (ONLY into its own dirs) -------------------------
log "Installing BoboXcode files into $DEST ..."
mkdir -p "$DEST"
for item in main.py ui bridge simulator engines templates; do
    [ -e "$SRC_DIR/$item" ] && cp -r "$SRC_DIR/$item" "$DEST/" 2>/dev/null || true
done
install -m 755 "$SRC_DIR/bobo-xcode" /usr/bin/bobo-xcode

# --- Isolated Python venv (best-effort; launcher falls back to system python)-
if python3 -m venv "$DEST/venv" 2>/dev/null; then
    "$DEST/venv/bin/pip" install --quiet paramiko watchdog requests pyyaml pygments cryptography 2>/dev/null \
        && ok "isolated venv ready" || warn "venv pip install partial (system libs used as fallback)"
else
    warn "venv creation skipped (system python3 libs used)"
fi

# --- Data + config dirs ------------------------------------------------------
mkdir -p /var/lib/bobo-xcode/{projects,simulators,cache,logs}
mkdir -p /etc/bobo-xcode
chmod 777 /var/lib/bobo-xcode 2>/dev/null || true

# --- XDG integration (ADD only) ----------------------------------------------
install -d /usr/share/applications /usr/share/icons/hicolor/scalable/apps
install -m 644 "$SRC_DIR/bobo-xcode.desktop" /usr/share/applications/bobo-xcode.desktop
install -m 644 "$SRC_DIR/bobo-xcode.svg" /usr/share/icons/hicolor/scalable/apps/bobo-xcode.svg

# --- Wayfire keybinding (APPEND only; never overwrite) -----------------------
WF="/etc/bobo-wayfire-defaults.ini"
if [ -f "$WF" ] && ! grep -q "command_xcode" "$WF" 2>/dev/null; then
    {
        echo ""
        echo "# BoboXcode (added by install.sh — Super+X)"
        echo "binding_xcode = <super> KEY_X"
        echo "command_xcode = bobo-xcode"
    } >> "$WF"
    ok "Super+X keybinding appended to $WF"
elif [ ! -f "$WF" ]; then
    warn "$WF not found — keybinding skipped (run after bobo-apps install)"
fi

# --- Refresh desktop/icon caches ---------------------------------------------
update-desktop-database /usr/share/applications/ 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true

# --- Final verification ------------------------------------------------------
echo
log "=== Verification ==="
if bobo-xcode --version >/dev/null 2>&1; then
    ok "bobo-xcode launches ($(bobo-xcode --version 2>/dev/null | head -1))"
else
    warn "bobo-xcode --version returned non-zero (normal headless without GI deps)"
fi
command -v swift >/dev/null 2>&1 && ok "swift: $(swift --version 2>/dev/null | head -1)" || warn "swift not installed (lean mode)"
command -v fastlane >/dev/null 2>&1 && ok "fastlane present" || warn "fastlane not installed (lean mode)"

echo
log "BoboXcode installed. Super+X to launch. Existing BOBO apps untouched."
exit 0
