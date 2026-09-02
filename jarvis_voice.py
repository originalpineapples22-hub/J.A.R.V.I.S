# -*- coding: utf-8 -*-
"""
J.A.R.V.I.S. VOICE BRIDGE

Default mode (no arguments):  python jarvis_voice.py
    Runs a tiny local HTTP bridge on http://localhost:8765 that the HUD's
    📞 VOICE CHANNEL panel talks to. The BROWSER does the listening and the
    speaking (reliable everywhere); this process just thinks and controls
    the PC (open apps, volume, screen vision, chat). Nothing is spoken from
    this window — keep it minimised.

Fallback mode:  python jarvis_voice.py --mic
    Fully standalone call mode using the PC microphone + PC speakers, no
    browser required. Uses a fresh speech engine per sentence (fixes the
    Windows "goes silent after first sentence" bug).

Both modes gate on the wake word "jarvis", so speech not addressed to
J.A.R.V.I.S. is ignored.
"""
import sys
import json
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jarvis_core import (
    PERSONA, parse_local_command, chat_once, load_settings, brain_label,
    tts_speak, clean_for_speech, HAS_TTS, execute_pc_tags,
)

PORT = 8765
LOG_FILE = Path("jarvis_voice_log.json")

_history = []


def log_exchange(heard: str, reply: str):
    entries = []
    if LOG_FILE.exists():
        try:
            entries = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    entries.append({"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "heard": heard, "reply": reply})
    LOG_FILE.write_text(json.dumps(entries[-200:], indent=2), encoding="utf-8")


def handle_text(text: str) -> str:
    """Shared brain: PC command first, then conversational AI."""
    global _history
    text = text.strip()
    if not text:
        return "Yes, sir?"
    settings = load_settings()  # re-read each time so HUD changes apply instantly
    try:
        direct = parse_local_command(text, settings)
    except Exception as e:
        direct = f"Command engine error: {e}"
    if direct:
        reply = direct
    else:
        messages = [{"role": "system", "content": PERSONA}] + _history[-8:] + [{"role": "user", "content": text}]
        try:
            reply = chat_once(messages, settings, temperature=0.4) or "I have no answer, sir."
            reply, _ = execute_pc_tags(reply, settings)
        except Exception as e:
            reply = f"I could not reach my cognitive core, sir. ({e})"
    _history += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
    log_exchange(text, reply)
    print(f"[you]      {text}\n[jarvis]   {reply}\n")
    return reply


class BridgeHandler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/health"):
            body = json.dumps({"status": "online", "brain": brain_label(load_settings())}).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

    def do_POST(self):
        if not self.path.startswith("/ask"):
            self.send_response(404)
            self._cors()
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            reply = handle_text(str(data.get("text", "")))
            status = 200
        except Exception as e:
            reply, status = f"Bridge error: {e}", 500
        body = json.dumps({"reply": reply}).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # keep the window quiet


def run_bridge():
    print("=" * 62)
    print(f"  J.A.R.V.I.S. VOICE BRIDGE online at http://localhost:{PORT}")
    print("  Open the HUD (streamlit run jarvis.py) and just say 'Jarvis, ...'")
    print("  This window stays silent — the browser listens and speaks.")
    print("=" * 62)
    ThreadingHTTPServer(("127.0.0.1", PORT), BridgeHandler).serve_forever()


def run_mic_mode():
    try:
        import speech_recognition as sr
    except Exception:
        raise SystemExit("Missing SpeechRecognition. Run: pip install SpeechRecognition pyaudio")

    def say(t):
        print(f"J.A.R.V.I.S. > {t}")
        if HAS_TTS:
            tts_speak(clean_for_speech(t))

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    mic = sr.Microphone()
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1.0)
    say("Voice systems online, sir. Say Jarvis whenever you need me.")
    while True:
        try:
            with mic as source:
                audio = recognizer.listen(source, phrase_time_limit=8)
            try:
                heard = recognizer.recognize_google(audio)
            except (sr.UnknownValueError, sr.RequestError):
                continue
            low = heard.lower()
            if any(s in low for s in ("stand down", "go to sleep", "shut down voice")):
                say("Standing down, sir.")
                break
            idx = low.find("jarvis")
            if idx < 0:
                continue  # not talking to JARVIS
            cmd = heard[idx + 6:].strip(" ,.!?")
            if not cmd:
                say("Yes, sir?")
                continue
            say(handle_text(cmd))
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[voice loop error] {e}")
            time.sleep(0.5)


if __name__ == "__main__":
    if "--mic" in sys.argv:
        run_mic_mode()
    else:
        run_bridge()
