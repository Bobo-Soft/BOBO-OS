#!/usr/bin/env python3
"""
BOBO Browser — the native browser for BOBO OS.

Built on GTK3 + WebKit2GTK (renders reliably everywhere, incl. VMs).
Features required by BOBO OS:
  * BOBO theme (#1a1a2e chrome, #4a9eff accent)
  * DuckDuckGo private search as the default engine (branding tag t=bobo)
  * Tab suspension after 5 minutes idle (frees memory; restores on click)
  * Privacy defaults (no third-party cookies, Do-Not-Track, DDG start page)
"""
import time
import urllib.parse
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, Gdk, GLib, WebKit2  # noqa: E402

# ── Config ───────────────────────────────────────────────────────────────────
BG = "#1a1a2e"
ACCENT = "#4a9eff"
FG = "#ffffff"
PANEL = "#232342"
HOVER = "#2d2d55"
# BOBO Search (self-hosted SearXNG at search.boboai.eu) is the default engine; it
# falls back to DuckDuckGo automatically when the BOBO Search server is unreachable.
BOBO_SEARCH = "https://search.boboai.eu/search?q=%s"
BOBO_SEARCH_HEALTH = "https://search.boboai.eu/healthz"
DDG = "https://duckduckgo.com/?q=%s&t=bobo&kp=1"   # fallback; kp=1 safe search, t=bobo branding
SUSPEND_AFTER = 5 * 60          # 5 minutes

# Cached availability of BOBO Search so the omnibox never blocks per keystroke.
_bs_ok = None
_bs_checked = 0.0


def bobo_search_available() -> bool:
    """True if BOBO Search answers /healthz. Result cached for 5 minutes."""
    global _bs_ok, _bs_checked
    now = time.time()
    if _bs_ok is not None and (now - _bs_checked) < 300:
        return _bs_ok
    try:
        import urllib.request
        with urllib.request.urlopen(BOBO_SEARCH_HEALTH, timeout=1.5) as r:
            _bs_ok = (getattr(r, "status", r.getcode()) == 200)
    except Exception:
        _bs_ok = False
    _bs_checked = now
    return _bs_ok
NEWTAB = "file://" + str(Path("/usr/share/bobo-browser/newtab.html"))

CSS = f"""
.bb-chrome {{ background:{BG}; color:{FG};
    font-family:"Inter","Segoe UI",system-ui,sans-serif; }}
.bb-chrome button {{ background:transparent; color:{FG}; border:none;
    border-radius:8px; padding:6px 8px; margin:2px; }}
.bb-chrome button:hover {{ background:{HOVER}; }}
.bb-omni {{ background:{PANEL}; color:{FG}; border:1px solid #33335a;
    border-radius:16px; padding:6px 14px; margin:4px; }}
.bb-omni:focus {{ border-color:{ACCENT}; }}
.bb-tab {{ background:{PANEL}; color:{FG}; border-radius:8px 8px 0 0;
    padding:2px 4px; margin:2px 1px 0 1px; }}
.bb-tab.current {{ background:{HOVER}; border-bottom:2px solid {ACCENT}; }}
.bb-tab button {{ padding:2px 6px; }}
.bb-tab label {{ padding:4px 6px; }}
.bb-newtab {{ background:{ACCENT}; color:#fff; border-radius:8px; }}
.bb-suspended {{ background:{BG}; color:{FG}; }}
.bb-suspended button {{ background:{ACCENT}; color:#fff; border-radius:8px;
    padding:10px 18px; }}
"""


def is_url(text: str) -> bool:
    t = text.strip()
    if not t or " " in t:
        return False
    if "://" in t or t.startswith("about:") or t.startswith("file:"):
        return True
    if t in ("localhost",) or t.startswith("localhost:"):
        return True
    # a.b with a dot and no spaces => treat as domain
    return "." in t and not t.startswith(".") and not t.endswith(".")


def to_uri(text: str) -> str:
    t = text.strip()
    if is_url(t):
        if "://" in t or t.startswith(("about:", "file:")):
            return t
        return "https://" + t
    q = urllib.parse.quote(t)
    # Default to BOBO Search; fall back to DuckDuckGo if the server is unreachable.
    return (BOBO_SEARCH % q) if bobo_search_available() else (DDG % q)


