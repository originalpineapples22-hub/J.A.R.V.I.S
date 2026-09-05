# -*- coding: utf-8 -*-
"""Deep Research — the multi-round, fully-cited investigation that ChatGPT and
Perplexity are known for, implemented natively so it belongs to 0.5.4.M.4.

Rounds: plan queries -> gather in parallel -> find the gaps -> gather again ->
write a sourced report. Every claim carries a numbered citation.
"""
import re
import json
import asyncio
from . import tool
from .. import brain, memory
from .web import web_search, fetch_url


async def _gather(queries, ctx):
    from .search import deep_search
    results = await asyncio.gather(*[deep_search({"query": q}, ctx) for q in queries])
    return list(zip(queries, results))


def _sources(blocks):
    """Pull URLs out of the gathered text and number them."""
    urls, seen = [], set()
    for _, txt in blocks:
        for u in re.findall(r"https?://[^\s)\]]+", txt or ""):
            u = u.rstrip(".,;")
            if u not in seen:
                seen.add(u)
                urls.append(u)
    return urls[:20]


@tool("deep_research",
      "A full research investigation on any subject: plans its own questions, searches many sources in parallel, identifies what is still missing, searches again, then writes a structured report with numbered citations. Takes a minute or two — use it when the answer really matters.",
      {"topic": "what to investigate", "depth": "quick|standard|thorough"}, agent="Research Agent")
async def deep_research(args, ctx):
    topic = (args.get("topic") or "").strip()
    if not topic:
        return "What should I investigate, sir?"
    depth = (args.get("depth") or "standard").lower()
    n_first = {"quick": 3, "standard": 5, "thorough": 7}.get(depth, 5)

    plan = await brain.complete([{"role": "user", "content":
        f"TOPIC: {topic}\n\nWrite {n_first} distinct web-search queries that together would let an expert "
        "answer this thoroughly, covering different angles (definitions, current state, evidence, "
        "counter-arguments, practical application). Return ONLY a JSON array of strings."}],
        temperature=0.3, timeout=120)
    try:
        s, e = plan.find("["), plan.rfind("]")
        queries = [str(q) for q in json.loads(plan[s:e + 1])][:n_first]
    except Exception:
        queries = [topic, f"{topic} evidence", f"{topic} criticism"]

    memory.add_event("learn", f"Deep research started: {topic[:70]}")
    round1 = await _gather(queries, ctx)
    corpus = "\n\n".join(f"## {q}\n{r[:2500]}" for q, r in round1)

    if depth != "quick":
        gaps = await brain.complete([{"role": "user", "content":
            f"TOPIC: {topic}\n\nRESEARCH SO FAR:\n{corpus[:6000]}\n\n"
            "What important questions remain unanswered? Return ONLY a JSON array of 2-3 follow-up "
            "search queries that would close the biggest gaps."}], temperature=0.3, timeout=120)
        try:
            s, e = gaps.find("["), gaps.rfind("]")
            follow = [str(q) for q in json.loads(gaps[s:e + 1])][:3]
        except Exception:
            follow = []
        if follow:
            round2 = await _gather(follow, ctx)
            corpus += "\n\n" + "\n\n".join(f"## {q}\n{r[:2500]}" for q, r in round2)
            round1 += round2

    srcs = _sources(round1)
    src_list = "\n".join(f"[{i+1}] {u}" for i, u in enumerate(srcs))
    report = await brain.complete([{"role": "user", "content":
        f"TOPIC: {topic}\n\nRESEARCH CORPUS:\n{corpus[:14000]}\n\nNUMBERED SOURCES:\n{src_list}\n\n"
        "Write a rigorous report: a two-line summary, then findings organised under headings, then "
        "'What is uncertain', then a short conclusion. Cite claims with [n] matching the source numbers. "
        "Say plainly where evidence is thin. Do not invent sources."}],
        temperature=0.35, timeout=400)

    memory.add_lesson(f"Research: {topic}", "investigation", report)
    memory.add_event("learn", f"Deep research complete: {topic[:70]}")
    return report + ("\n\n**Sources**\n" + src_list if srcs else "")


@tool("fact_check", "Verify a specific claim against live sources and say whether it holds, with citations.",
      {"claim": "the statement to check"}, agent="Research Agent")
async def fact_check(args, ctx):
    claim = args.get("claim", "")
    from .search import deep_search
    ev = await asyncio.gather(
        deep_search({"query": claim}, ctx),
        deep_search({"query": f"{claim} evidence against OR debunked OR criticism"}, ctx))
    return await brain.complete([{"role": "user", "content":
        f"CLAIM: {claim}\n\nSUPPORTING SEARCH:\n{ev[0][:3000]}\n\nOPPOSING SEARCH:\n{ev[1][:3000]}\n\n"
        "Verdict: TRUE / MOSTLY TRUE / MIXED / MOSTLY FALSE / FALSE / UNVERIFIABLE. Then the evidence "
        "for and against with source URLs, then one line of what would settle it."}],
        temperature=0.2, timeout=240)
