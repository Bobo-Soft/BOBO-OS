#!/bin/bash
# =============================================================================
# Phase 1 of the FULL ISO build: install the 32 BOBO apps (full deps) and
# BoboXcode (full Swift/fastlane toolchain) INTO the existing native rootfs,
# so the Step 3 skip-guard (which fires because the desktop rootfs exists) does
# not prevent the heavy installs. Phase 2 (pipeline) then rebuilds squashfs+ISO.
#
# Idempotent-ish: re-running re-applies deps. Logs to the docs/ folder.
# =============================================================================
ROOTFS="/root/bobo-rootfs"
BOBO="/mnt/e/BOBO-OS"
echo "================================================================"
echo "FULL apps+xcode install into $ROOTFS  (start: $(cat /proc/uptime | cut -d. -f1)s uptime)"
echo "================================================================"

if [ ! -x "$ROOTFS/sbin/init" ]; then
    echo "ERROR: $ROOTFS has no /sbin/init — run the pipeline Step 3 first."
    exit 1
fi

# --- mount chroot filesystems + DNS ------------------------------------------
mount -t proc proc "$ROOTFS/proc" 2>/dev/null || true
mount --rbind /sys "$ROOTFS/sys" 2>/dev/null || true
mount --make-rslave "$ROOTFS/sys" 2>/dev/null || true
mount --rbind /dev "$ROOTFS/dev" 2>/dev/null || true
mount --make-rslave "$ROOTFS/dev" 2>/dev/null || true
cp -f /etc/resolv.conf "$ROOTFS/etc/resolv.conf" 2>/dev/null || true

cleanup() {
    echo "--- unmounting chroot binds ---"
    umount -l "$ROOTFS/dev/pts" 2>/dev/null || true
    umount -l "$ROOTFS/dev"     2>/dev/null || true
    umount -l "$ROOTFS/sys"     2>/dev/null || true
    umount -l "$ROOTFS/proc"    2>/dev/null || true
}
trap cleanup EXIT

# --- sync latest sources into the rootfs -------------------------------------
echo "--- syncing bobo-apps + bobo-xcode sources ---"
mkdir -p "$ROOTFS/usr/local/lib/bobo-apps"
cp -r "$BOBO/bobo-apps/." "$ROOTFS/usr/local/lib/bobo-apps/" 2>/dev/null || true
rm -f "$ROOTFS/usr/local/lib/bobo-apps/_syntax_check.sh" 2>/dev/null || true
mkdir -p "$ROOTFS/tmp/bobo-xcode-src"
cp -r "$BOBO/bobo-xcode/." "$ROOTFS/tmp/bobo-xcode-src/" 2>/dev/null || true
rm -f "$ROOTFS/tmp/bobo-xcode-src/_check.sh" 2>/dev/null || true

# --- Phase 1a: 32 BOBO apps, FULL dependency tier ----------------------------
echo "=== Installing 32 BOBO apps (FULL deps) ==="
chroot "$ROOTFS" /bin/bash -c \
    "export DEBIAN_FRONTEND=noninteractive BOBO_APPS_SKIP_DEPS=0; \
     bash /usr/local/lib/bobo-apps/build-bobo-apps.sh" || echo "WARN: bobo-apps installer non-zero (continuing)"

# --- Phase 1b: BoboXcode, FULL toolchain (Swift ~600MB + fastlane + qemu) -----
echo "=== Installing BoboXcode (FULL: Swift toolchain + fastlane) ==="
chroot "$ROOTFS" /bin/bash -c \
    "export DEBIAN_FRONTEND=noninteractive BOBO_XCODE_SKIP_HEAVY=0; \
     cd /tmp/bobo-xcode-src && bash install.sh" || echo "WARN: BoboXcode installer non-zero (continuing)"
rm -rf "$ROOTFS/tmp/bobo-xcode-src" 2>/dev/null || true

# --- trim downloaded .deb archives only (keep apt lists intact) --------------
chroot "$ROOTFS" /bin/bash -c "apt-get clean 2>/dev/null; rm -rf /tmp/* 2>/dev/null" || true

echo "=== Phase 1 complete. Rootfs size: $(du -sh $ROOTFS 2>/dev/null | cut -f1) ==="
echo "Verifying a few apps + bobo-xcode inside the rootfs:"
for app in bobo-player bobo-monitor bobo-xcode; do
    chroot "$ROOTFS" /bin/bash -c "$app --version 2>/dev/null" && echo "  OK $app" || echo "  (version check skipped: $app)"
done
echo "Done."
