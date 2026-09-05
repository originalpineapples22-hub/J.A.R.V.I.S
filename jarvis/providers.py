# -*- coding: utf-8 -*-
"""Free brain pool.

Several companies give away serious models. This registry lets 0.5.4.M.4 use
them all: it tries the best available first and automatically fails over when a
provider is rate-limited or down, so the free tiers add up to a brain that is
effectively always on — no payment, ever.

Every provider here is OpenAI-compatible (/chat/completions).
"""
import time
from .config import load_settings

# id, name, base_url, key_setting, default model, tier, note
PROVIDERS = [
    ("github",   "GitHub Models",  "https://models.github.ai/inference",
     "github_models_key", "openai/gpt-4.1", "frontier",
     "FREE with any GitHub account — frontier-class models. Create a token at github.com/settings/tokens (no scopes needed)."),
    ("gemini",   "Google Gemini",  "https://generativelanguage.googleapis.com/v1beta/openai",
     "gemini_key", "gemini-3.6-flash", "frontier",   # a starting guess; retired names self-heal
     "FREE at aistudio.google.com/apikey — very generous daily limits."),
    ("cerebras", "Cerebras",       "https://api.cerebras.ai/v1",
     "cerebras_key", "llama-3.3-70b", "strong",
     "FREE at cloud.cerebras.ai — the fastest inference available."),
    ("groq",     "Groq",           "https://api.groq.com/openai/v1",
     "groq_api_key", "", "strong",
     "FREE at console.groq.com — fast, reliable."),
    ("openrouter", "OpenRouter",   "https://openrouter.ai/api/v1",
     "openrouter_key", "", "strong",                 # empty = whatever is free today
     "FREE at openrouter.ai — many models ending in :free."),
    ("mistral",  "Mistral",        "https://api.mistral.ai/v1",
     "mistral_key", "mistral-large-latest", "strong",
     "FREE tier at console.mistral.ai."),
    ("openai",   "OpenAI-compatible", "", "openai_api_key", "", "custom",
     "Any other OpenAI-compatible endpoint."),
    ("ollama",   "Your PC (Ollama)", "", "", "", "local",
     "UNLIMITED — runs on your own machine. Used automatically when the cloud tiers are exhausted, if your PC is on."),
]

BY_ID = {p[0]: p for p in PROVIDERS}
# provider id -> {"until": timestamp} while cooling off after a rate limit
_cooldown = {}


def configured(s=None):
    """Providers that actually have a credential, best tier first."""
    s = s or load_settings()
    out = []
    for pid, name, base, key_setting, model, tier, note in PROVIDERS:
        if pid == "ollama":
            if s.get("provider") == "ollama" or s.get("use_ollama"):
                out.append(pid)
            continue    # local is ranked last in order(), so it is the unlimited fallback
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
