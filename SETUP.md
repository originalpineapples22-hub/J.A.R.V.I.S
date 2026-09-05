# 0.5.4.M.4 — Step-by-step setup

Everything here is **free**. No card is charged. Total time ≈ 40 minutes,
most of it waiting.

Do the parts in order. If a step goes wrong, stop and ask — don't skip it.

---

## PART 1 — Get two free keys (10 min)

### 1.1 Groq key (the brain + voice)
1. Go to **console.groq.com** → sign in with Google or GitHub
2. Left menu → **API Keys** → **Create API Key**
3. Name it `jarvis` → **Submit**
4. **Copy it now** (it starts with `gsk_`) — it is shown only once
5. Paste it somewhere safe for a moment (Notes app)

### 1.2 GitHub key (a second, stronger brain)
1. Go to **github.com/settings/tokens**
2. **Generate new token** → **Generate new token (classic)**
3. Note: `jarvis`. Expiration: **No expiration**
4. Tick **nothing** — no permissions needed
5. **Generate token** → copy it (starts with `ghp_`)

> You now have 2 keys saved. Keep them private — they are like passwords.

---

## PART 2 — Free web address (5 min)

Needed because iPhone requires HTTPS for the app and notifications.

1. Go to **duckdns.org** → sign in with Google/GitHub
2. In the **domain** box type a name, e.g. `mohamedjarvis` → **add domain**
3. Copy the **token** shown at the top of the page
4. Note your address: `mohamedjarvis.duckdns.org`

> Save: the subdomain name + the DuckDNS token.

---

## PART 3 — Free 24/7 server (20 min)

### 3.1 Create the account
1. Go to **cloud.oracle.com** → **Start for free**
2. Choose country **Oman**, fill your details
3. It asks for a **card — for identity only**. Always Free resources are
   never charged. A debit card works.
4. Choose the home region **closest to Oman** (e.g. Jeddah or Dubai).
   ⚠️ This cannot be changed later.
5. Wait for the confirmation email (5–15 min)

### 3.2 Create the machine
1. Sign in → menu (☰) → **Compute** → **Instances** → **Create instance**
2. Name: `jarvis`
3. **Image and shape** → **Change image** → **Canonical Ubuntu 22.04** → Select
4. **Change shape** → **Ampere** → `VM.Standard.A1.Flex`
   → set **4 OCPUs** and **24 GB memory** (all free)
   - If it says *"out of capacity"*, either try again later, or pick
     **Specialty and previous generation → VM.Standard.E2.1.Micro** (also free)
5. **Add SSH keys** → **Generate a key pair for me** →
   **Download private key** (keep this file safe — it is your door key)
6. **Create**. Wait until the state is green **RUNNING**
7. **Copy the Public IP address** shown on the page

### 3.3 Open the doors (ports)
1. On the instance page click the **Subnet** link
2. Click the **Default Security List**
3. **Add Ingress Rules** → add these two, one at a time:
   - Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination Port **80**
   - Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination Port **443**
4. Save

### 3.4 Connect to the machine
On your PC, open **Command Prompt** and run (replace with your file and IP):

```
cd Downloads
icacls ssh-key.key /inheritance:r /grant:r "%USERNAME%":R
ssh -i ssh-key.key ubuntu@YOUR_PUBLIC_IP
```

Type `yes` if it asks about fingerprints. You are now on the server.

---

## PART 4 — Install 0.5.4.M.4 (5 min)

Paste this **one line** into that SSH window:

```
curl -fsSL https://raw.githubusercontent.com/originalpineapples22-hub/J.A.R.V.I.S/claude/jarvis-self-learning-pfsxu0/deploy/oracle_setup.sh | bash
```

It will ask you for:
1. **Groq API key** → paste the `gsk_...` key
2. **DuckDNS subdomain** → e.g. `mohamedjarvis` (no `.duckdns.org`)
3. **DuckDNS token** → paste it

Then it installs everything and prints:

```
Your operator access token is: XXXXXXXXXXXX
==> J.A.R.V.I.S. is live at https://mohamedjarvis.duckdns.org
```

**📋 COPY THAT ACCESS TOKEN.** It is your password to your own AI.
(You can see it again later with: `cat ~/jarvis/.env`)

---

## PART 5 — Connect your devices (5 min)

### On your PC
1. Open `https://mohamedjarvis.duckdns.org`
2. Settings (⚙) → paste the **access token** → **Save**
3. Paste the **GitHub key** into *GitHub Models key* → **Save**
4. Fill **WHO I AM**: your name, what to call you, location → **Save**

### On iPhone / iPad
1. Open the same address in **Safari**
2. **Share** → **Add to Home Screen** → you now have an app icon
3. Open it → ⚙ → paste the token → Save
4. ⚙ → **Enable notifications on this device**

### On Apple Watch
1. iPhone → **Shortcuts** app → **+**
2. Add **Dictate Text**
3. Add **Get Contents of URL** →
   `https://mohamedjarvis.duckdns.org/api/ask?token=YOUR_TOKEN&q=` + *Dictated Text*
4. Add **Speak Text** → Contents of URL
5. Name it **Jarvis** → then say *"Hey Siri, Jarvis"*

---

## PART 6 — First 10 minutes with it

Type these, in order:

1. `system check` → it tests every service and tells you what works
2. `who am I?` → confirms it knows you
3. `what's the weather in Muscat?` → a real live answer
4. `remind me in 2 minutes to test notifications` → check your phone buzzes
5. Settings → **Enrol my voice** (10 seconds)
6. `make me a PowerPoint about Oman` → download it from Files

**Leave these OFF for the first few days:** autonomous study and long missions.
Let the basics prove themselves first. Turn study on later with
`start self-study`.

---

## Everyday commands

| Say | It does |
|---|---|
| `system check` | Tests everything, tells you what's broken and how to fix |
| `quota status` | How much free allowance is left today |
| `add Ahmed as family` | Creates a guest link for a family member |
| `household activity` | Who used it and when |
| `start a mission to …` | Long job that runs for hours/days |
| `mission status` | Progress on long jobs |
| `learn Rust` | Masters a technology permanently |
| `safe mode on` | Blocks self-editing and deletions |

---

## If something breaks

**Site won't load** → on the server: `sudo systemctl status jarvis`
Restart with: `sudo systemctl restart jarvis`

**See the error log** → `journalctl -u jarvis -n 50 --no-pager`

**Update to my latest code** →
```
cd ~/jarvis && git pull && sudo systemctl restart jarvis
```

**Forgot the token** → `cat ~/jarvis/.env`

**Anything else** → run `system check` and send me what it says.
