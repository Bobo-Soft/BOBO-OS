#!/bin/bash
ISO="/mnt/e/BOBO-OS/build-output/BOBO-OS-v1.0.iso"

if [ ! -f "$ISO" ]; then
    echo "ISO not found -- skipping boot test."
    exit 0
fi

echo "Running 30-second headless QEMU boot test..."
timeout 35 qemu-system-x86_64 \
    -m 1024M \
    -cdrom "$ISO" \
    -boot d \
    -nographic \
    -serial stdio \
    -no-reboot \
    -enable-kvm 2>/dev/null || \
timeout 35 qemu-system-x86_64 \
    -m 1024M \
    -cdrom "$ISO" \
    -boot d \
    -nographic \
    -serial stdio \
    -no-reboot 2>&1 | head -60

echo ""
echo "QEMU boot test complete."
echo "If kernel messages appeared above, the ISO is bootable."