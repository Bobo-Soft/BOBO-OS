#!/bin/bash
# =============================================================================
# Faza 13.5 - Install NovaLayer runtimes into the BOBO OS rootfs (chroot).
# Wine+DXVK (Windows), Waydroid (Android), qemu-user-static (iOS ARM),
# Flatpak (Linux), Darling informational wrapper (macOS - no apt package).
# Read-only elsewhere; touches only the rootfs. Per-package fallback, verbose.
# =============================================================================
R="/root/bobo-rootfs"
CH() { chroot "$R" /bin/bash -c "$1"; }

echo "################ NovaLayer runtimes install ($(date '+%H:%M:%S' 2>/dev/null || echo now)) ################"
[ -x "$R/sbin/init" ] || { echo "ERROR: rootfs missing"; exit 1; }

# mount + DNS
mount -t proc proc "$R/proc" 2>/dev/null || true
mount --rbind /sys "$R/sys" 2>/dev/null || true
mount --rbind /dev "$R/dev" 2>/dev/null || true
cp -f /etc/resolv.conf "$R/etc/resolv.conf" 2>/dev/null || true
export DEBIAN_FRONTEND=noninteractive
cleanup(){ for m in dev/pts dev sys proc; do umount -l "$R/$m" 2>/dev/null; done; }
trap cleanup EXIT

echo "==== enable i386 + apt update ===="
CH "dpkg --add-architecture i386"
CH "apt-get update -qq" 2>&1 | tail -3

install_set() {
  local label="$1"; shift
  echo "==== $label ===="
  CH "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $*" 2>&1 | tail -4 || {
    echo "  bulk failed -> per-package fallback"
    for p in $*; do CH "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $p" >/dev/null 2>&1 && echo "  ok $p" || echo "  SKIP $p"; done
  }
}

# --- Wine (Windows) ---
install_set "Wine + Vulkan" wine wine64 winetricks libvulkan1 mesa-vulkan-drivers
install_set "Wine 32-bit (i386)" wine32:i386 libvulkan1:i386 mesa-vulkan-drivers:i386

# --- DXVK (DirectX -> Vulkan): download on host, extract into rootfs ---
echo "==== DXVK ===="
DXVK_VERSION="2.3.1"
if [ ! -d "$R/opt/dxvk-${DXVK_VERSION}" ]; then
  if wget -q "https://github.com/doitsujin/dxvk/releases/download/v${DXVK_VERSION}/dxvk-${DXVK_VERSION}.tar.gz" -O /tmp/dxvk.tar.gz; then
    tar xzf /tmp/dxvk.tar.gz -C "$R/opt/" && ln -sfn "/opt/dxvk-${DXVK_VERSION}" "$R/opt/dxvk" && echo "  DXVK ${DXVK_VERSION} extracted"
    rm -f /tmp/dxvk.tar.gz
  else echo "  DXVK download failed (install later)"; fi
else echo "  DXVK already present"; fi

# --- Waydroid (Android): try noble universe, else official repo ---
echo "==== Waydroid ===="
if ! CH "apt-get install -y --no-install-recommends waydroid" 2>&1 | tail -2 | grep -q .; then :; fi
if ! CH "command -v waydroid >/dev/null 2>&1"; then
  echo "  not in universe -> adding official repo"
  CH "apt-get install -y --no-install-recommends curl ca-certificates >/dev/null 2>&1"
  CH "curl -s https://repo.waydro.id/waydroid.gpg --output /usr/share/keyrings/waydroid.gpg 2>/dev/null"
  CH "echo 'deb [signed-by=/usr/share/keyrings/waydroid.gpg] https://repo.waydro.id/ noble main' > /etc/apt/sources.list.d/waydroid.list"
  CH "apt-get update -qq >/dev/null 2>&1; apt-get install -y --no-install-recommends waydroid" 2>&1 | tail -3
fi

# --- qemu-user-static (iOS ARM sandbox) ---
install_set "qemu-user-static (iOS ARM)" qemu-user-static binfmt-support
CH "update-binfmts --enable qemu-aarch64 2>/dev/null || true"

# --- Flatpak (Linux) ---
install_set "Flatpak" flatpak
CH "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo 2>/dev/null || true"

# --- Darling (macOS): informational wrapper (no apt package; full port is huge) ---
echo "==== Darling wrapper (macOS placeholder) ===="
cat > "$R/usr/bin/darling" <<'DARLING_EOF'
#!/bin/bash
# BOBO OS - Darling (macOS compatibility) is not yet a full runtime in this build.
echo "Darling (compatibilitate macOS) este in curs de integrare."
echo "Aplicatiile .app / .dmg vor fi suportate intr-o versiune viitoare."
exit 0
DARLING_EOF
chmod +x "$R/usr/bin/darling"
echo "  Darling informational wrapper installed"

# --- trim apt archives (keep lists) ---
CH "apt-get clean 2>/dev/null; rm -rf /tmp/* 2>/dev/null" || true

echo ""
echo "################ NovaLayer Runtime Audit ################"
echo -n "Wine:              "; CH "wine --version 2>/dev/null" || echo "MISSING"
echo -n "Wine64:            "; CH "command -v wine64 >/dev/null 2>&1 && echo present || echo MISSING"
echo -n "winetricks:        "; CH "command -v winetricks >/dev/null 2>&1 && echo present || echo MISSING"
echo -n "DXVK:              "; [ -e "$R/opt/dxvk" ] && echo "present (/opt/dxvk)" || echo "MISSING"
echo -n "Waydroid:          "; CH "command -v waydroid >/dev/null 2>&1 && waydroid --version 2>/dev/null || echo MISSING"
echo -n "qemu-aarch64-stat: "; CH "command -v qemu-aarch64-static >/dev/null 2>&1 && echo present || echo MISSING"
echo -n "Flatpak:           "; CH "flatpak --version 2>/dev/null" || echo "MISSING"
echo -n "Darling:           "; CH "command -v darling >/dev/null 2>&1 && echo 'wrapper (placeholder)' || echo MISSING"
echo -n "rootfs size:       "; du -sh "$R" 2>/dev/null | cut -f1
echo "DONE"
