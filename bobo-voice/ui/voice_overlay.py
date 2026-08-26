"""
BoboVoice status overlay — a small always-on-top window (top-right, 300x80) that
shows the assistant's state: Idle (blue), Listening (red), Processing (orange),
Speaking (green). Uses layer-shell when available.
"""
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gdk  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LayerShell
    HAVE_LAYER = True
except Exception:
    HAVE_LAYER = False

STATES = {
    "idle":       ("BoboVoice", "#4a9eff", "Spune 'Hey Bobo'"),
    "listening":  ("Ascult…", "#ff5d5d", "Vorbește acum"),
    "processing": ("Procesez…", "#ffb454", ""),
    "speaking":   ("Vorbesc…", "#4ade80", ""),
}


class VoiceOverlay(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.set_decorated(False)
        self.set_default_size(300, 80)
        self._css()
        self.dot = Gtk.Label(label="●")
        self.title = Gtk.Label(); self.sub = Gtk.Label()
        self.title.add_css_class("ov-title"); self.sub.add_css_class("ov-sub")
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); tb.append(self.title); tb.append(self.sub)
        row = Gtk.Box(spacing=10, margin_top=10, margin_bottom=10, margin_start=14, margin_end=14)
        self.dot.add_css_class("ov-dot"); row.append(self.dot); row.append(tb)
        box = Gtk.Box(); box.add_css_class("ov-bg"); box.append(row)
        self.set_child(box)
        if HAVE_LAYER:
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
            LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, True)
            LayerShell.set_margin(self, LayerShell.Edge.TOP, 16)
            LayerShell.set_margin(self, LayerShell.Edge.RIGHT, 16)
        self.set_state("idle")

    def _css(self):
        p = Gtk.CssProvider()
        p.load_from_data(b"""
        window { background: transparent; }
        .ov-bg { background: rgba(22,33,62,0.95); border-radius:14px; border:1px solid #4a9eff; }
        .ov-title { font-weight:bold; color:#e8eaf6; }
        .ov-sub { font-size:11px; color:#8899bb; }
        .ov-dot { font-size:20px; }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def set_state(self, state):
        title, color, sub = STATES.get(state, STATES["idle"])
        GLib.idle_add(self._apply, title, color, sub)

    def _apply(self, title, color, sub):
        self.title.set_text(title); self.sub.set_text(sub)
        self.dot.set_markup("<span color='%s'>●</span>" % color)
        return False

    def flash_text(self, text):
        GLib.idle_add(self.sub.set_text, text[:40])
