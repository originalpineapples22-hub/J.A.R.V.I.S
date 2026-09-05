# -*- coding: utf-8 -*-
"""Skill packs — the 'custom GPTs' idea, owned by 0.5.4.M.4.

A skill is a named set of instructions the operator can define once and invoke
forever ('financial analyst', 'my code reviewer', 'exam tutor'). They are stored
in the database and injected into the system prompt when active.
"""
from . import memory


def _table():
    memory.db().executescript("""
    CREATE TABLE IF NOT EXISTS skillpacks(
      name TEXT PRIMARY KEY, instructions TEXT, active INTEGER DEFAULT 0, ts TEXT);
    """)
    memory.db().commit()


def save(name: str, instructions: str, active: bool = False):
    _table()
    memory.db().execute(
        "INSERT OR REPLACE INTO skillpacks(name, instructions, active, ts) VALUES (?,?,?,?)",
        (name.strip().lower(), instructions.strip(), 1 if active else 0, memory.now()))
    memory.db().commit()


def all_packs():
    _table()
    return [dict(r) for r in memory.db().execute("SELECT * FROM skillpacks ORDER BY name").fetchall()]


def active_packs():
    _table()
    return [dict(r) for r in memory.db().execute("SELECT * FROM skillpacks WHERE active=1").fetchall()]


def set_active(name: str, active: bool):
    _table()
    memory.db().execute("UPDATE skillpacks SET active=? WHERE name=?", (1 if active else 0, name.strip().lower()))
    memory.db().commit()


def delete(name: str):
    _table()
    memory.db().execute("DELETE FROM skillpacks WHERE name=?", (name.strip().lower(),))
    memory.db().commit()


def prompt_block() -> str:
    packs = active_packs()
    if not packs:
        return ""
    return "\n\nACTIVE SKILL PACKS (follow these standing instructions):\n" + "\n".join(
        f"- {p['name'].upper()}: {p['instructions']}" for p in packs)
