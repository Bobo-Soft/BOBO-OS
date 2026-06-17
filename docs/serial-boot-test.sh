#!/bin/bash
KERNEL="/mnt/e/BOBO-OS/build-output/vmlinuz-6.6-bobo"
INITRD="/mnt/e/BOBO-OS/build-output/initrd-6.6-bobo.img"
ISO="/mnt/e/BOBO-OS/build-output/BOBO-OS-v1.0.iso"
SERIAL_LOG="/tmp/qemu-serial-test.log"

echo "=== BOBO OS Serial Boot Verification ==="
echo "Kernel: $(du -sh $KERNEL | cut -f1)  Initrd: $(du -sh $INITRD | cut -f1)  ISO: $(du -sh $ISO | cut -f1)"
echo ""

# Test A: Direct kernel boot with serial file capture
echo "[A] Direct kernel+initrd boot (25s serial capture)..."
rm -f "$SERIAL_LOG"
qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -kernel "$KERNEL" \
    -initrd "$INITRD" \
    -append "earlycon=uart8250,io,0x3f8,115200 console=ttyS0,115200n8 boot=live loglevel=7" \
    -display none \
    -serial file:"$SERIAL_LOG" \
    -no-reboot 2>/tmp/qemu-err-a.log &
QEMU_PID=$!
sleep 20
kill $QEMU_PID 2>/dev/null; wait $QEMU_PID 2>/dev/null

echo "Serial output: $(wc -c < $SERIAL_LOG 2>/dev/null || echo 0) bytes"
if [ -s "$SERIAL_LOG" ]; then
    echo "--- First 50 lines ---"
    head -50 "$SERIAL_LOG"
    echo "--- [OK] Serial output captured ---"
else
    echo "[WARN] No serial output - QEMU stderr:"
    cat /tmp/qemu-err-a.log | head -5
fi

echo ""
echo "[B] ISO cdrom boot test (20s serial capture)..."
rm -f "$SERIAL_LOG"
qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -cdrom "$ISO" \
    -boot d \
    -display none \
    -serial file:"$SERIAL_LOG" \
    -no-reboot 2>/tmp/qemu-err-b.log &
QEMU_PID=$!
sleep 20
kill $QEMU_PID 2>/dev/null; wait $QEMU_PID 2>/dev/null

echo "ISO boot serial: $(wc -c < $SERIAL_LOG 2>/dev/null || echo 0) bytes"
if [ -s "$SERIAL_LOG" ]; then
    echo "--- First 30 lines ---"
    head -30 "$SERIAL_LOG"
    echo "--- [OK] ISO serial output captured ---"
else
    echo "[WARN] No ISO serial output"
    cat /tmp/qemu-err-b.log | head -5
fi

echo ""
echo "=== Verification complete ==="