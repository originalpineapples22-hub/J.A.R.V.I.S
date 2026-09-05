# -*- coding: utf-8 -*-
from . import tool
from .. import missions


@tool("start_mission",
      "Begin a long-running job that continues in the background — across hours, days and restarts — until it is finished. Use for anything big: build an app, research a market, produce a full project.",
      {"goal": "what must be accomplished"}, agent="Task Agent")
def start_mission(args, ctx):
    goal = (args.get("goal") or "").strip()
    if not goal:
        return "What should the mission accomplish, sir?"
    mid = missions.create(goal)
    missions.start(mid)
    return (f"Mission #{mid} started: {goal}\nI will keep working on it in the background and report when it is "
            f"done — or ask you if I need a decision. Say 'mission status' any time.")


@tool("mission_status", "Show running missions and their progress.", {"id": "optional mission id"}, agent="Task Agent")
def mission_status(args, ctx):
    if args.get("id"):
        m = missions.get(int(args["id"]))
        if not m:
            return "No such mission."
        out = [f"Mission #{m['id']} — {m['state']} (step {m['step']})", f"Goal: {m['goal']}"]
        if m.get("question"):
            out.append(f"WAITING ON YOU: {m['question']}")
        if m.get("result"):
            out.append(f"Result: {m['result'][:800]}")
        out.append("Log:\n" + (m.get("log") or "")[-1200:])
        return "\n".join(out)
    ms = missions.all_missions()
    if not ms:
        return "No missions running, sir."
    return "\n".join(f"#{m['id']} [{m['state']}] step {m['step']} — {m['goal'][:70]}"
                     + (f"  ⚠ waiting: {m['question'][:80]}" if m.get("question") else "") for m in ms)


@tool("answer_mission", "Answer a mission that is waiting for your decision, so it can continue.",
      {"id": "mission id", "answer": "your decision"}, agent="Task Agent")
def answer_mission(args, ctx):
    return missions.answer(int(args.get("id")), args.get("answer", ""))


@tool("cancel_mission", "Stop a mission.", {"id": "mission id"}, agent="Task Agent")
def cancel_mission(args, ctx):
    missions.update(int(args.get("id")), state="cancelled")
    return f"Mission #{args.get('id')} cancelled."
