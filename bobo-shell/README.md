# BOBO Shell — Windows-like desktop shell

A lightweight Windows-style shell for BOBO OS, built on **GTK3 + gtk-layer-shell**
(renders reliably everywhere, including VMs — no GTK4/GL dependency). It replaces the
default top `wf-panel` with a bottom taskbar and adds the familiar Windows furniture.

## Components (`/usr/share/bobo-shell/`, launchers in `/usr/bin/`)

| Launcher | What it is |
|----------|-----------|
| `bobo-taskbar` | Bottom taskbar, **auto-hide** (slides up on hover). Start button, pinned quick-launch (Files, BOBO Browser, Terminal, BoboHub, Settings), system icons, **clock + date**. |
| `bobo-startmenu` | Start menu popup — search box + app grid (all `.desktop` apps) + user + power (Lock / Sign out / Restart / Shut down). Toggled by the Start button or **Ctrl+Esc**. |
| `bobo-sidebar` | Right vertical **action center** — clock, quick toggles (Wi-Fi, Bluetooth, Do-Not-Disturb, Night light), volume & brightness sliders, Personalize / All-settings. |
| `bobo-desktop` | Transparent background layer with **desktop icons** (This PC, Files, BOBO Browser, BoboHub, Recycle Bin + anything in `~/Desktop`). Double-click launches. |
| `bobo-cad` | **Ctrl+Alt+Del** security screen — Lock, Sign out, Task Manager, Restart, Shut down, Cancel. |
| `bobo-personalize` | Change **accent colour** (presets or custom), light/dark theme and taskbar auto-hide. Applies live. |

## Design tokens
Colours come from `CLAUDE.md`: background `#1a1a2e`, accent `#4a9eff`, taskbar height `48px`,
corner radius `8px`, font Inter. All live-configurable via `bobo-personalize`
(stored in `~/.config/bobo-shell/config.json`).

## Keybindings (merged into `wayfire.ini`)
- **Ctrl+Alt+Del** → security screen
- **Ctrl+Esc** → Start menu
- Taskbar Start button → Start menu; system icons / clock → action center

## Install
```bash
sudo bash install.sh
```
Installs the `gir1.2-gtklayershell-0.1` typelib, copies sources, creates launchers +
autostart entries, and rewires `wayfire.ini` (bottom taskbar + desktop icons instead of the
top panel). Integrated into the build via `compile-bobo-os.ps1` Step 3e.
