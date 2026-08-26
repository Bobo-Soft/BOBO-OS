#!/bin/bash
# =============================================================================
# Faza 15 installer - BoboVoice (offline "Hey Bobo" voice assistant).
# Self-locating. Installs ONLY into /usr/share/bobo-voice, /usr/bin/bobo-voice,
# XDG autostart + icon. Wayfire keybinding APPENDED (Super+Shift+V toggle).
# Heavy TTS (Coqui) + LLaVA pull gated by BOBO_VOICE_SKIP_HEAVY (default 1 = lean).
# =============================================================================
set -u
SRC="$(cd "$(dirname "$0")" && pwd)"
SKIP_HEAVY="${BOBO_VOICE_SKIP_HEAVY:-1}"
DEST=/usr/share/bobo-voice

log(){ echo -e "\033[1;34m[bobo-voice]\033[0m $*"; }
ok(){ echo -e "  \033[1;32mOK\033[0m $*"; }

log "=== BoboVoice installer (skip_heavy=$SKIP_HEAVY) ==="

# --- apt deps ----------------------------------------------------------------
ESSENTIAL="python3-gi gir1.2-gtk-4.0 python3-venv \
alsa-utils pulseaudio-utils ffmpeg sox libsox-fmt-all \
espeak-ng espeak-ng-data brightnessctl playerctl \
tesseract-ocr tesseract-ocr-ron tesseract-ocr-eng \
wtype grim wl-clipboard libnotify-bin portaudio19-dev python3-pyaudio"
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq 2>/dev/null || true
    log "Installing essential deps..."
    apt-get install -y --no-install-recommends $ESSENTIAL 2>/dev/null || \
        for p in $ESSENTIAL; do apt-get install -y --no-install-recommends "$p" 2>/dev/null || echo "  skip $p"; done
    # layer-shell for the overlay (best-effort)
    apt-get install -y --no-install-recommends gir1.2-gtk4-layer-shell-1.0 2>/dev/null || true
    apt-get install -y --no-install-recommends python3-numpy python3-pil python3-requests python3-psutil 2>/dev/null || true
fi

# --- copy payload ------------------------------------------------------------
log "Installing BoboVoice files..."
mkdir -p "$DEST"
for f in profile_manager.py wake_word.py stt_engine.py tts_engine.py document_reader.py \
         image_describer.py video_translator.py live_captioner.py action_executor.py \
         intent_engine.py bobo_voice.py ui sounds; do
    [ -e "$SRC/$f" ] && cp -r "$SRC/$f" "$DEST/" 2>/dev/null || true
done
install -m 755 "$SRC/bobo-voice" /usr/bin/bobo-voice

# --- activation sound (sox beep 440Hz 0.2s) ---------------------------------
mkdir -p "$DEST/sounds"
if command -v sox >/dev/null 2>&1; then
    sox -n "$DEST/sounds/activation.wav" synth 0.2 sine 440 gain -6 2>/dev/null && ok "activation.wav"
fi

# --- venv (system-site-packages so gi + audio libs coexist) ------------------
log "Creating voice venv..."
if python3 -m venv --system-site-packages "$DEST/venv" 2>/dev/null; then
    "$DEST/venv/bin/pip" install --quiet faster-whisper openwakeword sounddevice soundfile \
        pytesseract deep-translator ollama 2>/dev/null && ok "voice venv extras" || echo "  voice venv: partial"
    if [ "$SKIP_HEAVY" = "0" ]; then
        "$DEST/venv/bin/pip" install --quiet TTS 2>/dev/null || true
    else
        "$DEST/venv/bin/pip" install --quiet pyttsx3 2>/dev/null || true
    fi
fi
if [ "$SKIP_HEAVY" = "0" ] && command -v ollama >/dev/null 2>&1; then
    ollama pull llava:7b 2>/dev/null || true
fi

# --- XDG icon + desktop + autostart -----------------------------------------
install -d /usr/share/applications /usr/share/icons/hicolor/scalable/apps /etc/xdg/autostart
install -m 644 "$SRC/bobo-voice.desktop" /usr/share/applications/bobo-voice.desktop
install -m 644 "$SRC/bobo-voice.svg" /usr/share/icons/hicolor/scalable/apps/bobo-voice.svg
cat > /etc/xdg/autostart/bobo-voice.desktop <<'EOF'
[Desktop Entry]
Name=BoboVoice Autostart
Exec=bobo-voice --daemon
Terminal=false
Type=Application
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
NoDisplay=true
EOF
ok "autostart installed (3s delay)"

# --- Wayfire keybinding (APPEND) --------------------------------------------
WF="/etc/bobo-wayfire-defaults.ini"
if [ -f "$WF" ] && ! grep -q "command_voice" "$WF" 2>/dev/null; then
    { echo ""; echo "# BoboVoice"; echo "binding_voice = <super> <shift> KEY_V"; echo "command_voice = bobo-voice --toggle"; } >> "$WF"
    ok "Super+Shift+V -> bobo-voice --toggle appended"
fi

update-desktop-database /usr/share/applications/ 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true

echo ""; log "=== Verification ==="
bobo-voice --version >/dev/null 2>&1 && ok "bobo-voice launches" || echo "  WARN bobo-voice --version"
log "BoboVoice installed. Super+Shift+V toggle; autostarts at login."
exit 0
