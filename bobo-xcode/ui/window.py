"""
BoboXcode main window.
Layout: FileTree | (Editor / bottom notebook: Terminal, Build, Simulator, Preview).
Toolbar: Open, New, project-type selector, Run, Simulate, Publish (Bridge).
"""
import os
import threading
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

from ui.editor import CodeEditor
from ui.file_tree import FileTree
from ui.terminal import TerminalPanel
from ui.build_panel import BuildPanel
from ui.simulator_panel import SimulatorPanel
from ui.swift_preview import SwiftUIPreview
from engines.swift_engine import SwiftEngine
from engines.flutter_engine import FlutterEngine
from engines.react_native_engine import ReactNativeEngine
from engines.package_manager import PackageManager
from engines.lsp_server import LSPClient
from bridge.mac_connector import MacConnector

CSS_PATH = "/usr/share/bobo-xcode/ui/style.css"


class BoboXcodeWindow(Gtk.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("BoboXcode")
        self.set_default_size(1400, 900)
        self.project_path = None
        self.project_type = None
        self.swift_engine = SwiftEngine()
        self.flutter_engine = FlutterEngine()
        self.rn_engine = ReactNativeEngine()
        self.pkg_manager = PackageManager()
        self.mac_connector = MacConnector()
        self.lsp = None
        self._build_ui()
        self._load_css()
        self._setup_shortcuts()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        open_btn = Gtk.Button(icon_name="folder-open-symbolic")
        open_btn.set_tooltip_text("Open project")
        open_btn.connect("clicked", self._on_open_project)
        header.pack_start(open_btn)

        new_btn = Gtk.Button(icon_name="document-new-symbolic")
        new_btn.set_tooltip_text("New project")
        new_btn.connect("clicked", self._on_new_project)
        header.pack_start(new_btn)

        save_btn = Gtk.Button(icon_name="document-save-symbolic")
        save_btn.set_tooltip_text("Save (Ctrl+S)")
        save_btn.connect("clicked", lambda *a: self.editor.save())
        header.pack_start(save_btn)

        self.project_type_btn = Gtk.DropDown.new_from_strings(
            ["Swift/iOS", "SwiftUI", "Flutter", "React Native"])
        header.pack_start(self.project_type_btn)

        publish_btn = Gtk.Button(label="\U0001F680 Publish")
        publish_btn.add_css_class("bobo-publish-btn")
        publish_btn.set_tooltip_text("Publish to App Store via BoboiOS Bridge")
        publish_btn.connect("clicked", self._on_publish)
        header.pack_end(publish_btn)

        sim_btn = Gtk.Button(label="\U0001F4F1 Simulate")
        sim_btn.set_tooltip_text("Run in the iOS simulator")
        sim_btn.connect("clicked", self._on_simulate)
        header.pack_end(sim_btn)

        run_btn = Gtk.Button(label="▶ Run")
        run_btn.add_css_class("suggested-action")
        run_btn.set_tooltip_text("Compile & run locally")
        run_btn.connect("clicked", self._on_run)
        header.pack_end(run_btn)

        main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)

        self.file_tree = FileTree()
        self.file_tree.connect("file-selected", self._on_file_selected)
        self.file_tree.set_size_request(220, -1)
        main_paned.set_start_child(self.file_tree)
        main_paned.set_resize_start_child(False)
        main_paned.set_position(220)

        right_paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        main_paned.set_end_child(right_paned)

        self.editor_notebook = Gtk.Notebook()
        self.editor_notebook.set_scrollable(True)
        self.editor = CodeEditor()
        self.editor_notebook.append_page(self.editor, Gtk.Label(label="editor"))
        right_paned.set_start_child(self.editor_notebook)
        right_paned.set_position(580)

        bottom = Gtk.Notebook()
        right_paned.set_end_child(bottom)
        self.terminal = TerminalPanel()
        bottom.append_page(self.terminal, Gtk.Label(label="Terminal"))
        self.build_panel = BuildPanel()
        bottom.append_page(self.build_panel, Gtk.Label(label="Build"))
        self.simulator = SimulatorPanel()
        bottom.append_page(self.simulator, Gtk.Label(label="Simulator iOS"))
        self.swift_preview = SwiftUIPreview()
        bottom.append_page(self.swift_preview, Gtk.Label(label="SwiftUI Preview"))
        self.bottom_notebook = bottom

        # status bar under the paned
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(main_paned)
        main_paned.set_vexpand(True)
        self.status_bar = Gtk.Label(label="BoboXcode ready", xalign=0)
        self.status_bar.add_css_class("bobo-status-bar")
        root.append(self.status_bar)
        self.set_child(root)

    # ------------------------------------------------------------------ project
    def _on_open_project(self, btn):
        dialog = Gtk.FileDialog()
        dialog.select_folder(self, None, self._open_project_finished)

    def _open_project_finished(self, dialog, res):
        try:
            folder = dialog.select_folder_finish(res)
        except GLib.Error:
            return
        if folder:
            self.open_project(folder.get_path())

    def _on_new_project(self, btn):
        win = Gtk.Window(title="New project", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        name_e = Gtk.Entry(placeholder_text="Project name")
        type_dd = Gtk.DropDown.new_from_strings(["Swift", "SwiftUI", "Flutter", "React Native"])
        loc_btn = Gtk.Button(label="Choose parent folder...")
        self._new_parent = os.path.expanduser("/var/lib/bobo-xcode/projects")
        loc_lbl = Gtk.Label(label=self._new_parent, xalign=0)
        loc_lbl.add_css_class("dim-label")

        def choose_loc(*a):
            d = Gtk.FileDialog()
            d.select_folder(win, None, lambda dd, rr: self._new_loc_set(dd, rr, loc_lbl))
        loc_btn.connect("clicked", choose_loc)

        create = Gtk.Button(label="Create")
        create.add_css_class("suggested-action")

        def do_create(*a):
            name = name_e.get_text().strip() or "MyApp"
            kind = ["swift", "swiftui", "flutter", "react_native"][type_dd.get_selected()]
            path = os.path.join(self._new_parent, name)
            os.makedirs(self._new_parent, exist_ok=True)
            try:
                if kind in ("swift", "swiftui"):
                    self.swift_engine.create_project(path, name, "executable")
                elif kind == "flutter":
                    self.flutter_engine.create_project(path, name)
                else:
                    self.rn_engine.create_project(path, name)
            except Exception as e:
                self._show_error("Create failed: %s" % e)
            win.close()
            if os.path.isdir(path):
                self.open_project(path)
        create.connect("clicked", do_create)

        for w in (Gtk.Label(label="Name:", xalign=0), name_e,
                  Gtk.Label(label="Type:", xalign=0), type_dd, loc_btn, loc_lbl, create):
            box.append(w)
        win.set_child(box)
        win.present()

    def _new_loc_set(self, dialog, res, label):
        try:
            f = dialog.select_folder_finish(res)
            if f:
                self._new_parent = f.get_path()
                label.set_text(self._new_parent)
        except GLib.Error:
            pass

    def open_project(self, path: str):
        if not path or not os.path.isdir(path):
            self._show_error("Not a folder: %s" % path)
            return
        self.project_path = path
        self.project_type = self._detect_project_type(path)
        self.file_tree.load_directory(path)
        self.terminal.set_cwd(path)
        self.swift_preview.set_project(path)
        self.set_title("BoboXcode — %s" % os.path.basename(path))
        self.status_bar.set_label("Project: %s | %s" % (self.project_type, path))
        # start LSP for Swift projects (best-effort)
        if self.project_type == "swift" and self.swift_engine.is_available():
            self._start_lsp(path)

    def _start_lsp(self, path):
        def work():
            try:
                client = LSPClient(self.swift_engine.get_lsp_command(), root_path=path)
                if client.is_available() and client.start():
                    self.lsp = client
                    self.editor.lsp = client
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _detect_project_type(self, path: str) -> str:
        try:
            entries = os.listdir(path)
        except Exception:
            return "swift"
        if any(e.endswith(".xcodeproj") or e.endswith(".xcworkspace") or e == "Package.swift"
               for e in entries):
            return "swift"
        if "pubspec.yaml" in entries:
            return "flutter"
        if "package.json" in entries:
            return "react_native"
        return "swift"

    def _on_file_selected(self, tree, path):
        self.editor.open_file(path)
        self.status_bar.set_label(path)

    # ------------------------------------------------------------------ run
    def _on_run(self, btn):
        if not self.project_path:
            self._show_error("Open a project first")
            return
        self.bottom_notebook.set_current_page(1)  # Build tab
        self.build_panel.clear()
        self.build_panel.append("Building (%s)...\n" % self.project_type)
        threading.Thread(target=self._run_thread, daemon=True).start()

    def _run_thread(self):
        cb = lambda line: GLib.idle_add(self.build_panel.append, line)
        if self.project_type == "flutter":
            result = self.flutter_engine.run(self.project_path, "linux", callback=cb)
        elif self.project_type == "react_native":
            result = self.rn_engine.run_ios(self.project_path, callback=cb)
        else:
            result = self.swift_engine.run_binary(self.project_path, callback=cb)
        GLib.idle_add(self.build_panel.append,
                      "\n✅ Build complete\n" if result.success
                      else "\n❌ Errors:\n%s\n" % (result.errors or "(see output above)"))

    def _on_simulate(self, btn):
        self.bottom_notebook.set_current_page(2)  # Simulator tab
        self.simulator.start_simulator(self.project_path)

    # ------------------------------------------------------------------ publish
    def _on_publish(self, btn):
        if not self.project_path:
            self._show_error("Open a project first")
            return
        if not self.mac_connector.is_configured():
            self._open_bridge_setup()
            return
        self._show_publish_dialog()

    def _open_bridge_setup(self):
        from ui.settings_dialog import BridgeSetupDialog
        BridgeSetupDialog(parent=self).present()

    def _show_publish_dialog(self):
        from bridge.fastlane_runner import FastlaneRunner
        win = Gtk.Window(title="Publish to App Store", transient_for=self, modal=True)
        win.set_default_size(620, 480)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        cfg = self.mac_connector.config or {}
        apple_id = Gtk.Entry(text=cfg.get("apple_id", ""))
        apple_id.set_placeholder_text("Apple ID")
        apple_pw = Gtk.PasswordEntry()
        apple_pw.set_show_peek_icon(True)
        box.append(Gtk.Label(label="Apple ID:", xalign=0))
        box.append(apple_id)
        box.append(Gtk.Label(label="App-specific password:", xalign=0))
        box.append(apple_pw)
        log_view = Gtk.TextView()
        log_view.set_editable(False)
        log_view.set_monospace(True)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(log_view)
        box.append(sw)
        go = Gtk.Button(label="Publish now")
        go.add_css_class("bobo-publish-btn")

        def log(msg):
            buf = log_view.get_buffer()
            GLib.idle_add(lambda: buf.insert(buf.get_end_iter(), msg))

        def do_publish(*a):
            go.set_sensitive(False)
            runner = FastlaneRunner(self.project_path, self.mac_connector)
            threading.Thread(
                target=lambda: runner.publish(apple_id.get_text(), apple_pw.get_text(),
                                              callback=log),
                daemon=True).start()
        go.connect("clicked", do_publish)
        box.append(go)
        win.set_child(box)
        win.present()

    # ------------------------------------------------------------------ misc
    def _show_error(self, message: str):
        dialog = Gtk.AlertDialog()
        dialog.set_message("BoboXcode")
        dialog.set_detail(message)
        dialog.show(self)

    def _load_css(self):
        if not os.path.exists(CSS_PATH):
            return
        css = Gtk.CssProvider()
        css.load_from_path(CSS_PATH)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _setup_shortcuts(self):
        ctrl = Gtk.ShortcutController()
        ctrl.set_scope(Gtk.ShortcutScope.GLOBAL)
        mapping = {
            "<Control>r": lambda: self._on_run(None),
            "<Control>b": lambda: self._on_run(None),
            "<Control>s": lambda: self.editor.save(),
            "<Control><Shift>s": lambda: self._on_simulate(None),
            "<Control><Shift>p": lambda: self._on_publish(None),
        }
        for accel, fn in mapping.items():
            trigger = Gtk.ShortcutTrigger.parse_string(accel)
            action = Gtk.CallbackAction.new(lambda w, a, f=fn: (f(), True)[1])
            ctrl.add_shortcut(Gtk.Shortcut.new(trigger, action))
        self.add_controller(ctrl)
