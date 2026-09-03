# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import re
from . import tool
from .. import memory
from ..config import load_settings

try:
    import psutil
    HAS_PSUTIL = True
except Exception:
    HAS_PSUTIL = False


def system_metrics():
    if not HAS_PSUTIL:
        return {"cpu": 0, "ram": 0, "disk": 0, "online": False}
    return {"cpu": psutil.cpu_percent(interval=None), "ram": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("/").percent, "online": True}


def local_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(load_settings().get("timezone", "UTC")))
    except Exception:
        return datetime.now()


@tool("get_time", "Current local date and time.", {}, agent="System Agent")
def get_time(args, ctx):
    return local_now().strftime("%A, %d %B %Y, %H:%M")


@tool("system_status", "Server CPU/RAM/disk and memory statistics.", {}, agent="System Agent")
def system_status(args, ctx):
    m = system_metrics()
    s = memory.stats()
    return f"CPU {m['cpu']}%, RAM {m['ram']}%, disk {m['disk']}%. Memory: {s['memories']} memories, {s['lessons']} lessons across {s['skills']} skills, {s['tasks_open']} open tasks."


@tool("add_task", "Add a task to the operator's task list.", {"title": "string", "due": "optional ISO date/time"}, agent="Task Agent")
def add_task(args, ctx):
    memory.add_task(args.get("title", "").strip(), args.get("due"))
    memory.add_event("task", f"Task added: {args.get('title')}")
    return f"Task added: {args.get('title')}"


@tool("list_tasks", "List open tasks.", {}, agent="Task Agent")
def list_tasks(args, ctx):
    ts = memory.tasks()
    return "\n".join(f"#{t['id']} {t['title']}" + (f" (due {t['due']})" if t['due'] else "") for t in ts) or "No open tasks."


@tool("complete_task", "Mark a task done by id.", {"id": "integer"}, agent="Task Agent")
def complete_task(args, ctx):
    memory.complete_task(int(args.get("id")))
    return f"Task #{args.get('id')} completed."


def _parse_when(text: str):
    """'in 20 minutes', 'in 2 hours', 'tomorrow 9:00', '2026-06-15 14:30'."""
    t = (text or "").strip().lower()
    n = local_now().replace(tzinfo=None)
    m = re.match(r"in\s+(\d+)\s*(min|minute|minutes|h|hour|hours|day|days)", t)
    if m:
        v = int(m.group(1)); u = m.group(2)
        delta = timedelta(minutes=v) if u.startswith("min") else timedelta(hours=v) if u.startswith("h") else timedelta(days=v)
        return (n + delta).strftime("%Y-%m-%d %H:%M:%S")
    m = re.match(r"(tomorrow|today)\s*(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if m:
        h = int(m.group(2)); mi = int(m.group(3) or 0)
        if m.group(4) == "pm" and h < 12: h += 12
        d = n + (timedelta(days=1) if m.group(1) == "tomorrow" else timedelta())
        return d.replace(hour=h, minute=mi, second=0).strftime("%Y-%m-%d %H:%M:%S")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text.strip(), fmt).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return None


@tool("set_reminder", "Schedule a proactive reminder; J.A.R.V.I.S. will notify the operator's devices at that time.",
      {"when": "e.g. 'in 20 minutes', 'tomorrow 9:00', '2026-06-15 14:30'", "text": "what to say"}, agent="Task Agent")
def set_reminder(args, ctx):
    when = _parse_when(args.get("when", ""))
    if not when:
        return "Could not understand the time. Use 'in 20 minutes', 'tomorrow 9:00' or 'YYYY-MM-DD HH:MM'."
    memory.add_reminder(when, args.get("text", "Reminder"))
    memory.add_event("reminder", f"Reminder set for {when}: {args.get('text')}")
    return f"Reminder set for {when}."


@tool("remember", "Store an important fact about the operator or a decision in long-term memory.", {"text": "the fact"}, agent="Memory Agent")
def remember(args, ctx):
    memory.remember(args.get("text", ""), kind="fact")
    return "Committed to long-term memory."


@tool("recall", "Search long-term memory for past conversations and facts.", {"query": "what to look for"}, agent="Memory Agent")
def recall_tool(args, ctx):
    rows = memory.recall(args.get("query", ""), k=8)
    return "\n".join(f"[{r['ts']}] {r['text']}" for r in rows) or "Nothing relevant in memory."
