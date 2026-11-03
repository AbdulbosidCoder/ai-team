---
name: ops
description: Business automation. Turn notes, chat messages and descriptions of how the business works (inbox/biz/, inbox/telegram/) into step-by-step SOPs, a list of what to automate, and recurring tasks for the Telegram bot. Use when asked to automate the business, set up routines or reminders, write a process or SOP, or find repeated manual work.
---

# Ops: find the repeated work and automate it

1. **Read** everything in `inbox/biz/` (process notes, price lists, FAQ) and the last two weeks of `inbox/telegram/*.jsonl`.
2. **Find repeats.** Questions customers ask again and again, reports someone makes every week, reminders people send by hand, the same message copied to several chats. Count how often each happens.
3. **Write** `out/ops/automation.md` with three sections:
   - **Recurring tasks for the bot**: each as a ready command, e.g. `/every mon 09:00 Haftalik savdo hisoboti` or `/every weekdays 18:00 Kunlik kassa tekshiruvi`.
   - **SOPs**: for the top 3 processes, numbered steps, who does each, and what "done" looks like.
   - **Ready answers**: short replies for the top customer questions (FAQ), in the language customers use.
   - **Bigger automations** worth building later (CRM, payments, a sales bot), each with the time it would save per week.
4. **Do not set anything up yourself.** The owner sends the `/every` commands to the bot after reading the file.

Reply with the 3 automations that save the most time per week.
