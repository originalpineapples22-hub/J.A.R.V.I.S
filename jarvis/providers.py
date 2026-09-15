# -*- coding: utf-8 -*-
"""One brain, plus a backup — deliberately not a pool.

This used to try six different companies' APIs in turn. The operator asked for
the opposite: as few outside AIs as possible, not as many as could be
collected. What is left:

  1. Your own machine (Ollama) — genuinely yours, free, offline, permanent.
  2. Google Gemini — free, and the one cloud brain kept as backup for when
     your machine is off, since "no PC needed" was asked for too and a single
     local model can't deliver that on its own.

Nothing else is contacted. Add jarvis/tools/*.py custom endpoints yourself via
the "openai" slot below if you ever want a third, self-hosted option — nothing
here reaches out to it unless you fill in openai_api_key.
"""
import time
from .config import load_settings

# id, name, base_url, key_setting, default model, tier, note
PROVIDERS = [
    ("gemini",   "Google Gemini",  "https://generativelanguage.googleapis.com/v1beta/openai",
     "gemini_key", "gemini-3.6-flash", "frontier",   # a starting guess; retired names self-heal
     "FREE at aistudio.google.com/apikey — very generous daily limits. Kept as the one cloud "
     "backup, for when your own machine is off."),
    ("openai",   "OpenAI-compatible", "", "openai_api_key", "", "custom",
     "Off unless you fill this in yourself — any OpenAI-compatible endpoint you choose to point it at."),
    ("ollama",   "Your PC (Ollama)", "", "", "", "local",
     "YOURS — runs on your own machine. No key, no quota, works offline, and nobody "
     "can retire it. Used first when available; install it with deploy/local_brain.ps1."),
]

BY_ID = {p[0]: p for p in PROVIDERS}
# provider id -> {"until": timestamp} while cooling off after a rate limit
_cooldown = {}


_local = {"ts": 0.0, "url": "", "ok": False, "models": []}


def ollama_ready(s=None, force=False):
    """Is a local brain actually answering? Cached for a minute."""
    import httpx
    s = s or load_settings()
    url = (s.get("ollama_url") or "http://localhost:11434").rstrip("/")
    if not force and _local["url"] == url and time.time() - _local["ts"] < 60:
        return _local["ok"]
    ok, models = False, []
    try:
        r = httpx.get(f"{url}/api/tags", timeout=2.5)
        if r.status_code == 200:
            models = [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
            ok = bool(models)
    except Exception:
        ok = False
    _local.update(ts=time.time(), url=url, ok=ok, models=models)
    return ok


def local_models(s=None):
    ollama_ready(s)
    return list(_local["models"])


def configured(s=None):
    """Providers that actually have a credential, best tier first."""
    s = s or load_settings()
    out = []
    for pid, name, base, key_setting, model, tier, note in PROVIDERS:
        if pid == "ollama":
            # Only counts as configured when it is actually answering: an
            # unreachable local brain must not displace the cloud pool.
            if (s.get("provider") == "ollama" or s.get("use_ollama")) and ollama_ready(s):
                out.append(pid)
            continue
        if key_setting and (s.get(key_setting) or "").strip():
            out.append(pid)
    return out


def cool_off(pid: str, seconds: int = 900):
    """Mark a provider as rate-limited; it is skipped until it recovers."""
    _cooldown[pid] = time.time() + seconds


def is_cool(pid: str) -> bool:
    return _cooldown.get(pid, 0) > time.time()


def clear_cooldown(pid: str):
    _cooldown.pop(pid, None)


def cooldowns():
    now = time.time()
    return {p: int(t - now) for p, t in _cooldown.items() if t > now}


def resolve(pid: str, s=None):
    """(base_url, api_key, model) for a provider, honouring per-provider overrides."""
    s = s or load_settings()
    pid_, name, base, key_setting, model, tier, note = BY_ID[pid]
    if pid == "ollama":
        return s.get("ollama_url", "http://localhost:11434").rstrip("/"), "", s.get("ollama_model", "qwen2.5-coder:14b")
    if pid == "openai":
        return s.get("openai_base_url", "https://api.openai.com/v1").rstrip("/"), s.get("openai_api_key", ""), s.get("openai_model", "gpt-4o-mini")
    override = (s.get(f"{pid}_model") or "").strip()
    key = (s.get(key_setting) or "").strip()
    return base, key, (override or model)


def order(s=None):
    """The order to try providers: the operator's preference first, then the
    rest by tier, skipping any that are cooling off."""
    s = s or load_settings()
    have = configured(s)
    pref = s.get("provider")
    ranked = sorted(have, key=lambda p: (BY_ID[p][5] != "frontier", BY_ID[p][5] != "strong", p))
    if pref in have:
        ranked = [pref] + [p for p in ranked if p != pref]
    # A brain on the operator's own machine cannot be retired, rate-limited or
    # switched off by anyone else, so when one is available it leads and the
    # borrowed ones become backup.
    if s.get("prefer_local") and "ollama" in have:
        ranked = ["ollama"] + [p for p in ranked if p != "ollama"]
    live = [p for p in ranked if not is_cool(p)]
    return live or ranked        # if everything is cooling off, try anyway


def best_tier(s=None) -> str:
    s = s or load_settings()
    tiers = [BY_ID[p][5] for p in configured(s)]
    for t in ("frontier", "strong", "local", "custom"):
        if t in tiers:
            return t
    return "none"


def status(s=None):
    s = s or load_settings()
    have = configured(s)
    cd = cooldowns()
    return [{"id": p, "name": BY_ID[p][1], "tier": BY_ID[p][5], "note": BY_ID[p][6],
             "connected": p in have, "model": resolve(p, s)[2] if p in have else "",
             "cooldown": cd.get(p, 0)} for p, *_ in PROVIDERS]
