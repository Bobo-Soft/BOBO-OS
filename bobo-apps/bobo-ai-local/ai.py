#!/usr/bin/env python3
# =============================================================================
# BoboAI Local - GUI pentru modele AI locale (Ollama) pentru BOBO OS (APP 30)
# GTK4. Chat cu streaming, model manager (pull/delete), system prompt, RAG
# (drag PDF/text), export conversatie.
# =============================================================================
import os
import sys
import json
import time
import threading
import urllib.request
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk, Pango  # noqa: E402

APP_ID = "os.bobo.AILocal"
OLLAMA = "http://127.0.0.1:11434"
HISTORY_DIR = os.path.expanduser("~/.local/share/bobo-ai-local")


def ollama_get(path):
    try:
        return json.loads(urllib.request.urlopen(OLLAMA + path, timeout=10).read())
    except Exception:
        return {}


def list_models():
    data = ollama_get("/api/tags")
    return [m["name"] for m in data.get("models", [])]


class BoboAIWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboAI Local")
        self.set_default_size(820, 700)
        self.model = None
        self.messages = []
        self.system_prompt = "Esti BOBO AI, un asistent util care raspunde concis in limba utilizatorului."
        self.rag_context = ""

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        models = list_models()
        self.model_dd = Gtk.DropDown.new_from_strings(models or ["(niciun model)"])
        if models:
            self.model = models[0]
        self.model_dd.connect("notify::selected", self._on_model_changed)
        header.pack_start(self.model_dd)
        mgr = Gtk.Button.new_from_icon_name("system-software-install-symbolic")
        mgr.set_tooltip_text("Manager modele")
        mgr.connect("clicked", lambda *a: self.model_manager())
        header.pack_start(mgr)
        sys_btn = Gtk.Button.new_from_icon_name("preferences-system-symbolic")
        sys_btn.set_tooltip_text("System prompt")
        sys_btn.connect("clicked", lambda *a: self.edit_system())
        header.pack_end(sys_btn)
        new_btn = Gtk.Button.new_from_icon_name("document-new-symbolic")
        new_btn.set_tooltip_text("Conversatie noua")
        new_btn.connect("clicked", lambda *a: self.new_chat())
        header.pack_end(new_btn)
        exp = Gtk.Button.new_from_icon_name("document-save-symbolic")
        exp.set_tooltip_text("Exporta conversatia")
        exp.connect("clicked", lambda *a: self.export_chat())
        header.pack_end(exp)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(box)

        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_vexpand(True)
        self.chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.chat_box.set_margin_top(12)
        self.chat_box.set_margin_bottom(12)
        self.chat_box.set_margin_start(16)
        self.chat_box.set_margin_end(16)
        self.scroller.set_child(self.chat_box)
        box.append(self.scroller)

        # input
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        input_row.set_margin_top(6)
        input_row.set_margin_bottom(8)
        input_row.set_margin_start(10)
        input_row.set_margin_end(10)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Scrie un mesaj... (sau trage un PDF/text pentru RAG)")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", lambda *a: self.send())
        send_btn = Gtk.Button.new_from_icon_name("document-send-symbolic")
        send_btn.add_css_class("suggested-action")
        send_btn.connect("clicked", lambda *a: self.send())
        input_row.append(self.entry)
        input_row.append(send_btn)
        box.append(input_row)

        # drag & drop fisiere pentru RAG
        drop = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.scroller.add_controller(drop)

        self._css()
        if not list_models():
            self._add_bubble("system", "Ollama nu are modele. Apasa managerul de modele si descarca unul (ex: llama3).")

    def _css(self):
        p = Gtk.CssProvider()
        p.load_from_data(b"""
        .bubble-user { background: #4a9eff; color: #fff; border-radius: 14px 14px 2px 14px; padding: 10px 14px; }
        .bubble-ai { background: #16213e; color: #e8eaf6; border-radius: 14px 14px 14px 2px; padding: 10px 14px; }
        .bubble-system { color: #ffb454; }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _add_bubble(self, role, text):
        align = Gtk.Align.END if role == "user" else Gtk.Align.START
        lbl = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True)
        lbl.set_max_width_chars(60)
        lbl.add_css_class("bubble-%s" % role)
        lbl.set_halign(align)
        self.chat_box.append(lbl)
        GLib.idle_add(self._scroll_bottom)
        return lbl

    def _scroll_bottom(self):
        adj = self.scroller.get_vadjustment()
        adj.set_value(adj.get_upper())
        return False

    # ----------------------------------------------------------- send
    def send(self):
        text = self.entry.get_text().strip()
        if not text or not self.model:
            return
        self.entry.set_text("")
        self._add_bubble("user", text)
        prompt = text
        if self.rag_context:
            prompt = "Context document:\n%s\n\nIntrebare: %s" % (self.rag_context[:6000], text)
        self.messages.append({"role": "user", "content": prompt})
        ai_label = self._add_bubble("ai", "...")
        threading.Thread(target=self._stream, args=(ai_label,), daemon=True).start()

    def _stream(self, ai_label):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": self.system_prompt}] + self.messages,
            "stream": True,
        }
        try:
            req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            full = ""
            with urllib.request.urlopen(req, timeout=120) as resp:
                for line in resp:
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    piece = chunk.get("message", {}).get("content", "")
                    full += piece
                    GLib.idle_add(ai_label.set_text, full)
                    GLib.idle_add(self._scroll_bottom)
            self.messages.append({"role": "assistant", "content": full})
        except Exception as e:
            GLib.idle_add(ai_label.set_text, "Eroare: %s (este pornit 'ollama serve'?)" % e)

    # ----------------------------------------------------------- RAG
    def _on_drop(self, target, value, x, y):
        if value and value.get_path():
            path = value.get_path()
            threading.Thread(target=self._load_rag, args=(path,), daemon=True).start()
            return True
        return False

    def _load_rag(self, path):
        text = ""
        try:
            if path.lower().endswith(".pdf"):
                import fitz
                doc = fitz.open(path)
                text = "\n".join(page.get_text() for page in doc)
            else:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
        except Exception as e:
            text = ""
            GLib.idle_add(self._add_bubble, "system", "Nu pot citi documentul: %s" % e)
            return
        self.rag_context = text
        GLib.idle_add(self._add_bubble, "system", "Document incarcat (%d caractere). Pune intrebari despre el." % len(text))

    # ----------------------------------------------------------- model mgr
    def model_manager(self):
        win = Gtk.Window(title="Manager modele Ollama", transient_for=self, modal=True)
        win.set_default_size(440, 400)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
        pull_row = Gtk.Box(spacing=6)
        entry = Gtk.Entry(placeholder_text="Nume model (ex: llama3, mistral, gemma)")
        entry.set_hexpand(True)
        pull = Gtk.Button(label="Descarca")
        pull.add_css_class("suggested-action")
        pull.connect("clicked", lambda *a: self._pull_model(entry.get_text(), win))
        pull_row.append(entry)
        pull_row.append(pull)
        box.append(pull_row)
        lst = Gtk.ListBox()
        for m in list_models():
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lbl = Gtk.Label(label=m, xalign=0)
            lbl.set_hexpand(True)
            row.append(lbl)
            dele = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            dele.connect("clicked", lambda x, name=m: self._delete_model(name))
            row.append(dele)
            r = Gtk.ListBoxRow()
            r.set_child(row)
            lst.append(r)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(lst)
        box.append(sw)
        win.set_child(box)
        win.present()

    def _pull_model(self, name, win):
        if not name:
            return
        win.close()
        self._add_bubble("system", "Descarc modelul %s... (poate dura)" % name)

        def do():
            try:
                req = urllib.request.Request(OLLAMA + "/api/pull", data=json.dumps({"name": name}).encode())
                urllib.request.urlopen(req, timeout=3600).read()
                GLib.idle_add(self._refresh_models)
                GLib.idle_add(self._add_bubble, "system", "Model %s descarcat." % name)
            except Exception as e:
                GLib.idle_add(self._add_bubble, "system", "Descarcare esuata: %s" % e)
        threading.Thread(target=do, daemon=True).start()

    def _delete_model(self, name):
        try:
            req = urllib.request.Request(OLLAMA + "/api/delete", data=json.dumps({"name": name}).encode(), method="DELETE")
            urllib.request.urlopen(req, timeout=30)
            self._refresh_models()
        except Exception:
            pass

    def _refresh_models(self):
        models = list_models()
        self.model_dd.set_model(Gtk.StringList.new(models or ["(niciun model)"]))
        if models:
            self.model = models[0]

    def _on_model_changed(self, dd, _):
        item = dd.get_selected_item()
        if item:
            self.model = item.get_string()

    def edit_system(self):
        win = Gtk.Window(title="System prompt", transient_for=self, modal=True)
        win.set_default_size(480, 240)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
        tv = Gtk.TextView()
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        tv.get_buffer().set_text(self.system_prompt)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(tv)
        box.append(sw)
        save = Gtk.Button(label="Salveaza")
        save.add_css_class("suggested-action")

        def do(*a):
            b = tv.get_buffer()
            self.system_prompt = b.get_text(b.get_start_iter(), b.get_end_iter(), True)
            win.close()
        save.connect("clicked", do)
        box.append(save)
        win.set_child(box)
        win.present()

    def new_chat(self):
        self.messages = []
        self.rag_context = ""
        child = self.chat_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.chat_box.remove(child)
            child = nxt

    def export_chat(self):
        d = Gtk.FileDialog()
        d.set_initial_name("conversatie.md")
        d.save(self, None, self._do_export)

    def _do_export(self, dialog, res):
        try:
            f = dialog.save_finish(res)
        except GLib.Error:
            return
        if f:
            with open(f.get_path(), "w", encoding="utf-8") as fh:
                for m in self.messages:
                    fh.write("**%s:** %s\n\n" % (m["role"], m["content"]))


class BoboAIApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboAIWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboAI Local 1.0.0 (BOBO OS)")
        return 0
    return BoboAIApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
