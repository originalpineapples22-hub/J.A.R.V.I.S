# -*- coding: utf-8 -*-
"""
J.A.R.V.I.S. EAR + BRIDGE  —  python jarvis_voice.py

One process, two jobs:

  🎙️ THE EAR (always-on, offline)
     Listens on the PC microphone 24/7 and transcribes locally with Whisper
     (faster-whisper). It only acts after the wake word "Jarvis" (fuzzy:
     "Javis", "Jervis"... also count), so speech aimed at other people is
     ignored. No browser permission games, no internet needed for hearing.

  🔗 THE BRIDGE (http://localhost:8765)
     The HUD polls it for what the ear heard and what J.A.R.V.I.S. replied,
     then speaks the reply through the browser. Endpoints:
       GET  /health          GET /ear           GET /events?since=<id>
       POST /ask {text}      (typed commands from the HUD or any app)

Fallbacks (automatic):
  - faster-whisper missing  -> Google web recognizer (needs internet)
  - microphone/module missing -> ear disabled, bridge still runs
  - settings "pc_voice": true -> replies are ALSO spoken via PC speakers,
    so J.A.R.V.I.S. answers even with the HUD closed.
"""
import sys
import json
import time
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from jarvis_core import (
    PERSONA, parse_local_command, chat_once, load_settings, brain_label,
    tts_speak, clean_for_speech, HAS_TTS, execute_pc_tags, extract_wake_command,
    remember_exchange, recall_memory,
)

PORT = 8765
_history = []
_events = []          # {"id","ts","heard","reply"}
_lock = threading.Lock()
_ear = {"status": "starting", "engine": "none", "last_heard": "", "listening": False}
_mute_until = 0.0     # ignore the mic briefly while J.A.R.V.I.S. is speaking (no self-echo)


# ------------------------------------------------------------------ brain
def handle_text(text: str, source: str = "hud") -> str:
    global _history
    text = text.strip()
    if not text:
        return "Yes, sir?"
    settings = load_settings()          # re-read so HUD changes apply instantly
    try:
        direct = parse_local_command(text, settings)
    except Exception as e:
        direct = f"Command engine error: {e}"
    if direct:
        reply = direct
    else:
        memory = recall_memory(text)
        sys_prompt = PERSONA + (f"\n\nRELEVANT PAST CONVERSATIONS (your own memory):\n{memory}" if memory else "")
        messages = [{"role": "system", "content": sys_prompt}] + _history[-8:] + [{"role": "user", "content": text}]
        try:
            reply = chat_once(messages, settings, temperature=0.4) or "I have no answer, sir."
            reply, _ = execute_pc_tags(reply, settings)
        except Exception as e:
            reply = f"I could not reach my cognitive core, sir. ({e})"
    _history += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
    remember_exchange(text, reply, source)
    print(f"[{source}] {text}\n[jarvis] {reply}\n")
    return reply


def push_event(heard: str, reply: str):
    global _mute_until
    with _lock:
        _events.append({"id": len(_events) + 1, "ts": datetime.now().strftime("%H:%M:%S"),
                        "heard": heard, "reply": reply})
        del _events[:-200]
    # Assume ~14 chars/sec of browser speech; stay deaf meanwhile to avoid hearing ourselves
    _mute_until = time.time() + min(20, 1.0 + len(clean_for_speech(reply)) / 14.0)
    if load_settings().get("pc_voice") and HAS_TTS:
        threading.Thread(target=tts_speak, args=(clean_for_speech(reply),), daemon=True).start()


# ------------------------------------------------------------------ the ear
def ear_loop():
    try:
        import speech_recognition as sr
    except Exception:
        _ear.update(status="mic module missing — pip install SpeechRecognition pyaudio", engine="none")
        return

    whisper = None
    try:
        from faster_whisper import WhisperModel
        import numpy as np
        size = load_settings().get("whisper_model", "base.en")
        _ear.update(status=f"loading whisper ({size})...")
        whisper = WhisperModel(size, device="cpu", compute_type="int8")
        _ear["engine"] = f"whisper {size} (offline)"
    except Exception as e:
        _ear["engine"] = "google web recognizer (install faster-whisper for offline)"
        print(f"[ear] faster-whisper unavailable ({e}); using Google recognizer")

    rec = sr.Recognizer()
    rec.dynamic_energy_threshold = True
    rec.pause_threshold = 0.7
    try:
        mic = sr.Microphone(sample_rate=16000)
        with mic as src:
            rec.adjust_for_ambient_noise(src, duration=1.0)
    except Exception as e:
        _ear.update(status=f"no microphone: {e}")
        return

    def transcribe(audio) -> str:
        if whisper is not None:
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            arr = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
            segments, _ = whisper.transcribe(arr, language="en", beam_size=1, vad_filter=True)
            return " ".join(seg.text for seg in segments).strip()
        try:
            return rec.recognize_google(audio)
        except Exception:
            return ""

    _ear.update(status="listening", listening=True)
    print(f"[ear] online — engine: {_ear['engine']}. Say 'Jarvis, ...'")
    while True:
        try:
            with mic as src:
                audio = rec.listen(src, phrase_time_limit=8)
            if time.time() < _mute_until:
                continue
            text = transcribe(audio)
            if not text:
                continue
            _ear["last_heard"] = text
            found, cmd = extract_wake_command(text)
            if not found:
                continue
            if any(s in cmd.lower() for s in ("stand down", "go to sleep", "stop listening")):
                push_event(text, "Standing down, sir. Voice systems offline.")
                _ear.update(status="standing down", listening=False)
                return
            _ear["status"] = "processing"
            reply = "Yes, sir?" if not cmd else handle_text(cmd, source="ear")
            push_event(text, reply)
            _ear["status"] = "listening"
        except Exception as e:
            print(f"[ear] loop error: {e}")
            time.sleep(0.5)


# ------------------------------------------------------------------ the bridge
class BridgeHandler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            self._send(200, {"status": "online", "brain": brain_label(load_settings()), "ear": _ear})
        elif u.path == "/ear":
            self._send(200, _ear)
        elif u.path == "/events":
            since = int((parse_qs(u.query).get("since") or ["0"])[0])
            with _lock:
                new = [e for e in _events if e["id"] > since]
            self._send(200, {"events": new, "latest": _events[-1]["id"] if _events else 0})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/ask"):
            return self._send(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            self._send(200, {"reply": handle_text(str(data.get("text", "")), source="api")})
        except Exception as e:
            self._send(500, {"reply": f"Bridge error: {e}"})

    def log_message(self, *args):
        pass


def main():
    threading.Thread(target=ear_loop, daemon=True).start()
    print("=" * 64)
    print(f"  J.A.R.V.I.S. EAR + BRIDGE  ·  http://localhost:{PORT}")
    print("  Always listening. Say 'Jarvis, ...' — replies play in the HUD.")
    print("  Keep this window open (minimised is fine).")
    print("=" * 64)
    ThreadingHTTPServer(("127.0.0.1", PORT), BridgeHandler).serve_forever()


if __name__ == "__main__":
    main()
