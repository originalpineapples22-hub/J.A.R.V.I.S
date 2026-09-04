# -*- coding: utf-8 -*-
"""Free, no-login live-data tools: weather, prayer times, news, dictionary,
currency/crypto, world time, translate. All work immediately after deploy."""
import httpx
from datetime import datetime
from . import tool
from ..config import load_settings


async def _get(url, params=None, headers=None, timeout=12):
    async with httpx.AsyncClient(timeout=timeout, headers=headers or {"User-Agent": "0.5.4.M.4/3.0"}) as c:
        r = await c.get(url, params=params)
        r.raise_for_status()
        return r


@tool("weather", "Current weather and forecast for a city (no key needed).", {"city": "city name"}, agent="Research Agent")
async def weather(args, ctx):
    city = args.get("city") or "Muscat"
    try:
        g = (await _get("https://geocoding-api.open-meteo.com/v1/search", {"name": city, "count": 1})).json()
        if not g.get("results"):
            return f"Could not find {city}."
        loc = g["results"][0]
        w = (await _get("https://api.open-meteo.com/v1/forecast", {
            "latitude": loc["latitude"], "longitude": loc["longitude"],
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min", "forecast_days": 3, "timezone": "auto"})).json()
        cur = w["current"]; d = w["daily"]
        codes = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 61: "rain", 63: "rain", 80: "showers", 95: "thunderstorm"}
        sky = codes.get(cur["weather_code"], "mixed")
        fc = "; ".join(f"{d['time'][i][5:]}: {d['temperature_2m_min'][i]:.0f}–{d['temperature_2m_max'][i]:.0f}°C" for i in range(len(d["time"])))
        return f"{loc['name']}: {cur['temperature_2m']:.0f}°C, {sky}, humidity {cur['relative_humidity_2m']}%, wind {cur['wind_speed_10m']:.0f} km/h. Next days — {fc}."
    except Exception as e:
        return f"Weather lookup failed: {e}"


@tool("prayer_times", "Islamic prayer times for a city today (Aladhan, no key).", {"city": "city", "country": "country"}, agent="Research Agent")
async def prayer_times(args, ctx):
    city = args.get("city") or "Muscat"
    country = args.get("country") or "Oman"
    try:
        r = (await _get("https://api.aladhan.com/v1/timingsByCity", {"city": city, "country": country, "method": 8})).json()
        t = r["data"]["timings"]
        keys = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
        return f"Prayer times for {city} today — " + ", ".join(f"{k} {t[k]}" for k in keys) + "."
    except Exception as e:
        return f"Prayer time lookup failed: {e}"


@tool("news", "Top world news headlines right now.", {"topic": "optional keyword"}, agent="Research Agent")
async def news(args, ctx):
    topic = (args.get("topic") or "").strip()
    try:
        ids = (await _get("https://hacker-news.firebaseio.com/v0/topstories.json")).json()[:8]
        heads = []
        async with httpx.AsyncClient(timeout=12) as c:
            for i in ids:
                it = (await c.get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json")).json()
                if it and it.get("title"):
                    heads.append(f"- {it['title']}")
        if topic:
            from .web import web_search
            return await web_search({"query": f"{topic} latest news"}, ctx)
        return "Top tech headlines:\n" + "\n".join(heads)
    except Exception as e:
        return f"News fetch failed: {e}"


@tool("dictionary", "Define a word with meanings and synonyms.", {"word": "string"}, agent="Research Agent")
async def dictionary(args, ctx):
    w = args.get("word", "").strip()
    try:
        r = (await _get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}")).json()
        out = []
        for m in r[0]["meanings"][:3]:
            defs = "; ".join(d["definition"] for d in m["definitions"][:2])
            out.append(f"({m['partOfSpeech']}) {defs}")
        return f"{w}: " + " | ".join(out)
    except Exception:
        return f"No dictionary entry for '{w}'."


@tool("currency", "Convert currencies or get a crypto price.", {"amount": "number", "from": "e.g. USD or BTC", "to": "e.g. OMR or USD"}, agent="Research Agent")
async def currency(args, ctx):
    amt = float(args.get("amount", 1)); frm = (args.get("from") or "USD").upper(); to = (args.get("to") or "OMR").upper()
    crypto = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin", "XRP": "ripple"}
    try:
        if frm in crypto:
            r = (await _get("https://api.coingecko.com/api/v3/simple/price", {"ids": crypto[frm], "vs_currencies": to.lower()})).json()
            price = r[crypto[frm]][to.lower()]
            return f"{amt} {frm} = {amt * price:,.2f} {to} (1 {frm} = {price:,.2f} {to})."
        r = (await _get(f"https://open.er-api.com/v6/latest/{frm}")).json()
        rate = r["rates"].get(to)
        if not rate:
            return f"Unknown currency {to}."
        return f"{amt} {frm} = {amt * rate:,.2f} {to} (1 {frm} = {rate:.4f} {to})."
    except Exception as e:
        return f"Currency lookup failed: {e}"


@tool("world_time", "Current time in a city or timezone.", {"place": "city or Area/City"}, agent="Research Agent")
async def world_time(args, ctx):
    place = args.get("place", "Asia/Muscat")
    try:
        from zoneinfo import ZoneInfo, available_timezones
        tz = place if "/" in place else next((z for z in available_timezones() if place.lower() in z.lower()), None)
        if not tz:
            return f"Unknown place '{place}'. Try 'Asia/Muscat' or a city name."
        return f"Time in {tz}: {datetime.now(ZoneInfo(tz)).strftime('%A %H:%M')}."
    except Exception as e:
        return f"Time lookup failed: {e}"


@tool("translate", "Translate text to another language.", {"text": "string", "to": "language code e.g. ar, en, fr"}, agent="Research Agent")
async def translate(args, ctx):
    text = args.get("text", ""); to = args.get("to", "en")
    try:
        r = (await _get("https://api.mymemory.translated.net/get", {"q": text, "langpair": f"auto|{to}"})).json()
        return r["responseData"]["translatedText"]
    except Exception as e:
        return f"Translation failed: {e}"
