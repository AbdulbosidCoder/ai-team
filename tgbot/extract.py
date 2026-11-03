"""Turn Telegram chat messages into tasks (and content plans).

Two engines:
- Claude (anthropic SDK, structured JSON output) when credentials are available;
- a rule-based parser (Uzbek / Russian / English keywords, dates and times) as a fallback,
  so the bot keeps working with no API key and no internet to the API.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta

log = logging.getLogger(__name__)

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
USE_CLAUDE = os.getenv("USE_CLAUDE", "auto").lower()  # auto | yes | no

TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short imperative task, in the chat's language"},
                    "date": {"type": ["string", "null"], "description": "YYYY-MM-DD or null if no day was said"},
                    "time": {"type": ["string", "null"], "description": "HH:MM 24h or null"},
                    "duration_min": {"type": "integer"},
                    "owner": {"type": ["string", "null"], "description": "Who must do it, if named"},
                    "priority": {"type": "string", "enum": ["high", "normal", "low"]},
                    "source": {"type": "string", "description": "The message text the task came from"},
                },
                "required": ["title", "date", "time", "duration_min", "owner", "priority", "source"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["tasks"],
    "additionalProperties": False,
}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "days": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "platform": {"type": "string"},
                    "format": {"type": "string", "description": "reel, post, story, carousel, long video..."},
                    "topic": {"type": "string"},
                    "hook": {"type": "string", "description": "First line / first 3 seconds"},
                    "goal": {"type": "string", "description": "reach, trust, sales..."},
                    "prep_tasks": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["date", "platform", "format", "topic", "hook", "goal", "prep_tasks"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["days"],
    "additionalProperties": False,
}

TASK_SYSTEM = (
    "You read messages from a team's Telegram chats (Uzbek, Russian or English, often mixed) and pull out "
    "concrete things someone has to do: tasks, meetings, calls, deadlines, deliveries, payments, shoots. "
    "Ignore greetings, jokes, opinions and things already reported as done. Resolve relative dates "
    "(bugun/ertaga/indinga, сегодня/завтра/послезавтра, today/tomorrow, weekday names) against TODAY. "
    "Keep each title short and in the language of the message. Estimate duration_min realistically "
    "(meeting 60, call 15, small task 30). Use priority high only for deadlines, money or clients waiting. "
    "If nothing needs doing, return an empty list."
)


def _client():
    import anthropic  # imported lazily so the rule engine works without the package

    return anthropic.Anthropic()


def _claude_json(system: str, user: str, schema: dict) -> dict:
    client = _client()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined the request")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude output was cut off")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def _want_claude() -> bool:
    if USE_CLAUDE == "no":
        return False
    if USE_CLAUDE == "yes":
        return True
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


# ---------------- tasks ----------------

def extract_tasks(messages: list[dict], today: date | None = None) -> tuple[list[dict], str]:
    """Returns (tasks, engine_name)."""
    today = today or date.today()
    if not messages:
        return [], "none"
    if _want_claude():
        lines = [
            f"[{m.get('date', '')[:16]}] {m.get('chat', '')} / {m.get('from', '')}: {m.get('text', '')}"
            for m in messages
        ]
        user = f"TODAY is {today.isoformat()} ({today.strftime('%A')}).\n\nMessages:\n" + "\n".join(lines)
        try:
            data = _claude_json(TASK_SYSTEM, user, TASK_SCHEMA)
            return [_clean(t) for t in data.get("tasks", [])], "claude"
        except Exception as e:  # network, auth, refusal… fall back, never crash the bot
            log.warning("Claude extraction failed, using rules: %s", e)
    tasks = []
    for m in messages:
        tasks.extend(rule_extract(m.get("text", ""), today, owner_hint=None, source=m.get("text", "")))
    return tasks, "rules"


def _clean(t: dict) -> dict:
    t = dict(t)
    if t.get("time") and not re.fullmatch(r"\d{2}:\d{2}", t["time"]):
        t["time"] = None
    if t.get("date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["date"]):
        t["date"] = None
    return t


# Keyword lists: Uzbek (latin + cyrillic), Russian, English.
TASK_WORDS = [
    # uz
    "kerak", "qilish", "qiling", "qilamiz", "vazifa", "topshir", "yubor", "tayyorla", "uchrashuv", "majlis",
    "qo'ng'iroq", "qongiroq", "to'lov", "tolov", "deadline", "muddat", "suratga", "montaj", "yozib", "jo'nat",
    "keling", "boramiz", "eslatma", "unutma",
    # uz cyrillic
    "керак", "вазифа", "учрашув", "мажлис",
    # ru
    "нужно", "надо", "сделать", "сделай", "задача", "встреча", "созвон", "звонок", "отправ", "подготов",
    "срок", "дедлайн", "оплат", "напомни", "не забудь", "съёмк", "съемк",
    # en
    "todo", "to do", "task", "need to", "must", "should", "meeting", "call", "send", "prepare", "deadline",
    "remind", "don't forget", "shoot", "deliver", "pay",
]

WEEKDAYS = {
    0: ["dushanba", "понедельник", "monday", "душанба"],
    1: ["seshanba", "вторник", "tuesday", "сешанба"],
    2: ["chorshanba", "среда", "среду", "wednesday", "чоршанба"],
    3: ["payshanba", "четверг", "thursday", "пайшанба"],
    4: ["juma", "пятница", "пятницу", "friday", "жума"],
    5: ["shanba", "суббота", "субботу", "saturday", "шанба"],
    6: ["yakshanba", "воскресенье", "sunday", "якшанба"],
}

TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
HOUR_RE = re.compile(
    r"(?:soat|в|at|к)\s*([01]?\d|2[0-3])(?:\s*(?:da|ga|часов|час|ч|am|pm))?\b|"
    r"\b([01]?\d|2[0-3])\s*(?:da|ga|часов|часа|ч|am|pm)\b",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?!\d)")


def _find_date(text: str, today: date) -> date | None:
    low = text.lower()
    if any(w in low for w in ["indinga", "послезавтра", "day after tomorrow"]):
        return today + timedelta(days=2)
    if any(w in low for w in ["ertaga", "эртага", "завтра", "tomorrow"]):
        return today + timedelta(days=1)
    if any(w in low for w in ["bugun", "бугун", "сегодня", "today", "hozir", "сейчас", "tonight", "kechqurun"]):
        return today
    m = DATE_RE.search(text)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        if y < 100:
            y += 2000
        try:
            found = date(y, mo, d)
            if not m.group(3) and found < today - timedelta(days=30):
                found = date(y + 1, mo, d)
            return found
        except ValueError:
            pass
    for wd, words in WEEKDAYS.items():
        # "shanba" is inside "yakshanba/dushanba…" so match on word boundaries
        if any(re.search(rf"(?<![a-zа-яё']){re.escape(w)}", low) for w in words):
            delta = (wd - today.weekday()) % 7
            return today + timedelta(days=delta or 7)
    return None


def _find_time(text: str) -> str | None:
    m = TIME_RE.search(text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = HOUR_RE.search(text)
    if m:
        h = int(m.group(1) or m.group(2))
        if "pm" in m.group(0).lower() and h < 12:
            h += 12
        return f"{h:02d}:00"
    return None


def _priority(low: str) -> str:
    if any(w in low for w in ["srochno", "shoshilinch", "срочно", "urgent", "asap", "muhim", "важно", "deadline", "дедлайн"]):
        return "high"
    return "normal"


def _duration(low: str) -> int:
    if any(w in low for w in ["uchrashuv", "majlis", "встреча", "meeting", "suratga", "съемк", "съёмк", "shoot"]):
        return 60
    if any(w in low for w in ["qo'ng'iroq", "qongiroq", "созвон", "звонок", "call"]):
        return 15
    return 30


def rule_extract(text: str, today: date, owner_hint: str | None = None, source: str | None = None,
                 force: bool = False) -> list[dict]:
    """One message -> 0..n tasks. `force=True` treats the text as a task even without keywords (/add)."""
    if not text or text.startswith("/"):
        return []
    tasks = []
    # Split numbered / bulleted lists into separate tasks.
    parts = [p.strip(" -•*\t") for p in re.split(r"\n+|(?:^|\s)\d+[).]\s", text) if p.strip(" -•*\t")]
    whole_date = _find_date(text, today)
    for part in parts or [text]:
        low = part.lower()
        has_kw = any(w in low for w in TASK_WORDS)
        when = _find_time(part)
        if not (force or has_kw or (when and whole_date)):
            continue
        d = _find_date(part, today) or whole_date
        mention = re.search(r"@(\w+)", part)
        tasks.append({
            "title": re.sub(r"\s+", " ", part)[:120],
            "date": d.isoformat() if d else (today.isoformat() if force else None),
            "time": when,
            "duration_min": _duration(low),
            "owner": f"@{mention.group(1)}" if mention else owner_hint,
            "priority": _priority(low),
            "source": (source or text)[:300],
        })
    return tasks


def parse_single(text: str, today: date | None = None) -> list[dict]:
    """For /add: always produce at least one task."""
    today = today or date.today()
    if _want_claude():
        try:
            data = _claude_json(
                TASK_SYSTEM + " The user is adding tasks directly, so every line is a task; if no day is said use TODAY.",
                f"TODAY is {today.isoformat()} ({today.strftime('%A')}).\n\nMessages:\n{text}",
                TASK_SCHEMA,
            )
            tasks = [_clean(t) for t in data.get("tasks", [])]
            if tasks:
                return tasks
        except Exception as e:
            log.warning("Claude /add failed, using rules: %s", e)
    return rule_extract(text, today, force=True, source=text)


# ---------------- content plan ----------------

PLAN_SYSTEM = (
    "You are a content strategist for a small business. Build a practical content calendar: one item per day, "
    "mixing formats (reels, carousels, stories, posts), alternating goals (reach, trust, sales), each with a "
    "scroll-stopping hook and 2-4 concrete prep tasks. Write in the language of the topic text. "
    "Follow the brand rules if given."
)

FORMATS = ["Reel", "Carousel", "Stories", "Post", "Reel", "Live / Q&A", "Reel"]
GOALS = ["reach", "trust", "sales", "reach", "trust", "sales", "trust"]
ANGLES = [
    ("Xato / ошибка", "3 xato: {t} bo'yicha ko'pchilik qiladigan"),
    ("Qanday qilib / как", "{t}: 60 soniyada qanday qilish kerak"),
    ("Sahna ortidan / закулисье", "Biz {t} ni qanday qilamiz — sahna ortidan"),
    ("Mijoz natijasi / кейс", "Mijozimiz {t} bilan nimaga erishdi"),
    ("Mif / миф", "{t} haqida eng katta mif"),
    ("Savol-javob / Q&A", "{t} bo'yicha savollaringizga javob"),
    ("Taklif / оффер", "{t}: bu hafta uchun maxsus taklif"),
]


def content_plan(topic: str, days: int = 7, start: date | None = None,
                 platforms: str = "Instagram, Telegram, YouTube Shorts", brand_rules: str = "") -> tuple[list[dict], str]:
    start = start or date.today()
    if _want_claude():
        try:
            user = (
                f"Topic / business: {topic}\nPlatforms: {platforms}\nStart date: {start.isoformat()}\n"
                f"Number of days: {days}\nBrand rules: {brand_rules or 'none'}"
            )
            data = _claude_json(PLAN_SYSTEM, user, PLAN_SCHEMA)
            return data["days"][:days], "claude"
        except Exception as e:
            log.warning("Claude plan failed, using template: %s", e)
    plat = [p.strip() for p in platforms.split(",") if p.strip()] or ["Instagram"]
    plan = []
    for i in range(days):
        name, hook = ANGLES[i % len(ANGLES)]
        plan.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "platform": plat[i % len(plat)],
            "format": FORMATS[i % len(FORMATS)],
            "topic": f"{name}: {topic}",
            "hook": hook.format(t=topic),
            "goal": GOALS[i % len(GOALS)],
            "prep_tasks": ["Ssenariy yozish / сценарий", "Suratga olish / съёмка", "Montaj + cover", "Caption + post"],
        })
    return plan, "template"


def plan_to_markdown(topic: str, plan: list[dict]) -> str:
    out = [f"# Content plan: {topic}", "", "| Sana | Platforma | Format | Mavzu | Hook | Maqsad |", "|---|---|---|---|---|---|"]
    for d in plan:
        out.append(f"| {d['date']} | {d['platform']} | {d['format']} | {d['topic']} | {d['hook']} | {d['goal']} |")
    out.append("")
    out.append("## Tayyorgarlik vazifalari / Prep tasks")
    for d in plan:
        out.append(f"- **{d['date']}**: " + "; ".join(d.get("prep_tasks", [])))
    return "\n".join(out) + "\n"


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None
