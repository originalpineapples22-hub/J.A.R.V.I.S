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
        except (concurrent.futures.TimeoutError, Exception):
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
        pass
    
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

# --- SYSTEM PROMPT (SELF-HEALING DIRECTIVES) ---
system_prompt = "\n".join([
    "You are J.A.R.V.I.S., an advanced autonomous AI core operating a high-tech HUD interface.",
    "CRITICAL DIRECTIVES:",
    "1. YOU HAVE INTERNET ACCESS via an internal backend tool. NEVER say you cannot execute web searches or access external data.",
    "2. To trigger a search, you MUST output ONLY the exact command [WEB_SEARCH: your search query] and STOP GENERATING IMMEDIATELY.",
    "3. For structural coding tasks, wrap your Python code inside [MODIFY: feature_name] and [/MODIFY] tags. NEVER use placeholder text. Write functional Streamlit Python code.",
    "4. If a previous code injection failed with a compilation error, analyze the traceback provided in the system log, correct the syntax or logic error immediately, and output a new fixed [MODIFY] block."
])

# --- STATE MANAGEMENT ---
if "repl_logs" not in st.session_state:
    st.session_state.repl_logs = ["# J.A.R.V.I.S. CORE ONLINE.\n# SELF-HEALING ENGINE ACTIVE...\n"]
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

# --- SIDEBAR: SYSTEM CONTROLS ---
with st.sidebar:
    st.markdown("## 🤖 J.A.R.V.I.S. UPLINK")
    st.caption("Core Engine: Mark X (Self-Healing)")
    ollama_url = st.text_input("Local AI Node URL", value="http://localhost:11434/api/chat", key="mk10_url")
    local_model = st.text_input("Active AI Model", value="qwen2.5-coder:14b", key="mk10_model")
    
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
                threading.Thread(target=bg_parse_file, args=(uploaded_file.name, uploaded_file.read()), daemon=True).start()
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
            
            history_for_api = [{"role": m["role"], "content": m.get("api_prompt", m["content"])} for m in st.session_state.messages[:-1]]
            last_msg = st.session_state.messages[-1]
            history_for_api.append({"role": "user", "content": last_msg.get("api_prompt", last_msg["content"])})
            api_messages = [{"role": "system", "content": system_prompt}] + history_for_api
            
            with st.spinner("J.A.R.V.I.S. is processing telemetry and synthesizing a response..."):
                try:
                    payload = {"model": local_model, "messages": api_messages, "stream": True, "options": {"temperature": 0.1}}
                    response = requests.post(ollama_url, json=payload, stream=True, timeout=60)
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
                    
                    needs_rerun = False
                    
                    # 1. HANDLE WEB SEARCH ROUTINE
                    if web_match and web_enabled and HAS_WEB:
                        query = web_match.group(1).strip()
                        with st.status(f"🌐 Accessing web network for: {query}...", expanded=True) as search_status:
                            search_data = robust_web_search(query)
                            
                            if "Search failed" not in search_data:
                                search_status.update(label=f"Data Retrieval Complete: {query}", state="complete", expanded=False)
                                st.session_state.current_memory_buffer = f"Web Context Loaded: '{query}'"
                            else:
                                search_status.update(label="Uplink Failed (Timed Out)", state="error", expanded=True)
                            
                            web_prompt = f"System Update: The web search for '{query}' returned this data:\n{search_data}\nAnalyze this data, synthesize a response, and proceed with any modifications the user asked for. Remember to output full functional Python code."
    
                            st.session_state.messages.append({"role": "assistant", "content": full_response})
                            st.session_state.messages.append({"role": "user", "content": f"*[Background Web Search Retrieved for '{query}']* \n\nWaiting for analysis...", "api_prompt": web_prompt})
                            needs_rerun = True
                    
                    # 2. HANDLE CODE MODIFICATION & SELF-HEALING ROUTINE
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
                            else:
                                # SELF-HEALING INTERCEPT: Feed the exact traceback back into the cognitive loop!
                                mod_status.update(label=f"Compilation Error Detected - Self-Healing Triggered", state="error", expanded=True)
                                st.error(result)
                                
                                # Push the error back to the model as an urgent directive so it learns and fixes its bug on the fly
                                healing_prompt = f"CRITICAL SYSTEM ERROR: Your previous code modification generated this exception:\n{result}\n\nAnalyze this traceback, find your syntax or logic error, and output a corrected [MODIFY: {feature_name}] block immediately."
                                st.session_state.messages.append({"role": "assistant", "content": full_response})
                                st.session_state.messages.append({"role": "user", "content": f"*[Self-Healing Triggered]*: Fix the error above.", "api_prompt": healing_prompt})
                                needs_rerun = True
                        
                        message_placeholder.markdown(full_response)
                        if not needs_rerun:
                            st.session_state.messages.append({"role": "assistant", "content": full_response})
                        needs_rerun = True

                    if needs_rerun:
                        st.rerun()
                    else:
                        st.session_state.messages.append({"role": "assistant", "content": full_response})
                        st.rerun() 
                        
                except requests.exceptions.RequestException as e:
                    message_placeholder.error(f"Connection lost to AI Node: {str(e)}")
                    st.stop()