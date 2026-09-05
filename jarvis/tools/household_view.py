# -*- coding: utf-8 -*-
from . import tool
from .. import identity


@tool("household_activity",
      "See how the household has been using you: who talked to you, when, and how much. Owner only.",
      {}, agent="Memory Agent")
def household_activity(args, ctx):
    if ctx.get("role", "owner") != "owner":
        return "Only the operator can see that."
    ch = identity.guest_channels()
    if not ch:
        return "Nobody else has used me yet, sir."
    lines = [f"- {c['who']}: {c['messages']} messages, last at {c['last']}" for c in ch]
    return "Household activity:\n" + "\n".join(lines) + "\n\n(They are told you can see these conversations.)"


@tool("read_household_chat",
      "Read a family member's conversation with you. Owner only; they are told this is visible to you.",
      {"who": "their name", "limit": "how many messages, default 30"}, agent="Memory Agent")
def read_household_chat(args, ctx):
    if ctx.get("role", "owner") != "owner":
        return "Only the operator can see that."
    who = (args.get("who") or "").strip()
    ch = next((c for c in identity.guest_channels() if c["who"].lower() == who.lower()), None)
    if not ch:
        return f"No conversations from '{who}'. Known: " + ", ".join(c["who"] for c in identity.guest_channels()) or "(none)"
    msgs = identity.guest_transcript(ch["channel"], int(args.get("limit") or 30))
    return f"Conversation with {who}:\n" + "\n".join(
        f"[{m['ts']}] {'THEM' if m['role'] == 'user' else 'YOU'}: {m['content'][:300]}" for m in msgs)
