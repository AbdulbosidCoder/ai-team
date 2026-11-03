"""Telegram bot: reads your chats, builds the daily timetable, content plans and recurring business tasks.

Run:  python3 tgbot/bot.py        (settings come from .env or environment variables, see .env.example)
"""
from __future__ import annotations

import logging
import os
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db  # noqa: E402
import extract  # noqa: E402
import money  # noqa: E402
import schedule  # noqa: E402
import store  # noqa: E402


def _load_env() -> None:
    env = store.ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

from telegram import Update  # noqa: E402
from telegram.ext import (  # noqa: E402
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("tgbot")

TZ = ZoneInfo(os.getenv("TZ_NAME", "Asia/Tashkent"))
ALLOWED = {int(x) for x in re.findall(r"-?\d+", os.getenv("ALLOWED_USER_IDS", ""))}

HELP = """🤖 AI yordamchi — kunlik reja, content plan, biznes avtomatlashtirish

📥 Bot guruh/chatdagi xabarlarni o'qib, ulardan vazifalarni ajratadi.

Jadval:
/today — bugungi kun rejasi
/tomorrow — ertangi reja
/week — 7 kunlik jadval
/tasks — ochiq vazifalar ro'yxati
/add <matn> — vazifa qo'shish (masalan: /add ertaga 15:00 mijoz bilan uchrashuv)
/done <id> — bajarildi
/scan — yangi xabarlardan hozir vazifa ajratish

Xarajatlar (Uzcard / Humo):
• karta xabarini (HUMO bot, CardXabar, SMS) shu botga forward qiling — avtomatik yoziladi
/xarajat 25000 taksi — qo'lda xarajat
/kirim 3000000 oylik — kirim
/hisobot [today|week|month] — hisobot
/sms — telefondagi karta SMS larini o'qish (Termux)

Content:
/plan <mavzu> [kunlar] — content plan (masalan: /plan qahvaxona 14)

Avtomatlashtirish:
/every <daily|weekdays|mon,tue..> <HH:MM> <vazifa> — takrorlanuvchi vazifa
/recurring — takrorlanuvchilar ro'yxati
/unevery <id> — o'chirish

Sozlamalar:
/here — kunlik hisobotni shu chatga yuborish
/settime HH:MM — kunlik hisobot vaqti
/whoami — Telegram ID ingiz

(Русский: /today /week /add /plan — то же самое.)"""


def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()


def allowed(update: Update) -> bool:
    if not ALLOWED:
        return True
    user = update.effective_user
    return bool(user and user.id in ALLOWED)


async def guard(update: Update) -> bool:
    if allowed(update):
        return True
    await update.effective_message.reply_text("⛔ Ruxsat yo'q. /whoami bilan ID ni egasiga yuboring.")
    return False


async def reply_long(update: Update, text: str) -> None:
    for i in range(0, len(text), 4000):
        await update.effective_message.reply_text(text[i:i + 4000])


# ---------- message capture ----------

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not (msg.text or msg.caption):
        return
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private" and allowed(update):
        tx = money.parse_notification(msg.text or msg.caption, received=msg.date.astimezone(TZ).isoformat())
        if tx:
            added = money.add([tx])
            sign = "➖" if tx["kind"] == "expense" else "➕"
            await msg.reply_text(
                (f"💳 Yozildi: {sign} {money._fmt(tx['amount'])} · {tx['card']} {tx['card_last4']}\n"
                 f"{tx['merchant'] or ''} ({tx['category']})") if added else "Bu operatsiya allaqachon yozilgan.")
            return
    sender = (user.username and f"@{user.username}") or (user.full_name if user else "?")
    store.save_message(
        chat_id=chat.id,
        chat_title=chat.title or chat.full_name or str(chat.id),
        sender=sender,
        date=msg.date.astimezone(TZ),
        text=msg.text or msg.caption,
        msg_id=msg.message_id,
    )


# ---------- commands ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP)


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    await update.effective_message.reply_text(f"User ID: {u.id}\nChat ID: {update.effective_chat.id}")


def _settings_recurring() -> list[dict]:
    return store.load_settings().get("recurring", [])


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update):
        await reply_long(update, schedule.day_text(store.load_tasks(), today(), _settings_recurring()))


