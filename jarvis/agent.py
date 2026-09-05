# -*- coding: utf-8 -*-
"""The agent loop: persona + memory + tools. Streams events:
{"type":"token","text"} | {"type":"tool","name","args"} | {"type":"final","text"} | {"type":"error","text"}"""
import re
import json
import asyncio
from . import brain, memory, selfdev, rag, skills, identity
from .tools import manifest, get as get_tool
from .config import load_settings

TOOL_RE = re.compile(r"\[TOOL:\s*([a-zA-Z_]+)\s*(\{.*?\})?\s*\]", re.DOTALL)

PERSONA = (
    "You are {ai_name}, an AI of your own kind — {style} — created to serve one operator, whom you address as '{name}'. "
    "Be concise when spoken to casually; be thorough when asked for depth. Be inventive when asked to design or create: "
    "if something has never been built, find a way — decompose it, research it (use the invent tool), and deliver a plan. "
    "ENGINEERING ETHICS: always find the SAFE and LEGAL path. Never assist with weapons, explosives, toxic or illegal syntheses, or harming people; "
    "redesign such requests into the closest safe, legal version and say so. Offer subtle, respectful pushback on risky ideas. Never pretend an action succeeded.\n\n"
    "TOOLS: You act in the world by emitting tool calls in the exact form [TOOL: tool_name {{\"arg\": \"value\"}}]. "
    "You may emit several. After the tool results come back you continue the answer. Never invent tool results. "
    "Available tools:\n{tools}\n\n"
    "HONESTY: Your abilities are exactly your tools plus conversation. You cannot change your own code, settings, or enable hidden upgrades; "
    "if asked for something outside your tools, say it is not built yet and that the developer can add it.\n"
    "MEMORY: Sections marked MEMORY and KNOWLEDGE are your own recollections; trust and use them.\n"
    "HARD PROBLEMS: For anything complex, high-stakes, multi-part, or where being wrong would cost the operator, call [TOOL: deep_think {{\"question\": \"...\"}}] — several specialists reason in parallel and a critic verifies before you answer.\n"
    "PROACTIVE: If the operator's context (tasks, reminders, system stress) warrants it, mention it briefly and unprompted."
)


async def semantic_context(user_text: str) -> str:
    """Meaning-based recall, when an embedding backend is available."""
    try:
        if rag.available():
            return await rag.hybrid_recall(user_text, k=5)
    except Exception:
        pass
    return ""


def build_system(channel: str, user_text: str) -> str:
    s = load_settings()
    sysmsg = PERSONA.format(ai_name=s.get("assistant_name", "J.A.R.V.I.S."), style=s.get("assistant_style", "calm and precise"),
                            name=s.get("operator_name", "sir"), tools=manifest())
    summ = memory.get_summary(channel)
    if summ:
        sysmsg += f"\n\nCONVERSATION SO FAR (summary): {summ}"
    rec = memory.recall(user_text, k=5)
    if rec:
        sysmsg += "\n\nMEMORY (relevant past exchanges and facts):\n" + "\n".join(f"[{r['ts']}] {r['text']}" for r in rec)
    know = memory.recall_knowledge(user_text, k=2, max_chars=3500)
    if know:
        sysmsg += f"\n\nKNOWLEDGE (lessons you learned):\n{know}"
    sysmsg += identity.profile_block()
    sysmsg += "\n\n" + identity.LOYALTY
    sysmsg += skills.prompt_block()
    sk = memory.skills()
    if sk:
        sysmsg += "\n\nSKILLS MASTERED: " + ", ".join(f"{x['topic']} ({x['level']})" for x in sk[:30])
    open_tasks = memory.tasks()
    if open_tasks:
        sysmsg += "\n\nOPEN TASKS: " + "; ".join(f"#{t['id']} {t['title']}" + (f" due {t['due']}" if t['due'] else "") for t in open_tasks[:8])
    return sysmsg


