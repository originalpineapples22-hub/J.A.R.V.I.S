# -*- coding: utf-8 -*-
"""Provider-agnostic LLM access (Groq / OpenAI-compatible / Ollama), async streaming,
live model discovery, reasoning-block stripping."""
import re
import json
import time
import httpx
from .config import load_settings

GROQ_BASE = "https://api.groq.com/openai/v1"
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
    """Return (provider, base_url, api_key, model)."""
    s = settings or load_settings()
    p = s.get("provider", "groq")
    if p == "groq":
        models = await groq_models(s.get("groq_api_key"))
        want = s.get("vision_model") if vision else s.get("groq_model")
        model = want if want and want in models else pick_model(models, vision)
        return "groq", GROQ_BASE, s.get("groq_api_key", ""), model
    if p == "openai":
        return "openai", s.get("openai_base_url"), s.get("openai_api_key", ""), (s.get("vision_model") or s.get("openai_model"))
    return "ollama", s.get("ollama_url").rstrip("/"), "", (s.get("vision_model") or "llava") if vision else s.get("ollama_model")


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
    provider, base, key, model = await resolve(settings)
    if provider in ("groq", "openai"):
        if not key:
            raise RuntimeError(f"No API key configured for {provider}. Open Settings and add it.")
        if not model:
            raise RuntimeError("No usable model found for this provider/key.")
        payload = {"model": model, "messages": messages, "temperature": temperature, "stream": True}
        async with httpx.AsyncClient(timeout=timeout) as c:
            async with c.stream("POST", f"{base}/chat/completions", json=payload,
                                headers={"Authorization": f"Bearer {key}"}) as r:
                if r.status_code == 404 and provider == "groq":
                    _model_cache["ts"] = 0.0
                    raise RuntimeError("Model not found on Groq; retry (model list refreshed).")
                r.raise_for_status()
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
    else:
        payload = {"model": model, "messages": messages, "stream": True, "options": {"temperature": temperature}}
        async with httpx.AsyncClient(timeout=timeout) as c:
            async with c.stream("POST", f"{base}/api/chat", json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if line:
                        tok = json.loads(line).get("message", {}).get("content", "")
                        if tok:
                            yield tok


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
        if provider in ("groq", "openai"):
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
    out = {"groq": {"connected": bool(s.get("groq_api_key")), "model": None},
           "openai": {"connected": bool(s.get("openai_api_key")), "model": s.get("openai_model")},
           "ollama": {"connected": False, "model": s.get("ollama_model")}}
    if s.get("groq_api_key"):
        models = await groq_models(s["groq_api_key"])
        out["groq"]["model"] = s.get("groq_model") or pick_model(models)
        out["groq"]["connected"] = bool(models)
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            r = await c.get(f"{s['ollama_url'].rstrip('/')}/api/tags")
            out["ollama"]["connected"] = r.status_code == 200
    except Exception:
        pass
    out["active"] = s.get("provider")
    return out
