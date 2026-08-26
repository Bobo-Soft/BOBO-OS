# BOBO Browser

The native web browser for BOBO OS — GTK3 + WebKit2GTK, private by default.

## Features
- **BOBO theme** — `#1a1a2e` chrome, `#4a9eff` accent, Inter font; dark branded start page.
- **DuckDuckGo private search** as the default engine. Omnibox queries go to
  `duckduckgo.com/?q=…&t=bobo` (the `t=bobo` tag brands the traffic as BOBO OS). URLs load directly.
- **Tab suspension after 5 minutes idle** — background tabs older than 5 min have their WebView
  destroyed (freeing memory) and show a "💤 Tab suspended — click to restore" placeholder;
  switching to the tab (or clicking) reloads it.
- **Privacy defaults** — third-party cookies blocked, DuckDuckGo start page, no telemetry.
- Tabbed browsing, back/forward/reload/home, omnibox. Shortcuts: `Ctrl+T` new tab,
  `Ctrl+W` close, `Ctrl+L` focus address bar, `Ctrl+R` reload.
- Registered as the **default web browser** (http/https handler, `x-www-browser`).

## Files (`/usr/share/bobo-browser/`, launcher `/usr/bin/bobo-browser`)
- `bobo-browser.py` — the browser (engine + chrome + suspension).
- `newtab.html` — branded start / new-tab page with the DuckDuckGo search box and quick links.

## Install
```bash
sudo bash install.sh
```
Installs `gir1.2-webkit2-4.1` + `libwebkit2gtk-4.1-0`, copies sources, creates the launcher and
`.desktop`, and sets BOBO Browser as the default browser. Integrated into the build via
`compile-bobo-os.ps1` Step 3f. Referenced by the shell taskbar and desktop icons as `bobo-browser`.
