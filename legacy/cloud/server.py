# -*- coding: utf-8 -*-
"""
J.A.R.V.I.S. CLOUD — a small always-on server so you can talk to JARVIS from
your iPhone (web app) and Apple Watch (Siri Shortcut) even when your PC is off.

Runs on a free host (Render / Railway / Fly.io). Free servers have no GPU, so
this uses a FREE hosted AI API instead of your local Qwen model:
  - Groq (free tier, very fast):  set GROQ_API_KEY
  - or your own Ollama exposed over the internet: set OLLAMA_URL + OLLAMA_MODEL

Security: every request must carry your secret token (JARVIS_TOKEN env var),
so nobody else can use your JARVIS.

Endpoints
  GET  /                 -> mobile web app (tap to talk, spoken replies)
  POST /ask   {text}     -> {reply}          (header X-JARVIS-TOKEN or ?token=)
  GET  /ask?q=..&token=  -> plain text reply (for Apple Watch / Siri Shortcuts)
  GET  /health
"""
import os
import requests
from flask import Flask, request, jsonify, Response, render_template_string

app = Flask(__name__)

JARVIS_TOKEN = os.environ.get("JARVIS_TOKEN", "change-me")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")

PERSONA = (
    "You are J.A.R.V.I.S., a calm, articulate British AI with dry wit. "
    "You address the operator as 'sir'. Keep spoken replies concise (1-3 sentences) "
    "unless asked for detail. Offer subtle, respectful pushback on risky ideas."
)

_history = []


def think(text: str) -> str:
    global _history
    messages = [{"role": "system", "content": PERSONA}] + _history[-8:] + [{"role": "user", "content": text}]
    try:
        if GROQ_API_KEY:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={"model": GROQ_MODEL, "messages": messages, "temperature": 0.4},
                timeout=60,
            )
            r.raise_for_status()
            reply = r.json()["choices"][0]["message"]["content"].strip()
        elif OLLAMA_URL:
            r = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "messages": messages, "stream": False}, timeout=120)
            r.raise_for_status()
            reply = r.json().get("message", {}).get("content", "").strip()
        else:
            reply = "No AI provider configured, sir. Set GROQ_API_KEY or OLLAMA_URL on the server."
    except Exception as e:
        reply = f"My cognitive core is unreachable, sir. ({e})"
    _history += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
    return reply or "I have no answer, sir."


def authorized() -> bool:
    token = request.headers.get("X-JARVIS-TOKEN") or request.args.get("token")
    if not token and request.is_json:
        token = (request.get_json(silent=True) or {}).get("token")
    return bool(token) and token == JARVIS_TOKEN


MOBILE_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>J.A.R.V.I.S.</title>
<style>
 body{margin:0;background:#01040d;color:#7fd4de;font-family:-apple-system,system-ui,sans-serif;display:flex;flex-direction:column;align-items:center;min-height:100vh;padding:24px 16px;box-sizing:border-box}
 h1{color:#00f0ff;letter-spacing:6px;font-size:22px;text-shadow:0 0 12px rgba(0,240,255,.8);margin:12px 0 4px}
 .sub{font-size:11px;letter-spacing:3px;color:#5fb3bd;margin-bottom:22px}
 #btn{width:180px;height:180px;border-radius:50%;border:3px solid #00f0ff;background:radial-gradient(circle,#0a3a44,#01040d 70%);color:#00f0ff;font-size:16px;letter-spacing:2px;box-shadow:0 0 30px rgba(0,240,255,.5);transition:all .2s}
 #btn.live{background:radial-gradient(circle,#00f0ff,#01040d 70%);color:#01040d;box-shadow:0 0 60px rgba(0,240,255,1)}
 #log{width:100%;max-width:520px;margin-top:22px}
 #log div{border-left:2px solid #00f0ff;padding:6px 10px;margin:6px 0;background:rgba(0,240,255,.05);font-size:14px;line-height:1.4}
 #log b{color:#00f0ff}
 input{width:100%;max-width:520px;margin-top:14px;padding:12px;background:#010409;border:1px solid #00f0ff;color:#00f0ff;border-radius:4px;font-size:16px}
 .tok{margin-top:10px;font-size:12px}
</style></head><body>
<h1>J.A.R.V.I.S.</h1><div class="sub">MOBILE UPLINK</div>
<button id="btn">TAP TO SPEAK</button>
<input id="txt" placeholder="...or type here and press Enter">
<div class="tok">Access token: <input id="tok" type="password" style="width:200px;display:inline;margin:0;padding:6px;font-size:13px" placeholder="your JARVIS_TOKEN"></div>
<div id="log"></div>
<script>
const log=document.getElementById('log'),btn=document.getElementById('btn'),txt=document.getElementById('txt'),tok=document.getElementById('tok');
tok.value=localStorage.getItem('jarvis_token')||''; tok.onchange=()=>localStorage.setItem('jarvis_token',tok.value);
function add(w,t){const d=document.createElement('div');d.innerHTML='<b>'+w+'</b> '+t;log.prepend(d);}
function speak(t){try{const u=new SpeechSynthesisUtterance(t);u.rate=1.02;const vs=speechSynthesis.getVoices();const p=vs.find(v=>/en-GB/i.test(v.lang))||vs.find(v=>/^en/i.test(v.lang));if(p)u.voice=p;speechSynthesis.cancel();speechSynthesis.speak(u);}catch(e){}}
async function ask(q){add('YOU',q);try{const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json','X-JARVIS-TOKEN':tok.value},body:JSON.stringify({text:q})});const j=await r.json();const rep=j.reply||j.error||'No response, sir.';add('J.A.R.V.I.S.',rep);speak(rep);}catch(e){add('SYSTEM','Uplink failed: '+e);}}
txt.onkeydown=e=>{if(e.key==='Enter'&&txt.value.trim()){ask(txt.value.trim());txt.value='';}};
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(SR){const rec=new SR();rec.lang='en-US';rec.interimResults=false;
 rec.onresult=e=>{ask(e.results[0][0].transcript);};rec.onend=()=>btn.classList.remove('live');
 btn.onclick=()=>{speechSynthesis.cancel();btn.classList.add('live');try{rec.start();}catch(e){}};}
else{btn.onclick=()=>add('SYSTEM','Voice not supported in this browser — type instead.');}
</script></body></html>"""


@app.route("/")
def home():
    return render_template_string(MOBILE_PAGE)


@app.route("/health")
def health():
    return jsonify({"status": "online", "provider": "groq" if GROQ_API_KEY else ("ollama" if OLLAMA_URL else "none")})


@app.route("/ask", methods=["GET", "POST"])
def ask():
    if not authorized():
        if request.method == "GET":
            return Response("Access denied, sir.", mimetype="text/plain", status=401)
        return jsonify({"error": "Access denied, sir."}), 401
    if request.method == "GET":
        q = (request.args.get("q") or "").strip()
        return Response(think(q) if q else "Yes, sir?", mimetype="text/plain")
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    return jsonify({"reply": think(text) if text else "Yes, sir?"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
