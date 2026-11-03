---
name: planner
description: Build a content plan (content calendar) for 1 to 4 weeks, one item per day with platform, format, hook, goal and prep tasks, and put the prep work into the timetable. Use when asked for a content plan, content calendar, posting schedule or "what do we post this week".
---

# Planner: a content plan you can actually shoot

1. **Context.** Read the brand rules and lessons (`mcp__memory__open_nodes` with names ["Brand rules", "Lessons", "Ideas"]). If `out/radar/shortlist.md` or the latest `out/pulse/` file exists, read them: ideas people asked for and what worked.
2. **Ask only what is missing:** the business/topic, the platforms, how many days, how many posts per week the team can really make.
3. **Write** `out/plan/<date>-<topic>.md`: a table (date, platform, format, topic, hook, goal), then the prep tasks per day. Rules:
   - mix formats (reel, carousel, stories, post) and goals (reach → trust → sales); at most one sales post in three;
   - every hook is one line that works without the video;
   - reuse: one long piece can become 2 to 3 short ones.
4. **Into the timetable.** For each day add the prep work, the day before posting: `python3 tgbot/cli.py add "<YYYY-MM-DD> <task>"`.
5. **Remember** the plan's topics as observations on "Ideas" so radar does not suggest them again.

For a quick draft without asking anything, `python3 tgbot/cli.py plan "<topic>" <days>` makes one (the same thing the bot's /plan does). Reply with the first 3 days and the file path.
