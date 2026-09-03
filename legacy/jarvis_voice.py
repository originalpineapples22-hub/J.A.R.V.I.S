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
    remember_exchange, recall_memory, summarize_history,
)

PORT = 8765
_history = []
_summary = ""
_events = []          # {"id","ts","heard","reply"}
_lock = threading.Lock()
_ear = {"status": "starting", "engine": "none", "last_heard": "", "listening": False}
_echo_guard = {"until": 0.0, "text": ""}   # while J.A.R.V.I.S. speaks, ignore audio that matches its own words
_attentive_until = 0.0                     # after "Jarvis" alone or a reply: accept the next sentence with no wake word


# ------------------------------------------------------------------ brain
def handle_text(text: str, source: str = "hud") -> str:
    global _history, _summary
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
        if len(_history) > 16:
            _summary = summarize_history(_history[:-8], settings, _summary)
            del _history[:-8]
        memory = recall_memory(text)
        sys_prompt = PERSONA
        if _summary:
            sys_prompt += f"\n\nCONVERSATION SO FAR (auto-summary): {_summary}"
        if memory:
            sys_prompt += f"\n\nRELEVANT PAST CONVERSATIONS (your own memory):\n{memory}"
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


def _is_self_echo(text: str) -> bool:
    """True if what we heard is J.A.R.V.I.S.'s own voice coming back through the mic."""
    import difflib
    if time.time() > _echo_guard["until"] or not _echo_guard["text"]:
        return False
    heard = set(text.lower().split())
    own = set(_echo_guard["text"].lower().split())
    if heard and len(heard & own) / len(heard) >= 0.6:
        return True
    return difflib.SequenceMatcher(None, text.lower(), _echo_guard["text"].lower()).ratio() > 0.5


def push_event(heard: str, reply: str):
    global _attentive_until
    with _lock:
        _events.append({"id": len(_events) + 1, "ts": datetime.now().strftime("%H:%M:%S"),
                        "heard": heard, "reply": reply})
        del _events[:-200]
    spoken = clean_for_speech(reply)
    # Keep listening while speaking; just ignore our own words (~14 chars/sec)
    _echo_guard.update(until=time.time() + min(25, 1.5 + len(spoken) / 14.0), text=spoken)
    # Call-style follow-up: for a few seconds the operator can continue without the wake word
    _attentive_until = _echo_guard["until"] + float(load_settings().get("follow_up_seconds", 8))
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
    rec.energy_threshold = 300
    rec.dynamic_energy_threshold = True
    rec.pause_threshold = 0.8
    rec.non_speaking_duration = 0.4
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
            segments, _ = whisper.transcribe(
                arr, language="en", beam_size=3, vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt="Jarvis, open YouTube. Jarvis, what time is it? Jarvis.",  # biases Whisper toward the name
            )
            text = " ".join(seg.text for seg in segments).strip()
            # Whisper hallucinates these on near-silence
            return "" if text.lower().strip(" .!") in ("you", "thank you", "thanks", "bye", "the", "uh") else text
        try:
            return rec.recognize_google(audio)
        except Exception:
            return ""

    global _attentive_until
    _ear.update(status="listening", listening=True)
    print(f"[ear] online — engine: {_ear['engine']}. Say 'Jarvis, ...'")
    while True:
        try:
            with mic as src:
                audio = rec.listen(src, phrase_time_limit=12)
            text = transcribe(audio)
            if not text:
                continue
            if _is_self_echo(text):
                continue
            _ear["last_heard"] = text
            found, cmd = extract_wake_command(text)
            if not found:
                if time.time() < _attentive_until:
                    cmd = text.strip()          # follow-up / attentive mode: no wake word needed
                else:
                    continue
            if any(s in cmd.lower() for s in ("stand down", "go to sleep", "stop listening")):
                push_event(text, "Standing down, sir. Voice systems offline.")
                _ear.update(status="standing down", listening=False)
                return
            if not cmd:
                # Heard just "Jarvis" — acknowledge and wait for the order
                _attentive_until = time.time() + 8
                push_event(text, "Yes, sir?")
                continue
            _ear["status"] = "processing"
            reply = handle_text(cmd, source="ear")
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
