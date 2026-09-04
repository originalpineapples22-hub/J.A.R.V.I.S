# -*- coding: utf-8 -*-
"""Loop detection for self-repair. Stops 0.5.4.M.4 going round in circles when a
fix isn't working, and produces a clear report of exactly where it got stuck."""
import re
import json
import hashlib
from datetime import datetime
from .config import DATA_DIR

LEDGER = DATA_DIR / "repair_ledger.json"

# noise that changes between runs but doesn't mean the error changed
_NOISE = [
    (re.compile(r"0x[0-9a-fA-F]+"), "0xADDR"),
    (re.compile(r"line \d+"), "line N"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"), "TIME"),
    (re.compile(r"/tmp/[^\s'\"]+"), "TMPPATH"),
    (re.compile(r"\b\d+\.\d+s\b"), "DUR"),
]


def error_signature(text: str) -> str:
    """A stable fingerprint of an error, ignoring run-to-run noise."""
    t = (text or "").strip()
    for rx, rep in _NOISE:
        t = rx.sub(rep, t)
    # the exception type + message is the meaningful part
    m = re.findall(r"^([A-Za-z_.]*(?:Error|Exception|Warning))\s*:?\s*(.*)$", t, re.MULTILINE)
    core = " | ".join(f"{a}:{b[:120]}" for a, b in m[-2:]) if m else t[-300:]
    return hashlib.sha1(core.encode("utf-8", "ignore")).hexdigest()[:16]


def describe_error(text: str) -> dict:
    """Pull the useful facts out of a traceback for the report."""
    t = text or ""
    typ = msg = ""
    m = re.findall(r"^([A-Za-z_.]*(?:Error|Exception))\s*:\s*(.*)$", t, re.MULTILINE)
    if m:
        typ, msg = m[-1][0], m[-1][1].strip()
    locs = re.findall(r'File "([^"]+)", line (\d+)(?:, in (\S+))?', t)
    where = ""
    if locs:
        f, ln, fn = locs[-1]
        where = f"{f.split('/')[-1]}:{ln}" + (f" in {fn}()" if fn else "")
    return {"type": typ or "Failure", "message": msg or t.strip()[-200:], "where": where}


class LoopGuard:
    """Tracks attempts and stops as soon as progress stalls.

    Stalls it catches:
      • the same error twice in a row      -> the fix changed nothing
      • code identical to a previous try   -> it is rewriting the same thing
      • flipping between two versions      -> oscillation
    """

    def __init__(self, max_attempts=4, label="task"):
        self.max_attempts = max_attempts
        self.label = label
        self.errors = []     # signatures, in order
        self.codes = []      # code hashes, in order
        self.raw_errors = []
        self.attempts = 0

    def track(self, code: str, error: str):
        """Record one attempt. Returns None to continue, or a reason to stop."""
        self.attempts += 1
        ch = hashlib.sha1((code or "").encode("utf-8", "ignore")).hexdigest()[:16]
        es = error_signature(error)
        stall = None
        if ch in self.codes:
            stall = ("oscillating" if self.codes and self.codes[-1] != ch else "repeating the same code")
        elif len(self.errors) >= 1 and self.errors[-1] == es:
            stall = "the same error after a change"
        elif self.attempts >= self.max_attempts:
            stall = "attempt limit reached"
        self.codes.append(ch)
        self.errors.append(es)
        self.raw_errors.append(error or "")
        return stall

    def report(self, reason: str, extra: str = "") -> str:
        d = describe_error(self.raw_errors[-1] if self.raw_errors else "")
        distinct = len(set(self.errors))
        lines = [
            f"⚠️ I stopped repairing **{self.label}** — {reason}. I did not want to loop and waste your quota, sir.",
            "",
            f"**Where it fails:** {d['where'] or 'not reported'}",
            f"**Error:** {d['type']}: {d['message']}",
            f"**Attempts:** {self.attempts} · {distinct} distinct error{'s' if distinct != 1 else ''}",
        ]
        if distinct == 1 and self.attempts > 1:
            lines.append("**Diagnosis:** every rewrite produced the identical failure, so the cause is outside the code I was editing — a missing package, a wrong path/permission, or an assumption in the requirement itself.")
        elif reason.startswith("oscillat"):
            lines.append("**Diagnosis:** my fixes were undoing each other — two requirements are in conflict.")
        else:
            lines.append("**Diagnosis:** the error kept changing but never cleared; the task likely needs a different approach.")
        if extra:
            lines += ["", extra]
        lines += ["", "Tell me how you would like to proceed, or give me the missing detail and I will try once more."]
        return "\n".join(lines)


# ---------------------------------------------------------------- fault ledger
def _load():
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d):
    try:
        LEDGER.write_text(json.dumps(d, indent=1), encoding="utf-8")
    except Exception:
        pass


def repair_attempts(fingerprint: str) -> int:
    return _load().get(fingerprint, {}).get("attempts", 0)


def note_repair_attempt(fingerprint: str, detail: str = ""):
    d = _load()
    e = d.get(fingerprint, {"attempts": 0})
    e["attempts"] += 1
    e["last"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    e["detail"] = detail[:300]
    d[fingerprint] = e
    _save(d)
    return e["attempts"]


def give_up(fingerprint: str, max_tries=2) -> bool:
    """True once a fault has defeated the same automatic repair twice."""
    return repair_attempts(fingerprint) >= max_tries


def clear_fingerprint(fingerprint: str):
    d = _load()
    d.pop(fingerprint, None)
    _save(d)
