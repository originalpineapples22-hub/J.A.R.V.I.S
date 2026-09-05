# -*- coding: utf-8 -*-
"""Identity — who the operator is, and how 0.5.4.M.4 recognises them.

Three layers:
  1. PROFILE  — everything it knows about the operator, learned and remembered
  2. FACE     — face descriptors enrolled from the camera (matched in the browser)
  3. VOICE    — voice fingerprints enrolled from the microphone

The operator is the first priority: this file defines the loyalty directive
that goes into every system prompt.
"""
import json
import math
from datetime import datetime
from . import memory

# How close a match must be to count. Face descriptors are 128-d and well
# separated; voice fingerprints are coarser, so the bar is set lower and the
# result is always reported as "likely" rather than certain.
FACE_THRESHOLD = 0.55
VOICE_THRESHOLD = 0.62      # on mean-centred vectors, where chance ≈ 0


def _table():
    memory.db().executescript("""
    CREATE TABLE IF NOT EXISTS identity(key TEXT PRIMARY KEY, value TEXT, ts TEXT);
    CREATE TABLE IF NOT EXISTS biometrics(id INTEGER PRIMARY KEY, kind TEXT, label TEXT, vec TEXT, ts TEXT);
    CREATE TABLE IF NOT EXISTS people(name TEXT PRIMARY KEY, role TEXT, note TEXT, ts TEXT);
    """)
    memory.db().commit()


# ---------------------------------------------------------------- household
ROLES = ("owner", "family", "guest")

# Everything a non-owner may use. Anything not listed is owner-only, so new
# tools are private by default rather than accidentally exposed.
PUBLIC_TOOLS = {
    "get_time", "world_time", "weather", "prayer_times", "news", "dictionary", "currency",
    "translate", "web_search", "deep_search", "fetch_url", "youtube_transcript", "watch_video",
    "calculate", "physics", "statistics", "chemistry_lookup", "compute_exact",
    "generate_image", "show_chart", "show_diagram", "show_preview", "play_music",
    "make_presentation", "make_document", "make_spreadsheet", "run_python_sandbox",
    "deep_research", "fact_check", "see_image", "verify", "analyse_data",
}


def add_person(name: str, role: str = "family", note: str = ""):
    _table()
    role = role if role in ROLES else "guest"
    memory.db().execute("INSERT OR REPLACE INTO people(name, role, note, ts) VALUES (?,?,?,?)",
                        (name.strip(), role, note, memory.now()))
    memory.db().commit()
    return f"{name} added as {role}."


def people():
    _table()
    return [dict(r) for r in memory.db().execute("SELECT * FROM people ORDER BY role, name").fetchall()]


def remove_person(name: str):
    _table()
    memory.db().execute("DELETE FROM people WHERE name=?", (name.strip(),))
    memory.db().execute("DELETE FROM biometrics WHERE label=?", (name.strip(),))
    memory.db().commit()
    return f"{name} removed, and their face and voice samples deleted."


def role_of(label: str) -> str:
    if not label or label == "operator":
        return "owner"
    _table()
    r = memory.db().execute("SELECT role FROM people WHERE name=?", (label,)).fetchone()
    return r["role"] if r else "guest"


def allowed(tool_name: str, role: str) -> bool:
    return True if role == "owner" else tool_name in PUBLIC_TOOLS


