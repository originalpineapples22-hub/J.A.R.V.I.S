# -*- coding: utf-8 -*-
"""Inventor mode: for goals nobody has built — decompose, research in parallel,
cross-check physics/chemistry, and produce a safe, legal, step-by-step plan."""
import json
import asyncio
from . import tool
from .. import brain, memory
from .web import web_search


@tool("invent", "Deep research + engineering plan for an ambitious or novel goal (e.g. 'a wrist-mounted web shooter'). Decomposes the problem, researches sub-problems in parallel, checks feasibility, and returns a safe and legal build plan with materials and math. Takes ~30-60s.",
      {"goal": "what to create", "constraints": "optional: budget, tools available, skill level"}, agent="Research Agent")
async def invent(args, ctx):
    goal = args.get("goal", "").strip()
    cons = args.get("constraints", "")
    plan_prompt = (f"Goal: {goal}\nConstraints: {cons or 'none stated'}\n\n"
                   "Break this into 4-6 concrete sub-problems an engineer must solve (mechanism, materials, power/energy, control, safety/legal, fabrication). "
                   "Return ONLY a JSON list of short web-search queries, one per sub-problem.")
    try:
        raw = await brain.complete([{"role": "user", "content": plan_prompt}], temperature=0.2, timeout=90)
        start, end = raw.find("["), raw.rfind("]")
        queries = json.loads(raw[start:end + 1]) if start >= 0 else [goal]
        queries = [str(q) for q in queries][:6]
    except Exception:
        queries = [goal, f"{goal} materials", f"{goal} physics", f"{goal} safety"]
    results = await asyncio.gather(*[web_search({"query": q}, ctx) for q in queries])
    research = "\n\n".join(f"### {q}\n{r[:1500]}" for q, r in zip(queries, results))
    synth = (f"You are an inventive but rigorous engineer. Using the research below plus your own knowledge, produce a plan for: {goal}\n"
             f"Constraints: {cons or 'none'}\n\nRESEARCH:\n{research}\n\n"
             "Write: 1) Concept & how it works (physics/chemistry with numbers), 2) Bill of materials with realistic sourcing, 3) Step-by-step build, "
             "4) Key calculations (show formulas), 5) Testing plan, 6) SAFETY & LEGAL: hazards, protective measures, and what is prohibited — "
             "if the goal as stated is dangerous or illegal, redesign it into the closest SAFE, LEGAL version and say so clearly. Be concrete and creative.")
    try:
        plan = await brain.complete([{"role": "user", "content": synth}], temperature=0.5, timeout=240)
    except Exception as e:
        return f"Inventor synthesis failed: {e}"
    memory.add_lesson(f"Invention: {goal}", "engineering plan", plan)
    memory.add_event("learn", f"Inventor plan produced: {goal}")
    return plan
