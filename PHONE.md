# Запуск с телефона: Telegram-бот + content plan + автоматизация

Этот проект (форк [bekhruztbx/ai-creative-team](https://github.com/bekhruztbx/ai-creative-team)) добавляет:

| Что | Где | Как пользоваться с телефона |
|---|---|---|
| **Дневной планировщик из Telegram-чата** | `tgbot/bot.py` | Бот читает ваши группы, вытаскивает задачи (uz / ru / en) и каждое утро присылает расписание дня |
| **Timetable на неделю** | `/week` | Команда боту |
| **Content plan** | `/plan <тема> [дней]` + skill `planner` | Команда боту или Claude Code |
| **Бизнес-автоматизация** | `/every …` + skill `ops` | Повторяющиеся задачи и напоминания |
| **Новые skills для Claude Code** | `.claude/skills/timetable`, `planner`, `ops` | Claude Code в приложении Claude |

Интерфейс на телефоне — это сам Telegram. Бот работает на любом устройстве, которое включено: на Android-телефоне (Termux), на старом ноутбуке или на дешёвом VPS.

---

## Шаг 1. Создать бота (2 минуты, в Telegram)

1. Откройте **@BotFather** → `/newbot` → придумайте имя → скопируйте **токен**.
2. **Важно для чтения групп:** `@BotFather` → `/setprivacy` → выберите бота → **Disable**. Без этого бот в группе видит только команды.
3. Добавьте бота в рабочие группы. Бот видит только сообщения, пришедшие **после** добавления. Старую историю можно импортировать (шаг 4).

## Шаг 2а. Запуск на Android (Termux)

1. Установите **Termux** из F-Droid (версия из Google Play устарела). Для фоновой работы также поставьте **Termux:API**.
2. В Termux:

```bash
pkg install -y git
```

```bash
git clone https://github.com/AbdulbosidCoder/ai-team
```

```bash
cd ai-team
```

```bash
bash setup-termux.sh
```

Первая установка идёт 10–20 минут: собирается `pydantic-core`.

3. Впишите токен:

```bash
nano .env
```

Заполните `TELEGRAM_BOT_TOKEN=...`. Сохранение: Ctrl+O, Enter, Ctrl+X.

4. Запустите бота в фоне:

```bash
bash tgbot/run.sh
```

5. В настройках Android отключите для Termux **оптимизацию батареи**, иначе система «усыпит» бота.

> iPhone: на iOS нельзя держать фоновый Python-процесс. Запускайте бота на VPS или компьютере (шаг 2б), а с iPhone им пользуйтесь через Telegram.

## Шаг 2б. Запуск на сервере / компьютере (Linux, macOS, VPS)

```bash
cd ai-team
```

```bash
python3 -m pip install -r tgbot/requirements.txt
```

```bash
cp .env.example .env
```

Заполните `.env`, затем:

```bash
bash tgbot/run.sh
```

## Шаг 3. Настроить в Telegram

1. Напишите боту `/whoami` и впишите свой ID в `.env` → `ALLOWED_USER_IDS=...`, чтобы командами пользовались только вы. Перезапустите бота: `tmux kill-session -t tgbot`, затем `bash tgbot/run.sh`.
2. В чате, куда хотите получать утренний план (личка с ботом или группа): `/here`.
3. Время утреннего отчёта: `/settime 07:30`.

## Команды

| Команда | Что делает |
|---|---|
| `/today`, `/tomorrow` | План дня: задачи с временем стоят на своих местах, остальные распределяются по свободным окнам рабочего дня, срочные первыми |
| `/week` | Timetable на 7 дней |
| `/tasks`, `/done 3` | Открытые задачи, отметить выполненной |
| `/add ertaga 15:00 mijoz bilan uchrashuv` | Добавить задачу вручную (можно ответом на сообщение) |
| `/scan` | Прямо сейчас вытащить задачи из новых сообщений (утром это происходит само) |
| `/plan qahvaxona 14` | Content plan на 14 дней; каждый день попадает в timetable как задача на подготовку |
| `/every weekdays 18:00 Kassa hisoboti` | Повторяющаяся задача (`daily`, `weekdays`, `mon,thu`…) |
| `/recurring`, `/unevery 2` | Список повторяющихся задач / удалить |

Также каждые 5 минут бот напоминает о задачах с конкретным временем за 15 минут до начала.

## Учёт расходов Uzcard / Humo

- **Android + SMS (автоматически).** В `.env` поставьте `SMS_AUTO_IMPORT=1`, дайте Termux:API разрешение на SMS. Каждые 15 минут бот читает новые SMS от банков и присылает «💳 Yangi operatsiyalar».
- **Уведомления в Telegram** (HUMO bot, CardXabar): просто **пересылайте** их боту в личку, и он сам распознает сумму, карту, магазин и категорию.
- Наличные: `/xarajat 25000 taksi`, `/xarajat 150k kafe`. Доход: `/kirim 3mln oylik`.
- Отчёт: `/hisobot today`, `/hisobot week`, `/hisobot month`. Вчерашние расходы также приходят в утреннем плане.
- Данные хранятся только на вашем устройстве (`out/money/`), от карты сохраняются лишь последние 4 цифры.

## 4 агента и готовые промпты

В `.claude/agents/`: **scheduler**, **hisobchi**, **marketing**, **montaj**. Промпты для копирования — в [PROMPTS.md](PROMPTS.md).

## Claude (точнее) или правила (бесплатно)

- **Без ключа** бот распознаёт задачи по ключевым словам (kerak, uchrashuv, ertaga, soat 10 da / нужно, завтра, в 15:30 / meeting, tomorrow…) и строит план по шаблону.
- **С `ANTHROPIC_API_KEY`** в `.env` задачи из переписки вытаскивает Claude: понимает контекст, сокращает заголовки, определяет, кто исполнитель. Content plan он пишет под вашу тему. Если API недоступен, бот сам переключается на правила.

## Импорт старой переписки

Telegram Desktop → чат → ⋮ → **Export chat history** → формат **JSON**. Положите `result.json` в `inbox/`:

```bash
python3 tgbot/cli.py import inbox/result.json
```

```bash
python3 tgbot/cli.py scan
```

## Claude Code с телефона (skills `timetable`, `planner`, `ops`, `reel`…)

В приложении Claude (iOS / Android) откройте **Code**, выберите этот репозиторий и пишите, например:

- *«Telegram xabarlaridan bugungi rejani tuz»* → skill `timetable`
- *«Kafe uchun 2 haftalik content plan»* → skill `planner`
- *«inbox/biz dagi jarayonlarni avtomatlashtir»* → skill `ops` (выдаёт готовые команды `/every` для бота)

Облачная сессия не видит файлы бота на телефоне: `inbox/telegram` в git не попадает, так как переписка приватная. Поэтому в Claude Code лучше работать с экспортом чата, а повседневный план брать у бота.

## Где лежат данные

- `inbox/telegram/*.jsonl` — сохранённые сообщения (в git не попадают)
- `out/timetable/tasks.json`, `out/timetable/<дата>.md` — задачи и планы дней
- `out/plan/*.md` — content plans
