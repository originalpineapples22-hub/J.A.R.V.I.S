# -*- coding: utf-8 -*-
"""Provider-agnostic LLM access (Groq / OpenAI-compatible / Ollama), async streaming,
live model discovery, reasoning-block stripping."""
import re
import json
import time
import httpx
from .config import load_settings
from . import providers as pv
from . import budget

GROQ_BASE = "https://api.groq.com/openai/v1"
_CALL_KIND = {"kind": "operator"}


def set_call_kind(kind: str):
    """Tag subsequent calls as 'operator' or 'background' for budgeting."""
    _CALL_KIND["kind"] = kind


_model_cache = {"key": None, "ts": 0.0, "models": []}
_EXCLUDE = ("whisper", "tts", "guard", "embed", "moderation", "safety", "compound", "orpheus")
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    text = _THINK_RE.sub("", text)
    i = text.lower().find("<think>")
    if i >= 0:
        text = text[:i]
    for n in range(6, 0, -1):
        if text.lower().endswith("<think>"[:n]):
            return text[:-n]
    return text


async def groq_models(key: str):
    key = (key or "").strip()
    if not key:
        return []
    if _model_cache["key"] == key and time.time() - _model_cache["ts"] < 300:
        return _model_cache["models"]
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{GROQ_BASE}/models", headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
            ids = [m.get("id", "") for m in r.json().get("data", []) if m.get("active", True)]
            models = sorted(i for i in ids if i and not any(x in i.lower() for x in _EXCLUDE))
    except Exception:
        models = []
    _model_cache.update(key=key, ts=time.time(), models=models)
    return models


def _short_error(e) -> str:
    """One readable line per provider, so a failure names its own cause.

    Reporting only the last provider's error hid why the earlier ones failed —
    an expired key and a retired model look identical from the outside.
    """
    msg = str(e).strip().replace("\n", " ")
    m = re.search(r'"message"\s*:\s*"([^"]{3,200})"', msg)
    if m:
        detail = m.group(1)
    else:
        detail = msg[:200]
    code = re.search(r"HTTP (\d{3})", msg)
    if code:
        hint = {"401": "key rejected — check it was pasted whole",
                "403": "key lacks access to this model",
                "404": "model no longer offered",
                "429": "free allowance used up for now"}.get(code.group(1), "")
        return f"HTTP {code.group(1)} {hint or ''} — {detail}".strip()
    return detail or "no response"


_or_cache = {"key": "", "ts": 0.0, "models": []}


async def openrouter_free_models(key: str):
    """The models OpenRouter is giving away *today*.

    Its free line-up changes: a slug that was free last month starts answering
    404 with "use the paid version instead". Asking the catalogue for models
    priced at zero keeps the free tier working without anyone editing a list.
    """
    key = (key or "").strip()
    if not key:
        return []
    if _or_cache["key"] == key and time.time() - _or_cache["ts"] < 900:
        return _or_cache["models"]
    models = []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://openrouter.ai/api/v1/models",
                            headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
            for m in r.json().get("data", []):
                pr = m.get("pricing") or {}
                try:
                    free = float(pr.get("prompt", 1) or 0) == 0 and float(pr.get("completion", 1) or 0) == 0
                except (TypeError, ValueError):
                    free = False
                mid = m.get("id", "")
                if free and mid and not any(x in mid.lower() for x in _EXCLUDE):
                    models.append(mid)
    except Exception:
        models = []
    _or_cache.update(key=key, ts=time.time(), models=models)
    return models


def pick_model(models, vision=False):
    if not models:
        return None
    low = [(m, m.lower()) for m in models]
    if vision:
        for m, l in low:
            if any(k in l for k in ("vision", "scout", "maverick")):
                return m
        return None
    thinking = ("qwen3", "deepseek", "r1", "think")
    ranked = [x for x in low if not any(t in x[1] for t in thinking)] + [x for x in low if any(t in x[1] for t in thinking)]
    for pref in ("llama-3.3-70b", "llama-4-maverick", "llama-4", "70b", "gpt-oss-120b", "llama-3.1-8b", "llama", "gpt-oss", "kimi", "mixtral", "gemma"):
        for m, l in ranked:
            if pref in l:
                return m
    return ranked[0][0]


async def resolve(settings=None, vision=False):
    """Pick the best available provider right now. Returns (pid, base, key, model)."""
    s = settings or load_settings()
    for pid in pv.order(s):
        base, key, model = pv.resolve(pid, s)
        if pid == "groq" and not model:
            models = await groq_models(key)
            want = s.get("vision_model") if vision else s.get("groq_model")
            model = want if want and want in models else pick_model(models, vision)
        if vision and pid in ("groq",):
            models = await groq_models(key)
            model = pick_model(models, vision=True) or model
        if model:
            return pid, base, key, model
    return "none", "", "", ""


