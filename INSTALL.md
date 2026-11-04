# O'rnatish qo'llanmasi

Bu qo'llanma AI jamoangizni (Telegram bot, storislar, kontent-reja, subtitrli montaj) ishga tushirishni bosqichma-bosqich ko'rsatadi. Dasturlash bilmasangiz ham bo'ladi: buyruqlarni nusxalab, qo'yib, Enter bosasiz.

## Qaysi yo'lni tanlash kerak?

| Yo'l | Nima ishlaydi | Narxi | Qiyinligi |
|---|---|---|---|
| **A. Claude ilovasi (o'rnatishsiz)** | Storislar, kontent-reja, ssenariy, caption | Claude obunangiz ichida | Eng oson |
| **B. Android telefon** | Hammasi: bot, storislar, **subtitrli montaj**, xarajatlar, AI-agent | Bepul (ElevenLabs ixtiyoriy) | O'rtacha, 30–60 daqiqa |
| **C. Render server (bepul)** | Bot, reja, eslatmalar, xarajatlar. **Montaj ishlamaydi** | Bepul | O'rtacha, iPhone uchun |

Faqat storis va kontent yozdirmoqchi bo'lsangiz, **A** yetarli. Videoga subtitr qo'ydirmoqchi bo'lsangiz, **B** kerak.

---

## A. Claude ilovasi orqali (o'rnatishsiz)

1. Telefoningizda yoki kompyuterda **Claude** ilovasini oching.
2. **Code** bo'limiga kiring va `Risqulov06/ai-team` repozitoriyasini tanlang.
3. Oddiy so'z bilan yozing, masalan:
   - *"Shoxsaroy uchun 6 kunlik storis rejasi tuz"*
   - *"Universitet uchun haftalik kontent-reja"*
   - *"Qurilish haqida 45 soniyalik Reels ssenariy yoz"*

Tayyor ishlar `out/` papkasida paydo bo'ladi. Hech narsa o'zi joylanmaydi.

---

## B. Android telefonda (to'liq versiya)

### 1-qadam. Telegram bot yaratish (2 daqiqa)

1. Telegramda **@BotFather** ni oching → `/newbot` → botga nom bering → berilgan **tokenni** nusxalab qo'ying.
2. @BotFather → `/setprivacy` → botingizni tanlang → **Disable**. Busiz bot guruhlardagi xabarlarni ko'rmaydi.

### 2-qadam. Termux o'rnatish

1. **F-Droid** (f-droid.org) dan **Termux** va **Termux:API** ni o'rnating. Google Play'dagi Termux eskirgan, u ishlamaydi.
2. Android sozlamalarida Termux uchun **batareya tejashni o'chiring**. Aks holda telefon botni "uxlatib" qo'yadi.

### 3-qadam. Loyihani yuklab olish

Termux'ni oching va buyruqlarni **bittadan** nusxalab, Enter bosing:

```bash
pkg install -y git
```

```bash
git clone https://github.com/Risqulov06/ai-team
```

```bash
cd ai-team
```

```bash
bash setup-termux.sh
```

Birinchi o'rnatish 10–20 daqiqa davom etadi, kuting.

### 4-qadam. Tokenni yozish

```bash
nano .env
```

`TELEGRAM_BOT_TOKEN=` qatoriga 1-qadamdagi tokenni qo'ying. Saqlash: **Ctrl+O**, **Enter**, **Ctrl+X**.

### 5-qadam. Botni ishga tushirish

```bash
bash tgbot/run.sh
```

Bot fonda ishlay boshlaydi. Telegramda botingizga `/whoami` yozing va kelgan raqamni (ID) eslab qoling.

### 6-qadam. Botni faqat o'zingizga ochish

```bash
nano .env
```

`ALLOWED_USER_IDS=` qatoriga ID'ingizni yozing va saqlang. Keyin botni qayta ishga tushiring:

```bash
tmux kill-session -t tgbot
```

```bash
bash tgbot/run.sh
```

Botga `/here` yozing: ertalabki reja shu chatga keladi. Vaqtini o'zgartirish uchun `/settime 08:00` yozing.

### 7-qadam. Subtitrli montaj (o'zbekcha + ruscha)

```bash
bash setup-montaj.sh
```

Bu 10–20 daqiqa oladi. Android fayllarga ruxsat so'rasa, **Ruxsat bering**. Bu buyruq internetsiz ishlaydigan ko'p tilli modelni o'rnatadi.

**O'zbekcha subtitr aniqroq bo'lishi uchun (tavsiya etiladi):**

1. **elevenlabs.io** saytida ro'yxatdan o'ting (boshlash bepul).
2. **Profile → API Keys** bo'limidan kalitni oling.
3. Termux'da `nano .env` ni oching va kalitni `ELEVENLABS_API_KEY=` qatoriga qo'ying.

Kalit bo'lsa, subtitrlar ElevenLabs orqali yoziladi. Kalit bo'lmasa yoki internet uzilsa, telefondagi model ishlaydi.

Montajdan keyin botni qayta ishga tushiring:

```bash
tmux kill-session -t tgbot
```

```bash
bash tgbot/run.sh
```

**Foydalanish:** videoni botga yuboring (20 MB gacha). Bot pauzalarni va "eee", "эээ" kabi tovushlarni kesadi, videoni vertikal 9:16 qiladi, subtitr va muqova qo'shib, tayyor videoni qaytaradi. Kattaroq videoni telefonning "Yuklanmalar" (Download) papkasiga saqlang va botga `/edit ~/storage/downloads/video.mp4` deb yozing.

### 8-qadam (ixtiyoriy). Telegramda AI-agent

Bu qadamdan keyin botga oddiy matn yozsangiz ("Shoxsaroy uchun storis tuz"), u Claude orqali javob beradi. Taxminan 1,5 GB joy kerak.

```bash
bash setup-agent.sh
```

Oxirida skript qolgan 3 ta qadamni ko'rsatadi: Claude'ga kirish, my.telegram.org dan `api_id` va `api_hash` olish, so'ng botga `/ai` yozish.

---

## C. Render serverida (iPhone uchun, bepul)

iPhone fonda dastur ushlab tura olmaydi, shuning uchun bot bepul serverda ishlaydi. Montaj bu yerda **ishlamaydi**.

1. **neon.com** → GitHub orqali kiring → **Create project** → **Connect** → manzilni (`postgresql://...`) nusxalang.
2. **render.com** → GitHub orqali kiring → **New → Blueprint** → `Risqulov06/ai-team` ni tanlang.
3. Render so'raydigan maydonlar:
   - `TELEGRAM_BOT_TOKEN`: @BotFather tokeni
   - `DATABASE_URL`: Neon manzili
   - `ALLOWED_USER_IDS`: hozircha bo'sh qoldiring
   - `ANTHROPIC_API_KEY`: bo'sh qoldirsa bo'ladi (pullik)
4. **Apply** → holat **Live** bo'lishini kuting.
5. **cron-job.org** da har 10 daqiqada server manziliga murojaat qiladigan vazifa yarating. Shunda server uxlab qolmaydi.
6. Botga `/whoami` yozing → ID'ni Render → **Environment** → `ALLOWED_USER_IDS` ga yozing → **Save**.

Batafsil (ruscha): [RENDER.md](RENDER.md).

---

## Mijoz ma'lumotlarini kiritish

Agent faqat siz bergan faktlardan foydalanadi: narx va sanalarni o'zi to'qimaydi. Shuning uchun ma'lumotlarni quyidagi papkalarga yozing:

- `inbox/biz/shoxsaroy/README.md`: manzil, kvartira maydonlari, narxlar, topshirish muddati
- `inbox/biz/universitet/README.md`: nomi, fakultetlar, qabul muddatlari
- `inbox/biz/shaxsiy-brend/README.md`: tajribangiz, mavzularingiz, uslubingiz

Fayllarni o'zingiz o'zgartirishingiz shart emas: ma'lumotlarni Claude'ga yozib yuboring, u o'zi qo'shib qo'yadi.

## Muammo bo'lsa

| Belgi | Nima qilish kerak |
|---|---|
| Bot javob bermayapti | `tmux attach -t tgbot` bilan xatoni ko'ring (chiqish: **Ctrl+B**, keyin **D**). Tokenni tekshiring |
| Bot guruhdagi xabarlarni ko'rmayapti | @BotFather → `/setprivacy` → **Disable** |
| "Nutqni tanish yo'q" degan xabar chiqdi | `bash setup-montaj.sh` ni ishga tushiring yoki `ELEVENLABS_API_KEY` ni qo'shing |
| Subtitrda so'z noto'g'ri yozilgan | Agentga yozing: *"X so'zini Y ga almashtir"*. U subtitrni qayta yozadi |
| Bot vaqti-vaqti bilan to'xtab qoladi | Termux uchun batareya tejashni o'chiring |
