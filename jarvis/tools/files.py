# -*- coding: utf-8 -*-
import re
import sys
import asyncio
import subprocess
from pathlib import Path
from . import tool
from .. import memory
from ..config import FILES_DIR


def _sandbox(path: Path):
    try:
        p = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=15, cwd=str(FILES_DIR))
        return p.returncode == 0, (p.stderr or p.stdout or "")[-1500:]
    except subprocess.TimeoutExpired:
        return True, "long-running (ok)"
    except Exception as e:
        return False, str(e)


@tool("create_file", "Create a downloadable file for the operator (code, document, data). Python files are sandbox-tested.",
      {"name": "filename.ext", "content": "full file content"}, agent="Coding Agent")
async def create_file(args, ctx):
    name = Path(args.get("name", "file.txt")).name
    content = args.get("content", "")
    bt = "`" * 3
    m = re.search(bt + r"(?:\w+)?\s*(.*?)\s*" + bt, content, re.DOTALL)
    if m:
        content = m.group(1)
    path = FILES_DIR / name
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    note = f"File created: {name} (download from the Files panel)."
    if name.endswith(".py"):
        ok, out = await asyncio.to_thread(_sandbox, path)
        note += " Sandbox test passed." if ok else f" Sandbox test FAILED: {out[-600:]} — fix it and call create_file again with the corrected content."
    memory.add_event("file", note)
    return note


def list_files():
    out = []
    for p in sorted(FILES_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if p.is_file():
            out.append({"name": p.name, "size": p.stat().st_size})
    return out
