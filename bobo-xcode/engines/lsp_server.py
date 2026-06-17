"""
Minimal Language Server Protocol (LSP) client for BoboXcode.
Speaks JSON-RPC over stdio to sourcekit-lsp (Swift) for completion,
hover and go-to-definition. Degrades gracefully if the server is absent.
"""
import json
import os
import subprocess
import threading
import shutil
from typing import Optional, List, Dict, Callable


class LSPClient:
    def __init__(self, server_cmd: Optional[list] = None, root_path: str = None):
        self.server_cmd = server_cmd or self._default_server()
        self.root_path = root_path or os.getcwd()
        self.proc = None
        self._id = 0
        self._lock = threading.Lock()
        self._responses: Dict[int, dict] = {}
        self._reader_thread = None
        self._initialized = False

    def _default_server(self) -> Optional[list]:
        for cand in ["/usr/local/bin/sourcekit-lsp", shutil.which("sourcekit-lsp")]:
            if cand and os.path.exists(cand):
                return [cand]
        return None

    def is_available(self) -> bool:
        return self.server_cmd is not None

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> bool:
        if not self.server_cmd:
            return False
        try:
            self.proc = subprocess.Popen(
                self.server_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, bufsize=0)
        except Exception:
            self.proc = None
            return False
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._initialize()
        return True

    def stop(self):
        if self.proc:
            try:
                self._notify("exit", {})
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None

    # ------------------------------------------------------------------ protocol
    def _next_id(self) -> int:
        with self._lock:
            self._id += 1
            return self._id

    def _send(self, payload: dict):
        if not self.proc or not self.proc.stdin:
            return
        body = json.dumps(payload).encode("utf-8")
        header = ("Content-Length: %d\r\n\r\n" % len(body)).encode("ascii")
        try:
            self.proc.stdin.write(header + body)
            self.proc.stdin.flush()
        except Exception:
            pass

    def _request(self, method: str, params: dict, timeout: float = 5.0) -> Optional[dict]:
        rid = self._next_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        # Busy-wait for the matching response (LSP is fast for completion)
        import time
        waited = 0.0
        while waited < timeout:
            with self._lock:
                if rid in self._responses:
                    return self._responses.pop(rid)
            time.sleep(0.02)
            waited += 0.02
        return None

    def _notify(self, method: str, params: dict):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _read_loop(self):
        stream = self.proc.stdout
        while self.proc and stream:
            # read headers
            header = b""
            while b"\r\n\r\n" not in header:
                ch = stream.read(1)
                if not ch:
                    return
                header += ch
            length = 0
            for line in header.decode("ascii", "replace").split("\r\n"):
                if line.lower().startswith("content-length:"):
                    length = int(line.split(":")[1].strip())
            body = stream.read(length) if length else b""
            try:
                msg = json.loads(body.decode("utf-8"))
            except Exception:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                with self._lock:
                    self._responses[msg["id"]] = msg

    def _initialize(self):
        params = {
            "processId": os.getpid(),
            "rootUri": "file://" + self.root_path,
            "capabilities": {
                "textDocument": {
                    "completion": {"completionItem": {"snippetSupport": False}},
                    "hover": {}, "definition": {},
                }
            },
        }
        self._request("initialize", params, timeout=8.0)
        self._notify("initialized", {})
        self._initialized = True

    # ------------------------------------------------------------------ features
    def did_open(self, path: str, text: str, language_id: str = "swift"):
        self._notify("textDocument/didOpen", {
            "textDocument": {"uri": "file://" + path, "languageId": language_id,
                             "version": 1, "text": text}})

    def did_change(self, path: str, text: str, version: int = 2):
        self._notify("textDocument/didChange", {
            "textDocument": {"uri": "file://" + path, "version": version},
            "contentChanges": [{"text": text}]})

    def complete(self, path: str, line: int, character: int) -> List[str]:
        """Return completion labels at the given position."""
        if not self._initialized:
            return []
        resp = self._request("textDocument/completion", {
            "textDocument": {"uri": "file://" + path},
            "position": {"line": line, "character": character}})
        if not resp or "result" not in resp or resp["result"] is None:
            return []
        result = resp["result"]
        items = result.get("items", result) if isinstance(result, dict) else result
        labels = []
        for it in items or []:
            label = it.get("label") if isinstance(it, dict) else None
            if label:
                labels.append(label)
        return labels

    def hover(self, path: str, line: int, character: int) -> str:
        resp = self._request("textDocument/hover", {
            "textDocument": {"uri": "file://" + path},
            "position": {"line": line, "character": character}})
        if not resp or not resp.get("result"):
            return ""
        contents = resp["result"].get("contents", "")
        if isinstance(contents, dict):
            return contents.get("value", "")
        if isinstance(contents, list):
            return "\n".join(c.get("value", str(c)) if isinstance(c, dict) else str(c) for c in contents)
        return str(contents)
