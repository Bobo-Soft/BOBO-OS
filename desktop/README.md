# BOBO OS Desktop Environment

The BOBO OS desktop is built on Wayland (Wayfire compositor) with a GTK4/Adwaita UI stack.

## Components

```
desktop/
├── window-manager/
│   └── wayfire.ini          ← Wayfire compositor config (plugins, keybindings, autostart)
├── taskbar/
│   ├── taskbar.py           ← GTK4 taskbar anchored at bottom via layer-shell
│   └── start-menu/
│       └── start-menu.py    ← Start menu with search, pinned apps, power options
├── notifications/
│   └── notifications.py     ← Notification center + Quick Settings panel
├── settings/
│   └── settings.py          ← 9-section Settings app (System, Sound, Network, ...)
└── themes/
    └── bobo-default/
        ├── gtk.css           ← GTK4 theme (dark mode, 8px radius, #4a9eff accent)
        ├── colors-dark.css   ← Dark colour token definitions
        ├── colors-light.css  ← Light colour token definitions
        ├── qt6-style.qss     ← Qt6 stylesheet matching the GTK4 theme
        └── index.theme       ← Theme metadata
```

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| Win+D | Show/hide desktop |
| Win+E | Open Files (Nemo) |
| Win+A | Open AI Assistant |
| Win+L | Lock screen |
| Win+R | Run dialog |
| Win+N | Notification center |
| Win+V | Clipboard history |
| Win+Left/Right | Snap window left/right |
| Win+Up | Maximise window |
| PrintScreen | Screenshot (grim + slurp) |
| Alt+F4 | Close window |

## Theming

Design tokens:

| Token | Dark | Light |
|-------|------|-------|
| Background | `#1a1a2e` | `#f5f5f5` |
| Accent | `#4a9eff` | `#0066cc` |
| Corner radius | `8px` | `8px` |
| Taskbar height | `48px` | `48px` |
| Font | Inter, Segoe UI, system-ui | same |
| Animation | `150ms ease-in-out` | same |

## Running components manually

```bash
# Taskbar
python3 desktop/taskbar/taskbar.py

# Start menu
python3 desktop/taskbar/start-menu/start-menu.py

# Notification center (toggle)
python3 desktop/notifications/notifications.py --toggle

# Settings
python3 desktop/settings/settings.py
```
