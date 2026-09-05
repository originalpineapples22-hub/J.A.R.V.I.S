# -*- coding: utf-8 -*-
"""FastAPI server: the single-screen PWA, streaming chat (WebSocket), REST for panels,
push notifications, PC-agent relay, Siri-friendly plain-text endpoint."""
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request, Query, UploadFile, File
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import httpx
from . import __version__, memory, agent, brain, learning, speech, curriculum, selfdev, rag, missions, idle, budget, doctor, identity
from .config import load_settings, save_settings, operator_token, ROOT, FILES_DIR, DEFAULTS
from .push import vapid_keys, notify_all
from .scheduler import loop as scheduler_loop
from .tools import agents_status
from . import connectors
from .tools.system import system_metrics, local_now
from .tools.files import list_files
from .tools import pc as pc_tools

WEB = ROOT / "web"
app = FastAPI(title="J.A.R.V.I.S.", version=__version__)


def auth(request: Request, token: str = Query(default=None)):
    tok = request.headers.get("X-JARVIS-TOKEN") or token
    if tok != operator_token():
        raise HTTPException(401, "Access denied, sir.")
    return True


@app.on_event("startup")
async def _startup():
    memory.db()
    asyncio.get_event_loop().create_task(scheduler_loop())
    asyncio.get_event_loop().create_task(curriculum.autonomous_loop())
    asyncio.get_event_loop().create_task(missions.resume_all())
    asyncio.get_event_loop().create_task(idle.loop())
    memory.add_event("system", f"J.A.R.V.I.S. core v{__version__} online")


# ---------------- PWA
@app.get("/")
async def index():
    return FileResponse(WEB / "index.html")


@app.get("/sw.js")
async def sw():
    return FileResponse(WEB / "sw.js", media_type="application/javascript")


@app.get("/manifest.json")
async def manifest():
    return FileResponse(WEB / "manifest.json", media_type="application/manifest+json")


# ---------------- status for panels
@app.get("/api/health")
async def health():
    return {"status": "online", "version": __version__, "time": local_now().isoformat()}


@app.get("/api/status", dependencies=[Depends(auth)])
async def status():
    s = load_settings()
    prov = await brain.provider_status(s)
    return {
        "version": __version__,
        "name": s.get("assistant_name", "J.A.R.V.I.S."),
        "time": local_now().strftime("%H:%M:%S"),
        "date": local_now().strftime("%A, %d %B %Y"),
        "system": system_metrics(),
        "memory": memory.stats(),
        "skills": memory.skills()[:12],
        "agents": agents_status(),
        "events": memory.events(8),
        "tasks": memory.tasks()[:8],
        "reminders": memory.upcoming_reminders(6),
        "providers": prov,
        "learning": learning.status(),
        "pc_online": pc_tools.pc_connected(),
        "files": list_files()[:8],
        "push_subs": len(memory.push_subs()),
        "capability": connectors.status(),
        "curriculum": curriculum.auto_state(),
        "rag": {"available": rag.available(), "backend": rag.backend_name()},
        "missions": missions.all_missions(),
        "idle": idle.state(),
        "budget": budget.status(),
        "identity": identity.status(),
        "preview": __import__("jarvis.tools.preview", fromlist=["latest"]).latest(),
    }


@app.get("/api/history", dependencies=[Depends(auth)])
async def history(channel: str = "web", n: int = 30):
    return memory.recent_messages(channel, n)


# ---------------- chat
@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    if ws.query_params.get("token") != operator_token():
        await ws.send_text(json.dumps({"type": "error", "text": "Access denied, sir."}))
        await ws.close()
        return
    try:
        while True:
            data = json.loads(await ws.receive_text())
            text = str(data.get("text", "")).strip()
            if not text:
                continue
            async for ev in agent.run(text, channel=data.get("channel", "web")):
                await ws.send_text(json.dumps(ev))
    except WebSocketDisconnect:
        pass


@app.post("/api/chat", dependencies=[Depends(auth)])
async def chat(req: Request):
    data = await req.json()
    final = ""
    async for ev in agent.run(str(data.get("text", "")), channel=data.get("channel", "api")):
        if ev["type"] == "final":
            final = ev["text"]
        elif ev["type"] == "error":
            final = ev["text"]
    return {"reply": final}


@app.get("/api/ask", response_class=PlainTextResponse, dependencies=[Depends(auth)])
async def ask(q: str = ""):
    """Plain-text reply for Siri Shortcuts / Apple Watch."""
    final = "Yes, sir?"
    if q.strip():
        async for ev in agent.run(q, channel="siri"):
            if ev["type"] in ("final", "error"):
                final = ev["text"]
    return final


# ---------------- tasks / files / settings / learning
@app.post("/api/tasks", dependencies=[Depends(auth)])
async def add_task(req: Request):
    d = await req.json()
    memory.add_task(d.get("title", ""), d.get("due"))
    return {"ok": True}


@app.post("/api/tasks/{tid}/done", dependencies=[Depends(auth)])
async def done_task(tid: int):
    memory.complete_task(tid)
    return {"ok": True}


