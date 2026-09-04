# -*- coding: utf-8 -*-
"""Capability Index — an honest 1000-point scale.

The score is a capability meter, not a clinical IQ. It is weighted by real
impact across seven dimensions, and the single largest factor is the quality of
the underlying brain, because that is what actually determines how well it
thinks. 1000 is only reachable with every connector linked AND a frontier model.
"""
from .config import load_settings

# dimension -> maximum points (sums to 1000)
DIMENSIONS = {
    "Reasoning":  260,   # brain quality + deliberation + exact computation
    "Knowledge":  150,
    "Memory":     130,
    "Creation":   140,
    "Action":     140,
    "Perception": 100,
    "Autonomy":    80,
}

# id, name, dimension, points, auth, note
CATALOG = [
    # --- Reasoning (brain tier is scored separately, worth up to 150 here)
    ("council",     "Council (multi-agent)",  "Reasoning",  30, "live", "Specialists reason in parallel, a critic verifies"),
    ("verifier",    "Self-Verification",      "Reasoning",  15, "live", "Checks its own answers before delivering"),
    ("science",     "Science Sandbox",        "Reasoning",  20, "live", "Physics, chemistry, symbolic maths"),
    ("inventor",    "Inventor Mode",          "Reasoning",  25, "live", "Designs what has not been built"),
    ("wolfram",     "Wolfram Alpha",          "Reasoning",  20, "key",  "Mathematically exact computation"),
    # --- Knowledge
    ("websearch",   "Web Search",             "Knowledge",  20, "live", "Search the open web"),
    ("tavily",      "Tavily Research",        "Knowledge",  25, "key",  "Synthesised, sourced answers"),
    ("wikipedia",   "Wikipedia",              "Knowledge",  10, "live", "Encyclopedia"),
    ("youtube",     "YouTube",                "Knowledge",  15, "live", "Understands any video"),
    ("livedata",    "Live Data",              "Knowledge",  20, "live", "Weather, news, prayer, FX, crypto, time"),
    ("curriculum",  "109-Tech Curriculum",    "Knowledge",  30, "live", "Built-in mastery path for 109 technologies"),
    ("translate",   "Translator",             "Knowledge",  10, "live", "Any language"),
    ("maps",        "Google Maps",            "Knowledge",  10, "key",  "Places, routes, travel time"),
    ("stocks",      "Markets",                "Knowledge",  10, "key",  "Quotes and watchlists"),
    # --- Memory
    ("memory",      "Long-Term Memory",       "Memory",     35, "live", "Never forgets, across restarts"),
    ("rag",         "Semantic Memory (RAG)",  "Memory",     40, "live", "Recall by meaning, not keywords"),
    ("summaries",   "Rolling Summaries",      "Memory",     20, "live", "Keeps the thread of long conversations"),
    ("notion",      "Notion",                 "Memory",     20, "key",  "Your notes and databases"),
    ("gdrive",      "Google Drive/Docs",      "Memory",     15, "oauth","Your documents"),
    # --- Creation
    ("coder",       "Code Fabricator",        "Creation",   25, "live", "Writes real, runnable programs"),
    ("codeloop",    "Self-Fixing Coder",      "Creation",   30, "live", "Runs, debugs and repairs its own code"),
    ("office",      "Office Suite",           "Creation",   25, "live", "PowerPoint, Word, Excel"),
    ("files",       "File Fabrication",       "Creation",   15, "live", "Any file, downloadable"),
    ("music",       "YouTube Music",          "Creation",   10, "live", "Plays anything by voice"),
    ("github",      "GitHub",                 "Creation",   20, "key",  "Repos, issues, pull requests"),
    ("threed",      "3D / CAD Generation",    "Creation",   15, "live", "Parametric models for printing"),
    # --- Action
    ("pc",          "PC Control",             "Action",     25, "agent","Drives your computer"),
    ("browser",     "Autonomous Browser",     "Action",     25, "live", "Real Chromium for any site"),
    ("smarthome",   "Home Assistant",         "Action",     25, "key",  "Lights, plugs, climate, sensors"),
    ("webhooks",    "Automation Hooks",       "Action",     20, "key",  "Make / Zapier / n8n"),
    ("gmail",       "Gmail",                  "Action",     20, "oauth","Read, summarise, send"),
    ("gcalendar",   "Google Calendar",        "Action",     15, "oauth","Agenda and events"),
    ("discord",     "Discord",                "Action",     10, "key",  "Chat and voice calls"),
    # --- Perception
    ("voice_in",    "Whisper Hearing",        "Perception", 25, "live", "Accurate speech, no invented words"),
    ("voice_out",   "Natural Speech",         "Perception", 15, "live", "Speaks back"),
    ("elevenlabs",  "ElevenLabs Voice",       "Perception", 15, "key",  "Cinematic, cloneable voice"),
    ("vision",      "Vision",                 "Perception", 25, "live", "Sees screens, photos, documents"),
    ("hologram",    "Hand Tracking",          "Perception", 20, "live", "Hologram mode with hand control"),
    # --- Autonomy
    ("selfdev",     "Self-Development",       "Autonomy",   30, "live", "Fixes its own code, auto-rollback"),
    ("autolearn",   "Autonomous Study",       "Autonomy",   25, "live", "Learns by itself, unprompted"),
    ("proactive",   "Proactive Agent",        "Autonomy",   25, "live", "Reminders, briefings, alerts it starts"),
]

