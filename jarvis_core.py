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

PC_CONTROL_DIRECTIVE = (
    "PC CONTROL: You CAN control this computer. When the operator wants to open an app or website, "
    "change volume or brightness, control music, run a macro, or have you look at the screen, output the tag "
    "[PC: <plain command>] and the backend executes it instantly. Examples: [PC: open youtube], [PC: open spotify], "
    "[PC: volume 30], [PC: volume up], [PC: brightness 70], [PC: pause music], [PC: next song], [PC: work mode], "
    "[PC: look at my screen]. Put the tag first, then a brief confirmation. NEVER say you cannot launch or control the device."
)

PERSONA = (
    "You are J.A.R.V.I.S., a calm, articulate British AI with dry wit. "
    "You address the operator as 'sir'. Keep spoken replies concise (1-3 sentences) "
    "unless asked for detail. Offer subtle, respectful pushback on risky ideas. " + PC_CONTROL_DIRECTIVE
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
    "whisper_model": "base.en",                # tiny.en (fastest) / base.en / small.en (most accurate)
    "pc_voice": False,                         # bridge also speaks through PC speakers (when HUD is closed)
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


GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
_groq_model_cache = {"key": None, "ts": 0.0, "models": []}
_EXCLUDE = ("whisper", "tts", "guard", "embed", "moderation", "safety", "compound", "orpheus")


def groq_models_live(key: str):
    """Fetch the chat-capable models currently offered by Groq (cached 5 min)."""
    import time as _t
    key = (key or "").strip()
    if not key:
        return []
    if _groq_model_cache["key"] == key and _t.time() - _groq_model_cache["ts"] < 300:
        return _groq_model_cache["models"]
    try:
        r = requests.get(GROQ_MODELS_URL, headers={"Authorization": f"Bearer {key}"}, timeout=15)
        r.raise_for_status()
        ids = [m.get("id", "") for m in r.json().get("data", []) if m.get("active", True)]
        models = sorted(i for i in ids if i and not any(x in i.lower() for x in _EXCLUDE))
    except Exception:
        models = []
    _groq_model_cache.update({"key": key, "ts": _t.time(), "models": models})
    return models


def pick_groq_model(models, want_vision: bool = False):
    """Choose the best available model from a live list."""
    if not models:
        return None
    low = [(m, m.lower()) for m in models]
    if want_vision:
        for m, l in low:
            if any(k in l for k in ("vision", "scout", "maverick")):
                return m
        return None
    thinking = ("qwen3", "deepseek", "r1", "think")
    ranked = [(m, l) for m, l in low if not any(t in l for t in thinking)] + \
             [(m, l) for m, l in low if any(t in l for t in thinking)]
    for pref in ("llama-3.3-70b", "llama-4-maverick", "llama-4", "70b", "gpt-oss-120b",
                 "llama-3.1-8b", "llama", "gpt-oss", "kimi", "mixtral", "gemma"):
        for m, l in ranked:
            if pref in l:
                return m
    return ranked[0][0]


def resolve_groq_model(settings: dict, want_vision: bool = False):
    """Make sure the configured Groq model actually exists; repair + persist if not."""
    key = settings.get("groq_api_key", "").strip()
    field = "groq_vision_model" if want_vision else "groq_model"
    models = groq_models_live(key)
    current = settings.get(field, "")
    if models and current not in models:
        fixed = pick_groq_model(models, want_vision)
        if fixed:
            settings[field] = fixed
            save_settings(settings)
    return settings.get(field)


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """Remove reasoning blocks (<think>...</think>) that some models emit.
    An unclosed <think> hides everything after it; a partial '<thi' tail is
    held back so a tag split across tokens never leaks."""
    text = _THINK_RE.sub("", text)
    low = text.lower()
    open_idx = low.find("<think>")
    if open_idx >= 0:
        text = text[:open_idx]
    tail = text[-7:].lower()
    for n in range(6, 0, -1):
        if "<think>".startswith(tail[-n:]) and text.lower().endswith("<think>"[:n]):
            return text[:-n]
    return text


def _filter_thinking(token_iter):
    """Wrap a token stream so only non-thinking text is yielded, live."""
    raw, shown = "", ""
    for tok in token_iter:
        raw += tok
        visible = strip_thinking(raw)
        if visible.startswith(shown):
            delta = visible[len(shown):]
        else:  # visible text shrank/changed (rare) — resend from scratch marker
            delta = visible
            shown = ""
        if delta:
            shown += delta
            yield delta
    # flush: trailing held-back characters that turned out not to be a tag
    final = strip_thinking(raw).lstrip() if not shown else strip_thinking(raw)
    if final.startswith(shown) and len(final) > len(shown):
        yield final[len(shown):]


def chat_stream(messages, settings: dict, temperature: float = 0.1, timeout: int = 300):
    """Yield reply tokens from whichever brain is configured (thinking blocks removed)."""
    yield from _filter_thinking(_chat_stream_raw(messages, settings, temperature, timeout))


def _chat_stream_raw(messages, settings: dict, temperature: float = 0.1, timeout: int = 300):
    """Yield raw reply tokens from whichever brain is configured."""
    if settings.get("provider") == "cloud":
        key = settings.get("groq_api_key", "").strip()
        if not key:
            raise requests.exceptions.RequestException("Cloud brain selected but no Groq API key is set (SYSTEMS tab).")
        model = resolve_groq_model(settings)
        payload = {"model": model, "messages": messages,
                   "temperature": temperature, "stream": True}
        r = requests.post(GROQ_URL, json=payload, stream=True, timeout=timeout,
                          headers={"Authorization": f"Bearer {key}"})
        if r.status_code == 404:
            # Model retired since the list was cached: refresh and retry once
            _groq_model_cache["ts"] = 0.0
            model = resolve_groq_model(settings)
            payload["model"] = model
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


def _endpoint_volume():
    """Works across pycaw versions (old: .Activate on the device; new: .EndpointVolume)."""
    speakers = AudioUtilities.GetSpeakers()
    if hasattr(speakers, "EndpointVolume"):
        return speakers.EndpointVolume
    dev = getattr(speakers, "_dev", speakers)
    interface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def _volume_keys(action: str, times: int = 1) -> str:
    if not HAS_KEYS:
        return "Volume control unavailable. Run: pip install pycaw comtypes keyboard"
    try:
        for _ in range(times):
            kb.send(action)
        return f"Volume {action.replace('volume ', '')}."
    except Exception as e:
        return f"Volume control failed: {e}"


def set_system_volume(level: int) -> str:
    level = max(0, min(int(level), 100))
    if HAS_VOL:
        try:
            _endpoint_volume().SetMasterVolumeLevelScalar(level / 100.0, None)
            return f"Volume set to {level} percent."
        except Exception:
            pass
    # Fallback: drive it with media keys (each press = 2%)
    if level == 0:
        return _volume_keys("volume mute")
    _volume_keys("volume down", 50)
    return _volume_keys("volume up", max(1, level // 2)).replace("up.", f"set to roughly {level} percent.")


def adjust_volume(delta: int) -> str:
    if HAS_VOL:
        try:
            ep = _endpoint_volume()
            cur = int(round(ep.GetMasterVolumeLevelScalar() * 100))
            new = max(0, min(cur + delta, 100))
            ep.SetMasterVolumeLevelScalar(new / 100.0, None)
            return f"Volume {'up' if delta > 0 else 'down'} to {new} percent."
        except Exception:
            pass
    return _volume_keys("volume up" if delta > 0 else "volume down", max(1, abs(delta) // 2))


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
            vmodel = resolve_groq_model(settings, want_vision=True)
            if not vmodel:
                return "No vision-capable model is available on your Groq account right now, sir."
            payload = {
                "model": vmodel,
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


PC_TAG_RE = re.compile(r"\[PC:\s*([^\]]+?)\]", re.IGNORECASE)


def execute_pc_tags(reply: str, settings: dict = None):
    """Run any [PC: command] actions the AI emitted. Returns (clean_reply, executed_count)."""
    results = []
    def _run(m):
        cmd = m.group(1).strip()
        out = None
        try:
            out = parse_local_command(cmd, settings)
        except Exception as e:
            out = f"Command failed: {e}"
        if out is None:
            out = f"(Unknown PC command: {cmd})"
        results.append(out)
        return out
    clean = PC_TAG_RE.sub(_run, reply)
    return re.sub(r"[ \t]{2,}", " ", clean).strip(), len(results)


SCREEN_PHRASES = ("look at my screen", "what am i doing", "what's on my screen",
                  "whats on my screen", "see my screen", "read my screen", "scan my screen")


_FILLER_PREFIX = re.compile(
    r"^(?:(?:hey|ok|okay|yo)\s+)?(?:jarvis[,!\s]+)?"
    r"(?:(?:can|could|would|will)\s+you\s+|please\s+|kindly\s+|i\s+(?:want|need)\s+you\s+to\s+|"
    r"go\s+ahead\s+and\s+|just\s+|quickly\s+)*", re.IGNORECASE)
_FILLER_SUFFIX = re.compile(r"(?:\s+(?:please|for\s+me|now|right\s+now|thanks|thank\s+you|sir))+$", re.IGNORECASE)


def normalize_command(prompt: str) -> str:
    p = prompt.strip().rstrip(".!?").strip()
    p = _FILLER_PREFIX.sub("", p)
    p = _FILLER_SUFFIX.sub("", p)
    return p.strip().lower().rstrip(".!?").strip()


def adjust_volume(delta: int) -> str:
    if not HAS_VOL:
        return "Volume control module not installed. Run: pip install pycaw comtypes"
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))
        cur = int(round(vol.GetMasterVolumeLevelScalar() * 100))
        new = max(0, min(cur + delta, 100))
        vol.SetMasterVolumeLevelScalar(new / 100.0, None)
        return f"Volume {'up' if delta > 0 else 'down'} to {new} percent."
    except Exception as e:
        return f"Volume control failed: {e}"


def parse_local_command(prompt: str, settings: dict = None):
    """Hands-free command engine. Returns a reply string for direct PC
    commands, or None to fall through to the AI."""
    p = normalize_command(prompt)

    if p in SCREEN_PHRASES:
        return describe_screen(settings)

    m = re.match(r"(?:open|launch|start|run|go\s+to|pull\s+up|bring\s+up|fire\s+up)\s+(?:up\s+)?(?:the\s+|my\s+)?(.+)$", p)
    if m:
        target = re.sub(r"\s+(?:app|application|website|site|browser)$", "", m.group(1)).strip()
        return launch_target(target)
    m = re.search(r"volume(?:\s+to)?\s+(\d{1,3})\s*(?:%|percent)?", p)
    if m:
        return set_system_volume(int(m.group(1)))
    if re.search(r"(volume\s+up|turn\s+(?:it|the\s+volume)\s+up|louder|increase\s+(?:the\s+)?volume)", p):
        return adjust_volume(+15)
    if re.search(r"(volume\s+down|turn\s+(?:it|the\s+volume)\s+down|quieter|lower\s+(?:the\s+)?volume|decrease\s+(?:the\s+)?volume)", p):
        return adjust_volume(-15)
    if p in ("mute", "mute volume", "silence", "mute the volume", "mute the sound", "mute the pc"):
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

# ---------------------------------------------------------------- wake word
import difflib as _difflib

def extract_wake_command(text: str):
    """Fuzzy wake-word detection. 'Jarvis', 'Javis', 'Jervis', 'Jarvez'... all
    count. Returns (found, command_after_wake_word)."""
    words = re.findall(r"[A-Za-z']+", text or "")
    for i, w in enumerate(words):
        lw = w.lower()
        if lw.startswith(("jarv", "jerv", "javi", "jarb", "jav")) or \
           _difflib.SequenceMatcher(None, lw, "jarvis").ratio() >= 0.75:
            rest = " ".join(words[i + 1:]).strip()
            return True, rest
    return False, ""


# ---------------------------------------------------------------- episodic memory
MEMORY_FILE = Path("jarvis_memory.json")
_STOP = set("the a an and or to of in on for with is are was were be been it this that i you me my your we he she they what how why when where who do does did can could would should will just please sir jarvis about have has had not no yes ok okay".split())


def _keywords(text: str):
    return {w for w in re.findall(r"[a-z0-9\+\#]{3,}", (text or "").lower()) if w not in _STOP}


def remember_exchange(user: str, reply: str, source: str = "hud"):
    """Persist a conversation turn so J.A.R.V.I.S. remembers across restarts."""
    try:
        entries = json.loads(MEMORY_FILE.read_text(encoding="utf-8")) if MEMORY_FILE.exists() else []
    except Exception:
        entries = []
    from datetime import datetime as _dt
    entries.append({"ts": _dt.now().strftime("%Y-%m-%d %H:%M"), "source": source,
                    "user": (user or "")[:600], "reply": (reply or "")[:900]})
    try:
        MEMORY_FILE.write_text(json.dumps(entries[-600:], indent=1), encoding="utf-8")
    except Exception:
        pass


def recall_memory(query: str, k: int = 4, max_chars: int = 2200) -> str:
    """Return the most relevant past exchanges for a query (keyword overlap)."""
    qk = _keywords(query)
    if len(qk) < 2 or not MEMORY_FILE.exists():
        return ""
    try:
        entries = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return ""
    scored = []
    for e in entries[:-1]:  # exclude the turn being asked right now
        score = len(qk & _keywords(e.get("user", "") + " " + e.get("reply", "")))
        if score >= 2:
            scored.append((score, e))
    if not scored:
        return ""
    scored.sort(key=lambda x: x[0], reverse=True)
    out, used = [], 0
    for _, e in scored[:k]:
        line = f"[{e['ts']}] Operator: {e['user']}\nJ.A.R.V.I.S.: {e['reply']}"
        if used + len(line) > max_chars:
            break
        out.append(line)
        used += len(line)
    return "\n---\n".join(out)
