"""Montaj on the phone: raw clip -> vertical Reel with captions and a cover, using the reel and pixel skill scripts.

The bot calls edit() when you send it a video (or /edit <file>). It runs the same steps as the reel and
pixel skills: cut pauses and fillers, burn in 3-word captions, pick a cover frame with short bold text,
write notes.md, then move the raw clip from inbox/ to done/. Nothing is posted anywhere.

Needs ffmpeg and a speech-to-text engine. On Android (Termux) that is whisper.cpp: set WHISPER_CPP_MODEL
in .env (setup-termux.sh does it). Brand rules (length, colors) are read from brain/memory.jsonl.

CLI test:  python3 tgbot/montaj.py inbox/clip.mp4 [--cover "UCH SO'Z MATN"]
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REEL = ROOT / ".claude" / "skills" / "reel" / "scripts"
PIXEL = ROOT / ".claude" / "skills" / "pixel" / "scripts"
INBOX, OUT, DONE = ROOT / "inbox", ROOT / "out", ROOT / "done"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".3gp", ".avi"}
TG_SEND_LIMIT = 48 * 1024 * 1024          # bots may upload up to 50 MB
_lock = asyncio.Lock()                    # one edit at a time: a phone CPU is busy enough with one

sys.path.insert(0, str(REEL))


def brand() -> dict:
    """Length, pause and colors from the shared brain (brain/memory.jsonl, entity "Brand rules"); .env overrides."""
    rules = {"max": 45.0, "pause": 0.45, "color": "#FFD400", "cover_color": "#FFD400", "words": 3}
    try:
        for line in (ROOT / "brain" / "memory.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("type") != "entity" or row.get("name") != "Brand rules":
                continue
            for obs in row.get("observations", []):
                low = obs.lower()
                if m := re.search(r"(\d+)\s*seconds?\s*max", low):
                    rules["max"] = float(m[1])
                if "half a second" in low:
                    rules["pause"] = 0.5
                elif m := re.search(r"pause longer than ([\d.]+)", low):
                    rules["pause"] = float(m[1])
                hexes = re.findall(r"#[0-9a-fA-F]{6}", obs)
                if low.startswith("caption") and hexes:
                    rules["color"] = hexes[0]
                    if m := re.search(r"(\d+)\s*words? per line", low):
                        rules["words"] = int(m[1])
                if low.startswith("cover") and hexes:
                    rules["cover_color"] = hexes[0]
    except (OSError, json.JSONDecodeError):
        pass
    if os.getenv("EDIT_MAX"):
        rules["max"] = float(os.environ["EDIT_MAX"])
    if os.getenv("EDIT_COLOR"):
        rules["color"] = rules["cover_color"] = os.environ["EDIT_COLOR"]
    return rules


def ready() -> str | None:
    """None when editing can run here, otherwise what is missing (in Uzbek, shown to the user)."""
    if not shutil.which(os.getenv("FFMPEG", "ffmpeg")):
        return "ffmpeg topilmadi. Termux: pkg install ffmpeg (Render serverida montaj ishlamaydi)."
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        return "numpy / pillow yo'q. Termux: pkg install python-numpy python-pillow"
    from media import whisper_cpp
    if whisper_cpp():
        return None
    for mod in ("faster_whisper", "sherpa_onnx"):
        try:
            __import__(mod)
            return None
        except ImportError:
            continue
    return ("Nutqni tanish (speech-to-text) yo'q. Termux: bash setup-montaj.sh, "
            "keyin .env da WHISPER_CPP_MODEL ni tekshiring.")


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXT


def clips() -> list[Path]:
    return sorted((p for p in INBOX.glob("*") if p.is_file() and is_video(p)), key=lambda p: p.stat().st_mtime)


def safe_name(name: str) -> str:
    stem = re.sub(r"[^\w-]+", "_", Path(name).stem, flags=re.UNICODE).strip("_")[:40]
    return stem or datetime.now().strftime("clip_%Y%m%d_%H%M%S")


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(2, 1000):
        p = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not p.exists():
            return p
    raise RuntimeError(f"too many copies of {path.name}")


def take_in(src: Path) -> Path:
    """Copy a clip from phone storage into inbox/ (the original stays where it was)."""
    src = src.expanduser().resolve()
    if src.parent == INBOX.resolve():
        return src
    INBOX.mkdir(parents=True, exist_ok=True)
    dst = _unique(INBOX / (safe_name(src.name) + src.suffix.lower()))
    shutil.copy2(src, dst)
    return dst


async def _step(script: Path, *args: str) -> dict:
    """Run one skill script; it prints one JSON line with its result."""
    proc = await asyncio.create_subprocess_exec(sys.executable, str(script), *args, cwd=str(ROOT),
                                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"{script.name}: {err.decode(errors='replace')[-700:]}")
    lines = [ln for ln in out.decode(errors="replace").splitlines() if ln.startswith("{")]
    return json.loads(lines[-1]) if lines else {}


def _texts(transcript: str, hint: str | None) -> tuple[str, str]:
    """(title, cover text). Your caption on the video wins; then Claude if a key is set; then simple rules."""
    if hint and hint.strip():
        hint = " ".join(hint.split())
        return hint[:60], " ".join(hint.split()[:3]).upper()
    try:
        import extract
        if extract._want_claude() and transcript:
            js = extract._claude_json(
                "You write titles and cover text for short vertical videos. Title: under 60 characters, plain and "
                "specific, no clickbait. Cover: the strongest idea in at most 3 words. Use the video's language.",
                transcript[:4000],
                {"type": "object", "additionalProperties": False, "required": ["title", "cover"],
                 "properties": {"title": {"type": "string"}, "cover": {"type": "string"}}})
            return js["title"].strip()[:60], " ".join(js["cover"].split()[:3]).upper()
    except Exception:  # no key, no network, API error: fall back to rules
        pass
    first = re.split(r"(?<=[.!?])\s+", transcript.strip())[0] if transcript.strip() else "Yangi video"
    words = [w for w in re.sub(r"[^\w\s'-]", "", first).split() if w]
    return first[:60], " ".join(words[:3]).upper() or "YANGI VIDEO"


async def _telegram_copy(edit: Path) -> Path:
    """The edit itself if it fits Telegram's 50 MB bot upload limit, else a lighter 720p copy next to it."""
    if edit.stat().st_size <= TG_SEND_LIMIT:
        return edit
    small = edit.with_name("edit_telegram.mp4")
    proc = await asyncio.create_subprocess_exec(
        os.getenv("FFMPEG", "ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(edit),
        "-vf", "scale=720:1280", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "128k",
        str(small))
    await proc.wait()
    return small


async def edit(src: Path, hint: str | None = None, progress=None) -> dict:
    """Edit one clip. progress(text) is awaited between steps, if given."""
    async def say(text):
        if progress:
            await progress(text)

    async with _lock:
        rules = brand()
        name = safe_name(src.name)
        out = OUT / name
        if out.exists():
            out = _unique(out)
        out.mkdir(parents=True)
        cut, final, srt, cover = out / "cut.mp4", out / "edit.mp4", out / "captions.srt", out / "cover.jpg"

        await say("✂️ 1/3 Pauzalar va «um/uh» kesilmoqda…")
        c = await _step(REEL / "cut.py", str(src), str(cut), "--max", str(rules["max"]), "--pause", str(rules["pause"]))
        await say("💬 2/3 Subtitrlar yozilmoqda…")
        cap = await _step(REEL / "captions.py", str(cut), str(final), "--srt", str(srt), "--color", rules["color"],
                          "--words", str(rules["words"]), "--size", "56")
        transcript = cap.get("transcript", "")
        title, cover_text = await asyncio.to_thread(_texts, transcript, hint)
        await say("🖼 3/3 Muqova tayyorlanmoqda…")
        th = await _step(PIXEL / "thumbnail.py", str(cut), str(cover), "--text", cover_text, "--color", rules["cover_color"])

        hook = re.split(r"(?<=[.!?])\s+", transcript.strip())[0] if transcript.strip() else ""
        (out / "notes.md").write_text(
            f"# {title}\n\n"
            f"- Hook: {hook}\n"
            f"- Raw length: {c.get('raw_seconds')} s\n"
            f"- Edit length: {c.get('edit_seconds')} s\n"
            f"- Seconds removed: {c.get('removed_seconds')} s\n"
            f"- Fillers removed: {', '.join(c.get('fillers_removed') or []) or '-'}\n"
            f"- Speech-to-text: {cap.get('engine')}\n"
            f"- Cover text: {cover_text}\n\n"
            f"## Transcript\n\n{transcript}\n", encoding="utf-8")

        moved = None
        if src.resolve().parent == INBOX.resolve():       # finished: raw clip goes to done/ (never deleted)
            DONE.mkdir(exist_ok=True)
            moved = _unique(DONE / src.name)
            shutil.move(str(src), moved)
        send = await _telegram_copy(final)
        return {"folder": str(out.relative_to(ROOT)), "edit": str(final), "send": str(send), "cover": str(cover),
                "notes": str(out / "notes.md"), "title": title, "cover_text": cover_text,
                "raw_seconds": c.get("raw_seconds"), "edit_seconds": c.get("edit_seconds"),
                "removed_seconds": c.get("removed_seconds"), "engine": cap.get("engine"),
                "frame_at": th.get("frame_at_seconds"), "raw_moved_to": str(moved.relative_to(ROOT)) if moved else None}


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Raw clip -> Reel with captions and a cover")
    ap.add_argument("clip")
    ap.add_argument("--cover", default=None, help="cover text / title (default: from the transcript)")
    a = ap.parse_args(argv)
    problem = ready()
    if problem:
        print(json.dumps({"ok": False, "error": problem}, ensure_ascii=False))
        return 1
    src = take_in(Path(a.clip))

    async def progress(text):
        print(text, file=sys.stderr)

    res = asyncio.run(edit(src, a.cover, progress))
    print(json.dumps({"ok": True, **res}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import db  # noqa: F401  (loads .env / .env.local, e.g. WHISPER_CPP_MODEL)
    sys.exit(main(sys.argv[1:]))