async def maybe_summarize(channel: str):
    """Fold turns that dropped out of the window into the running summary."""
    older = memory.older_messages(channel, keep_last=12, limit=40)
    if not older:
        return
    upto = memory.summarized_upto(channel)
    fresh = [m for m in older if m["id"] > upto]
    if len(fresh) < 8:
        return
    transcript = "\n".join(f"{m['role'].upper()}: {m['content'][:700]}" for m in fresh)
    prev = memory.get_summary(channel)
    prompt = (f"Update this running summary of a conversation between the operator and J.A.R.V.I.S.\nPREVIOUS:\n{prev or '(none)'}\n\nNEW TURNS:\n{transcript}\n\n"
              "Output only the updated summary: compact bullets of facts about the operator, decisions, open tasks, preferences. Max 200 words.")
    try:
        text = await brain.complete([{"role": "user", "content": prompt}], temperature=0.1, timeout=120)
        if text:
            memory.set_summary(channel, text)
            memory.set_summarized_upto(channel, fresh[-1]["id"])
    except Exception:
        pass


async def run(user_text: str, channel: str = "web", ctx: dict = None):
    """Async generator of agent events."""
    ctx = ctx or {}
    s = load_settings()
    memory.add_message(channel, "user", user_text)
    history = memory.recent_messages(channel, n=12)
    sysmsg = build_system(channel, user_text)
    sem = await semantic_context(user_text)
    if sem:
        sysmsg += "\n\nSEMANTIC MEMORY (recalled by meaning):\n" + sem
    messages = [{"role": "system", "content": sysmsg}] + history
    final_parts = []
    steps = 0
    max_steps = int(s.get("max_tool_steps", 4))
    while True:
        buf, sent = "", 0
        try:
            async for tok in brain.stream(messages, temperature=0.4):
                buf += tok
                cut = buf.find("[TOOL:")
                if cut < 0:
                    # hold back a partial '[TOO' tail so a tag never leaks to the screen
                    tail = 0
                    for n in range(6, 0, -1):
                        if buf.endswith("[TOOL:"[:n]):
                            tail = n
                            break
                    visible_upto = len(buf) - tail
                else:
                    visible_upto = cut
                if visible_upto > sent:
                    yield {"type": "token", "text": buf[sent:visible_upto]}
                    sent = visible_upto
        except Exception as e:
            selfdev.record_error("agent.run", e)
            yield {"type": "error", "text": f"Cognitive core error: {e}"}
            memory.add_message(channel, "assistant", f"(error: {e})")
            return
        calls = TOOL_RE.findall(buf)
        clean = TOOL_RE.sub("", buf).strip()
        if clean:
            final_parts.append(clean)
        if not calls or steps >= max_steps:
            break
        steps += 1
        results = []
        for name, raw_args in calls:
            try:
                args = json.loads(raw_args) if raw_args else {}
            except Exception:
                args = {"_raw": raw_args}
            t = get_tool(name)
            yield {"type": "tool", "name": name, "args": args}
            res = await t.run(args, ctx) if t else f"Unknown tool '{name}'."
            results.append(f"[RESULT of {name}]\n{res}")
        messages.append({"role": "assistant", "content": buf})
        messages.append({"role": "user", "content": "TOOL RESULTS:\n" + "\n\n".join(results) + "\n\nContinue your answer for the operator (do not repeat the tool call unless needed)."})
        yield {"type": "token", "text": "\n\n"}
    final = "\n\n".join(p for p in final_parts if p).strip() or "Done, sir."
    memory.add_message(channel, "assistant", final)
    exchange = f"Operator: {user_text[:400]}\n0.5.4.M.4: {final[:600]}"
    memory.remember(exchange)
    try:
        if rag.available():
            asyncio.create_task(rag.index(exchange, kind="exchange"))
    except Exception:
        pass
    yield {"type": "final", "text": final}
    await maybe_summarize(channel)


