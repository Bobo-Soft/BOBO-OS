#!/bin/bash
# Install Bobo Office + BoboAssist into the existing rootfs via chroot (Faza 14).
# Lean by default (SKIP_HEAVY=1): apps + deps, no TTS/model pull.
R="/root/bobo-rootfs"
BOBO="/mnt/e/BOBO-OS"
[ -x "$R/sbin/init" ] || { echo "rootfs missing"; exit 1; }
mount -t proc proc "$R/proc" 2>/dev/null || true
mount --rbind /sys "$R/sys" 2>/dev/null || true
mount --rbind /dev "$R/dev" 2>/dev/null || true
cp -f /etc/resolv.conf "$R/etc/resolv.conf" 2>/dev/null || true
cleanup(){ for m in dev/pts dev sys proc; do umount -l "$R/$m" 2>/dev/null; done; }
trap cleanup EXIT

echo "=== copying sources ==="
rm -rf "$R/tmp/bobo-office-src" "$R/tmp/bobo-assist-src"
mkdir -p "$R/tmp/bobo-office-src" "$R/tmp/bobo-assist-src"
cp -r "$BOBO/bobo-office/." "$R/tmp/bobo-office-src/" 2>/dev/null || true
cp -r "$BOBO/bobo-assist/." "$R/tmp/bobo-assist-src/" 2>/dev/null || true

echo "=== running install.sh in chroot (SKIP_HEAVY=${BOBO_OFFICE_SKIP_HEAVY:-1}) ==="
chroot "$R" /bin/bash -c "export BOBO_OFFICE_SKIP_HEAVY=${BOBO_OFFICE_SKIP_HEAVY:-1}; cd /tmp/bobo-office-src && bash install.sh"
rc=$?
rm -rf "$R/tmp/bobo-office-src" "$R/tmp/bobo-assist-src"
chroot "$R" /bin/bash -c "apt-get clean 2>/dev/null; rm -rf /tmp/* 2>/dev/null" || true
echo "=== rootfs size: $(du -sh $R 2>/dev/null | cut -f1) ==="
echo "install rc=$rc  DONE"