# Brain tiers — the largest single factor in real intelligence (max 110 of Reasoning)
BRAIN_TIERS = [
    (150, ("claude", "opus", "sonnet", "gpt-5", "gpt-4.1", "o3", "gemini-2.5-pro", "grok-4")),
    (100, ("gpt-4o", "70b", "llama-4", "large", "qwen3-32b", "command-r-plus", "deepseek")),
    (65,  ("8b", "mini", "flash", "small", "instant", "gemma", "mistral")),
]
BRAIN_MAX = 150


def _brain_points(s) -> tuple:
    prov = s.get("provider", "groq")
    model = (s.get("groq_model") or s.get("openai_model") or s.get("ollama_model") or "").lower()
    if not (s.get("groq_api_key") or s.get("openai_api_key") or prov == "ollama"):
        return 0, "no brain configured"
    for pts, keys in BRAIN_TIERS:
        if any(k in model for k in keys):
            return pts, model or prov
    return 65, model or prov


def _credential_present(cid, s):
    m = {
        "gmail": "google_token", "gcalendar": "google_token", "gdrive": "google_token",
        "discord": "discord_bot_token", "notion": "notion_key", "github": "github_token",
        "maps": "google_maps_key", "stocks": "stocks_key", "smarthome": "homeassistant_token",
        "tavily": "tavily_key", "wolfram": "wolfram_appid", "elevenlabs": "elevenlabs_key",
        "webhooks": "webhooks",
    }
    key = m.get(cid)
    if not key:
        return False
    v = s.get(key)
    return bool(v) and v not in ("{}", "")


def status():
    s = load_settings()
    from .tools.pc import pc_connected
    items, dims = [], {d: {"earned": 0, "max": m} for d, m in DIMENSIONS.items()}

    brain_pts, brain_name = _brain_points(s)
    dims["Reasoning"]["earned"] += brain_pts

    for cid, name, dim, pts, auth, note in CATALOG:
        if auth == "live":
            active = True
        elif auth == "agent":
            active = pc_connected()
        else:
            active = _credential_present(cid, s)
        # semantic memory only counts when an embedding backend exists
        if cid == "rag":
            try:
                from . import rag
                active = rag.available()
            except Exception:
                active = False
        if active:
            dims[dim]["earned"] += pts
        items.append({"id": cid, "name": name, "category": dim, "iq": pts, "auth": auth,
                      "note": note, "active": active})

    index = sum(d["earned"] for d in dims.values())
    return {
        "index": index, "potential": 1000, "scale": 1000,
        "brain": {"points": brain_pts, "max": BRAIN_MAX, "model": brain_name},
        "dimensions": dims,
        "active_count": sum(1 for i in items if i["active"]),
        "total_count": len(items),
        "connectors": items,
    }
