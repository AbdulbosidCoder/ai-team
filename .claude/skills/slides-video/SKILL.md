---
name: slides-video
description: Build a presentation and turn it into a cinematic video — slides with Ken Burns motion, rising text, transitions, color grade, film grain, voice-over in Uzbek, Russian or English, music and subtitles; also turns a ready PDF / PPTX deck or a folder of photos into a video. Use for taqdimot, prezentatsiya, slayd video, presentation video, "taqdimotni videoga aylantir", photo slideshow, cinematic promo from photos.
---

# Slides-video: a presentation that moves like a film

Script: `python3 .claude/skills/slides-video/scripts/slides2video.py` (free: ffmpeg + Pillow; voice-over via edge-tts). Prints one JSON line. One command per Bash call.

## 1. Plan the story (5–8 slides, one idea each)
Hook → problem or desire → 2–4 proofs (facts, numbers, photos) → call to action. Every number comes from "Clients" in memory or `inbox/biz/<client>/`; never invent one.

## 2. Write `out/<name>/slides.json`
```json
{"size": "1080x1920", "fps": 30,
 "theme": {"bg": "#0E0E12", "bg2": "#2A2216", "accent": "#C9A86A", "text": "#FFFFFF", "grade": "luxury", "grain": 6, "bars": false},
 "voice": {"lang": "uz", "gender": "male", "rate": "+0%"},
 "music": "auto", "music_volume": 0.16, "subtitles": true, "transition": "fade", "transition_dur": 0.7,
 "slides": [
  {"layout": "title",   "title": "Shoxsaroy Towers", "subtitle": "Premium turar-joy", "image": "inbox/biz/shoxsaroy/1.jpg", "say": "Shoxsaroy Towers — premium turar-joy majmuasi."},
  {"layout": "bullets", "title": "Atrofda hammasi bor", "bullets": ["2 ta metro bekati", "10 ta bog'cha", "3 ta park"], "say": "..."},
  {"layout": "number",  "number": "20%", "caption": "boshlang'ich to'lov, qolgani 36 oyga", "say": "..."},
  {"layout": "image",   "image": "inbox/biz/shoxsaroy/2.jpg", "caption": "Kechki ko'rinish"},
  {"layout": "quote",   "text": "...", "author": "..."},
  {"layout": "cta",     "title": "Uyingizni band qiling", "subtitle": "2 va 4 xonali", "button": "DM → NARX"}
 ]}
```
- **Layouts:** `title`, `bullets` (≤4 short bullets), `number` (one big figure), `image` (full photo, optional caption), `quote`, `cta` (button).
- **Size:** `1080x1920` Reels/Stories, `1080x1350` post, `1920x1080` YouTube/presentation.
- **Per slide:** `duration` (default 3.5 s; a voice line makes it longer by itself), `motion` (`in`, `out`, `left`, `right`, `none`), `image`.
- **Look:** `grade` = any edit-skill preset (`luxury` for Shoxsaroy, `cinematic`, `teal-orange`, `warm`, `natural`…); `grain` 0–10; `bars: true` for thin cinema bars.
- **Voice:** `lang` uz / ru / en, `gender` female / male; each slide's `say` is its line. Leave `voice` null for music only.
- **Music:** a file the owner gave (`inbox/music/…`), or `"auto"` (a generated calm pad, free), or null. Never download copyrighted songs.
- Transitions: fade, dissolve, slideleft, slideup, circleopen, zoomin, smoothleft, fadeblack, wipeleft…

## 3. Render and look
1. `python3 .claude/skills/slides-video/scripts/slides2video.py out/<name>/slides.json out/<name>/video.mp4`
2. `python3 .claude/skills/reel/scripts/frames.py out/<name>/video.mp4 out/<name>/frames.jpg`, Read it. Text too long or touching the edges → shorten it and render again. Read `notes` in the result (e.g. no voice without internet).

## Ready decks and photos
- PDF: `slides2video.py --pdf deck.pdf out/<name>/video.mp4 --size 1920x1080 --seconds 5 --music auto`
- PowerPoint (needs LibreOffice): `slides2video.py --pptx deck.pptx out/<name>/video.mp4 ...`
- Photos: `slides2video.py --images inbox/biz/shoxsaroy/photos/ out/<name>/video.mp4 --seconds 3 --grade luxury --music auto`
Then add subtitles, a logo or a voice-over with the edit and voice skills if needed.

In a montaj plan this is the `slides.video` step (`"src"` = the slides.json). Never delete files. Nothing is posted.
