"""Simple JSON storage: chat messages, tasks, recurring tasks and settings.

Everything lives in plain files so Claude Code skills can read them too:
- inbox/telegram/<chat_id>.jsonl   one saved message per line
- out/timetable/tasks.json         all tasks (open and done)
- inbox/telegram/settings.json     report chat, daily time, last scan, recurring tasks
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MSG_DIR = Path(os.getenv("TG_DATA_DIR", ROOT / "inbox" / "telegram"))
OUT_DIR = ROOT / "out" / "timetable"
PLAN_DIR = ROOT / "out" / "plan"
TASKS_FILE = OUT_DIR / "tasks.json"
SETTINGS_FILE = MSG_DIR / "settings.json"

_lock = threading.Lock()

import db  # noqa: E402  (after the paths above)

_db = db.backend(
    {"tasks": TASKS_FILE, "settings": SETTINGS_FILE},
    lambda name: MSG_DIR / f"{name.split(':', 1)[1]}.jsonl",
)

DEFAULT_SETTINGS = {
    "daily_time": os.getenv("DAILY_TIME", "08:00"),
    "report_chat_id": int(os.getenv("REPORT_CHAT_ID")) if os.getenv("REPORT_CHAT_ID") else None,
    "last_scan": None,
    "recurring": [],  # {"id", "days": ["mon",..] or ["daily"], "time": "HH:MM", "title"}
}


def _ensure_dirs() -> None:
    MSG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PLAN_DIR.mkdir(parents=True, exist_ok=True)


# ---------- settings ----------

def load_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    data.update(_db.get_doc("settings", {}))
    return data


def save_settings(settings: dict) -> None:
    with _lock:
        _db.put_doc("settings", settings)


# ---------- messages ----------

def save_message(chat_id: int, chat_title: str, sender: str, date: datetime, text: str, msg_id: int | None = None) -> None:
    row = {
        "id": msg_id,
        "chat_id": chat_id,
        "chat": chat_title,
        "from": sender,
        "date": date.isoformat(),
        "text": text,
    }
    _db.append(f"messages:{chat_id}", row)


def load_messages(since: datetime | None = None) -> list[dict]:
    """All saved messages from every chat, oldest first, optionally newer than `since`."""
    rows: list[dict] = []
    for row in _db.lines("messages:"):
        if since is not None:
            try:
                if datetime.fromisoformat(row["date"]) <= since:
                    continue
            except (KeyError, ValueError, TypeError):
                continue
        rows.append(row)
    rows.sort(key=lambda r: r.get("date", ""))
    return rows


# ---------- tasks ----------

def _norm(title: str) -> str:
    return re.sub(r"\W+", " ", title.lower()).strip()


def load_tasks() -> list[dict]:
    return _db.get_doc("tasks", [])


def save_tasks(tasks: list[dict]) -> None:
    with _lock:
        _db.put_doc("tasks", tasks)


def add_tasks(new: list[dict]) -> list[dict]:
    """Add tasks, skipping duplicates (same title and date). Returns the tasks actually added."""
    tasks = load_tasks()
    seen = {(_norm(t["title"]), t.get("date")) for t in tasks}
    next_id = max((t["id"] for t in tasks), default=0) + 1
    added = []
    for t in new:
        title = (t.get("title") or "").strip()
        if not title:
            continue
        key = (_norm(title), t.get("date"))
        if key in seen:
            continue
        seen.add(key)
        task = {
            "id": next_id,
            "title": title,
            "date": t.get("date"),
            "time": t.get("time"),
            "duration_min": int(t.get("duration_min") or 30),
            "owner": t.get("owner"),
            "priority": t.get("priority") or "normal",
            "source": t.get("source"),
            "status": "open",
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        next_id += 1
        tasks.append(task)
        added.append(task)
    save_tasks(tasks)
    return added


def set_status(task_id: int, status: str) -> dict | None:
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            t["status"] = status
            save_tasks(tasks)
            return t
    return None
