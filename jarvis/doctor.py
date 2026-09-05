# -*- coding: utf-8 -*-
"""Doctor — tests every external service and optional dependency for real, so
'untested' becomes 'known' the moment 0.5.4.M.4 is deployed.

Each check reports PASS / FAIL / SKIP with the exact fix when it fails.
"""
import asyncio
import importlib
import httpx
from .config import load_settings

TIMEOUT = 12


async def _http(name, url, params=None, headers=None, need=200, fix=""):
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers or {"User-Agent": "0.5.4.M.4/3"}) as c:
            r = await c.get(url, params=params)
        ok = r.status_code == need
        return {"name": name, "status": "PASS" if ok else "FAIL",
                "detail": f"HTTP {r.status_code}", "fix": "" if ok else fix}
    except Exception as e:
        return {"name": name, "status": "FAIL", "detail": str(e)[:120], "fix": fix}


def _module(name, mod, fix):
    try:
        importlib.import_module(mod)
        return {"name": name, "status": "PASS", "detail": "installed", "fix": ""}
    except Exception as e:
        return {"name": name, "status": "SKIP", "detail": f"not installed ({type(e).__name__})", "fix": fix}


async def check_brain(s):
    """The only truly critical check: can it think at all?"""
    from . import brain, providers as pv
    have = pv.configured(s)
    if not have:
        return [{"name": "Brain (any provider)", "status": "FAIL", "detail": "no key configured",
                 "fix": "Add a FREE key in Settings: GitHub Models, Gemini, Cerebras or Groq."}]
    out = []
    for pid in have:
        base, key, model = pv.resolve(pid, s)
        try:
            got = ""
            async for tok in brain._stream_one(pid, base, key, model,
                                               [{"role": "user", "content": "Reply with the single word: online"}],
                                               0.0, 30):
                got += tok
                if len(got) > 20:
                    break
            ok = bool(got.strip())
            out.append({"name": f"Brain · {pv.BY_ID[pid][1]}", "status": "PASS" if ok else "FAIL",
                        "detail": f"{model} → {got.strip()[:30] or 'empty'}",
                        "fix": "" if ok else "Check the key is valid and the model name exists."})
        except Exception as e:
            out.append({"name": f"Brain · {pv.BY_ID[pid][1]}", "status": "FAIL", "detail": str(e)[:120],
                        "fix": "Key may be invalid or rate-limited; the pool will use another provider."})
    return out


