# Готовые промпты (копировать и вставлять с телефона)

Где вставлять: приложение **Claude** → вкладка **Code** → репозиторий `AbdulbosidCoder/ai-team`.

---

## 0. Установочный промпт (один раз)

```
CLAUDE.md, PHONE.md va .claude/agents/ ni o'qi.
Menga telefonda (Android, Termux) ishga tushirish uchun qadam-baqadam yo'l-yo'riq ber:
Termux o'rnatish, setup-termux.sh, .env to'ldirish (TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS,
ANTHROPIC_API_KEY, SMS_AUTO_IMPORT=1, MONTHLY_BUDGET), @BotFather da /setprivacy Disable,
botni guruhlarga qo'shish, /here va /settime 08:00.
Keyin 4 agent (scheduler, hisobchi, marketing, montaj) to'g'ri sozlanganini tekshir:
har bir agent qaysi skilldan foydalanadi, tgbot/cli.py va tgbot/money.py ishlaydimi —
test ma'lumot bilan sinab ko'r, natijani qisqa jadval qilib ko'rsat.
```

## 1. Scheduler: задачи из Telegram

```
scheduler agentini ishlat: inbox/ dagi Telegram eksportini import qil, xabarlardan
kim kimga qaysi kunga qanday vazifa berganini ajrat, out/timetable/log.md ga yoz,
bugungi reja va haftalik jadvalni tuz. Muddati o'tgan va egasiz vazifalarni alohida ko'rsat.
```

## 2. Hisobchi: расходы Uzcard / Humo

```
hisobchi agentini ishlat: quyidagi karta xabarlarini yoz va shu oyning hisobotini ber —
kategoriyalar, Humo va Uzcard alohida, eng ko'p pul ketgan 5 joy, kunlik o'rtacha va
oyiga qancha tejash mumkinligi:
<HUMO / CardXabar / SMS xabarlarini shu yerga joylashtiring>
```

## 3. Marketing: content plan для Instagram

```
marketing agentini ishlat: <biznes nomi va nima sotishi> uchun Instagram'ga 14 kunlik
content plan tuz (Reels, Carousel, Stories), har kunga hook, maqsad (reach/trust/sales)
va tayyorgarlik vazifalari. Birinchi 3 Reels uchun ssenariy va caption yoz.
Tayyorgarlik vazifalarini timetable ga qo'sh.
```

## 4. Montaj: видео

```
montaj agentini ishlat: inbox/ dagi yangi klipdan 45 soniyalik vertikal Reels qil,
subtitr va cover bilan. Agar content plan da shu kunga mos mavzu bo'lsa, shu nom bilan sakla.
```

## Всё вместе (утренний промпт)

```
Ertalabki tekshiruv: scheduler — bugungi reja; hisobchi — kechagi xarajatlar;
marketing — bugun qaysi post chiqishi va nima tayyor emas; montaj — inbox/ da yangi klip
bormi. Hammasini 10 qatorda yig'ib ber.
```

---

## Команды бота в Telegram (работают без Claude Code)

| Агент | Команды |
|---|---|
| Scheduler | `/today` `/tomorrow` `/week` `/tasks` `/add …` `/done 3` `/scan` `/every …` |
| Hisobchi | переслать боту уведомление HUMO / CardXabar / SMS → запишется само; `/xarajat 25000 taksi`, `/kirim 3mln oylik`, `/hisobot today\|week\|month`, `/sms` |
| Marketing | `/plan <тема> 14` |
| Montaj | только через Claude Code: монтажу нужны ffmpeg и Whisper, на телефоне это медленно |
