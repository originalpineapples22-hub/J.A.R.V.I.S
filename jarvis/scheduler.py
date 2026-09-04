# -*- coding: utf-8 -*-
"""Proactive behaviour: due reminders, daily briefing, system alerts → push notifications + feed."""
import asyncio
from datetime import datetime
from . import memory, brain
from .push import notify_all
from .config import load_settings
from .tools.system import system_metrics, local_now
from . import curriculum, selfdev

_last_briefing_day = None
_last_alert = 0.0
_last_repair = 0.0


async def loop():
    global _last_briefing_day, _last_alert
    import time
    while True:
        try:
            for r in memory.due_reminders():
                memory.mark_reminder_sent(r["id"])
                memory.add_event("reminder", f"Reminder: {r['text']}")
                await notify_all("J.A.R.V.I.S.", f"Sir, a reminder: {r['text']}")

            s = load_settings()
            now = local_now()
            hour = int(s.get("briefing_hour", 8))
            if hour >= 0 and now.hour == hour and _last_briefing_day != now.date():
                _last_briefing_day = now.date()
                await daily_briefing()

            # unprompted self-repair: if a fault was recorded, try to fix it
            global _last_repair
            errs = selfdev.recent_errors(1)
            if errs and time.time() - _last_repair > 1800:
                _last_repair = time.time()
                res = await selfdev.auto_repair()
                memory.add_event("system", f"Auto-repair: {res[:160]}")
                if res.startswith("⚠️"):
                    # it got stuck repairing itself — tell the operator, do not keep trying
                    memory.add_message("web", "assistant", res)
                    await notify_all("0.5.4.M.4 needs you",
                                     "I could not repair a fault on my own — details are in the command centre.")

            m = system_metrics()
            import time
            if m["online"] and (m["cpu"] > 92 or m["ram"] > 92) and time.time() - _last_alert > 900:
                _last_alert = time.time()
                memory.add_event("alert", f"Server load high: CPU {m['cpu']}% RAM {m['ram']}%")
        except Exception as e:
            selfdev.record_error('scheduler', e)
        await asyncio.sleep(30)


async def daily_briefing():
    tasks = memory.tasks()
    rem = memory.upcoming_reminders(5)
    skills = memory.skills()
    ctx = (f"Date: {local_now().strftime('%A %d %B %Y')}. Open tasks: {[t['title'] for t in tasks][:8]}. "
           f"Upcoming reminders: {[(r['when_ts'], r['text']) for r in rem]}. Skills mastered: {len(skills)}.")
    try:
        text = await brain.complete([{"role": "system", "content": "You are J.A.R.V.I.S. Write a 2-3 sentence spoken morning briefing for 'sir': date, tasks, anything due. Dry wit welcome."},
                                     {"role": "user", "content": ctx}], temperature=0.5, timeout=60)
    except Exception:
        text = f"Good morning, sir. You have {len(tasks)} open tasks today."
    memory.add_event("briefing", text)
    memory.add_message("web", "assistant", "☀️ " + text)
    await notify_all("J.A.R.V.I.S. — Morning briefing", text)
