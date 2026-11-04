# Бесплатный запуск: Render + Neon + cron-job.org ($0)

Схема:

```
iPhone (Telegram)  ──►  Render free (bot.py, webhook)  ──►  Neon free Postgres (задачи, расходы, сообщения)
                               ▲
cron-job.org: каждые 10 мин GET на адрес бота, чтобы Render не засыпал
```

Почему так:
- Render free засыпает через 15 минут без запросов. Пинг каждые 10 минут не даёт ему уснуть, поэтому утренний план и напоминания работают. 750 бесплатных часов хватает на один сервис на весь месяц.
- На Render free нет постоянного диска: при перезапуске файлы стираются. Поэтому данные лежат в Postgres (Neon).
- Neon free засыпает через 5 минут без запросов, а вычислительное время ограничено. Поэтому бот держит данные в памяти, пишет в базу только при изменениях, а сообщения чатов сохраняет пачками раз в 10 минут.

Лимиты бесплатных тарифов меняются. Проверьте их на render.com/pricing и neon.com/pricing.

---

## 1. Neon (база, 3 минуты)

1. Зайдите на **neon.com** и войдите через GitHub или Google, карта не нужна. Нажмите **Create project**, регион выберите ближе, например Frankfurt.
2. **Connect** → скопируйте **connection string**. Выглядит так: `postgresql://user:pass@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`
3. Таблицы бот создаст сам.

## 2. Telegram

1. @BotFather → `/newbot` → скопируйте токен.
2. @BotFather → `/setprivacy` → бот → **Disable**, чтобы бот видел сообщения в группах.

## 3. Render (бот)

1. Зайдите на **render.com** и войдите через GitHub.
2. **New → Blueprint** → выберите репозиторий `Risqulov06/ai-team`. Render найдёт `render.yaml` и создаст сервис `ai-team-bot` на бесплатном тарифе.
3. Render спросит секреты:
   - `TELEGRAM_BOT_TOKEN` — токен из шага 2
   - `DATABASE_URL` — строка из Neon
   - `ALLOWED_USER_IDS` — пока оставьте пустым (после шага 5 впишите свой ID)
   - `ANTHROPIC_API_KEY` — необязательно. Без него задачи ищутся по правилам. Учтите: ключ API платный, при бюджете $0 оставьте пустым.
4. **Apply** → дождитесь статуса **Live**. В логах будет `Bot ishga tushdi`. Адрес сервиса будет вида `https://ai-team-bot-xxxx.onrender.com`.

Webhook бот ставит сам: Render передаёт ему свой адрес (`RENDER_EXTERNAL_URL`).

## 4. cron-job.org (чтобы не засыпал)

1. Зарегистрируйтесь на **cron-job.org** (бесплатно) → **Create cronjob**.
2. URL: адрес вашего сервиса, например `https://ai-team-bot-xxxx.onrender.com/`. Расписание: **every 10 minutes**.
3. Ответ будет `404`, это нормально: важен сам запрос, он будит Render.

## 5. Настройка в Telegram

1. Напишите боту `/whoami` → скопируйте User ID → Render → Environment → `ALLOWED_USER_IDS` → Save. Сервис перезапустится, данные останутся в Neon.
2. В чате для утреннего плана: `/here`, затем `/settime 08:00`.
3. Добавьте бота в рабочие группы.

## Что работает на Render, а что нет

| Функция | Render free |
|---|---|
| Задачи из чатов, `/today`, `/week`, напоминания, утренний план | ✅ |
| Расходы: пересланные уведомления HUMO/CardXabar, `/xarajat`, `/hisobot` | ✅ |
| Content plan `/plan` | ✅ (с ключом Claude получается точнее) |
| Чтение SMS (`/sms`) | ❌ Только Android/Termux. На iPhone пересылайте уведомления боту |
| Монтаж видео | ❌ Не хватит 512 МБ / 0.1 CPU. Запустите бота на Android-телефоне (`setup-montaj.sh`, см. PHONE.md) или используйте приложение Claude → Code |
| Агенты Claude Code | Работают в приложении Claude → Code (бесплатно в рамках вашей подписки Claude) |

## Если что-то не так

- **Бот молчит** → Render → Logs. Ошибка `TELEGRAM_BOT_TOKEN topilmadi` означает, что не задан токен. Ошибка `connection` означает неверный `DATABASE_URL`.
- **Утренний план не пришёл** → проверьте, что cron-job.org пингует каждые 10 минут, и что вы отправили `/here`.
- **Хочу вернуться на polling** (Termux или компьютер) → просто не задавайте `WEBHOOK_URL` и `RENDER_EXTERNAL_URL`. Без `DATABASE_URL` данные хранятся в файлах.
