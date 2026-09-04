# -*- coding: utf-8 -*-
"""Connector catalog + Capability Index. Each connector adds 'IQ' points (a
playful capability score, not a clinical IQ). 'live' = works now (no login);
'oauth'/'key' = ready to activate once its credential is added after deploy."""
from .config import load_settings

BASE_IQ = 100  # baseline cognition of the brain itself

CATALOG = [
    # id, name, category, iq, auth, note
    ("weather",     "Weather",          "Live Data",     6,  "live",  "Forecasts (Open-Meteo, no key)"),
    ("prayer",      "Prayer Times",     "Live Data",     4,  "live",  "Accurate times for your city (Aladhan)"),
    ("news",        "World News",       "Live Data",     6,  "live",  "Top headlines"),
    ("dictionary",  "Dictionary",       "Live Data",     3,  "live",  "Definitions & synonyms"),
    ("currency",    "Currency & Crypto","Live Data",     5,  "live",  "FX + crypto prices"),
    ("worldtime",   "World Clock",      "Live Data",     2,  "live",  "Time in any city"),
    ("wikipedia",   "Wikipedia",        "Knowledge",     6,  "live",  "Encyclopedia lookup"),
    ("websearch",   "Web Search",       "Knowledge",     8,  "live",  "Search the whole web"),
    ("youtube",     "YouTube",          "Knowledge",     6,  "live",  "Answer questions about videos"),
    ("science",     "Science Sandbox",  "Reasoning",    10,  "live",  "Physics, chemistry, symbolic math"),
    ("inventor",    "Inventor Mode",    "Reasoning",    12,  "live",  "Design what nobody has built"),
    ("office",      "Office Suite",     "Creation",      8,  "live",  "PowerPoint, Word, Excel"),
    ("coder",       "Code Fabricator",  "Creation",      9,  "live",  "Write & sandbox-test programs"),
    ("learn",       "Self-Learning",    "Reasoning",    10,  "live",  "Master any tech in minutes"),
    ("memory",      "Long-Term Memory", "Core",          8,  "live",  "Remembers everything, forever"),
    ("pc",          "PC Control",       "Control",       7,  "agent", "Drive your PC (needs PC agent)"),
    ("vision",      "Screen/Cam Vision","Perception",    7,  "live",  "See screen & webcam"),
    # activate after deploy + credential
    ("gmail",       "Gmail",            "Google",        9,  "oauth", "Read, summarise, draft & send"),
    ("gcalendar",   "Google Calendar",  "Google",        7,  "oauth", "Agenda, events, reminders"),
    ("gdrive",      "Google Drive/Docs","Google",        6,  "oauth", "Read & create documents"),
    ("gtasks",      "Google Tasks",     "Google",        3,  "oauth", "Sync to-dos"),
    ("ytmusic",     "YouTube Music",    "Media",         5,  "live",  "Play any song or playlist by voice"),
    ("discord",     "Discord",          "Messaging",     7,  "key",   "Chat + voice calls with 0.5.4.M.4"),
    ("notion",      "Notion",           "Productivity",  6,  "key",   "Your notes & databases"),
    ("github",      "GitHub",           "Productivity",  6,  "key",   "Repos, issues, notifications"),
    ("maps",        "Google Maps",      "Live Data",     4,  "key",   "Travel time, 'when to leave'"),
    ("stocks",      "Stocks",           "Live Data",     4,  "key",   "Market quotes & watchlist"),
    ("smarthome",   "Smart Home",       "Control",       6,  "key",   "Lights, plugs, climate"),
    ("email_imap",  "Any Email (IMAP)", "Messaging",     6,  "key",   "Non-Google inboxes"),
    ("translate",   "Translator",       "Live Data",     4,  "live",  "Any language, both ways"),
]

# which live connectors are considered active (their tools are always available)
_LIVE_ACTIVE = {c[0] for c in CATALOG if c[4] == "live"}


def _credential_present(cid, s):
    m = {
        "gmail": "google_token", "gcalendar": "google_token", "gdrive": "google_token", "gtasks": "google_token",
        "discord": "discord_bot_token", "notion": "notion_key",
        "github": "github_token", "maps": "google_maps_key", "stocks": "stocks_key",
        "smarthome": "smarthome_token", "email_imap": "imap_password",
    }
    key = m.get(cid)
    return bool(key and s.get(key))


def status():
    s = load_settings()
    from .tools.pc import pc_connected
    items, active_iq = [], 0
    for cid, name, cat, iq, auth, note in CATALOG:
        if auth == "live":
            active = cid in _LIVE_ACTIVE
        elif auth == "agent":
            active = pc_connected()
        else:
            active = _credential_present(cid, s)
        if active:
            active_iq += iq
        items.append({"id": cid, "name": name, "category": cat, "iq": iq, "auth": auth, "note": note, "active": active})
    total = BASE_IQ + active_iq
    potential = BASE_IQ + sum(c[3] for c in CATALOG)
    return {"base": BASE_IQ, "index": total, "potential": potential,
            "active_count": sum(1 for i in items if i["active"]), "total_count": len(items),
            "connectors": items}
