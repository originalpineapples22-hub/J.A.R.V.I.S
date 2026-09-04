# -*- coding: utf-8 -*-
"""YouTube Music control — opens/plays on the operator's PC when the agent is
connected, otherwise returns a direct link to tap."""
from urllib.parse import quote_plus
from . import tool
from .pc import pc_connected, pc_command


@tool("play_music", "Play a song, artist or playlist on YouTube Music.", {"query": "song / artist / playlist"}, agent="System Agent")
async def play_music(args, ctx):
    q = (args.get("query") or "").strip()
    if not q:
        return "What would you like me to play, sir?"
    url = f"https://music.youtube.com/search?q={quote_plus(q)}"
    if pc_connected():
        await pc_command({"command": url}, ctx)
        return f"Playing {q} on YouTube Music, sir."
    return f"YouTube Music is ready: {url} — tap to play (or start the PC agent and I will open it for you)."


@tool("music_control", "Control playback on the PC: play/pause, next, previous.", {"action": "play|pause|next|previous"}, agent="System Agent")
async def music_control(args, ctx):
    a = (args.get("action") or "play").lower()
    cmd = {"play": "pause music", "pause": "pause music", "next": "next song", "previous": "previous song"}.get(a, "pause music")
    if not pc_connected():
        return "Your PC is offline, sir — playback control needs the PC agent."
    return await pc_command({"command": cmd}, ctx)
