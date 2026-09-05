# 0.5.4.M.4 — personal AI command centre

An always-on assistant that runs on a **free** cloud server and works from
iPhone, iPad, Apple Watch, tablets and PC — one screen, one operator.

**👉 Setting it up for the first time? Follow [SETUP.md](SETUP.md).**

```
jarvis/        core: brain pool, memory, agent loop, tools, missions,
               learning, identity, budget, diagnostics, FastAPI server
web/           the single-screen app (installs to the iPhone home screen)
pc_agent/      optional: links your PC so it can be controlled remotely
discord_bot/   optional: chat and voice calls through Discord
deploy/        one-command installer with free HTTPS
legacy/        the earlier local-only build, kept for reference
```

## What it does

- **Remembers everything** — conversations, decisions and documents, permanently
- **Acts** — 89 tools: files, PC control, smart home, music, web, images, Office
- **Works alone** — missions that run for days, self-study, self-repair
- **Knows you** — profile, face and voice; family get help but never your data
- **Costs nothing** — a pool of free brains that fails over when one is busy

## Free brains (add one or more)

| Provider | Free tier |
|---|---|
| GitHub Models | frontier-class, with any GitHub account |
| Google Gemini | generous daily limits |
| Cerebras | fastest inference |
| Groq | fast; also powers Whisper voice |
| OpenRouter, Mistral | more free models |
| Ollama | your own PC — unlimited fallback |

It uses the best available and switches automatically when one is rate-limited.

## Install

```
curl -fsSL https://raw.githubusercontent.com/originalpineapples22-hub/J.A.R.V.I.S/claude/jarvis-self-learning-pfsxu0/deploy/oracle_setup.sh | bash
```

Core dependencies must succeed; the optional extras (push notifications,
semantic memory, social video, browsing) are best-effort — if one will not
build, the matching feature simply stays off and everything else still runs.

## Run locally instead

```
pip install -r requirements.txt
cp .env.example .env          # add a free key
uvicorn jarvis.server:app --port 8080 --env-file .env
```

## First commands

| Say | It does |
|---|---|
| `system check` | Tests every service and says what to fix |
| `who am I?` | Confirms it knows you |
| `quota status` | Free allowance used today |
| `add Ahmed as family` | Guest link with no access to your data |
| `start a mission to …` | Long job that survives restarts |
| `learn Rust` | Masters a technology permanently |
| `safe mode on` | Blocks self-editing and deletions |

## Safety

Self-modification requires your approval and rolls itself back if verification
fails. Destructive file actions and PC control are owner-only. Background work
is capped so it can never spend the quota you need. Safe mode disables all of
it at once.
