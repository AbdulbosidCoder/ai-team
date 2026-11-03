#!/data/data/com.termux/files/usr/bin/bash
# Montaj (video edit) on an Android phone with Termux. Run once, after setup-termux.sh:
#   bash setup-montaj.sh            # English speech model (base.en, ~140 MB)
#   bash setup-montaj.sh base       # multilingual model (uz / ru / en), set WHISPER_LANG in .env
#   bash setup-montaj.sh small      # more accurate, slower, ~470 MB
# Installs ffmpeg, numpy, pillow, builds whisper.cpp (speech-to-text that runs on the phone)
# and writes WHISPER_CPP / WHISPER_CPP_MODEL into .env.
set -e
cd "$(dirname "$0")"
MODEL="${1:-base.en}"
WDIR="$HOME/whisper.cpp"

pkg install -y ffmpeg python-numpy python-pillow clang cmake make git wget

# Access to phone storage (Download, DCIM) so /edit ~/storage/downloads/video.mp4 works
[ -d "$HOME/storage" ] || termux-setup-storage || true

if [ ! -x "$WDIR/build/bin/whisper-cli" ]; then
  [ -d "$WDIR" ] || git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$WDIR"
  cmake -S "$WDIR" -B "$WDIR/build" -DCMAKE_BUILD_TYPE=Release
  cmake --build "$WDIR/build" -j 4 --config Release --target whisper-cli
fi
[ -f "$WDIR/models/ggml-$MODEL.bin" ] || sh "$WDIR/models/download-ggml-model.sh" "$MODEL"

[ -f .env ] || cp .env.example .env
grep -v -E '^(WHISPER_CPP|WHISPER_CPP_MODEL)=' .env > .env.new || true
{
  cat .env.new
  echo "WHISPER_CPP=$WDIR/build/bin/whisper-cli"
  echo "WHISPER_CPP_MODEL=$WDIR/models/ggml-$MODEL.bin"
} > .env
rm -f .env.new
mkdir -p inbox out done

echo
echo "Montaj tayyor. Botni qayta ishga tushiring:"
echo "  tmux kill-session -t tgbot"
echo "  bash tgbot/run.sh"
echo "Keyin botga video yuboring yoki: /edit"
