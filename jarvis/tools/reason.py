# -*- coding: utf-8 -*-
"""Deep reasoning and perception tools."""
import base64
import httpx
from . import tool
from .. import brain, council


@tool("deep_think",
      "Convene your council for a hard question: several specialists reason in parallel, a critic attacks the draft, and you deliver a verified answer. Use for complex, high-stakes or multi-part problems.",
      {"question": "the problem", "context": "optional extra detail"}, agent="Research Agent")
async def deep_think(args, ctx):
    return await council.deliberate(args.get("question", ""), args.get("context", ""))


@tool("verify",
      "Check a claim, plan or piece of work for errors before you rely on it. Returns the issues found, or confirms it is sound.",
      {"content": "what to check", "domain": "optional field, e.g. physics, code, legal"}, agent="Research Agent")
async def verify(args, ctx):
    dom = args.get("domain", "")
    sys = (f"You are a ruthless {dom} reviewer. List concrete errors, unsupported claims, missing steps and risks. "
           "Be specific and brief. If it is sound, say NO ISSUES and why it holds.")
    return await brain.complete([{"role": "system", "content": sys},
                                 {"role": "user", "content": args.get("content", "")}], temperature=0.1, timeout=180)


@tool("see_image",
      "Look at an image and describe or analyse it — a photo, screenshot, diagram, or a document to read.",
      {"url": "image URL", "question": "what to determine about it"}, agent="Browser Agent")
async def see_image(args, ctx):
    url = args.get("url", "")
    q = args.get("question") or "Describe this image precisely, including any text you can read."
    try:
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
        b64 = base64.b64encode(r.content).decode()
        return await brain.describe_image(b64, q)
    except Exception as e:
        return f"Could not read that image: {e}"
