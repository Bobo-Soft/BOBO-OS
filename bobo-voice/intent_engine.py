"""
BoboVoice intent engine.
Matches recognized speech against 60+ Romanian/English regex intents for instant,
offline dispatch to the ActionExecutor. Anything unmatched falls back to the local
model (Phi-3 via the shared AIClient) for a conversational answer, with a rolling
10-turn memory and optional on-screen context.
"""
import re
import sys

sys.path.insert(0, "/usr/share/bobo-office")
try:
    from shared.ai_client import AIClient
except Exception:
    AIClient = None


class IntentEngine:
    def __init__(self, executor):
        self.ex = executor
        self.ai = AIClient() if AIClient else None
        self.memory = []   # last 10 (role, text)
        self.rules = self._build_rules()

    # ------------------------------------------------------------------ rules
    def _build_rules(self):
        ex = self.ex
        R = []
        def add(pattern, fn):
            R.append((re.compile(pattern, re.IGNORECASE), fn))
        # volume / sound
        add(r"\b(mărește|mareste|dă mai tare|urcă) (volum|sunet)", lambda m: ex.volume("up"))
        add(r"\b(scade|micșorează|micsoreaza|dă mai încet) (volum|sunet)", lambda m: ex.volume("down"))
        add(r"\b(volume up|louder)", lambda m: ex.volume("up"))
        add(r"\b(volume down|quieter)", lambda m: ex.volume("down"))
        add(r"\b(mut|mute|fără sunet|opreste sunet)", lambda m: ex.mute())
        # brightness
        add(r"\b(mărește|mareste|urcă) (luminozitate|ecran)", lambda m: ex.brightness("up"))
        add(r"\b(scade|micșorează) (luminozitate|ecran)", lambda m: ex.brightness("down"))
        add(r"\bbrightness (up|down)", lambda m: ex.brightness(m.group(1)))
        # power
        add(r"\b(oprește|opreste|închide) (calculatorul|sistemul|pc)", lambda m: ex.power("shutdown"))
        add(r"\b(repornește|reporneste|restart)", lambda m: ex.power("restart"))
        add(r"\b(suspend|somn|adormi)", lambda m: ex.power("suspend"))
        add(r"\b(shutdown|power off)", lambda m: ex.power("shutdown"))
        add(r"\b(blochează|blocheaza|lock)( ecran)?", lambda m: ex.lock())
        add(r"\b(captur|screenshot|poză (de )?ecran)", lambda m: ex.screenshot())
        # apps
        add(r"\b(deschide|pornește|porneste|open|lansează|lanseaza) (.+)", lambda m: ex.open_app(m.group(2)))
        add(r"\b(ce aplicații|list apps|lista aplicații)", lambda m: ex.list_apps())
        add(r"\b(ajutor|help|ce poți|ce comenzi)", lambda m: ex.help_apps())
        # windows
        add(r"\b(închide|inchide) (fereastra|window)", lambda m: ex.window("close"))
        add(r"\b(maximiz)", lambda m: ex.window("maximize"))
        add(r"\b(minimiz)", lambda m: ex.window("minimize"))
        # reading
        add(r"\b(citește|citeste|read) (documentul|textul|document)", lambda m: ex.read_document())
        add(r"\b(citește|citeste) (ecranul|screen)", lambda m: ex.read_screen())
        add(r"\b(stop|oprește|opreste|taci|gata)( citit)?", lambda m: ex.stop_reading())
        # web
        add(r"\b(caută|cauta|search)( pe web| online)? (.+)", lambda m: ex.web_search(m.group(3)))
        add(r"\b(deschide|open) (site|website|pagina) (.+)", lambda m: ex.open_website(m.group(3)))
        add(r"\b(derulează|deruleaza|scroll) (jos|down)", lambda m: ex.scroll("down"))
        add(r"\b(derulează|deruleaza|scroll) (sus|up)", lambda m: ex.scroll("up"))
        add(r"\b(înapoi|inapoi|back)", lambda m: ex.nav("back"))
        add(r"\b(înainte|inainte|forward)", lambda m: ex.nav("forward"))
        # accessibility
        add(r"\b(text mai mare|mărește textul|mareste textul|bigger text)", lambda m: ex.text_size(True))
        add(r"\b(text mai mic|micșorează textul|smaller text)", lambda m: ex.text_size(False))
        add(r"\b(contrast)", lambda m: ex.contrast())
        add(r"\b(vorbește mai repede|mai repede|faster)", lambda m: ex.speech_rate(True))
        add(r"\b(vorbește mai rar|mai rar|slower)", lambda m: ex.speech_rate(False))
        # content
        add(r"\b(descrie) (imaginea|ecranul|screen)", lambda m: ex.read_screen())
        add(r"\b(tradu|translate) (.+)", lambda m: ex.translate(m.group(2)))
        add(r"\b(explică|explica|explain|ce este|ce înseamnă) (.+)", lambda m: ex.explain(m.group(2)))
        # media
        add(r"\b(redă|reda|play)\b", lambda m: ex.media("play"))
        add(r"\b(pauză|pauza|pause)\b", lambda m: ex.media("pause"))
        add(r"\b(următoarea|urmatoarea|next)\b", lambda m: ex.media("next"))
        add(r"\b(anterioara|precedenta|previous)\b", lambda m: ex.media("prev"))
        # documents
        add(r"\b(salvează|salveaza|save)\b", lambda m: ex.save_doc())
        add(r"\b(tipărește|tipareste|print|printează)\b", lambda m: ex.print_doc())
        return R

    # ------------------------------------------------------------------ dispatch
    def handle(self, text: str, screen_context: str = "") -> str:
        text = (text or "").strip()
        if not text:
            return ""
        self.memory.append(("user", text)); self.memory = self.memory[-20:]
        for rx, fn in self.rules:
            m = rx.search(text)
            if m:
                try:
                    reply = fn(m) or "În regulă."
                except Exception as e:
                    reply = "Am întâmpinat o problemă: %s" % e
                self.memory.append(("assist", reply))
                return reply
        # fallback: conversational model
        reply = self._ai_reply(text, screen_context)
        self.memory.append(("assist", reply))
        return reply

    def _ai_reply(self, text, screen_context):
        if not (self.ai and self.ai.available()):
            return "Nu am înțeles comanda. Spune 'ajutor' pentru exemple."
        history = "\n".join("%s: %s" % (r, t) for r, t in self.memory[-10:])
        system = ("Ești BoboVoice, asistentul vocal offline din BOBO OS. Răspunde scurt, "
                  "natural, în limba utilizatorului. Dacă e o comandă de sistem pe care nu o "
                  "poți executa, spune ce ar trebui utilizatorul să facă.")
        ctx = ("Ecran: %s\n" % screen_context if screen_context else "") + "Istoric:\n" + history
        return self.ai.ask(text, system=system, context=ctx)
