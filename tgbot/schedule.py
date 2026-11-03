"""Build a daily timetable and a weekly view from tasks + recurring tasks."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

WORK_START = os.getenv("WORK_START", "09:00")
WORK_END = os.getenv("WORK_END", "19:00")
DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_NAMES = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
PRIO = {"high": 0, "normal": 1, "low": 2}


def _min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(minutes: int) -> str:
    minutes = max(0, min(minutes, 24 * 60 - 1))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def recurring_for(day: date, recurring: list[dict]) -> list[dict]:
    key = DAY_KEYS[day.weekday()]
    out = []
    for r in recurring:
        days = r.get("days", [])
        if "daily" in days or key in days or ("weekdays" in days and day.weekday() < 5):
            out.append({
                "id": f"r{r['id']}", "title": f"🔁 {r['title']}", "date": day.isoformat(), "time": r.get("time"),
                "duration_min": int(r.get("duration_min") or 30), "priority": "normal", "status": "open",
                "owner": r.get("owner"),
            })
    return out


def build_day(tasks: list[dict], day: date, recurring: list[dict] | None = None, today: date | None = None) -> list[dict]:
    """Returns slots: {"start","end","task"} sorted by time.

    Fixed-time tasks keep their time. Tasks without time (for this day, plus overdue and undated open
    tasks when `day` is today) are put into free gaps inside the working day, high priority first.
    """
    today = today or date.today()
    iso = day.isoformat()
    open_tasks = [t for t in tasks if t.get("status") == "open"]
    todays = [t for t in open_tasks if t.get("date") == iso]
    if day == today:
        todays += [t for t in open_tasks if not t.get("date") or t["date"] < iso]
    todays += recurring_for(day, recurring or [])

    fixed = sorted([t for t in todays if t.get("time")], key=lambda t: t["time"])
    floating = sorted([t for t in todays if not t.get("time")],
                      key=lambda t: (PRIO.get(t.get("priority"), 1), t.get("date") or "9999"))

    slots = []
    busy = []
    for t in fixed:
        s = _min(t["time"])
        e = s + int(t.get("duration_min") or 30)
        slots.append({"start": _hhmm(s), "end": _hhmm(e), "task": t})
        busy.append((s, e))
    busy.sort()

    cursor = _min(WORK_START)
    if day == today:
        now = datetime.now()
        cursor = max(cursor, now.hour * 60 + now.minute)
        cursor = ((cursor + 14) // 15) * 15  # round up to the next quarter hour
    end_of_day = _min(WORK_END)
    for t in floating:
        dur = int(t.get("duration_min") or 30)
        while True:
            clash = next(((s, e) for s, e in busy if s < cursor + dur and e > cursor), None)
            if not clash:
                break
            cursor = clash[1]
        if cursor + dur > end_of_day:
            slots.append({"start": None, "end": None, "task": t})  # does not fit today
            continue
        slots.append({"start": _hhmm(cursor), "end": _hhmm(cursor + dur), "task": t})
        busy.append((cursor, cursor + dur))
        busy.sort()
        cursor += dur + 5  # 5 minute buffer between tasks

    slots.sort(key=lambda s: s["start"] or "99:99")
    return slots


def _line(slot: dict) -> str:
    t = slot["task"]
    flag = "🔴 " if t.get("priority") == "high" else ""
    owner = f" — {t['owner']}" if t.get("owner") else ""
    tid = f" [#{t['id']}]" if isinstance(t.get("id"), int) else ""
    when = f"{slot['start']}–{slot['end']}" if slot["start"] else "⏳ vaqt yetmadi"
    return f"{when}  {flag}{t['title']}{owner}{tid}"


def day_text(tasks: list[dict], day: date, recurring: list[dict] | None = None) -> str:
    slots = build_day(tasks, day, recurring)
    head = f"📅 {DAY_NAMES[day.weekday()]}, {day.strftime('%d.%m.%Y')}"
    if not slots:
        return head + "\n\nVazifalar yo'q ✨ / Задач нет"
    return head + "\n\n" + "\n".join(_line(s) for s in slots)


def week_text(tasks: list[dict], start: date, recurring: list[dict] | None = None, days: int = 7) -> str:
    blocks = []
    for i in range(days):
        d = start + timedelta(days=i)
        slots = build_day(tasks, d, recurring)
        lines = "\n".join("  " + _line(s) for s in slots) or "  —"
        blocks.append(f"▫️ {DAY_NAMES[d.weekday()]} {d.strftime('%d.%m')}\n{lines}")
    return "🗓 Haftalik jadval / Расписание на неделю\n\n" + "\n\n".join(blocks)


def day_markdown(tasks: list[dict], day: date, recurring: list[dict] | None = None) -> str:
    slots = build_day(tasks, day, recurring)
    rows = ["| Vaqt | Vazifa | Kim | Muhimlik |", "|---|---|---|---|"]
    for s in slots:
        t = s["task"]
        when = f"{s['start']}–{s['end']}" if s["start"] else "sig'madi"
        rows.append(f"| {when} | {t['title']} | {t.get('owner') or ''} | {t.get('priority', 'normal')} |")
    return f"# Kun rejasi {day.isoformat()} ({DAY_NAMES[day.weekday()]})\n\n" + "\n".join(rows) + "\n"
