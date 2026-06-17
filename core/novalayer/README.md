# NovaLayer — Multi-Platform App Compatibility

NovaLayer is the BOBO OS compatibility daemon. It automatically detects the type of any application file and routes it to the correct runtime.

## Supported formats

| File type | Runtime | Notes |
|-----------|---------|-------|
| `.exe`, `.msi`, `.bat`, `.cmd` | Wine + DXVK | Per-app isolated Wine prefix |
| `.app`, `.dmg`, `.pkg` | Darling | macOS app compatibility |
| `.ipa` | QEMU aarch64 | iOS arm64 user-mode emulation |
| `.apk`, `.xapk` | Waydroid | Android container |
| `.flatpak`, `.AppImage`, `.deb`, `.rpm` | Native Linux | Direct install/exec |

## Components

- `novalayer-daemon.py` — D-Bus service (`os.bobo.NovaLayer`), inotify watcher, file type router
- `wine/wine-wrapper.sh` — Windows app launcher with DXVK, per-app prefix, first-run setup
- `darling/darling-wrapper.sh` — macOS app launcher (.app exec, .dmg mount, .pkg install)
- `ios-runtime/ios-launcher.py` — iOS app extractor and QEMU launcher with touch simulation
- `waydroid/waydroid-setup.sh` — Waydroid installation and initialisation
- `waydroid/waydroid-launcher.py` — GTK4 Android app grid and APK installer

## Usage

```bash
# Open any app file — NovaLayer auto-detects type
/usr/local/lib/bobo/core/novalayer/novalayer-daemon.py --open /path/to/app.exe

# Identify a file type
/usr/local/lib/bobo/core/novalayer/novalayer-daemon.py --identify /path/to/file

# Start the daemon (normally done by runit)
python3 novalayer-daemon.py

# Self-test
python3 novalayer-daemon.py --test
```

## D-Bus interface

Service: `os.bobo.NovaLayer`  
Object: `/os/bobo/NovaLayer`

| Method | Signature | Description |
|--------|-----------|-------------|
| `OpenFile(path)` | `s → s` | Open and route a file |
| `IdentifyFile(path)` | `s → s` | Return runtime name without opening |
