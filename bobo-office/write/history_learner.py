"""
BoboWrite history learner (opt-in).
Learns the user's frequent words, preferred phrasings and corrected mistakes,
stored locally in ~/.local/share/bobo-write/learning.db. Used for smarter
autocomplete suggestions. Nothing leaves the machine.
"""
import os
import re
import sqlite3
import time

DB = os.path.expanduser("~/.local/share/bobo-write/learning.db")
FLAG = os.path.expanduser("~/.config/bobo-write/learn_enabled")


class HistoryLearner:
    def __init__(self):
        self.enabled = os.path.exists(FLAG)
        if self.enabled:
            self._init_db()

    def set_enabled(self, on: bool):
        os.makedirs(os.path.dirname(FLAG), exist_ok=True)
        if on:
            open(FLAG, "w").close()
            self.enabled = True
            self._init_db()
        else:
            try:
                os.remove(FLAG)
            except Exception:
                pass
            self.enabled = False

    def _con(self):
        os.makedirs(os.path.dirname(DB), exist_ok=True)
        return sqlite3.connect(DB)

    def _init_db(self):
        con = self._con()
        con.execute("CREATE TABLE IF NOT EXISTS words(word TEXT PRIMARY KEY, n INTEGER, ts INTEGER)")
        con.execute("CREATE TABLE IF NOT EXISTS corrections(wrong TEXT PRIMARY KEY, right TEXT, n INTEGER)")
        con.commit(); con.close()

    def learn_text(self, text: str):
        if not self.enabled or not text:
            return
        con = self._con()
        for w in re.findall(r"[A-Za-zĂÂÎȘȚăâîșț]{4,}", text):
            wl = w.lower()
            con.execute("INSERT INTO words(word,n,ts) VALUES(?,1,?) "
                        "ON CONFLICT(word) DO UPDATE SET n=n+1, ts=?",
                        (wl, int(time.time()), int(time.time())))
        con.commit(); con.close()

    def learn_correction(self, wrong: str, right: str):
        if not self.enabled or not wrong or not right:
            return
        con = self._con()
        con.execute("INSERT INTO corrections(wrong,right,n) VALUES(?,?,1) "
                    "ON CONFLICT(wrong) DO UPDATE SET right=?, n=n+1", (wrong.lower(), right, right))
        con.commit(); con.close()

    def suggest(self, prefix: str, limit=5):
        if not self.enabled or len(prefix) < 2:
            return []
        con = self._con()
        rows = con.execute("SELECT word FROM words WHERE word LIKE ? ORDER BY n DESC LIMIT ?",
                           (prefix.lower() + "%", limit)).fetchall()
        con.close()
        return [r[0] for r in rows]

    def autocorrect(self, word: str) -> str:
        if not self.enabled:
            return word
        con = self._con()
        row = con.execute("SELECT right FROM corrections WHERE wrong=?", (word.lower(),)).fetchone()
        con.close()
        return row[0] if row else word
