#!/bin/bash
set -e
ISO_TREE="/mnt/e/BOBO-OS/build-output/iso-tree"
ISO_OUT="/mnt/e/BOBO-OS/build-output/BOBO-OS-v1.0.iso"
EFI_IMG="/mnt/e/BOBO-OS/build-output/efi.img"

echo "Regenerating ISO with fixed ASCII grub.cfg..."

# Copy efi.img into ISO tree
if [ -s "$EFI_IMG" ]; then
    cp "$EFI_IMG" "$ISO_TREE/boot/efi.img"
fi

HAS_BIOS=0; [ -s "$ISO_TREE/boot/grub/bios.img" ] && HAS_BIOS=1
HAS_EFI=0;  [ -s "$ISO_TREE/boot/efi.img" ] && HAS_EFI=1
echo "BIOS=$HAS_BIOS EFI=$HAS_EFI"

if [ "$HAS_BIOS" -eq 1 ] && [ "$HAS_EFI" -eq 1 ]; then
    xorriso -as mkisofs -iso-level 3 -full-iso9660-filenames \
        -volid "BOBO_OS_1_0" -appid "BOBO OS 1.0.0" \
        -publisher "BOBO OS" -preparer "BOBO OS Build System" \
        -eltorito-boot boot/grub/bios.img \
            -no-emul-boot -boot-load-size 4 -boot-info-table \
        -eltorito-alt-boot -e boot/efi.img -no-emul-boot \
        -isohybrid-gpt-basdat \
        -output "$ISO_OUT" "$ISO_TREE" 2>&1
elif [ "$HAS_BIOS" -eq 1 ]; then
    xorriso -as mkisofs -iso-level 3 -full-iso9660-filenames \
        -volid "BOBO_OS_1_0" -appid "BOBO OS 1.0.0" \
        -publisher "BOBO OS" -preparer "BOBO OS Build System" \
        -eltorito-boot boot/grub/bios.img \
            -no-emul-boot -boot-load-size 4 -boot-info-table \
        -output "$ISO_OUT" "$ISO_TREE" 2>&1
else
    xorriso -as mkisofs -iso-level 3 -full-iso9660-filenames \
        -volid "BOBO_OS_1_0" \
        -output "$ISO_OUT" "$ISO_TREE" 2>&1
fi

SIZE=$(du -sh "$ISO_OUT" | cut -f1)
SHA256=$(sha256sum "$ISO_OUT" | cut -d' ' -f1)
echo "$SHA256  BOBO-OS-v1.0.iso" > "/mnt/e/BOBO-OS/build-output/BOBO-OS-v1.0.iso.sha256"
echo ""
echo "[OK] ISO regenerated: $SIZE  SHA256: ${SHA256:0:16}..."