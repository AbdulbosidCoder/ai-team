#!/usr/bin/env bash
# Запускает бота в фоне в tmux-сессии "tgbot" и перезапускает его при падении.
# На Termux дополнительно держит телефон «бодрствующим» (termux-wake-lock).
cd "$(dirname "$0")/.."
command -v termux-wake-lock >/dev/null && termux-wake-lock
if tmux has-session -t tgbot 2>/dev/null; then
  echo "Бот уже запущен. Посмотреть: tmux attach -t tgbot  (выйти: Ctrl+B, затем D)"
  exit 0
fi
tmux new-session -d -s tgbot 'while true; do python3 tgbot/bot.py; echo "Перезапуск через 10 с…"; sleep 10; done'
echo "Бот запущен в фоне. Логи: tmux attach -t tgbot   Остановить: tmux kill-session -t tgbot"
