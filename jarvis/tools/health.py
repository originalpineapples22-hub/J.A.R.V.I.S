# -*- coding: utf-8 -*-
from . import tool
from .. import doctor, budget, selfdev


@tool("system_check",
      "Test every external service and dependency for real and report exactly what works, what does not, and how to fix it. Run this after deploying or when something behaves oddly.",
      {"quick": "true to skip the slower network tests"}, agent="System Agent")
async def system_check(args, ctx):
    quick = str(args.get("quick", "")).lower() in ("true", "1", "yes")
    return doctor.format_report(await doctor.run_all(quick=quick))


@tool("quota_status", "Show how much of today's free model quota has been used, by you and by background work.", {}, agent="System Agent")
def quota_status(args, ctx):
    b = budget.status()
    return (f"Today: {b['used']}/{b['daily_limit']} model calls ({b['percent']}%). "
            f"You: {b['operator']}. Background study and thinking: {b['background']}/{b['background_limit']}"
            f"{' — background is paused to protect your quota' if not b['background_allowed'] else ''}.")


@tool("apply_change", "Install the self-modification you prepared, now that the operator has approved it.", {}, agent="System Agent")
async def apply_change(args, ctx):
    return await selfdev.apply_pending()
