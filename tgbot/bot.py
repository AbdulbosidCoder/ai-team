"""Telegram bot: reads your chats, builds the daily timetable, content plans and recurring business tasks.

Run:  python3 tgbot/bot.py        (settings come from .env or environment variables, see .env.example)
"""
from __future__ import annotations

import asyncio
import json
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
import agent  # noqa: E402
import montaj  # noqa: E402
import schedule  # noqa: E402
import userbot  # noqa: E402
import store  # noqa: E402


db.load_env_files()  # already ran when store imported db; kept so the order is explicit

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

💬 AI agent (Claude Code): shu chatga oddiy matn yozing — savol, topshiriq, "bugun kim nima yozdi?"
/new — yangi suhbat   /ai — agent va Telegram ulanishi holati   /sync — o'z chatlaringizni hozir o'qish

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

Montaj (Android telefonda):
• botga video yuboring (20 MB gacha) — pauzalar kesiladi, subtitr + muqova, tayyor Reel qaytadi
  (video izohi = sarlavha / muqova matni)
/edit — inbox/ dagi kliplar; /edit 1 — montaj; /edit ~/storage/downloads/v.mp4 — katta fayl

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
        if agent_on() and msg.text:
            context.application.create_task(_agent_reply(update, context, msg.text))
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
    if userbot.configured():                 # pull your own chats first, so the plan sees the latest messages
        await run_userbot("sync")
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


# ---------- AI agent (Claude Code) and your own Telegram (userbot) ----------

def agent_on() -> bool:
    """Free text in the private chat goes to Claude Code. Only with ALLOWED_USER_IDS set: the agent runs commands."""
    return bool(ALLOWED) and os.getenv("AGENT", "auto") != "no" and agent.ready() is None


async def _agent_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    msg = update.effective_message
    chat_id = update.effective_chat.id

    async def typing():
        while True:
            try:
                await context.bot.send_chat_action(chat_id, "typing")
            except Exception:
                pass
            await asyncio.sleep(4.5)

    ticker = asyncio.create_task(typing())
    try:
        settings = store.load_settings()
        res = await agent.ask(text, settings.get("agent_session"))
    finally:
        ticker.cancel()
    if res["session_id"]:
        settings = store.load_settings()
        settings["agent_session"] = res["session_id"]
        store.save_settings(settings)
    if res["error"] and not res["text"]:
        await msg.reply_text("⚠️ Agent xatosi: " + str(res["error"])[:900])
        return
    await reply_long(update, res["text"] or "(bo'sh javob)")


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    settings = store.load_settings()
    settings["agent_session"] = None
    store.save_settings(settings)
    await update.effective_message.reply_text("🆕 Yangi suhbat boshlandi.")


async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    problem = agent.ready()
    lines = [
        "🤖 Agent (Claude Code): " + ("✅ yoqilgan — oddiy matn yozing" if agent_on() else "❌ o'chiq"),
        *( [f"   {problem}"] if problem else []),
        *( ["   ALLOWED_USER_IDS bo'sh: agent faqat egasi uchun ishlaydi (/whoami → .env)"] if not ALLOWED else []),
        "📨 Telegram (sizning akkauntingiz): " + ("✅ ulangan" if userbot.configured() else
                                                 "❌ ulanmagan — python3 tgbot/userbot.py login"),
    ]
    await update.effective_message.reply_text("\n".join(lines))


async def run_userbot(*args: str) -> dict:
    proc = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name("userbot.py")), *args,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    lines = [ln for ln in out.decode(errors="replace").splitlines() if ln.startswith("{")]
    if not lines:
        return {"ok": False, "error": err.decode(errors="replace")[-500:]}
    return json.loads(lines[-1])


