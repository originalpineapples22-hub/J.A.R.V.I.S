# -*- coding: utf-8 -*-
"""Speech services: accurate transcription (Whisper via Groq) and natural TTS
(edge-tts, free). Both degrade gracefully when unavailable."""
import re
import asyncio
import httpx
from .config import load_settings

GROQ_STT = "https://api.groq.com/openai/v1/audio/transcriptions"
STT_MODELS = ["whisper-large-v3-turbo", "whisper-large-v3"]

# Whisper's classic hallucinations on silence/noise — never pass these through.
_JUNK = {
    "", ".", "you", "thank you", "thanks", "thank you.", "bye", "bye.", "okay", "ok",
    "thanks for watching", "thanks for watching!", "thank you for watching",
    "please subscribe", "subscribe", "the", "uh", "um", "mm", "hmm", "yeah",
    "silence", "[silence]", "[music]", "(music)", "*", "so", "bye bye",
}


def _clean(text: str) -> str:
    t = (text or "").strip()
    low = re.sub(r"[^a-z ]", "", t.lower()).strip()
    if low in _JUNK or len(t) < 2:
        return ""
    # a single repeated token is also a hallucination artefact
    words = low.split()
    if len(words) > 3 and len(set(words)) == 1:
        return ""
    return t


async def transcribe(audio: bytes, filename: str = "audio.webm") -> str:
    s = load_settings()
    key = (s.get("groq_api_key") or "").strip()
    if not key or len(audio) < 2000:      # too short to contain speech
        return ""
    name = s.get("assistant_name", "0.5.4.M.4")
    prompt = f"Osama. {name}. Commands to a personal AI assistant."
    async with httpx.AsyncClient(timeout=60) as c:
        for model in STT_MODELS:
            try:
                r = await c.post(GROQ_STT, headers={"Authorization": f"Bearer {key}"},
                                 files={"file": (filename, audio, "audio/webm")},
                                 data={"model": model, "language": "en", "temperature": "0",
                                       "prompt": prompt, "response_format": "json"})
                if r.status_code == 200:
                    return _clean(r.json().get("text", ""))
            except Exception:
                continue
    return ""


async def synthesize(text: str, voice: str = "") -> bytes:
    """Natural speech via edge-tts (no key). Returns mp3 bytes, or b'' if unavailable."""
    text = (text or "").strip()
    if not text:
        return b""
    try:
        import edge_tts
    except Exception:
        return b""
    s = load_settings()
    v = voice or s.get("tts_voice") or "en-GB-RyanNeural"
    clean = re.sub(r"```.*?```", " code omitted ", text, flags=re.DOTALL)
    clean = re.sub(r"[*_#`>\[\]|]", "", clean)[:2000]
    try:
        com = edge_tts.Communicate(clean, v)
        buf = bytearray()
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        return bytes(buf)
    except Exception:
        return b""
