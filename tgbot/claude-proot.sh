#!/data/data/com.termux/files/usr/bin/bash
# Runs Claude Code inside Ubuntu (proot-distro) on Android, in this repo, with the repo at the same path.
# Claude Code has no Android build, but its Linux arm64 build runs in Ubuntu under proot.
#   bash tgbot/claude-proot.sh            interactive (first time: log in with your Claude account)
#   echo "salom" | bash tgbot/claude-proot.sh -p     what the bot does for each message
REPO="$(cd "$(dirname "$0")/.." && pwd)"
exec proot-distro login "${PROOT_DISTRO:-ubuntu}" --shared-tmp --bind "$REPO:$REPO" -- \
  bash -lc 'cd "$1" && shift && export PATH="$HOME/.local/bin:$PATH" && exec claude "$@"' _ "$REPO" "$@"
