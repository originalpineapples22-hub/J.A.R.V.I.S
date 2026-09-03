# -*- coding: utf-8 -*-
"""Fast autonomous learning: 10-module curriculum researched and written IN PARALLEL on the cloud brain."""
import asyncio
from . import brain, memory
from .tools.web import web_search

CURRICULUM = [
    "core syntax, variables and data types",
    "control flow, functions and error handling",
    "data structures and collections",
    "object oriented and idiomatic design patterns",
    "standard library and essential built-ins",
    "modules, packages and project structure",
    "concurrency, async and performance optimization",
    "testing, debugging and profiling",
    "ecosystem, tooling and package management",
    "advanced real-world usage, security and best practices",
]
_running: dict = {}


def status():
    return {t: v for t, v in _running.items()}


def start_study(topic: str) -> bool:
    if topic in _running:
        return False
    _running[topic] = {"done": 0, "total": len(CURRICULUM), "state": "running"}
    asyncio.get_event_loop().create_task(_study(topic))
    memory.add_event("learn", f"Study session started: {topic}")
    return True


async def _module(topic, sub, sem):
    async with sem:
        research = await web_search({"query": f"{topic} {sub}"}, {})
        prompt = (f"Write a thorough lesson about '{topic}' — specifically: '{sub}'. Combine this research with your own knowledge. "
                  f"Include code examples, syntax, pitfalls and best practices. Output only the lesson.\n\nRESEARCH:\n{research[:3000]}")
        try:
            text = await brain.complete([{"role": "user", "content": prompt}], temperature=0.1, timeout=300)
        except Exception as e:
            text = ""
        if len(text) > 100:
            memory.add_lesson(topic, sub, text)
            _running[topic]["done"] += 1
            return True
        return False


async def _study(topic):
    sem = asyncio.Semaphore(4)
    results = await asyncio.gather(*[_module(topic, sub, sem) for sub in CURRICULUM])
    learned = sum(1 for r in results if r)
    level = "MASTER" if learned >= len(CURRICULUM) - 1 else f"TRAINED ({learned}/{len(CURRICULUM)})"
    memory.set_skill(topic, level, f"{learned}/{len(CURRICULUM)}")
    memory.add_event("learn", f"Study complete: {topic} — {level}")
    memory.remember(f"J.A.R.V.I.S. completed a study session on {topic} ({level}).", kind="learning")
    _running[topic]["state"] = "done"
    try:
        from .push import notify_all
        await notify_all("J.A.R.V.I.S.", f"Study complete, sir: {topic} — {level}.")
    except Exception:
        pass
    await asyncio.sleep(30)
    _running.pop(topic, None)