async def stream(messages, temperature=0.3, settings=None, timeout=300):
    """Async generator of visible reply tokens (thinking removed)."""
    raw, shown = "", ""
    async for tok in _stream_raw(messages, temperature, settings, timeout):
        raw += tok
        vis = strip_thinking(raw)
        if vis.startswith(shown):
            delta = vis[len(shown):]
        else:
            delta, shown = vis, ""
        if delta:
            shown += delta
            yield delta
    final = strip_thinking(raw)
    if final.startswith(shown) and len(final) > len(shown):
        yield final[len(shown):]


async def _stream_raw(messages, temperature, settings, timeout):
    """Try each configured provider in turn; a rate-limited or failing provider
    is put on cooldown and the next one takes over, so the free tiers add up."""
    s = settings or load_settings()
    tried, errors = [], []
    for pid in pv.order(s):
        base, key, model = pv.resolve(pid, s)
        if pid == "groq" and not model:
            model = pick_model(await groq_models(key)) or ""
        if pid == "openrouter":
            free = await openrouter_free_models(key)
            # Only keep the configured model if OpenRouter still gives it away.
            if free and model not in free:
                model = pick_model(free) or model
        if not model or (pid not in ("ollama",) and not key):
            continue
        tried.append(pid)
        try:
            got = False
            budget.record(_CALL_KIND.get("kind", "operator"))
            async for tok in _stream_one(pid, base, key, model, messages, temperature, timeout):
                got = True
                yield tok
            if got:
                pv.clear_cooldown(pid)
                return
        except Exception as e:
            errors.append(f"{pid}: {_short_error(e)}")
            msg = str(e)
            if "429" in msg or "rate" in msg.lower() or "quota" in msg.lower():
                pv.cool_off(pid, 900)      # rate-limited: rest for 15 minutes
            else:
                pv.cool_off(pid, 120)
            continue
    if not tried:
        raise RuntimeError(
            "No brain available — no provider is configured. Add a free key in Settings: "
            "GitHub Models (github.com/settings/tokens), Gemini (aistudio.google.com/apikey), "
            "Cerebras (cloud.cerebras.ai) or Groq (console.groq.com).")
    raise RuntimeError(
        "No brain available. Every provider refused:\n  " + "\n  ".join(errors) +
        "\nFix whichever is closest, or add another free key in Settings.")


async def _stream_one(pid, base, key, model, messages, temperature, timeout):
    if pid == "ollama":
        payload = {"model": model, "messages": messages, "stream": True, "options": {"temperature": temperature}}
        async with httpx.AsyncClient(timeout=timeout) as c:
            async with c.stream("POST", f"{base}/api/chat", json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if line:
                        tok = json.loads(line).get("message", {}).get("content", "")
                        if tok:
                            yield tok
        return
    payload = {"model": model, "messages": messages, "temperature": temperature, "stream": True}
    headers = {"Authorization": f"Bearer {key}"}
    if pid == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/originalpineapples22-hub"
        headers["X-Title"] = "0.5.4.M.4"
    async with httpx.AsyncClient(timeout=timeout) as c:
        async with c.stream("POST", f"{base}/chat/completions", json=payload, headers=headers) as r:
            if r.status_code >= 400:
                body = (await r.aread())[:200].decode("utf-8", "ignore")
                raise RuntimeError(f"HTTP {r.status_code} {body}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content") or ""
                except Exception:
                    delta = ""
                if delta:
                    yield delta


async def complete(messages, temperature=0.3, settings=None, timeout=300) -> str:
    out = []
    async for t in stream(messages, temperature, settings, timeout):
        out.append(t)
    return "".join(out).strip()


async def describe_image(b64_png: str, question: str, settings=None) -> str:
    provider, base, key, model = await resolve(settings, vision=True)
    if not model:
        return "No vision-capable model is available on the current provider."
    async with httpx.AsyncClient(timeout=120) as c:
        if provider != "ollama":
            payload = {"model": model, "temperature": 0.2, "messages": [{"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_png}"}}]}]}
            r = await c.post(f"{base}/chat/completions", json=payload, headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        r = await c.post(f"{base}/api/chat", json={"model": model, "stream": False,
                                                    "messages": [{"role": "user", "content": question, "images": [b64_png]}]})
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()


async def provider_status(settings=None) -> dict:
    s = settings or load_settings()
    items = pv.status(s)
    active, base, key, model = await resolve(s)
    return {"pool": items, "active": active, "model": model,
            "tier": pv.best_tier(s), "cooldowns": pv.cooldowns()}
