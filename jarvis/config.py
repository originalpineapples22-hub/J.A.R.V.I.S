# -*- coding: utf-8 -*-
"""Settings: environment variables first, then data/settings.json (editable from the UI)."""
import os
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("JARVIS_DATA", ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
FILES_DIR = DATA_DIR / "files"
FILES_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
DB_FILE = DATA_DIR / "jarvis.db"

DEFAULTS = {
    "assistant_name": "0.5.4.M.4",           # the AI's identity — change it and everything follows
    "assistant_style": "calm, articulate, British, dry wit",
    "operator_name": "sir",
    "provider": "groq",                 # groq | openai | ollama
    "groq_api_key": "",
    "groq_model": "",                   # empty = auto-pick best live model
    "openai_base_url": "https://api.openai.com/v1",
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5-coder:14b",
    "vision_model": "",                 # empty = auto
    "timezone": "Asia/Muscat",
    "briefing_hour": 8,                 # daily proactive briefing (local hour), -1 to disable
    "voice_name": "en-GB",
    "tts_voice": "en-GB-RyanNeural",   # edge-tts voice used by Discord and optional web speech
    "wake_word": "osama",
    "sleep_phrase": "all done sleep",
    "max_tool_steps": 4,
    # premium / optional services (all degrade gracefully when blank)
    "elevenlabs_key": "",
    "elevenlabs_voice": "onwK4e9ZLuTAKqWW03F9",
    "elevenlabs_model": "eleven_turbo_v2_5",
    "tavily_key": "",
    "wolfram_appid": "",
    "homeassistant_url": "",
    "homeassistant_token": "",
    "webhooks": "{}",
    "embed_model": "text-embedding-3-small",
    "semantic_memory": True,
    # --- free brain pool (add any, it uses the best available and fails over)
    "github_models_key": "",
    "gemini_key": "",
    "cerebras_key": "",
    "openrouter_key": "",
    "mistral_key": "",
    "github_model": "", "gemini_model": "", "cerebras_model": "",
    "openrouter_model": "", "mistral_model": "",
}


def load_settings() -> dict:
    s = dict(DEFAULTS)
    try:
        if SETTINGS_FILE.exists():
            s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    # environment overrides (used on the server)
    env_map = {
        "GROQ_API_KEY": "groq_api_key", "OPENAI_API_KEY": "openai_api_key",
        "JARVIS_PROVIDER": "provider", "OLLAMA_URL": "ollama_url", "JARVIS_TZ": "timezone",
    }
    for env, key in env_map.items():
        if os.environ.get(env):
            s[key] = os.environ[env]
    return s


def save_settings(new: dict):
    cur = {}
    try:
        if SETTINGS_FILE.exists():
            cur = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        cur = {}
    for k, v in new.items():
        if k in DEFAULTS:
            cur[k] = v.strip() if isinstance(v, str) else v
    SETTINGS_FILE.write_text(json.dumps(cur, indent=2), encoding="utf-8")


def operator_token() -> str:
    """Single-operator access token. Set JARVIS_TOKEN on the server; generated once otherwise."""
    tok = os.environ.get("JARVIS_TOKEN", "").strip()
    if tok:
        return tok
    f = DATA_DIR / "token.txt"
    if not f.exists():
        import secrets
        f.write_text(secrets.token_urlsafe(24), encoding="utf-8")
    return f.read_text(encoding="utf-8").strip()
