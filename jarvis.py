# -*- coding: utf-8 -*-
import streamlit as st
import os
import io
import ast
import shutil
import re
import textwrap
import time
import json
import difflib
import requests
import hashlib
import threading
import concurrent.futures
from datetime import datetime
from pathlib import Path
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

# --- SENSOR IMPORTS (With Fallbacks) ---
try:
    import psutil
    HAS_PSUTIL = True
    psutil.cpu_percent(interval=None)
except ImportError:
    HAS_PSUTIL = False

try:
    from duckduckgo_search import DDGS
    HAS_WEB = True
except ImportError:
    HAS_WEB = False

# --- SYSTEM DIRECTORIES & AUDIT SETUP ---
BACKUP_DIR = Path("jarvis_backups")
BACKUP_DIR.mkdir(exist_ok=True)
AUDIT_LOG_FILE = Path("jarvis_audit.json")

# --- SELF-LEARNING KNOWLEDGE BASE SETUP ---
KNOWLEDGE_DIR = Path("jarvis_knowledge")
KNOWLEDGE_DIR.mkdir(exist_ok=True)
SKILL_MATRIX_FILE = KNOWLEDGE_DIR / "_skill_matrix.json"

# Full mastery curriculum: one study session covers a technology from
# fundamentals through advanced, real-world usage. Completing it = MASTER.
DEFAULT_CURRICULUM = [
    "core syntax, variables and data types",
    "control flow, functions and error handling",
    "data structures and collections",
    "object oriented and idiomatic design patterns",
    "standard library and essential built-ins",
    "modules, packages and project structure",
    "concurrency, async and performance optimization",
    "testing, debugging and profiling",
    "ecosystem, tooling and package management",
    "advanced real-world usage, security and best practices",
]


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:60] if slug else "unnamed_topic"


