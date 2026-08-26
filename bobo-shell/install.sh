#!/bin/bash
# BOBO Shell installer — Windows-like desktop shell (GTK3 + gtk-layer-shell).
# Self-locating; safe to run inside the build chroot or on a live system.
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARE="/usr/share/bobo-shell"
BIN="/usr/bin"

echo "== BOBO Shell install =="

# 1) Dependencies. GTK3 + PyGObject are already in the desktop stack; we add the
#    gtk-layer-shell *typelib* (the .so ships already, only the GIR is missing) and
#    a couple of optional helpers used by the sidebar sliders.
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y 2>/dev/null || true
    apt-get install -y --no-install-recommends \
        gir1.2-gtklayershell-0.1 python3-gi gir1.2-gtk-3.0 \
        brightnessctl 2>/dev/null || echo "  [warn] some optional deps unavailable"
fi

# 2) Copy the shell sources
mkdir -p "$SHARE"
cp -f "$HERE"/shell_common.py "$HERE"/style.css "$SHARE"/
for f in taskbar startmenu sidebar desktop cad personalize; do
    cp -f "$HERE/bobo-$f.py" "$SHARE/bobo-$f.py"
done

# 3) Launchers in /usr/bin
for f in taskbar startmenu sidebar desktop cad personalize; do
    cat > "$BIN/bobo-$f" <<EOF
#!/bin/bash
exec python3 "$SHARE/bobo-$f.py" "\$@"
EOF
    chmod 0755 "$BIN/bobo-$f"
done

# 4) .desktop entries (Start menu / launchers)
APPDIR="/usr/share/applications"
mkdir -p "$APPDIR"
cat > "$APPDIR/bobo-personalize.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Personalization
Comment=Change accent colour, theme and taskbar behaviour
Exec=bobo-personalize
Icon=preferences-desktop-theme
Categories=Settings;DesktopSettings;
EOF

# 5) Autostart: replace the top wf-panel with the Windows-like bottom taskbar +
#    desktop icons; keep the wallpaper (wf-background). Runs for every session.
mkdir -p /etc/xdg/autostart
for entry in \
  "bobo-desktop|BOBO Desktop Icons|bobo-desktop" \
  "bobo-taskbar|BOBO Taskbar|bobo-taskbar"; do
    id="${entry%%|*}"; rest="${entry#*|}"; name="${rest%%|*}"; cmd="${rest##*|}"
    cat > "/etc/xdg/autostart/$id.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$name
Exec=$cmd
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF
done

# 6) Wire keybindings + autostart into the user's wayfire.ini and the shared defaults.
wire_wayfire() {
    local WF="$1"; [ -f "$WF" ] || return 0
    # --- [autostart]: drop wf-panel + kitty autoloads, add taskbar + desktop icons ---
    if grep -q '^\[autostart\]' "$WF"; then
        sed -i -E '/^[0-9]*_?panel[[:space:]]*=[[:space:]]*wf-panel/d' "$WF"
        sed -i -E '/^[0-9]*_?terminal[[:space:]]*=[[:space:]]*kitty/d' "$WF"
        if ! grep -q 'bobo-taskbar' "$WF"; then
            sed -i -E '/^\[autostart\]/a 8_bobo_desktop = bobo-desktop\n9_bobo_taskbar = bobo-taskbar' "$WF"
        fi
    fi
    # --- [command]: Ctrl+Alt+Del -> security screen, Ctrl+Esc -> Start menu ---
    if grep -q '^\[command\]' "$WF" && ! grep -q 'command_cad' "$WF"; then
        sed -i -E '/^\[command\]/a binding_cad   = <ctrl> <alt> KEY_DELETE\ncommand_cad   = bobo-cad\nbinding_start = <ctrl> KEY_ESC\ncommand_start = bobo-startmenu' "$WF"
    fi
}
wire_wayfire "/home/bobo/.config/wayfire.ini"
chroot_owner=""
if id bobo >/dev/null 2>&1; then chown bobo:bobo /home/bobo/.config/wayfire.ini 2>/dev/null || true; fi

# Also add the bindings to the shared defaults so future merges keep them.
DEF="/etc/bobo-wayfire-defaults.ini"
if [ -f "$DEF" ] && ! grep -q 'command_cad' "$DEF"; then
    printf 'binding_cad   = <ctrl> <alt> KEY_DELETE\ncommand_cad   = bobo-cad\nbinding_start = <ctrl> KEY_ESC\ncommand_start = bobo-startmenu\n' >> "$DEF"
fi

# 7) Byte-compile check
python3 -m py_compile "$SHARE"/*.py && echo "  [ok] python compiles"

echo "== BOBO Shell installed =="
