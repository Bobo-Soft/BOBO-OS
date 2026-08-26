"""
BoboWrite AI helper — wraps the shared AIClient with document-aware prompts.
The current document text is sent as context automatically.
"""
import sys
sys.path.insert(0, "/usr/share/bobo-office")
try:
    from shared.ai_client import AIClient
except Exception:
    AIClient = None

PROMPTS = {
    "continue": "Continuă textul în același stil, natural.",
    "formal":   "Rescrie textul într-un ton formal și clar.",
    "concise":  "Rescrie textul mai concis, păstrând sensul.",
    "summary":  "Rezumă textul în câteva puncte cheie.",
    "translate_en": "Tradu textul în engleză.",
    "translate_ro": "Tradu textul în română.",
    "fix":      "Corectează gramatica și ortografia, fără a schimba sensul.",
}


class AIWriter:
    def __init__(self, model=None):
        self.ai = AIClient(model=model) if AIClient else None

    def available(self):
        return bool(self.ai and self.ai.available())

    def run(self, action: str, document_text: str, extra: str = "", on_token=None) -> str:
        if not self.ai:
            return "[AI indisponibil]"
        prompt = PROMPTS.get(action, action)
        if extra:
            prompt += " " + extra
        system = "Ești editorul AI din BoboWrite. Returnează doar textul rezultat, fără explicații."
        if on_token:
            return self.ai.stream(prompt, system=system, context=document_text, on_token=on_token)
        return self.ai.ask(prompt, system=system, context=document_text)
