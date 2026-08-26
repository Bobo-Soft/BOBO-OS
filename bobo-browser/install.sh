#!/bin/bash
# BOBO Browser installer — native WebKit2GTK browser for BOBO OS.
# Self-locating; safe to run inside the build chroot or on a live system.
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARE="/usr/share/bobo-browser"
BIN="/usr/bin"
APPDIR="/usr/share/applications"

echo "== BOBO Browser install =="

# 1) Dependencies: WebKit2GTK 4.1 (GTK3) introspection + runtime.
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y 2>/dev/null || true
    apt-get install -y --no-install-recommends \
        gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0 python3-gi gir1.2-gtk-3.0 \
        2>/dev/null || echo "  [warn] some deps unavailable"
fi

# 2) Sources
mkdir -p "$SHARE"
cp -f "$HERE/bobo-browser.py" "$HERE/newtab.html" "$SHARE/"
[ -f "$HERE/bobo-browser.svg" ] && install -Dm644 "$HERE/bobo-browser.svg" \
    /usr/share/icons/hicolor/scalable/apps/bobo-browser.svg || true

# 3) Launcher
cat > "$BIN/bobo-browser" <<EOF
#!/bin/bash
exec python3 "$SHARE/bobo-browser.py" "\$@"
EOF
chmod 0755 "$BIN/bobo-browser"

# 4) .desktop (also the http/https handler so links open in BOBO Browser)
mkdir -p "$APPDIR"
cat > "$APPDIR/bobo-browser.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=BOBO Browser
GenericName=Web Browser
Comment=Private, lightweight browser for BOBO OS (DuckDuckGo default)
Exec=bobo-browser %U
Icon=bobo-browser
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;x-scheme-handler/about;x-scheme-handler/unknown;
StartupNotify=true
EOF

# 5) Make it the default web browser
update-desktop-database "$APPDIR" 2>/dev/null || true
if command -v update-alternatives >/dev/null 2>&1; then
    update-alternatives --install /usr/bin/x-www-browser x-www-browser "$BIN/bobo-browser" 200 2>/dev/null || true
    update-alternatives --set x-www-browser "$BIN/bobo-browser" 2>/dev/null || true
fi
# default handler via mimeapps (system-wide)
MAPPS="$APPDIR/mimeapps.list"
touch "$MAPPS"
grep -q '^\[Default Applications\]' "$MAPPS" || echo '[Default Applications]' >> "$MAPPS"
for m in text/html x-scheme-handler/http x-scheme-handler/https x-scheme-handler/about; do
    grep -q "^$m=" "$MAPPS" && sed -i "s#^$m=.*#$m=bobo-browser.desktop#" "$MAPPS" \
        || sed -i "/^\[Default Applications\]/a $m=bobo-browser.desktop" "$MAPPS"
done
xdg-settings set default-web-browser bobo-browser.desktop 2>/dev/null || true

# 6) Compile check
python3 -m py_compile "$SHARE/bobo-browser.py" && echo "  [ok] python compiles"
echo "== BOBO Browser installed =="
