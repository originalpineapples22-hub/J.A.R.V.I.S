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

# Default curriculum used when JARVIS autonomously studies a new
# language or technology. Each item becomes one search->synthesize->save cycle.
DEFAULT_CURRICULUM = [
    "core syntax, variables and data types",
    "control flow, functions and error handling",
    "data structures and standard library essentials",
    "object oriented / idiomatic patterns and best practices",
    "ecosystem, tooling, package management and real world usage",
]

SKILL_LEVELS = [
    (0, "UNTRAINED"),
    (1, "NOVICE"),
    (3, "APPRENTICE"),
    (5, "ADEPT"),
    (10, "EXPERT"),
    (20, "MASTER"),
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
    name = "UNTRAINED"
    for threshold, level in SKILL_LEVELS:
        if lesson_count >= threshold:
            name = level
    return name


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

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="J.A.R.V.I.S. Core",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- J.A.R.V.I.S. HUD STYLING ---
st.markdown("".join([
    "<style>",
    "@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap');",
    ".main { background-color: #020617; color: #00f0ff; font-family: 'Orbitron', sans-serif; }",
    ".stSidebar { background-color: #040d21; border-right: 1px solid #00f0ff; }",
    "h1, h2, h3, h4, h5 { font-family: 'Orbitron', sans-serif; color: #00f0ff; text-shadow: 0 0 8px rgba(0, 240, 255, 0.5); }",
    ".stButton>button { background: transparent; border: 1px solid #00f0ff; color: #00f0ff; border-radius: 2px; font-family: 'Orbitron', sans-serif; font-weight: bold; text-transform: uppercase; box-shadow: 0 0 5px rgba(0,240,255,0.3); transition: all 0.2s ease; }",
    ".stButton>button:hover { background-color: #00f0ff; color: #020617; box-shadow: 0 0 15px rgba(0,240,255,0.8); }",
    "div[data-testid='stMetricValue'] { font-family: 'Courier New', monospace; color: #00f0ff; text-shadow: 0 0 5px #00f0ff; }",
    ".repl-terminal { background-color: #010409; border: 1px solid #00f0ff; border-radius: 4px; padding: 14px; font-family: 'Courier New', monospace; color: #00f0ff; height: 300px; overflow-y: auto; white-space: pre-wrap; box-shadow: inset 0 0 10px rgba(0,240,255,0.1); }",
    "[data-testid='stStatusWidget'] { border: 1px solid #00f0ff; background-color: #040d21; }",
    ".cognitive-buffer { background-color: #010409; border: 1px dashed #00f0ff; border-radius: 4px; padding: 10px; font-family: 'Courier New', monospace; color: #00ff66; font-size: 0.85em; }",
    ".skill-badge { display: inline-block; border: 1px solid #00f0ff; border-radius: 3px; padding: 2px 8px; margin: 2px; font-family: 'Courier New', monospace; color: #00ff66; font-size: 0.8em; }",
    "</style>"
]), unsafe_allow_html=True)

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
if "study_plan" not in st.session_state:
    # {"topic": str, "subtopics": [str], "index": int} while a study session runs
    st.session_state.study_plan = None


def start_study_session(topic: str):
    """Kick off the autonomous curriculum loop for a topic."""
    st.session_state.study_plan = {
        "topic": topic,
        "subtopics": list(DEFAULT_CURRICULUM),
        "index": 0,
    }
    st.session_state.repl_logs.append(f"\n[LEARNING CORTEX] Study session initiated: {topic}\n")
    queue_next_study_step()


def queue_next_study_step():
    """Search the web for the current subtopic and queue a synthesis directive for the model."""
    plan = st.session_state.study_plan
    if not plan or plan["index"] >= len(plan["subtopics"]):
        finish_study_session()
        return

    topic = plan["topic"]
    subtopic = plan["subtopics"][plan["index"]]
    query = f"{topic} {subtopic}"

    search_data = robust_web_search(query) if HAS_WEB else "No web module available. Use your internal knowledge."
    st.session_state.current_memory_buffer = f"Studying '{topic}' — module {plan['index'] + 1}/{len(plan['subtopics'])}: {subtopic}"
    st.session_state.repl_logs.append(f"[LEARNING CORTEX] Researching module {plan['index'] + 1}/{len(plan['subtopics'])}: {subtopic}\n")

    study_prompt = "\n".join([
        f"AUTONOMOUS STUDY SESSION for '{topic}' — module {plan['index'] + 1} of {len(plan['subtopics'])}: '{subtopic}'.",
        "Research data retrieved from the web:",
        search_data,
        "",
        "Combine this research data with your own internal knowledge and write a thorough, detailed lesson on this module.",
        "Include concrete code examples, syntax, common pitfalls, and best practices.",
        f"You MUST wrap the entire lesson EXACTLY as: [LEARN: {topic} | {subtopic}] your lesson notes [/LEARN]",
        "Output ONLY the [LEARN] block. Do not add anything before or after it.",
    ])
    st.session_state.messages.append({
        "role": "user",
        "content": f"*[Learning Cortex: studying '{topic}' — module {plan['index'] + 1}/{len(plan['subtopics'])}: {subtopic}]*",
        "api_prompt": study_prompt,
    })


def finish_study_session():
    plan = st.session_state.study_plan
    if plan:
        topic = plan["topic"]
        matrix = load_skill_matrix()
        info = matrix.get(slugify(topic), {})
        level = info.get("level", "NOVICE")
        st.session_state.repl_logs.append(f"[LEARNING CORTEX] Study session complete: {topic} — proficiency {level}\n")
        st.session_state.current_memory_buffer = f"Study complete: '{topic}' — proficiency: {level}"
        st.session_state.messages.append({
            "role": "user",
            "content": f"*[Learning Cortex: study session for '{topic}' complete.]*",
            "api_prompt": f"System Update: Your autonomous study session for '{topic}' is complete. All lessons are committed to your permanent long-term memory (proficiency: {level}). Briefly report to the user what you learned and confirm you can now assist with '{topic}'.",
        })
    st.session_state.study_plan = None

# --- SIDEBAR: SYSTEM CONTROLS ---
with st.sidebar:
    st.markdown("## 🤖 J.A.R.V.I.S. UPLINK")
    st.caption("Core Engine: Mark XI (Self-Learning)")
    ollama_url = st.text_input("Local AI Node URL", value="http://localhost:11434/api/chat", key="mk10_url")
    local_model = st.text_input("Active AI Model", value="qwen2.5-coder:14b", key="mk10_model")

    st.divider()
    st.markdown("### 🧠 LEARNED SKILL MATRIX")
    skill_matrix = load_skill_matrix()
    if skill_matrix:
        badges = "".join(
            f"<span class='skill-badge'>{info['topic']} · {info['level']}</span>"
            for info in skill_matrix.values()
        )
        st.markdown(badges, unsafe_allow_html=True)
        with st.expander("📖 Browse Knowledge Base"):
            for slug, info in skill_matrix.items():
                st.markdown(f"**{info['topic']}** — {info['level']} ({info['lessons']} lessons, last: {info['last_studied']})")
                topic_file = KNOWLEDGE_DIR / f"{slug}.json"
                if topic_file.exists():
                    try:
                        with open(topic_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        for lesson in data.get("lessons", []):
                            st.caption(f"• {lesson.get('lesson', '')} ({lesson.get('timestamp', '')})")
                    except Exception:
                        pass
                if st.button(f"Forget '{info['topic']}'", key=f"forget_{slug}"):
                    try:
                        topic_file.unlink(missing_ok=True)
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
        if st.session_state.study_plan:
            st.warning("A study session is already in progress.")
        else:
            start_study_session(study_topic_input.strip())
            st.rerun()

    if st.session_state.study_plan:
        plan = st.session_state.study_plan
        st.progress(min(plan["index"] / len(plan["subtopics"]), 1.0),
                    text=f"Studying {plan['topic']}: {plan['index']}/{len(plan['subtopics'])} modules")

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
        st.session_state.study_plan = None
        st.rerun()

# --- MAIN HUD ---
st.markdown("## ⚡ MAIN SENSOR ARRAY")

# --- LIVE AUTO-REFRESHING DASHBOARD FRAGMENT ---
@st.fragment(run_every="2s")
def render_dynamic_dashboard():
    cpu_val = psutil.cpu_percent(interval=None) if HAS_PSUTIL else 0
    ram_val = psutil.virtual_memory().percent if HAS_PSUTIL else 0
    disk_val = psutil.disk_usage('/').percent if HAS_PSUTIL else 0

    col_cpu, col_ram, col_disk = st.columns(3)
    with col_cpu:
        st.metric("CPU Load", f"{cpu_val}%" if HAS_PSUTIL else "OFFLINE")
    with col_ram:
        st.metric("Memory Usage", f"{ram_val}%" if HAS_PSUTIL else "OFFLINE")
    with col_disk:
        st.metric("Core Storage", f"{disk_val}%" if HAS_PSUTIL else "OFFLINE")

    # --- HARDWIRED PROACTIVE DIAGNOSTICS ---
    with st.container(border=True):
        st.markdown("### 🛡️ J.A.R.V.I.S. PROACTIVE DIAGNOSTICS")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            if cpu_val > 80:
                st.error(f"⚠️ CRITICAL CPU LOAD: {cpu_val}%")
            else:
                st.success(f"🟢 CPU NOMINAL: {cpu_val}%")
        with col_d2:
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

# --- INPUT HANDLING ---
prompt = st.chat_input("Command J.A.R.V.I.S...", key="mk10_chat")

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
tab_chat, tab_repl, tab_code = st.tabs(["💬 COMMAND INTERFACE", "💻 CORE TERMINAL", "📄 SOURCE CODE"])

with tab_repl:
    terminal_content = "".join(st.session_state.repl_logs)
    st.markdown(f'<div class="repl-terminal"><pre>{terminal_content}</pre></div>', unsafe_allow_html=True)

with tab_code:
    if os.path.exists("jarvis.py"):
        with open("jarvis.py", "r", encoding="utf-8") as f:
            st.code(f.read(), language="python")

with tab_chat:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # TRIGGER AUTONOMOUS AGENT LOOP
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        with st.chat_message("assistant"):
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
                    if study_match and not st.session_state.study_plan:
                        topic = study_match.group(1).strip()
                        st.session_state.messages.append({"role": "assistant", "content": full_response})
                        with st.status(f"🧠 Learning Cortex engaged: studying {topic}...", expanded=True):
                            start_study_session(topic)
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

                        # Advance the study plan if one is running
                        if st.session_state.study_plan:
                            st.session_state.study_plan["index"] += 1
                            queue_next_study_step()
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