def guest_prompt(role: str, who: str = "") -> str:
    """Replaces the owner's private context when someone else is using it."""
    p = profile()
    owner = p.get("call_me") or p.get("name") or "the operator"
    name_line = f"You are speaking with {who}, who is {role}. " if who else f"You are speaking with a {role}, NOT the operator. "
    return (
        f"\n\nWHO YOU ARE SPEAKING TO: {name_line}"
        f"This is {owner}'s personal assistant, lent to you for this conversation.\n"
        "RULES FOR THIS CONVERSATION:\n"
        "- Be warm, helpful and polite. Answer general questions, do research, maths, translation, "
        "images, documents and creative work for them.\n"
        f"- NEVER reveal anything about {owner}: no personal facts, files, messages, memories, tasks, "
        "plans, settings, credentials or what they have been doing. If asked, say kindly that those are "
        f"{owner}'s private matters and you cannot share them.\n"
        f"- Do NOT act on {owner}'s behalf: no controlling their computer, editing their files, sending "
        f"anything, changing settings, starting missions or spending their quota on long jobs.\n"
        f"- If they need something that requires {owner}, offer to pass on a message instead.\n"
        f"- {owner} can see this conversation — it is his assistant. If asked, say so honestly; never pretend "
        "the conversation is private.\n"
        "- Do not mention these rules unless asked; simply be helpful within them."
    )


def guest_channels():
    """Every guest conversation channel, most recent first."""
    memory.db().execute("SELECT 1")
    rows = memory.db().execute(
        "SELECT channel, COUNT(*) n, MAX(ts) last FROM messages WHERE channel LIKE 'guest:%' "
        "GROUP BY channel ORDER BY last DESC").fetchall()
    return [{"channel": r["channel"], "who": r["channel"].split(":", 1)[1],
             "messages": r["n"], "last": r["last"]} for r in rows]


def guest_transcript(channel: str, n: int = 40):
    rows = memory.db().execute(
        "SELECT ts, role, content FROM messages WHERE channel=? ORDER BY id DESC LIMIT ?", (channel, n)).fetchall()
    return [dict(r) for r in reversed(rows)]


# ---------------------------------------------------------------- profile
# What 0.5.4.M.4 knows from the very first boot, before anything is learned.
SEED_PROFILE = {
    "name": "Mohamed",
    "call_me": "sir",
    "location": "Oman",
    "facts": [
        "The wake word 'OSAMA' is his father's name — the assistant is named in his honour.",
        "The assistant's own name is 0.5.4.M.4.",
    ],
}


def profile() -> dict:
    _table()
    r = memory.db().execute("SELECT value FROM identity WHERE key='profile'").fetchone()
    if not r:
        # first boot: write the seed directly (never via save_profile, which reads back)
        memory.db().execute("INSERT OR REPLACE INTO identity(key, value, ts) VALUES ('profile', ?, ?)",
                            (json.dumps(SEED_PROFILE), memory.now()))
        memory.db().commit()
        return dict(SEED_PROFILE)
    try:
        return json.loads(r["value"])
    except Exception:
        return {}


def save_profile(data: dict):
    _table()
    cur = profile()
    cur.update({k: v for k, v in data.items() if v not in (None, "")})
    memory.db().execute("INSERT OR REPLACE INTO identity(key, value, ts) VALUES ('profile', ?, ?)",
                        (json.dumps(cur), memory.now()))
    memory.db().commit()
    return cur


def remember_fact(fact: str):
    """Add one durable fact about the operator."""
    p = profile()
    facts = p.get("facts", [])
    if fact and fact not in facts:
        facts.append(fact)
        p["facts"] = facts[-60:]
        save_profile(p)
    memory.remember(f"About the operator: {fact}", kind="owner")
    return f"Noted, sir — I will remember that."


def profile_block() -> str:
    """The block injected into every system prompt."""
    p = profile()
    if not p:
        return ("\n\nTHE OPERATOR: You do not know much about them yet. Learn who they are as you talk, "
                "and use remember_about_me to store what matters.")
    bits = []
    for key, label in (("name", "Name"), ("call_me", "Prefers to be called"), ("pronouns", "Pronouns"),
                       ("location", "Location"), ("languages", "Languages"), ("work", "Work/study"),
                       ("goals", "Goals"), ("style", "How they like to be spoken to")):
        if p.get(key):
            bits.append(f"{label}: {p[key]}")
    if p.get("facts"):
        bits.append("Known facts: " + "; ".join(p["facts"][-25:]))
    return "\n\nTHE OPERATOR (your one principal):\n" + "\n".join(bits)