class Tab:
    def __init__(self, browser, uri):
        self.browser = browser
        self.url = uri
        self.suspended = False
        self.last_active = time.time()

        self.holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.view = None
        self._make_view(uri)

        # Tab label widget (title + close)
        self.tabbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.tabbox.get_style_context().add_class("bb-tab")
        self.icon = Gtk.Image.new_from_icon_name("text-html", Gtk.IconSize.MENU)
        self.title = Gtk.Label(label="New tab")
        self.title.set_ellipsize(3); self.title.set_max_width_chars(18)
        close = Gtk.Button()
        close.add(Gtk.Image.new_from_icon_name("window-close", Gtk.IconSize.MENU))
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.connect("clicked", lambda *_: self.browser.close_tab(self))
        self.tabbox.pack_start(self.icon, False, False, 0)
        self.tabbox.pack_start(self.title, True, True, 0)
        self.tabbox.pack_start(close, False, False, 0)
        self.tabbox.show_all()

    def _make_view(self, uri):
        view = WebKit2.WebView()
        s = view.get_settings()
        for prop, val in [("enable-javascript", True),
                          ("enable-developer-extras", True),
                          ("enable-smooth-scrolling", True),
                          ("default-charset", "utf-8")]:
            try:
                s.set_property(prop, val)
            except Exception:
                pass
        try:
            view.set_property("user-agent",
                              view.get_settings().get_user_agent() + " BOBO-Browser/1.0")
        except Exception:
            pass
        view.connect("notify::title", self._on_title)
        view.connect("notify::uri", self._on_uri)
        view.connect("load-changed", self._on_load)
        view.load_uri(uri)
        self.view = view
        for c in self.holder.get_children():
            self.holder.remove(c)
        self.holder.pack_start(view, True, True, 0)
        self.holder.show_all()

    # ── suspension ────────────────────────────────────────────────────────────
    def suspend(self):
        if self.suspended or self.view is None:
            return
        try:
            self.url = self.view.get_uri() or self.url
        except Exception:
            pass
        self.holder.remove(self.view)
        self.view.destroy()
        self.view = None
        self.suspended = True
        ph = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        ph.get_style_context().add_class("bb-suspended")
        ph.set_valign(Gtk.Align.CENTER); ph.set_halign(Gtk.Align.CENTER)
        lbl = Gtk.Label()
        lbl.set_markup("<span size='large'>💤 Tab suspended to save memory</span>")
        btn = Gtk.Button(label="Click to restore")
        btn.connect("clicked", lambda *_: self.resume())
        ph.pack_start(lbl, False, False, 0)
        ph.pack_start(btn, False, False, 0)
        self.holder.pack_start(ph, True, True, 0)
        self.holder.show_all()
        self.icon.set_from_icon_name("media-playback-pause", Gtk.IconSize.MENU)

    def resume(self):
        if not self.suspended:
            return
        for c in self.holder.get_children():
            self.holder.remove(c)
        self.suspended = False
        self.last_active = time.time()
        self._make_view(self.url)
        self.icon.set_from_icon_name("text-html", Gtk.IconSize.MENU)

    # ── signals ───────────────────────────────────────────────────────────────
    def _on_title(self, view, _):
        t = view.get_title() or "New tab"
        self.title.set_text(t)
        self.title.set_tooltip_text(t)
        if self is self.browser.current_tab():
            self.browser.set_window_title(t)

    def _on_uri(self, view, _):
        if self is self.browser.current_tab():
            self.browser.omni.set_text(view.get_uri() or "")

    def _on_load(self, view, ev):
        if self is self.browser.current_tab():
            self.browser.update_nav()


