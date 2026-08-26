#!/usr/bin/env python3
"""
BoboMind — mind maps for BOBO OS (GTK4 + Cairo DrawingArea).
Interactive radial/tree map: add child/sibling, rename, delete, click to select.
AI can generate a map from a topic. Export to PNG, SVG and FreeMind (.mm) XML.
"""
import os
import sys
import math
import threading

sys.path.insert(0, "/usr/share/bobo-office")
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gdk  # noqa: E402

try:
    from shared.ai_client import AIClient
except Exception:
    AIClient = None


class Node:
    _id = 0
    def __init__(self, text, parent=None):
        Node._id += 1
        self.id = Node._id
        self.text = text
        self.parent = parent
        self.children = []
        self.x = 0.0
        self.y = 0.0

    def add(self, text):
        n = Node(text, self); self.children.append(n); return n


class BoboMindWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboMind")
        self.set_default_size(1000, 700)
        self.root = Node("Idee centrală")
        self.selected = self.root
        self.ai = AIClient() if AIClient else None

        header = Gtk.HeaderBar(); self.set_titlebar(header)
        for lbl, cb in [("+ Copil", lambda *a: self._add_child()), ("+ Frate", lambda *a: self._add_sibling()),
                       ("Redenumește", lambda *a: self._rename()), ("Șterge", lambda *a: self._delete())]:
            b = Gtk.Button(label=lbl); b.connect("clicked", cb); header.pack_start(b)
        ai = Gtk.Button(label="✨ AI"); ai.connect("clicked", lambda *a: self._ai_dialog()); header.pack_end(ai)
        exp = Gtk.MenuButton(label="Export"); exp.set_menu_model(self._menu()); header.pack_end(exp)
        self._install_actions()

        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self._draw)
        self.area.set_hexpand(True); self.area.set_vexpand(True)
        click = Gtk.GestureClick(); click.connect("released", self._on_click); self.area.add_controller(click)
        self.set_child(self.area)

    # ------------------------------------------------------------------ layout + draw
    def _layout(self, w, h):
        self.root.x, self.root.y = w / 2, h / 2
        self._layout_children(self.root, 0, 2 * math.pi, 160)

    def _layout_children(self, node, a0, a1, radius):
        n = len(node.children)
        if not n:
            return
        for i, ch in enumerate(node.children):
            ang = a0 + (a1 - a0) * (i + 0.5) / n
            ch.x = node.x + radius * math.cos(ang)
            ch.y = node.y + radius * math.sin(ang)
            self._layout_children(ch, ang - 0.5, ang + 0.5, radius * 0.7)

    def _draw(self, area, cr, w, h, *a):
        cr.set_source_rgb(0.10, 0.10, 0.18); cr.rectangle(0, 0, w, h); cr.fill()
        self._layout(w, h)
        self._draw_edges(cr, self.root)
        self._draw_nodes(cr, self.root)

    def _draw_edges(self, cr, node):
        for ch in node.children:
            cr.set_source_rgba(0.29, 0.62, 1.0, 0.5); cr.set_line_width(2)
            cr.move_to(node.x, node.y); cr.line_to(ch.x, ch.y); cr.stroke()
            self._draw_edges(cr, ch)

    def _draw_nodes(self, cr, node):
        sel = node is self.selected
        tw = max(60, len(node.text) * 8 + 20)
        cr.set_source_rgb(0.29, 0.62, 1.0) if sel else cr.set_source_rgb(0.086, 0.13, 0.24)
        self._round_rect(cr, node.x - tw / 2, node.y - 14, tw, 28, 8); cr.fill()
        cr.set_source_rgb(1, 1, 1) if sel else cr.set_source_rgb(0.9, 0.92, 0.96)
        cr.select_font_face("Inter"); cr.set_font_size(13)
        ext = cr.text_extents(node.text)
        cr.move_to(node.x - ext.width / 2, node.y + 5); cr.show_text(node.text)
        node._box = (node.x - tw / 2, node.y - 14, tw, 28)
        for ch in node.children:
            self._draw_nodes(cr, ch)

    def _round_rect(self, cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _on_click(self, g, n, x, y):
        hit = self._hit(self.root, x, y)
        if hit:
            self.selected = hit; self.area.queue_draw()

    def _hit(self, node, x, y):
        b = getattr(node, "_box", None)
        if b and b[0] <= x <= b[0] + b[2] and b[1] <= y <= b[1] + b[3]:
            return node
        for ch in node.children:
            r = self._hit(ch, x, y)
            if r:
                return r
        return None

    # ------------------------------------------------------------------ edit
    def _add_child(self):
        self.selected = self.selected.add("Nod nou"); self.area.queue_draw(); self._rename()

    def _add_sibling(self):
        p = self.selected.parent or self.root
        self.selected = p.add("Nod nou"); self.area.queue_draw(); self._rename()

    def _delete(self):
        p = self.selected.parent
        if p:
            p.children.remove(self.selected); self.selected = p; self.area.queue_draw()

    def _rename(self):
        win = Gtk.Window(title="Redenumește", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
        e = Gtk.Entry(); e.set_text(self.selected.text)
        e.connect("activate", lambda *a: (self._set_text(e.get_text()), win.close()))
        b = Gtk.Button(label="OK"); b.connect("clicked", lambda *a: (self._set_text(e.get_text()), win.close()))
        box.append(e); box.append(b); win.set_child(box); win.present()

    def _set_text(self, t):
        self.selected.text = t or self.selected.text; self.area.queue_draw()

    # ------------------------------------------------------------------ AI
    def _ai_dialog(self):
        win = Gtk.Window(title="Generează hartă", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        e = Gtk.Entry(); e.set_placeholder_text("Subiect (ex: Planificarea unui proiect)")
        go = Gtk.Button(label="Generează"); go.add_css_class("suggested-action")
        go.connect("clicked", lambda *a: (self._ai_gen(e.get_text()), win.close()))
        box.append(e); box.append(go); win.set_child(box); win.present()

    def _ai_gen(self, topic):
        if not (self.ai and self.ai.available()):
            return
        def work():
            txt = self.ai.ask("Creează o structură de mind-map pentru '%s'. Format: linii cu "
                              "indentare prin '-' pentru nivel (ex: '- Ramură', '-- Sub-ramură')." % topic)
            GLib.idle_add(self._build_from_outline, topic, txt)
        threading.Thread(target=work, daemon=True).start()

    def _build_from_outline(self, topic, txt):
        self.root = Node(topic); self.selected = self.root
        stack = [(0, self.root)]
        for line in txt.splitlines():
            s = line.rstrip()
            if not s.strip().lstrip("-"):
                continue
            level = len(s) - len(s.lstrip("-"))
            label = s.lstrip("- ").strip()
            if not label:
                continue
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else self.root
            node = parent.add(label)
            stack.append((level, node))
        self.area.queue_draw()

    # ------------------------------------------------------------------ export
    def _menu(self):
        m = Gio_menu()
        for fmt in ["png", "svg", "mm"]:
            m.append(fmt.upper(), "win.mexp::" + fmt)
        return m

    def _install_actions(self):
        from gi.repository import Gio
        a = Gio.SimpleAction.new("mexp", GLib.VariantType.new("s"))
        a.connect("activate", lambda ac, p: self._export(p.get_string()))
        self.add_action(a)

    def _export(self, fmt):
        d = Gtk.FileDialog(); d.set_initial_name("harta." + fmt)
        d.save(self, None, lambda dd, r: self._do_export(dd, r, fmt))

    def _do_export(self, dialog, res, fmt):
        try:
            f = dialog.save_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        out = f.get_path()
        if fmt == "mm":
            self._export_freemind(out)
        else:
            self._export_image(out, fmt)

    def _export_image(self, out, fmt):
        try:
            import cairo
            W, H = 1400, 900
            surf = (cairo.SVGSurface(out, W, H) if fmt == "svg"
                    else cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H))
            cr = cairo.Context(surf)
            self.area.set_size_request(W, H)
            self._layout(W, H); self._draw_edges(cr, self.root); self._draw_nodes(cr, self.root)
            if fmt == "png":
                surf.write_to_png(out)
            surf.finish()
        except Exception as e:
            print("[mind export] %s" % e)

    def _export_freemind(self, out):
        def node_xml(n):
            inner = "".join(node_xml(c) for c in n.children)
            safe = n.text.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
            return '<node TEXT="%s">%s</node>' % (safe, inner)
        xml = '<map version="1.0.1">%s</map>' % node_xml(self.root)
        open(out, "w", encoding="utf-8").write(xml)


def Gio_menu():
    from gi.repository import Gio
    return Gio.Menu()


class BoboMindApp(Gtk.Application):
    def __init__(self):
        from gi.repository import Gio
        super().__init__(application_id="os.bobo.Mind", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboMindWindow(self)
        self.win.present()


def main():
    if "--version" in sys.argv:
        print("BoboMind 1.0.0 (BOBO OS)"); return 0
    return BoboMindApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
