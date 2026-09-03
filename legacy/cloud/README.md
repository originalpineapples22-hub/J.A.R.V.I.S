# J.A.R.V.I.S. Cloud — iPhone & Apple Watch access (PC can be off)

Free servers have no GPU, so the cloud copy uses a **free hosted AI API**
(Groq) instead of the local Qwen model. It keeps JARVIS's persona; it does
not share the PC's learned knowledge base or control the PC.

## 1. Get a free AI key
Create a free account at https://console.groq.com and make an API key.

## 2. Deploy for free on Render
1. Push this repo to GitHub (already done).
2. Go to https://render.com → New → **Blueprint** → pick this repo.
   Render reads `cloud/render.yaml` automatically.
3. When asked for environment variables:
   - `JARVIS_TOKEN` → invent a long secret password (this locks JARVIS to you)
   - `GROQ_API_KEY` → paste your Groq key
4. Deploy. You get a URL like `https://jarvis-cloud.onrender.com`.

(Free Render services sleep after 15 min idle and take ~30s to wake on the
first request. That's the free-tier trade-off.)

## 3. iPhone
Open the URL in Safari → Share → **Add to Home Screen**. You now have a
JARVIS app icon. Open it, paste your token once, tap the reactor button,
speak, and JARVIS answers out loud.

## 4. Apple Watch (via Siri Shortcut)
On iPhone, open **Shortcuts** → + → add these actions:
1. **Dictate Text**
2. **Get Contents of URL** →
   `https://YOUR-URL/ask?token=YOUR_TOKEN&q=` + (Dictated Text)  — method GET
3. **Speak Text** → (Contents of URL)

Name it **"Jarvis"**. It syncs to the Watch automatically. Raise your wrist:
"Hey Siri, Jarvis" → dictate → JARVIS speaks the reply from your watch.
