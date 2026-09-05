# -*- coding: utf-8 -*-
"""Quota budget — keeps autonomous work from exhausting the free tiers.

Every model call is counted. Background work (self-study, idle thinking) draws
from a separate, smaller allowance than the operator, so 0.5.4.M.4 can never
spend the day's quota on studying and leave nothing for you.
"""
from datetime import date
from . import memory

DEFAULTS = {"daily_total": 900, "background_share": 0.35}   # background may use 35% of the day


def _today():
    return date.today().isoformat()


def _table():
    memory.db().executescript(
        "CREATE TABLE IF NOT EXISTS usage(day TEXT, kind TEXT, n INTEGER, PRIMARY KEY(day, kind));")
    memory.db().commit()


def record(kind: str = "operator", n: int = 1):
    _table()
    memory.db().execute(
        "INSERT INTO usage(day, kind, n) VALUES (?,?,?) ON CONFLICT(day, kind) DO UPDATE SET n = n + ?",
        (_today(), kind, n, n))
    memory.db().commit()


def used(kind: str = None) -> int:
    _table()
    if kind:
        r = memory.db().execute("SELECT n FROM usage WHERE day=? AND kind=?", (_today(), kind)).fetchone()
        return r["n"] if r else 0
    r = memory.db().execute("SELECT SUM(n) AS n FROM usage WHERE day=?", (_today(),)).fetchone()
    return (r["n"] or 0) if r else 0


def limits():
    from .config import load_settings
    s = load_settings()
    total = int(s.get("daily_call_budget", DEFAULTS["daily_total"]))
    share = float(s.get("background_share", DEFAULTS["background_share"]))
    return total, int(total * share)


def can_spend(kind: str = "background") -> bool:
    """Background work stops well before the operator's own use is at risk."""
    total, bg_cap = limits()
    if used() >= total:
        return False
    if kind == "background":
        return used("background") < bg_cap
    return True


def status() -> dict:
    total, bg_cap = limits()
    return {"day": _today(), "used": used(), "operator": used("operator"),
            "background": used("background"), "daily_limit": total,
            "background_limit": bg_cap,
            "background_allowed": can_spend("background"),
            "percent": round(used() / total * 100, 1) if total else 0}
