# Deploy 0.5.4.M.4 on Fly.io

Fly is a good fit because it gives the app a **persistent disk**. Most free
hosts wipe the filesystem on every restart — which would erase 0.5.4.M.4's
entire memory. Fly keeps it.

⚠️ **Card note:** Fly changed its plans and may ask for a card to verify your
account, with a small free allowance. If you would rather not give a card at
all, skip to *No-card alternative* at the bottom — you keep every feature.

---

## Step 1 — Install the Fly tool (2 min)

**Windows** — open **PowerShell** (Windows key → type `powershell` → Enter) and paste:
```
iwr https://fly.io/install.ps1 -useb | iex
```
Then **close PowerShell and open it again** so it picks up the new command.

> If you see *"running scripts is disabled on this system"*, run this once and
> then retry the line above:
> ```
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

> If `fly` is still not recognised after reopening PowerShell, add it manually:
> ```
> $env:Path += ";$env:USERPROFILE\.fly\bin"
> ```
> (For a permanent fix: Windows key → "environment variables" → Path → New →
> `%USERPROFILE%\.fly\bin`)

**Mac / Linux:**
```
curl -L https://fly.io/install.sh | sh
```

Check it worked:
```
fly version
```

## Step 2 — Sign up (2 min)

```
fly auth signup
```
A browser opens. Sign up with GitHub — quickest. Then back in the terminal:
```
fly auth whoami
```

## Step 3 — Get the code

```
git clone -b claude/jarvis-self-learning-pfsxu0 https://github.com/originalpineapples22-hub/J.A.R.V.I.S.git
cd J.A.R.V.I.S
```

## Step 4 — Create the app (3 min)

```
fly launch --no-deploy
```

Answer the questions like this:

| Question | Answer |
|---|---|
| App name | `mohamed-jarvis` (must be globally unique) |
| Region | pick the closest — **Dubai (dxb)** or **Frankfurt (fra)** for Oman |
| Postgres database? | **No** |
| Redis? | **No** |
| Deploy now? | **No** |
| Overwrite fly.toml? | **No** ← important, keep the one in the repo |

## Step 5 — Create the persistent disk (1 min)

This is what keeps your memory forever:

```
fly volumes create jarvis_data --size 3 --region dxb
```
Use the same region you chose in step 4. 3 GB is plenty.

## Step 6 — Set your secrets (2 min)

Generate an access token and store your free keys. Replace the placeholders:

```
fly secrets set JARVIS_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(18))")
fly secrets set GROQ_API_KEY=gsk_your_groq_key_here
```

On Windows PowerShell, generate the token separately:
```
python -c "import secrets;print(secrets.token_urlsafe(18))"
fly secrets set JARVIS_TOKEN=paste_the_output_here
fly secrets set GROQ_API_KEY=gsk_your_groq_key_here
```

**📋 Save that token — it is your password.**
You can see it again later with `fly secrets list` (name only) or set a new one.

## Step 7 — Deploy 🚀

```
fly deploy
```

First build takes 3–5 minutes. When it finishes:

```
fly status          # should show a machine "started"
fly logs            # live logs
```

Your address is: **https://mohamed-jarvis.fly.dev**

## Step 8 — Connect your devices

1. Open the address → ⚙ → paste the **access token** → Save
2. Add your **GitHub Models key** in the same panel → Save
3. Fill in **WHO I AM** → Save
4. iPhone: Safari → Share → **Add to Home Screen** → open it → ⚙ → paste token
   → **Enable notifications**
5. Type **`system check`** — it tests everything and tells you what works

---

## Everyday commands

```
fly logs                 # what it is doing right now
fly status               # is it alive
fly apps restart mohamed-jarvis
fly ssh console          # a shell inside the machine
fly secrets set KEY=val  # add or change a key (restarts automatically)
```

**Updating to my newest code:**
```
cd J.A.R.V.I.S
git pull
fly deploy
```

---

## Cost control

`fly.toml` keeps **one machine always awake** so reminders, the morning
briefing and background missions still run while you are away.

If you want to minimise usage instead, edit `fly.toml`:
```
auto_stop_machines = "stop"
min_machines_running = 0
```
It then sleeps when idle and wakes in a few seconds when you open it — but
**proactive features pause while it sleeps**. Your choice.

Check usage any time: `fly dashboard`

---

## No-card alternative — Cloudflare Tunnel

Genuinely free, no card, no server. Runs on your own PC and gives you a real
HTTPS address reachable from your phone anywhere.

The only trade-off: it works while your PC is on.

```
# 1. run 0.5.4.M.4 locally
pip install -r requirements.txt
python -m uvicorn jarvis.server:app --port 8080

# 2. in a second terminal, expose it (installs from cloudflare.com/products/tunnel)
cloudflared tunnel --url http://localhost:8080
```

It prints a public `https://something.trycloudflare.com` address. Open that on
your phone, paste your token, and everything works — voice, camera,
notifications — because it is real HTTPS.

Ask me and I will write you a one-click launcher for this.
