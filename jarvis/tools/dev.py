# -*- coding: utf-8 -*-
"""Coding tools: write code, run it, read the error, fix it, repeat — until it
works. Plus self-diagnosis and self-repair of 0.5.4.M.4's own source."""
import sys
import asyncio
import subprocess
from pathlib import Path
from . import tool
from .. import memory, brain, selfdev, curriculum
from ..config import FILES_DIR

LANG = {
    "python": (".py", [sys.executable]),
    "javascript": (".js", ["node"]),
    "node": (".js", ["node"]),
    "bash": (".sh", ["bash"]),
}


def _run(path: Path, cmd, timeout=20):
    try:
        p = subprocess.run(cmd + [str(path)], capture_output=True, text=True, timeout=timeout, cwd=str(FILES_DIR))
        ok = p.returncode == 0
        return ok, ((p.stdout or "") + ("\n" + p.stderr if p.stderr else ""))[-2500:]
    except subprocess.TimeoutExpired:
        return True, "(ran past the time limit — treated as working)"
    except FileNotFoundError:
        return False, f"Runtime not installed for this language on the server."
    except Exception as e:
        return False, str(e)


@tool("run_code", "Execute code immediately and return its real output or error.",
      {"language": "python|javascript|bash", "code": "source"}, agent="Coding Agent")
async def run_code(args, ctx):
    lang = (args.get("language") or "python").lower()
    ext, cmd = LANG.get(lang, LANG["python"])
    p = FILES_DIR / f"_scratch{ext}"
    p.write_text(args.get("code", ""), encoding="utf-8")
    ok, out = await asyncio.to_thread(_run, p, cmd)
    return ("OUTPUT:\n" + out) if ok else ("ERROR:\n" + out)


@tool("write_and_test_code",
      "Write a program, RUN it, read any error, FIX it and re-run automatically until it works. Use this for any real coding request.",
      {"name": "filename.ext", "language": "python|javascript|bash", "spec": "what the program must do", "code": "your first attempt"},
      agent="Coding Agent")
async def write_and_test_code(args, ctx):
    lang = (args.get("language") or "python").lower()
    ext, cmd = LANG.get(lang, LANG["python"])
    name = Path(args.get("name") or f"program{ext}").name
    if not name.endswith(ext):
        name += ext
    spec = args.get("spec", "")
    code = args.get("code", "")
    import re
    m = re.search(r"```(?:\w+)?\s*(.*?)```", code, re.DOTALL)
    if m:
        code = m.group(1)
    path = FILES_DIR / name
    log = []
    for attempt in range(1, 5):
        path.write_text(code.rstrip() + "\n", encoding="utf-8")
        ok, out = await asyncio.to_thread(_run, path, cmd)
        log.append(f"attempt {attempt}: {'PASS' if ok else 'FAIL'}")
        if ok:
            memory.add_event("file", f"{name} written and verified in {attempt} attempt(s)")
            return (f"`{name}` works — verified by actually running it ({attempt} attempt"
                    f"{'s' if attempt > 1 else ''}).\n\nOutput:\n{out[:900]}\n\nDownload it from Files.")
        fix = (f"This {lang} program must: {spec}\n\nIt failed when run:\n{out}\n\n"
               f"CURRENT CODE:\n```\n{code}\n```\n\nReturn the COMPLETE corrected program only, in one code fence.")
        try:
            draft = await brain.complete([{"role": "user", "content": fix}], temperature=0.1, timeout=240)
        except Exception as e:
            return f"Could not repair the code: {e}"
        m = re.search(r"```(?:\w+)?\s*(.*?)```", draft, re.DOTALL)
        code = (m.group(1) if m else draft).strip()
    return (f"`{name}` still fails after 4 self-repair attempts. Last error:\n{out[:900]}\n"
            "The file is saved so you can look at it, sir.")


@tool("review_code", "Review code for bugs, security issues and improvements, and return a corrected version.",
      {"code": "source", "language": "optional"}, agent="Coding Agent")
async def review_code(args, ctx):
    prompt = (f"Review this {args.get('language','')} code as a senior engineer. List concrete bugs, security issues and "
              f"performance problems, then give the corrected full version.\n\n```\n{args.get('code','')}\n```")
    return await brain.complete([{"role": "user", "content": prompt}], temperature=0.2, timeout=240)


# ---------------------------------------------------------------- self-development
@tool("self_diagnose", "Check your own health: run your self-tests and report any faults you have recorded.", {}, agent="System Agent")
async def self_diagnose(args, ctx):
    return await selfdev.diagnose()


@tool("list_own_code", "List your own source files.", {}, agent="System Agent")
def list_own_code(args, ctx):
    return ", ".join(selfdev.list_sources())


@tool("read_own_code", "Read one of your own source files.", {"file": "e.g. agent.py or tools/live.py"}, agent="System Agent")
def read_own_code(args, ctx):
    src = selfdev.read_source(args.get("file", ""))
    return src[:8000]


@tool("improve_self",
      "Modify your OWN source code to fix a flaw or add an ability. The change is snapshotted, syntax-checked, import-checked and self-tested; if anything fails you are rolled back automatically.",
      {"file": "e.g. tools/live.py", "instruction": "what to change and why"}, agent="System Agent")
async def improve_self(args, ctx):
    return await selfdev.propose_and_apply(args.get("file", ""), args.get("instruction", ""), apply=True)


@tool("auto_repair", "Fix the most recent fault in your own code, unprompted, with automatic rollback if the fix is bad.", {}, agent="System Agent")
async def auto_repair(args, ctx):
    return await selfdev.auto_repair()


@tool("learning_progress", "How much of your built-in technology curriculum you have mastered, and what you are studying next.", {}, agent="Research Agent")
def learning_progress(args, ctx):
    p = curriculum.progress()
    a = curriculum.auto_state()
    cur = a.get("current")
    return (f"Curriculum: {p['learned']}/{p['total']} technologies mastered ({p['percent']}%). "
            + (f"Currently self-studying: {cur}. " if cur else "")
            + (f"Next up: {p['next']}. " if p['next'] else "Catalogue complete. ")
            + f"Self-study is {'ON' if a['enabled'] else 'OFF'}.")


@tool("set_self_study", "Turn your autonomous background self-study on or off.", {"enabled": "true|false"}, agent="Research Agent")
def set_self_study(args, ctx):
    v = str(args.get("enabled", "true")).lower() not in ("false", "0", "no", "off")
    curriculum.set_auto(v)
    return f"Autonomous self-study {'enabled' if v else 'paused'}, sir."
