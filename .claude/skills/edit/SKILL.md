---
name: edit
description: Full video-editing toolkit and montaj plans — trim, cut, join with transitions, 9:16 reframe, speed, color grading presets and LUTs, stabilize, denoise, zoom, b-roll, text titles, logo, music with ducking, subtitles from any .srt, fades and exports for Reels, Stories, posts, YouTube and Telegram; plus plan.py, which runs the director's ordered plan step by step. Use for any video edit beyond a quick reel, and whenever a plan.json is written or run.
---

# Edit: every montaj function, and the plan that orders them

Scripts: `.claude/skills/edit/scripts/vtool.py` (functions) and `plan.py` (runs a plan). Free: ffmpeg + Pillow only. Each command prints one JSON line. One command per Bash call. Help for one function: `python3 .claude/skills/edit/scripts/vtool.py <command> -h`.

## Functions (`vtool.py <command> <in> <out> …`)
| Need | Command |
|---|---|
| length, size, audio | `info <in>` |
| keep one part / drop parts | `trim --start 2 --end 14` · `cut --remove "3-5.2,10-11"` (or `--keep`) |
| split into equal parts | `split <in> <outdir> --every 60` |
| join clips | `concat <out> a.mp4 b.mp4 --transition fade --dur 0.5 --size 1080x1920` (transitions: fade, dissolve, slideleft, circleopen, zoomin, wipeleft, smoothup, fadeblack…, none) |
| vertical 9:16 | `vertical --mode crop` (fill) · `blur` (blurred background) · `fit` (bars) |
| speed | `speed --factor 1.25` (0.25–4, voice pitch kept) |
| color grade | `grade --preset luxury\|cinematic\|teal-orange\|warm\|cool\|vivid\|natural\|matte\|vintage\|bw` and/or `--brightness --contrast --saturation --gamma --warmth -1..1 --lut file.cube` |
| choose a grade by eye | `looks <in> out/<name>/looks.jpg` then Read the image |
| film look | `cinematic --bars 2.39 --grain 7 --vignette` |
| shaky / noisy picture | `stabilize` · `denoise --strength 4` · `sharpen --amount 0.8` |
| slow push-in | `zoom --to 1.15 --mode in` |
| title on screen | `text --text "…" --start 1 --end 4 --pos top --box --color #FFD400` |
| logo | `logo --image inbox/biz/<client>/logo.png --pos tr --scale 0.18` |
| cover with b-roll, keep voice | `broll --clip b.mp4 --at 5 --dur 3` |
| music under the voice | `music --music inbox/music/x.mp3 --volume 0.15` (auto ducking; `--no-duck` to switch off) |
| sound | `audio --gain 3` · `--mute` · `--add voice.mp3` · `--replace voice.mp3` |
| subtitles from .srt (any language) | `subs --srt captions.ru.srt --box --size 60 --y 0.78` |
| fade in/out | `fade --in 0.5 --out 0.8` |
| final file | `export --preset reel\|story\|post\|youtube\|telegram` (story splits into ≤60 s parts) |
| one still | `frame --at 3.5 <out.jpg>` |

Word-by-word captions in the spoken language and pause/filler cutting stay in the **reel** skill (`captions.py`, `cut.py`). Speech, language and voice-over are in the **voice** skill.

## The plan (`out/<name>/plan.json`), written by the rejissor
```json
{"name": "shoxsaroy-01", "src": "inbox/clip.mp4", "client": "shoxsaroy", "goal": "45 s Reel, luxury, uz + ru subtitles",
 "steps": [
  {"agent": "ovozchi",    "fn": "voice.transcript"},
  {"agent": "montaj",     "fn": "reel.cut",      "args": {"max": 45}},
  {"agent": "montaj",     "fn": "vtool.grade",   "args": {"preset": "luxury"}},
  {"agent": "subtitrchi", "fn": "reel.captions", "args": {"color": "#FFD400", "size": 56}},
  {"agent": "subtitrchi", "fn": "task", "task": "Translate @dir/captions.srt to Russian, keep timings", "makes": "captions.ru.srt"},
  {"agent": "subtitrchi", "fn": "vtool.subs",    "args": {"srt": "@dir/captions.ru.srt", "y": 0.88, "size": 44, "box": true}},
  {"agent": "montaj",     "fn": "vtool.music",   "args": {"music": "inbox/music/calm.mp3", "volume": 0.15}},
  {"agent": "montaj",     "fn": "vtool.export",  "args": {"preset": "reel"}},
  {"agent": "montaj",     "fn": "pixel.cover",   "in": "@2", "args": {"text": "20% BOSHLANG'ICH TO'LOV"}}
 ]}
```
- Every video step works on the previous step's video; `"in": "@src"` or `"@N"` takes another one. In args, `@dir` = `out/<name>`, `@N` = step N's output.
- `fn` names: `python3 .claude/skills/edit/scripts/plan.py fns` (grouped by agent). Args are the function's flags without `--`.
- A `"fn": "task"` step is work only an agent can do (translate, choose, write). The run stops there.

## Running it
1. `python3 .claude/skills/edit/scripts/plan.py check out/<name>/plan.json`
2. `python3 .claude/skills/edit/scripts/plan.py run out/<name>/plan.json`
3. Paused at a task → give it to the agent named in the result; it writes the file, then `plan.py done out/<name>/plan.json <N> --out <file>`; then `run` again.
4. Failed → read `error` (and `out/<name>/plan.log.jsonl`), fix that step in plan.json, `run` again: it resumes at the first unfinished step. `--from N` reruns from step N.
5. Finished → `out/<name>/final.mp4`. Look at it with `reel/scripts/frames.py` before reporting.

Never delete files. Nothing is posted.