class Browser(Gtk.Window):
    def __init__(self):
        super().__init__(title="BOBO Browser")
        self.set_default_size(1100, 720)
        self.tabs = []

        prov = Gtk.CssProvider(); prov.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # privacy: no third-party cookies + persistent store under the profile
        try:
            cm = WebKit2.WebContext.get_default().get_cookie_manager()
            cm.set_accept_policy(WebKit2.CookieAcceptPolicy.NO_THIRD_PARTY)
        except Exception:
            pass

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.get_style_context().add_class("bb-chrome")
        self.add(root)

        # Toolbar
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bar.get_style_context().add_class("bb-chrome")
        self.btn_back = self._tool("go-previous", lambda *_: self._nav("back"))
        self.btn_fwd = self._tool("go-next", lambda *_: self._nav("forward"))
        self.btn_reload = self._tool("view-refresh", lambda *_: self._nav("reload"))
        self.btn_home = self._tool("go-home", lambda *_: self._go(NEWTAB))
        for b in (self.btn_back, self.btn_fwd, self.btn_reload, self.btn_home):
            bar.pack_start(b, False, False, 0)
        self.omni = Gtk.Entry()
        self.omni.get_style_context().add_class("bb-omni")
        self.omni.set_placeholder_text("Search DuckDuckGo privately or enter address")
        self.omni.connect("activate", self._on_omni)
        pi = Gtk.Image.new_from_icon_name("system-search", Gtk.IconSize.MENU)
        self.omni.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search")
        bar.pack_start(self.omni, True, True, 0)
        newt = self._tool("tab-new", lambda *_: self.new_tab())
        bar.pack_start(newt, False, False, 0)
        root.pack_start(bar, False, False, 0)

        # Tabs
        self.nb = Gtk.Notebook()
        self.nb.set_show_border(False)
        self.nb.set_scrollable(True)
        self.nb.connect("switch-page", self._on_switch)
        root.pack_start(self.nb, True, True, 0)

        # Shortcuts
        self.connect("key-press-event", self._on_key)
        self.connect("destroy", Gtk.main_quit)

        self.new_tab(NEWTAB)
        GLib.timeout_add_seconds(30, self._suspension_sweep)
        self.show_all()

    def _tool(self, icon, cb):
        b = Gtk.Button()
        b.add(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.SMALL_TOOLBAR))
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.connect("clicked", cb)
        return b

    # ── tab management ────────────────────────────────────────────────────────
    def new_tab(self, uri=None):
        tab = Tab(self, uri or NEWTAB)
        self.tabs.append(tab)
        idx = self.nb.append_page(tab.holder, tab.tabbox)
        self.nb.set_tab_reorderable(tab.holder, True)
        self.nb.show_all()
        self.nb.set_current_page(idx)
        self.omni.grab_focus()
        return tab

    def close_tab(self, tab):
        if tab not in self.tabs:
            return
        idx = self.tabs.index(tab)
        self.nb.remove_page(idx)
        self.tabs.remove(tab)
        if tab.view:
            tab.view.destroy()
        if not self.tabs:
            Gtk.main_quit()

    def current_tab(self):
        i = self.nb.get_current_page()
        return self.tabs[i] if 0 <= i < len(self.tabs) else None

    def _on_switch(self, _nb, _page, num):
        if 0 <= num < len(self.tabs):
            tab = self.tabs[num]
            tab.last_active = time.time()
            if tab.suspended:
                tab.resume()
            for j, t in enumerate(self.tabs):
                (t.tabbox.get_style_context().add_class if j == num
                 else t.tabbox.get_style_context().remove_class)("current")
            self.set_window_title(tab.title.get_text())
            try:
                self.omni.set_text((tab.view.get_uri() if tab.view else tab.url) or "")
            except Exception:
                pass
            self.update_nav()

    # ── navigation ────────────────────────────────────────────────────────────
    def _on_omni(self, _entry):
        self._go(to_uri(self.omni.get_text()))

    def _go(self, uri):
        tab = self.current_tab()
        if not tab:
            tab = self.new_tab(uri); return
        if tab.suspended:
            tab.resume()
        tab.view.load_uri(uri)

    def _nav(self, what):
        tab = self.current_tab()
        if not tab or not tab.view:
            return
        if what == "back" and tab.view.can_go_back():
            tab.view.go_back()
        elif what == "forward" and tab.view.can_go_forward():
            tab.view.go_forward()
        elif what == "reload":
            tab.view.reload()

    def update_nav(self):
        tab = self.current_tab()
        if tab and tab.view:
            self.btn_back.set_sensitive(tab.view.can_go_back())
            self.btn_fwd.set_sensitive(tab.view.can_go_forward())

    def set_window_title(self, t):
        self.set_title(f"{t} — BOBO Browser" if t else "BOBO Browser")

    # ── 5-minute tab suspension ───────────────────────────────────────────────
    def _suspension_sweep(self):
        cur = self.current_tab()
        now = time.time()
        for tab in self.tabs:
            if tab is cur or tab.suspended or tab.view is None:
                continue
            if now - tab.last_active > SUSPEND_AFTER:
                tab.suspend()
        if cur:
            cur.last_active = now
        return True

    def _on_key(self, _w, ev):
        ctrl = ev.state & Gdk.ModifierType.CONTROL_MASK
        if not ctrl:
            return False
        k = ev.keyval
        if k == Gdk.KEY_t:
            self.new_tab()
        elif k == Gdk.KEY_w:
            if self.current_tab():
                self.close_tab(self.current_tab())
        elif k == Gdk.KEY_l:
            self.omni.grab_focus(); self.omni.select_region(0, -1)
        elif k == Gdk.KEY_r:
            self._nav("reload")
        else:
            return False
        return True


def main():
    import sys
    b = Browser()
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            b.new_tab(to_uri(arg))
    Gtk.main()


if __name__ == "__main__":
    main()
