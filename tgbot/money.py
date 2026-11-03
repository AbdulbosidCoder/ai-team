"""Expense tracker for Uzcard / Humo card notifications.

Sources:
- SMS on the Android phone (Termux:API `termux-sms-list`), from senders like HUMO, UZCARD, 6464, banks;
- notifications forwarded or pasted to the bot (HUMOcard bot, CardXabar, bank apps);
- manual entries: /xarajat 25000 taksi

Data: out/money/transactions.json (private, not in git).

CLI:
python3 tgbot/money.py sms                 import new card SMS (Termux only)
python3 tgbot/money.py parse "<text>"      parse one notification and save it
python3 tgbot/money.py add 25000 taksi     manual expense
python3 tgbot/money.py report [today|week|month|all]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store  # noqa: E402

MONEY_DIR = store.ROOT / "out" / "money"
TX_FILE = MONEY_DIR / "transactions.json"
import db  # noqa: E402

_db = db.backend({"transactions": TX_FILE}, lambda name: store.MSG_DIR / f"{name}.jsonl")

SMS_SENDERS = [s.strip().lower() for s in os.getenv(
    "CARD_SMS_SENDERS",
    "humo,uzcard,cardxabar,6464,kapitalbank,hamkorbank,ipoteka,agrobank,nbu,xalqbank,asakabank,tbc,anorbank,"
    "infinbank,aloqabank,davr,orient,trastbank,paynet,click,payme,uzum",
).split(",") if s.strip()]

EXPENSE_WORDS = [
    "списание", "оплата", "покупка", "pokupka", "spisanie", "oplata", "xarid", "харид", "to'lov", "tolov",
    "перевод", "perevod", "o'tkazma", "otkazma", "снятие", "snyatie", "naqd", "debit", "payment", "purchase",
    "withdraw", "yechib", "списано", "🔴", "➖",
]
INCOME_WORDS = [
    "пополнение", "popolnenie", "зачисление", "zachislenie", "kirim", "кирим", "tushum", "тушум",
    "поступление", "credit", "income", "refund", "возврат", "qaytarish", "🟢", "➕", "to'ldirish", "toldirish",
]
CATEGORIES = {
    "Oziq-ovqat / Продукты": ["korzinka", "makro", "havas", "karzinka", "baraka", "magnit", "supermarket", "market", "oziq", "продукт", "bozor"],
    "Kafe / Кафе": ["cafe", "kafe", "coffee", "restoran", "restaurant", "evos", "kfc", "oqtepa", "burger", "pizza", "lavash", "choyxona", "bellissimo", "max way", "maxway"],
    "Transport / Транспорт": ["yandex go", "yandex.go", "taxi", "taksi", "такси", "mytaxi", "metro", "benzin", "azs", "uzgasoil", "zapravka", "propan", "metan", "parking"],
    "Aloqa / Связь": ["beeline", "ucell", "uzmobile", "mobiuz", "humans", "internet", "uztelecom", "turon"],
    "Kommunal / Коммуналка": ["hududgaz", "elektr", "энерго", "suv", "issiqlik", "kommunal", "gaz"],
    "Onlayn xarid / Онлайн": ["uzum", "wildberries", "ozon", "aliexpress", "olx", "zoodmall"],
    "O'tkazma / Перевод": ["p2p", "перевод", "perevod", "o'tkazma", "otkazma", "transfer"],
    "Naqd pul / Наличные": ["atm", "банкомат", "bankomat", "снятие", "naqd"],
    "Reklama / Реклама": ["facebook", "meta", "instagram", "google", "target", "tiktok"],
    "Obuna / Подписки": ["netflix", "spotify", "apple", "icloud", "openai", "anthropic", "claude", "telegram premium", "youtube"],
    "Sog'liq / Здоровье": ["apteka", "dorixona", "аптека", "clinic", "klinika", "medical"],
}

AMOUNT_RE = re.compile(
    r"([-+➖➕]?\s*\d{1,3}(?:[   .,]\d{3})+(?:[.,]\d{1,2})?|[-+➖➕]?\s*\d+(?:[.,]\d{1,2})?)\s*"
    r"(uzs|sum|so'm|som|сум|сўм)",
    re.IGNORECASE,
)
BALANCE_HINT = re.compile(r"(balans|баланс|остаток|ostatok|qoldiq|💰|доступно|dostupno|available)", re.IGNORECASE)
CARD_RE = re.compile(r"(humo|uzcard|visa|mastercard)?[^\n\d*]{0,15}[*•x]{1,6}\s?(\d{4})", re.IGNORECASE)
DT_RE = re.compile(r"(\d{1,2}:\d{2})(?::\d{2})?\s+(\d{2})[./-](\d{2})[./-](\d{2,4})|(\d{2})[./-](\d{2})[./-](\d{2,4})\s+(\d{1,2}:\d{2})")


def _to_float(raw: str) -> float:
    s = re.sub(r"[-+➖➕\s  ]", "", raw)
    # "1.234.567,89" / "1,234,567.89" / "50 000.00" -> last separator with 1-2 digits is decimal
    m = re.search(r"[.,](\d{1,2})$", s)
    if m:
        whole, dec = s[: m.start()], m.group(1)
    else:
        whole, dec = s, "0"
    whole = re.sub(r"[.,]", "", whole)
    return float(f"{whole or 0}.{dec}")


def _card_type(text: str) -> str:
    low = text.lower()
    if "humo" in low or "хумо" in low:
        return "Humo"
    if "uzcard" in low or "узкард" in low or "cardxabar" in low:
        return "Uzcard"
    if "visa" in low:
        return "Visa"
    if "mastercard" in low:
        return "Mastercard"
    m = re.search(r"\b(9860|8600|5614|4\d{3}|5[1-5]\d{2})\d*", text)
    if m:
        return {"9860": "Humo", "8600": "Uzcard", "5614": "Uzcard"}.get(m.group(1), "Visa/MC")
    return "Karta"


def _category(text: str) -> str:
    low = text.lower()
    for cat, words in CATEGORIES.items():
        if any(w in low for w in words):
            return cat
    return "Boshqa / Прочее"


def _merchant(text: str) -> str:
    for pat in [r"📍\s*(.+)", r"(?:merchant|мерчант|торговец|место|joy|do'kon|магазин|v|в|at)\s*[:：]\s*(.+)",
                r"(?:oplata|pokupka|оплата|покупка|xarid)\s*[:：]?\s*[\d\s.,]+\s*(?:uzs|sum|сум)?\s*[,;]?\s*([A-Za-z][^\n,;]{2,40})"]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = BALANCE_HINT.split(m.group(1))[0]
            name = re.split(r"\d{2}[./]\d{2}[./]\d{2,4}|\d{1,2}:\d{2}|[💳🕓💰🏦⏰📅🔴🟢]|[*•]{1,6}\d{4}|\b(?:humo|uzcard)\w*", name, flags=re.IGNORECASE)[0]
            return re.sub(r"\s+", " ", name).strip(" .,;")[:60]
    return ""


def _when(text: str) -> str:
    m = DT_RE.search(text)
    try:
        if m and m.group(1):
            y = int(m.group(4)); y += 2000 if y < 100 else 0
            return datetime(y, int(m.group(3)), int(m.group(2)), *map(int, m.group(1).split(":"))).isoformat()
        if m and m.group(5):
            y = int(m.group(7)); y += 2000 if y < 100 else 0
            return datetime(y, int(m.group(6)), int(m.group(5)), *map(int, m.group(8).split(":"))).isoformat()
    except ValueError:
        pass
    return ""


def parse_notification(text: str, received: str | None = None) -> dict | None:
    """One card notification -> transaction dict, or None if it is not a card operation."""
    if not text:
        return None
    amounts = []
    for line in text.splitlines() or [text]:
        for m in AMOUNT_RE.finditer(line):
            if BALANCE_HINT.search(line[max(0, m.start() - 25): m.start()]):
                continue  # skip "Balans: 1 234 567 UZS"
            amounts.append(m.group(1))
    if not amounts:
        return None
    low = text.lower()
    raw = amounts[0].strip()
    has_exp = any(w in low for w in EXPENSE_WORDS)
    has_inc = any(w in low for w in INCOME_WORDS)
    if raw.startswith(("-", "➖")):
        kind = "expense"
    elif raw.startswith(("+", "➕")):
        kind = "income"
    elif has_inc and not has_exp:
        kind = "income"
    elif has_exp:
        kind = "expense"
    else:
        return None
    card = CARD_RE.search(text)
    merchant = _merchant(text)
    return {
        "kind": kind,
        "amount": _to_float(raw),
        "card": _card_type(text),
        "card_last4": card.group(2) if card else "",
        "merchant": merchant,
        "category": _category(merchant + " " + text) if kind == "expense" else "Kirim / Доход",
        "date": _when(text) or received or datetime.now().isoformat(timespec="seconds"),
        "source": "notification",
        "text": text[:500],
    }


# ---------- storage ----------

def load() -> list[dict]:
    return _db.get_doc("transactions", [])


def _save(rows: list[dict]) -> None:
    _db.put_doc("transactions", rows)


def _key(tx: dict) -> str:
    base = f"{tx['kind']}|{tx['amount']:.2f}|{tx.get('card_last4')}|{tx['date'][:16]}|{tx.get('text', '')[:80]}"
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def add(txs: list[dict]) -> list[dict]:
    rows = load()
    seen = {r["key"] for r in rows}
    added = []
    for tx in txs:
        tx["key"] = _key(tx)
        if tx["key"] in seen:
            continue
        seen.add(tx["key"])
        rows.append(tx)
        added.append(tx)
    rows.sort(key=lambda r: r["date"])
    _save(rows)
    return added


def manual(amount: float, note: str, card: str = "Naqd / Наличные", kind: str = "expense") -> dict:
    tx = {
        "kind": kind, "amount": float(amount), "card": card, "card_last4": "", "merchant": note,
        "category": _category(note) if kind == "expense" else "Kirim / Доход",
        "date": datetime.now().isoformat(timespec="seconds"), "source": "manual", "text": note,
    }
    added = add([tx])
    return added[0] if added else tx


def import_sms(limit: int = 300) -> dict:
    """Read the phone's SMS inbox via Termux:API and save card operations."""
    if not shutil.which("termux-sms-list"):
        return {"ok": False, "error": "termux-sms-list topilmadi: Termux:API ilovasi va `pkg install termux-api` kerak"}
    out = subprocess.run(["termux-sms-list", "-l", str(limit), "-t", "inbox"], capture_output=True, text=True, timeout=60)
    try:
        sms = json.loads(out.stdout or "[]")
    except json.JSONDecodeError:
        return {"ok": False, "error": out.stderr.strip() or "SMS o'qib bo'lmadi (ruxsat bering)"}
    txs = []
    for s in sms:
        sender = str(s.get("number") or s.get("sender") or "").lower()
        body = s.get("body") or ""
        if SMS_SENDERS and not any(k in sender or k in body.lower()[:40] for k in SMS_SENDERS):
            continue
        tx = parse_notification(body, received=(s.get("received") or "").replace(" ", "T")[:19] or None)
        if tx:
            tx["source"] = f"sms:{sender}"
            txs.append(tx)
    added = add(txs)
    return {"ok": True, "checked": len(sms), "found": len(txs), "added": len(added)}


