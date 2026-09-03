# -*- coding: utf-8 -*-
import re
import asyncio
import httpx
from . import tool

try:
    from duckduckgo_search import DDGS
    HAS_DDG = True
except Exception:
    HAS_DDG = False


def _ddg(query, n=5):
    try:
        with DDGS() as d:
            return list(d.text(query, max_results=n))
    except Exception:
        return []


@tool("web_search", "Search the web for current information.", {"query": "string"}, agent="Research Agent")
async def web_search(args, ctx):
    q = args.get("query", "")
    results = await asyncio.to_thread(_ddg, q) if HAS_DDG else []
    if results:
        return "\n".join(f"- {r.get('title')}: {r.get('body')} ({r.get('href')})" for r in results)
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get("https://en.wikipedia.org/w/api.php",
                            params={"action": "query", "list": "search", "srsearch": q, "format": "json"},
                            headers={"User-Agent": "JARVIS/3.0"})
            items = r.json()["query"]["search"][:5]
            return "\n".join(f"- {i['title']}: {re.sub('<[^>]+>', '', i['snippet'])}" for i in items) or "No results."
    except Exception as e:
        return f"Search failed: {e}"


@tool("fetch_url", "Read the text content of a web page.", {"url": "string"}, agent="Browser Agent")
async def fetch_url(args, ctx):
    url = args.get("url", "")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 JARVIS/3.0"}) as c:
            r = await c.get(url)
            html = r.text
        html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:6000] or "Page had no readable text."
    except Exception as e:
        return f"Fetch failed: {e}"


_YT_RE = re.compile(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})")


@tool("youtube_transcript", "Get the transcript of a YouTube video so questions about it can be answered.", {"url": "YouTube URL or video id"}, agent="Browser Agent")
async def youtube_transcript(args, ctx):
    url = args.get("url", "")
    m = _YT_RE.search(url)
    vid = m.group(1) if m else url.strip()
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        def _get():
            try:
                api = YouTubeTranscriptApi()
                tr = api.fetch(vid, languages=["en", "en-US", "ar"])
                return " ".join(s.text for s in tr)
            except AttributeError:
                tr = YouTubeTranscriptApi.get_transcript(vid, languages=["en", "en-US", "ar"])
                return " ".join(s["text"] for s in tr)
        text = await asyncio.to_thread(_get)
        return text[:12000]
    except Exception as e:
        return f"Transcript unavailable ({e}). Try fetch_url on the page for the description instead."
