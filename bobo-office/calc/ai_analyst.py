"""
BoboCalc AI analyst — natural-language data analysis via the shared AIClient.
Turns requests like "suma vânzărilor pe ianuarie" into a formula or a summary,
using the current sheet as context.
"""
import sys
sys.path.insert(0, "/usr/share/bobo-office")
try:
    from shared.ai_client import AIClient
except Exception:
    AIClient = None


class AIAnalyst:
    def __init__(self, model=None):
        self.ai = AIClient(model=model) if AIClient else None

    def available(self):
        return bool(self.ai and self.ai.available())

    def _sheet_text(self, rows, max_rows=40):
        lines = []
        for r in rows[:max_rows]:
            lines.append("\t".join("" if c is None else str(c) for c in r))
        return "\n".join(lines)

    def analyze(self, question: str, rows) -> str:
        if not self.ai:
            return "[AI indisponibil — pornește Ollama]"
        system = ("Ești analistul de date din BoboCalc. Ai o foaie de calcul (TSV). "
                  "Dacă cererea implică un calcul, propune o formulă în stil Excel "
                  "(ex: =SUM(B2:B10)). Răspunde scurt, în limba utilizatorului.")
        return self.ai.ask(question, system=system, context=self._sheet_text(rows))

    def suggest_formula(self, request: str, rows) -> str:
        if not self.ai:
            return ""
        system = "Returnează DOAR o formulă Excel validă care rezolvă cererea, nimic altceva."
        out = self.ai.ask(request, system=system, context=self._sheet_text(rows))
        for line in out.splitlines():
            line = line.strip().strip("`")
            if line.startswith("="):
                return line
        return out.strip()
