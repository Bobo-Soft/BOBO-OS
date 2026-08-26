#!/usr/bin/env python3
"""
BoboVoice — hands-free voice assistant for BOBO OS (GTK4, fully offline).
State machine: IDLE → (wake word) → LISTENING → PROCESSING → SPEAKING → IDLE.
Wires wake_word + stt_engine + intent_engine + action_executor + tts_engine and
a small status overlay. Speaks a welcome message on start.
Modes: --daemon (background, wake-word), --toggle (start/stop), default = window.
"""
import os
import sys
import signal
import threading

sys.path.insert(0, "/usr/share/bobo-voice")
sys.path.insert(0, "/usr/share/bobo-office")

TOGGLE_FLAG = os.path.expanduser("~/.cache/bobo-voice/active")
WELCOME = "Bună ziua. Sunt BoboVoice. Spune Hey Bobo pentru o comandă."


def _lazy():
    """Import heavy pieces lazily so --version/--toggle stay instant."""
    from profile_manager import ProfileManager
    from wake_word import WakeWord
    from stt_engine import STTEngine
    from tts_engine import TTSEngine
    from action_executor import ActionExecutor
    from intent_engine import IntentEngine
    from document_reader import DocumentReader
    import image_describer
    try:
        from shared.ai_client import AIClient
    except Exception:
        AIClient = None
    return (ProfileManager, WakeWord, STTEngine, TTSEngine, ActionExecutor,
            IntentEngine, DocumentReader, image_describer, AIClient)


class BoboVoice:
    def __init__(self, overlay=None):
        (ProfileManager, WakeWord, STTEngine, TTSEngine, ActionExecutor,
         IntentEngine, DocumentReader, image_describer, AIClient) = _lazy()
        self.profile = ProfileManager()
        self.tts = TTSEngine(rate=self.profile.get("tts_rate"),
                             volume=self.profile.get("tts_volume"),
                             lang=self.profile.get("language", "ro"))
        self.stt = STTEngine(language=self.profile.get("language"))
        self.ai = AIClient() if AIClient else None
        self.doc = DocumentReader(self.tts)
        self.executor = ActionExecutor(tts=self.tts, doc_reader=self.doc,
                                       describer=image_describer, ai=self.ai, profile=self.profile)
        self.intents = IntentEngine(self.executor)
        self.overlay = overlay
        self.wake = WakeWord(sensitivity=self.profile.get("wake_sensitivity", 0.5),
                             on_wake=self._on_wake)
        self.state = "idle"

    def _set_state(self, s):
        self.state = s
        if self.overlay:
            self.overlay.set_state(s)

    def start(self):
        os.makedirs(os.path.dirname(TOGGLE_FLAG), exist_ok=True)
        open(TOGGLE_FLAG, "w").close()
        if self.profile.get("welcome", True):
            self.tts.speak(WELCOME)
        self._set_state("idle")
        self.wake.start()

    def stop(self):
        self.wake.stop()
        self.tts.stop()
        try:
            os.remove(TOGGLE_FLAG)
        except Exception:
            pass

    # ------------------------------------------------------------------ state machine
    def _on_wake(self):
        threading.Thread(target=self._turn, daemon=True).start()

    def _turn(self):
        self._set_state("listening")
        text = self.stt.listen()
        if not text:
            self._set_state("idle"); return
        if self.overlay:
            self.overlay.flash_text(text)
        self._set_state("processing")
        reply = self.intents.handle(text)
        self._set_state("speaking")
        if reply:
            self.tts.speak(reply, block=True)
        self._set_state("idle")


# --------------------------------------------------------------------- entry
def run_gui(daemon=False):
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk, Gio, GLib
    from ui.voice_overlay import VoiceOverlay

    class App(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="os.bobo.Voice",
                             flags=Gio.ApplicationFlags.FLAGS_NONE)
            self.hold()  # keep running for the wake-word loop

        def do_activate(self):
            self.overlay = VoiceOverlay()
            self.voice = BoboVoice(overlay=self.overlay)
            if not daemon:
                self.overlay.present()
            self.voice.start()

    return App().run([sys.argv[0]])


def toggle():
    if os.path.exists(TOGGLE_FLAG):
        # signal the running instance to stop
        os.remove(TOGGLE_FLAG)
        try:
            import subprocess
            subprocess.run(["pkill", "-f", "bobo_voice.py"])
        except Exception:
            pass
        return 0
    import subprocess
    subprocess.Popen(["bobo-voice", "--daemon"])
    return 0


def main():
    if "--version" in sys.argv:
        print("BoboVoice 1.0.0 (BOBO OS)"); return 0
    if "--toggle" in sys.argv:
        return toggle()
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    return run_gui(daemon="--daemon" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
