# -*- coding: utf-8 -*-
"""Image generation and document grounding — the creative and NotebookLM-style
powers, native and free."""
import re
import json
import asyncio
import httpx
from pathlib import Path
from urllib.parse import quote
from . import tool
from .. import brain, memory, rag
from ..config import FILES_DIR
from .preview import _publish, SHELL


@tool("generate_image",
      "Create an image from a description — concept art, diagrams, logos, mockups, illustrations. Free, no key needed. It appears in the live window and is saved to Files.",
      {"prompt": "what to draw", "style": "optional e.g. photorealistic, blueprint, anime, 3d render",
       "width": "optional px", "height": "optional px"}, agent="Coding Agent")
async def generate_image(args, ctx):
    desc = (args.get("prompt") or "").strip()
    if not desc:
        return "What should I create, sir?"
    style = args.get("style") or ""
    full = f"{desc}, {style}" if style else desc
    w = int(args.get("width") or 1024)
    h = int(args.get("height") or 1024)
    url = f"https://image.pollinations.ai/prompt/{quote(full[:400])}?width={w}&height={h}&nologo=true"
    name = re.sub(r"[^a-z0-9]+", "_", desc.lower())[:40] or "image"
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            data = r.content
        p = FILES_DIR / f"{name}.jpg"
        p.write_bytes(data)
        import base64
        b64 = base64.b64encode(data).decode()
        body = (f'<div style="padding:10px;text-align:center">'
                f'<img src="data:image/jpeg;base64,{b64}" style="max-width:100%;border-radius:8px">'
                f'<div style="color:#8fa8c8;font-size:12px;margin-top:8px">{desc[:120]}</div></div>')
        _publish(name, SHELL.format(body=body), "image", desc[:40])
        memory.add_event("file", f"Image generated: {desc[:60]}")
        return f"Created **{desc[:60]}** — it is in the live window and saved as `{p.name}` in Files."
    except Exception as e:
        return f"Image generation failed: {e}"


@tool("ingest_document",
      "Read a document into permanent memory so it can be questioned later — a PDF, text, markdown, code or CSV file in the workspace.",
      {"path": "file path"}, agent="Memory Agent")
async def ingest_document(args, ctx):
    from .filesystem import _safe
    try:
        p = _safe(args.get("path", ""))
    except Exception as e:
        return str(e)
    if not p.exists():
        return f"No such file: {p}"
    text = ""
    if p.suffix.lower() == ".pdf":
        try:
            import pypdf
            text = " ".join((pg.extract_text() or "") for pg in pypdf.PdfReader(str(p)).pages)
        except Exception as e:
            return f"Could not read the PDF: {e}"
    else:
        text = p.read_text(encoding="utf-8", errors="replace")
    if len(text.strip()) < 30:
        return f"{p.name} had no readable text."
    chunks = [text[i:i + 1200] for i in range(0, min(len(text), 120000), 1000)]
    stored = 0
    for i, ch in enumerate(chunks):
        memory.add_lesson(f"Document: {p.name}", f"part {i+1}", ch)
        if rag.available():
            if await rag.index(f"[{p.name} part {i+1}] {ch}", kind="document"):
                stored += 1
    memory.add_event("file", f"Ingested {p.name} ({len(chunks)} sections)")
    return (f"Read **{p.name}** into memory — {len(chunks)} sections"
            f"{f', {stored} semantically indexed' if stored else ''}. Ask me anything about it.")


@tool("ask_documents", "Answer a question using only the documents that have been read into memory, with quotes.",
      {"question": "what to find out"}, agent="Memory Agent")
async def ask_documents(args, ctx):
    q = args.get("question", "")
    ctxt = memory.recall_knowledge(q, k=6, max_chars=8000)
    if rag.available():
        sem = await rag.search(q, k=6)
        ctxt += "\n\n" + "\n".join(s["text"] for s in sem if s.get("kind") == "document")
    if not ctxt.strip():
        return "No documents in memory match that. Use ingest_document first, sir."
    return await brain.complete([{"role": "user", "content":
        f"QUESTION: {q}\n\nDOCUMENT EXTRACTS:\n{ctxt[:12000]}\n\n"
        "Answer using only these extracts. Quote the relevant lines. If they do not contain the answer, say so."}],
        temperature=0.2, timeout=240)
