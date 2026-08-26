#!/usr/bin/env python3
"""
BoboCalc — spreadsheet for BOBO OS (GTK4).
Grid of cells with a formula bar (Excel-style), the FormulaEngine (100+ funcs),
import/export XLSX/CSV/ODS/JSON, conditional formatting, AI analysis, and chart
insertion. Selected cell edits its raw formula in the top bar; cells show results.
"""
import os
import sys
import json
import threading

sys.path.insert(0, "/usr/share/bobo-office")
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk  # noqa: E402

from calc.formula_engine import FormulaEngine, num_to_col
from calc.ai_analyst import AIAnalyst
from calc import chart_builder
from shared import file_formats

ROWS, COLS = 40, 12


class BoboCalcWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboCalc")
        self.set_default_size(1000, 700)
        self.raw = {}                # {(r,c): raw string}
        self.buttons = {}            # {(r,c): Gtk.Button}
        self.sel = (0, 0)
        self.path = None
        self.analyst = AIAnalyst()

        header = Gtk.HeaderBar(); self.set_titlebar(header)
        for icon, tip, cb in [
            ("document-open-symbolic", "Deschide", lambda *a: self.open_dialog()),
            ("document-save-symbolic", "Salvează (.bcalc)", lambda *a: self.save()),
        ]:
            b = Gtk.Button.new_from_icon_name(icon); b.set_tooltip_text(tip); b.connect("clicked", cb)
            header.pack_start(b)
        exp = Gtk.MenuButton(label="Export"); exp.set_menu_model(self._exp_menu()); header.pack_end(exp)
        chart = Gtk.Button(label="📊 Grafic"); chart.connect("clicked", lambda *a: self._chart_dialog()); header.pack_end(chart)
        ai = Gtk.Button(label="AI"); ai.connect("clicked", lambda *a: self._ai_dialog()); header.pack_end(ai)
        self._install_actions()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # formula bar
        fb = Gtk.Box(spacing=6, margin_top=4, margin_start=6, margin_end=6)
        self.cell_lbl = Gtk.Label(label="A1"); self.cell_lbl.set_size_request(48, -1)
        self.formula = Gtk.Entry(hexpand=True)
        self.formula.set_placeholder_text("Valoare sau =FORMULĂ (ex: =SUM(A1:A10))")
        self.formula.connect("activate", lambda *a: self._commit_formula())
        fb.append(self.cell_lbl); fb.append(self.formula); root.append(fb)

        # grid
        sw = Gtk.ScrolledWindow(); sw.set_vexpand(True)
        self.grid = Gtk.Grid(); self.grid.set_column_spacing(1); self.grid.set_row_spacing(1)
        self._build_grid()
        sw.set_child(self.grid); root.append(sw)
        self.status = Gtk.Label(xalign=0); self.status.add_css_class("dim-label"); root.append(self.status)
        self.set_child(root)
        self._css()

    def _css(self):
        p = Gtk.CssProvider()
        p.load_from_data(b".cell-sel { background:#4a9eff; color:#fff; } .cell-hdr { color:#8899bb; font-weight:bold; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _build_grid(self):
        # column headers
        for c in range(COLS):
            l = Gtk.Label(label=num_to_col(c)); l.add_css_class("cell-hdr"); l.set_size_request(80, 24)
            self.grid.attach(l, c + 1, 0, 1, 1)
        for r in range(ROWS):
            rl = Gtk.Label(label=str(r + 1)); rl.add_css_class("cell-hdr"); rl.set_size_request(36, 24)
            self.grid.attach(rl, 0, r + 1, 1, 1)
            for c in range(COLS):
                b = Gtk.Button(label=""); b.set_size_request(80, 24); b.set_has_frame(True)
                b.connect("clicked", lambda x, rr=r, cc=c: self._select(rr, cc))
                self.buttons[(r, c)] = b
                self.grid.attach(b, c + 1, r + 1, 1, 1)
        self._select(0, 0)

    # ------------------------------------------------------------------ editing
    def _select(self, r, c):
        old = self.buttons.get(self.sel)
        if old:
            old.remove_css_class("cell-sel")
        self.sel = (r, c)
        self.buttons[(r, c)].add_css_class("cell-sel")
        self.cell_lbl.set_text("%s%d" % (num_to_col(c), r + 1))
        self.formula.set_text(str(self.raw.get((r, c), "")))
        self.formula.grab_focus()

    def _commit_formula(self):
        r, c = self.sel
        self.raw[(r, c)] = self.formula.get_text()
        self._recompute()
        # move down
        if r + 1 < ROWS:
            self._select(r + 1, c)

    def _recompute(self):
        eng = FormulaEngine(self.raw)
        for (r, c), b in self.buttons.items():
            if (r, c) in self.raw and self.raw[(r, c)] != "":
                v = eng.evaluate(r, c)
                b.set_label(self._fmt(v))
                # conditional formatting: negatives red
                if isinstance(v, (int, float)) and v < 0:
                    b.get_style_context().add_class("error")
            else:
                b.set_label("")

    def _fmt(self, v):
        if isinstance(v, float):
            return ("%.4f" % v).rstrip("0").rstrip(".")
        return str(v)

    # ------------------------------------------------------------------ IO
    def _rows_matrix(self):
        eng = FormulaEngine(self.raw)
        out = []
        for r in range(ROWS):
            row = [eng.evaluate(r, c) for c in range(COLS)]
            if any(x != "" for x in row):
                out.append(row)
        return out

    def open_dialog(self):
        d = Gtk.FileDialog(); d.open(self, None, self._open_done)

    def _open_done(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        path = f.get_path(); ext = os.path.splitext(path)[1].lower()
        self.raw.clear()
        if ext == ".bcalc":
            with open(path) as fh:
                data = json.load(fh)
            for k, v in data.get("content", {}).get("cells", {}).items():
                r, c = map(int, k.split(","))
                self.raw[(r, c)] = v
        else:
            rows = file_formats.read_xlsx(path) if ext == ".xlsx" else file_formats.read_csv(path)
            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    if r < ROWS and c < COLS and val not in (None, ""):
                        self.raw[(r, c)] = val
        self.path = path
        self._recompute(); self.status.set_text("Deschis: %s" % path)

    def save(self):
        d = Gtk.FileDialog(); d.set_initial_name((os.path.basename(self.path) if self.path else "foaie") + ".bcalc")
        d.save(self, None, self._save_done)

    def _save_done(self, dialog, res):
        try:
            f = dialog.save_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        cells = {"%d,%d" % k: v for k, v in self.raw.items() if v != ""}
        with open(f.get_path(), "w", encoding="utf-8") as fh:
            json.dump({"title": os.path.basename(f.get_path()), "content": {"cells": cells}}, fh, ensure_ascii=False)
        self.status.set_text("Salvat: %s" % f.get_path())

    def _exp_menu(self):
        m = Gio.Menu()
        for fmt in ["xlsx", "csv", "json"]:
            m.append(fmt.upper(), "win.exp::" + fmt)
        return m

    def _install_actions(self):
        a = Gio.SimpleAction.new("exp", GLib.VariantType.new("s"))
        a.connect("activate", lambda ac, p: self._export(p.get_string()))
        self.add_action(a)

    def _export(self, fmt):
        d = Gtk.FileDialog(); d.set_initial_name("export." + fmt)
        d.save(self, None, lambda dd, r: self._do_export(dd, r, fmt))

    def _do_export(self, dialog, res, fmt):
        try:
            f = dialog.save_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        rows = self._rows_matrix(); out = f.get_path(); ok = False
        if fmt == "xlsx":
            ok = file_formats.write_xlsx(out, rows)
        elif fmt == "csv":
            ok = file_formats.write_csv(out, rows)
        elif fmt == "json":
            json.dump(rows, open(out, "w"), default=str); ok = True
        self.status.set_text(("Exportat: %s" % out) if ok else "Export eșuat")

    # ------------------------------------------------------------------ chart + AI
    def _chart_dialog(self):
        win = Gtk.Window(title="Grafic din selecție", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        kind = Gtk.DropDown.new_from_strings(["bar", "line", "pie", "scatter", "radar"])
        lbl = Gtk.Entry(); lbl.set_placeholder_text("Coloana etichete (ex: A)")
        val = Gtk.Entry(); val.set_placeholder_text("Coloana valori (ex: B)")
        go = Gtk.Button(label="Generează PNG"); go.add_css_class("suggested-action")
        go.connect("clicked", lambda *a: self._make_chart(["bar", "line", "pie", "scatter", "radar"][kind.get_selected()], lbl.get_text().strip().upper(), val.get_text().strip().upper(), win))
        for w in (Gtk.Label(label="Tip:"), kind, lbl, val, go):
            box.append(w)
        win.set_child(box); win.present()

    def _make_chart(self, kind, lcol, vcol, win):
        from calc.formula_engine import col_to_num
        eng = FormulaEngine(self.raw)
        labels, values = [], []
        try:
            lc = col_to_num(lcol); vc = col_to_num(vcol)
        except Exception:
            self.status.set_text("Coloane invalide"); return
        for r in range(ROWS):
            lv = eng.evaluate(r, lc); vv = eng.evaluate(r, vc)
            if lv != "" and isinstance(vv, (int, float)):
                labels.append(str(lv)); values.append(vv)
        out = os.path.expanduser("~/Imagini/bobo-calc-chart.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        ok = chart_builder.build(kind, labels, values, out)
        win.close()
        self.status.set_text(("Grafic salvat: %s" % out) if ok else "Grafic eșuat (lipsă matplotlib?)")

    def _ai_dialog(self):
        win = Gtk.Window(title="BoboCalc AI", transient_for=self, modal=True)
        win.set_default_size(460, 300)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        q = Gtk.Entry(); q.set_placeholder_text("Ex: suma coloanei B, sau grafic evoluție lunară")
        out = Gtk.Label(xalign=0, wrap=True, selectable=True)
        ask = Gtk.Button(label="Întreabă"); ask.add_css_class("suggested-action")
        def do(*a):
            out.set_text("…")
            rows = self._rows_matrix()
            def work():
                res = self.analyst.analyze(q.get_text(), rows)
                GLib.idle_add(out.set_text, res)
            threading.Thread(target=work, daemon=True).start()
        ask.connect("clicked", do); q.connect("activate", do)
        for w in (q, ask, out):
            box.append(w)
        win.set_child(box); win.present()


class BoboCalcApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.Calc", flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboCalcWindow(self)
        self.win.present()

    def do_open(self, files, n, hint):
        self.do_activate()


def main():
    if "--version" in sys.argv:
        print("BoboCalc 1.0.0 (BOBO OS)"); return 0
    return BoboCalcApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
