#!/bin/bash
# Note: no set -e here -- we handle errors explicitly so dracut pipe failures don't mask
# FIX 3: the rootfs lives on native ext4, not /mnt/e.
ROOTFS="/root/bobo-rootfs"
KERNEL_OUT="/mnt/e/BOBO-OS/build-output"
INITRD_OUT="$KERNEL_OUT/initrd-6.6-bobo.img"

# Skip if initrd already exists
if [ -s "$INITRD_OUT" ]; then
    echo "initrd already exists ($(du -sh $INITRD_OUT | cut -f1)) -- skipping."
    exit 0
fi

KVER=$(ls "$ROOTFS/lib/modules/" 2>/dev/null | head -1)
if [ -z "$KVER" ]; then
    KVER="6.6.87-bobo"
    echo "Warning: No modules dir found, using $KVER"
fi
echo "Generating initrd for kernel: $KVER"

# Install busybox-static unconditionally (needed for cpio fallback)
apt-get install -y busybox-static &>/dev/null || true

# --- Method 1: dracut with explicit module path ---
# FIX: dracut is DISABLED for the live ISO. It produces a hostonly/dmsquash initrd that does
# not match our CD -> squashfs -> overlay -> switch_root live boot. Always use the busybox
# live-boot initrd (Method 2) which is the proven, reproducible path.
DRACUT_OK=0
if false; then
    # Install kernel modules to host so dracut can find them
    MODULES_DIR="/lib/modules/$KVER"
    if [ ! -d "$MODULES_DIR" ] && [ -d "$ROOTFS/lib/modules/$KVER" ]; then
        cp -r "$ROOTFS/lib/modules/$KVER" "$MODULES_DIR" 2>/dev/null || true
        depmod "$KVER" 2>/dev/null || true
        echo "Copied kernel modules to host for dracut"
    fi
    dracut --force \
        --kver "$KVER" \
        --add "base" \
        --no-hostonly \
        --no-hostonly-cmdline \
        "$INITRD_OUT" 2>&1 | tail -10
    if [ -s "$INITRD_OUT" ]; then
        echo "[OK] initrd built with dracut"
        DRACUT_OK=1
    else
        echo "[WARN] dracut did not produce a file"
    fi
fi

# --- Method 2: minimal live-boot cpio initrd with busybox ---
if [ "$DRACUT_OK" -eq 0 ]; then
    echo "Building minimal live-boot initrd with busybox..."
    INITRD_TMP=$(mktemp -d)
    # SEPARATE top-level dirs in the (writable tmpfs) initramfs. NEVER use subdirs of the
    # read-only iso9660 mount (the old /mnt/squashfs + /mnt/rootfs bug -> "Read-only file system").
    mkdir -p "$INITRD_TMP"/{bin,sbin,etc,proc,sys,dev,run,cdrom,lower,upper,newroot}

    # Copy static busybox; applets are installed at boot via 'busybox --install'.
    BUSYBOX=$(command -v busybox 2>/dev/null || echo "/bin/busybox")
    cp "$BUSYBOX" "$INITRD_TMP/bin/busybox"
    chmod +x "$INITRD_TMP/bin/busybox"

    # Write the live-boot init. The kernel has squashfs/overlay/loop/iso9660/sr_mod/ahci
    # BUILT-IN (FIX 2), so no module loading is needed. Mount CD at /cdrom, loop-mount the
    # squashfs at /lower, overlay a tmpfs upper, then switch_root into systemd.
    cat > "$INITRD_TMP/init" <<'INITEOF'
#!/bin/busybox sh
/bin/busybox --install -s /bin
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
msg(){ echo "[bobo-live] $*"; }

mount -t proc     proc /proc 2>/dev/null
mount -t sysfs    sys  /sys  2>/dev/null
mount -t devtmpfs dev  /dev  2>/dev/null || mdev -s

msg "searching for BOBO OS live media (squashfs)..."
FOUND=""
i=0
while [ $i -lt 30 ]; do
  for d in /dev/sr0 /dev/sr1 /dev/cdrom /dev/sda /dev/sdb /dev/vda; do
    [ -b "$d" ] || continue
    mount -t iso9660 -o ro "$d" /cdrom 2>/dev/null || continue
    if [ -f /cdrom/live/filesystem.squashfs ]; then FOUND="$d"; break; fi
    umount /cdrom 2>/dev/null
  done
  [ -n "$FOUND" ] && break
  i=$((i+1)); sleep 1
done
if [ -z "$FOUND" ]; then msg "live media not found -> rescue shell"; exec /bin/busybox sh; fi
msg "live media on $FOUND"

if ! mount -t squashfs -o ro /cdrom/live/filesystem.squashfs /lower 2>/dev/null; then
  msg "squashfs mount failed -> rescue shell"; exec /bin/busybox sh
fi
mount -t tmpfs tmpfs /upper
mkdir -p /upper/up /upper/work
if ! mount -t overlay overlay -o lowerdir=/lower,upperdir=/upper/up,workdir=/upper/work /newroot 2>/dev/null; then
  msg "overlay failed -> binding squashfs read-only"; mount --bind /lower /newroot
fi
for fs in proc sys dev run; do mkdir -p /newroot/$fs; mount --move /$fs /newroot/$fs 2>/dev/null; done
if [ -x /newroot/sbin/init ]; then
  msg "handover to systemd (switch_root)"
  exec switch_root /newroot /sbin/init
fi
msg "no /sbin/init in root -> rescue shell"
exec switch_root /newroot /bin/sh
INITEOF
    chmod +x "$INITRD_TMP/init"

    # Pack into compressed cpio
    (cd "$INITRD_TMP" && find . | cpio -H newc -o 2>/dev/null | gzip -9 > "$INITRD_OUT")
    rm -rf "$INITRD_TMP"

    if [ -s "$INITRD_OUT" ]; then
        echo "initrd size: $(du -sh $INITRD_OUT | cut -f1)"
        echo "[OK] live-boot initrd generated"
    else
        echo "ERROR: initrd creation failed"
        exit 1
    fi
fi