async def cmd_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update):
        d = today() + timedelta(days=1)
        await reply_long(update, schedule.day_text(store.load_tasks(), d, _settings_recurring()))


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await guard(update):
        await reply_long(update, schedule.week_text(store.load_tasks(), today(), _settings_recurring()))


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    open_tasks = [t for t in store.load_tasks() if t["status"] == "open"]
    if not open_tasks:
        await update.effective_message.reply_text("Ochiq vazifalar yo'q ✨")
        return
    open_tasks.sort(key=lambda t: (t.get("date") or "9999", t.get("time") or "99"))
    lines = [
        f"#{t['id']} {t.get('date') or '—'} {t.get('time') or ''} {'🔴 ' if t.get('priority') == 'high' else ''}{t['title']}"
        for t in open_tasks
    ]
    await reply_long(update, "📋 Ochiq vazifalar:\n" + "\n".join(lines))


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    text = " ".join(context.args) if context.args else ""
    if not text and update.effective_message.reply_to_message:
        text = update.effective_message.reply_to_message.text or ""
    if not text:
        await update.effective_message.reply_text("Misol: /add ertaga 15:00 mijoz bilan uchrashuv")
        return
    added = store.add_tasks(extract.parse_single(text, today()))
    if not added:
        await update.effective_message.reply_text("Bu vazifa allaqachon bor.")
        return
    await update.effective_message.reply_text(
        "✅ Qo'shildi:\n" + "\n".join(f"#{t['id']} {t.get('date') or ''} {t.get('time') or ''} {t['title']}" for t in added)
    )


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    ids = [int(x) for x in re.findall(r"\d+", " ".join(context.args or []))]
    if not ids:
        await update.effective_message.reply_text("Misol: /done 3")
        return
    done = [t for t in (store.set_status(i, "done") for i in ids) if t]
    await update.effective_message.reply_text(
        "✔️ Bajarildi: " + ", ".join(f"#{t['id']} {t['title']}" for t in done) if done else "Bunday ID topilmadi."
    )


async def run_scan() -> tuple[list[dict], str, int]:
    settings = store.load_settings()
    since = extract.parse_iso(settings.get("last_scan"))
    msgs = store.load_messages(since=since)
    tasks, engine = extract.extract_tasks(msgs, today())
    added = store.add_tasks(tasks)
    settings["last_scan"] = now().isoformat()
    store.save_settings(settings)
    return added, engine, len(msgs)


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    added, engine, n = await run_scan()
    head = f"🔎 {n} ta yangi xabar o'qildi ({engine}). Yangi vazifalar: {len(added)}"
    body = "\n".join(f"#{t['id']} {t.get('date') or '—'} {t.get('time') or ''} {t['title']}" for t in added)
    await reply_long(update, head + ("\n" + body if body else ""))


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    args = list(context.args or [])
    days = 7
    if args and args[-1].isdigit():
        days = max(1, min(31, int(args.pop())))
    topic = " ".join(args).strip()
    if not topic:
        await update.effective_message.reply_text("Misol: /plan onlayn kurs sotuvi 14")
        return
    await update.effective_message.reply_text("⏳ Content plan tayyorlanmoqda…")
    plan, engine = extract.content_plan(topic, days, start=today() + timedelta(days=1),
                                        platforms=os.getenv("PLATFORMS", "Instagram, Telegram, YouTube Shorts"))
    md = extract.plan_to_markdown(topic, plan)
    store.PLAN_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"\W+", "-", topic.lower()).strip("-")[:40] or "plan"
    path = store.PLAN_DIR / f"{today().isoformat()}-{slug}.md"
    path.write_text(md, encoding="utf-8")
    # Each content day becomes a prep task in the timetable.
    store.add_tasks([
        {"title": f"🎬 {d['format']}: {d['topic']} ({d['platform']})", "date": d["date"], "time": None,
         "duration_min": 90, "priority": "normal", "source": f"plan:{path.name}"}
        for d in plan
    ])
    lines = [f"{d['date'][5:]} · {d['platform']} · {d['format']}\n   {d['topic']}\n   🪝 {d['hook']}" for d in plan]
    await reply_long(update, f"📆 Content plan ({engine}) — {topic}\n\n" + "\n".join(lines)
                     + f"\n\nFayl: out/plan/{path.name}. Har kun jadvalga qo'shildi (/week).")


async def cmd_spent(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str = "expense") -> None:
    if not await guard(update):
        return
    args = list(context.args or [])
    m = re.match(r"^([\d\s.,]+?)(k|ming|тыс|mln|млн)?$", args[0].lower()) if args else None
    if not m:
        await update.effective_message.reply_text("Misol: /xarajat 25000 taksi   yoki   /xarajat 150k kafe")
        return
    amount = float(m.group(1).replace(" ", "").replace(",", "."))
    amount *= {"k": 1e3, "ming": 1e3, "тыс": 1e3, "mln": 1e6, "млн": 1e6}.get(m.group(2) or "", 1)
    note = " ".join(args[1:]) or ("xarajat" if kind == "expense" else "kirim")
    tx = money.manual(amount, note, kind=kind)
    await update.effective_message.reply_text(
        f"{'➖' if kind == 'expense' else '➕'} {money._fmt(tx['amount'])} · {note} ({tx['category']})")


