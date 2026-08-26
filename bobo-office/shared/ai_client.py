"""
Shared AI client for Bobo Office / BoboAssist.
Talks to a local Ollama server (127.0.0.1:11434). Fully offline; degrades
gracefully with a clear message when Ollama or the model is unavailable.
"""
import json
import os
import urllib.request
import urllib.error

OLLAMA = os.environ.get("BOBO_OLLAMA", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("BOBO_AI_MODEL", "phi3:mini")


class AIClient:
    def __init__(self, model: str = DEFAULT_MODEL, base: str = OLLAMA):
        self.model = model
        self.base = base

    # ------------------------------------------------------------------ status
    def available(self) -> bool:
        try:
            urllib.request.urlopen(self.base + "/api/tags", timeout=3)
            return True
        except Exception:
            return False

    def models(self):
        try:
            data = json.loads(urllib.request.urlopen(self.base + "/api/tags", timeout=5).read())
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def has_model(self, name=None) -> bool:
        name = name or self.model
        return any(m.split(":")[0] == name.split(":")[0] for m in self.models())

    # ------------------------------------------------------------------ generate
    def ask(self, prompt: str, system: str = "", context: str = "") -> str:
        """One-shot completion. Returns text or a clear offline message."""
        if not self.available():
            return ("[BoboAssist offline] Pornește Ollama: `ollama serve`, apoi "
                    "descarcă un model (ex: `ollama pull phi3:mini`).")
        full = prompt if not context else "Context:\n%s\n\nCerere: %s" % (context[:6000], prompt)
        payload = {
            "model": self.model,
            "prompt": full,
            "system": system or "Ești BoboAssist, asistentul din Bobo Office. Răspunde concis, în limba utilizatorului.",
            "stream": False,
        }
        try:
            req = urllib.request.Request(self.base + "/api/generate",
                                         data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            data = json.loads(urllib.request.urlopen(req, timeout=120).read())
            return data.get("response", "").strip() or "(răspuns gol)"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ("[Model lipsă] Descarcă modelul cu: `ollama pull %s`" % self.model)
            return "[Eroare AI] %s" % e
        except Exception as e:
            return "[Eroare AI] %s" % e

    def stream(self, prompt: str, system: str = "", context: str = "", on_token=None) -> str:
        """Streaming completion; calls on_token(str) per chunk. Returns full text."""
        if not self.available():
            msg = "[BoboAssist offline] Pornește `ollama serve` și `ollama pull %s`." % self.model
            if on_token:
                on_token(msg)
            return msg
        full = prompt if not context else "Context:\n%s\n\nCerere: %s" % (context[:6000], prompt)
        payload = {"model": self.model, "prompt": full,
                   "system": system or "Ești BoboAssist. Răspunde concis.", "stream": True}
        out = []
        try:
            req = urllib.request.Request(self.base + "/api/generate",
                                         data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                for line in resp:
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    tok = chunk.get("response", "")
                    if tok:
                        out.append(tok)
                        if on_token:
                            on_token(tok)
        except Exception as e:
            err = "\n[Eroare AI] %s" % e
            out.append(err)
            if on_token:
                on_token(err)
        return "".join(out)

    def pull(self, name: str, on_progress=None) -> bool:
        """Download a model via Ollama; on_progress(status_str) per line."""
        try:
            req = urllib.request.Request(self.base + "/api/pull",
                                         data=json.dumps({"name": name}).encode())
            with urllib.request.urlopen(req, timeout=3600) as resp:
                for line in resp:
                    if on_progress and line.strip():
                        try:
                            st = json.loads(line).get("status", "")
                            if st:
                                on_progress(st)
                        except Exception:
                            pass
            return True
        except Exception:
            return False
