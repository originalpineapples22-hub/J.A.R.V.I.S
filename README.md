# J.A.R.V.I.S. v3 — cloud command center

Always-on personal AI that runs on a free cloud server and works on iPhone, iPad,
Apple Watch (via Siri Shortcut + mirrored notifications), tablets and PC — one screen.

```
jarvis/        the core: brain (Groq/OpenAI/Ollama), memory (SQLite+FTS), agent loop,
               tool plugins, parallel learning, push notifications, scheduler, FastAPI server
web/           the single-screen PWA (install to Home Screen on iPhone/iPad)
pc_agent/      tiny program for your PC: lets the cloud JARVIS control the PC and
               adds the offline Whisper always-on ear
deploy/        one-shot Oracle Cloud (Always Free) installer with HTTPS
legacy/        the previous local-only build (kept for reference)
```

## Deploy (free, ~15 minutes)
1. Create an Oracle Cloud Always-Free account and an Ubuntu VM (Ampere A1 or Micro).
   In the VM's VCN security list, open TCP ports 80 and 443.
2. Get a free DuckDNS subdomain at duckdns.org (gives you HTTPS, required by iPhone for
   Home-Screen apps and notifications).
3. SSH into the VM and run:
   `curl -fsSL https://raw.githubusercontent.com/originalpineapples22-hub/J.A.R.V.I.S/claude/jarvis-self-learning-pfsxu0/deploy/oracle_setup.sh | bash`
   It asks for your Groq key and DuckDNS details, prints your **access token**, and
   brings JARVIS up at `https://<name>.duckdns.org`.
4. On each device: open the URL → Settings (⚙) → paste the token → Save.
   iPhone/iPad: Share → **Add to Home Screen**, then ⚙ → *Enable notifications*.
5. Apple Watch: Shortcuts app → new shortcut: **Dictate Text** → **Get Contents of URL**
   `https://<name>.duckdns.org/api/ask?token=<TOKEN>&q=<Dictated Text>` → **Speak Text**.
   Name it "Jarvis". Raise wrist: "Hey Siri, Jarvis".

## Run locally (for development)
```
pip install -r requirements.txt
cp .env.example .env   # add your Groq key
uvicorn jarvis.server:app --port 8080 --env-file .env
```

## PC agent (optional)
`pip install websockets` then `python pc_agent/agent.py` — first run creates
`pc_agent/config.json`; fill in your server URL (`wss://<name>.duckdns.org/ws/pc`) and token.
Add `pip install SpeechRecognition pyaudio faster-whisper numpy pyttsx3` for the always-on ear.

## Talking to it
- Type or tap the mic. On a PC browser, tick **Always listen** for the wake word "Jarvis".
- "learn Rust" / "study docker" → 10-module mastery curriculum in ~2 minutes, permanent.
- "remind me in 20 minutes to …" → notification on all your devices.
- Share a YouTube link to the app → "what is this video about?"
- "make me a python script that …" → file appears in Files, sandbox-tested.
