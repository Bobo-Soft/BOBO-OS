#!/bin/bash
# =============================================================================
# Faza 14 installer - Bobo Office (9 apps) + BoboAssist.
# Self-locating. Installs ONLY into /usr/share/bobo-office, /usr/share/bobo-assist,
# /usr/bin/bobo-* and XDG entries. Wayfire keybinding APPENDED (Super+O -> hub).
# Heavy TTS / model pull gated by BOBO_OFFICE_SKIP_HEAVY (default 1 = lean).
# =============================================================================
set -u
SRC="$(cd "$(dirname "$0")" && pwd)"
SKIP_HEAVY="${BOBO_OFFICE_SKIP_HEAVY:-1}"
# BoboAssist source: sibling dir, /tmp copy, or repo path
ASSIST=""
for cand in "$SRC/../bobo-assist" "$SRC/../bobo-assist-src" "/tmp/bobo-assist-src" "/mnt/e/BOBO-OS/bobo-assist"; do
    [ -d "$cand" ] && { ASSIST="$cand"; break; }
done

log(){ echo -e "\033[1;34m[bobo-office]\033[0m $*"; }
ok(){ echo -e "  \033[1;32mOK\033[0m $*"; }

log "=== Bobo Office installer (skip_heavy=$SKIP_HEAVY) ==="

# --- essential apt deps ------------------------------------------------------
ESSENTIAL="python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-gtksource-5 \
python3-cairo python3-venv fonts-liberation fonts-noto \
tesseract-ocr tesseract-ocr-ron tesseract-ocr-eng pandoc imagemagick espeak-ng ffmpeg \
wl-clipboard libnotify-bin"
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq 2>/dev/null || true
    log "Installing essential deps..."
    apt-get install -y --no-install-recommends $ESSENTIAL 2>/dev/null || \
        for p in $ESSENTIAL; do apt-get install -y --no-install-recommends "$p" 2>/dev/null || echo "  skip $p"; done
    apt-get install -y --no-install-recommends gir1.2-webkit2-4.1 2>/dev/null || true
    # apt-provided python libs (fast; venv --system-site-packages sees them)
    apt-get install -y --no-install-recommends python3-matplotlib python3-numpy python3-pandas \
        python3-pil python3-docx python3-openpyxl python3-reportlab python3-markdown \
        python3-requests python3-psutil 2>/dev/null || true
fi

# --- copy Office payload -----------------------------------------------------
log "Installing Bobo Office files..."
DEST=/usr/share/bobo-office
mkdir -p "$DEST"
for d in shared write calc present chart form sign translate mind hub; do
    [ -d "$SRC/$d" ] && cp -r "$SRC/$d" "$DEST/" 2>/dev/null || true
