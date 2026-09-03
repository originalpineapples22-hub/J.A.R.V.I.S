# -*- coding: utf-8 -*-
"""Long-term memory on SQLite: conversations, episodic memory (FTS), knowledge base,
skills, tasks, reminders, push subscriptions, intelligence-feed events."""
import re
import json
import sqlite3
import threading
from datetime import datetime
from .config import DB_FILE

_lock = threading.Lock()
_conn = None


def db():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        init(_conn)
    return _conn


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, ts TEXT, channel TEXT, role TEXT, content TEXT);
    CREATE TABLE IF NOT EXISTS summaries(id INTEGER PRIMARY KEY, ts TEXT, channel TEXT, text TEXT);
    CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, text TEXT);
    CREATE TABLE IF NOT EXISTS knowledge(id INTEGER PRIMARY KEY, ts TEXT, topic TEXT, lesson TEXT, content TEXT);
    CREATE TABLE IF NOT EXISTS skills(topic TEXT PRIMARY KEY, level TEXT, coverage TEXT, updated TEXT);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, ts TEXT, title TEXT, due TEXT, done INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, ts TEXT, when_ts TEXT, text TEXT, sent INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS push_subs(id INTEGER PRIMARY KEY, endpoint TEXT UNIQUE, sub TEXT);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, text TEXT);
    CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
    """)
    try:
        c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(text, content='memories', content_rowid='id')")
        c.execute("""CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN
                     INSERT INTO mem_fts(rowid, text) VALUES (new.id, new.text); END;""")
        c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS know_fts USING fts5(topic, lesson, content, content='knowledge', content_rowid='id')")
        c.execute("""CREATE TRIGGER IF NOT EXISTS know_ai AFTER INSERT ON knowledge BEGIN
                     INSERT INTO know_fts(rowid, topic, lesson, content) VALUES (new.id, new.topic, new.lesson, new.content); END;""")
        c.execute("INSERT OR REPLACE INTO kv(key, value) VALUES('fts', '1')")
    except sqlite3.OperationalError:
        c.execute("INSERT OR REPLACE INTO kv(key, value) VALUES('fts', '0')")
    c.commit()


def has_fts():
    r = db().execute("SELECT value FROM kv WHERE key='fts'").fetchone()
    return bool(r and r["value"] == "1")


def _q(sql, args=()):
    with _lock:
        cur = db().execute(sql, args)
        db().commit()
        return cur


def _fts_query(text: str) -> str:
    words = [w for w in re.findall(r"[a-zA-Z0-9]{3,}", text.lower())][:12]
    return " OR ".join(f'"{w}"' for w in words) if words else ""


# ---------------- conversation
def add_message(channel, role, content):
    _q("INSERT INTO messages(ts, channel, role, content) VALUES (?,?,?,?)", (now(), channel, role, content))


def recent_messages(channel, n=12):
    rows = db().execute("SELECT role, content FROM messages WHERE channel=? ORDER BY id DESC LIMIT ?", (channel, n)).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def message_count(channel=None):
    if channel:
        return db().execute("SELECT COUNT(*) FROM messages WHERE channel=?", (channel,)).fetchone()[0]
    return db().execute("SELECT COUNT(*) FROM messages").fetchone()[0]


def set_summary(channel, text):
    _q("INSERT INTO summaries(ts, channel, text) VALUES (?,?,?)", (now(), channel, text))


def get_summary(channel):
    r = db().execute("SELECT text FROM summaries WHERE channel=? ORDER BY id DESC LIMIT 1", (channel,)).fetchone()
    return r["text"] if r else ""


def older_messages(channel, keep_last=12, limit=40):
    total = message_count(channel)
    if total <= keep_last:
        return []
    rows = db().execute("SELECT id, role, content FROM messages WHERE channel=? ORDER BY id DESC LIMIT ? OFFSET ?",
                        (channel, limit, keep_last)).fetchall()
    return [{"id": r["id"], "role": r["role"], "content": r["content"]} for r in reversed(rows)]


def summarized_upto(channel):
    r = db().execute("SELECT value FROM kv WHERE key=?", (f"sum_upto:{channel}",)).fetchone()
    return int(r["value"]) if r else 0


def set_summarized_upto(channel, msg_id):
    _q("INSERT OR REPLACE INTO kv(key, value) VALUES (?,?)", (f"sum_upto:{channel}", str(msg_id)))


# ---------------- episodic memory
def remember(text, kind="exchange"):
    _q("INSERT INTO memories(ts, kind, text) VALUES (?,?,?)", (now(), kind, text[:1500]))


def recall(query, k=6):
    q = _fts_query(query)
    if not q:
        return []
    if has_fts():
        rows = db().execute("SELECT m.ts, m.kind, m.text FROM mem_fts f JOIN memories m ON m.id=f.rowid WHERE mem_fts MATCH ? ORDER BY rank LIMIT ?", (q, k)).fetchall()
    else:
        words = re.findall(r"[a-zA-Z0-9]{3,}", query.lower())[:6]
        rows = db().execute("SELECT ts, kind, text FROM memories WHERE " + " OR ".join("lower(text) LIKE ?" for _ in words) + " ORDER BY id DESC LIMIT ?",
                            tuple(f"%{w}%" for w in words) + (k,)).fetchall() if words else []
    return [dict(r) for r in rows]


def memory_count():
    return db().execute("SELECT COUNT(*) FROM memories").fetchone()[0]


# ---------------- knowledge / skills
def add_lesson(topic, lesson, content):
    _q("INSERT INTO knowledge(ts, topic, lesson, content) VALUES (?,?,?,?)", (now(), topic, lesson, content))


def set_skill(topic, level, coverage):
    _q("INSERT OR REPLACE INTO skills(topic, level, coverage, updated) VALUES (?,?,?,?)", (topic, level, coverage, now()))


def skills():
    return [dict(r) for r in db().execute("SELECT * FROM skills ORDER BY updated DESC").fetchall()]


def recall_knowledge(query, k=3, max_chars=5000):
    q = _fts_query(query)
    if not q:
        return ""
    if has_fts():
        rows = db().execute("SELECT k.topic, k.lesson, k.content FROM know_fts f JOIN knowledge k ON k.id=f.rowid WHERE know_fts MATCH ? ORDER BY rank LIMIT ?", (q, k)).fetchall()
    else:
        words = re.findall(r"[a-zA-Z0-9]{3,}", query.lower())[:6]
        rows = db().execute("SELECT topic, lesson, content FROM knowledge WHERE " + " OR ".join("lower(topic) LIKE ? OR lower(content) LIKE ?" for _ in words) + " LIMIT ?",
                            tuple(x for w in words for x in (f"%{w}%", f"%{w}%")) + (k,)).fetchall() if words else []
    out, used = [], 0
    for r in rows:
        chunk = f"### {r['topic']} — {r['lesson']}\n{r['content']}"
        if used + len(chunk) > max_chars:
            chunk = chunk[:max_chars - used]
        out.append(chunk)
        used += len(chunk)
        if used >= max_chars:
            break
    return "\n\n".join(out)


def lessons(topic=None):
    if topic:
        rows = db().execute("SELECT ts, topic, lesson, content FROM knowledge WHERE topic=? ORDER BY id", (topic,)).fetchall()
    else:
        rows = db().execute("SELECT ts, topic, lesson, substr(content,1,200) AS content FROM knowledge ORDER BY id DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]


# ---------------- tasks / reminders
def add_task(title, due=None):
    _q("INSERT INTO tasks(ts, title, due) VALUES (?,?,?)", (now(), title, due))


def tasks(include_done=False):
    sql = "SELECT * FROM tasks" + ("" if include_done else " WHERE done=0") + " ORDER BY COALESCE(due, '9999') , id"
    return [dict(r) for r in db().execute(sql).fetchall()]


def complete_task(task_id):
    _q("UPDATE tasks SET done=1 WHERE id=?", (task_id,))


def add_reminder(when_ts, text):
    _q("INSERT INTO reminders(ts, when_ts, text) VALUES (?,?,?)", (now(), when_ts, text))


def due_reminders():
    return [dict(r) for r in db().execute("SELECT * FROM reminders WHERE sent=0 AND when_ts<=? ORDER BY when_ts", (now(),)).fetchall()]


def upcoming_reminders(limit=10):
    return [dict(r) for r in db().execute("SELECT * FROM reminders WHERE sent=0 ORDER BY when_ts LIMIT ?", (limit,)).fetchall()]


def mark_reminder_sent(rid):
    _q("UPDATE reminders SET sent=1 WHERE id=?", (rid,))


# ---------------- push subs / events
def add_push_sub(sub: dict):
    _q("INSERT OR REPLACE INTO push_subs(endpoint, sub) VALUES (?,?)", (sub.get("endpoint"), json.dumps(sub)))


def push_subs():
    return [json.loads(r["sub"]) for r in db().execute("SELECT sub FROM push_subs").fetchall()]


def remove_push_sub(endpoint):
    _q("DELETE FROM push_subs WHERE endpoint=?", (endpoint,))


def add_event(kind, text):
    _q("INSERT INTO events(ts, kind, text) VALUES (?,?,?)", (now(), kind, text[:300]))


def events(limit=8):
    return [dict(r) for r in db().execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


def stats():
    c = db()
    return {
        "messages": c.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        "memories": c.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
        "lessons": c.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0],
        "skills": c.execute("SELECT COUNT(*) FROM skills").fetchone()[0],
        "tasks_open": c.execute("SELECT COUNT(*) FROM tasks WHERE done=0").fetchone()[0],
        "reminders": c.execute("SELECT COUNT(*) FROM reminders WHERE sent=0").fetchone()[0],
    }
