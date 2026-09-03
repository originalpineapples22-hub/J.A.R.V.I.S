# -*- coding: utf-8 -*-
"""
J.A.R.V.I.S. PC AGENT — run this on your PC:  python pc_agent/agent.py
Connects your PC to the cloud J.A.R.V.I.S. so it can control it from anywhere
(open apps, volume, brightness, media, screen vision) and, optionally, listens
with the offline Whisper ear and speaks replies through the PC speakers.

Set JARVIS_URL and JARVIS_TOKEN in pc_agent/config.json (created on first run).
"""
import os, sys, json, time, asyncio, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "legacy"))   # reuse the proven PC-control engine
CFG = HERE / "config.json"

try:
    import websockets
except ImportError:
    raise SystemExit("pip install websockets")

from jarvis_core import parse_local_command, describe_screen, tts_speak, clean_for_speech, extract_wake_command, HAS_TTS  # noqa


def config():
    if not CFG.exists():
        CFG.write_text(json.dumps({"url": "wss://YOUR-SERVER/ws/pc", "token": "YOUR_TOKEN", "ear": True, "speak": True, "whisper_model": "base.en"}, indent=2))
        print(f"Created {CFG} — fill in your server URL and token, then rerun.")
        sys.exit(0)
    return json.loads(CFG.read_text())


def run_command(cmd: str) -> str:
    settings = {"provider": "local"}
    out = parse_local_command(cmd, settings)
    return out or f"Unknown PC command: {cmd}"


async def main():
    cfg = config()
    url = f"{cfg['url']}?token={cfg['token']}"
    heard_q: asyncio.Queue = asyncio.Queue()
    if cfg.get("ear"):
        threading.Thread(target=ear_thread, args=(heard_q, cfg, asyncio.get_event_loop()), daemon=True).start()
    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                print("[pc-agent] connected to J.A.R.V.I.S. cloud")

                async def sender():
                    while True:
                        text = await heard_q.get()
                        await ws.send(json.dumps({"type": "heard", "text": text}))

                st = asyncio.create_task(sender())
                try:
                    async for raw in ws:
                        msg = json.loads(raw)
                        if "command" in msg:
                            res = await asyncio.to_thread(run_command, msg["command"])
                            await ws.send(json.dumps({"id": msg["id"], "result": res}))
                        elif msg.get("type") == "speak" and cfg.get("speak") and HAS_TTS:
                            threading.Thread(target=tts_speak, args=(clean_for_speech(msg["text"]),), daemon=True).start()
                finally:
                    st.cancel()
        except Exception as e:
            print(f"[pc-agent] disconnected ({e}); retrying in 5s")
            await asyncio.sleep(5)


def ear_thread(q: asyncio.Queue, cfg: dict, loop):
    try:
        import speech_recognition as sr
        import numpy as np
        from faster_whisper import WhisperModel
    except Exception as e:
        print(f"[ear] disabled ({e}) — pip install SpeechRecognition pyaudio faster-whisper numpy")
        return
    model = WhisperModel(cfg.get("whisper_model", "base.en"), device="cpu", compute_type="int8")
    rec = sr.Recognizer(); rec.energy_threshold = 300; rec.dynamic_energy_threshold = True; rec.pause_threshold = 0.8
    mic = sr.Microphone(sample_rate=16000)
    with mic as s:
        rec.adjust_for_ambient_noise(s, 1.0)
    print("[ear] listening — say 'Jarvis, ...'")
    attentive_until = 0.0
    while True:
        try:
            with mic as s:
                audio = rec.listen(s, phrase_time_limit=12)
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            arr = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
            segs, _ = model.transcribe(arr, language="en", beam_size=3, vad_filter=True, condition_on_previous_text=False,
                                       initial_prompt="Jarvis, open YouTube. Jarvis, what time is it? Jarvis.")
            text = " ".join(x.text for x in segs).strip()
            if not text or text.lower().strip(" .!") in ("you", "thank you", "thanks"):
                continue
            found, cmd = extract_wake_command(text)
            if not found and time.time() > attentive_until:
                continue
            cmd = cmd if found else text
            if not cmd:
                attentive_until = time.time() + 8
                if cfg.get("speak") and HAS_TTS:
                    tts_speak("Yes, sir?")
                continue
            attentive_until = time.time() + 10
            asyncio.run_coroutine_threadsafe(q.put(cmd), loop)
        except Exception as e:
            print(f"[ear] {e}"); time.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(main())
