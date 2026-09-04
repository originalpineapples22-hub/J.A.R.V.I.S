# -*- coding: utf-8 -*-
"""The Council — multi-agent reasoning.

For hard questions one pass from one model is the weakest link. The Council
decomposes the problem, runs specialists IN PARALLEL, has a critic attack the
draft, then synthesises a verified answer. This is the largest genuine quality
gain available without changing the underlying model.

Flow:  plan -> [specialist, specialist, ...] in parallel -> critique -> revise
"""
import json
import asyncio
from . import brain, memory

PLANNER = (
    "You are the planning mind of 0.5.4.M.4. Break the operator's request into 2-4 INDEPENDENT "
    "sub-questions that different specialists can answer at the same time. Each must be answerable "
    "on its own. Return ONLY a JSON array of objects: "
    '[{"role": "short specialist title", "question": "the sub-question"}]'
)
CRITIC = (
    "You are a ruthless technical critic. Find factual errors, unsupported claims, missing steps, "
    "safety problems and wrong maths in the draft. Be specific and brief. "
    "If the draft is sound, reply exactly: NO ISSUES."
)


async def _ask(system: str, user: str, temp=0.3, timeout=180) -> str:
    return await brain.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temp, timeout=timeout)


async def deliberate(question: str, context: str = "", on_event=None) -> str:
    """Run the full council. `on_event(stage, detail)` is optional progress."""
    async def ev(stage, detail=""):
        if on_event:
            try:
                await on_event(stage, detail)
            except Exception:
                pass

    # 1. plan
    await ev("planning")
    try:
        raw = await _ask(PLANNER, f"REQUEST:\n{question}\n\nCONTEXT:\n{context[:2000]}", 0.2, 120)
        s, e = raw.find("["), raw.rfind("]")
        tasks = json.loads(raw[s:e + 1]) if s >= 0 else []
        tasks = [t for t in tasks if isinstance(t, dict) and t.get("question")][:4]
    except Exception:
        tasks = []
    if not tasks:
        tasks = [{"role": "Analyst", "question": question}]

    # 2. specialists in parallel
    await ev("consulting", ", ".join(t.get("role", "Analyst") for t in tasks))
    async def specialist(t):
        sys = (f"You are the {t.get('role', 'Analyst')} of 0.5.4.M.4. Answer your assigned sub-question "
               "precisely and concretely. State uncertainty plainly rather than guessing. Be concise.")
        try:
            return f"### {t.get('role', 'Analyst')}\n" + await _ask(sys, t["question"] + (f"\n\nCONTEXT:\n{context[:1500]}" if context else ""), 0.3, 180)
        except Exception as ex:
            return f"### {t.get('role','Analyst')}\n(unavailable: {ex})"
    findings = "\n\n".join(await asyncio.gather(*[specialist(t) for t in tasks]))

    # 3. draft
    await ev("drafting")
    draft = await _ask(
        "You are 0.5.4.M.4. Synthesise the specialist findings into one coherent, well-structured answer "
        "for the operator. Do not mention the specialists or this process.",
        f"REQUEST:\n{question}\n\nFINDINGS:\n{findings}", 0.4, 240)

    # 4. critique
    await ev("verifying")
    issues = await _ask(CRITIC, f"REQUEST:\n{question}\n\nDRAFT:\n{draft}", 0.1, 180)
    if "NO ISSUES" in issues.upper() or len(issues.strip()) < 40:
        memory.add_event("system", "Council answer verified with no issues")
        return draft

    # 5. revise
    await ev("revising")
    final = await _ask(
        "You are 0.5.4.M.4. Rewrite the draft so every criticism is resolved. Keep what was correct. "
        "Output only the corrected answer.",
        f"REQUEST:\n{question}\n\nDRAFT:\n{draft}\n\nCRITICISM:\n{issues}", 0.35, 300)
    memory.add_event("system", f"Council revised an answer after critique ({len(tasks)} specialists)")
    return final
