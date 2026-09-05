# -*- coding: utf-8 -*-
"""Live preview — 0.5.4.M.4 renders working things into a window on the
dashboard that the operator can see and interact with immediately."""
import re
import json
import secrets
import time
from pathlib import Path
from . import tool
from .. import memory
from ..config import DATA_DIR

PREVIEW_DIR = DATA_DIR / "previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
LATEST = DATA_DIR / "preview_latest.json"

SHELL = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{margin:0;font-family:system-ui,sans-serif;background:#0a1020;color:#dbe9ff}}</style>
</head><body>{body}</body></html>"""


def _clean_old(keep_seconds=86400, keep_max=40):
    """Previews are transient: drop old ones so nothing lingers on disk."""
    try:
        files = sorted(PREVIEW_DIR.glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True)
        now = time.time()
        for i, f in enumerate(files):
            if i >= keep_max or now - f.stat().st_mtime > keep_seconds:
                f.unlink(missing_ok=True)
    except Exception:
        pass


def _publish(name: str, html: str, kind: str, title: str):
    # Previews are served without a token so the dashboard iframe can render
    # them, so the FILENAME is the secret: a guessable name like
    # "salary_report.html" would let anyone who knows the address read private
    # content. Every preview therefore gets 128 bits of randomness.
    stem = re.sub(r"[^a-z0-9]+", "_", Path(name).stem.lower())[:32] or "preview"
    name = f"{stem}_{secrets.token_urlsafe(16)}.html"
    _clean_old()
    p = PREVIEW_DIR / name
    p.write_text(html, encoding="utf-8")
    LATEST.write_text(json.dumps({"name": name, "title": title, "kind": kind, "ts": memory.now()}), encoding="utf-8")
    memory.add_event("file", f"Preview opened: {title}")
    return f"Opened **{title}** in the live window on your dashboard, sir — you can interact with it there."


def latest():
    try:
        return json.loads(LATEST.read_text(encoding="utf-8"))
    except Exception:
        return None


@tool("show_preview",
      "Render something into the live window on the operator's dashboard so they can SEE and INTERACT with it right now — a web page, app UI, form, game, animation or demo. Use whenever you build anything visual.",
      {"title": "short name", "html": "complete HTML (may include <style> and <script>)"},
      agent="Coding Agent")
def show_preview(args, ctx):
    html = args.get("html", "")
    m = re.search(r"```(?:html)?\s*(.*?)```", html, re.DOTALL)
    if m:
        html = m.group(1)
    if "<html" not in html.lower():
        html = SHELL.format(body=html)
    title = args.get("title") or "Preview"
    return _publish(title, html, "html", title)


@tool("show_chart",
      "Draw a chart in the operator's live window: line, bar, pie, scatter or radar. Give the data and it renders interactively.",
      {"title": "chart title", "type": "line|bar|pie|doughnut|scatter|radar",
       "labels": "list of x labels", "series": "[{\"name\": str, \"data\": [numbers]}]"},
      agent="Coding Agent")
def show_chart(args, ctx):
    title = args.get("title") or "Chart"
    ctype = (args.get("type") or "line").lower()
    labels = args.get("labels") or []
    series = args.get("series") or []
    if isinstance(labels, str):
        labels = [x.strip() for x in labels.split(",") if x.strip()]
    if isinstance(series, str):
        try:
            series = json.loads(series)
        except Exception:
            series = []
    colors = ["#38e6ff", "#3fa9ff", "#39ffb0", "#ffb347", "#ff4d6d", "#b388ff"]
    datasets = [{"label": s.get("name", f"Series {i+1}"), "data": s.get("data", []),
                 "borderColor": colors[i % len(colors)],
                 "backgroundColor": colors[i % len(colors)] + ("cc" if ctype in ("pie", "doughnut") else "33"),
                 "borderWidth": 2, "tension": 0.35, "fill": ctype == "line"}
                for i, s in enumerate(series)]
    if ctype in ("pie", "doughnut") and datasets:
        datasets[0]["backgroundColor"] = colors[:len(datasets[0].get("data", []))]
    body = f"""<div style="padding:14px"><h3 style="font-family:system-ui;color:#8fd3ff;margin:0 0 10px">{title}</h3>
<canvas id="c"></canvas></div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
new Chart(document.getElementById('c'), {{
  type: {json.dumps(ctype)},
  data: {{ labels: {json.dumps(labels)}, datasets: {json.dumps(datasets)} }},
  options: {{ responsive:true, plugins:{{legend:{{labels:{{color:'#dbe9ff'}}}}}},
    scales: {json.dumps({}) if ctype in ('pie','doughnut','radar') else '{x:{ticks:{color:"#8fa8c8"},grid:{color:"#1d2c4a"}},y:{ticks:{color:"#8fa8c8"},grid:{color:"#1d2c4a"}}}'} }}
}});
</script>"""
    return _publish(title, SHELL.format(body=body), "chart", title)


@tool("show_diagram",
      "Draw a diagram or flowchart in the live window using Mermaid syntax — architecture, process flow, sequence, mind map.",
      {"title": "name", "mermaid": "mermaid source, e.g. 'graph TD; A-->B;'"}, agent="Coding Agent")
def show_diagram(args, ctx):
    title = args.get("title") or "Diagram"
    src = args.get("mermaid", "graph TD; A-->B;")
    m = re.search(r"```(?:mermaid)?\s*(.*?)```", src, re.DOTALL)
    if m:
        src = m.group(1)
    body = f"""<div style="padding:14px"><h3 style="font-family:system-ui;color:#8fd3ff;margin:0 0 10px">{title}</h3>
<pre class="mermaid">{src}</pre></div>
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
mermaid.initialize({{startOnLoad:true, theme:'dark'}});
</script>"""
    return _publish(title, SHELL.format(body=body), "diagram", title)
