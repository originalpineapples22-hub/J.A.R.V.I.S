# -*- coding: utf-8 -*-
"""Built-in technology curriculum + the autonomous learner.

Everything here is what 0.5.4.M.4 knows how to master. A background worker
studies the queue by itself, forever, without being asked."""
import asyncio
import random
from . import memory

LANGUAGES = [
    "Python", "JavaScript", "TypeScript", "Java", "C", "C++", "C#", "Go", "Rust", "Swift",
    "Kotlin", "Ruby", "PHP", "Dart", "Scala", "Lua", "Haskell", "Elixir", "Clojure", "R",
    "Julia", "MATLAB", "Objective-C", "x86 Assembly", "SQL", "Bash scripting", "PowerShell",
    "Zig", "Nim", "Solidity", "Verilog", "GDScript", "Perl", "F#", "OCaml", "Groovy",
]
FRAMEWORKS = [
    "React", "Next.js", "Vue.js", "Angular", "Svelte", "Node.js", "Django", "Flask", "FastAPI",
    "Spring Boot", ".NET", "Laravel", "Ruby on Rails", "Express.js", "Flutter", "React Native",
    "SwiftUI", "Tailwind CSS", "Electron", "Qt",
]
SYSTEMS = [
    "Docker", "Kubernetes", "Git", "Linux administration", "Nginx", "CI/CD pipelines",
    "Terraform", "Ansible", "AWS", "Microsoft Azure", "Google Cloud", "PostgreSQL",
    "MongoDB", "Redis", "GraphQL", "REST API design", "WebSockets", "Computer networking",
    "Cybersecurity fundamentals", "Cryptography", "System design", "Operating systems",
]
AI_DATA = [
    "Data structures and algorithms", "Machine learning", "Deep learning", "PyTorch",
    "TensorFlow", "scikit-learn", "Computer vision with OpenCV", "Natural language processing",
    "Large language models and prompt engineering", "Reinforcement learning", "Pandas and NumPy",
    "Data visualisation", "Vector databases and RAG",
]
HARDWARE_MAKER = [
    "Arduino", "Raspberry Pi", "ESP32", "Embedded C", "Real-time operating systems",
    "ROS robotics", "3D printing and slicing", "OpenSCAD parametric CAD", "Fusion 360",
    "PCB design with KiCad", "Signal processing", "Control systems", "Mechatronics",
    "Blender 3D", "Unity game engine", "Unreal Engine", "Godot engine", "Game development",
]
FINANCE = [
    "Personal finance and budgeting", "Investing fundamentals", "Stock market analysis",
    "Fundamental analysis and company valuation", "Technical analysis", "Portfolio theory and diversification",
    "Risk management and position sizing", "Bonds and fixed income", "Index funds and ETFs",
    "Banking systems and how banks make money", "Central banking and monetary policy",
    "Interest rates, inflation and the yield curve", "Islamic finance and sukuk",
    "Cryptocurrency and blockchain", "Real estate investment", "Accounting and financial statements",
    "Business models and unit economics", "Startup fundraising", "Digital marketing and growth",
    "E-commerce operations", "Taxation basics", "Behavioural finance and investor psychology",
    "Quantitative trading and backtesting", "Economics: micro and macro",
]

CATALOG = LANGUAGES + FRAMEWORKS + SYSTEMS + AI_DATA + HARDWARE_MAKER + FINANCE

# Studied first — the foundation everything else builds on.
PRIORITY = [
    "Python", "JavaScript", "TypeScript", "Data structures and algorithms", "Git",
    "SQL", "Linux administration", "React", "Node.js", "Docker", "System design",
    "Bash scripting", "REST API design", "C", "C++", "Rust", "Go", "Java",
    "Machine learning", "Large language models and prompt engineering",
    "Investing fundamentals", "Personal finance and budgeting", "Banking systems and how banks make money",
]


def ordered_catalog():
    rest = [t for t in CATALOG if t not in PRIORITY]
    return PRIORITY + rest


def learned_topics() -> set:
    return {s["topic"] for s in memory.skills()}


def next_topic():
    """The next unlearned technology, priority first."""
    known = learned_topics()
    for t in ordered_catalog():
        if t not in known:
            return t
    return None


def progress() -> dict:
    known = learned_topics()
    total = len(CATALOG)
    done = len([t for t in CATALOG if t in known])
    return {"learned": done, "total": total, "percent": round(done / total * 100, 1),
            "next": next_topic(), "extra": len(known) - done}


# ---------------------------------------------------------------- autonomous learner
_auto = {"enabled": True, "current": None, "studied": 0}


def auto_state():
    return dict(_auto, **progress())


def set_auto(enabled: bool):
    _auto["enabled"] = bool(enabled)


async def autonomous_loop():
    """Studies the catalog by itself, forever, pausing while the operator is active."""
    from .learning import start_study, status as learn_status
    from .config import load_settings
    await asyncio.sleep(60)                      # let the server settle after boot
    while True:
        try:
            s = load_settings()
            key_ok = bool(s.get("groq_api_key") or s.get("openai_api_key") or s.get("provider") == "ollama")
            if _auto["enabled"] and key_ok and not learn_status():
                topic = next_topic()
                if topic:
                    _auto["current"] = topic
                    memory.add_event("learn", f"Self-study started: {topic}")
                    start_study(topic)
                    # wait for it to finish before queueing the next
                    while learn_status():
                        await asyncio.sleep(10)
                    _auto["studied"] += 1
                    _auto["current"] = None
        except Exception as e:
            memory.add_event("system", f"Self-study loop error: {e}")
        # gentle pacing so the free API tier is never hammered
        await asyncio.sleep(random.randint(600, 900))