async def userbot_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save new messages from your own chats; card notifications become expenses."""
    if not userbot.configured():
        return
    res = await run_userbot("sync")
    if not res.get("ok"):
        log.warning("userbot sync failed: %s", res.get("error"))
        return
    chat_id = store.load_settings().get("report_chat_id")
    if res.get("expenses_added") and chat_id:
        lines = [f"{'➖' if t['kind'] == 'expense' else '➕'} {money._fmt(t['amount'])} {t.get('merchant') or ''}"
                 for t in res["expenses"]]
        await context.bot.send_message(chat_id, "💳 Yangi operatsiyalar:\n" + "\n".join(lines))


async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    if not userbot.configured():
        await update.effective_message.reply_text("📨 Telegram akkaunt ulanmagan. Termux: python3 tgbot/userbot.py login")
        return
    res = await run_userbot("sync")
    await update.effective_message.reply_text(
        f"📨 {res.get('chats', 0)} ta chatdan {res.get('messages_saved', 0)} ta xabar saqlandi, "
        f"{res.get('expenses_added', 0)} ta karta operatsiyasi." if res.get("ok") else f"⚠️ {res.get('error')}")


# ---------- montaj (video edit, on the phone) ----------

TG_DOWNLOAD_LIMIT = 20 * 1024 * 1024   # Bot API: getFile works up to 20 MB


async def _run_edit(msg, src: Path, hint: str | None) -> None:
    """Edit in the background and send the result back to the same chat."""
    status = await msg.reply_text("⏳ Montaj navbatga qo'yildi…")

    async def progress(text):
        try:
            await status.edit_text(text)
        except Exception:
            pass

    try:
        res = await montaj.edit(src, hint, progress)
    except Exception as e:  # noqa: BLE001
        log.exception("montaj failed")
        await status.edit_text(f"❌ Montaj xatosi: {str(e)[:900]}")
        return
    caption = (f"🎬 {res['title']}\n"
               f"⏱ {res['raw_seconds']} s → {res['edit_seconds']} s (−{res['removed_seconds']} s)\n"
               f"🖼 Muqova: {res['cover_text']}\n📁 {res['folder']}/")
    await status.edit_text("📤 Yuborilmoqda…")
    with open(res["cover"], "rb") as f:
        await msg.reply_photo(f, caption="Muqova (cover)", read_timeout=120, write_timeout=120)
    with open(res["send"], "rb") as f:
        await msg.reply_video(f, caption=caption[:1000], supports_streaming=True, width=1080, height=1920,
                              read_timeout=600, write_timeout=600)
    note = "" if res["send"] == res["edit"] else "\n(Telegram uchun 720p nusxa; asl 1080p fayl telefonda)"
    await status.edit_text("✅ Tayyor. Hech narsa joylanmadi — tekshirib, o'zingiz post qiling." + note)


async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if update.effective_chat.type != "private" or not await guard(update):
        return
    problem = montaj.ready()
    if problem:
        await msg.reply_text("🎬 Montaj bu qurilmada ishlamaydi: " + problem)
        return
    media = msg.video or msg.document
    if media.file_size and media.file_size > TG_DOWNLOAD_LIMIT:
        await msg.reply_text(
            f"📦 Video {media.file_size / 1048576:.0f} MB — Telegram botga faqat 20 MB gacha yuklab olishga ruxsat beradi.\n"
            "Videoni telefondagi Download papkasiga saqlang va yozing:\n/edit ~/storage/downloads/<fayl>.mp4\n"
            "yoki /edit — inbox/ dagi kliplar ro'yxati.")
        return
    name = getattr(media, "file_name", None) or f"tg_{msg.date.astimezone(TZ):%Y%m%d_%H%M%S}.mp4"
    montaj.INBOX.mkdir(parents=True, exist_ok=True)
    dst = montaj._unique(montaj.INBOX / (montaj.safe_name(name) + (Path(name).suffix.lower() or ".mp4")))
    tg_file = await media.get_file()
    await tg_file.download_to_drive(dst)
    context.application.create_task(_run_edit(msg, dst, msg.caption))


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/edit — list clips in inbox/; /edit 2 or /edit <file or path> [| cover text] — edit one."""
    if not await guard(update):
        return
    msg = update.effective_message
    problem = montaj.ready()
    if problem:
        await msg.reply_text("🎬 Montaj bu qurilmada ishlamaydi: " + problem)
        return
    arg = " ".join(context.args or [])
    target, _, hint = arg.partition("|")
    target, hint = target.strip(), hint.strip() or None
    found = montaj.clips()
    if not target:
        if not found:
            await msg.reply_text("📭 inbox/ bo'sh. Botga video yuboring (20 MB gacha) yoki:\n/edit ~/storage/downloads/video.mp4")
            return
        lines = [f"{i}. {p.name} ({p.stat().st_size / 1048576:.0f} MB)" for i, p in enumerate(found, 1)]
        await msg.reply_text("🎞 inbox/ dagi kliplar:\n" + "\n".join(lines) +
                             "\n\nMontaj: /edit 1   (muqova matni bilan: /edit 1 | UCH SO'Z MATN)")
        return
    if target.isdigit() and 1 <= int(target) <= len(found):
        src = found[int(target) - 1]
    else:
        p = Path(target).expanduser()
        p = p if p.is_absolute() else (montaj.INBOX / target if (montaj.INBOX / target).exists() else montaj.ROOT / target)
        if not p.is_file() or not montaj.is_video(p):
            await msg.reply_text(f"❓ Video topilmadi: {target}")
            return
        src = montaj.take_in(p)
    context.application.create_task(_run_edit(msg, src, hint))


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
        "edit": cmd_edit, "montaj": cmd_edit,
        "new": cmd_new, "ai": cmd_ai, "sync": cmd_sync,
    }
    for name, fn in commands.items():
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.VIDEO | filters.Document.VIDEO), on_video))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, on_message))
    schedule_daily(app)
    app.job_queue.run_repeating(reminder_job, interval=300, first=30, name="reminders")
    if os.getenv("SMS_AUTO_IMPORT", "0") == "1":
        app.job_queue.run_repeating(sms_job, interval=900, first=60, name="sms")
    app.job_queue.run_repeating(flush_job, interval=600, first=600, name="db-flush")
    app.job_queue.run_repeating(userbot_job, interval=60 * int(os.getenv("TG_SYNC_MINUTES", "10")), first=90,
                                name="userbot-sync")
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
