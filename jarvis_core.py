# -*- coding: utf-8 -*-
"""
J.A.R.V.I.S. CORE — shared brain used by the HUD (jarvis.py), the local
voice bridge (jarvis_voice.py) and the cloud server (cloud/server.py).

Pure functions only: no Streamlit here, so every front-end can import it.
"""
import io
import os
import re
import json
import subprocess
import webbrowser
from pathlib import Path

import requests

# ---------------------------------------------------------------- optional deps
try:
    import pyttsx3
    HAS_TTS = True
except Exception:
    HAS_TTS = False

try:
    import screen_brightness_control as sbc
    HAS_BRIGHT = True
except Exception:
    HAS_BRIGHT = False

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    HAS_VOL = True
except Exception:
    HAS_VOL = False

try:
    import keyboard as kb
    HAS_KEYS = True
except Exception:
    HAS_KEYS = False

try:
    import mss as _mss
    from PIL import Image as _PILImage
    HAS_SCREEN = True
except Exception:
    HAS_SCREEN = False

MACROS_FILE = Path("jarvis_macros.json")
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"

PERSONA = (
    "You are J.A.R.V.I.S., a calm, articulate British AI with dry wit. "
    "You address the operator as 'sir'. Keep spoken replies concise (1-3 sentences) "
    "unless asked for detail. Offer subtle, respectful pushback on risky ideas."
)

# ---------------------------------------------------------------- brain settings
SETTINGS_FILE = Path("jarvis_settings.json")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_SETTINGS = {
    "provider": "local",                       # "local" (Ollama on this PC) or "cloud" (Groq free API)
    "ollama_url": DEFAULT_OLLAMA_URL,
    "ollama_model": "qwen2.5-coder:14b",
    "ollama_vision_model": "llava",
    "groq_api_key": "",
    "groq_model": "llama-3.3-70b-versatile",
    "groq_vision_model": "meta-llama/llama-4-scout-17b-16e-instruct",
}
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
]


def load_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    try:
        if SETTINGS_FILE.exists():
            data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return data


def save_settings(settings: dict):
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass


def brain_label(settings: dict) -> str:
    if settings.get("provider") == "cloud":
        return f"CLOUD · {settings.get('groq_model', '')}"
    return f"LOCAL · {settings.get('ollama_model', '')}"


def chat_stream(messages, settings: dict, temperature: float = 0.1, timeout: int = 300):
    """Yield reply tokens from whichever brain is configured."""
    if settings.get("provider") == "cloud":
        key = settings.get("groq_api_key", "").strip()
        if not key:
            raise requests.exceptions.RequestException("Cloud brain selected but no Groq API key is set (SYSTEMS tab).")
        payload = {"model": settings.get("groq_model"), "messages": messages,
                   "temperature": temperature, "stream": True}
        r = requests.post(GROQ_URL, json=payload, stream=True, timeout=timeout,
                          headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8") if isinstance(line, bytes) else line
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
        payload = {"model": settings.get("ollama_model"), "messages": messages,
                   "stream": True, "options": {"temperature": temperature}}
        r = requests.post(settings.get("ollama_url", DEFAULT_OLLAMA_URL), json=payload, stream=True, timeout=timeout)
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                chunk = json.loads(line.decode("utf-8"))
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token


def chat_once(messages, settings: dict, temperature: float = 0.1, timeout: int = 300) -> str:
    return "".join(chat_stream(messages, settings, temperature, timeout))


def brain_online(settings: dict) -> bool:
    if settings.get("provider") == "cloud":
        return bool(settings.get("groq_api_key", "").strip())
    try:
        base = settings.get("ollama_url", DEFAULT_OLLAMA_URL).split("/api/")[0]
        return requests.get(f"{base}/api/tags", timeout=2).ok
    except Exception:
        return False


# ---------------------------------------------------------------- LLM helpers
def ollama_chat(messages, chat_url=DEFAULT_OLLAMA_URL, model="qwen2.5-coder:14b",
                temperature=0.3, timeout=180) -> str:
    payload = {"model": model, "messages": messages, "stream": False,
               "options": {"temperature": temperature}}
    r = requests.post(chat_url, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json().get("message", {}).get("content", "").strip()


def clean_for_speech(text: str, limit: int = 400) -> str:
    clean = re.sub(r"```.*?```", " code block omitted ", text, flags=re.DOTALL)
    clean = re.sub(r"[*_#`>\[\]()|]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:limit]


# ---------------------------------------------------------------- PC speech (fallback)
def tts_speak(text: str, rate: int = 178):
    """Blocking local TTS. A FRESH engine per call avoids the Windows bug
    where a reused pyttsx3 engine goes silent after its first sentence."""
    if not HAS_TTS or not text:
        return False
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        try:
            for v in engine.getProperty("voices"):
                n = v.name.lower()
                if any(k in n for k in ("george", "daniel", "david", "ryan")):
                    engine.setProperty("voice", v.id)
                    break
        except Exception:
            pass
        engine.say(text)
        engine.runAndWait()
        try:
            engine.stop()
        except Exception:
            pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- PC control
APP_ALIASES = {
    "notepad": "notepad", "calculator": "calc", "paint": "mspaint",
    "file explorer": "explorer", "explorer": "explorer", "files": "explorer",
    "terminal": "cmd", "cmd": "cmd", "command prompt": "cmd",
    "settings": "ms-settings:", "task manager": "taskmgr",
    "chrome": "chrome", "firefox": "firefox", "edge": "msedge",
    "vs code": "code", "vscode": "code", "visual studio code": "code",
    "spotify": "spotify", "discord": "discord", "steam": "steam",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
}
SITE_ALIASES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "github": "https://github.com",
    "reddit": "https://www.reddit.com", "twitch": "https://www.twitch.tv",
    "netflix": "https://www.netflix.com", "chatgpt": "https://chat.openai.com",
}


def launch_target(target: str) -> str:
    t = target.lower().strip()
    if t in SITE_ALIASES:
        webbrowser.open(SITE_ALIASES[t])
        return f"Opening {t}, sir."
    if t.startswith("http") or ("." in t and " " not in t):
        url = t if t.startswith("http") else "https://" + t
        webbrowser.open(url)
        return f"Opening {url}."
    exe = APP_ALIASES.get(t, t)
    try:
        if os.name == "nt":
            subprocess.Popen(f'start "" "{exe}"', shell=True)
        else:
            subprocess.Popen([exe])
        return f"Launching {t}, sir."
    except Exception as e:
        return f"Unable to launch '{t}': {e}"


def set_system_volume(level: int) -> str:
    if not HAS_VOL:
        return "Volume control module not installed. Run: pip install pycaw comtypes"
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))
        vol.SetMasterVolumeLevelScalar(max(0, min(level, 100)) / 100.0, None)
        return f"Volume set to {level} percent."
    except Exception as e:
        return f"Volume control failed: {e}"


