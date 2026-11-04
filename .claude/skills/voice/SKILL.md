---
name: voice
description: Speech in videos — detect the spoken language (Uzbek, Russian, English, mixed), make a word-timed transcript, clean noisy sound, cut a video by editing its transcript text or dropping phrases, and make free voice-overs in uz/ru/en (edge-tts). Use for til aniqlash, transkript, ovoz tozalash, "matndan kes", voice-over, ovoz berish, diktor.
---

# Voice: what is said, in which language, and how it sounds

Script: `python3 .claude/skills/voice/scripts/voice.py <command> …` — one JSON line per run, one command per Bash call.
Speech-to-text: ElevenLabs Scribe when `ELEVENLABS_API_KEY` is set (best Uzbek), else a free local multilingual Whisper. Language: `WHISPER_LANG=auto` (Uzbek + Russian + English, mixed).

| Need | Command |
|---|---|
| Which language is spoken | `detect <video> --out out/<name>/language.json` → `main`, `share` (e.g. uz 0.7, ru 0.3), `mixed`, per-sentence languages |
| Transcript with word times | `transcript <video> out/<name>/transcript` → `words.json`, `transcript.txt` (one sentence per line), `transcript.srt`, `language.json` |
| Clean sound | `clean <in> <out> --level light\|normal\|strong` (hum, hiss, loudness −14 LUFS) |
| Cut by text | copy `transcript.txt` → `edited.txt`, delete lines/words, then `textcut <video> <words.json> <edited.txt> <out.mp4>` |
| Drop a phrase everywhere | `cutwords <video> <words.json> <out.mp4> --drop "eee" --drop "xullas"` |
| Voice-over | `tts "<text or .txt file>" <out.mp3> --lang uz\|ru\|en --gender female\|male [--rate +5%] [--srt out.srt]` |
| Available voices | `voices` |

Voices (free, Microsoft edge-tts, needs internet): uz — Madina (female), Sardor (male); ru — Svetlana, Dmitry; en — Aria, Guy. Offline fallback: `espeak-ng` if installed.

Notes:
- Whisper sometimes names Uzbek speech as Kazakh or Turkish; `detect` corrects this from the words themselves.
- In `textcut`, words you add to the text cannot be spoken by the video: the result says so in `note`.
- After a voice-over, put it on the video with the edit skill: `vtool.py audio <video> <out> --add voice.mp3` (or `--replace`).

Never delete files. Nothing is posted.