done
install -d /usr/bin
for launcher in "$SRC"/bin/*; do
    install -m 755 "$launcher" "/usr/bin/$(basename "$launcher")"
done

# --- BoboAssist payload ------------------------------------------------------
if [ -n "$ASSIST" ]; then
    log "Installing BoboAssist from $ASSIST ..."
    ADEST=/usr/share/bobo-assist
    mkdir -p "$ADEST"
    cp -r "$ASSIST/"* "$ADEST/" 2>/dev/null || true
    [ -f "$ADEST/bobo-assist" ] && install -m 755 "$ADEST/bobo-assist" /usr/bin/bobo-assist
    rm -f "$ADEST/_"*.sh 2>/dev/null || true
else
    log "WARN: BoboAssist source not found - office AI features will report offline"
fi

# --- venvs (system-site-packages so gi + apt libs are visible) ---------------
log "Creating isolated venvs (best-effort)..."
if python3 -m venv --system-site-packages "$DEST/venv" 2>/dev/null; then
    "$DEST/venv/bin/pip" install --quiet python-pptx pypdf2 plotly cairosvg pyhanko \
        langdetect deep-translator pyttsx3 watchdog 2>/dev/null && ok "office venv extras" || echo "  office venv: partial"
fi
if [ -d /usr/share/bobo-assist ] && python3 -m venv --system-site-packages /usr/share/bobo-assist/venv 2>/dev/null; then
    /usr/share/bobo-assist/venv/bin/pip install --quiet ollama psutil 2>/dev/null || true
fi

# --- heavy (gated): Coqui TTS + default model --------------------------------
if [ "$SKIP_HEAVY" = "0" ]; then
    log "Heavy mode: TTS + model pull"
    "$DEST/venv/bin/pip" install --quiet TTS 2>/dev/null || true
    command -v ollama >/dev/null 2>&1 && ollama pull phi3:mini 2>/dev/null || true
fi

# --- generate .desktop + .svg per app ---------------------------------------
install -d /usr/share/applications /usr/share/icons/hicolor/scalable/apps
gen_app() {   # name cmd comment letter
    local name="$1" cmd="$2" comment="$3" letter="$4"
    cat > "/usr/share/applications/$cmd.desktop" <<EOF
[Desktop Entry]
Name=$name
Comment=$comment
Exec=$cmd %F
Icon=$cmd
Terminal=false
Type=Application
Categories=BOBO;Office;
StartupNotify=true
StartupWMClass=$cmd
EOF
    cat > "/usr/share/icons/hicolor/scalable/apps/$cmd.svg" <<EOF
<svg width="128" height="128" viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
<rect width="128" height="128" rx="24" fill="#1a1a2e"/>
<rect x="20" y="102" width="88" height="8" rx="4" fill="#4a9eff" opacity="0.5"/>
<text x="64" y="82" font-family="Inter,sans-serif" font-size="64" font-weight="bold" fill="#4a9eff" text-anchor="middle">$letter</text>
</svg>
EOF
}
gen_app "BoboWrite"     bobo-write     "Procesor de text"      "W"
gen_app "BoboCalc"      bobo-calc      "Foaie de calcul"       "C"
gen_app "BoboPresent"   bobo-present   "Prezentări"            "P"
gen_app "BoboChart"     bobo-chart     "Grafice & infografice" "G"
gen_app "BoboForm"      bobo-form      "Formulare"             "F"
gen_app "BoboSign"      bobo-sign      "Semnătură digitală"    "S"
gen_app "BoboTranslate" bobo-translate "Traducere documente"   "T"
gen_app "BoboMind"      bobo-mind      "Mind maps"             "M"
gen_app "BoboHub"       bobo-hub       "Launcher Bobo Office"  "H"
[ -f /usr/share/bobo-assist/bobo-assist.desktop ] && install -m 644 /usr/share/bobo-assist/bobo-assist.desktop /usr/share/applications/ 2>/dev/null || true
[ -f /usr/share/bobo-assist/bobo-assist.svg ] && install -m 644 /usr/share/bobo-assist/bobo-assist.svg /usr/share/icons/hicolor/scalable/apps/ 2>/dev/null || true

# --- Wayfire keybindings (APPEND; Super+A already used by bobo-ai-local) ------
WF="/etc/bobo-wayfire-defaults.ini"
if [ -f "$WF" ] && ! grep -q "command_hub" "$WF" 2>/dev/null; then
    { echo ""; echo "# Bobo Office"; echo "binding_hub = <super> KEY_O"; echo "command_hub = bobo-hub"; } >> "$WF"
    ok "Super+O -> bobo-hub appended"
fi
# Super+A stays with bobo-ai-local (already bound); BoboAssist launches via Hub.

update-desktop-database /usr/share/applications/ 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true

# --- verify ------------------------------------------------------------------
echo ""; log "=== Verification ==="
for a in bobo-write bobo-calc bobo-present bobo-chart bobo-form bobo-sign bobo-translate bobo-mind bobo-hub bobo-assist; do
    "$a" --version >/dev/null 2>&1 && ok "$a" || echo "  WARN $a --version"
done
log "Bobo Office installed. Super+O -> BoboHub."
exit 0
