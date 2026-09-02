# -*- coding: utf-8 -*-
"""
J.A.R.V.I.S. VOICE DAEMON — always-on, hands-free "call mode".

Runs as a SEPARATE program alongside the Streamlit HUD (jarvis.py). Because
web browsers require a click before using the microphone, true 24/7 listening
has to live in a standalone process like this one, which uses your PC's
microphone directly.

How it decides you're talking to IT and not someone else:
  It stays silent until it hears the wake word "jarvis". Only the speech that
  follows the wake word is treated as a command. Say "Jarvis, what's my CPU
  doing" — it answers. Talk to a person in the room without saying "Jarvis" —
  it ignores you. This is exactly how the movie version gates attention.

Screen vision:
  Say "Jarvis, look at my screen" / "what am I doing" / "what's on my screen"
  and it captures a screenshot and describes it — IF you have a local vision
  model pulled in Ollama (e.g. `ollama pull llava`). Set VISION_MODEL below.

Run it:
  pip install SpeechRecognition pyttsx3 pyaudio mss pillow requests
  python jarvis_voice.py

Notes:
  - pyaudio can be fussy on Windows. If `pip install pyaudio` fails, use:
        pip install pipwin && pipwin install pyaudio
  - Speech recognition uses Google's free web recognizer by default (needs
    internet). For fully offline recognition, install vosk and set
    USE_VOSK = True with a downloaded model.
"""

import json
import time
import threading
import requests

# ---- CONFIG (edit to taste) ----
OLLAMA_URL = "http://localhost:11434/api/chat"
TEXT_MODEL = "qwen2.5-coder:14b"     # your main brain
VISION_MODEL = "llava"               # a vision model for screen-reading; pull with `ollama pull llava`
WAKE_WORDS = ("jarvis", "hey jarvis")
STOP_WORDS = ("stand down", "go to sleep", "that's all jarvis", "shut down voice")
VOICE_RATE = 178
SYSTEM_PERSONA = (
    "You are J.A.R.V.I.S., a calm, articulate British AI butler with dry wit. "
    "You address the user as 'sir'. Keep spoken replies concise (1-3 sentences) "
    "unless asked for detail. You may offer subtle, respectful pushback on risky ideas."
)

# ---- Optional imports with clear guidance ----
try:
    import speech_recognition as sr
except Exception:
    raise SystemExit("Missing SpeechRecognition. Run: pip install SpeechRecognition pyaudio")

try:
    import pyttsx3
    _tts = pyttsx3.init()
    _tts.setProperty("rate", VOICE_RATE)
    # Prefer a male 'butler'-ish voice if one is available
    for v in _tts.getProperty("voices"):
        if "david" in v.name.lower() or "george" in v.name.lower() or "daniel" in v.name.lower():
            _tts.setProperty("voice", v.id)
            break
    HAS_TTS = True
except Exception:
    HAS_TTS = False

try:
    import mss
    from PIL import Image
    import base64
    import io
    HAS_VISION = True
except Exception:
    HAS_VISION = False

_speak_lock = threading.Lock()


def speak(text: str):
    print(f"J.A.R.V.I.S. > {text}")
    if not HAS_TTS or not text.strip():
        return
    with _speak_lock:
        try:
            _tts.say(text)
            _tts.runAndWait()
        except Exception:
            pass


def ask_ollama(user_text: str, history: list) -> str:
    messages = [{"role": "system", "content": SYSTEM_PERSONA}] + history[-8:] + [
        {"role": "user", "content": user_text}
    ]
    try:
        payload = {"model": TEXT_MODEL, "messages": messages, "stream": False,
                   "options": {"temperature": 0.4}}
        r = requests.post(OLLAMA_URL, json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip() or "I have no answer, sir."
    except Exception as e:
        return f"I could not reach my cognitive core, sir. {e}"


def capture_and_describe_screen() -> str:
    if not HAS_VISION:
        return "My visual sensors are offline, sir. Install them with: pip install mss pillow"
    try:
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        img.thumbnail((1280, 1280))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        payload = {
            "model": VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": "Describe what is on this screen concisely, as J.A.R.V.I.S. would report to sir.",
                "images": [b64],
            }],
            "stream": False,
        }
        r = requests.post(OLLAMA_URL, json=payload, timeout=180)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip() or "I cannot interpret the display, sir."
    except Exception as e:
        return (f"My visual analysis failed, sir. Ensure a vision model is installed "
                f"(ollama pull {VISION_MODEL}). Error: {e}")


def extract_command(heard: str):
    """Return the command text if a wake word is present, else None."""
    low = heard.lower().strip()
    for w in WAKE_WORDS:
        if w in low:
            after = low.split(w, 1)[1].strip(" ,.!?")
            return after if after else "(awaiting orders)"
    return None


def main():
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    mic = sr.Microphone()

    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1.0)

    history = []
    speak("Voice systems online, sir. Say 'Jarvis' whenever you need me.")
    print("=" * 60)
    print("  Always listening. Say 'Jarvis ...' to give an order.")
    print("  Say 'stand down' to stop the voice daemon.")
    print("=" * 60)

    while True:
        try:
            with mic as source:
                audio = recognizer.listen(source, phrase_time_limit=8)
            try:
                heard = recognizer.recognize_google(audio)
            except sr.UnknownValueError:
                continue
            except sr.RequestError:
                # Offline / no internet for the recognizer
                continue

            print(f"[heard] {heard}")

            if any(s in heard.lower() for s in STOP_WORDS):
                speak("Standing down, sir. Voice systems offline.")
                break

            command = extract_command(heard)
            if command is None:
                # Not addressed to JARVIS — ignore (this is the "talking to
                # someone else" filter).
                continue

            if command == "(awaiting orders)":
                speak("Yes, sir?")
                continue

            # Screen-vision intent
            if any(k in command for k in ("look at my screen", "what am i doing",
                                          "what's on my screen", "whats on my screen",
                                          "see my screen", "read my screen")):
                speak("One moment, sir. Analysing your display.")
                report = capture_and_describe_screen()
                speak(report)
                history += [{"role": "user", "content": command},
                            {"role": "assistant", "content": report}]
                continue

            # Normal conversation
            reply = ask_ollama(command, history)
            history += [{"role": "user", "content": command},
                        {"role": "assistant", "content": reply}]
            speak(reply)

        except KeyboardInterrupt:
            speak("Voice systems offline, sir.")
            break
        except Exception as e:
            print(f"[voice loop error] {e}")
            time.sleep(0.5)


if __name__ == "__main__":
    main()