@app.get("/api/files/{name}", dependencies=[Depends(auth)])
async def get_file(name: str):
    p = FILES_DIR / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, filename=p.name)


@app.get("/api/settings", dependencies=[Depends(auth)])
async def get_settings():
    s = load_settings()
    masked = dict(s)
    for k in ("groq_api_key", "openai_api_key"):
        if masked.get(k):
            masked[k] = masked[k][:6] + "…"
    masked["groq_models"] = await brain.groq_models(s.get("groq_api_key"))
    return masked


@app.post("/api/settings", dependencies=[Depends(auth)])
async def post_settings(req: Request):
    d = await req.json()
    d = {k: v for k, v in d.items() if k in DEFAULTS and not (isinstance(v, str) and v.endswith("…"))}
    save_settings(d)
    return {"ok": True}


@app.post("/api/learn", dependencies=[Depends(auth)])
async def learn(req: Request):
    d = await req.json()
    return {"started": learning.start_study(d.get("topic", "").strip())}


@app.post("/api/transcribe", dependencies=[Depends(auth)])
async def transcribe(file: UploadFile = File(...)):
    """Accurate speech-to-text via Whisper (Groq). Far fewer invented words
    than the browser recogniser, and it returns empty for silence/noise."""
    data = await file.read()
    text = await speech.transcribe(data, file.filename or "audio.webm")
    return {"text": text}


@app.get("/api/tts", dependencies=[Depends(auth)])
async def tts(text: str = "", voice: str = ""):
    audio = await speech.synthesize(text, voice)
    if not audio:
        raise HTTPException(503, "TTS unavailable")
    from fastapi.responses import Response
    return Response(content=audio, media_type="audio/mpeg")


@app.get("/preview/{name}")
async def preview_file(name: str):
    """Served without a token so the dashboard iframe can render it; the file
    names are unguessable-by-design content the operator just created."""
    from .tools.preview import PREVIEW_DIR
    p = PREVIEW_DIR / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="text/html")


@app.get("/api/identity", dependencies=[Depends(auth)])
async def api_identity():
    return identity.status()


@app.post("/api/identity/enrol", dependencies=[Depends(auth)])
async def api_enrol(req: Request):
    d = await req.json()
    kind = d.get("kind", "face")
    vec = d.get("vector") or []
    if kind not in ("face", "voice") or not isinstance(vec, list) or len(vec) < 8:
        raise HTTPException(400, "Bad enrolment data")
    return {"message": identity.enrol(kind, vec)}


@app.post("/api/identity/verify", dependencies=[Depends(auth)])
async def api_verify(req: Request):
    d = await req.json()
    kind = d.get("kind", "face")
    vec = d.get("vector") or []
    if not isinstance(vec, list) or len(vec) < 8:
        raise HTTPException(400, "Bad sample")
    res = identity.verify(kind, vec)
    if res.get("enrolled"):
        memory.add_event("system", f"{kind.title()} check: {'operator recognised' if res['known'] else 'UNKNOWN PERSON'} ({res['score']})")
    return res


@app.post("/api/identity/profile", dependencies=[Depends(auth)])
async def api_profile(req: Request):
    return identity.save_profile(await req.json())


@app.get("/api/doctor", dependencies=[Depends(auth)])
async def api_doctor(quick: bool = False):
    return await doctor.run_all(quick=quick)


@app.get("/api/connectors", dependencies=[Depends(auth)])
async def get_connectors():
    return connectors.status()


@app.get("/api/knowledge", dependencies=[Depends(auth)])
async def knowledge(topic: str = None):
    return memory.lessons(topic)


# ---------------- push
@app.get("/api/push/vapid", dependencies=[Depends(auth)])
async def push_vapid():
    return {"public": vapid_keys().get("public", "")}


@app.post("/api/push/subscribe", dependencies=[Depends(auth)])
async def push_subscribe(req: Request):
    memory.add_push_sub(await req.json())
    return {"ok": True}


@app.post("/api/push/test", dependencies=[Depends(auth)])
async def push_test():
    n = await notify_all("J.A.R.V.I.S.", "Push channel confirmed, sir. I can reach this device.")
    return {"sent": n}


# ---------------- PC agent relay
@app.websocket("/ws/pc")
async def ws_pc(ws: WebSocket):
    await ws.accept()
    if ws.query_params.get("token") != operator_token():
        await ws.close()
        return
    pc_tools.set_pc_socket(ws)
    memory.add_event("system", "PC agent connected")
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "heard":
                # the PC's Whisper ear heard a command: run it through the agent and answer
                final = ""
                async for ev in agent.run(msg.get("text", ""), channel="pc"):
                    if ev["type"] in ("final", "error"):
                        final = ev["text"]
                await ws.send_text(json.dumps({"type": "speak", "text": final}))
            else:
                pc_tools.resolve_pc_reply(msg)
    except WebSocketDisconnect:
        pass
    finally:
        pc_tools.set_pc_socket(None)
        memory.add_event("system", "PC agent disconnected")


app.mount("/static", StaticFiles(directory=str(WEB)), name="static")
