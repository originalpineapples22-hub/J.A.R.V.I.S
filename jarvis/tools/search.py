# -*- coding: utf-8 -*-
"""Agent-grade search and guaranteed-correct computation."""
import httpx
from . import tool
from ..config import load_settings


@tool("deep_search",
      "Best-quality web research: returns a clean synthesised answer with sources instead of raw links. Use for anything factual or current.",
      {"query": "string", "depth": "basic|advanced"}, agent="Research Agent")
async def deep_search(args, ctx):
    s = load_settings()
    key = (s.get("tavily_key") or "").strip()
    q = args.get("query", "")
    if key:
        try:
            async with httpx.AsyncClient(timeout=45) as c:
                r = await c.post("https://api.tavily.com/search", json={
                    "api_key": key, "query": q,
                    "search_depth": args.get("depth", "advanced"),
                    "include_answer": True, "max_results": 6})
                r.raise_for_status()
                d = r.json()
            out = []
            if d.get("answer"):
                out.append("ANSWER: " + d["answer"])
            for it in d.get("results", [])[:6]:
                out.append(f"- {it.get('title')}: {(it.get('content') or '')[:300]} ({it.get('url')})")
            return "\n".join(out) or "No results."
        except Exception as e:
            pass  # fall through to the free search
    from .web import web_search
    return await web_search({"query": q}, ctx)


@tool("compute_exact",
      "Mathematically guaranteed answers via Wolfram Alpha — equations, unit conversions, physics, chemistry, engineering. Use whenever the number must be right.",
      {"query": "e.g. 'solve x^2+3x-4=0' or 'resistance of 30m copper wire 1.5mm2'"}, agent="Research Agent")
async def compute_exact(args, ctx):
    s = load_settings()
    key = (s.get("wolfram_appid") or "").strip()
    q = args.get("query", "")
    if not key:
        from .science import calculate
        res = calculate({"expression": q}, ctx)
        return (f"{res}\n(Computed locally — add a free Wolfram Alpha AppID in Settings for "
                f"guaranteed-exact answers on harder questions.)")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get("https://api.wolframalpha.com/v1/result", params={"appid": key, "i": q})
            if r.status_code == 200:
                return f"{q} = {r.text}"
            r2 = await c.get("https://api.wolframalpha.com/v2/query",
                             params={"appid": key, "input": q, "output": "json", "format": "plaintext"})
            pods = r2.json().get("queryresult", {}).get("pods", [])
            out = [f"{p.get('title')}: {p['subpods'][0].get('plaintext','')}" for p in pods[:4] if p.get("subpods")]
            return "\n".join(out) or "Wolfram Alpha had no result for that."
    except Exception as e:
        return f"Wolfram Alpha failed: {e}"
