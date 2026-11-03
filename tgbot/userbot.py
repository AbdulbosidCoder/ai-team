"""Read your own Telegram (MTProto, as your account, via Telethon) for the agent and the timetable. Read-only.

The bot only sees groups it was added to. This sees every chat your account sees, so the timetable and
the agent can work from your real conversations. It never sends, edits, deletes or marks anything read.

Setup (once): get api_id and api_hash at https://my.telegram.org -> API development tools, put them in .env
as TG_API_ID / TG_API_HASH, then log in in a terminal (code from Telegram, and your 2FA password if set):
    python3 tgbot/userbot.py login

Commands (each prints one JSON line):
    python3 tgbot/userbot.py chats [--limit 40]               your chats, newest first
    python3 tgbot/userbot.py read <chat> [--limit 30]         last messages of one chat (id, @username or part of the title)
    python3 tgbot/userbot.py search "<text>" [--chat <chat>] [--limit 20]
    python3 tgbot/userbot.py sync [--per-chat 100] [--days 7] save new messages to inbox/telegram for the timetable;
                                                              card notifications (HUMO, CardXabar...) go to expenses

The session file is a full login to your account: it lives in .secrets/ (git-ignored, mode 600). Never share it.
To log out: Telegram -> Settings -> Devices -> end the "ai-team" session.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402,F401  (loads .env / .env.local)

ROOT = Path(__file__).resolve().parents[1]
SECRETS = Path(os.getenv("TG_SECRETS_DIR", ROOT / ".secrets"))
SESSION = Path(os.getenv("TG_SESSION", SECRETS / "telegram"))      # Telethon adds .session
STATE = SECRETS / "userbot_state.json"                             # last synced message id per chat
CARD_HINTS = [s.strip().lower() for s in os.getenv(
    "CARD_SMS_SENDERS", "humo,uzcard,cardxabar,6464,kapitalbank,hamkorbank,agrobank,nbu,xalqbank,asakabank,tbc,anorbank").split(",") if s.strip()]


def out(**kw) -> None:
    print(json.dumps(kw, ensure_ascii=False, default=str))


def configured() -> bool:
    return bool(os.getenv("TG_API_ID") and os.getenv("TG_API_HASH") and SESSION.with_suffix(".session").exists())


@contextmanager
def one_at_a_time():
    """The bot's sync job and the agent may both call this; one session file, one connection at a time."""
    SECRETS.mkdir(parents=True, exist_ok=True)
    os.chmod(SECRETS, 0o700)
    with open(SECRETS / "telegram.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def client():
    from telethon import TelegramClient
    api_id, api_hash = os.getenv("TG_API_ID"), os.getenv("TG_API_HASH")
    if not (api_id and api_hash):
        raise SystemExit("TG_API_ID / TG_API_HASH yo'q: my.telegram.org dan olib .env ga yozing")
    return TelegramClient(str(SESSION), int(api_id), api_hash, device_model="ai-team", app_version="1.0",
                          receive_updates=False)


def kind(dialog) -> str:
    e = dialog.entity
    if dialog.is_user:
        return "bot" if getattr(e, "bot", False) else "private"
    if dialog.is_channel and not getattr(e, "megagroup", False):
        return "channel"
    return "group"


def sender_name(msg) -> str:
    s = msg.sender
    if s is None:
        return getattr(msg, "post_author", None) or "?"
    if getattr(s, "username", None):
        return "@" + s.username
    name = " ".join(x for x in (getattr(s, "first_name", None), getattr(s, "last_name", None)) if x)
    return name or getattr(s, "title", None) or str(msg.sender_id)


def row(msg, chat_title: str) -> dict:
    text = msg.message or ""
    if not text and msg.media:
        text = f"[{type(msg.media).__name__.replace('MessageMedia', '').lower()}]"
    return {"id": msg.id, "chat_id": msg.chat_id, "chat": chat_title, "from": "me" if msg.out else sender_name(msg),
            "date": msg.date.astimezone().isoformat(), "text": text}


async def find_chat(c, query: str):
    q = query.strip()
    if q.lstrip("-").isdigit() or q.startswith("@"):
        try:
            ent = await c.get_entity(int(q) if q.lstrip("-").isdigit() else q)
            return ent, getattr(ent, "title", None) or sender_name_of(ent)
        except (ValueError, TypeError):
            pass
    low = q.lower()
    async for d in c.iter_dialogs(limit=500):
        if low in (d.name or "").lower():
            return d.entity, d.name
    raise SystemExit(f"Chat topilmadi: {query}")


def sender_name_of(ent) -> str:
    if getattr(ent, "username", None):
        return "@" + ent.username
    return " ".join(x for x in (getattr(ent, "first_name", None), getattr(ent, "last_name", None)) if x) or str(ent.id)


# ---------------- commands ----------------

async def cmd_login(a) -> None:
    c = client()
    await c.start()                     # asks for phone, code and 2FA password in the terminal
    me = await c.get_me()
    await c.disconnect()
    os.chmod(SESSION.with_suffix(".session"), 0o600)
    out(ok=True, user=sender_name_of(me), id=me.id, session=str(SESSION.with_suffix(".session").relative_to(ROOT)))


async def connected():
    c = client()
    await c.connect()
    if not await c.is_user_authorized():
        await c.disconnect()
        raise SystemExit("Telegram ga kirilmagan: python3 tgbot/userbot.py login")
    return c


async def cmd_chats(a) -> None:
    c = await connected()
    rows = []
    async for d in c.iter_dialogs(limit=a.limit):
        rows.append({"id": d.id, "title": d.name, "type": kind(d), "unread": d.unread_count,
                     "last": d.date.astimezone().isoformat() if d.date else None})
    await c.disconnect()
    out(ok=True, chats=rows)


async def cmd_read(a) -> None:
    c = await connected()
    ent, title = await find_chat(c, a.chat)
    msgs = [row(m, title) async for m in c.iter_messages(ent, limit=a.limit)]
    await c.disconnect()
    out(ok=True, chat=title, messages=list(reversed(msgs)))


async def cmd_search(a) -> None:
    c = await connected()
    ent, title = (await find_chat(c, a.chat)) if a.chat else (None, None)
    msgs = []
    async for m in c.iter_messages(ent, search=a.query, limit=a.limit):
        chat_title = title or getattr(m.chat, "title", None) or (sender_name_of(m.chat) if m.chat else str(m.chat_id))
        msgs.append(row(m, chat_title))
    await c.disconnect()
    out(ok=True, query=a.query, messages=msgs)


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


async def cmd_sync(a) -> None:
    import money
    import store
    state = _load_state()
    since = datetime.now(timezone.utc) - timedelta(days=a.days)
    only = [x.strip().lower() for x in os.getenv("TG_SYNC_CHATS", "").split(",") if x.strip()]
    skip = {"channel"} if os.getenv("TG_SYNC_CHANNELS", "0") != "1" else set()
    c = await connected()
    saved, chats, txs = 0, 0, []
    async for d in c.iter_dialogs(limit=a.dialogs):
        k = kind(d)
        name = (d.name or "").lower()
        is_card = k == "bot" and any(h in name for h in CARD_HINTS)
        if k in skip or (k == "bot" and not is_card):
            continue
        if only and not any(o == str(d.id) or o in name for o in only) and not is_card:
            continue
        if d.date and d.date < since:
            continue
        last = int(state.get(str(d.id), 0))
        new = []
        async for m in c.iter_messages(d.entity, limit=a.per_chat, min_id=last):
            if m.date < since:
                break
            new.append(m)
        if not new:
            continue
        chats += 1
        for m in reversed(new):                      # oldest first
            r = row(m, d.name)
            if is_card:
                tx = money.parse_notification(r["text"], received=r["date"])
                if tx:
                    txs.extend(money.add([tx]))
                continue
            if not r["text"] or r["text"].startswith("["):
                continue
            store.save_message(chat_id=d.id, chat_title=d.name, sender=r["from"],
                               date=datetime.fromisoformat(r["date"]), text=r["text"], msg_id=m.id)
            saved += 1
        state[str(d.id)] = max(m.id for m in new)
    await c.disconnect()
    db.flush()
    SECRETS.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state), encoding="utf-8")
    out(ok=True, chats=chats, messages_saved=saved, expenses_added=len(txs),
        expenses=[{"amount": t["amount"], "kind": t["kind"], "merchant": t.get("merchant"), "card": t.get("card")} for t in txs])


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description="Read-only Telegram access (your account)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    p = sub.add_parser("chats"); p.add_argument("--limit", type=int, default=40)
    p = sub.add_parser("read"); p.add_argument("chat"); p.add_argument("--limit", type=int, default=30)
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--chat"); p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("sync"); p.add_argument("--per-chat", type=int, default=100); p.add_argument("--days", type=int, default=7)
    p.add_argument("--dialogs", type=int, default=150)
    a = ap.parse_args(argv)
    fn = {"login": cmd_login, "chats": cmd_chats, "read": cmd_read, "search": cmd_search, "sync": cmd_sync}[a.cmd]
    with one_at_a_time():
        try:
            asyncio.run(fn(a))
        except SystemExit as e:
            out(ok=False, error=str(e))
            sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