def set_brightness(level: int) -> str:
    if not HAS_BRIGHT:
        return "Brightness module not installed. Run: pip install screen-brightness-control"
    try:
        sbc.set_brightness(max(0, min(level, 100)))
        return f"Brightness set to {level} percent."
    except Exception as e:
        return f"Brightness control failed: {e}"


def media_key(action: str) -> str:
    if not HAS_KEYS:
        return "Media control module not installed. Run: pip install keyboard"
    keys = {"playpause": "play/pause media", "next": "next track",
            "previous": "previous track", "stop": "stop media"}
    try:
        kb.send(keys[action])
        return "Done, sir."
    except Exception as e:
        return f"Media control failed: {e}"


def load_macros() -> dict:
    try:
        with open(MACROS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def run_macro(name: str, macro: dict) -> str:
    results = []
    for app in macro.get("apps", []):
        results.append(launch_target(app))
    for url in macro.get("urls", []):
        webbrowser.open(url)
        results.append(f"Opening {url}.")
    return f"Executing protocol '{name}'. " + " ".join(results)


# ---------------------------------------------------------------- screen vision
def describe_screen(settings: dict = None) -> str:
    settings = settings or load_settings()
    if not HAS_SCREEN:
        return "Visual sensors offline, sir. Install them with: pip install mss pillow"
    try:
        import base64
        with _mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])
            img = _PILImage.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        img.thumbnail((1280, 1280))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        question = "Describe what is on this screen concisely, as J.A.R.V.I.S. reporting to sir."
        if settings.get("provider") == "cloud":
            payload = {
                "model": settings.get("groq_vision_model"),
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ]}],
                "temperature": 0.2,
            }
            r = requests.post(GROQ_URL, json=payload, timeout=120,
                              headers={"Authorization": f"Bearer {settings.get('groq_api_key', '')}"})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip() or "I cannot interpret the display, sir."
        payload = {
            "model": settings.get("ollama_vision_model", "llava"),
            "messages": [{"role": "user", "content": question, "images": [b64]}],
            "stream": False,
        }
        r = requests.post(settings.get("ollama_url", DEFAULT_OLLAMA_URL), json=payload, timeout=180)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip() or "I cannot interpret the display, sir."
    except Exception as e:
        return f"Visual analysis failed, sir. (Local mode needs: ollama pull llava) {e}"


SCREEN_PHRASES = ("look at my screen", "what am i doing", "what's on my screen",
                  "whats on my screen", "see my screen", "read my screen", "scan my screen")


def normalize_command(prompt: str) -> str:
    p = re.sub(r"^(hey\s+)?jarvis[,!\s]+", "", prompt.strip(), flags=re.IGNORECASE)
    return p.strip().lower().rstrip(".!?")


def parse_local_command(prompt: str, settings: dict = None):
    """Hands-free command engine. Returns a reply string for direct PC
    commands, or None to fall through to the AI."""
    p = normalize_command(prompt)

    if p in SCREEN_PHRASES:
        return describe_screen(settings)

    m = re.match(r"(?:open|launch|start)\s+(.+)$", p)
    if m:
        return launch_target(m.group(1))
    m = re.match(r"(?:set\s+)?volume(?:\s+to)?\s+(\d{1,3})", p)
    if m:
        return set_system_volume(int(m.group(1)))
    if p in ("mute", "mute volume", "silence"):
        return set_system_volume(0)
    m = re.match(r"(?:set\s+)?brightness(?:\s+to)?\s+(\d{1,3})", p)
    if m:
        return set_brightness(int(m.group(1)))
    if p in ("pause", "play", "pause music", "play music", "pause the music", "resume music", "resume"):
        return media_key("playpause")
    if p in ("next", "next song", "next track", "skip", "skip song"):
        return media_key("next")
    if p in ("previous song", "previous track", "go back a song", "last song"):
        return media_key("previous")

    for name, macro in load_macros().items():
        n = name.lower()
        if p in (n, f"run {n}", f"activate {n}", f"{n} protocol"):
            return run_macro(name, macro)
    return None
