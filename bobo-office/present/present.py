#!/usr/bin/env python3
"""
BoboPresent — presentations for BOBO OS (GTK4).
Slide list + editor (title/body/theme), live PNG preview, AI "generate deck from
a prompt", import PPTX, export PDF/PPTX/HTML/MP4 (+ avatar tutorial video), and a
fullscreen teleprompter present mode.
"""
import os
import sys
import threading

sys.path.insert(0, "/usr/share/bobo-office")
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, GdkPixbuf, Gdk  # noqa: E402

from present.slide_editor import SlideDeck, THEMES
from present import video_exporter  # noqa: F401 (used via deck.export_mp4)

sys.path.insert(0, "/usr/share/bobo-office")
try:
    from shared.ai_client import AIClient
except Exception:
    AIClient = None


class BoboPresentWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboPresent")
        self.set_default_size(1100, 720)
        self.deck = SlideDeck()
        self.idx = 0
        self.ai = AIClient() if AIClient else None

        header = Gtk.HeaderBar(); self.set_titlebar(header)
        gen = Gtk.Button(label="✨ Generează cu AI"); gen.connect("clicked", lambda *a: self._ai_dialog()); header.pack_start(gen)
        imp = Gtk.Button(label="Import PPTX"); imp.connect("clicked", lambda *a: self._import()); header.pack_start(imp)
        play = Gtk.Button(label="▶ Prezintă"); play.add_css_class("suggested-action"); play.connect("clicked", lambda *a: self._present()); header.pack_end(play)
        exp = Gtk.MenuButton(label="Export"); exp.set_menu_model(self._exp_menu()); header.pack_end(exp)
        self._install_actions()

        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL); self.set_child(split)
        # left: slide list
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); left.set_size_request(200, -1)
        self.listbox = Gtk.ListBox(); self.listbox.connect("row-selected", self._on_sel)
        lsw = Gtk.ScrolledWindow(); lsw.set_vexpand(True); lsw.set_child(self.listbox); left.append(lsw)
        addbar = Gtk.Box(spacing=4, margin_top=4, margin_start=4, margin_bottom=4)
        for lbl, cb in [("+", lambda *a: self._add()), ("−", lambda *a: self._del()),
                       ("↑", lambda *a: self._move(-1)), ("↓", lambda *a: self._move(1))]:
            b = Gtk.Button(label=lbl); b.connect("clicked", cb); addbar.append(b)
        left.append(addbar); split.set_start_child(left); split.set_resize_start_child(False)

        # right: editor + preview
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_start=8, margin_end=8)
        self.title_e = Gtk.Entry(); self.title_e.set_placeholder_text("Titlu slide"); self.title_e.connect("changed", self._edit)
        right.append(self.title_e)
        self.body_v = Gtk.TextView(); self.body_v.set_wrap_mode(Gtk.WrapMode.WORD)
        self.body_v.get_buffer().connect("changed", self._edit)
        bsw = Gtk.ScrolledWindow(); bsw.set_min_content_height(140); bsw.set_child(self.body_v); right.append(bsw)
        trow = Gtk.Box(spacing=6)
        trow.append(Gtk.Label(label="Temă:"))
        self.theme_dd = Gtk.DropDown.new_from_strings(list(THEMES.keys())); self.theme_dd.connect("notify::selected", self._edit)
        trow.append(self.theme_dd); right.append(trow)
        self.preview = Gtk.Picture(); self.preview.set_size_request(-1, 320); self.preview.set_content_fit(Gtk.ContentFit.CONTAIN)
        right.append(self.preview)
        self.status = Gtk.Label(xalign=0); self.status.add_css_class("dim-label"); right.append(self.status)
        split.set_end_child(right)

        self._refresh_list(); self.listbox.select_row(self.listbox.get_row_at_index(0))

    # ------------------------------------------------------------------ list
    def _refresh_list(self):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling(); self.listbox.remove(child); child = nxt
        for i, s in enumerate(self.deck.slides):
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label="%d. %s" % (i + 1, s.title[:22]), xalign=0, margin_top=6, margin_bottom=6, margin_start=6))
            self.listbox.append(row)

    def _on_sel(self, lb, row):
        if not row:
            return
        self.idx = row.get_index()
        s = self.deck.slides[self.idx]
        self.title_e.set_text(s.title)
        self.body_v.get_buffer().set_text(s.body)
        try:
            self.theme_dd.set_selected(list(THEMES.keys()).index(s.theme))
        except ValueError:
            pass
        self._render_preview()

    def _edit(self, *a):
        if self.idx >= len(self.deck.slides):
            return
        s = self.deck.slides[self.idx]
        s.title = self.title_e.get_text()
        b = self.body_v.get_buffer()
        s.body = b.get_text(b.get_start_iter(), b.get_end_iter(), True)
        s.theme = list(THEMES.keys())[self.theme_dd.get_selected()]
        self._render_preview()

    def _render_preview(self):
        s = self.deck.slides[self.idx]
        out = "/tmp/bobo-present-preview.png"
        if self.deck.render_png(s, out):
            self.preview.set_filename(out)

    def _add(self):
        self.deck.add(self.idx); self._refresh_list(); self.listbox.select_row(self.listbox.get_row_at_index(self.idx + 1))

    def _del(self):
        self.deck.remove(self.idx); self._refresh_list(); self.listbox.select_row(self.listbox.get_row_at_index(min(self.idx, len(self.deck.slides) - 1)))

    def _move(self, d):
        self.idx = self.deck.move(self.idx, d); self._refresh_list(); self.listbox.select_row(self.listbox.get_row_at_index(self.idx))

    # ------------------------------------------------------------------ AI / import / export
    def _ai_dialog(self):
        win = Gtk.Window(title="Generează prezentare", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        e = Gtk.Entry(); e.set_placeholder_text("Subiect (ex: Istoria BOBO OS în 5 slide-uri)")
        go = Gtk.Button(label="Generează"); go.add_css_class("suggested-action")
        go.connect("clicked", lambda *a: (self._ai_generate(e.get_text()), win.close()))
        box.append(e); box.append(go); win.set_child(box); win.present()

    def _ai_generate(self, topic):
        if not (self.ai and self.ai.available()):
            self.status.set_text("AI offline — pornește Ollama."); return
        self.status.set_text("Generez slide-uri…")
        def work():
            prompt = ("Creează o prezentare despre: %s. Format: fiecare slide pe linii, "
                      "'TITLU: ...' apoi 'BODY: ...' separate prin '---'." % topic)
            txt = self.ai.ask(prompt)
            slides = self._parse(txt)
            GLib.idle_add(self._apply_generated, slides)
        threading.Thread(target=work, daemon=True).start()

    def _parse(self, txt):
        from present.slide_editor import Slide
        out = []
        for block in txt.split("---"):
            title, body = "Slide", ""
            for line in block.strip().splitlines():
                if line.upper().startswith("TITLU"):
                    title = line.split(":", 1)[-1].strip()
                elif line.upper().startswith("BODY"):
                    body = line.split(":", 1)[-1].strip()
                else:
                    body += ("\n" + line.strip()) if line.strip() else ""
            if title or body:
                out.append(Slide(title, body.strip()))
        return out or None

    def _apply_generated(self, slides):
        if slides:
            self.deck.slides = slides; self.idx = 0
            self._refresh_list(); self.listbox.select_row(self.listbox.get_row_at_index(0))
            self.status.set_text("Generat %d slide-uri." % len(slides))
        else:
            self.status.set_text("Generare eșuată.")

    def _import(self):
        d = Gtk.FileDialog(); d.open(self, None, self._import_done)

    def _import_done(self, dialog, res):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        from shared import file_formats
        from present.slide_editor import Slide
        texts = file_formats.read_pptx_texts(f.get_path())
        self.deck.slides = [Slide(t.split("\n")[0][:60] or "Slide", "\n".join(t.split("\n")[1:])) for t in texts] or self.deck.slides
        self.idx = 0; self._refresh_list(); self.listbox.select_row(self.listbox.get_row_at_index(0))

    def _exp_menu(self):
        m = Gio.Menu()
        for fmt in ["pdf", "pptx", "html", "mp4"]:
            m.append(fmt.upper(), "win.pexp::" + fmt)
        return m

    def _install_actions(self):
        a = Gio.SimpleAction.new("pexp", GLib.VariantType.new("s"))
        a.connect("activate", lambda ac, p: self._export(p.get_string()))
        self.add_action(a)

    def _export(self, fmt):
        d = Gtk.FileDialog(); d.set_initial_name("prezentare." + fmt)
        d.save(self, None, lambda dd, r: self._do_export(dd, r, fmt))

    def _do_export(self, dialog, res, fmt):
        try:
            f = dialog.save_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        out = f.get_path(); self.status.set_text("Export %s…" % fmt)
        def work():
            ok = {"pdf": self.deck.export_pdf, "pptx": self.deck.export_pptx,
                  "html": self.deck.export_html, "mp4": self.deck.export_mp4}[fmt](out)
            GLib.idle_add(self.status.set_text, ("Exportat: %s" % out) if ok else "Export eșuat")
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ present mode
    def _present(self):
        win = Gtk.Window(title="Prezentare"); win.fullscreen()
        pic = Gtk.Picture(); pic.set_content_fit(Gtk.ContentFit.CONTAIN); win.set_child(pic)
        state = {"i": 0}
        def show(i):
            if 0 <= i < len(self.deck.slides):
                state["i"] = i
                out = "/tmp/bobo-present-full.png"
                self.deck.render_png(self.deck.slides[i], out, size=(1920, 1080))
                pic.set_filename(out)
        show(0)
        key = Gtk.EventControllerKey()
        def on_key(c, kv, kc, st):
            if kv in (Gdk.KEY_Right, Gdk.KEY_space, Gdk.KEY_Page_Down):
                show(state["i"] + 1)
            elif kv in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
                show(state["i"] - 1)
            elif kv == Gdk.KEY_Escape:
                win.close()
            return True
        key.connect("key-pressed", on_key); win.add_controller(key); win.present()


class BoboPresentApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.Present", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboPresentWindow(self)
        self.win.present()


def main():
    if "--version" in sys.argv:
        print("BoboPresent 1.0.0 (BOBO OS)"); return 0
    return BoboPresentApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