# ---------- reports ----------

def _fmt(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ") + " so'm"


def period_range(period: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if period == "today":
        return today, today
    if period == "yesterday":
        return today - timedelta(days=1), today - timedelta(days=1)
    if period == "week":
        return today - timedelta(days=today.weekday()), today
    if period == "month":
        return today.replace(day=1), today
    return date(2000, 1, 1), today


def report(period: str = "month", today: date | None = None) -> str:
    start, end = period_range(period, today)
    rows = [r for r in load() if start.isoformat() <= r["date"][:10] <= end.isoformat()]
    spent = [r for r in rows if r["kind"] == "expense"]
    income = [r for r in rows if r["kind"] == "income"]
    total = sum(r["amount"] for r in spent)
    names = {"today": "Bugun", "yesterday": "Kecha", "week": "Shu hafta", "month": "Shu oy", "all": "Hammasi"}
    out = [f"💳 {names.get(period, period)} ({start.strftime('%d.%m')}–{end.strftime('%d.%m')})",
           f"Xarajat / Расход: {_fmt(total)}", f"Kirim / Доход: {_fmt(sum(r['amount'] for r in income))}"]
    if spent:
        by_cat, by_card, by_merchant = defaultdict(float), defaultdict(float), defaultdict(float)
        for r in spent:
            by_cat[r["category"]] += r["amount"]
            by_card[f"{r['card']} {('*' + r['card_last4']) if r.get('card_last4') else ''}".strip()] += r["amount"]
            if r.get("merchant"):
                by_merchant[r["merchant"]] += r["amount"]
        out.append("\nKategoriyalar:")
        out += [f"  {c}: {_fmt(v)} ({v / total * 100:.0f}%)" for c, v in sorted(by_cat.items(), key=lambda x: -x[1])]
        out.append("\nKartalar:")
        out += [f"  {c}: {_fmt(v)}" for c, v in sorted(by_card.items(), key=lambda x: -x[1])]
        if by_merchant:
            out.append("\nTop-5 joy:")
            out += [f"  {m}: {_fmt(v)}" for m, v in sorted(by_merchant.items(), key=lambda x: -x[1])[:5]]
        days = (end - start).days + 1
        if days > 1:
            out.append(f"\nKuniga o'rtacha: {_fmt(total / days)}")
    budget = float(os.getenv("MONTHLY_BUDGET", "0") or 0)
    if budget and period == "month":
        left = budget - total
        out.append(f"\nOylik byudjet: {_fmt(budget)} → qoldi {_fmt(left)}" + (" ⚠️" if left < 0 else ""))
    return "\n".join(out)


def main(argv: list[str]) -> dict:
    if not argv:
        return {"ok": False, "error": __doc__}
    cmd, args = argv[0], argv[1:]
    if cmd == "sms":
        return import_sms()
    if cmd == "parse":
        tx = parse_notification(" ".join(args))
        return {"ok": bool(tx), "added": add([tx]) if tx else [], "parsed": tx}
    if cmd == "add":
        return {"ok": True, "added": manual(float(args[0].replace(" ", "")), " ".join(args[1:]) or "xarajat")}
    if cmd == "report":
        text = report(args[0] if args else "month")
        MONEY_DIR.mkdir(parents=True, exist_ok=True)
        path = MONEY_DIR / f"report-{args[0] if args else 'month'}-{date.today().isoformat()}.md"
        path.write_text(text + "\n", encoding="utf-8")
        return {"ok": True, "file": str(path.relative_to(store.ROOT)), "text": text}
    return {"ok": False, "error": f"unknown command {cmd}"}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:]), ensure_ascii=False))
