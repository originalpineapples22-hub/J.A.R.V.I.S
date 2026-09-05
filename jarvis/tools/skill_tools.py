# -*- coding: utf-8 -*-
from . import tool
from .. import skills


@tool("create_skill",
      "Teach yourself a reusable skill the operator defines once and can invoke forever — a persona, a workflow, a standard, a checklist (e.g. 'financial analyst', 'my code style', 'exam tutor').",
      {"name": "short name", "instructions": "how to behave when this skill is active", "activate": "true|false"},
      agent="Memory Agent")
def create_skill(args, ctx):
    name = (args.get("name") or "").strip()
    ins = (args.get("instructions") or "").strip()
    if not name or not ins:
        return "Give the skill a name and its instructions, sir."
    act = str(args.get("activate", "true")).lower() not in ("false", "0", "no")
    skills.save(name, ins, act)
    return f"Skill '{name}' saved{' and activated' if act else ''}. I will follow it from now on."


@tool("list_skills", "List the skill packs you know and which are active.", {}, agent="Memory Agent")
def list_skills(args, ctx):
    packs = skills.all_packs()
    if not packs:
        return "No skill packs yet. Create one with create_skill."
    return "\n".join(f"{'●' if p['active'] else '○'} {p['name']} — {p['instructions'][:90]}" for p in packs)


@tool("toggle_skill", "Turn a skill pack on or off.", {"name": "skill name", "active": "true|false"}, agent="Memory Agent")
def toggle_skill(args, ctx):
    act = str(args.get("active", "true")).lower() not in ("false", "0", "no")
    skills.set_active(args.get("name", ""), act)
    return f"Skill '{args.get('name')}' {'activated' if act else 'deactivated'}."
