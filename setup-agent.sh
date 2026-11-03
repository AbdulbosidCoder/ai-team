#!/data/data/com.termux/files/usr/bin/bash
# AI agent in Telegram on an Android phone (Termux), run once after setup-termux.sh:
#   bash setup-agent.sh
# 1) Ubuntu inside Termux (proot-distro) with Claude Code in it: Claude Code has no Android build.
# 2) Telethon (MTProto) so the agent can read your own Telegram chats, read-only.
# 3) CLAUDE_CMD in .env, so the bot hands your messages to Claude Code.
# Needs ~1.5 GB free. No root.
set -e
cd "$(dirname "$0")"
REPO="$(pwd)"

pkg install -y proot-distro python-pip
proot-distro list 2>/dev/null | grep -q "ubuntu.*installed" || proot-distro install ubuntu || true

proot-distro login ubuntu -- bash -lc '
  set -e
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y curl ca-certificates git python3 python3-pip tzdata
  python3 -m pip install --break-system-packages -q telethon tzdata
  export PATH="$HOME/.local/bin:$PATH"
  command -v claude >/dev/null || curl -fsSL https://claude.ai/install.sh | bash
  claude --version
'

# the bot (in Termux) also reads your chats on a timer
python -m pip install --use-pep517 telethon

[ -f .env ] || cp .env.example .env
grep -v -E '^CLAUDE_CMD=' .env > .env.new || true
{ cat .env.new; echo "CLAUDE_CMD=$REPO/tgbot/claude-proot.sh"; } > .env
rm -f .env.new
chmod +x tgbot/claude-proot.sh
mkdir -p .secrets && chmod 700 .secrets

cat <<'EOF'

Deyarli tayyor. Yana 3 qadam (bir marta):

1) Claude Code ga kiring (Claude akkauntingiz; ochilgan havolani brauzerda oching):
     bash tgbot/claude-proot.sh
   kirgandan keyin /exit

2) Telegram akkauntingizni ulang (faqat o'qish uchun):
   https://my.telegram.org -> API development tools -> api_id va api_hash
     nano .env        (TG_API_ID=..., TG_API_HASH=...)
     python3 tgbot/userbot.py login

3) Botni qayta ishga tushiring va unga /ai yozing:
     tmux kill-session -t tgbot
     bash tgbot/run.sh
EOF
