# -*- coding: utf-8 -*-
"""Semantic memory (RAG) — vector recall over conversations and knowledge.

Deliberately lightweight: vectors live in the existing SQLite database and are
compared with numpy. No Chroma/FAISS server to run on a free VM.

Embedding backends, in order of preference:
  1. fastembed  (local ONNX, ~50 MB, no key, CPU-friendly)
  2. an OpenAI-compatible /embeddings endpoint (if a key is configured)
  3. none -> the system falls back to keyword search, which still works
"""
import json
import struct
import asyncio
import httpx
from . import memory
from .config import load_settings

_backend = {"kind": None, "model": None, "dim": 0}


def _init_backend():
    if _backend["kind"] is not None:
        return _backend
    try:
        from fastembed import TextEmbedding
        _backend["model"] = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        _backend["kind"] = "fastembed"
        _backend["dim"] = 384
        return _backend
    except Exception:
        pass
    s = load_settings()
    if s.get("openai_api_key"):
        _backend["kind"] = "api"
        _backend["dim"] = 1536
    else:
        _backend["kind"] = "none"
    return _backend


def available() -> bool:
    return _init_backend()["kind"] in ("fastembed", "api")


def backend_name() -> str:
    b = _init_backend()
    return {"fastembed": "local (bge-small)", "api": "OpenAI-compatible API", "none": "keyword only"}[b["kind"]]


async def embed(texts):
    """Return a list of float vectors, or [] when no backend is available."""
    b = _init_backend()
    texts = [t[:2000] for t in texts if t]
    if not texts or b["kind"] == "none":
        return []
    if b["kind"] == "fastembed":
        def _run():
            return [list(map(float, v)) for v in b["model"].embed(texts)]
        return await asyncio.to_thread(_run)
    s = load_settings()
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{s['openai_base_url'].rstrip('/')}/embeddings",
                             headers={"Authorization": f"Bearer {s['openai_api_key']}"},
                             json={"model": s.get("embed_model", "text-embedding-3-small"), "input": texts})
            r.raise_for_status()
            return [d["embedding"] for d in r.json()["data"]]
    except Exception:
        return []


def _pack(vec):
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob):
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def _ensure_table():
    memory.db().execute("CREATE TABLE IF NOT EXISTS vectors(id INTEGER PRIMARY KEY, kind TEXT, ref INTEGER, text TEXT, vec BLOB)")
    memory.db().commit()


async def index(text: str, kind: str = "memory", ref: int = 0) -> bool:
    """Store one item with its embedding for semantic recall."""
    if not available() or not text:
        return False
    vecs = await embed([text])
    if not vecs:
        return False
    _ensure_table()
    memory.db().execute("INSERT INTO vectors(kind, ref, text, vec) VALUES (?,?,?,?)",
                        (kind, ref, text[:2000], _pack(vecs[0])))
    memory.db().commit()
    return True


async def search(query: str, k: int = 5):
    """Semantic nearest-neighbour search. Returns [{text, score, kind}]."""
    if not available() or not query:
        return []
    _ensure_table()
    rows = memory.db().execute("SELECT kind, text, vec FROM vectors").fetchall()
    if not rows:
        return []
    qv = await embed([query])
    if not qv:
        return []
    try:
        import numpy as np
        q = np.array(qv[0], dtype="float32")
        qn = q / (np.linalg.norm(q) + 1e-9)
        scored = []
        for r in rows:
            v = np.array(_unpack(r["vec"]), dtype="float32")
            if v.shape != q.shape:
                continue
            scored.append((float(qn @ (v / (np.linalg.norm(v) + 1e-9))), r["text"], r["kind"]))
        scored.sort(reverse=True)
        return [{"score": round(s, 3), "text": t, "kind": k_} for s, t, k_ in scored[:k] if s > 0.35]
    except Exception:
        return []


async def hybrid_recall(query: str, k: int = 5) -> str:
    """Semantic + keyword recall merged — the best of both, de-duplicated."""
    sem = await search(query, k)
    kw = memory.recall(query, k)
    seen, out = set(), []
    for s in sem:
        key = s["text"][:80]
        if key not in seen:
            seen.add(key)
            out.append(f"[semantic {s['score']}] {s['text']}")
    for r in kw:
        key = r["text"][:80]
        if key not in seen:
            seen.add(key)
            out.append(f"[{r['ts']}] {r['text']}")
    return "\n".join(out[:k * 2])


async def backfill(limit=300) -> str:
    """Index existing memories and lessons that have no vector yet."""
    if not available():
        return f"No embedding backend available ({backend_name()}). Install fastembed for semantic recall."
    _ensure_table()
    have = {r["text"][:80] for r in memory.db().execute("SELECT text FROM vectors").fetchall()}
    rows = memory.db().execute("SELECT id, text FROM memories ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    rows += memory.db().execute("SELECT id, (topic || ' — ' || lesson || ': ' || substr(content,1,600)) AS text FROM knowledge ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    todo = [r for r in rows if r["text"] and r["text"][:80] not in have]
    n = 0
    for i in range(0, len(todo), 32):
        batch = todo[i:i + 32]
        vecs = await embed([b["text"] for b in batch])
        if not vecs:
            break
        for b, v in zip(batch, vecs):
            memory.db().execute("INSERT INTO vectors(kind, ref, text, vec) VALUES (?,?,?,?)",
                                ("memory", b["id"], b["text"][:2000], _pack(v)))
            n += 1
        memory.db().commit()
    return f"Indexed {n} items for semantic recall using {backend_name()}."
