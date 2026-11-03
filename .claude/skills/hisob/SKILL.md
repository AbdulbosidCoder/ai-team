---
name: hisob
description: Track and analyse personal and business spending from Uzcard and Humo card notifications (SMS, HUMO bot, CardXabar) and manual entries. Use when asked about expenses, spending, xarajat, расходы, a budget, or where the money went.
---

# Hisob: where did the money go?

Transactions live in `out/money/transactions.json` (private, never in git). The script `tgbot/money.py` prints one JSON line per command.

1. **Collect.** On the phone (Termux): `python3 tgbot/money.py sms` reads new card SMS. Pasted notifications go in with `python3 tgbot/money.py parse "<notification text>"`. Cash goes in with `python3 tgbot/money.py add <sum> <note>`.
2. **Report.** `python3 tgbot/money.py report month` (or `today`, `week`, `all`). It writes `out/money/report-*.md`.
3. **Check the categories.** Read `transactions.json`. Anything in "Boshqa / Прочее" whose merchant you can recognise (for example "OOO XYZ" is a café) should be put into the right category in your summary, and you should suggest adding the keyword to `CATEGORIES` in `tgbot/money.py`. Show the change and wait for an OK.
4. **Analyse** into `out/money/analysis-<date>.md`:
   - totals by category and by card (Humo / Uzcard), and the change against the previous period;
   - the 3 biggest leaks: subscriptions, many small café or taxi payments, fees;
   - business vs personal spending, if the notes show which is which (ads, hosting and subscriptions count as business);
   - one concrete saving per leak, in so'm per month.
5. **Reply** in 5 lines: the total, the top category, the biggest leak, the saving and the budget left (if `MONTHLY_BUDGET` is set).

Never move money, log in to a bank or share card numbers. Only the last 4 digits are stored.
