# -*- coding: utf-8 -*-
"""Missions — long-running work that continues 24/7 until it is done.

A mission survives restarts (checkpointed to the database), works in steps,
verifies its own progress, and pauses to ask the operator when it needs a
decision. Loop protection stops it burning quota on a step that will not move.
"""
import json
import asyncio
from datetime import datetime
from . import memory, brain
from .loopguard import LoopGuard

_running = {}


def _table():
    memory.db().executescript("""
    CREATE TABLE IF NOT EXISTS missions(
      id INTEGER PRIMARY KEY, ts TEXT, goal TEXT, state TEXT, step INTEGER DEFAULT 0,
      plan TEXT, log TEXT, result TEXT, question TEXT, answer TEXT, updated TEXT);
    """)
    memory.db().commit()


def create(goal: str) -> int:
    _table()
    cur = memory.db().execute(
        "INSERT INTO missions(ts, goal, state, plan, log, updated) VALUES (?,?,?,?,?,?)",
        (memory.now(), goal, "planning", "[]", "", memory.now()))
    memory.db().commit()
    memory.add_event("task", f"Mission started: {goal[:80]}")
    return cur.lastrowid


def get(mid: int):
    _table()
    r = memory.db().execute("SELECT * FROM missions WHERE id=?", (mid,)).fetchone()
    return dict(r) if r else None


def all_missions(active_only=True):
    _table()
    sql = "SELECT id, goal, state, step, question, updated FROM missions"
    if active_only:
        sql += " WHERE state NOT IN ('done','failed','cancelled')"
    return [dict(r) for r in memory.db().execute(sql + " ORDER BY id DESC LIMIT 20").fetchall()]


def update(mid: int, **fields):
    if not fields:
        return
    fields["updated"] = memory.now()
    sets = ", ".join(f"{k}=?" for k in fields)
    memory.db().execute(f"UPDATE missions SET {sets} WHERE id=?", (*fields.values(), mid))
    memory.db().commit()


def log(mid: int, line: str):
    m = get(mid)
    if m:
        update(mid, log=((m.get("log") or "") + f"[{datetime.now().strftime('%H:%M')}] {line}\n")[-8000:])


def answer(mid: int, text: str):
    """The operator answers a mission's pending question; work resumes."""
    update(mid, answer=text, question="", state="running")
    memory.add_event("task", f"Mission #{mid} unblocked by the operator")
    start(mid)
    return f"Mission #{mid} resumed with your answer."


async def _ask_operator(mid: int, question: str):
    update(mid, state="waiting", question=question)
    memory.add_event("alert", f"Mission #{mid} needs your approval: {question[:120]}")
    memory.add_message("web", "assistant", f"🔔 **Mission #{mid} needs you, sir:** {question}")
    try:
        from .push import notify_all
        await notify_all("0.5.4.M.4 needs approval", question[:180])
    except Exception:
        pass


async def _plan(goal: str):
    prompt = (f"GOAL: {goal}\n\nBreak this into 3-8 concrete steps that can be executed one at a time. "
              "Each step must be a single actionable instruction. Return ONLY a JSON array of strings.")
    try:
        raw = await brain.complete([{"role": "user", "content": prompt}], temperature=0.2, timeout=180)
        s, e = raw.find("["), raw.rfind("]")
        steps = json.loads(raw[s:e + 1]) if s >= 0 else []
        return [str(x) for x in steps][:8] or [goal]
    except Exception:
        return [goal]


async def _run(mid: int):
    """Execute a mission step by step, checkpointing after each one."""
    from .agent import run as agent_run
    m = get(mid)
    if not m:
        return
    try:
        plan = json.loads(m.get("plan") or "[]")
        if not plan:
            update(mid, state="planning")
            plan = await _plan(m["goal"])
            update(mid, plan=json.dumps(plan), state="running")
            log(mid, f"Planned {len(plan)} steps")

        guard = LoopGuard(max_attempts=3, label=f"mission #{mid}")
        while True:
            m = get(mid)
            if not m or m["state"] in ("cancelled", "done", "failed", "waiting"):
                return
            step = m["step"]
            if step >= len(plan):
                break
            instruction = plan[step]
            log(mid, f"Step {step + 1}/{len(plan)}: {instruction}")
            ctx_note = f"(Working on mission #{mid}: {m['goal']}. " \
                       f"{'The operator answered: ' + m['answer'] if m.get('answer') else ''} " \
                       f"Progress so far:\n{(m.get('log') or '')[-1500:]})"
            final = ""
            async for ev in agent_run(f"{instruction}\n\n{ctx_note}", channel=f"mission{mid}"):
                if ev["type"] in ("final", "error"):
                    final = ev["text"]
            log(mid, f"→ {final[:400]}")

            low = final.lower()
            if any(k in low for k in ("i need your", "please confirm", "should i", "which would you prefer",
                                      "needs your approval", "cannot proceed without")):
                await _ask_operator(mid, final[:400])
                return
            stall = guard.track(instruction + final[:200], final if "error" in low or "failed" in low else "")
            if stall and ("error" in low or "failed" in low):
                log(mid, f"Stalled: {stall}")
                await _ask_operator(mid, guard.report(stall, extra=f"Mission #{mid} is stuck on step {step + 1}."))
                return
            update(mid, step=step + 1, answer="")
            await asyncio.sleep(2)

        summary_prompt = f"GOAL: {m['goal']}\n\nWORK LOG:\n{(get(mid) or {}).get('log', '')[-4000:]}\n\nWrite a short report of what was accomplished."
        result = await brain.complete([{"role": "user", "content": summary_prompt}], temperature=0.3, timeout=180)
        update(mid, state="done", result=result)
        memory.add_event("task", f"Mission #{mid} complete: {m['goal'][:60]}")
        memory.add_message("web", "assistant", f"✅ **Mission #{mid} complete, sir.**\n\n{result}")
        try:
            from .push import notify_all
            await notify_all("Mission complete", m["goal"][:120])
        except Exception:
            pass
    except Exception as e:
        from . import selfdev
        selfdev.record_error(f"mission{mid}", e)
        update(mid, state="failed", result=str(e))
        log(mid, f"Failed: {e}")
    finally:
        _running.pop(mid, None)


def start(mid: int) -> bool:
    if mid in _running:
        return False
    try:
        _running[mid] = asyncio.get_event_loop().create_task(_run(mid))
        return True
    except RuntimeError:
        return False


async def resume_all():
    """On boot, pick up any mission that was mid-flight."""
    _table()
    for m in all_missions():
        if m["state"] in ("running", "planning"):
            memory.add_event("task", f"Resuming mission #{m['id']} after restart")
            start(m["id"])
