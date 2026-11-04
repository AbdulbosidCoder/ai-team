#!/data/data/com.termux/files/usr/bin/bash
# Montaj (video edit) on an Android phone with Termux. Run once, after setup-termux.sh:
#   bash setup-montaj.sh            # multilingual model for Uzbek + Russian (small, ~470 MB)
#   bash setup-montaj.sh base       # faster, less accurate, ~140 MB
#   bash setup-montaj.sh medium     # most accurate on a phone, slow, ~1.5 GB
# Best Uzbek quality without a big model: put ELEVENLABS_API_KEY in .env instead (cloud, needs internet).
# Installs ffmpeg, numpy, pillow, builds whisper.cpp (speech-to-text that runs on the phone)
# and writes WHISPER_CPP / WHISPER_CPP_MODEL into .env.
set -e
cd "$(dirname "$0")"
MODEL="${1:-small}"
WDIR="$HOME/whisper.cpp"

pkg install -y ffmpeg python-numpy python-pillow clang cmake make git wget poppler
# Free voice-over voices in Uzbek, Russian and English (needs internet when it speaks)
python -m pip install edge-tts || echo "edge-tts did not install: voice-over will be off, everything else works"

# Access to phone storage (Download, DCIM) so /edit ~/storage/downloads/video.mp4 works
[ -d "$HOME/storage" ] || termux-setup-storage || true

if [ ! -x "$WDIR/build/bin/whisper-cli" ]; then
  [ -d "$WDIR" ] || git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$WDIR"
  cmake -S "$WDIR" -B "$WDIR/build" -DCMAKE_BUILD_TYPE=Release
  cmake --build "$WDIR/build" -j 4 --config Release --target whisper-cli
fi
[ -f "$WDIR/models/ggml-$MODEL.bin" ] || sh "$WDIR/models/download-ggml-model.sh" "$MODEL"

[ -f .env ] || cp .env.example .env
grep -v -E '^(WHISPER_CPP|WHISPER_CPP_MODEL|WHISPER_LANG)=' .env > .env.new || true
{
  cat .env.new
  echo "WHISPER_LANG=auto"
  echo "WHISPER_CPP=$WDIR/build/bin/whisper-cli"
  echo "WHISPER_CPP_MODEL=$WDIR/models/ggml-$MODEL.bin"
} > .env
rm -f .env.new
mkdir -p inbox inbox/music out done

echo
echo "Montaj tayyor. Botni qayta ishga tushiring:"
echo "  tmux kill-session -t tgbot"
echo "  bash tgbot/run.sh"
echo "Keyin botga video yuboring yoki: /edit"
