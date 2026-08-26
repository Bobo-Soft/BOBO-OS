"""
BoboVoice live captioner — a transparent GTK4 overlay pinned to the bottom of the
screen showing live transcription (Whisper tiny) of system audio. 28px bold text
on a semi-transparent background. Toggle on/off.
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


class LiveCaptioner(Gtk.Window):
    def __init__(self, translator):
        super().__init__()
        self.translator = translator
        self.set_decorated(False)
        self.set_default_size(1000, 90)
        self._css()
        self.label = Gtk.Label(label="")
        self.label.add_css_class("caption")
        self.label.set_wrap(True)
        self.label.set_justify(Gtk.Justification.CENTER)
        box = Gtk.Box(); box.add_css_class("caption-bg")
        box.append(self.label); self.label.set_hexpand(True)
        self.set_child(box)
        if HAVE_LAYER:
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_anchor(self, LayerShell.Edge.BOTTOM, True)
            LayerShell.set_margin(self, LayerShell.Edge.BOTTOM, 60)

    def _css(self):
        p = Gtk.CssProvider()
        p.load_from_data(b"""
        .caption { font-size:28px; font-weight:bold; color:#ffffff; padding:12px 20px; }
        .caption-bg { background: rgba(0,0,0,0.65); border-radius:12px; }
        window { background: transparent; }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def start(self):
        self.present()
        self.translator.start_live(lambda text: GLib.idle_add(self._set, text))

    def _set(self, text):
        self.label.set_text(text[-160:])
        return False

    def stop(self):
        self.translator.stop_live()
        self.close()
