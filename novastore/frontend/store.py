#!/usr/bin/env python3
# =============================================================================
# BOBO OS — NovaStore GTK4 Frontend (Phase 6.2)
# E:\BOBO-OS\novastore\frontend\store.py
#
# App store UI that connects to the FastAPI backend at http://127.0.0.1:8740.
# Features: category sidebar, app grid (FlowBox), detail view, install progress.
# =============================================================================

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, GdkPixbuf, Gdk

import sys
import json
import threading
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

BACKEND_URL = "http://127.0.0.1:8740"

CATEGORIES = [
    ("all",         "All Apps",      "view-app-grid-symbolic"),
    ("productivity","Productivity",  "emblem-documents-symbolic"),
    ("games",       "Games",         "applications-games-symbolic"),
    ("media",       "Media",         "applications-multimedia-symbolic"),
    ("internet",    "Internet",      "network-wireless-symbolic"),
    ("utilities",   "Utilities",     "applications-system-symbolic"),
    ("education",   "Education",     "accessories-text-editor-symbolic"),
    ("updates",     "Updates",       "software-update-available-symbolic"),
]

# ---------------------------------------------------------------------------
# Backend API helpers (synchronous, called from threads)
# ---------------------------------------------------------------------------

def _api_get(path: str, params: dict = None) -> dict:
    url = BACKEND_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def _api_post(path: str, data: dict = None) -> dict:
    url = BACKEND_URL + path
    payload = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# App card widget — shown in the grid
# ---------------------------------------------------------------------------

class AppCard(Gtk.Box):
    def __init__(self, app_data: dict, on_click):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.app_data = app_data
        self.set_size_request(168, 196)
        self.add_css_class("card")
        self.add_css_class("app-card")
        self.set_margin_start(4)
        self.set_margin_end(4)
        self.set_margin_top(4)
        self.set_margin_bottom(4)

        # Icon placeholder (use icon-name from app data or generic)
        icon_name = app_data.get("icon", "application-x-executable")
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(64)
        icon.set_margin_top(16)
        self.append(icon)

        # App name label
        name_label = Gtk.Label(label=app_data.get("name", "Unknown"))
        name_label.set_max_width_chars(18)
        name_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        name_label.add_css_class("heading")
        self.append(name_label)

        # Short description
        desc = app_data.get("summary", app_data.get("description", ""))[:60]
        desc_label = Gtk.Label(label=desc)
        desc_label.set_max_width_chars(22)
        desc_label.set_ellipsize(3)
        desc_label.add_css_class("dim-label")
        desc_label.add_css_class("caption")
        self.append(desc_label)

        # Platform badge
        platform = app_data.get("platform", "linux")
        badge_map = {
            "linux": ("Linux", "success"),
            "windows": ("Windows", "accent"),
            "macos": ("macOS", ""),
            "ios": ("iOS", ""),
        }
        badge_text, badge_class = badge_map.get(platform, ("App", ""))
        badge = Gtk.Label(label=badge_text)
        badge.add_css_class("tag")
        if badge_class:
            badge.add_css_class(badge_class)
        badge.set_margin_bottom(12)
        self.append(badge)

        # Click gesture
        gesture = Gtk.GestureClick()
        gesture.connect("released", lambda g, n, x, y: on_click(app_data))
        self.add_controller(gesture)


# ---------------------------------------------------------------------------
# Install progress dialog
# ---------------------------------------------------------------------------

