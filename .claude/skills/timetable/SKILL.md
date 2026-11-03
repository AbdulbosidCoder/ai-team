---
name: timetable
description: Read the team's Telegram chats (saved by the bot in inbox/telegram/, or a Telegram Desktop export) and build today's schedule, the weekly timetable and the open task list. Use when asked what to do today, for a daily plan, a timetable, or to go through Telegram messages for tasks.
---

# Timetable: Telegram chat in, a daily schedule out

The bot (`tgbot/bot.py`) saves every chat message to `inbox/telegram/<chat_id>.jsonl`. Tasks live in `out/timetable/tasks.json`. The script `tgbot/cli.py` prints one JSON line per command.

1. **New export?** If there is a Telegram Desktop export (`result.json`) in `inbox/`, import it: `python3 tgbot/cli.py import inbox/<file>.json`.
2. **Pull tasks out of new messages.** `python3 tgbot/cli.py scan`. It uses Claude when `ANTHROPIC_API_KEY` is set and simple rules otherwise.
3. **Check the result yourself.** Read `out/timetable/tasks.json`. The rules engine can miss tasks or take whole sentences as titles. Read the recent lines of `inbox/telegram/*.jsonl` and fix things with `python3 tgbot/cli.py add "<day> <HH:MM> <short task>"` (missed tasks) and `python3 tgbot/cli.py done <id>` (finished or wrong tasks).
4. **Build the day.** `python3 tgbot/cli.py today` writes `out/timetable/<date>.md`. For the week: `python3 tgbot/cli.py week`.
5. **Reply** with the day plan as a short list (time, task, who), red flags first: overdue tasks, a task that did not fit into the working day, two meetings at the same time.

Never send messages to Telegram yourself. The bot sends the morning plan on its own schedule.
