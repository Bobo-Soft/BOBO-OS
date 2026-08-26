"""
BoboAssist side panel (GTK4).
Streaming chat with the local model, context-aware (reads the active Bobo Office
document excerpt), quick-action chips, and an "Insert into document" button that
pushes the answer to the focused window (wtype) with a clipboard fallback.
Target: < 80 MB idle; the model is unloaded after 5 min idle (handled by the daemon).
"""
import os
import sys
import subprocess
import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gdk  # noqa: E402

sys.path.insert(0, "/usr/share/bobo-office")
sys.path.insert(0, "/usr/share/bobo-assist")
try:
    from shared.ai_client import AIClient
except Exception:
    AIClient = None
try:
    from context_watcher import ContextWatcher
except Exception:
    ContextWatcher = None
try:
    from model_manager import ModelManagerWindow, active_model
except Exception:
    ModelManagerWindow = None
    def active_model():
        return "phi3:mini"

QUICK = [
    ("Rezumă", "Rezumă concis textul de mai jos."),
    ("Continuă", "Continuă textul în același stil."),
    ("Rescrie formal", "Rescrie formal și clar."),
    ("Corectează", "Corectează gramatica și ortografia."),
    ("Traduce EN", "Tradu în engleză."),
]


class AssistPanel(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboAssist")
        self.set_default_size(400, 720)
        self.ai = AIClient(model=active_model()) if AIClient else None
        self.ctx = ContextWatcher() if ContextWatcher else None
        self.last_answer = ""

        self._css()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        title = Gtk.Label()
        title.set_markup("<b>BoboAssist</b>")
        header.set_title_widget(title)
        models_btn = Gtk.Button.new_from_icon_name("system-software-install-symbolic")
        models_btn.set_tooltip_text("Modele AI")
        models_btn.connect("clicked", lambda *a: self._open_models())
        header.pack_end(models_btn)

        # conversation
        self.scroller = Gtk.ScrolledWindow(); self.scroller.set_vexpand(True)
        self.chat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                            margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
        self.scroller.set_child(self.chat)
        root.append(self.scroller)

        # quick chips
        chips = Gtk.Box(spacing=4); chips.set_margin_start(8); chips.set_margin_end(8)
        chips.add_css_class("bobo-chips")
        for label, prompt in QUICK:
            b = Gtk.Button(label=label); b.add_css_class("pill")
            b.connect("clicked", lambda x, p=prompt: self._send(p, use_context=True))
            chips.append(b)
        chip_sw = Gtk.ScrolledWindow(); chip_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        chip_sw.set_child(chips)
        root.append(chip_sw)

        # input row
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                      margin_top=6, margin_bottom=8, margin_start=8, margin_end=8)
        self.entry = Gtk.Entry(hexpand=True)
        self.entry.set_placeholder_text("Întreabă BoboAssist…")
        self.entry.connect("activate", lambda *a: self._send(self.entry.get_text()))
        send = Gtk.Button.new_from_icon_name("document-send-symbolic")
        send.add_css_class("suggested-action")
        send.connect("clicked", lambda *a: self._send(self.entry.get_text()))
        row.append(self.entry); row.append(send)
        root.append(row)

        if not (self.ai and self.ai.available()):
            self._bubble("assist", "Offline. Pornește Ollama (`ollama serve`) și descarcă un model din butonul de modele.")
        else:
            self._bubble("assist", "Salut! Sunt BoboAssist. Te pot ajuta cu documentele tale.")

    def _css(self):
        p = Gtk.CssProvider()
        p.load_from_data(b"""
        .bubble-user { background:#4a9eff; color:#fff; border-radius:12px 12px 2px 12px; padding:8px 12px; }
        .bubble-assist { background:#16213e; color:#e8eaf6; border-radius:12px 12px 12px 2px; padding:8px 12px; }
        .pill { border-radius:14px; padding:2px 10px; font-size:11px; }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _bubble(self, role, text):
        lbl = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True)
        lbl.set_max_width_chars(44)
        lbl.add_css_class("bubble-%s" % role)
        lbl.set_halign(Gtk.Align.END if role == "user" else Gtk.Align.START)
        self.chat.append(lbl)
        if role == "assist":
            # add an "insert" action under assistant answers
            act = Gtk.Button(label="⇤ Inserează în document")
            act.add_css_class("pill")
            act.set_halign(Gtk.Align.START)
            act.connect("clicked", lambda *a, l=lbl: self._insert(l.get_text()))
            self.chat.append(act)
        GLib.idle_add(self._scroll)
        return lbl

    def _scroll(self):
        adj = self.scroller.get_vadjustment(); adj.set_value(adj.get_upper()); return False

    def _send(self, text, use_context=False):
        text = (text or "").strip()
        if not text:
            return
        self.entry.set_text("")
        context = ""
        if use_context and self.ctx:
            c = self.ctx.read_context()
            context = c.get("excerpt", "")
            self._bubble("user", text + (("  ·  (context: %s)" % c.get("app")) if c.get("app") else ""))
        else:
            self._bubble("user", text)
        answer = self._bubble("assist", "…")
        buf = {"txt": ""}
        def on_tok(t):
            buf["txt"] += t
            GLib.idle_add(answer.set_text, buf["txt"])
            GLib.idle_add(self._scroll)
        def work():
            self.ai.stream(text, context=context, on_token=on_tok) if self.ai else on_tok("[AI indisponibil]")
            self.last_answer = buf["txt"]
        threading.Thread(target=work, daemon=True).start()

    def _insert(self, text):
        """Push text into the focused window: wtype, else clipboard + notify."""
        try:
            p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE); p.communicate(text.encode())
        except Exception:
            pass
        if subprocess.run(["which", "wtype"], capture_output=True).returncode == 0:
            subprocess.Popen(["wtype", text])
        else:
            subprocess.Popen(["notify-send", "BoboAssist", "Răspuns copiat în clipboard (Ctrl+V pentru inserare)."])

    def _open_models(self):
        if ModelManagerWindow:
            ModelManagerWindow(self).present()
