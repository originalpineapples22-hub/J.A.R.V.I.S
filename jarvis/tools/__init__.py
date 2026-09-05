# -*- coding: utf-8 -*-
"""Tool registry. Each tool is a plugin: name, description, args, async run(args, ctx)."""
import json
import inspect
from typing import Callable, Awaitable

_REGISTRY: dict = {}


class Tool:
    def __init__(self, name, description, args, fn, agent="System Agent"):
        self.name, self.description, self.args, self.fn, self.agent = name, description, args, fn, agent

    async def run(self, args: dict, ctx: dict) -> str:
        try:
            res = self.fn(args, ctx)
            if inspect.isawaitable(res):
                res = await res
            return str(res)
        except Exception as e:
            return f"Tool '{self.name}' failed: {e}"


def tool(name: str, description: str, args: dict = None, agent: str = "System Agent"):
    def deco(fn):
        _REGISTRY[name] = Tool(name, description, args or {}, fn, agent)
        return fn
    return deco


def get(name):
    return _REGISTRY.get(name)


def all_tools():
    return list(_REGISTRY.values())


def manifest() -> str:
    lines = []
    for t in _REGISTRY.values():
        lines.append(f"- {t.name}: {t.description} Args: {json.dumps(t.args)}")
    return "\n".join(lines)


def agents_status() -> list:
    """Group tools into the 'agents' shown on the dashboard."""
    groups = {}
    for t in _REGISTRY.values():
        groups.setdefault(t.agent, []).append(t.name)
    return [{"name": k, "tools": v, "status": "standby"} for k, v in groups.items()]


# import plugins so they register
from . import system, web, files, learn, pc, office, science, invent, live, music, dev, search, actions, reason, filesystem, mission_tools, preview, research, interpreter, create_media, skill_tools, health, identity_tools, household  # noqa: E402,F401
