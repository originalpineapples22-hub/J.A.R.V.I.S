# -*- coding: utf-8 -*-
from . import tool
from .. import identity


@tool("remember_about_me",
      "Store something durable about the operator — a preference, a fact, a goal, how they like to be addressed. Use whenever you learn something that should outlive this conversation.",
      {"fact": "the thing to remember"}, agent="Memory Agent")
def remember_about_me(args, ctx):
    return identity.remember_fact((args.get("fact") or "").strip())


@tool("update_my_profile",
      "Update the operator's core profile: name, what to call them, pronouns, location, languages, work, goals, and how they like to be spoken to.",
      {"name": "", "call_me": "", "pronouns": "", "location": "", "languages": "", "work": "", "goals": "", "style": ""},
      agent="Memory Agent")
def update_my_profile(args, ctx):
    keep = {k: v for k, v in args.items() if k in ("name", "call_me", "pronouns", "location",
                                                   "languages", "work", "goals", "style") and v}
    if not keep:
        return "Tell me what to record, sir."
    identity.save_profile(keep)
    return "Profile updated — " + ", ".join(f"{k}: {v}" for k, v in keep.items())


@tool("who_am_i", "Report everything you know about the operator, and whether their face and voice are enrolled.", {}, agent="Memory Agent")
def who_am_i(args, ctx):
    s = identity.status()
    p = s["profile"]
    if not p and not s["face_samples"] and not s["voice_samples"]:
        return "I do not know you yet, sir. Tell me about yourself, and enrol your face and voice in Settings."
    lines = [identity.profile_block().strip()]
    lines.append(f"Face enrolled: {s['face_samples']} sample(s). Voice enrolled: {s['voice_samples']} sample(s).")
    return "\n".join(lines)


@tool("forget_biometrics", "Delete the enrolled face or voice samples.", {"kind": "face|voice"}, agent="Memory Agent")
def forget_biometrics(args, ctx):
    k = (args.get("kind") or "").lower()
    if k not in ("face", "voice"):
        return "Say face or voice, sir."
    return identity.clear(k)
