# Fresh FULL build wrapper: wipes the rootfs so Step 3 re-debootstraps cleanly,
# sets full-dependency mode for both the 32 apps and BoboXcode, then runs the
# canonical pipeline. Kernel/initrd are cached so Steps 1/2/4 skip.
$ErrorActionPreference = "Continue"
$env:BOBO_APPS_SKIP_DEPS  = "0"   # full deps for the 32 BOBO apps
$env:BOBO_XCODE_SKIP_HEAVY = "0"  # full Swift/fastlane/qemu toolchain for BoboXcode

Write-Host "=== FRESH FULL BUILD ===" -ForegroundColor Cyan
Write-Host "Wiping /root/bobo-rootfs to force a clean Step 3 debootstrap..." -ForegroundColor Cyan
wsl -d Ubuntu-24.04 -u root -- bash -c "for m in dev/pts dev sys proc; do umount -l /root/bobo-rootfs/`$m 2>/dev/null; done; rm -rf /root/bobo-rootfs /root/_aptgate"

Write-Host "Launching pipeline (compile-bobo-os.ps1) in full mode..." -ForegroundColor Cyan
& "E:\BOBO-OS\scripts\windows\compile-bobo-os.ps1"
Write-Host "=== run-full-build.ps1 finished ===" -ForegroundColor Green