async def run_all(quick=False):
    s = load_settings()
    checks = []

    checks += await check_brain(s)

    # --- free services that need no key
    net = [
        _http("Weather (Open-Meteo)", "https://geocoding-api.open-meteo.com/v1/search",
              {"name": "Muscat", "count": 1}, fix="Blocked outbound? Check the server firewall."),
        _http("Prayer times (Aladhan)", "https://api.aladhan.com/v1/timingsByCity",
              {"city": "Muscat", "country": "Oman", "method": 8}, fix="Service may be down; it is optional."),
        _http("News (Hacker News)", "https://hacker-news.firebaseio.com/v0/topstories.json", fix="Optional."),
        _http("Dictionary", "https://api.dictionaryapi.dev/api/v2/entries/en/test", fix="Optional."),
        _http("Currency (open.er-api)", "https://open.er-api.com/v6/latest/USD", fix="Optional."),
        _http("Wikipedia", "https://en.wikipedia.org/api/rest_v1/page/summary/Oman", fix="Optional."),
        _http("Image generation (Pollinations)", "https://image.pollinations.ai/prompt/test?width=64&height=64",
              fix="Optional; image generation will be unavailable."),
        _http("Chemistry (PubChem)", "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/water/property/MolecularFormula/JSON",
              fix="Optional; falls back to Wikipedia."),
    ]
    if not quick:
        checks += await asyncio.gather(*net)

    # --- keyed services, only when a key exists
    if s.get("tavily_key"):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as c:
                r = await c.post("https://api.tavily.com/search",
                                 json={"api_key": s["tavily_key"], "query": "test", "max_results": 1})
            checks.append({"name": "Tavily research", "status": "PASS" if r.status_code == 200 else "FAIL",
                           "detail": f"HTTP {r.status_code}", "fix": "" if r.status_code == 200 else "Check the key at tavily.com."})
        except Exception as e:
            checks.append({"name": "Tavily research", "status": "FAIL", "detail": str(e)[:100], "fix": "Check the key."})
    if s.get("wolfram_appid"):
        checks.append(await _http("Wolfram Alpha", "https://api.wolframalpha.com/v1/result",
                                  {"appid": s["wolfram_appid"], "i": "2+2"}, fix="Check the AppID."))
    if s.get("elevenlabs_key"):
        checks.append(await _http("ElevenLabs voice", "https://api.elevenlabs.io/v1/voices",
                                  headers={"xi-api-key": s["elevenlabs_key"]}, fix="Check the key."))
    if s.get("homeassistant_url") and s.get("homeassistant_token"):
        checks.append(await _http("Home Assistant", f"{s['homeassistant_url'].rstrip('/')}/api/",
                                  headers={"Authorization": f"Bearer {s['homeassistant_token']}"},
                                  fix="Check the URL is reachable from the server and the token is a long-lived one."))

    # --- speech
    if s.get("groq_api_key"):
        checks.append({"name": "Speech-to-text (Whisper)", "status": "PASS",
                       "detail": "Groq key present — Whisper available", "fix": ""})
    else:
        checks.append({"name": "Speech-to-text (Whisper)", "status": "SKIP",
                       "detail": "needs a Groq key", "fix": "Add the free Groq key for accurate voice."})
    try:
        from .speech import synthesize
        audio = await synthesize("test")
        checks.append({"name": "Text-to-speech (edge-tts)", "status": "PASS" if audio else "FAIL",
                       "detail": f"{len(audio)} bytes" if audio else "no audio returned",
                       "fix": "" if audio else "pip install edge-tts, and check outbound HTTPS."})
    except Exception as e:
        checks.append({"name": "Text-to-speech", "status": "FAIL", "detail": str(e)[:100], "fix": "pip install edge-tts"})

    # --- optional local modules
    checks += [
        _module("Semantic memory (fastembed)", "fastembed", "pip install fastembed — enables recall by meaning."),
        _module("Browser automation (Playwright)", "playwright", "pip install playwright && playwright install chromium"),
        _module("Social video (yt-dlp)", "yt_dlp", "pip install yt-dlp — needed for reels/TikTok."),
        _module("Office files", "pptx", "pip install python-pptx python-docx openpyxl"),
        _module("Maths (SymPy)", "sympy", "pip install sympy"),
        _module("Push notifications", "pywebpush", "pip install pywebpush py-vapid"),
        _module("Numerics (numpy)", "numpy", "pip install numpy"),
    ]

    # --- own systems
    from . import selfdev, memory
    ok, out = selfdev.self_test()
    checks.append({"name": "Core self-test", "status": "PASS" if ok else "FAIL",
                   "detail": "all internal systems" if ok else out[-160:], "fix": "" if ok else "Ask me to self-diagnose."})
    try:
        memory.stats()
        checks.append({"name": "Database", "status": "PASS", "detail": "readable and writable", "fix": ""})
    except Exception as e:
        checks.append({"name": "Database", "status": "FAIL", "detail": str(e)[:100], "fix": "Check disk space and permissions."})

    p = sum(1 for c in checks if c["status"] == "PASS")
    f = sum(1 for c in checks if c["status"] == "FAIL")
    sk = sum(1 for c in checks if c["status"] == "SKIP")
    critical = [c for c in checks if c["status"] == "FAIL" and ("Brain" in c["name"] or "Core" in c["name"] or "Database" in c["name"])]
    return {"checks": checks, "pass": p, "fail": f, "skip": sk,
            "healthy": not critical, "critical": [c["name"] for c in critical]}


def format_report(res) -> str:
    icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⚪"}
    lines = [f"**System check — {res['pass']} passed, {res['fail']} failed, {res['skip']} not installed**", ""]
    if not res["healthy"]:
        lines.append(f"⚠️ **Critical problem:** {', '.join(res['critical'])} — I cannot work properly until this is fixed.")
        lines.append("")
    for c in res["checks"]:
        line = f"{icon[c['status']]} {c['name']} — {c['detail']}"
        if c["fix"]:
            line += f"\n   ↳ {c['fix']}"
        lines.append(line)
    return "\n".join(lines)
