# -*- coding: utf-8 -*-
"""Relay commands to the operator's PC agent (pc_agent/agent.py) when it is connected."""
import asyncio
import json
import uuid
from . import tool

_pc_ws = None
_pending: dict = {}


def pc_connected():
    return _pc_ws is not None


def set_pc_socket(ws):
    global _pc_ws
    _pc_ws = ws


def resolve_pc_reply(msg: dict):
    fut = _pending.pop(msg.get("id"), None)
    if fut and not fut.done():
        fut.set_result(msg.get("result", ""))


@tool("pc_command", "Control the operator's PC when it is online: open apps/websites, volume, brightness, media, macros, or 'look at my screen'.",
      {"command": "plain command, e.g. 'open spotify', 'volume 30', 'look at my screen'"}, agent="System Agent")
async def pc_command(args, ctx):
    if _pc_ws is None:
        return "The PC is offline (PC agent not connected)."
    rid = uuid.uuid4().hex
    fut = asyncio.get_event_loop().create_future()
    _pending[rid] = fut
    try:
        await _pc_ws.send_text(json.dumps({"id": rid, "command": args.get("command", "")}))
        return await asyncio.wait_for(fut, timeout=60)
    except asyncio.TimeoutError:
        _pending.pop(rid, None)
        return "The PC did not respond in time."
    except Exception as e:
        return f"PC relay error: {e}"
