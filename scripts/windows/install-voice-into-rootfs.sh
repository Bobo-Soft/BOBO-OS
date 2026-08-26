#!/bin/bash
# Install BoboVoice into the existing rootfs via chroot (Faza 15). Lean by default.
R="/root/bobo-rootfs"
BOBO="/mnt/e/BOBO-OS"
[ -x "$R/sbin/init" ] || { echo "rootfs missing"; exit 1; }
mount -t proc proc "$R/proc" 2>/dev/null || true
mount --rbind /sys "$R/sys" 2>/dev/null || true
mount --rbind /dev "$R/dev" 2>/dev/null || true
cp -f /etc/resolv.conf "$R/etc/resolv.conf" 2>/dev/null || true
cleanup(){ for m in dev/pts dev sys proc; do umount -l "$R/$m" 2>/dev/null; done; }
trap cleanup EXIT

rm -rf "$R/tmp/bobo-voice-src"; mkdir -p "$R/tmp/bobo-voice-src"
cp -r "$BOBO/bobo-voice/." "$R/tmp/bobo-voice-src/" 2>/dev/null || true
echo "=== running install.sh in chroot (SKIP_HEAVY=${BOBO_VOICE_SKIP_HEAVY:-1}) ==="
chroot "$R" /bin/bash -c "export BOBO_VOICE_SKIP_HEAVY=${BOBO_VOICE_SKIP_HEAVY:-1}; cd /tmp/bobo-voice-src && bash install.sh"
rc=$?
rm -rf "$R/tmp/bobo-voice-src"
chroot "$R" /bin/bash -c "apt-get clean 2>/dev/null; rm -rf /tmp/* 2>/dev/null" || true
echo "=== rootfs size: $(du -sh $R 2>/dev/null | cut -f1) ==="
echo "install rc=$rc DONE"
