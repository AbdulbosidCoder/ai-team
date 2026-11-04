---
name: stories
description: Plan and write Instagram Stories for a client — a multi-day story plan with every story's on-screen text, visual, sticker and call to action. Use when asked for stories, "storis", "story plan", "bugungi storislar", or anything for the Shoxsaroy Towers account.
---

# Stories: story plans the owner can post straight away

1. **Which client?** shoxsaroy, universitet or shaxsiy-brend. If unclear, ask in one line.
2. **Read the brain.** `mcp__memory__open_nodes` with names ["Brand rules", "Clients", "Lessons", "Ideas"]. Then read every file in `inbox/biz/<client>/` if the folder exists. Use only facts found there.
3. **Defaults** (unless the owner says otherwise):
   - **shoxsaroy**: 6 days, at least 3 stories a day.
   - other clients: 7 days, 2 to 3 stories a day.
4. **Shape of each day** — a small story arc, not random slides:
   - story 1: hook / attention (a question, a surprising fact, a view, a "before–after" of the construction);
   - story 2: value or proof (a benefit, a fact, construction progress, a nearby amenity, a client answer);
   - story 3: action (a poll, a quiz, a question sticker, "DM yozing", a call button, a link).
   Rotate the angles across the week: location & amenities, apartment layouts, payment terms, construction progress, trust (team, documents, quality), lifestyle, FAQ, offer. **At most one hard-sell day in three.**
5. **Each story** gets: number, type (photo / video / text / poll / quiz / question / countdown / link), on-screen text in Uzbek (8–12 words max, big and readable), what to show in the picture or video, the sticker, and the call to action.
6. **Facts.** Prices, payment terms, dates and numbers come only from "Clients" or `inbox/biz/<client>/`. Anything you are not sure of: `[tekshiring]`.
7. **Save** to `out/stories/<client>/<YYYY-MM-DD>-<topic>.md`: a short table for the week (day, theme, goal), then each day's stories in order, then a short list of photos/videos to shoot.
8. **Timetable.** If the owner asks, add shooting tasks the day before: `python3 tgbot/cli.py add "<YYYY-MM-DD> <task>"`.
9. **Remember** the week's themes as observations on "Ideas" (start with the client name) so they are not repeated next week.

Reply in Uzbek: day 1's stories in full, the other days as one line each, then the file path. End with: "Hech narsa joylanmadi. Sizning OK'ingizni kutyapti."
