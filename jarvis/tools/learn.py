# -*- coding: utf-8 -*-
from . import tool
from .. import memory


@tool("study_topic", "Autonomously master a technology or language: researches and writes a full curriculum into permanent memory (runs in the background, ~2 minutes).",
      {"topic": "string"}, agent="Research Agent")
async def study_topic(args, ctx):
    from ..learning import start_study
    topic = args.get("topic", "").strip()
    if not topic:
        return "No topic given."
    started = start_study(topic)
    return f"Study session for '{topic}' {'started' if started else 'is already running'} in the background. I will report when it is complete."


@tool("knowledge_lookup", "Look up what you have already learned about a topic.", {"query": "string"}, agent="Memory Agent")
def knowledge_lookup(args, ctx):
    return memory.recall_knowledge(args.get("query", ""), k=4) or "Nothing learned about that yet."
