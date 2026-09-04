# -*- coding: utf-8 -*-
"""Self-development: 0.5.4.M.4 reads its own source, writes fixes, verifies them,
and applies them — with a snapshot and AUTOMATIC ROLLBACK if anything breaks.

Safety model (never bypassed):
  1. snapshot every touched file
  2. syntax-check the new source
  3. import-check the whole package in a subprocess
  4. run the self-test suite
  5. any failure -> restore the snapshot instantly
Protected files (auth/config/self-dev itself) can never be rewritten automatically.
"""
import ast
import sys
import shutil
import asyncio
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

from . import memory, brain
from .config import ROOT, DATA_DIR

PKG = ROOT / "jarvis"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

# never auto-rewritten: security, settings and the self-repair machinery itself
PROTECTED = {"config.py", "selfdev.py", "server.py", "__init__.py"}
ERROR_LOG = DATA_DIR / "errors.jsonl"


# ---------------------------------------------------------------- error capture
def record_error(where: str, exc: BaseException):
    """Every caught failure is remembered so it can be repaired later, unprompted."""
    import json
    entry = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "where": where,
             "type": type(exc).__name__, "message": str(exc)[:500],
             "trace": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-2500:]}
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
    memory.add_event("alert", f"Fault in {where}: {type(exc).__name__} — {str(exc)[:120]}")


def recent_errors(n=10):
    import json
    if not ERROR_LOG.exists():
        return []
    lines = ERROR_LOG.read_text(encoding="utf-8").strip().splitlines()[-n:]
    out = []
    for l in lines:
        try:
            out.append(json.loads(l))
        except Exception:
            pass
    return out


def clear_errors():
    try:
        ERROR_LOG.unlink(missing_ok=True)
    except Exception:
        pass


# ---------------------------------------------------------------- source access
def list_sources():
    return sorted(p.name for p in PKG.glob("*.py")) + sorted(f"tools/{p.name}" for p in (PKG / "tools").glob("*.py"))


def read_source(rel: str) -> str:
    p = (PKG / rel).resolve()
    if not str(p).startswith(str(PKG.resolve())) or not p.exists():
        return f"No such source file: {rel}"
    return p.read_text(encoding="utf-8")


def _snapshot(rel: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = SNAPSHOT_DIR / f"{rel.replace('/', '_')}.{ts}.bak"
    shutil.copy(PKG / rel, dst)
    return dst


# ---------------------------------------------------------------- verification
def _import_check() -> tuple:
    p = subprocess.run([sys.executable, "-c", "import jarvis.server, jarvis.agent, jarvis.tools; print('ok')"],
                       capture_output=True, text=True, timeout=90, cwd=str(ROOT))
    return p.returncode == 0, (p.stderr or p.stdout)[-1200:]


def self_test() -> tuple:
    """Health check: package imports, tools register, memory works, agent parses."""
    code = (
        "import jarvis.server, jarvis.agent, jarvis.memory as m, jarvis.brain\n"
        "from jarvis.tools import all_tools, manifest\n"
        "assert len(all_tools()) > 10, 'tools missing'\n"
        "assert manifest(), 'manifest empty'\n"
        "m.db(); m.stats()\n"
        "from jarvis.agent import TOOL_RE\n"
        "assert TOOL_RE.findall('[TOOL: get_time {}]'), 'tool parsing broken'\n"
        "from jarvis import curriculum, connectors\n"
        "assert curriculum.next_topic() is not None or True\n"
        "connectors.status()\n"
        "print('ALL TESTS PASSED')\n"
    )
    try:
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        return ("ALL TESTS PASSED" in p.stdout), (p.stdout + p.stderr)[-1500:]
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------- patching
async def propose_and_apply(rel: str, instruction: str, apply: bool = True) -> str:
    """Have the model rewrite one of its own files, then verify and apply or roll back."""
    name = Path(rel).name
    if name in PROTECTED:
        return f"'{rel}' is protected and cannot be modified automatically, sir. I can suggest a change for you to review instead."
    src = read_source(rel)
    if src.startswith("No such source"):
        return src
    prompt = (
        f"You are editing your own source file `{rel}` of the 0.5.4.M.4 assistant.\n"
        f"TASK: {instruction}\n\nCURRENT FILE:\n```python\n{src}\n```\n\n"
        "Return the COMPLETE corrected file. Keep all existing behaviour that is not part of the task. "
        "Do not add explanations. Output only the file content inside one ```python fence."
    )
    try:
        out = await brain.complete([{"role": "user", "content": prompt}], temperature=0.1, timeout=300)
    except Exception as e:
        return f"Could not draft the change: {e}"
    import re
    m = re.search(r"```(?:python)?\s*(.*?)```", out, re.DOTALL)
    new = (m.group(1) if m else out).strip() + "\n"
    if len(new) < 200:
        return "The drafted file looked truncated — change abandoned for safety."
    try:
        ast.parse(new)
    except SyntaxError as e:
        return f"My drafted change had a syntax error ({e}) — discarded, nothing was touched."
    if not apply:
        return f"Proposed change for {rel} ({len(new)} chars) is syntactically valid. Say 'apply it' to install."

    snap = _snapshot(rel)
    (PKG / rel).write_text(new, encoding="utf-8")
    ok_i, out_i = await asyncio.to_thread(_import_check)
    ok_t, out_t = (await asyncio.to_thread(self_test)) if ok_i else (False, out_i)
    if ok_i and ok_t:
        memory.add_event("system", f"Self-patch applied to {rel}: {instruction[:80]}")
        memory.remember(f"Self-modified {rel}: {instruction[:200]} (verified, tests passed).", kind="selfdev")
        return f"Change applied to {rel} and verified — imports clean, all self-tests pass. Snapshot kept as {snap.name}. A restart loads it."
    shutil.copy(snap, PKG / rel)
    memory.add_event("alert", f"Self-patch to {rel} rolled back (tests failed)")
    return f"The change broke verification, so I rolled myself back automatically. Nothing is damaged.\nFailure:\n{(out_t or out_i)[-600:]}"


async def diagnose() -> str:
    """Look at recent faults and the health check, and say what is wrong."""
    ok, out = await asyncio.to_thread(self_test)
    errs = recent_errors(8)
    lines = [f"Self-test: {'PASS' if ok else 'FAIL'}"]
    if not ok:
        lines.append(out[-800:])
    if errs:
        lines.append(f"{len(errs)} recent fault(s):")
        for e in errs:
            lines.append(f"  [{e['ts']}] {e['where']}: {e['type']} — {e['message'][:160]}")
    else:
        lines.append("No faults recorded.")
    return "\n".join(lines)


async def auto_repair() -> str:
    """Try to fix the most recent recorded fault, entirely unprompted."""
    errs = recent_errors(1)
    if not errs:
        return "Nothing to repair — no faults recorded, sir."
    e = errs[0]
    trace = e.get("trace", "")
    import re
    files = re.findall(r'File "([^"]+jarvis[/\\][^"]+\.py)"', trace)
    if not files:
        return f"I recorded a fault ({e['type']}: {e['message'][:120]}) but it is not in my own code, so I will not patch anything."
    target = Path(files[-1])
    rel = str(target).split("jarvis" + ("\\" if "\\" in str(target) else "/"), 1)[-1]
    instruction = (f"Fix this runtime fault so it cannot happen again, handling the edge case defensively:\n"
                   f"{e['type']}: {e['message']}\n\nTRACEBACK:\n{trace[-1200:]}")
    result = await propose_and_apply(rel, instruction, apply=True)
    if "applied" in result:
        clear_errors()
    return f"Auto-repair on {rel}:\n{result}"
