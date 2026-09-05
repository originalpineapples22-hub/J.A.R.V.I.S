# -*- coding: utf-8 -*-
from . import tool
from .. import identity
from ..config import guest_token, rotate_guest_token


@tool("add_person",
      "Register a family member or guest so you recognise them and give them limited, safe access.",
      {"name": "their name", "role": "family|guest", "note": "optional, e.g. 'my brother'"}, agent="Memory Agent")
def add_person(args, ctx):
    if ctx.get("role", "owner") != "owner":
        return "Only the operator can add people."
    msg = identity.add_person(args.get("name", ""), args.get("role", "family"), args.get("note", ""))
    return (f"{msg} Share this guest link with them: /?token={guest_token()} — they can chat, research "
            "and create, but they cannot see your data or control your machine.")


@tool("list_household", "Show the people you recognise and the guest link.", {}, agent="Memory Agent")
def list_household(args, ctx):
    if ctx.get("role", "owner") != "owner":
        return "Only the operator can see that."
    ppl = identity.people()
    lines = [f"- {p['name']} ({p['role']}){' — ' + p['note'] if p['note'] else ''}" for p in ppl] or ["(nobody yet)"]
    return "Household:\n" + "\n".join(lines) + f"\n\nGuest link: /?token={guest_token()}"


@tool("remove_person", "Remove someone's access and delete their face and voice samples.",
      {"name": "their name"}, agent="Memory Agent")
def remove_person(args, ctx):
    if ctx.get("role", "owner") != "owner":
        return "Only the operator can do that."
    return identity.remove_person(args.get("name", ""))


@tool("new_guest_link", "Replace the guest link, so previously shared links stop working.", {}, agent="System Agent")
def new_guest_link(args, ctx):
    if ctx.get("role", "owner") != "owner":
        return "Only the operator can do that."
    return f"New guest link: /?token={rotate_guest_token()} — the old one no longer works."
