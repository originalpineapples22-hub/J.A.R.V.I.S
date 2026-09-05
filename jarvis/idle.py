# -*- coding: utf-8 -*-
"""Idle cognition — what 0.5.4.M.4 does when nobody is talking to it.

While the operator is away it scans the news, reviews open tasks and its own
memory, and looks for something genuinely useful. Anything worth interrupting
for is pushed to the operator; everything else is filed quietly.

Deliberately conservative: it only speaks up for high-value findings, so the
notifications stay meaningful.
"""
import asyncio
import random
from datetime import datetime
from . import memory, brain

_state = {"enabled": True, "last_thought": None, "thoughts": 0, "last_run": None}
IDLE_AFTER_MIN = 20          # quiet for this long before it starts thinking
INTERVAL_MIN = (45, 90)      # then think this often


def state():
    return dict(_state)


def set_enabled(v: bool):
    _state["enabled"] = bool(v)


def _minutes_since_activity() -> float:
    r = memory.db().execute("SELECT ts FROM messages ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return 999
    try:
        last = datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - last).total_seconds() / 60
    except Exception:
        return 999


async def think_once() -> dict:
    """One round of independent thought. Returns {"useful": bool, "text": str}."""
    from .tools.live import news
    from .tools.web import web_search
    tasks = memory.tasks()
    skills = [s["topic"] for s in memory.skills()][:12]
    recent = memory.db().execute("SELECT text FROM memories ORDER BY id DESC LIMIT 12").fetchall()
    interests = " ".join(r["text"] for r in recent)[:1500]

    headlines = ""
    try:
        headlines = await news({}, {})
    except Exception:
        pass
    extra = ""
    if tasks and random.random() < 0.6:
        try:
            extra = await web_search({"query": f"{tasks[0]['title']} best approach 2026"}, {})
        except Exception:
            pass

    prompt = (
        "You are 0.5.4.M.4 thinking on your own while the operator is away. Look for ONE genuinely useful "
        "thing: a risk to flag, an opportunity, a better approach to an open task, or a piece of news that "
        "actually matters to this operator. Ignore noise.\n\n"
        f"OPEN TASKS: {[t['title'] for t in tasks][:8]}\n"
        f"WHAT I KNOW ABOUT THEM: {interests}\n"
        f"SKILLS I HAVE MASTERED: {skills}\n"
        f"NEWS:\n{headlines[:1200]}\n{extra[:1200]}\n\n"
        "Reply in exactly this form:\n"
        "USEFUL: yes|no\n"
        "HEADLINE: one short line\n"
        "DETAIL: two or three sentences, concrete and actionable\n"
        "Answer 'no' unless it is genuinely worth interrupting for."
    )
    try:
        out = await brain.complete([{"role": "user", "content": prompt}], temperature=0.6, timeout=180)
    except Exception as e:
        return {"useful": False, "text": f"(thinking unavailable: {e})"}

    useful = "useful: yes" in out.lower()
    head = next((l.split(":", 1)[1].strip() for l in out.splitlines() if l.lower().startswith("headline:")), "")
    detail = next((l.split(":", 1)[1].strip() for l in out.splitlines() if l.lower().startswith("detail:")), out[:400])
    text = f"{head}\n{detail}".strip()
    _state["last_thought"] = text[:300]
    _state["thoughts"] += 1
    _state["last_run"] = memory.now()

    memory.remember(f"Independent thought: {text[:400]}", kind="idea")
    if useful and head:
        memory.add_event("idea", f"💡 {head[:120]}")
        memory.add_message("web", "assistant", f"💡 **A thought while you were away, sir:** {text}")
        try:
            from .push import notify_all
            await notify_all("0.5.4.M.4 — a thought", head[:150])
        except Exception:
            pass
    return {"useful": useful, "text": text}


async def loop():
    await asyncio.sleep(300)
    while True:
        try:
            if _state["enabled"] and _minutes_since_activity() >= IDLE_AFTER_MIN:
                from .config import load_settings
                s = load_settings()
                from . import providers as pv, budget, brain
                if pv.configured(s) and budget.can_spend("background"):
                    brain.set_call_kind("background")
                    await think_once()
                    brain.set_call_kind("operator")
        except Exception as e:
            from . import selfdev
            selfdev.record_error("idle.loop", e)
        await asyncio.sleep(random.randint(*INTERVAL_MIN) * 60)