class InstallDialog(Adw.Dialog):
    def __init__(self, parent, app_data: dict):
        super().__init__()
        self.app_data = app_data
        self.set_title(f"Installing {app_data.get('name', 'app')}…")
        self.set_content_width(400)
        self.set_can_close(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        self._label = Gtk.Label(label="Preparing installation…")
        self._label.add_css_class("body")
        box.append(self._label)

        self._progress = Gtk.ProgressBar()
        self._progress.set_pulse_step(0.05)
        box.append(self._progress)

        self._status = Gtk.Label(label="")
        self._status.add_css_class("caption")
        self._status.add_css_class("dim-label")
        box.append(self._status)

        self.set_child(box)
        self._pulse_id = GLib.timeout_add(80, self._pulse)

        # Start install in background
        threading.Thread(target=self._do_install, daemon=True).start()

    def _pulse(self):
        self._progress.pulse()
        return True

    def _do_install(self):
        result = _api_post(f"/apps/{self.app_data['id']}/install")
        if "error" in result:
            GLib.idle_add(self._on_error, result["error"])
            return
        job_id = result.get("job_id")
        if job_id:
            self._poll_job(job_id)
        else:
            GLib.idle_add(self._on_done)

    def _poll_job(self, job_id: str):
        import time
        for _ in range(120):
            time.sleep(1)
            data = _api_get(f"/jobs/{job_id}")
            status = data.get("status", "running")
            msg = data.get("message", "")
            GLib.idle_add(self._set_status, msg)
            if status == "done":
                GLib.idle_add(self._on_done)
                return
            if status == "error":
                GLib.idle_add(self._on_error, data.get("error", "Installation failed."))
                return
        GLib.idle_add(self._on_error, "Timed out waiting for installation.")

    def _set_status(self, msg: str):
        self._status.set_text(msg)

    def _on_done(self):
        GLib.source_remove(self._pulse_id)
        self._progress.set_fraction(1.0)
        self._label.set_text("Installation complete!")
        self.set_can_close(True)

        close_btn = Gtk.Button(label="Close")
        close_btn.add_css_class("suggested-action")
        close_btn.connect("clicked", lambda b: self.close())
        child = self.get_child()
        child.append(close_btn)

    def _on_error(self, msg: str):
        GLib.source_remove(self._pulse_id)
        self._label.set_text("Installation failed")
        self._status.set_text(msg)
        self._progress.set_fraction(0.0)
        self.set_can_close(True)

        close_btn = Gtk.Button(label="Close")
        close_btn.add_css_class("destructive-action")
        close_btn.connect("clicked", lambda b: self.close())
        child = self.get_child()
        child.append(close_btn)


# ---------------------------------------------------------------------------
# App detail view (shown in a split-view or navigation push)
# ---------------------------------------------------------------------------

class AppDetailPage(Gtk.Box):
    def __init__(self, app_data: dict, on_back, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._parent = parent_window
        self.app_data = app_data

        # Header bar
        header = Adw.HeaderBar()
        back_btn = Gtk.Button(label="Back")
        back_btn.set_icon_name("go-previous-symbolic")
        back_btn.connect("clicked", lambda b: on_back())
        header.pack_start(back_btn)
        header.set_title_widget(Adw.WindowTitle(
            title=app_data.get("name", "App"),
            subtitle=app_data.get("category", "")
        ))
        self.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(48)
        content.set_margin_end(48)
        content.set_halign(Gtk.Align.CENTER)
        content.set_size_request(640, -1)
        scroll.set_child(content)

        # Hero row
        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        hero.set_halign(Gtk.Align.FILL)
        content.append(hero)

        icon_name = app_data.get("icon", "application-x-executable")
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(96)
        hero.append(icon)

        meta_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        meta_box.set_valign(Gtk.Align.CENTER)
        hero.append(meta_box)

        name_lbl = Gtk.Label(label=app_data.get("name", ""))
        name_lbl.set_halign(Gtk.Align.START)
        name_lbl.add_css_class("title-1")
        meta_box.append(name_lbl)

        dev_lbl = Gtk.Label(label=app_data.get("developer", ""))
        dev_lbl.set_halign(Gtk.Align.START)
        dev_lbl.add_css_class("dim-label")
        meta_box.append(dev_lbl)

        platform = app_data.get("platform", "linux")
        plat_lbl = Gtk.Label(label=f"Platform: {platform.capitalize()}")
        plat_lbl.set_halign(Gtk.Align.START)
        plat_lbl.add_css_class("caption")
        meta_box.append(plat_lbl)

        # Install button (spacer + button right-aligned)
        install_btn = Gtk.Button()
        installed = app_data.get("installed", False)
        if installed:
            install_btn.set_label("Installed")
            install_btn.set_sensitive(False)
        else:
            install_btn.set_label("Install")
            install_btn.add_css_class("suggested-action")
            install_btn.add_css_class("pill")
            install_btn.connect("clicked", self._on_install)
        install_btn.set_valign(Gtk.Align.CENTER)
        install_btn.set_halign(Gtk.Align.END)
        hero.set_hexpand(True)
        hero.append(Gtk.Box())  # spacer
        hero.get_last_child().set_hexpand(True)
        hero.append(install_btn)

        # Size / version info strip
        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=32)
        info_box.add_css_class("card")
        info_box.set_margin_top(8)
        info_box.set_margin_bottom(8)

        for label, key in [("Version", "version"), ("Size", "size"), ("Downloads", "downloads")]:
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            col.set_margin_top(12)
            col.set_margin_bottom(12)
            col.set_margin_start(16)
            col.set_margin_end(16)
            val = Gtk.Label(label=str(app_data.get(key, "—")))
            val.add_css_class("heading")
            lbl = Gtk.Label(label=label)
            lbl.add_css_class("caption")
            lbl.add_css_class("dim-label")
            col.append(val)
            col.append(lbl)
            info_box.append(col)
            if label != "Downloads":
                sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
                sep.set_margin_top(8)
                sep.set_margin_bottom(8)
                info_box.append(sep)
        content.append(info_box)

        # Description
        group = Adw.PreferencesGroup(title="About")
        desc_row = Adw.ActionRow()
        desc_text = app_data.get("description", "No description available.")
        desc_lbl = Gtk.Label(label=desc_text)
        desc_lbl.set_wrap(True)
        desc_lbl.set_xalign(0)
        desc_lbl.set_margin_top(8)
        desc_lbl.set_margin_bottom(8)
        desc_row.set_child(desc_lbl)
        group.add(desc_row)
        content.append(group)

    def _on_install(self, btn):
        dialog = InstallDialog(self._parent, self.app_data)
        dialog.present(self._parent)


# ---------------------------------------------------------------------------
# Main store window
# ---------------------------------------------------------------------------

class NovaStoreWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("NovaStore")
        self.set_default_size(1100, 720)
        self.set_size_request(800, 560)

        self._current_category = "all"
        self._all_apps: list = []
        self._search_query = ""

        self._build_ui()
        self._load_apps()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self):
        # Top-level: NavigationView so we can push detail pages
        self._nav = Adw.NavigationView()
        self.set_content(self._nav)

        # Main page inside NavigationView
        main_page = Adw.NavigationPage(title="NovaStore")
        self._nav.add(main_page)

        overlay_split = Adw.OverlaySplitView()
        overlay_split.set_min_sidebar_width(200)
        overlay_split.set_max_sidebar_width(240)
        overlay_split.set_sidebar_width_fraction(0.22)
        main_page.set_child(overlay_split)

        # ── Sidebar ──────────────────────────────────────────────────────
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_end_title_buttons(False)
        sidebar_header.set_title_widget(Gtk.Label(label=""))
        sidebar_box.append(sidebar_header)

        self._sidebar_list = Gtk.ListBox()
        self._sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._sidebar_list.add_css_class("navigation-sidebar")
        self._sidebar_list.connect("row-selected", self._on_category_selected)
        sidebar_box.append(self._sidebar_list)

        for cat_id, cat_name, cat_icon in CATEGORIES:
            row = Adw.ActionRow()
            row.set_title(cat_name)
            row.set_icon_name(cat_icon)
            row._cat_id = cat_id
            self._sidebar_list.append(row)

        # Select "All Apps" by default
        self._sidebar_list.select_row(self._sidebar_list.get_row_at_index(0))

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_vexpand(True)
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_child(sidebar_box)

        overlay_split.set_sidebar(sidebar_scroll)

        # ── Content area ─────────────────────────────────────────────────
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Header bar with search
        content_header = Adw.HeaderBar()

        toggle_btn = Gtk.ToggleButton()
        toggle_btn.set_icon_name("system-search-symbolic")
        toggle_btn.connect("toggled", self._on_search_toggled)
        content_header.pack_end(toggle_btn)

        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.connect("clicked", lambda b: self._load_apps())
        content_header.pack_end(refresh_btn)

        self._search_bar = Gtk.SearchBar()
        self._search_bar.set_key_capture_widget(self)
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_size_request(320, -1)
        self._search_entry.connect("search-changed", self._on_search_changed)
        self._search_bar.set_child(self._search_entry)
        toggle_btn.bind_property("active", self._search_bar, "search-mode-enabled",
                                  GLib.BindingFlags.BIDIRECTIONAL)

        self._title_widget = Adw.WindowTitle(title="All Apps", subtitle="")
        content_header.set_title_widget(self._title_widget)

        content_box.append(content_header)
        content_box.append(self._search_bar)

        # Banner for backend offline
        self._banner = Adw.Banner(title="Cannot connect to NovaStore server. Check that it is running.")
        self._banner.set_revealed(False)
        content_box.append(self._banner)

        # Stack: spinner / grid / empty
        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(150)
        content_box.append(self._stack)

        # Loading spinner page
        spinner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        spinner_box.set_valign(Gtk.Align.CENTER)
        spinner_box.set_halign(Gtk.Align.CENTER)
        spinner = Gtk.Spinner()
        spinner.set_spinning(True)
        spinner.set_size_request(48, 48)
        spinner_box.append(spinner)
        spinner_box.append(Gtk.Label(label="Loading apps…"))
        self._stack.add_named(spinner_box, "loading")

        # App grid page
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._flow = Gtk.FlowBox()
        self._flow.set_valign(Gtk.Align.START)
        self._flow.set_max_children_per_line(6)
        self._flow.set_min_children_per_line(2)
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_homogeneous(True)
        self._flow.set_column_spacing(4)
        self._flow.set_row_spacing(4)
        self._flow.set_margin_top(12)
        self._flow.set_margin_bottom(12)
        self._flow.set_margin_start(12)
        self._flow.set_margin_end(12)
        scroll.set_child(self._flow)
        self._stack.add_named(scroll, "grid")

        # Empty state page
        empty_box = Adw.StatusPage()
        empty_box.set_icon_name("system-search-symbolic")
        empty_box.set_title("No apps found")
        empty_box.set_description("Try a different search or category.")
        self._stack.add_named(empty_box, "empty")

        overlay_split.set_content(content_box)

    # -----------------------------------------------------------------------
    # Data loading
    # -----------------------------------------------------------------------

    def _load_apps(self, *_):
        self._stack.set_visible_child_name("loading")
        self._banner.set_revealed(False)
        threading.Thread(target=self._fetch_apps, daemon=True).start()

    def _fetch_apps(self):
        category = self._current_category
        if category == "updates":
            data = _api_get("/updates")
        elif category == "all":
            data = _api_get("/apps", {"limit": 200})
        else:
            data = _api_get("/apps", {"category": category, "limit": 200})

        if "error" in data or (isinstance(data, dict) and "detail" in data):
            GLib.idle_add(self._on_load_error)
            return

        apps = data if isinstance(data, list) else data.get("apps", [])
        GLib.idle_add(self._on_apps_loaded, apps)

    def _on_load_error(self):
        self._banner.set_revealed(True)
        self._stack.set_visible_child_name("empty")

    def _on_apps_loaded(self, apps: list):
        self._all_apps = apps
        self._render_apps(apps)

    def _render_apps(self, apps: list):
        # Clear existing cards
        while True:
            child = self._flow.get_first_child()
            if child is None:
                break
            self._flow.remove(child)

        query = self._search_query.lower()
        filtered = [a for a in apps
                    if not query
                    or query in a.get("name", "").lower()
                    or query in a.get("description", "").lower()]

        if not filtered:
            self._stack.set_visible_child_name("empty")
            return

        for app in filtered:
            card = AppCard(app, self._on_app_clicked)
            self._flow.append(card)

        self._stack.set_visible_child_name("grid")

    # -----------------------------------------------------------------------
    # Event handlers
    # -----------------------------------------------------------------------

    def _on_category_selected(self, listbox, row):
        if row is None:
            return
        cat_id = row._cat_id
        self._current_category = cat_id
        cat_name = next((c[1] for c in CATEGORIES if c[0] == cat_id), "Apps")
        self._title_widget.set_title(cat_name)
        self._load_apps()

    def _on_search_toggled(self, btn):
        if not btn.get_active():
            self._search_entry.set_text("")
            self._search_query = ""
            self._render_apps(self._all_apps)

    def _on_search_changed(self, entry):
        self._search_query = entry.get_text()
        self._render_apps(self._all_apps)

    def _on_app_clicked(self, app_data: dict):
        # Fetch full details then push detail page
        threading.Thread(
            target=self._fetch_detail,
            args=(app_data,),
            daemon=True
        ).start()

    def _fetch_detail(self, app_data: dict):
        detail = _api_get(f"/apps/{app_data['id']}")
        if "error" not in detail:
            app_data = detail
        GLib.idle_add(self._show_detail, app_data)

    def _show_detail(self, app_data: dict):
        detail_page = Adw.NavigationPage(title=app_data.get("name", "App"))
        detail_content = AppDetailPage(
            app_data,
            on_back=lambda: self._nav.pop(),
            parent_window=self
        )
        detail_page.set_child(detail_content)
        self._nav.push(detail_page)


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------

class NovaStoreApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.NovaStore",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self._on_activate)

    def _on_activate(self, app):
        win = NovaStoreWindow(application=app)
        self._apply_css(win)
        win.present()

    def _apply_css(self, win):
        css = b"""
        .app-card {
            cursor: pointer;
            border-radius: 12px;
            transition: background-color 150ms ease;
        }
        .app-card:hover {
            background-color: alpha(@accent_bg_color, 0.12);
        }
        .tag {
            border-radius: 999px;
            padding: 2px 10px;
            font-size: 11px;
            background-color: alpha(@accent_color, 0.15);
            color: @accent_color;
        }
        .tag.success {
            background-color: alpha(#3a7a3a, 0.18);
            color: #4caf50;
        }
        .pill {
            border-radius: 999px;
            padding: 4px 20px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            win.get_display(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _run_self_test():
    print("=== NovaStore Frontend Self-Test ===")
    pass_count = 0
    fail_count = 0

    def ok(msg):
        nonlocal pass_count
        print(f"  PASS  {msg}")
        pass_count += 1

    def fail(msg):
        nonlocal fail_count
        print(f"  FAIL  {msg}")
        fail_count += 1

    # Test backend connectivity
    result = _api_get("/apps", {"limit": 1})
    if "error" in result:
        print(f"  WARN  Backend offline ({result['error']}) — skipping live tests")
    else:
        ok("Backend reachable")
        if isinstance(result, list) or "apps" in result:
            ok("Apps endpoint returns expected format")
        else:
            fail(f"Unexpected response shape: {result}")

    # Test CATEGORIES constant
    if len(CATEGORIES) >= 7 and all(len(c) == 3 for c in CATEGORIES):
        ok("CATEGORIES list well-formed")
    else:
        fail("CATEGORIES list malformed")

    # Test _api_get error handling (bad endpoint)
    err = _api_get("/nonexistent-path-xyz")
    if "error" in err:
        ok("_api_get handles HTTP errors gracefully")
    else:
        fail("_api_get did not return error key on bad path")

    print(f"  PASS: {pass_count}  FAIL: {fail_count}")
    print("====================================")


if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_self_test()
        sys.exit(0)

    app = NovaStoreApp()
    sys.exit(app.run(sys.argv))