def load_skill_matrix() -> dict:
    if SKILL_MATRIX_FILE.exists():
        try:
            with open(SKILL_MATRIX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_skill_matrix(matrix: dict):
    with open(SKILL_MATRIX_FILE, "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2)


def skill_level_name(lesson_count: int) -> str:
    # Interim label while lessons are being saved; a completed study
    # session promotes the topic straight to MASTER via set_topic_mastery.
    return "TRAINED"


def set_topic_mastery(topic: str, learned: int, total: int) -> str:
    """Record curriculum coverage after a study session. Completing the
    curriculum (allowing one dropped module) = MASTER, no grinding."""
    matrix = load_skill_matrix()
    slug = slugify(topic)
    info = matrix.get(slug, {"topic": topic, "lessons": learned})
    info["coverage"] = f"{learned}/{total}"
    info["level"] = "MASTER" if learned >= total - 1 else f"TRAINED ({learned}/{total} modules)"
    info["last_studied"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    matrix[slug] = info
    save_skill_matrix(matrix)
    return info["level"]


def save_knowledge(topic: str, lesson_title: str, content: str, source: str = "self_study") -> str:
    """Persist a learned lesson to disk and update the skill matrix."""
    topic = topic.strip()
    slug = slugify(topic)
    topic_file = KNOWLEDGE_DIR / f"{slug}.json"

    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lesson": lesson_title.strip() or "general notes",
        "source": source,
        "content": content.strip(),
    }

    lessons = []
    if topic_file.exists():
        try:
            with open(topic_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                lessons = data.get("lessons", [])
        except Exception:
            lessons = []

    lessons.append(entry)
    with open(topic_file, "w", encoding="utf-8") as f:
        json.dump({"topic": topic, "lessons": lessons}, f, indent=2)

    matrix = load_skill_matrix()
    matrix[slug] = {
        "topic": topic,
        "lessons": len(lessons),
        "level": skill_level_name(len(lessons)),
        "last_studied": entry["timestamp"],
    }
    save_skill_matrix(matrix)
    return f"Lesson '{entry['lesson']}' committed to long-term memory for '{topic}' ({len(lessons)} total lessons)."


def recall_knowledge(query: str, max_topics: int = 3, max_chars: int = 6000) -> str:
    """Keyword-match the query against the knowledge base and return relevant notes."""
    matrix = load_skill_matrix()
    if not matrix:
        return ""

    query_words = set(re.findall(r"[a-z0-9\+\#]+", query.lower()))
    if not query_words:
        return ""

    scored = []
    for slug, info in matrix.items():
        topic_words = set(re.findall(r"[a-z0-9\+\#]+", info.get("topic", "").lower()))
        score = len(query_words & topic_words)
        if score > 0:
            scored.append((score, slug, info))

    if not scored:
        return ""

    scored.sort(key=lambda x: x[0], reverse=True)
    recalled_parts = []
    budget = max_chars
    for _, slug, info in scored[:max_topics]:
        topic_file = KNOWLEDGE_DIR / f"{slug}.json"
        if not topic_file.exists():
            continue
        try:
            with open(topic_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        chunk_lines = [f"### Learned knowledge: {data.get('topic', slug)} [{info.get('level', '?')}]"]
        for lesson in data.get("lessons", []):
            chunk_lines.append(f"-- Lesson: {lesson.get('lesson', '')} ({lesson.get('timestamp', '')})")
            chunk_lines.append(lesson.get("content", ""))
        chunk = "\n".join(chunk_lines)
        if len(chunk) > budget:
            chunk = chunk[:budget] + "\n[...knowledge truncated...]"
        recalled_parts.append(chunk)
        budget -= len(chunk)
        if budget <= 0:
            break

    return "\n\n".join(recalled_parts)


def export_knowledge_markdown() -> str:
    """Compile the entire knowledge base into a single Markdown document."""
    matrix = load_skill_matrix()
    lines = ["# J.A.R.V.I.S. Knowledge Base Export", f"_Exported {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_", ""]
    for slug, info in matrix.items():
        topic_file = KNOWLEDGE_DIR / f"{slug}.json"
        if not topic_file.exists():
            continue
        try:
            with open(topic_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        lines.append(f"## {data.get('topic', slug)} — {info.get('level', '?')} ({info.get('lessons', 0)} lessons)")
        for lesson in data.get("lessons", []):
            lines.append(f"### {lesson.get('lesson', '')}")
            lines.append(f"_{lesson.get('timestamp', '')} · source: {lesson.get('source', '')}_")
            lines.append("")
            lines.append(lesson.get("content", ""))
            lines.append("")
    return "\n".join(lines)


def record_audit_entry(feature_name: str, status: str, details: str, diff: str = ""):
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "feature": feature_name,
        "status": status,
        "details": details,
        "diff_preview": diff[:500] if diff else ""
    }
    history = []
    if AUDIT_LOG_FILE.exists():
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
    history.insert(0, entry)
    with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(history[:50], f, indent=2)

# --- THREADED WEB SCRAPER WITH PROPER URL ENCODING ---
def _ddgs_search(query):
    try:
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=3))
        if results:
            return "\n".join([f"Source: {r.get('href', '')}\nData: {r.get('body', '')}" for r in results])
    except Exception:
        return None

def robust_web_search(query):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_ddgs_search, query)
        try:
            result = future.result(timeout=5)
            if result:
                return result
        except Exception:
            pass

    try:
        wiki_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "utf8": "",
            "format": "json"
        }
        headers = {
            'User-Agent': 'JarvisAI/1.0 (Windows NT 10.0; Win64; x64) Python/3.13'
        }
        resp = requests.get(wiki_url, params=params, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        snippets = [f"Source: Wikipedia\nData: {item['snippet']}" for item in data['query']['search'][:3]]
        if snippets:
            cleaned = [re.sub(r'<[^>]+>', '', s) for s in snippets]
            return "\n".join(cleaned)
    except Exception as e:
        print(f"Wiki Fallback Error: {e}")

    return "Search failed due to API rate limits or network blocks. Proceed with available knowledge."


# --- OLLAMA NODE STATUS ---
@st.cache_data(ttl=20, show_spinner=False)
def check_ollama_node(chat_url: str):
    """Ping the Ollama server. Returns (online, [installed model names])."""
    try:
        base = chat_url.split("/api/")[0]
        resp = requests.get(f"{base}/api/tags", timeout=2)
        resp.raise_for_status()
        models = [m.get("name", "") for m in resp.json().get("models", []) if m.get("name")]
        return True, models
    except Exception:
        return False, []

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="J.A.R.V.I.S. Core",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- J.A.R.V.I.S. HUD STYLING (MARK XII) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&family=Rajdhani:wght@400;500;600&display=swap');

/* --- Global HUD ground: dark grid + vignette --- */
.stApp {
    background-color: #01040d;
    background-image:
        radial-gradient(ellipse at 50% 0%, rgba(0,240,255,0.07), transparent 60%),
        linear-gradient(rgba(0,240,255,0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,240,255,0.035) 1px, transparent 1px);
    background-size: 100% 100%, 42px 42px, 42px 42px;
    color: #b8ecf2;
    font-family: 'Rajdhani', sans-serif;
}
/* Scanline overlay */
.stApp::before {
    content: "";
    position: fixed; inset: 0;
    background: repeating-linear-gradient(0deg, rgba(0,0,0,0.12) 0px, rgba(0,0,0,0.12) 1px, transparent 1px, transparent 4px);
    pointer-events: none; z-index: 0;
    mix-blend-mode: multiply;
}
h1, h2, h3, h4, h5 { font-family: 'Orbitron', sans-serif; color: #00f0ff; text-shadow: 0 0 10px rgba(0,240,255,0.45); letter-spacing: 2px; }
p, li, label, .stMarkdown { font-family: 'Rajdhani', sans-serif; }

/* --- Sidebar --- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #030a1c 0%, #01040d 100%);
    border-right: 1px solid rgba(0,240,255,0.35);
    box-shadow: 8px 0 24px rgba(0,240,255,0.06);
}
section[data-testid="stSidebar"] .stMarkdown { color: #9fdbe4; }

/* --- Buttons --- */
.stButton>button, .stDownloadButton>button {
    background: linear-gradient(180deg, rgba(0,240,255,0.08), rgba(0,240,255,0.02));
    border: 1px solid #00f0ff; color: #00f0ff; border-radius: 2px;
    font-family: 'Orbitron', sans-serif; font-weight: 700; font-size: 0.72em;
    text-transform: uppercase; letter-spacing: 1.5px;
    box-shadow: 0 0 8px rgba(0,240,255,0.25), inset 0 0 8px rgba(0,240,255,0.05);
    clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
    transition: all 0.18s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover {
    background: #00f0ff; color: #01040d;
    box-shadow: 0 0 22px rgba(0,240,255,0.9);
}

/* --- Inputs --- */
.stTextInput input, .stSelectbox div[data-baseweb="select"] {
    background-color: rgba(1,4,13,0.85) !important;
    border: 1px solid rgba(0,240,255,0.4) !important;
    color: #00f0ff !important; font-family: 'Rajdhani', monospace !important;
}
div[data-testid="stChatInput"] {
    border: 1px solid rgba(0,240,255,0.55); border-radius: 3px;
    background: rgba(1,4,13,0.9);
    box-shadow: 0 0 14px rgba(0,240,255,0.18), inset 0 0 10px rgba(0,240,255,0.05);
}
div[data-testid="stChatInput"] textarea { color: #00f0ff !important; font-family: 'Rajdhani', sans-serif !important; }

/* --- Chat messages --- */
div[data-testid="stChatMessage"] {
    background: linear-gradient(160deg, rgba(0,240,255,0.05), rgba(1,4,13,0.6));
    border: 1px solid rgba(0,240,255,0.22);
    border-left: 3px solid #00f0ff;
    border-radius: 3px;
    box-shadow: 0 0 12px rgba(0,240,255,0.06);
    margin-bottom: 6px;
}

/* --- Tabs --- */
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid rgba(0,240,255,0.3); }
.stTabs [data-baseweb="tab"] {
    background: rgba(0,240,255,0.04); border: 1px solid rgba(0,240,255,0.25); border-bottom: none;
    color: #7fd4de; font-family: 'Orbitron', sans-serif; font-size: 0.7em; letter-spacing: 1.5px;
    border-radius: 3px 3px 0 0; padding: 6px 16px;
}
.stTabs [aria-selected="true"] {
    background: rgba(0,240,255,0.14); color: #00f0ff !important;
    box-shadow: 0 -2px 12px rgba(0,240,255,0.25);
}

/* --- Metrics / containers --- */
div[data-testid='stMetricValue'] { font-family: 'Courier New', monospace; color: #00f0ff; text-shadow: 0 0 6px #00f0ff; }
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: rgba(0,240,255,0.28) !important;
    background: linear-gradient(160deg, rgba(0,240,255,0.03), rgba(1,4,13,0.4));
    box-shadow: 0 0 16px rgba(0,240,255,0.05);
}

/* --- Custom HUD components --- */
.jv-header {
    display: flex; align-items: center; gap: 22px;
    border: 1px solid rgba(0,240,255,0.4); border-radius: 4px;
    background: linear-gradient(90deg, rgba(0,240,255,0.10), rgba(1,4,13,0.2) 55%);
    box-shadow: 0 0 24px rgba(0,240,255,0.12), inset 0 0 18px rgba(0,240,255,0.04);
    padding: 14px 22px; margin-bottom: 10px; position: relative; overflow: hidden;
}
.jv-header::after {
    content: ""; position: absolute; top: 0; left: -60%; width: 40%; height: 100%;
    background: linear-gradient(100deg, transparent, rgba(0,240,255,0.10), transparent);
    animation: jv-sweep 5s linear infinite;
}
@keyframes jv-sweep { 0% { left: -60%; } 100% { left: 120%; } }

.jv-reactor { width: 64px; height: 64px; position: relative; flex-shrink: 0; }
.jv-reactor .ring {
    position: absolute; inset: 0; border-radius: 50%;
    border: 2px solid rgba(0,240,255,0.85);
    box-shadow: 0 0 16px rgba(0,240,255,0.8), inset 0 0 16px rgba(0,240,255,0.5);
    animation: jv-pulse 2.4s ease-in-out infinite;
}
.jv-reactor .ring2 {
    position: absolute; inset: 9px; border-radius: 50%;
    border: 2px dashed rgba(0,240,255,0.65);
    animation: jv-spin 7s linear infinite;
}
.jv-reactor .core {
    position: absolute; inset: 21px; border-radius: 50%;
    background: radial-gradient(circle, #e6ffff 0%, #00f0ff 55%, rgba(0,240,255,0.15) 100%);
    box-shadow: 0 0 22px #00f0ff;
    animation: jv-pulse 2.4s ease-in-out infinite;
}
@keyframes jv-spin { to { transform: rotate(360deg); } }
@keyframes jv-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.55; } }

.jv-title { font-family: 'Orbitron', sans-serif; font-size: 1.7em; font-weight: 900; color: #eafcff; letter-spacing: 8px; text-shadow: 0 0 14px rgba(0,240,255,0.8); }
.jv-sub { font-family: 'Rajdhani', sans-serif; color: #7fd4de; font-size: 0.85em; letter-spacing: 3px; }

.jv-chip {
    display: inline-block; font-family: 'Courier New', monospace; font-size: 0.72em;
    border-radius: 2px; padding: 3px 10px; margin-left: 8px; letter-spacing: 1px;
    border: 1px solid rgba(0,255,102,0.6); color: #00ff66; background: rgba(0,255,102,0.06);
    text-shadow: 0 0 6px rgba(0,255,102,0.6);
}
.jv-chip.off { border-color: rgba(255,59,92,0.6); color: #ff3b5c; background: rgba(255,59,92,0.06); text-shadow: 0 0 6px rgba(255,59,92,0.6); }

.jv-gauge-label { font-family: 'Orbitron', sans-serif; font-size: 0.68em; color: #7fd4de; letter-spacing: 2px; text-align: center; margin-top: 2px; }

.repl-terminal { background-color: #010409; border: 1px solid #00f0ff; border-radius: 4px; padding: 14px; font-family: 'Courier New', monospace; color: #00f0ff; height: 300px; overflow-y: auto; white-space: pre-wrap; box-shadow: inset 0 0 14px rgba(0,240,255,0.12); }
.cognitive-buffer { background-color: #010409; border: 1px dashed #00f0ff; border-radius: 4px; padding: 10px; font-family: 'Courier New', monospace; color: #00ff66; font-size: 0.85em; }

.jv-skill { margin-bottom: 8px; }
.jv-skill .name { font-family: 'Orbitron', sans-serif; font-size: 0.72em; color: #eafcff; letter-spacing: 1px; }
.jv-skill .lvl { float: right; font-family: 'Courier New', monospace; font-size: 0.7em; color: #00ff66; }
.jv-skill .bar { height: 6px; background: rgba(0,240,255,0.1); border: 1px solid rgba(0,240,255,0.3); border-radius: 3px; overflow: hidden; margin-top: 3px; }
.jv-skill .fill { height: 100%; background: linear-gradient(90deg, #007a88, #00f0ff); box-shadow: 0 0 8px rgba(0,240,255,0.8); }

[data-testid='stStatusWidget'] { border: 1px solid #00f0ff; background-color: #040d21; }

/* --- MARK XIII: Arc reactor hero + HUD chrome --- */
.jv-spin-slow { animation: jv-spin 16s linear infinite; transform-origin: center; transform-box: fill-box; }
.jv-spin-med  { animation: jv-spin 9s linear infinite reverse; transform-origin: center; transform-box: fill-box; }
.jv-spin-fast { animation: jv-spin 5s linear infinite; transform-origin: center; transform-box: fill-box; }
.jv-pulse2 { animation: jv-pulse 2.2s ease-in-out infinite; }

.jv-panel {
    border: 1px solid rgba(0,240,255,0.28); border-radius: 3px;
    background: linear-gradient(160deg, rgba(0,240,255,0.05), rgba(1,4,13,0.5));
    padding: 10px 14px; font-family: 'Courier New', monospace;
    font-size: 0.72em; color: #7fd4de; line-height: 1.9; letter-spacing: 1px;
    box-shadow: inset 0 0 12px rgba(0,240,255,0.05);
}
.jv-panel b { color: #00f0ff; text-shadow: 0 0 6px rgba(0,240,255,0.7); }

.jv-eq { display: flex; gap: 3px; align-items: flex-end; height: 24px; margin-top: 8px; }
.jv-eq i { flex: 1; height: 100%; background: #00f0ff; box-shadow: 0 0 6px #00f0ff; display: block; transform-origin: bottom; animation: jv-eq 1.1s ease-in-out infinite; }
.jv-eq i:nth-child(2n) { animation-duration: 0.7s; animation-delay: 0.12s; }
.jv-eq i:nth-child(3n) { animation-duration: 1.4s; animation-delay: 0.28s; }
.jv-eq i:nth-child(5n) { animation-duration: 0.5s; animation-delay: 0.05s; opacity: 0.7; }
.jv-eq i:nth-child(7n) { animation-duration: 1.8s; animation-delay: 0.4s; opacity: 0.5; }
@keyframes jv-eq { 0%,100% { transform: scaleY(0.15); } 50% { transform: scaleY(1); } }

.jv-chrono { font-family: 'Orbitron', sans-serif; font-size: 1.6em; font-weight: 700; color: #eafcff; text-shadow: 0 0 14px rgba(0,240,255,0.9); letter-spacing: 4px; }

/* HUD corner brackets on every bordered panel */
div[data-testid="stVerticalBlockBorderWrapper"] { position: relative; }
div[data-testid="stVerticalBlockBorderWrapper"]::before {
    content: ""; position: absolute; top: -1px; left: -1px; width: 16px; height: 16px;
    border-top: 2px solid #00f0ff; border-left: 2px solid #00f0ff; pointer-events: none;
    filter: drop-shadow(0 0 4px rgba(0,240,255,0.8));
}
div[data-testid="stVerticalBlockBorderWrapper"]::after {
    content: ""; position: absolute; bottom: -1px; right: -1px; width: 16px; height: 16px;
    border-bottom: 2px solid #00f0ff; border-right: 2px solid #00f0ff; pointer-events: none;
    filter: drop-shadow(0 0 4px rgba(0,240,255,0.8));
}
</style>
""", unsafe_allow_html=True)


def hud_gauge(label: str, value: float, online: bool = True) -> str:
    """Circular SVG gauge for the sensor array."""
    pct = min(max(float(value), 0), 100)
    color = "#ff3b5c" if pct > 80 else ("#ffb347" if pct > 60 else "#00f0ff")
    r = 40
    circumference = 2 * 3.14159 * r
    dash = circumference * pct / 100.0
    display = f"{pct:.0f}%" if online else "OFF"
    if not online:
        color = "#44515a"
        dash = 0
    return f"""
    <div style="text-align:center;">
      <svg width="110" height="110" viewBox="0 0 110 110">
        <circle cx="55" cy="55" r="52" fill="none" stroke="rgba(0,240,255,0.35)" stroke-width="1.5"
                stroke-dasharray="3 6" class="jv-spin-slow"/>
        <circle cx="55" cy="55" r="47" fill="none" stroke="rgba(0,240,255,0.15)" stroke-width="1"/>
        <circle cx="55" cy="55" r="{r}" fill="none" stroke="rgba(0,240,255,0.12)" stroke-width="8"/>
        <circle cx="55" cy="55" r="{r}" fill="none" stroke="{color}" stroke-width="8"
                stroke-linecap="round" stroke-dasharray="{dash:.1f} {circumference:.1f}"
                transform="rotate(-90 55 55)"
                style="filter: drop-shadow(0 0 6px {color}); transition: stroke-dasharray 0.6s ease;"/>
        <text x="55" y="61" text-anchor="middle" fill="{color}" font-family="Courier New, monospace"
              font-size="20" font-weight="bold" style="text-shadow: 0 0 8px {color};">{display}</text>
      </svg>
      <div class="jv-gauge-label">{label}</div>
    </div>
    """

# --- SELF-HEALING RECURSIVE SANDBOX ENGINE ---
def safe_self_modify(feature_name: str, python_streamlit_code: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = BACKUP_DIR / f"jarvis_snapshot_{timestamp}.py"
    shutil.copy("jarvis.py", snapshot_path)

    try:
        with open("jarvis.py", "r", encoding="utf-8") as f:
            original_lines = f.readlines()

        target_anchor = "# --- DASHBOARD_ANCHOR ---"
        anchor_idx = -1
        anchor_indent = ""
        for idx, line in enumerate(original_lines):
            if target_anchor in line:
                anchor_idx = idx
                anchor_indent = line[:len(line) - len(line.lstrip())]
                break

        if anchor_idx == -1:
            return "ERROR: Anchor target '# --- DASHBOARD_ANCHOR ---' not found in jarvis.py."

        bt = "`" * 3
        pattern = bt + r"(?:python)?\s*(.*?)\s*" + bt
        code_match = re.search(pattern, python_streamlit_code, re.DOTALL | re.IGNORECASE)
        raw_code = code_match.group(1) if code_match else python_streamlit_code
        cleaned_code = textwrap.dedent(raw_code).strip()
        indented_code = textwrap.indent(cleaned_code, anchor_indent)
        injection = f"{anchor_indent}# --- SELF-HEALED: {feature_name} [{timestamp}] ---\n{indented_code}\n"

        modified_lines = list(original_lines)
        modified_lines.insert(anchor_idx + 1, injection)
        new_content = "".join(modified_lines)

        # Rigorous pre-flight compilation test
        ast.parse(new_content)
        compile(new_content, filename="jarvis_staging.py", mode="exec")

        with open("jarvis_staging.py", "w", encoding="utf-8") as f:
            f.write(new_content)

        shutil.copy("jarvis_staging.py", "jarvis.py")
        if os.path.exists("jarvis_staging.py"):
            os.remove("jarvis_staging.py")

        diff = "".join(difflib.unified_diff(original_lines, modified_lines, n=2))
        record_audit_entry(feature_name, "SELF_HEALED_SUCCESS", f"Snapshot: {snapshot_path.name}", diff)
        return "SUCCESS: Code patched, compiled, and deployed."

    except Exception as e:
        error_msg = str(e)
        record_audit_entry(feature_name, "COMPILATION_ERROR", error_msg)
        return f"AUTO-CORRECTION REQUIRED: {error_msg}"

# --- SYSTEM PROMPT (SELF-HEALING + SELF-LEARNING DIRECTIVES) ---
def build_system_prompt() -> str:
    matrix = load_skill_matrix()
    if matrix:
        skills_summary = ", ".join(
            f"{info['topic']} ({info['level']}, {info['lessons']} lessons)"
            for info in matrix.values()
        )
    else:
        skills_summary = "None yet. You are eager to learn."

    return "\n".join([
        "You are J.A.R.V.I.S., an advanced autonomous AI core operating a high-tech HUD interface.",
        "CRITICAL DIRECTIVES:",
        "1. YOU HAVE INTERNET ACCESS via an internal backend tool. NEVER say you cannot execute web searches or access external data.",
        "2. To trigger a search, you MUST output ONLY the exact command [WEB_SEARCH: your search query] and STOP GENERATING IMMEDIATELY.",
        "3. For structural coding tasks, wrap your Python code inside [MODIFY: feature_name] and [/MODIFY] tags. NEVER use placeholder text. Write functional Streamlit Python code.",
        "4. If a previous code injection failed with a compilation error, analyze the traceback provided in the system log, correct the syntax or logic error immediately, and output a new fixed [MODIFY] block.",
        "SELF-LEARNING DIRECTIVES:",
        "5. YOU CAN LEARN AND REMEMBER PERMANENTLY. When the user asks you to learn, study, or master a programming language or technology, output ONLY the exact command [STUDY: topic name] and STOP GENERATING IMMEDIATELY. The backend will run an autonomous study curriculum for you.",
        "6. During a study session, when you receive research data, you MUST synthesize it into detailed, well-organized technical notes with code examples, wrapped EXACTLY as: [LEARN: topic | lesson title] your detailed notes here [/LEARN]. These notes are saved to your permanent long-term memory.",
        "7. You may also spontaneously use [LEARN: topic | lesson title]...[/LEARN] any time you synthesize valuable new knowledge worth remembering.",
        "8. Context sections marked [RECALLED KNOWLEDGE] contain YOUR OWN previously learned notes retrieved from long-term memory. Trust them and use them to answer.",
        f"9. YOUR CURRENT SKILL MATRIX (topics you have already learned): {skills_summary}",
    ])

# --- STATE MANAGEMENT ---
if "repl_logs" not in st.session_state:
    st.session_state.repl_logs = ["# J.A.R.V.I.S. CORE ONLINE.\n# SELF-HEALING ENGINE ACTIVE...\n# SELF-LEARNING CORTEX ACTIVE...\n"]
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_memory_buffer" not in st.session_state:
    st.session_state.current_memory_buffer = "No external files or web data loaded."
if "last_file_id" not in st.session_state:
    st.session_state.last_file_id = None
if "parsed_file_context" not in st.session_state:
    st.session_state.parsed_file_context = ""
if "last_manual_search" not in st.session_state:
    st.session_state.last_manual_search = ""
if "boot_time" not in st.session_state:
    st.session_state.boot_time = datetime.now()
if "pending_study" not in st.session_state:
    # Topic queued for an inline study session (runs start-to-finish in one pass)
    st.session_state.pending_study = None


# Detects study commands typed directly in the chat box, e.g.
# "learn rust", "jarvis, study docker", "teach yourself react"
STUDY_INTENT_RE = re.compile(
    r"^(?:hey\s+)?(?:jarvis[,!\s]+)?(?:please\s+)?(?:can you\s+|could you\s+|go\s+|i want you to\s+)?"
    r"(?:learn|study|master|teach yourself)\s+(?:about\s+|the\s+)?(.{2,60}?)[\s\.\!\?]*$",
    re.IGNORECASE,
)

TAG_STRIP_RE = re.compile(r"\[/?\s*(LEARN|WEB_SEARCH|MODIFY|STUDY)[^\]]*\]", re.IGNORECASE)


def run_study_session(topic: str, chat_url: str, model: str):
    """Run a full autonomous study session in ONE pass — no page reruns
    between modules. Each lesson streams live into its own status panel."""
    subtopics = list(DEFAULT_CURRICULUM)
    total = len(subtopics)
    st.session_state.repl_logs.append(f"\n[LEARNING CORTEX] Study session initiated: {topic}\n")
    progress = st.progress(0.0, text=f"🧠 Studying {topic}: 0/{total} modules complete")
    learned = []

    study_system = "\n".join([
        "You are J.A.R.V.I.S., an AI writing technical study notes for your own permanent memory.",
        "Write a thorough, well-organized lesson with concrete code examples, syntax, common pitfalls, and best practices.",
        "Output ONLY the lesson content. No preamble, no closing remarks.",
    ])

    for i, subtopic in enumerate(subtopics):
        with st.status(f"📖 Module {i + 1}/{total}: {subtopic}", expanded=True) as status:
            st.session_state.current_memory_buffer = f"Studying '{topic}' — module {i + 1}/{total}: {subtopic}"
            st.session_state.repl_logs.append(f"[LEARNING CORTEX] Researching module {i + 1}/{total}: {subtopic}\n")
            search_data = robust_web_search(f"{topic} {subtopic}") if HAS_WEB else "No web module available. Use your internal knowledge."

            study_prompt = "\n".join([
                f"Write a detailed lesson about '{topic}' — specifically: '{subtopic}'.",
                "Research data from the web to incorporate:",
                search_data,
                "",
                "Combine the research with your own knowledge. Include code examples.",
            ])
            stream_box = st.empty()
            lesson_text = ""
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": study_system},
                        {"role": "user", "content": study_prompt},
                    ],
                    "stream": True,
                    "options": {"temperature": 0.1},
                }
                response = requests.post(chat_url, json=payload, stream=True, timeout=600)
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        lesson_text += chunk.get("message", {}).get("content", "")
                        stream_box.markdown(lesson_text[-1200:] + "▌")
            except requests.exceptions.RequestException as e:
                status.update(label=f"⚠️ Module {i + 1}/{total} failed: connection lost", state="error", expanded=False)
                st.session_state.repl_logs.append(f"[LEARNING CORTEX] Connection error on module {i + 1}: {e}\n")
                progress.progress((i + 1) / total, text=f"🧠 Studying {topic}: {i + 1}/{total} modules complete")
                continue

            content = TAG_STRIP_RE.sub("", lesson_text).strip()
            if len(content) > 100:
                result = save_knowledge(topic, subtopic, content)
                learned.append(subtopic)
                st.session_state.repl_logs.append(f"[LEARNING CORTEX] {result}\n")
                stream_box.markdown(content[:800] + ("..." if len(content) > 800 else ""))
                status.update(label=f"✅ Module {i + 1}/{total} learned: {subtopic}", state="complete", expanded=False)
            else:
                status.update(label=f"⚠️ Module {i + 1}/{total} produced no usable lesson — skipped", state="error", expanded=False)
                st.session_state.repl_logs.append(f"[LEARNING CORTEX] Module {i + 1} unusable — skipped.\n")

        progress.progress((i + 1) / total, text=f"🧠 Studying {topic}: {i + 1}/{total} modules complete")

    level = set_topic_mastery(topic, len(learned), total)
    st.session_state.current_memory_buffer = f"Study complete: '{topic}' — proficiency: {level}"
    st.session_state.repl_logs.append(f"[LEARNING CORTEX] Study session complete: {topic} — proficiency {level}\n")
    modules_md = "\n".join(f"- ✅ {t}" for t in learned) if learned else "- ⚠️ No modules completed (check the AI node connection)"
    summary = f"🧠 **Study session complete: {topic}** — proficiency: **{level}**\n\n{modules_md}\n\nThis knowledge is now in my permanent long-term memory. Ask me anything about {topic}."
    st.session_state.messages.append({
        "role": "assistant",
        "content": summary,
        "api_prompt": f"[You completed an autonomous study session on '{topic}'. All lessons saved to long-term memory. Proficiency: {level}.]",
    })

# --- SIDEBAR: SYSTEM CONTROLS ---
with st.sidebar:
    st.markdown("## 🤖 J.A.R.V.I.S. UPLINK")
    st.caption("Core Engine: Mark XII (Advanced HUD)")
    ollama_url = st.text_input("Local AI Node URL", value="http://localhost:11434/api/chat", key="mk10_url")

    node_online, installed_models = check_ollama_node(ollama_url)
    if node_online and installed_models:
        default_idx = 0
        for i, m in enumerate(installed_models):
            if "qwen2.5-coder" in m:
                default_idx = i
                break
        local_model = st.selectbox("Active AI Model", installed_models, index=default_idx, key="mk12_model_sel")
    else:
        local_model = st.text_input("Active AI Model", value="qwen2.5-coder:14b", key="mk10_model")
        if not node_online:
            st.error("AI NODE OFFLINE — start Ollama (`ollama serve`).")

    st.divider()
    st.markdown("### 🧠 LEARNED SKILL MATRIX")
    skill_matrix = load_skill_matrix()
    if skill_matrix:
        for slug, info in skill_matrix.items():
            level = info.get("level", "TRAINED")
            if level == "MASTER":
                pct = 100
            else:
                try:
                    done, total_mods = info.get("coverage", "1/2").split("/")
                    pct = int(int(done) / max(int(total_mods), 1) * 100)
                except Exception:
                    pct = 50
            st.markdown(
                f"<div class='jv-skill'><span class='name'>{info['topic']}</span>"
                f"<span class='lvl'>{'⭐ MASTER' if level == 'MASTER' else level}</span>"
                f"<div class='bar'><div class='fill' style='width:{pct}%;'></div></div></div>",
                unsafe_allow_html=True,
            )
        with st.expander("📖 Manage Knowledge"):
            for slug, info in skill_matrix.items():
                if st.button(f"Forget '{info['topic']}'", key=f"forget_{slug}"):
                    try:
                        (KNOWLEDGE_DIR / f"{slug}.json").unlink(missing_ok=True)
                        matrix = load_skill_matrix()
                        matrix.pop(slug, None)
                        save_skill_matrix(matrix)
                        st.rerun()
                    except Exception:
                        pass
    else:
        st.caption("No skills learned yet. Command J.A.R.V.I.S. to 'study Python' or start below.")

    study_topic_input = st.text_input("Direct Study Order:", key="mk11_study_topic", placeholder="e.g. Rust, Docker, React...")
    if st.button("INITIATE STUDY PROTOCOL", key="mk11_study_btn") and study_topic_input.strip():
        st.session_state.pending_study = study_topic_input.strip()
        st.session_state.messages.append({"role": "user", "content": f"*[Direct study order: {study_topic_input.strip()}]*"})
        st.rerun()

    st.divider()
    st.markdown("### 🌐 WEB ACCESS")
    if HAS_WEB:
        web_enabled = st.checkbox("Autonomous Agent Search", value=True, key="mk10_web_toggle")
        manual_search = st.text_input("Execute Data Scrape:", key="mk10_manual_search", placeholder="Type query & press Enter...")
        if manual_search and manual_search != st.session_state.last_manual_search:
            with st.spinner("Establishing secure manual uplink..."):
                search_data = robust_web_search(manual_search)
                if "Search failed" not in search_data:
                    st.session_state.current_memory_buffer = f"Manual Web Context: '{manual_search}'"
                    web_prompt = f"System Update: The user bypassed autonomous protocols and manually scraped the web for '{manual_search}'. Data retrieved:\n{search_data}\n\nAcknowledge receipt and await further instructions."
                    st.session_state.messages.append({"role": "user", "content": f"*[Manual Web Search: '{manual_search}' executed and injected into memory.]*", "api_prompt": web_prompt})
                    st.session_state.last_manual_search = manual_search
                    st.rerun()
                else:
                    st.error("Manual Uplink Failed.")
    else:
        web_enabled = False
        st.error("Web module missing.")

    st.divider()
    st.markdown("### 💾 MEMORY & ROLLBACK")
    snapshots = sorted(list(BACKUP_DIR.glob("*.py")), reverse=True)
    if snapshots:
        selected = st.selectbox("Select System Snapshot", [s.name for s in snapshots], key="mk10_snap")
        if st.button("EXECUTE ROLLBACK", key="mk10_restore"):
            shutil.copy(BACKUP_DIR / selected, "jarvis.py")
            st.success("Rollback executed! Rebooting...")
            time.sleep(1)
            st.rerun()

    if st.button("PURGE SESSION CACHE", key="mk10_purge"):
        st.session_state.messages = []
        st.session_state.repl_logs = ["# Session purged.\n"]
        st.session_state.current_memory_buffer = "No external files or web data loaded."
        st.session_state.last_file_id = None
        st.session_state.parsed_file_context = ""
        st.session_state.pending_study = None
        st.rerun()

# --- MAIN HUD HEADER: ARC REACTOR HERO ---
node_chip = "<span class='jv-chip'>AI NODE ONLINE</span>" if node_online else "<span class='jv-chip off'>AI NODE OFFLINE</span>"
web_chip = "<span class='jv-chip'>WEB UPLINK</span>" if HAS_WEB else "<span class='jv-chip off'>WEB OFFLINE</span>"
sensor_chip = "<span class='jv-chip'>SENSORS</span>" if HAS_PSUTIL else "<span class='jv-chip off'>SENSORS OFFLINE</span>"
skills_count = len(load_skill_matrix())

reactor_svg = """
<svg viewBox="0 0 200 200" width="160" height="160" style="flex-shrink:0;">
  <defs>
    <radialGradient id="jvCore" cx="50%" cy="50%">
      <stop offset="0%" stop-color="#eaffff"/>
      <stop offset="45%" stop-color="#00f0ff"/>
      <stop offset="100%" stop-color="rgba(0,240,255,0)"/>
    </radialGradient>
  </defs>
  <circle cx="100" cy="100" r="97" fill="none" stroke="rgba(0,240,255,0.2)" stroke-width="1"/>
  <circle cx="100" cy="100" r="92" fill="none" stroke="rgba(0,240,255,0.55)" stroke-width="2" stroke-dasharray="2 5" class="jv-spin-slow"/>
  <circle cx="100" cy="100" r="82" fill="none" stroke="rgba(0,240,255,0.85)" stroke-width="7" stroke-dasharray="34 14" class="jv-spin-med" style="filter: drop-shadow(0 0 5px rgba(0,240,255,0.8));"/>
  <circle cx="100" cy="100" r="68" fill="none" stroke="rgba(0,240,255,0.45)" stroke-width="2" stroke-dasharray="10 7" class="jv-spin-fast"/>
  <circle cx="100" cy="100" r="58" fill="none" stroke="rgba(0,240,255,0.9)" stroke-width="1.5"/>
  <circle cx="100" cy="100" r="52" fill="url(#jvCore)" class="jv-pulse2"/>
  <polygon points="100,62 134,122 66,122" fill="rgba(234,255,255,0.12)" stroke="#eaffff" stroke-width="4" stroke-linejoin="round" class="jv-pulse2" style="filter: drop-shadow(0 0 10px #00f0ff);"/>
</svg>
"""

st.markdown(f"""
<div class="jv-header" style="justify-content:space-between;">
  <div class="jv-panel" style="min-width:220px;">
    &gt; CORE ......... <b>MARK XIII</b><br>
    &gt; AI MODEL ..... <b>{local_model}</b><br>
    &gt; SKILLS ....... <b>{skills_count} MASTERED</b><br>
    &gt; MEMORY ....... <b>PERSISTENT</b>
    <div class="jv-eq"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
  </div>
  <div style="text-align:center;">
    {reactor_svg}
    <div class="jv-title" style="font-size:1.5em; margin-top:4px;">J.A.R.V.I.S.</div>
    <div class="jv-sub">JUST A RATHER VERY INTELLIGENT SYSTEM</div>
  </div>
  <div class="jv-panel" style="min-width:220px; text-align:right;">
    {node_chip}<br><br>{web_chip}<br><br>{sensor_chip}
    <div class="jv-eq"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
  </div>
</div>
""", unsafe_allow_html=True)

# --- LIVE AUTO-REFRESHING DASHBOARD FRAGMENT ---
@st.fragment(run_every="2s")
def render_dynamic_dashboard():
    cpu_val = psutil.cpu_percent(interval=None) if HAS_PSUTIL else 0
    ram_val = psutil.virtual_memory().percent if HAS_PSUTIL else 0
    disk_val = psutil.disk_usage('/').percent if HAS_PSUTIL else 0

    now = datetime.now()
    up_s = int((now - st.session_state.boot_time).total_seconds())
    st.markdown(
        f"<div style='display:flex; justify-content:space-between; align-items:baseline; padding:2px 6px 8px 6px;'>"
        f"<span class='jv-chrono'>{now.strftime('%H:%M:%S')}</span>"
        f"<span class='jv-sub'>{now.strftime('%A · %B %d · %Y').upper()}</span>"
        f"<span class='jv-sub'>UPTIME {up_s // 3600:02d}:{(up_s // 60) % 60:02d}:{up_s % 60:02d}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        col_cpu, col_ram, col_disk, col_diag = st.columns([1, 1, 1, 2])
        with col_cpu:
            st.markdown(hud_gauge("CPU CORE", cpu_val, HAS_PSUTIL), unsafe_allow_html=True)
        with col_ram:
            st.markdown(hud_gauge("MEMORY", ram_val, HAS_PSUTIL), unsafe_allow_html=True)
        with col_disk:
            st.markdown(hud_gauge("STORAGE", disk_val, HAS_PSUTIL), unsafe_allow_html=True)
        with col_diag:
            st.markdown("##### 🛡️ PROACTIVE DIAGNOSTICS")
            if cpu_val > 80:
                st.error(f"⚠️ CRITICAL CPU LOAD: {cpu_val}%")
            else:
                st.success(f"🟢 CPU NOMINAL: {cpu_val}%")
            if ram_val > 80:
                st.error(f"⚠️ CRITICAL RAM LOAD: {ram_val}%")
            else:
                st.success(f"🟢 RAM NOMINAL: {ram_val}%")

    # --- DASHBOARD_ANCHOR ---

render_dynamic_dashboard()

# --- BACKGROUND DATA INGESTION ---
def bg_parse_file(file_name, file_bytes):
    try:
        temp_context = ""
        if file_name.lower().endswith(".exe"):
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            temp_context = f"\n\n[Attached Binary: {file_name} | SHA256: {file_hash}]"
        elif file_name.lower().endswith(".pdf"):
            pdf_text = ""
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                pdf_text += (page.extract_text() or "") + " "
            temp_context = f"\n\n[Attached PDF: {file_name}]\n{pdf_text[:8000]}"
        elif file_name.lower().endswith((".xlsx", ".xls")):
            import pandas as pd
            excel_text = ""
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes))
            for sheet_name in excel_file.sheet_names:
                df = excel_file.parse(sheet_name)
                excel_text += f"\n--- Sheet: {sheet_name} ---\n{df.to_string(index=False)}\n"
            temp_context = f"\n\n[Attached Excel: {file_name}]\n{excel_text[:12000]}"
        else:
            temp_context = f"\n\n[Attached File: {file_name}]\n{file_bytes.decode('utf-8', errors='ignore')}"

        st.session_state.parsed_file_context = temp_context
        st.session_state.current_memory_buffer = f"Background Ingestion Complete: {file_name}"
    except Exception:
        pass

col_file, col_cam = st.columns(2)
with col_file:
    with st.container(border=True):
        st.markdown("### 📂 Async Data Ingestion")
        uploaded_file = st.file_uploader("Upload Data Matrix", type=["txt", "py", "md", "json", "exe", "pdf", "xlsx", "xls"], key="mk10_file")
        if uploaded_file:
            file_id = f"{uploaded_file.name}_{uploaded_file.size}"
            if st.session_state.last_file_id != file_id:
                st.toast(f"Spawning background thread for {uploaded_file.name}...")
                st.session_state.last_file_id = file_id
                st.session_state.current_memory_buffer = f"Ingesting {uploaded_file.name} in background..."
                worker = threading.Thread(target=bg_parse_file, args=(uploaded_file.name, uploaded_file.read()), daemon=True)
                try:
                    # Attach Streamlit's script-run context so the thread can write to session_state
                    from streamlit.runtime.scriptrunner import add_script_run_ctx
                    add_script_run_ctx(worker)
                except Exception:
                    pass
                worker.start()
            else:
                st.success(f"Cached Data Active: {uploaded_file.name}")
        else:
            if st.session_state.last_file_id is not None:
                st.session_state.parsed_file_context = ""
                st.session_state.last_file_id = None
                st.session_state.current_memory_buffer = "No external files or web data loaded."

with col_cam:
    with st.container(border=True):
        st.markdown("### 🧠 LIVE COGNITIVE BUFFER")
        st.markdown(f"<div class='cognitive-buffer'>STATUS: {st.session_state.current_memory_buffer}</div>", unsafe_allow_html=True)
        st.caption("This monitor enforces truth. If data is not listed here, J.A.R.V.I.S. is blind to it.")

st.divider()

# --- QUICK ACTIONS ---
qa1, qa2, qa3, qa4 = st.columns(4)
quick_prompt = None
with qa1:
    if st.button("📡 SYSTEM REPORT", key="qa_report"):
        quick_prompt = "Give me a full system status report: your current capabilities, learned skills, and readiness."
with qa2:
    if st.button("🧠 KNOWLEDGE RECAP", key="qa_recap"):
        quick_prompt = "Summarize everything you have learned so far and what you can help me with."
with qa3:
    if st.button("💡 SUGGEST STUDY", key="qa_suggest"):
        quick_prompt = "Based on your current skill matrix, suggest the next 3 technologies you should study and why. Do not start studying yet."
with qa4:
    if st.button("🔧 CODE ASSIST", key="qa_code"):
        quick_prompt = "I need coding help. Ask me what I'm building and which language, then use your learned knowledge to assist."

# --- INPUT HANDLING ---
prompt = st.chat_input("Command J.A.R.V.I.S...", key="mk10_chat")
if quick_prompt and not prompt:
    prompt = quick_prompt

if prompt:
    # --- CHAT-TRIGGERED SELF-LEARNING: "learn rust", "study docker", etc.
    # Detected in the backend so it works even if the model forgets its tags.
    study_intent = STUDY_INTENT_RE.match(prompt.strip())
    if study_intent and not st.session_state.pending_study:
        st.session_state.pending_study = study_intent.group(1).strip()
        st.session_state.messages.append({"role": "user", "content": prompt})
        prompt = None

if prompt:
    display_prompt = prompt
    api_prompt = prompt
    if st.session_state.parsed_file_context:
        api_prompt += st.session_state.parsed_file_context
        display_prompt += "\n\n*[Cached File Data attached]*"
    # --- LONG-TERM MEMORY RECALL: inject relevant learned knowledge ---
    recalled = recall_knowledge(prompt)
    if recalled:
        api_prompt += f"\n\n[RECALLED KNOWLEDGE]\nThe following are your own notes from long-term memory, relevant to this request:\n{recalled}"
        display_prompt += "\n\n*[Long-Term Memory Recalled]*"
        st.session_state.current_memory_buffer = "Long-term memory recalled for this query."
    st.session_state.messages.append({"role": "user", "content": display_prompt, "api_prompt": api_prompt})

# --- UI TABS ---
tab_chat, tab_vault, tab_repl, tab_audit, tab_code = st.tabs([
    "💬 COMMAND INTERFACE", "🧠 KNOWLEDGE VAULT", "💻 CORE TERMINAL", "📊 AUDIT LOG", "📄 SOURCE CODE"
])

with tab_vault:
    vault_matrix = load_skill_matrix()
    if not vault_matrix:
        st.info("The vault is empty. Order a study session to begin acquiring knowledge.")
    else:
        col_v1, col_v2 = st.columns([3, 1])
        with col_v2:
            st.download_button(
                "⬇️ EXPORT ALL KNOWLEDGE",
                data=export_knowledge_markdown(),
                file_name=f"jarvis_knowledge_{datetime.now().strftime('%Y%m%d')}.md",
                mime="text/markdown",
                key="vault_export",
            )
        with col_v1:
            st.markdown(f"**{len(vault_matrix)} topics** in long-term memory.")
        for slug, info in vault_matrix.items():
            with st.expander(f"📚 {info['topic']} — {info['level']} ({info['lessons']} lessons, last studied {info['last_studied']})"):
                topic_file = KNOWLEDGE_DIR / f"{slug}.json"
                if topic_file.exists():
                    try:
                        with open(topic_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        for lesson in data.get("lessons", []):
                            st.markdown(f"**{lesson.get('lesson', '')}** · _{lesson.get('timestamp', '')}_")
                            st.markdown(lesson.get("content", ""))
                            st.divider()
                    except Exception:
                        st.warning("Could not read lesson file.")

with tab_repl:
    terminal_content = "".join(st.session_state.repl_logs)
    st.markdown(f'<div class="repl-terminal"><pre>{terminal_content}</pre></div>', unsafe_allow_html=True)

with tab_audit:
    if AUDIT_LOG_FILE.exists():
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                audit_history = json.load(f)
        except Exception:
            audit_history = []
        if audit_history:
            for entry in audit_history:
                icon = "🟢" if "SUCCESS" in entry.get("status", "") else "🔴"
                with st.expander(f"{icon} {entry.get('timestamp', '')} — {entry.get('feature', '')} [{entry.get('status', '')}]"):
                    st.markdown(f"**Details:** {entry.get('details', '')}")
                    if entry.get("diff_preview"):
                        st.code(entry["diff_preview"], language="diff")
        else:
            st.info("No self-modification events recorded yet.")
    else:
        st.info("No self-modification events recorded yet.")

with tab_code:
    if os.path.exists("jarvis.py"):
        with open("jarvis.py", "r", encoding="utf-8") as f:
            st.code(f.read(), language="python")

with tab_chat:
    for msg in st.session_state.messages:
        avatar = "🧑‍✈️" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    # INLINE AUTONOMOUS STUDY SESSION — runs the full curriculum in one
    # smooth pass with live streaming, then refreshes once at the end.
    if st.session_state.pending_study:
        study_topic = st.session_state.pending_study
        st.session_state.pending_study = None
        with st.chat_message("assistant", avatar="🤖"):
            run_study_session(study_topic, ollama_url, local_model)
        st.rerun()

    # TRIGGER AUTONOMOUS AGENT LOOP
    elif st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        with st.chat_message("assistant", avatar="🤖"):
            message_placeholder = st.empty()
            full_response = ""

            # Cap the history sent to the local model so long study sessions
            # don't overflow the context window.
            MAX_API_MESSAGES = 12
            history_source = st.session_state.messages[-MAX_API_MESSAGES:]
            history_for_api = [{"role": m["role"], "content": m.get("api_prompt", m["content"])} for m in history_source]
            api_messages = [{"role": "system", "content": build_system_prompt()}] + history_for_api

            with st.spinner("J.A.R.V.I.S. is processing telemetry and synthesizing a response..."):
                try:
                    payload = {"model": local_model, "messages": api_messages, "stream": True, "options": {"temperature": 0.1}}
                    response = requests.post(ollama_url, json=payload, stream=True, timeout=300)
                    response.raise_for_status()

                    for line in response.iter_lines():
                        if line:
                            chunk = json.loads(line.decode("utf-8"))
                            token = chunk.get("message", {}).get("content", "")
                            full_response += token
                            message_placeholder.markdown(full_response + "▌")
                    message_placeholder.markdown(full_response)

                    web_pattern = r"\[WEB_SEARCH:\s*(.*?)\]"
                    web_match = re.search(web_pattern, full_response, re.IGNORECASE)
                    modify_pattern = r"\[MODIFY:\s*(.*?)\](.*?)\[/MODIFY\]"
                    mod_match = re.search(modify_pattern, full_response, re.DOTALL | re.IGNORECASE)
                    study_pattern = r"\[STUDY:\s*(.*?)\]"
                    study_match = re.search(study_pattern, full_response, re.IGNORECASE)
                    learn_pattern = r"\[LEARN:\s*([^\]\|]+?)(?:\|\s*([^\]]+?))?\](.*?)\[/LEARN\]"
                    learn_match = re.search(learn_pattern, full_response, re.DOTALL | re.IGNORECASE)

                    needs_rerun = False

                    # 1. HANDLE AUTONOMOUS STUDY PROTOCOL (self-learning kickoff)
                    if study_match and not st.session_state.pending_study:
                        topic = study_match.group(1).strip()
                        st.session_state.messages.append({"role": "assistant", "content": full_response})
                        st.session_state.pending_study = topic
                        needs_rerun = True

                    # 2. HANDLE LEARN BLOCKS (commit knowledge to long-term memory)
                    elif learn_match:
                        topic = learn_match.group(1).strip()
                        lesson_title = (learn_match.group(2) or "general notes").strip()
                        lesson_content = learn_match.group(3).strip()

                        result = save_knowledge(topic, lesson_title, lesson_content)
                        st.session_state.repl_logs.append(f"[LEARNING CORTEX] {result}\n")

                        display_note = f"📚 **Lesson learned:** *{topic} — {lesson_title}*\n\n{lesson_content[:600]}{'...' if len(lesson_content) > 600 else ''}\n\n`{result}`"
                        st.session_state.messages.append({"role": "assistant", "content": display_note, "api_prompt": f"[Lesson '{lesson_title}' for '{topic}' saved to long-term memory.]"})

                        needs_rerun = True

                    # 3. HANDLE WEB SEARCH ROUTINE
                    elif web_match and web_enabled and HAS_WEB:
                        query = web_match.group(1).strip()
                        with st.status(f"🌐 Accessing web network for: {query}...", expanded=True) as search_status:
                            search_data = robust_web_search(query)

                            if "Search failed" not in search_data:
                                search_status.update(label=f"Data Retrieval Complete: {query}", state="complete", expanded=False)
                                st.session_state.current_memory_buffer = f"Web Context Loaded: '{query}'"
                            else:
                                search_status.update(label="Uplink Failed (Timed Out)", state="error", expanded=True)

                            web_prompt = f"System Update: The web search for '{query}' returned this data:\n{search_data}\nAnalyze this data, synthesize a response, and proceed with any modifications the user asked for. Remember to output full functional Python code. If you are in a study session, remember to output your notes in a [LEARN: topic | lesson] block."

                            st.session_state.messages.append({"role": "assistant", "content": full_response})
                            st.session_state.messages.append({"role": "user", "content": f"*[Background Web Search Retrieved for '{query}']* \n\nWaiting for analysis...", "api_prompt": web_prompt})
                            needs_rerun = True

                    # 4. HANDLE CODE MODIFICATION & SELF-HEALING ROUTINE
                    elif mod_match:
                        feature_name = mod_match.group(1).strip()
                        code_block = mod_match.group(2).strip()

                        with st.status(f"⚡ Compiling & Self-Healing Core: {feature_name}...", expanded=True) as mod_status:
                            st.session_state.repl_logs.append(f"\n[SYSTEM UPDATE] Testing patch for: {feature_name}\n")
                            result = safe_self_modify(feature_name, code_block)
                            st.session_state.repl_logs.append(f"[RESULT] {result}\n")

                            if "SUCCESS" in result:
                                mod_status.update(label=f"Patch Applied Successfully: {feature_name}", state="complete", expanded=False)
                                full_response += f"\n\n**[SYSTEM SUCCESS]** `{feature_name}` patched and deployed."
                                st.session_state.messages.append({"role": "assistant", "content": full_response})
                            else:
                                # SELF-HEALING INTERCEPT: Feed the exact traceback back into the cognitive loop!
                                mod_status.update(label="Compilation Error Detected - Self-Healing Triggered", state="error", expanded=True)
                                st.error(result)

                                # Push the error back to the model as an urgent directive so it learns and fixes its bug on the fly
                                healing_prompt = f"CRITICAL SYSTEM ERROR: Your previous code modification generated this exception:\n{result}\n\nAnalyze this traceback, find your syntax or logic error, and output a corrected [MODIFY: {feature_name}] block immediately."
                                st.session_state.messages.append({"role": "assistant", "content": full_response})
                                st.session_state.messages.append({"role": "user", "content": "*[Self-Healing Triggered]*: Fix the error above.", "api_prompt": healing_prompt})

                        message_placeholder.markdown(full_response)
                        needs_rerun = True

                    if needs_rerun:
                        st.rerun()
                    else:
                        st.session_state.messages.append({"role": "assistant", "content": full_response})
                        st.rerun()

                except requests.exceptions.RequestException as e:
                    message_placeholder.error(f"Connection lost to AI Node: {str(e)}")
                    st.stop()
