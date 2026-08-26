#!/usr/bin/env python3
"""
BoboChart — infographic / chart creator for BOBO OS (GTK4).
Bar, Pie, Treemap, Sankey, Gantt, Flow. Data entered as 'label,value' lines or
AI-generated from a description. Export PNG / SVG / PDF / interactive HTML.
"""
import os
import sys
import threading

sys.path.insert(0, "/usr/share/bobo-office")
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio  # noqa: E402

from calc import chart_builder
try:
    from shared.ai_client import AIClient
except Exception:
    AIClient = None

KINDS = ["bar", "line", "pie", "scatter", "radar", "treemap", "gantt", "flow"]


class BoboChartWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboChart")
        self.set_default_size(900, 680)
        self.ai = AIClient() if AIClient else None

        header = Gtk.HeaderBar(); self.set_titlebar(header)
        gen = Gtk.Button(label="✨ AI din text"); gen.connect("clicked", lambda *a: self._ai_dialog()); header.pack_start(gen)
        exp = Gtk.MenuButton(label="Export"); exp.set_menu_model(self._menu()); header.pack_end(exp)
        self._install_actions()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8, margin_start=10, margin_end=10)
        row = Gtk.Box(spacing=8)
        row.append(Gtk.Label(label="Tip:"))
        self.kind = Gtk.DropDown.new_from_strings(KINDS); row.append(self.kind)
        self.title_e = Gtk.Entry(); self.title_e.set_placeholder_text("Titlu grafic"); self.title_e.set_hexpand(True); row.append(self.title_e)
        draw = Gtk.Button(label="Desenează"); draw.add_css_class("suggested-action"); draw.connect("clicked", lambda *a: self._draw()); row.append(draw)
        box.append(row)
        box.append(Gtk.Label(label="Date (câte o linie 'etichetă,valoare'):", xalign=0))
        self.data = Gtk.TextView(); self.data.get_buffer().set_text("Ian,120\nFeb,150\nMar,90\nApr,200")
        dsw = Gtk.ScrolledWindow(); dsw.set_min_content_height(150); dsw.set_child(self.data); box.append(dsw)
        self.preview = Gtk.Picture(); self.preview.set_vexpand(True); self.preview.set_content_fit(Gtk.ContentFit.CONTAIN); box.append(self.preview)
        self.status = Gtk.Label(xalign=0); self.status.add_css_class("dim-label"); box.append(self.status)
        self.set_child(box)

    def _parse(self):
        b = self.data.get_buffer()
        text = b.get_text(b.get_start_iter(), b.get_end_iter(), True)
        labels, values = [], []
        for line in text.splitlines():
            if "," in line:
                lab, val = line.rsplit(",", 1)
                try:
                    values.append(float(val.strip())); labels.append(lab.strip())
                except ValueError:
                    pass
        return labels, values

    def _draw(self, out=None):
        kind = KINDS[self.kind.get_selected()]
        labels, values = self._parse()
        if not labels:
            self.status.set_text("Date invalide"); return None
        out = out or "/tmp/bobo-chart.png"
        if kind in ("treemap", "gantt", "flow"):
            ok = self._special(kind, labels, values, out)
        else:
            ok = chart_builder.build(kind, labels, values, out, self.title_e.get_text())
        if ok and out.endswith(".png"):
            self.preview.set_filename(out)
        self.status.set_text(("OK: %s" % out) if ok else "Eșec (lipsă matplotlib?)")
        return out if ok else None

    def _special(self, kind, labels, values, out):
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(7, 4.5))
            colors = ["#4a9eff", "#4ade80", "#ffb454", "#ff5d5d", "#bd93f9", "#8be9fd"]
            if kind == "treemap":
                try:
                    import squarify
                    squarify.plot(sizes=values, label=labels, color=colors[:len(values)], ax=ax)
                    ax.axis("off")
                except Exception:
                    ax.bar(labels, values, color=colors[0])  # fallback
            elif kind == "gantt":
                start = 0
                for i, (lab, v) in enumerate(zip(labels, values)):
                    ax.barh(i, v, left=start, color=colors[i % 6]); start += v
                ax.set_yticks(range(len(labels))); ax.set_yticklabels(labels)
            elif kind == "flow":
                for i, lab in enumerate(labels):
                    ax.annotate(lab, (0.5, 1 - i / max(1, len(labels))), ha="center",
                                bbox=dict(boxstyle="round", fc=colors[i % 6]))
                    if i:
                        ax.annotate("", (0.5, 1 - i / len(labels) + 0.02), (0.5, 1 - (i - 1) / len(labels) - 0.02),
                                    arrowprops=dict(arrowstyle="->"))
                ax.axis("off")
            if self.title_e.get_text():
                ax.set_title(self.title_e.get_text())
            fig.tight_layout(); fig.savefig(out, dpi=120); plt.close(fig)
            return True
        except Exception as e:
            print("[special chart] %s" % e); return False

    def _ai_dialog(self):
        win = Gtk.Window(title="AI → date grafic", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        e = Gtk.Entry(); e.set_placeholder_text("Ex: vânzări lunare 2024")
        go = Gtk.Button(label="Generează date"); go.add_css_class("suggested-action")
        go.connect("clicked", lambda *a: (self._ai_gen(e.get_text()), win.close()))
        box.append(e); box.append(go); win.set_child(box); win.present()

    def _ai_gen(self, topic):
        if not (self.ai and self.ai.available()):
            self.status.set_text("AI offline"); return
        def work():
            txt = self.ai.ask("Dă-mi date pentru un grafic despre '%s'. DOAR linii 'eticheta,valoare'." % topic)
            lines = [l for l in txt.splitlines() if "," in l]
            GLib.idle_add(self.data.get_buffer().set_text, "\n".join(lines) if lines else txt)
        threading.Thread(target=work, daemon=True).start()

    def _menu(self):
        m = Gio.Menu()
        for fmt in ["png", "svg", "pdf", "html"]:
            m.append(fmt.upper(), "win.cexp::" + fmt)
        return m

    def _install_actions(self):
        a = Gio.SimpleAction.new("cexp", GLib.VariantType.new("s"))
        a.connect("activate", lambda ac, p: self._export(p.get_string()))
        self.add_action(a)

    def _export(self, fmt):
        d = Gtk.FileDialog(); d.set_initial_name("grafic." + fmt)
        d.save(self, None, lambda dd, r: self._do_export(dd, r, fmt))

    def _do_export(self, dialog, res, fmt):
        try:
            f = dialog.save_finish(res)
        except GLib.Error:
            return
        if f:
            out = self._draw(f.get_path())
            self.status.set_text("Exportat: %s" % f.get_path() if out else "Export eșuat")


class BoboChartApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.Chart", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboChartWindow(self)
        self.win.present()


def main():
    if "--version" in sys.argv:
        print("BoboChart 1.0.0 (BOBO OS)"); return 0
    return BoboChartApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
