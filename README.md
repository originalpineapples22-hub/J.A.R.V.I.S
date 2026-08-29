# J.A.R.V.I.S. Core — Mark XI (Self-Learning)

A local, Iron-Man-style AI assistant HUD built with Streamlit, powered by a local
Ollama model (default: `qwen2.5-coder:14b`). It can search the web, modify its own
source code with a self-healing loop, and — new in Mark XI — **teach itself
programming languages and technologies and remember them permanently**.

## Setup

```bash
pip install -r requirements.txt
ollama pull qwen2.5-coder:14b   # or any model you prefer
streamlit run jarvis.py
```

Make sure Ollama is running (`ollama serve`, default URL `http://localhost:11434`).

## Self-Learning: how it works

JARVIS has a persistent **knowledge base** stored in `jarvis_knowledge/` (one JSON
file per topic) plus a **skill matrix** (`_skill_matrix.json`) tracking proficiency
levels: UNTRAINED → NOVICE → APPRENTICE → ADEPT → EXPERT → MASTER, based on how
many lessons it has learned. Everything survives restarts.

### Ways to make it learn

1. **Chat command** — tell JARVIS `study Rust` (or "learn Docker", "master Go").
   The model outputs a `[STUDY: Rust]` tag and the backend runs an autonomous
   curriculum loop:
   - For each of 5 curriculum modules (syntax → control flow → data structures →
     idioms → ecosystem), it web-searches the module, feeds the research back to
     the model, and the model writes a detailed lesson in a
     `[LEARN: topic | lesson]...[/LEARN]` block.
   - Each lesson is saved to disk and the skill matrix is updated.
   - A progress bar in the sidebar tracks the session.

2. **Sidebar "Direct Study Order"** — type a topic and hit
   **INITIATE STUDY PROTOCOL** to skip the chat round-trip.

3. **Spontaneous learning** — the model can emit `[LEARN: ...]` blocks any time it
   synthesizes something worth remembering.

### Recall

When you send a prompt, JARVIS keyword-matches it against learned topics and
injects the relevant notes into the model's context as `[RECALLED KNOWLEDGE]`.
The system prompt also always lists the current skill matrix, so JARVIS knows
what it knows.

You can browse or delete learned topics from the sidebar (**Browse Knowledge
Base** / **Forget**).

## Other systems (from Mark X)

- **Self-healing code modification** — `[MODIFY: feature]` blocks are injected at
  the `# --- DASHBOARD_ANCHOR ---` in `jarvis.py`, syntax-checked before deploy,
  snapshotted to `jarvis_backups/`, and compile errors are fed back to the model
  to fix itself. Rollback from the sidebar.
- **Web access** — DuckDuckGo with Wikipedia fallback, autonomous via
  `[WEB_SEARCH: query]` or manual from the sidebar.
- **File ingestion** — upload txt/py/md/json/pdf/xlsx/exe files into context.
- **Live telemetry** — CPU/RAM/disk HUD refreshing every 2 seconds.

## Files created at runtime

| Path | Purpose |
|---|---|
| `jarvis_knowledge/` | Learned lessons (one JSON per topic) + skill matrix |
| `jarvis_backups/` | Snapshots taken before every self-modification |
| `jarvis_audit.json` | Audit log of self-modification attempts |
