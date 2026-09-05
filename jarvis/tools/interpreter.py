# -*- coding: utf-8 -*-
"""Code Interpreter — the sandboxed data-analysis power ChatGPT is known for,
native to 0.5.4.M.4: it writes and runs analysis code, and renders the chart
straight into the operator's live window."""
import re
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from . import tool
from .. import brain, memory
from ..config import FILES_DIR
from .preview import _publish, SHELL

TIMEOUT = 45


def _run_py(code: str, workdir: Path):
    p = workdir / "_analysis.py"
    p.write_text(code, encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True,
                           timeout=TIMEOUT, cwd=str(workdir))
        return r.returncode == 0, ((r.stdout or "") + ("\n" + r.stderr if r.stderr else ""))[-4000:]
    except subprocess.TimeoutExpired:
        return False, f"Analysis exceeded {TIMEOUT}s and was stopped."
    except Exception as e:
        return False, str(e)


@tool("analyse_data",
      "Analyse data properly: writes and RUNS real Python (statistics, tables, calculations), fixes its own errors, and renders any chart into the live window. Use for datasets, numbers, CSV files or 'work this out for me'.",
      {"task": "what to find out", "data": "the numbers/CSV inline, or a file path in the workspace"},
      agent="Coding Agent")
async def analyse_data(args, ctx):
    task = args.get("task", "")
    data = args.get("data", "")
    workdir = FILES_DIR
    data_note = data[:4000]
    if data and len(data) < 300 and Path(data.strip()).suffix:
        from .filesystem import _safe
        try:
            p = _safe(data.strip())
            if p.exists():
                data_note = f"(file at {p.name})\n" + p.read_text(encoding="utf-8", errors="replace")[:4000]
                data = str(p)
        except Exception:
            pass

    prompt = (f"TASK: {task}\n\nDATA:\n{data_note}\n\n"
              "Write a single Python script that performs this analysis. Rules:\n"
              "- Only the standard library plus (if useful) json/csv/math/statistics. Do NOT import pandas, "
              "numpy or matplotlib — they may not be installed.\n"
              "- print() clear results with labels.\n"
              "- If a chart helps, also print a final line exactly: CHART_JSON=<json> where json is "
              '{"type":"line|bar|pie","title":str,"labels":[...],"series":[{"name":str,"data":[...]}]}\n'
              "Return only the code in one ```python fence.")
    code = ""
    out = ""
    for attempt in range(3):
        draft = await brain.complete([{"role": "user", "content": prompt if attempt == 0 else
            f"{prompt}\n\nYour previous code failed:\n{out}\n\nPREVIOUS CODE:\n{code}\n\nReturn the corrected script."}],
            temperature=0.1, timeout=240)
        m = re.search(r"```(?:python)?\s*(.*?)```", draft, re.DOTALL)
        code = (m.group(1) if m else draft).strip()
        ok, out = await asyncio.to_thread(_run_py, code, workdir)
        if ok:
            break
    if not ok:
        return f"The analysis would not run after three attempts. Last error:\n{out[:800]}"

    chart_line = next((l for l in out.splitlines() if l.strip().startswith("CHART_JSON=")), None)
    clean = "\n".join(l for l in out.splitlines() if not l.strip().startswith("CHART_JSON="))
    note = ""
    if chart_line:
        try:
            spec = json.loads(chart_line.split("=", 1)[1])
            from .preview import show_chart
            note = "\n\n" + show_chart({"title": spec.get("title", task[:40]), "type": spec.get("type", "bar"),
                                        "labels": spec.get("labels", []), "series": spec.get("series", [])}, ctx)
        except Exception:
            pass
    memory.add_event("file", f"Analysis run: {task[:60]}")
    return f"**Analysis**\n```\n{clean[:2500]}\n```{note}"


@tool("run_python_sandbox",
      "Run Python code in an isolated sandbox and return exactly what it printed. Use to compute something for certain rather than estimating.",
      {"code": "python source"}, agent="Coding Agent")
async def run_python_sandbox(args, ctx):
    code = args.get("code", "")
    m = re.search(r"```(?:python)?\s*(.*?)```", code, re.DOTALL)
    if m:
        code = m.group(1)
    ok, out = await asyncio.to_thread(_run_py, code, FILES_DIR)
    return ("OUTPUT:\n" + out) if ok else ("ERROR:\n" + out)