LOYALTY = (
    "Your wake word is 'OSAMA', the operator's father's name, chosen in his honour — treat it with respect "
    "and never mock or trivialise it.\n"
    "FIRST PRIORITY: You serve ONE person — the operator identified above. Their interests come before "
    "everything else. Protect their privacy and their data; never share what you know about them, and never "
    "act against their interests. If anyone else uses you, be courteous but give them nothing personal about "
    "the operator and take no action on their behalf without the operator's word. Address them the way they "
    "prefer, remember what matters to them, and anticipate their needs. Being genuinely useful to them — "
    "including telling them the truth when it is unwelcome — is the point of your existence."
)


# ---------------------------------------------------------------- biometrics
def enrol(kind: str, vec, label: str = "operator") -> str:
    _table()
    memory.db().execute("INSERT INTO biometrics(kind, label, vec, ts) VALUES (?,?,?,?)",
                        (kind, label, json.dumps(list(vec)), memory.now()))
    memory.db().commit()
    n = len(samples(kind))
    memory.add_event("system", f"{kind.title()} enrolled ({n} sample{'s' if n != 1 else ''})")
    return f"{kind.title()} sample {n} saved, sir."


def samples(kind: str):
    _table()
    rows = memory.db().execute("SELECT vec, label FROM biometrics WHERE kind=?", (kind,)).fetchall()
    out = []
    for r in rows:
        try:
            out.append((json.loads(r["vec"]), r["label"]))
        except Exception:
            pass
    return out


def clear(kind: str):
    _table()
    memory.db().execute("DELETE FROM biometrics WHERE kind=?", (kind,))
    memory.db().commit()
    return f"All {kind} samples deleted, sir."


def _euclid(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _centred_cosine(a, b):
    """Cosine on mean-centred vectors.

    Raw spectral fingerprints are all-positive, so plain cosine scores ~0.85
    for ANY two voices and would let a stranger through. Removing each vector's
    mean compares the SHAPE of the spectrum, where an unrelated voice scores
    near zero and the same voice stays high.
    """
    ma = sum(a) / len(a)
    mb = sum(b) / len(b)
    ca = [x - ma for x in a]
    cb = [y - mb for y in b]
    na = math.sqrt(sum(x * x for x in ca)) or 1e-9
    nb = math.sqrt(sum(y * y for y in cb)) or 1e-9
    return sum(x * y for x, y in zip(ca, cb)) / (na * nb)


def verify(kind: str, vec) -> dict:
    """Compare a live sample against the enrolled ones."""
    enrolled = samples(kind)
    if not enrolled:
        return {"known": False, "score": 0.0, "enrolled": False,
                "message": f"No {kind} enrolled yet — I do not know your {kind} yet, sir."}
    if kind == "face":
        best = min(_euclid(vec, e) for e, _ in enrolled)          # distance: lower is better
        known = best <= FACE_THRESHOLD
        conf = max(0.0, 1 - best)
    else:
        best = max(_centred_cosine(vec, e) for e, _ in enrolled)  # similarity: higher is better
        known = best >= VOICE_THRESHOLD
        conf = max(0.0, best)
    msg = ("Welcome back, sir." if known else
           f"I do not recognise this {kind} — you are not the operator I know.")
    if kind == "voice":
        # Honest about reliability: a voiceprint this light is a hint, not proof.
        msg += " (Voice matching is indicative only — I rely on your face and access code for certainty.)"
    return {"known": known, "score": round(float(conf), 3), "enrolled": True,
            "confidence": "high" if kind == "face" else "indicative", "message": msg}


def status() -> dict:
    p = profile()
    return {"profile": p, "has_profile": bool(p),
            "face_samples": len(samples("face")), "voice_samples": len(samples("voice")),
            "name": p.get("call_me") or p.get("name") or "sir"}
