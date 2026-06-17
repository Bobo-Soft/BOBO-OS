#!/bin/bash
KERNEL="/mnt/e/BOBO-OS/build-output/vmlinuz-6.6-bobo"
INITRD="/mnt/e/BOBO-OS/build-output/initrd-6.6-bobo.img"
ISO="/mnt/e/BOBO-OS/build-output/BOBO-OS-v1.0.iso"

echo "=== BOBO OS Boot Verification ==="
echo ""

# 1. Verify artifacts
echo "[1] Artifact check:"
[ -s "$KERNEL" ] && echo "  vmlinuz: OK ($(du -sh $KERNEL | cut -f1))" || echo "  vmlinuz: MISSING!"
[ -s "$INITRD" ] && echo "  initrd:  OK ($(du -sh $INITRD | cut -f1))" || echo "  initrd:  MISSING!"
[ -s "$ISO"    ] && echo "  ISO:     OK ($(du -sh $ISO | cut -f1))"    || echo "  ISO:     MISSING!"

# 2. Verify squashfs
echo ""
echo "[2] Squashfs check:"
SQFS="/mnt/e/BOBO-OS/build-output/iso-tree/live/filesystem.squashfs"
if [ -s "$SQFS" ]; then
    file "$SQFS"
    unsquashfs -s "$SQFS" 2>/dev/null | head -8 || echo "  (unsquashfs not available for stat)"
else
    echo "  squashfs: MISSING!"
fi

# 3. Verify initrd content
echo ""
echo "[3] Initrd check:"
INITRD_TYPE=$(file "$INITRD" | cut -d: -f2)
echo "  Type: $INITRD_TYPE"
echo "  Init script contents:"
zcat "$INITRD" 2>/dev/null | cpio -t 2>/dev/null | grep -E "^(init|sbin/init|bin/busybox|lib/modules|proc|sys|dev)" | head -20 || \
  (zcat "$INITRD" | cpio -t | head -20)

# 4. Quick kernel boot test (direct, no ISO, no GRUB)
echo ""
echo "[4] Direct kernel boot test (15 seconds, KVM)..."
timeout 20 qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -kernel "$KERNEL" \
    -initrd "$INITRD" \
    -append "earlycon=uart8250,io,0x3f8,115200 console=ttyS0,115200n8 boot=live loglevel=6" \
    -display none \
    -serial stdio \
    -no-reboot 2>&1 | head -80
echo ""
echo "[4] Direct kernel boot test: DONE"

# 5. ISO cdrom boot test (20 seconds, BIOS)
echo ""
echo "[5] ISO cdrom boot test (20 seconds, BIOS)..."
timeout 25 qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -cdrom "$ISO" \
    -boot d \
    -display none \
    -serial stdio \
    -no-reboot 2>&1 | head -40
echo ""
echo "[5] ISO cdrom boot test: DONE"

echo ""
echo "=== Verification complete ==="
