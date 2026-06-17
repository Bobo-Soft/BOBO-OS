"""
Project file explorer for BoboXcode.
A lazy-loading directory tree that emits 'file-selected' (str path) when a
file row is activated.
"""
import os
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject  # noqa: E402

HIDE = {".build", ".git", "DerivedData", "node_modules", ".dart_tool", "__pycache__"}


class FileTree(Gtk.ScrolledWindow):
    __gsignals__ = {
        "file-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self.root_path = None
        # columns: display name, absolute path, is_dir
        self.store = Gtk.TreeStore(str, str, bool)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_visible(False)
        col = Gtk.TreeViewColumn("Project")
        icon = Gtk.CellRendererText()
        col.pack_start(icon, False)
        col.add_attribute(icon, "text", 0)
        self.view.append_column(col)
        self.view.connect("row-activated", self._on_activated)
        self.set_child(self.view)

    def load_directory(self, path: str):
        self.root_path = path
        self.store.clear()
        self._populate(None, path)

    def _populate(self, parent_iter, path: str):
        try:
            entries = sorted(os.listdir(path),
                             key=lambda n: (not os.path.isdir(os.path.join(path, n)), n.lower()))
        except Exception:
            return
        for name in entries:
            if name in HIDE or (name.startswith(".") and name not in (".swiftpm",)):
                continue
            full = os.path.join(path, name)
            is_dir = os.path.isdir(full)
            label = ("📁 " if is_dir else "📄 ") + name
            it = self.store.append(parent_iter, [label, full, is_dir])
            if is_dir:
                # placeholder child for lazy expansion
                self.store.append(it, ["", "", False])

    def _on_activated(self, view, path, column):
        it = self.store.get_iter(path)
        full = self.store.get_value(it, 1)
        is_dir = self.store.get_value(it, 2)
        if is_dir:
            if view.row_expanded(path):
                view.collapse_row(path)
            else:
                # lazy-fill once
                if self.store.iter_n_children(it) == 1:
                    child = self.store.iter_children(it)
                    if self.store.get_value(child, 1) == "":
                        self.store.remove(child)
                        self._populate(it, full)
                view.expand_row(path, False)
        elif full:
            self.emit("file-selected", full)
