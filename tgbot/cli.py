"""Command line for the skills (and for phones without the bot running).

python3 tgbot/cli.py import <result.json>   import a Telegram Desktop chat export (JSON)
python3 tgbot/cli.py scan                   pull tasks out of new saved messages
python3 tgbot/cli.py today | tomorrow | week
python3 tgbot/cli.py add "ertaga 15:00 mijoz bilan uchrashuv"
python3 tgbot/cli.py done <id>
python3 tgbot/cli.py plan "<topic>" [days]

Each command prints one JSON line with its result (same convention as the other skill scripts).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract  # noqa: E402
import schedule  # noqa: E402
import store  # noqa: E402


def _text(field) -> str:
    if isinstance(field, str):
        return field
    if isinstance(field, list):
        return "".join(p if isinstance(p, str) else p.get("text", "") for p in field)
    return ""


def import_export(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    chats = data.get("chats", {}).get("list") if "chats" in data else [data]
    count = 0
    for chat in chats or []:
        cid = chat.get("id", 0)
        title = chat.get("name") or str(cid)
        for m in chat.get("messages", []):
            if m.get("type") != "message":
                continue
            text = _text(m.get("text"))
            if not text.strip():
                continue
            try:
                when = datetime.fromisoformat(m["date"])
            except (KeyError, ValueError):
                continue
            store.save_message(cid, title, m.get("from") or "?", when, text, m.get("id"))
            count += 1
    return {"ok": True, "imported": count, "chats": len(chats or [])}


def main(argv: list[str]) -> dict:
    if not argv:
        return {"ok": False, "error": __doc__}
    cmd, args = argv[0], argv[1:]
    settings = store.load_settings()
    rec = settings.get("recurring", [])
    today = date.today()
    if cmd == "import":
        return import_export(args[0])
    if cmd == "scan":
        since = extract.parse_iso(settings.get("last_scan"))
        msgs = store.load_messages(since=since)
        tasks, engine = extract.extract_tasks(msgs, today)
        added = store.add_tasks(tasks)
        settings["last_scan"] = datetime.now().astimezone().isoformat()
        store.save_settings(settings)
        return {"ok": True, "messages": len(msgs), "engine": engine, "added": added}
    if cmd in ("today", "tomorrow"):
        d = today + timedelta(days=1 if cmd == "tomorrow" else 0)
        md = schedule.day_markdown(store.load_tasks(), d, rec)
        out = store.OUT_DIR / f"{d.isoformat()}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        return {"ok": True, "file": str(out.relative_to(store.ROOT)), "text": schedule.day_text(store.load_tasks(), d, rec)}
    if cmd == "week":
        text = schedule.week_text(store.load_tasks(), today, rec)
        out = store.OUT_DIR / f"week-{today.isoformat()}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        return {"ok": True, "file": str(out.relative_to(store.ROOT)), "text": text}
    if cmd == "add":
        return {"ok": True, "added": store.add_tasks(extract.parse_single(" ".join(args), today))}
    if cmd == "done":
        return {"ok": True, "done": [store.set_status(int(i), "done") for i in args]}
    if cmd == "plan":
        days = int(args[1]) if len(args) > 1 and args[1].isdigit() else 7
        plan, engine = extract.content_plan(args[0], days, start=today + timedelta(days=1))
        slug = re.sub(r"\W+", "-", args[0].lower()).strip("-")[:40] or "plan"
        out = store.PLAN_DIR / f"{today.isoformat()}-{slug}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(extract.plan_to_markdown(args[0], plan), encoding="utf-8")
        return {"ok": True, "engine": engine, "file": str(out.relative_to(store.ROOT)), "days": len(plan)}
    return {"ok": False, "error": f"unknown command {cmd}"}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:]), ensure_ascii=False))
