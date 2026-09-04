# -*- coding: utf-8 -*-
"""Acting on the world: smart home, webhooks, and autonomous browsing."""
import json
import asyncio
import httpx
from . import tool
from .. import memory
from ..config import load_settings


@tool("smart_home",
      "Control the physical environment through Home Assistant: lights, plugs, climate, scenes; or read a sensor.",
      {"action": "turn_on|turn_off|toggle|set|state", "entity": "e.g. light.bedroom", "value": "optional brightness/temperature"},
      agent="System Agent")
async def smart_home(args, ctx):
    s = load_settings()
    base = (s.get("homeassistant_url") or "").rstrip("/")
    token = (s.get("homeassistant_token") or "").strip()
    if not base or not token:
        return "Home Assistant is not linked yet, sir. Add its URL and a long-lived access token in Settings."
    entity = args.get("entity", "")
    action = (args.get("action") or "state").lower()
    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            if action == "state":
                r = await c.get(f"{base}/api/states/{entity}", headers=H)
                d = r.json()
                return f"{entity} is {d.get('state')} ({d.get('attributes', {}).get('friendly_name', '')})."
            domain = entity.split(".")[0] or "homeassistant"
            svc = {"turn_on": "turn_on", "turn_off": "turn_off", "toggle": "toggle", "set": "turn_on"}.get(action, "turn_on")
            payload = {"entity_id": entity}
            if args.get("value") not in (None, ""):
                v = args["value"]
                if domain == "light":
                    payload["brightness_pct"] = int(float(v))
                elif domain == "climate":
                    payload["temperature"] = float(v)
            r = await c.post(f"{base}/api/services/{domain}/{svc}", headers=H, json=payload)
            r.raise_for_status()
        memory.add_event("system", f"Smart home: {action} {entity}")
        return f"Done — {entity} {action.replace('_', ' ')}."
    except Exception as e:
        return f"Home Assistant call failed: {e}"


@tool("trigger_webhook",
      "Fire an automation webhook (Make.com, Zapier, IFTTT, n8n) to do anything they can do — send email, update a sheet, post a message.",
      {"name": "the saved webhook name, or a full URL", "data": "optional JSON payload"}, agent="System Agent")
async def trigger_webhook(args, ctx):
    s = load_settings()
    hooks = {}
    try:
        hooks = json.loads(s.get("webhooks") or "{}")
    except Exception:
        pass
    name = args.get("name", "")
    url = hooks.get(name) or (name if name.startswith("http") else "")
    if not url:
        return (f"No webhook called '{name}'. Saved: {', '.join(hooks) or 'none'}. "
                "Add them in Settings as JSON, e.g. {\"email me\": \"https://hook.eu2.make.com/...\"}")
    payload = args.get("data")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {"text": payload}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, json=payload or {})
        memory.add_event("system", f"Webhook fired: {name}")
        return f"Webhook '{name}' fired (HTTP {r.status_code})."
    except Exception as e:
        return f"Webhook failed: {e}"


@tool("browse",
      "Open a real browser to read pages that need JavaScript, or to follow a short sequence of steps and report what is there. Read-only: it will not log in or submit payments.",
      {"url": "starting URL", "goal": "what to find or do (e.g. 'get the price', 'click Next and read results')"},
      agent="Browser Agent")
async def browse(args, ctx):
    url = args.get("url", "")
    goal = args.get("goal", "read the page")
    try:
        from playwright.async_api import async_playwright
    except Exception:
        from .web import fetch_url
        return (await fetch_url({"url": url}, ctx)) + "\n(Static fetch — install Playwright on the server for full browsing.)"
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch(args=["--no-sandbox"])
            pg = await (await b.new_context(user_agent="Mozilla/5.0 0.5.4.M.4")).new_page()
            await pg.goto(url, wait_until="domcontentloaded", timeout=45000)
            await pg.wait_for_timeout(1500)
            title = await pg.title()
            text = await pg.evaluate("document.body.innerText")
            links = await pg.evaluate("Array.from(document.querySelectorAll('a')).slice(0,25).map(a=>a.innerText.trim()+' -> '+a.href).filter(x=>x.length>8)")
            await b.close()
        return (f"PAGE: {title}\nGOAL: {goal}\n\nCONTENT:\n{text[:5000]}\n\nLINKS:\n" + "\n".join(links[:15]))
    except Exception as e:
        return f"Browsing failed: {e}"


@tool("semantic_recall", "Search your memory by meaning rather than keywords.", {"query": "string"}, agent="Memory Agent")
async def semantic_recall(args, ctx):
    from .. import rag
    if not rag.available():
        from .. import memory as m
        rows = m.recall(args.get("query", ""), k=6)
        return "\n".join(f"[{r['ts']}] {r['text']}" for r in rows) or "Nothing relevant found."
    return await rag.hybrid_recall(args.get("query", ""), k=6) or "Nothing relevant found."


@tool("index_memory", "Re-index your memories and lessons so semantic recall covers everything.", {}, agent="Memory Agent")
async def index_memory(args, ctx):
    from .. import rag
    return await rag.backfill()
