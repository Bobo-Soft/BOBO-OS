#!/bin/bash
KERNEL="/mnt/e/BOBO-OS/build-output/vmlinuz-6.6-bobo"
INITRD="/mnt/e/BOBO-OS/build-output/initrd-6.6-bobo.img"
ISO="/mnt/e/BOBO-OS/build-output/BOBO-OS-v1.0.iso"
SERIAL_LOG="/tmp/qemu-serial-boot.log"

echo "=== Test A: Direct kernel+initrd boot (file-based serial capture) ==="
rm -f "$SERIAL_LOG"

# Run QEMU in background, capture serial to file
qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -kernel "$KERNEL" \
    -initrd "$INITRD" \
    -append "earlycon=uart8250,io,0x3f8,115200 console=ttyS0,115200n8 boot=live loglevel=7 quiet" \
    -display none \
    -serial file:"$SERIAL_LOG" \
    -no-reboot 2>/tmp/qemu-stderr.log &
QEMU_PID=$!

echo "QEMU started (PID $QEMU_PID), waiting 20 seconds..."
sleep 20
kill $QEMU_PID 2>/dev/null
wait $QEMU_PID 2>/dev/null

echo ""
echo "--- QEMU stderr (errors) ---"
cat /tmp/qemu-stderr.log 2>/dev/null | head -5

echo ""
echo "--- Serial output (first 60 lines) ---"
if [ -s "$SERIAL_LOG" ]; then
    echo "Serial log size: $(wc -c < $SERIAL_LOG) bytes"
    head -60 "$SERIAL_LOG"
else
    echo "NO OUTPUT: serial log is empty or missing."
    echo "Checking if QEMU wrote anything at all..."
    ls -la "$SERIAL_LOG" 2>/dev/null || echo "File does not exist."
fi

echo ""
echo "=== Test B: ISO cdrom boot (file-based serial capture) ==="
rm -f "$SERIAL_LOG"

qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -cdrom "$ISO" \
    -boot d \
    -display none \
    -serial file:"$SERIAL_LOG" \
    -no-reboot 2>/tmp/qemu-stderr2.log &
QEMU_PID=$!

echo "QEMU started (PID $QEMU_PID), waiting 20 seconds..."
sleep 20
kill $QEMU_PID 2>/dev/null
wait $QEMU_PID 2>/dev/null

echo ""
echo "--- ISO boot QEMU stderr ---"
cat /tmp/qemu-stderr2.log 2>/dev/null | head -5

echo ""
echo "--- ISO boot Serial output (first 40 lines) ---"
if [ -s "$SERIAL_LOG" ]; then
    echo "Serial log size: $(wc -c < $SERIAL_LOG) bytes"
    head -40 "$SERIAL_LOG"
else
    echo "NO OUTPUT: serial log is empty."
fi

echo ""
echo "=== All tests complete ==="