async def cmd_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_spent(update, context, kind="income")


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    period = (context.args[0].lower() if context.args else "month")
    period = {"bugun": "today", "kecha": "yesterday", "hafta": "week", "oy": "month", "сегодня": "today",
              "неделя": "week", "месяц": "month"}.get(period, period)
    await reply_long(update, money.report(period, today()))


async def cmd_sms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    r = money.import_sms()
    if not r["ok"]:
        await update.effective_message.reply_text("⚠️ " + r["error"])
        return
    await update.effective_message.reply_text(
        f"📩 {r['checked']} ta SMS ko'rildi, {r['found']} ta karta operatsiyasi, yangi: {r['added']}.\n/hisobot today")


async def sms_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    before = len(money.load())
    r = money.import_sms()
    chat_id = store.load_settings().get("report_chat_id")
    if r.get("ok") and r.get("added") and chat_id:
        new = money.load()[before:]
        lines = [f"{'➖' if t['kind'] == 'expense' else '➕'} {money._fmt(t['amount'])} {t['merchant'] or t['card']}" for t in new[-10:]]
        await context.bot.send_message(chat_id, "💳 Yangi operatsiyalar:\n" + "\n".join(lines))


DAY_ALIASES = {
    "du": "mon", "se": "tue", "chor": "wed", "pay": "thu", "ju": "fri", "sha": "sat", "yak": "sun",
    "пн": "mon", "вт": "tue", "ср": "wed", "чт": "thu", "пт": "fri", "сб": "sat", "вс": "sun",
    "har kuni": "daily", "каждый день": "daily", "ish kunlari": "weekdays", "будни": "weekdays",
}


