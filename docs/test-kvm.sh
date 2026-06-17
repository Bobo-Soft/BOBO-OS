#!/bin/bash
echo "=== KVM availability ==="
ls -la /dev/kvm 2>/dev/null && echo "KVM device: OK" || echo "KVM device: NOT FOUND"
cat /proc/cpuinfo | grep -o -E "vmx|svm" | sort -u
echo ""
echo "=== QEMU version ==="
qemu-system-x86_64 --version 2>&1 | head -2
echo ""
echo "=== Test: QEMU with -serial stdio, redirect to file ==="
KERNEL="/mnt/e/BOBO-OS/build-output/vmlinuz-6.6-bobo"
INITRD="/mnt/e/BOBO-OS/build-output/initrd-6.6-bobo.img"
timeout 25 qemu-system-x86_64 \
    -m 512M \
    -kernel "$KERNEL" \
    -initrd "$INITRD" \
    -append "earlycon=uart8250,io,0x3f8,115200 console=ttyS0,115200n8 loglevel=8" \
    -display none \
    -serial stdio \
    -no-reboot > /tmp/qemu-stdio.log 2>&1
echo "Exit code: $?"
echo "Output size: $(wc -c < /tmp/qemu-stdio.log) bytes"
echo "--- Output ---"
cat /tmp/qemu-stdio.log | head -60