# -*- coding: utf-8 -*-
"""
0.5.4.M.4 on Discord — chat, voice messages, and voice-channel calls.

Run beside the server:  python discord_bot/bot.py

What works:
  • DM or mention it  -> it answers as your assistant (same brain, same memory)
  • Send a VOICE MESSAGE / audio clip -> transcribed with Whisper, answered,
    and it replies with a spoken audio note back
  • "!join" in a server channel -> it joins your voice channel and SPEAKS its
    replies aloud, so it feels like a phone call. "!leave" to hang up.

Setup (5 minutes):
  1. discord.com/developers/applications -> New Application -> Bot -> Reset Token, copy it
  2. Under Bot, enable MESSAGE CONTENT INTENT
  3. OAuth2 -> URL Generator -> scopes: bot -> permissions: Send Messages, Read Message
     History, Attach Files, Connect, Speak -> open the URL and invite it to your server
  4. Put the token + your server URL/token in discord_bot/config.json (created on first run)
  5. pip install discord.py PyNaCl
"""
import io
import json
import sys
import asyncio
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / "config.json"

try:
    import discord
    import httpx
except ImportError:
    raise SystemExit("pip install discord.py PyNaCl httpx")


def config():
    if not CFG.exists():
        CFG.write_text(json.dumps({
            "discord_token": "PASTE_BOT_TOKEN",
            "server_url": "https://YOUR-SUBDOMAIN.duckdns.org",
            "jarvis_token": "PASTE_ACCESS_TOKEN",
            "allowed_user_ids": []      # empty = anyone who can see the bot; add your ID to lock it to you
        }, indent=2), encoding="utf-8")
        print(f"Created {CFG} — fill it in, then rerun.")
        sys.exit(0)
    return json.loads(CFG.read_text(encoding="utf-8"))


CFG_D = config()
API = CFG_D["server_url"].rstrip("/")
HEAD = {"X-JARVIS-TOKEN": CFG_D["jarvis_token"]}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


async def ask(text: str) -> str:
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{API}/api/chat", headers=HEAD, json={"text": text, "channel": "discord"})
        r.raise_for_status()
        return r.json().get("reply", "…")


async def transcribe(data: bytes, name: str) -> str:
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{API}/api/transcribe", headers=HEAD, files={"file": (name, data, "audio/ogg")})
        return r.json().get("text", "") if r.status_code == 200 else ""


async def tts(text: str) -> bytes:
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(f"{API}/api/tts", headers=HEAD, params={"text": text[:1500]})
        return r.content if r.status_code == 200 else b""


def allowed(user_id: int) -> bool:
    ids = CFG_D.get("allowed_user_ids") or []
    return not ids or user_id in ids


@client.event
async def on_ready():
    print(f"[discord] online as {client.user} — DM it, or use !join in a voice channel")


@client.event
async def on_message(msg: discord.Message):
    if msg.author.bot or not allowed(msg.author.id):
        return
    is_dm = isinstance(msg.channel, discord.DMChannel)
    mentioned = client.user in msg.mentions
    content = msg.content.replace(f"<@{client.user.id}>", "").strip()

    # --- voice channel controls
    if content.lower().startswith("!join"):
        if msg.author.voice and msg.author.voice.channel:
            vc = await msg.author.voice.channel.connect()
            await msg.channel.send("Connected, sir. Speak in chat and I will answer aloud. `!leave` to hang up.")
            audio = await tts("Online, sir. How may I help?")
            if audio:
                await play(vc, audio)
        else:
            await msg.channel.send("Join a voice channel first, sir.")
        return
    if content.lower().startswith("!leave"):
        for vc in client.voice_clients:
            if vc.guild == msg.guild:
                await vc.disconnect()
        await msg.channel.send("Disconnected, sir.")
        return

    # --- audio attachment = a spoken message
    spoken = ""
    for att in msg.attachments:
        if att.content_type and att.content_type.startswith("audio"):
            spoken = await transcribe(await att.read(), att.filename)
            break

    text = spoken or content
    if not text or (not is_dm and not mentioned and not spoken):
        return

    async with msg.channel.typing():
        reply = await ask(text)
    if spoken:
        await msg.reply(f"*heard:* “{spoken}”\n\n{reply}"[:1900])
    else:
        await msg.reply(reply[:1900])

    # speak back: in the voice channel if connected, else as a voice note
    vc = discord.utils.get(client.voice_clients, guild=msg.guild) if msg.guild else None
    audio = await tts(reply)
    if audio:
        if vc and vc.is_connected():
            await play(vc, audio)
        elif spoken:
            await msg.channel.send(file=discord.File(io.BytesIO(audio), "reply.mp3"))


async def play(vc, audio: bytes):
    path = HERE / "_reply.mp3"
    path.write_bytes(audio)
    if vc.is_playing():
        vc.stop()
    vc.play(discord.FFmpegPCMAudio(str(path)))
    while vc.is_playing():
        await asyncio.sleep(0.2)


if __name__ == "__main__":
    client.run(CFG_D["discord_token"])
