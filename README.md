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
- **Costs nothing** — your own machine first, one free key as backup, no paid AI anywhere

## One brain, not a pool

Earlier versions tried six different companies' AIs in turn. That is not
independence, just more companies to depend on — so it was cut down to
exactly two, deliberately:

1. **Your own machine.** Install it once:

   ```
   .\deploy\local_brain.ps1        # Windows      ./deploy/local_brain.sh on Mac/Linux
   ```

   It sizes a model to your hardware, installs it, and makes it first choice.
   No key, no quota, no account, works offline, and no company can retire it
   out from under you.

2. **Google Gemini**, free, kept only as backup for when your PC is off — the
   one exception, because "no PC needed, always on" was asked for too, and a
   local model alone can't deliver that. Add a key at aistudio.google.com/apikey
   if you want it; skip it and the assistant simply waits for your PC.

Nothing else is contacted, ever. Ask it "which brain are you using?" and it
answers honestly. A Gemini model that gets retired is replaced automatically
from whatever Google currently serves — no manual fix needed.

Groq stays as a separate, optional key purely for voice transcription
(Whisper) — unrelated to which brain answers you.

## Install

```
curl -fsSL https://raw.githubusercontent.com/originalpineapples22-hub/J.A.R.V.I.S/claude/jarvis-self-learning-pfsxu0/deploy/oracle_setup.sh | bash
```

Core dependencies must succeed; the optional extras (push notifications,
semantic memory, social video, browsing) are best-effort — if one will not
build, the matching feature simply stays off and everything else still runs.

## Run locally instead

**Windows** — double-click **`BOOT.bat`**. It opens both windows for you: the
core, and the tunnel that gives you a public HTTPS address for your phone.
Leave both open; closing either takes it offline.

**Mac / Linux** — `./start.sh`, then `./tunnel.sh` in a second terminal.

To run the core alone, without publishing it: `.\start.ps1` / `./start.sh`.

Either one sets up its own Python environment, installs what is missing, prints
your access token and opens on <http://localhost:8080>. To reach it from your
phone, run `tunnel.ps1` / `tunnel.sh` in a second window — it fetches
cloudflared itself and prints a public HTTPS address. By hand:

```
pip install -r requirements.txt
cp .env.example .env          # add a free key
uvicorn jarvis.server:app --port 8080 --env-file .env
```

> **`Could not import module "jarvis.server"`** means Python is not looking at
> this code. Almost always one of: you are in the older Streamlit build (the
> giveaway is a wall of `missing ScriptRunContext` warnings), or a stray
> `jarvis.py` next to the `jarvis/` folder is hiding the package. The launchers
> check both and tell you which.

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
