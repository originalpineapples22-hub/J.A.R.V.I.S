# -*- coding: utf-8 -*-
"""File system — browse, read, edit, create and organise files.

Scoped to a workspace root for safety: it can do anything inside the workspace
and its own output folder, but never touch system files or credentials.
"""
import os
import shutil
import difflib
from pathlib import Path
from . import tool
from .. import memory
from ..config import FILES_DIR, DATA_DIR

WORKSPACE = Path(os.environ.get("JARVIS_WORKSPACE", DATA_DIR / "workspace"))
WORKSPACE.mkdir(parents=True, exist_ok=True)
ROOTS = [WORKSPACE.resolve(), FILES_DIR.resolve()]
BLOCKED = {"settings.json", "token.txt", "vapid.json", ".env"}
TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".json", ".yml", ".yaml", ".html", ".css",
            ".csv", ".sh", ".c", ".cpp", ".java", ".go", ".rs", ".sql", ".xml", ".toml", ".ini", ".log"}


def _safe(p: str) -> Path:
    """Resolve a path and refuse anything outside the workspace."""
    q = Path(p).expanduser()
    if not q.is_absolute():
        q = WORKSPACE / q
    q = q.resolve()
    if q.name in BLOCKED:
        raise PermissionError(f"'{q.name}' is protected")
    if not any(str(q).startswith(str(r)) for r in ROOTS):
        raise PermissionError(f"'{p}' is outside the workspace")
    return q


@tool("list_files", "Browse the file system: list a folder's contents with sizes and types.",
      {"path": "folder, default the workspace root"}, agent="File Agent")
def list_files_tool(args, ctx):
    try:
        d = _safe(args.get("path") or ".")
    except Exception as e:
        return str(e)
    if not d.exists():
        return f"No such folder: {d}"
    if d.is_file():
        return f"{d.name} — {d.stat().st_size} bytes (a file, not a folder)"
    rows = []
    for p in sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        rows.append(f"{'📁' if p.is_dir() else '📄'} {p.name}" + ("" if p.is_dir() else f"  ({p.stat().st_size} bytes)"))
    rel = str(d).replace(str(WORKSPACE), "workspace")
    return f"{rel} — {len(rows)} item(s):\n" + "\n".join(rows[:200]) or "(empty)"


@tool("read_file", "Read a file's contents.", {"path": "file path", "start": "optional first line", "end": "optional last line"}, agent="File Agent")
def read_file(args, ctx):
    try:
        p = _safe(args.get("path", ""))
    except Exception as e:
        return str(e)
    if not p.exists() or p.is_dir():
        return f"No such file: {p}"
    if p.suffix.lower() not in TEXT_EXT and p.stat().st_size > 200_000:
        return f"{p.name} is a binary or very large file ({p.stat().st_size} bytes)."
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Could not read: {e}"
    lines = text.splitlines()
    a = int(args.get("start") or 1); b = int(args.get("end") or min(len(lines), 400))
    chunk = "\n".join(f"{i:>4}| {l}" for i, l in enumerate(lines[a - 1:b], start=a))
    return f"{p.name} ({len(lines)} lines):\n{chunk[:12000]}"


@tool("write_file", "Create or overwrite a file with new content.", {"path": "file path", "content": "full content"}, agent="File Agent")
def write_file(args, ctx):
    try:
        p = _safe(args.get("path", ""))
    except Exception as e:
        return str(e)
    p.parent.mkdir(parents=True, exist_ok=True)
    old = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    if old:
        (DATA_DIR / "file_backups").mkdir(exist_ok=True)
        shutil.copy(p, DATA_DIR / "file_backups" / f"{p.name}.bak")
    p.write_text(args.get("content", ""), encoding="utf-8")
    memory.add_event("file", f"Wrote {p.name}")
    return f"Wrote {p.name} ({len(args.get('content', ''))} chars)." + (" Previous version backed up." if old else "")


@tool("edit_file", "Change part of a file: replace exact text with new text.",
      {"path": "file path", "find": "exact text to replace", "replace": "new text"}, agent="File Agent")
def edit_file(args, ctx):
    try:
        p = _safe(args.get("path", ""))
    except Exception as e:
        return str(e)
    if not p.exists():
        return f"No such file: {p}"
    text = p.read_text(encoding="utf-8", errors="replace")
    find = args.get("find", "")
    if find not in text:
        return f"Could not find that text in {p.name}. Read the file first to copy the exact wording."
    new = text.replace(find, args.get("replace", ""), 1)
    (DATA_DIR / "file_backups").mkdir(exist_ok=True)
    shutil.copy(p, DATA_DIR / "file_backups" / f"{p.name}.bak")
    p.write_text(new, encoding="utf-8")
    diff = "\n".join(list(difflib.unified_diff(text.splitlines(), new.splitlines(), lineterm="", n=1))[:20])
    memory.add_event("file", f"Edited {p.name}")
    return f"Edited {p.name}.\n{diff}"


@tool("search_files", "Search file contents or names across the workspace.",
      {"query": "text to find", "path": "optional folder"}, agent="File Agent")
def search_files(args, ctx):
    q = (args.get("query") or "").lower()
    try:
        root = _safe(args.get("path") or ".")
    except Exception as e:
        return str(e)
    hits = []
    for p in root.rglob("*"):
        if not p.is_file() or p.name in BLOCKED:
            continue
        if q in p.name.lower():
            hits.append(f"📄 {p.relative_to(root)} (filename)")
        elif p.suffix.lower() in TEXT_EXT and p.stat().st_size < 2_000_000:
            try:
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if q in line.lower():
                        hits.append(f"📄 {p.relative_to(root)}:{i}  {line.strip()[:120]}")
                        break
            except Exception:
                pass
        if len(hits) >= 60:
            break
    return "\n".join(hits) if hits else f"Nothing matching '{q}'."


@tool("manage_file", "Move, copy, rename or delete a file or folder.",
      {"action": "move|copy|delete|mkdir", "path": "source", "to": "destination for move/copy"}, agent="File Agent")
def manage_file(args, ctx):
    action = (args.get("action") or "").lower()
    try:
        p = _safe(args.get("path", ""))
        dest = _safe(args["to"]) if args.get("to") else None
    except Exception as e:
        return str(e)
    try:
        if action == "mkdir":
            p.mkdir(parents=True, exist_ok=True); return f"Created folder {p.name}."
        if action == "delete":
            if p.is_dir():
                shutil.rmtree(p)
            else:
                (DATA_DIR / "file_backups").mkdir(exist_ok=True)
                shutil.copy(p, DATA_DIR / "file_backups" / f"{p.name}.deleted")
                p.unlink()
            memory.add_event("file", f"Deleted {p.name}")
            return f"Deleted {p.name} (a copy was kept in backups)."
        if not dest:
            return "Give a destination with 'to'."
        dest.parent.mkdir(parents=True, exist_ok=True)
        if action == "move":
            shutil.move(str(p), str(dest)); return f"Moved to {dest.name}."
        if action == "copy":
            shutil.copytree(p, dest) if p.is_dir() else shutil.copy(p, dest)
            return f"Copied to {dest.name}."
        return "Unknown action. Use move, copy, delete or mkdir."
    except Exception as e:
        return f"Failed: {e}"
