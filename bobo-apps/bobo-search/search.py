#!/usr/bin/env python3
# =============================================================================
# BoboSearch - Cautare globala pentru BOBO OS (APP 16)
# GTK4 overlay floating (Super+Space). Aplicatii, fisiere, web, calcule,
# conversii unitati, comenzi rapide.
# =============================================================================
import os
import sys
import ast
import glob
import math
import operator
import subprocess
import configparser
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gdk, Gio  # noqa: E402

APP_ID = "os.bobo.Search"

# operatori permisi pentru calculator (eval sigur via AST)
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.FloorDiv: operator.floordiv,
}
_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
          "log": math.log, "abs": abs, "round": round, "pi": math.pi, "e": math.e}


def safe_eval(expr):
    """Evalueaza o expresie matematica fara a executa cod arbitrar."""
    def _ev(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            return _OPS[type(node.op)](_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp):
            return _OPS[type(node.op)](_ev(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return _FUNCS[node.func.id](*[_ev(a) for a in node.args])
        if isinstance(node, ast.Name):
            return _FUNCS[node.id]
        raise ValueError("nepermis")
    return _ev(ast.parse(expr, mode="eval").body)


CONVERSIONS = {
    ("km", "miles"): lambda v: v * 0.621371,
    ("miles", "km"): lambda v: v / 0.621371,
    ("c", "f"): lambda v: v * 9 / 5 + 32,
    ("f", "c"): lambda v: (v - 32) * 5 / 9,
    ("kg", "lb"): lambda v: v * 2.20462,
    ("lb", "kg"): lambda v: v / 2.20462,
    ("m", "ft"): lambda v: v * 3.28084,
}

COMMANDS = {
    ">shutdown": (["systemctl", "poweroff"], "Opreste calculatorul"),
    ">restart": (["systemctl", "reboot"], "Reporneste"),
    ">lock": (["swaylock", "-f", "-c", "1a1a2e"], "Blocheaza ecranul"),
    ">settings": (["bobo-settings"], "Deschide setarile"),
    ">logout": (["pkill", "wayfire"], "Inchide sesiunea"),
}


def load_desktop_apps():
    """Indexeaza aplicatiile din fisierele .desktop."""
    apps = []
    seen = set()
    for d in ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]:
        for path in glob.glob(os.path.join(d, "*.desktop")):
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(path, encoding="utf-8")
                if "Desktop Entry" not in cp:
                    continue
                e = cp["Desktop Entry"]
                if e.get("NoDisplay", "false").lower() == "true":
                    continue
                name = e.get("Name", "")
                exec_cmd = e.get("Exec", "").split("%")[0].strip()
                if name and exec_cmd and name not in seen:
                    seen.add(name)
                    apps.append((name, exec_cmd, e.get("Icon", "application-x-executable")))
            except Exception:
                continue
    return apps


class BoboSearchWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_default_size(640, 480)
        self.set_decorated(False)
        self.add_css_class("bobo-search-win")
        self.apps = load_desktop_apps()
        self._apply_css()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.add_css_class("bobo-search-box")
        self.set_child(box)

        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text("Cauta aplicatii, fisiere, calcule, >comenzi ...")
        self.entry.add_css_class("bobo-search-entry")
        self.entry.connect("search-changed", self._on_changed)
        self.entry.connect("activate", self._on_activate)
        box.append(self.entry)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        self.results = Gtk.ListBox()
        self.results.connect("row-activated", lambda lb, row: self._launch(row))
        scroller.set_child(self.results)
        box.append(scroller)

        # Escape inchide
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)
        self.entry.grab_focus()

    def _apply_css(self):
        css = Gtk.CssProvider()
        css.load_from_data(b"""
        .bobo-search-box { background: rgba(22,33,62,0.97); border-radius: 14px;
            border: 1px solid #4a9eff; }
        .bobo-search-entry { font-size: 18px; padding: 14px; }
        row { padding: 8px 12px; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _on_key(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def _clear(self):
        child = self.results.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.results.remove(child)
            child = nxt

    def _add_result(self, icon, title, subtitle, action):
        row = Gtk.ListBoxRow()
        b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        b.append(Gtk.Image.new_from_icon_name(icon))
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        t = Gtk.Label(label=title, xalign=0)
        s = Gtk.Label(label=subtitle, xalign=0)
        s.add_css_class("dim-label")
        tb.append(t)
        tb.append(s)
        b.append(tb)
        row.set_child(b)
        row._action = action
        self.results.append(row)

    def _on_changed(self, entry):
        q = entry.get_text().strip()
        self._clear()
        if not q:
            return
        ql = q.lower()

        # 1. comenzi rapide
        if q.startswith(">"):
            for cmd, (action, desc) in COMMANDS.items():
                if q in cmd:
                    self._add_result("system-run-symbolic", cmd, desc, ("run", action))
            return

        # 2. calcul
        try:
            if any(c in q for c in "+-*/^") or "sqrt" in ql:
                val = safe_eval(q.replace("^", "**"))
                self._add_result("accessories-calculator-symbolic", str(val), "Rezultat calcul", ("copy", str(val)))
        except Exception:
            pass

        # 3. conversie unitati: "5 km in miles"
        parts = ql.split()
        if len(parts) == 4 and parts[2] == "in":
            try:
                val = float(parts[0])
                key = (parts[1], parts[3])
                if key in CONVERSIONS:
                    res = CONVERSIONS[key](val)
                    self._add_result("accessories-calculator-symbolic",
                                     "%.4g %s" % (res, parts[3]), "Conversie din %s" % parts[1], ("copy", str(res)))
            except Exception:
                pass

        # 4. aplicatii
        matches = [a for a in self.apps if ql in a[0].lower()][:8]
        for name, exec_cmd, icon in matches:
            self._add_result(icon, name, "Aplicatie", ("run", exec_cmd.split()))

        # 5. fisiere (cautare rapida in HOME)
        try:
            home = os.path.expanduser("~")
            found = 0
            for root, dirs, files in os.walk(home):
                dirs[:] = [d for d in dirs if not d.startswith(".")][:20]
                for f in files:
                    if ql in f.lower():
                        self._add_result("text-x-generic-symbolic", f, os.path.join(root, f),
                                         ("open", os.path.join(root, f)))
                        found += 1
                        if found >= 6:
                            raise StopIteration
        except StopIteration:
            pass
        except Exception:
            pass

        # 6. web fallback
        self._add_result("web-browser-symbolic", "Cauta pe web: %s" % q, "DuckDuckGo",
                         ("web", q))

    def _on_activate(self, entry):
        row = self.results.get_row_at_index(0)
        if row:
            self._launch(row)

    def _launch(self, row):
        if not hasattr(row, "_action"):
            return
        kind, payload = row._action
        if kind == "run":
            subprocess.Popen(payload if isinstance(payload, list) else [payload])
        elif kind == "open":
            subprocess.Popen(["xdg-open", payload])
        elif kind == "web":
            subprocess.Popen(["xdg-open", "https://duckduckgo.com/?q=" + payload.replace(" ", "+")])
        elif kind == "copy":
            try:
                p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
                p.communicate(payload.encode())
            except Exception:
                pass
        self.close()


class BoboSearchApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboSearchWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboSearch 1.0.0 (BOBO OS)")
        return 0
    return BoboSearchApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
