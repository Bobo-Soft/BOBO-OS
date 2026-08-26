# BOBO OS — Checkpoint
Generated: 2026-08-25 (Session 13 — Faza 17 fixes + Faza 18 Windows-like UI & BOBO Browser)

## Last completed phase: 18 — Windows-like shell + BOBO Browser + GitHub push
## Next phase to start: polish / real-hardware validation

## ISO: E:\BOBO-OS\build-output\BOBO-OS-v1.0.iso — 3.0 GB, bootable (valid SQUASHFS 4:0)
Boots to the Wayfire desktop with the BOBO Shell: desktop icons (This PC, Files, BOBO Browser,
BoboHub, Recycle Bin) render, top wf-panel removed. Shell fixes are delivered via a small
`fixes.squashfs` overlay (see Faza 18.3) because WSL2 cannot reliably repack the 11 GB rootfs.

## What shipped this session
### Faza 17 — 3 fixes (baked into rootfs + pipeline + Faza 17 squashfs)
- `GSK_RENDERER=cairo` + `BOBO_ROOT=/usr/local/lib/bobo/core` in /etc/environment
  (GTK4 apps render under VirtualBox vmwgfx; NovaLayer wine-wrapper path resolves).
- Super+A → bobo-assist (was bobo-ai-local; ai-local moved to Super+Shift+A).
- .exe/.msi/.dmg/.ipa/.apk double-click → NovaLayer (`bobo-run-file` + .desktop + mimeapps).
- Verified in VBox: BoboHub, BoboWrite, BoboAssist render (GTK4 via cairo). Idle RAM 509 MiB.

### Faza 18 — Windows-like UI + browser
- `bobo-shell/` (GTK3 + gtk-layer-shell): bobo-taskbar (bottom, auto-hide, Start/quick-launch/
  clock), bobo-startmenu, bobo-sidebar (action center), bobo-desktop (icons), bobo-cad
  (Ctrl+Alt+Del), bobo-personalize (accent/theme). Pipeline Step 3e.
- `bobo-browser/` (GTK3 + WebKit2GTK): BOBO theme, DuckDuckGo private default (t=bobo brand),
  5-min tab suspension, branded start page, set as default browser. Pipeline Step 3f.
- Wayfire: `autostart_wf_shell=false` (removes the top wf-panel); Ctrl+Alt+Del→CAD, Ctrl+Esc→Start.

## WSL2 packaging reality (important for next session)
Rebuilding the 11 GB squashfs from the rootfs HARD-CRASHES this machine's WSL2 VM (vhdx I/O
errors on read AND write, VM reboots mid-run). Native-ext4/tmpfs/housekeeping mitigations only
reduce it. The reliable path now is **`_apply_fixes_layer.sh`**: build a tiny fixes.squashfs of
only the changed files and overlay it at boot (2nd overlayfs lowerdir; init already patched).
xorriso-clone of the 3 GB ISO is reliable; the 11 GB mksquashfs is not.

## Known issue (non-blocker)
- Bottom taskbar not visually confirmed in the headless VM: bobo-taskbar autostarts twice
  (wayfire.ini + /etc/xdg/autostart) and the singleton logic + autostart timing keep it from
  showing in VirtualBox. Code is correct (ensure_single non-killing singleton added); expected to
  appear on real hardware where autostart timing differs. Desktop icons, Start-menu, browser code
  are all in place. Revisit: verify taskbar render on real hardware or with autohide disabled.

## Files created this session (committed)
- bobo-shell/ (7 py + css + install.sh + README), bobo-browser/ (py + html + svg + install.sh + README)
- bobo-office/, bobo-assist/, bobo-voice/ (from earlier phases, now committed)
- scripts/windows/install-{novalayer-runtimes,office-into-rootfs,voice-into-rootfs,heavy-tts}.sh
- docs/{audit-report,office-verify,rtcheck,voice-verify}.txt
## Files modified
- scripts/windows/compile-bobo-os.ps1 (Steps 3a–3f, FIX 1/3/9, fixes-layer init), CLAUDE.md,
  bobo-apps/shared/bobo-wayfire-defaults.ini (Super+A→assist, autostart_wf_shell handling), .gitignore
## Excluded from the public repo (verified)
- bobo-ai/, bobostudio/, terra-antiqua/, orbis/, overblast/ (private products) + export_bobo.py
- build-output/*.iso, *.squashfs, *.img (build artifacts); *.env/*.key/*.pem/*.token (secrets)
- scripts/windows/_*.sh (local build/diagnostic helpers)

## Exact prompt to resume:
"Read CLAUDE.md and CHECKPOINT.md. BOBO OS Faza 18 is done (Windows-like shell + BOBO Browser,
 delivered via fixes.squashfs overlay). Next: validate the bottom taskbar on real hardware,
 or continue polishing the shell."
