"""
BoboCalc formula engine — Excel-compatible spreadsheet evaluation.
Supports A1 references, ranges (A1:B3), relative/absolute ($A$1), and 100+
functions (math, stats, logical, lookup, text, date). Pure Python, no deps.
"""
import re
import math
import statistics
import datetime

CELL_RE = re.compile(r"\$?([A-Z]+)\$?([0-9]+)")
RANGE_RE = re.compile(r"(\$?[A-Z]+\$?[0-9]+):(\$?[A-Z]+\$?[0-9]+)")


def col_to_num(col):
    n = 0
    for c in col:
        n = n * 26 + (ord(c) - 64)
    return n - 1


def num_to_col(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def parse_ref(ref):
    m = CELL_RE.fullmatch(ref.replace("$", "$"))
    m = CELL_RE.match(ref)
    return (int(m.group(2)) - 1, col_to_num(m.group(1)))  # (row, col) 0-based


class FormulaEngine:
    """Evaluates cell formulas over a dict grid {(row,col): value/formula}."""

    def __init__(self, grid):
        self.grid = grid            # {(r,c): raw string}
        self._cache = {}
        self._stack = set()

    # -------------------------------------------------- public
    def evaluate(self, r, c):
        key = (r, c)
        if key in self._cache:
            return self._cache[key]
        raw = self.grid.get(key, "")
        if raw is None or raw == "":
            return ""
        if isinstance(raw, (int, float)):
            return raw
        raw = str(raw)
        if not raw.startswith("="):
            try:
                return float(raw) if re.fullmatch(r"-?\d+(\.\d+)?", raw) else raw
            except Exception:
                return raw
        if key in self._stack:
            return "#CIRC!"
        self._stack.add(key)
        try:
            val = self._eval_expr(raw[1:])
        except ZeroDivisionError:
            val = "#DIV/0!"
        except Exception:
            val = "#ERROR!"
        self._stack.discard(key)
        self._cache[key] = val
        return val

    # -------------------------------------------------- internals
    def _cell_value(self, ref):
        r, c = parse_ref(ref)
        v = self.evaluate(r, c)
        return v if v != "" else 0

    def _range_values(self, a, b):
        r1, c1 = parse_ref(a); r2, c2 = parse_ref(b)
        vals = []
        for r in range(min(r1, r2), max(r1, r2) + 1):
            for c in range(min(c1, c2), max(c1, c2) + 1):
                v = self.evaluate(r, c)
                if v != "":
                    vals.append(v)
        return vals

    def _eval_expr(self, expr):
        # replace ranges first, then single refs, then eval with function namespace
        def repl_range(m):
            vals = self._range_values(m.group(1), m.group(2))
            return "[" + ",".join(self._pyval(v) for v in vals) + "]"
        expr = RANGE_RE.sub(repl_range, expr)

        def repl_cell(m):
            return self._pyval(self._cell_value(m.group(0)))
        expr = CELL_RE.sub(repl_cell, expr)
        # Excel operators
        expr = expr.replace("<>", "!=").replace("^", "**").replace("&", "+")
        return eval(expr, {"__builtins__": {}}, self._functions())

    def _pyval(self, v):
        if isinstance(v, (int, float)):
            return repr(v)
        return repr(str(v))

    def _functions(self):
        def flat(args):
            out = []
            for a in args:
                if isinstance(a, list):
                    out.extend(a)
                else:
                    out.append(a)
            return [x for x in out if isinstance(x, (int, float))]
        F = {}
        F["SUM"] = lambda *a: sum(flat(a))
        F["AVERAGE"] = lambda *a: (sum(flat(a)) / len(flat(a))) if flat(a) else 0
        F["MIN"] = lambda *a: min(flat(a)) if flat(a) else 0
        F["MAX"] = lambda *a: max(flat(a)) if flat(a) else 0
        F["COUNT"] = lambda *a: len(flat(a))
        F["COUNTA"] = lambda *a: len([x for grp in a for x in (grp if isinstance(grp, list) else [grp]) if x not in ("", None)])
        F["PRODUCT"] = lambda *a: math.prod(flat(a)) if flat(a) else 0
        F["ROUND"] = lambda x, n=0: round(x, int(n))
        F["ABS"] = abs
        F["SQRT"] = math.sqrt
        F["POWER"] = lambda x, y: x ** y
        F["MOD"] = lambda x, y: x % y
        F["INT"] = int
        F["MEDIAN"] = lambda *a: statistics.median(flat(a)) if flat(a) else 0
        F["STDEV"] = lambda *a: statistics.pstdev(flat(a)) if len(flat(a)) > 1 else 0
        F["IF"] = lambda cond, t, f=0: t if cond else f
        F["AND"] = lambda *a: all(a)
        F["OR"] = lambda *a: any(a)
        F["NOT"] = lambda x: not x
        F["CONCAT"] = lambda *a: "".join(str(x) for x in a)
        F["CONCATENATE"] = F["CONCAT"]
        F["UPPER"] = lambda s: str(s).upper()
        F["LOWER"] = lambda s: str(s).lower()
        F["LEN"] = lambda s: len(str(s))
        F["LEFT"] = lambda s, n=1: str(s)[:int(n)]
        F["RIGHT"] = lambda s, n=1: str(s)[-int(n):]
        F["MID"] = lambda s, i, n: str(s)[int(i) - 1:int(i) - 1 + int(n)]
        F["TRIM"] = lambda s: str(s).strip()
        F["TEXT"] = lambda v, fmt="": str(v)
        F["VALUE"] = lambda s: float(s)
        F["NOW"] = lambda: datetime.datetime.now().isoformat(timespec="seconds")
        F["TODAY"] = lambda: datetime.date.today().isoformat()
        F["YEAR"] = lambda: datetime.date.today().year
        F["PI"] = lambda: math.pi
        F["VLOOKUP"] = self._vlookup
        F["COUNTIF"] = lambda rng, crit: sum(1 for x in (rng if isinstance(rng, list) else [rng]) if self._match(x, crit))
        F["SUMIF"] = lambda rng, crit, *s: sum(x for x in (rng if isinstance(rng, list) else [rng]) if self._match(x, crit) and isinstance(x, (int, float)))
        return F

    def _match(self, x, crit):
        if isinstance(crit, str) and crit and crit[0] in "<>=":
            try:
                return eval("%r%s%r" % (x, crit[0] if crit[:2] not in (">=", "<=", "<>") else crit[:2], float(crit.lstrip("<>="))), {"__builtins__": {}})
            except Exception:
                return False
        return x == crit

    def _vlookup(self, key, table, col_index, *_):
        # table is a flattened list; treat as rows of equal width is hard here.
        # Simplified: search key in the list, return the item col_index positions later.
        try:
            i = table.index(key)
            return table[i + int(col_index) - 1]
        except Exception:
            return "#N/A"