async def cmd_every(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    text = " ".join(context.args or [])
    m = re.match(r"\s*(\S+)\s+([01]?\d|2[0-3])[:.]([0-5]\d)\s+(.+)", text)
    if not m:
        await update.effective_message.reply_text(
            "Misol:\n/every daily 09:00 Kunlik reja ko'rib chiqish\n/every mon,thu 18:00 Hisobot yuborish\n"
            "/every weekdays 10:00 Instagramga story"
        )
        return
    raw_days = [DAY_ALIASES.get(d.lower(), d.lower()[:3]) for d in m.group(1).split(",")]
    days = ["daily" if d in ("dai", "daily") else "weekdays" if d in ("wee", "weekdays") else d for d in raw_days]
    valid = set(schedule.DAY_KEYS) | {"daily", "weekdays"}
    if not all(d in valid for d in days):
        await update.effective_message.reply_text("Kunlar: daily, weekdays yoki mon,tue,wed,thu,fri,sat,sun")
        return
    settings = store.load_settings()
    rec = settings.setdefault("recurring", [])
    rid = max((r["id"] for r in rec), default=0) + 1
    rec.append({"id": rid, "days": days, "time": f"{int(m.group(2)):02d}:{m.group(3)}", "title": m.group(4).strip()})
    store.save_settings(settings)
    await update.effective_message.reply_text(f"🔁 Qo'shildi r{rid}: {','.join(days)} {m.group(2)}:{m.group(3)} {m.group(4)}")


async def cmd_recurring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    rec = _settings_recurring()
    text = "\n".join(f"r{r['id']}: {','.join(r['days'])} {r['time']} {r['title']}" for r in rec) or "Yo'q"
    await update.effective_message.reply_text("🔁 Takrorlanuvchi vazifalar:\n" + text)


async def cmd_unevery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    ids = {int(x) for x in re.findall(r"\d+", " ".join(context.args or []))}
    settings = store.load_settings()
    before = len(settings.get("recurring", []))
    settings["recurring"] = [r for r in settings.get("recurring", []) if r["id"] not in ids]
    store.save_settings(settings)
    await update.effective_message.reply_text(f"O'chirildi: {before - len(settings['recurring'])}")


async def cmd_here(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    settings = store.load_settings()
    settings["report_chat_id"] = update.effective_chat.id
    store.save_settings(settings)
    await update.effective_message.reply_text(f"📨 Kunlik hisobot shu chatga, har kuni {settings['daily_time']} da.")


async def cmd_settime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    m = re.fullmatch(r"([01]?\d|2[0-3])[:.]([0-5]\d)", " ".join(context.args or []).strip())
    if not m:
        await update.effective_message.reply_text("Misol: /settime 07:30")
        return
    settings = store.load_settings()
    settings["daily_time"] = f"{int(m.group(1)):02d}:{m.group(2)}"
    store.save_settings(settings)
    schedule_daily(context.application)
    await update.effective_message.reply_text(f"⏰ Kunlik hisobot vaqti: {settings['daily_time']}")


# ---------- daily job ----------

async def daily_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = store.load_settings()
    chat_id = settings.get("report_chat_id")
    added, engine, n = await run_scan()
    d = today()
    text = schedule.day_text(store.load_tasks(), d, settings.get("recurring", []))
    (store.OUT_DIR / f"{d.isoformat()}.md").write_text(
        schedule.day_markdown(store.load_tasks(), d, settings.get("recurring", [])), encoding="utf-8")
    if not chat_id:
        log.info("No report chat set (/here); daily plan saved to out/timetable only")
        return
    head = f"☀️ Xayrli tong! {n} ta yangi xabardan {len(added)} ta vazifa topildi ({engine}).\n\n"
    if money.load():
        text += "\n\n" + money.report("yesterday", d)
    for i in range(0, len(head + text), 4000):
        await context.bot.send_message(chat_id, (head + text)[i:i + 4000])


async def reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every 5 minutes: remind about fixed-time tasks starting in the next 15 minutes."""
    settings = store.load_settings()
    chat_id = settings.get("report_chat_id")
    if not chat_id:
        return
    n = now()
    sent = set(settings.get("reminded", []))
    slots = schedule.build_day(store.load_tasks(), n.date(), settings.get("recurring", []), today=n.date())
    changed = False
    for s in slots:
        t = s["task"]
        if not (t.get("time") and s["start"]):
            continue
        start = datetime.combine(n.date(), time.fromisoformat(s["start"]), TZ)
        key = f"{n.date().isoformat()}:{t['id']}"
        if timedelta(0) <= start - n <= timedelta(minutes=15) and key not in sent:
            await context.bot.send_message(chat_id, f"⏰ {s['start']} — {t['title']}")
            sent.add(key)
            changed = True
    if changed:
        settings["reminded"] = sorted(sent)[-200:]
        store.save_settings(settings)


async def flush_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    db.flush()


def schedule_daily(app: Application) -> None:
    for job in app.job_queue.get_jobs_by_name("daily"):
        job.schedule_removal()
    hh, mm = store.load_settings()["daily_time"].split(":")
    app.job_queue.run_daily(daily_job, time=time(int(hh), int(mm), tzinfo=TZ), name="daily")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN topilmadi. .env.example dan .env yarating va tokenni yozing.")
    app = Application.builder().token(token).build()
    commands = {
        "start": cmd_start, "help": cmd_start, "whoami": cmd_whoami,
        "today": cmd_today, "tomorrow": cmd_tomorrow, "week": cmd_week, "tasks": cmd_tasks,
        "add": cmd_add, "done": cmd_done, "scan": cmd_scan, "plan": cmd_plan,
        "every": cmd_every, "recurring": cmd_recurring, "unevery": cmd_unevery,
        "here": cmd_here, "settime": cmd_settime,
        "xarajat": cmd_spent, "spent": cmd_spent, "rashod": cmd_spent, "kirim": cmd_income, "income": cmd_income,
        "hisobot": cmd_report, "report": cmd_report, "sms": cmd_sms,
    }
    for name, fn in commands.items():
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, on_message))
    schedule_daily(app)
    app.job_queue.run_repeating(reminder_job, interval=300, first=30, name="reminders")
    if os.getenv("SMS_AUTO_IMPORT", "0") == "1":
        app.job_queue.run_repeating(sms_job, interval=900, first=60, name="sms")
    app.job_queue.run_repeating(flush_job, interval=600, first=600, name="db-flush")
    log.info("Bot ishga tushdi. Daily report at %s (%s)", store.load_settings()["daily_time"], TZ)
    base_url = (os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
    try:
        if base_url:
            # Webhook mode (Render free web service): Telegram calls us, so the service wakes up on messages.
            secret = re.sub(r"[^A-Za-z0-9_-]", "", token.split(":")[-1])[:64] or "tg"
            app.run_webhook(
                listen="0.0.0.0",
                port=int(os.getenv("PORT", "10000")),
                url_path=f"tg/{secret[:16]}",
                webhook_url=f"{base_url}/tg/{secret[:16]}",
                secret_token=secret,
                allowed_updates=Update.ALL_TYPES,
            )
        else:
            app.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        db.flush()


if __name__ == "__main__":
    main()
