"""Voice tools: which language is spoken, the transcript, clean audio, editing by text, and a voice-over.

usage:
  python3 voice.py detect     <video|audio> [--out language.json]
  python3 voice.py transcript <video|audio> <out folder>            # words.json, transcript.txt, transcript.srt, language.json
  python3 voice.py clean      <in> <out> [--level light|normal|strong] [--lufs -14]
  python3 voice.py textcut    <in> <words.json> <edited.txt> <out> [--pad 0.12]
  python3 voice.py cutwords   <in> <words.json> <out> --drop "phrase" [--drop ...]
  python3 voice.py tts        "<text>" <out.mp3> [--lang uz|ru|en] [--gender female|male] [--rate +0%] [--srt out.srt]
  python3 voice.py voices

Free: ffmpeg, local Whisper or ElevenLabs Scribe (see media.py), edge-tts (free Microsoft voices, needs internet).
Every command prints one JSON line.
"""
import argparse, difflib, json, os, re, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "reel", "scripts"))
from media import FFMPEG, detect_languages, norm_text, probe, report, run, transcribe_words  # noqa: E402

VOICES = {
    "uz": {"female": "uz-UZ-MadinaNeural", "male": "uz-UZ-SardorNeural"},
    "ru": {"female": "ru-RU-SvetlanaNeural", "male": "ru-RU-DmitryNeural"},
    "en": {"female": "en-US-AriaNeural", "male": "en-US-GuyNeural"},
}


def ts(t):
    ms = int(round(t * 1000)); return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path, cues):
    with open(path, "w", encoding="utf-8") as f:
        for i, (s, e, t) in enumerate(cues):
            f.write(f"{i + 1}\n{ts(s)} --> {ts(e)}\n{t}\n\n")


def read_words(path):
    with open(path, encoding="utf-8") as f:
        return [(w["w"], w["s"], w["e"]) for w in json.load(f)]


def keep_cut(src, keep, out):
    """Re-encode only the kept [(start, end)] ranges of src, joined in order."""
    info = probe(src); has_audio = bool(subprocess.run([FFMPEG, "-hide_banner", "-i", src], capture_output=True, text=True).stderr.count("Audio:"))
    parts, labels = [], ""
    for i, (s, e) in enumerate(keep):
        parts.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{i}]")
        if has_audio:
            parts.append(f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels += f"[v{i}]" + (f"[a{i}]" if has_audio else "")
    parts.append(f"{labels}concat=n={len(keep)}:v=1:a={1 if has_audio else 0}[v]" + ("[a]" if has_audio else ""))
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(";\n".join(parts)); script = f.name
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    args = ["-i", src, "-filter_complex_script", script, "-map", "[v]"] + (["-map", "[a]", "-c:a", "aac", "-b:a", "160k"] if has_audio else []) + \
           ["-c:v", "libx264", "-preset", os.environ.get("EDIT_PRESET", "veryfast"), "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    run(args); os.unlink(script)
    return info["duration"], sum(e - s for s, e in keep)


def ranges_from_words(words, keep_idx, pad, dur):
    """Merge kept word indices into time ranges, with a little padding, joining gaps under 0.35 s."""
    rs = []
    for i in sorted(keep_idx):
        s, e = max(0, words[i][1] - pad), min(dur, words[i][2] + pad)
        if rs and s - rs[-1][1] < 0.35:
            rs[-1][1] = max(rs[-1][1], e)
        else:
            rs.append([s, e])
    return [(round(s, 3), round(e, 3)) for s, e in rs if e - s > 0.05]


def tok(w):
    return re.sub(r"[^\w']", "", norm_text(w).lower())


# ---------------- commands ----------------

def cmd_detect(a):
    words, engine, el = transcribe_words(a.src)
    res = detect_languages(words, el)
    res.update(engine=engine, words=len(words))
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    report(tool="voice.detect", main=res["main"], share=res["share"], mixed=res["mixed"], engine=engine,
           out=a.out, sentences=res["sentences"][:8])


def cmd_transcript(a):
    os.makedirs(a.out, exist_ok=True)
    words, engine, el = transcribe_words(a.src)
    words = [(norm_text(w), s, e) for w, s, e in words]
    json.dump([{"w": w, "s": round(s, 3), "e": round(e, 3)} for w, s, e in words],
              open(os.path.join(a.out, "words.json"), "w", encoding="utf-8"), ensure_ascii=False)
    lang = detect_languages(words, el)
    json.dump(lang, open(os.path.join(a.out, "language.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from media import sentences
    sents = sentences(words)
    with open(os.path.join(a.out, "transcript.txt"), "w", encoding="utf-8") as f:
        for sn in sents:
            f.write(" ".join(w[0] for w in sn) + "\n")
    write_srt(os.path.join(a.out, "transcript.srt"), [(sn[0][1], sn[-1][2], " ".join(w[0] for w in sn)) for sn in sents])
    report(tool="voice.transcript", folder=a.out, engine=engine, words=len(words), sentences=len(sents),
           main=lang["main"], share=lang["share"], mixed=lang["mixed"],
           files=["words.json", "transcript.txt", "transcript.srt", "language.json"])


def cmd_clean(a):
    nf = {"light": -20, "normal": -25, "strong": -30}[a.level]
    chain = f"highpass=f=80,lowpass=f=12000,afftdn=nf={nf},acompressor=threshold=-20dB:ratio=3:attack=5:release=80,loudnorm=I={a.lufs}:LRA=11:TP=-1.5"
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    is_audio = a.out.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg"))
    args = ["-i", a.src, "-af", chain] + (["-vn"] if is_audio else ["-c:v", "copy", "-c:a", "aac", "-b:a", "160k"]) + [a.out]
    run(args)
    report(tool="voice.clean", out=a.out, level=a.level, lufs=a.lufs)


def cmd_textcut(a):
    """Edit by text: delete sentences or words from transcript.txt, then this keeps only what is left."""
    words = read_words(a.words)
    edited = open(a.edited, encoding="utf-8").read().split()
    src_t, ed_t = [tok(w[0]) for w in words], [tok(w) for w in edited]
    sm = difflib.SequenceMatcher(a=src_t, b=ed_t, autojunk=False)
    keep = set()
    for blk in sm.get_matching_blocks():
        keep.update(range(blk.a, blk.a + blk.size))
    added = [" ".join(edited[j1:j2]) for op, i1, i2, j1, j2 in sm.get_opcodes() if op in ("insert", "replace") and j2 > j1]
    dur = probe(a.src)["duration"]
    rs = ranges_from_words(words, keep, a.pad, dur)
    if not rs:
        report(tool="voice.textcut", error="nothing left to keep"); return
    before, after = keep_cut(a.src, rs, a.out)
    report(tool="voice.textcut", out=a.out, kept_words=len(keep), dropped_words=len(words) - len(keep),
           before=round(before, 2), after=round(after, 2), ranges=len(rs),
           note=("words added in the text can't be spoken by the video: " + "; ".join(added)[:200]) if added else None)


def cmd_cutwords(a):
    """Drop every occurrence of the given phrases (filler words, a wrong sentence, a name...)."""
    words = read_words(a.words); toks = [tok(w[0]) for w in words]; drop = set()
    for ph in a.drop:
        p = [tok(x) for x in ph.split() if tok(x)]
        for i in range(len(toks) - len(p) + 1):
            if p and toks[i:i + len(p)] == p:
                drop.update(range(i, i + len(p)))
    keep = set(range(len(words))) - drop
    rs = ranges_from_words(words, keep, a.pad, probe(a.src)["duration"])
    before, after = keep_cut(a.src, rs, a.out)
    report(tool="voice.cutwords", out=a.out, dropped_words=len(drop), before=round(before, 2), after=round(after, 2))


def parse_subs(path):
    """Cues from an .srt or .vtt file: [(start, end, text)]."""
    txt = open(path, encoding="utf-8").read().replace("\r", "")
    cues = []
    for m in re.finditer(r"(\d+:)?(\d+):(\d+)[.,](\d+) --> (\d+:)?(\d+):(\d+)[.,](\d+)[^\n]*\n(.+?)(?:\n\n|\Z)", txt, re.S):
        g = m.groups()
        s = int((g[0] or "0:")[:-1]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
        e = int((g[4] or "0:")[:-1]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
        cues.append((s, e, " ".join(g[8].split())))
    return cues


def cmd_tts(a):
    voice = a.voice or VOICES.get(a.lang, VOICES["uz"])[a.gender]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    text = a.text if not os.path.isfile(a.text) else open(a.text, encoding="utf-8").read()
    engine = None
    with tempfile.TemporaryDirectory() as d:
        subs = os.path.join(d, "s.srt")
        exe = [sys.executable, "-m", "edge_tts"] if _has("edge_tts") else ([shutil.which("edge-tts")] if shutil.which("edge-tts") else None)
        if exe:
            tf = os.path.join(d, "t.txt"); open(tf, "w", encoding="utf-8").write(text)
            p = subprocess.run(exe + ["--voice", voice, f"--rate={a.rate}", "--file", tf, "--write-media", a.out, "--write-subtitles", subs],
                               capture_output=True, text=True)
            if p.returncode == 0 and os.path.isfile(a.out) and os.path.getsize(a.out) > 0:
                engine = "edge-tts"
            else:
                err = p.stderr[-300:]
        if not engine and shutil.which("espeak-ng"):          # offline fallback, robotic but free
            wav = os.path.join(d, "e.wav")
            subprocess.run(["espeak-ng", "-v", a.lang, "-w", wav, text], check=True)
            run(["-i", wav, a.out]); engine = "espeak-ng"
        if not engine:
            report(tool="voice.tts", error="no voice engine worked: pip install edge-tts (needs internet)" + (f"; {err}" if exe else "")); return
        dur = probe(a.out)["duration"]
        if a.srt:
            cues = parse_subs(subs) if engine == "edge-tts" and os.path.isfile(subs) else []
            if not cues:                                       # spread sentences over the audio by length
                sents = [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x]
                tot = sum(len(x) for x in sents) or 1; t = 0
                for x in sents:
                    l = dur * len(x) / tot; cues.append((t, t + l, x)); t += l
            write_srt(a.srt, cues)
    report(tool="voice.tts", out=a.out, voice=voice, engine=engine, seconds=round(dur, 2), srt=a.srt)


def _has(mod):
    try:
        __import__(mod); return True
    except ImportError:
        return False


def cmd_voices(a):
    report(tool="voice.voices", voices=VOICES, edge_tts=_has("edge_tts"), espeak=bool(shutil.which("espeak-ng")))


ap = argparse.ArgumentParser(description="voice tools")
sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("detect"); p.add_argument("src"); p.add_argument("--out"); p.set_defaults(f=cmd_detect)
p = sub.add_parser("transcript"); p.add_argument("src"); p.add_argument("out"); p.set_defaults(f=cmd_transcript)
p = sub.add_parser("clean"); p.add_argument("src"); p.add_argument("out"); p.add_argument("--level", choices=["light", "normal", "strong"], default="normal")
p.add_argument("--lufs", type=float, default=-14); p.set_defaults(f=cmd_clean)
p = sub.add_parser("textcut"); p.add_argument("src"); p.add_argument("words"); p.add_argument("edited"); p.add_argument("out")
p.add_argument("--pad", type=float, default=0.12); p.set_defaults(f=cmd_textcut)
p = sub.add_parser("cutwords"); p.add_argument("src"); p.add_argument("words"); p.add_argument("out"); p.add_argument("--drop", action="append", default=[])
p.add_argument("--pad", type=float, default=0.08); p.set_defaults(f=cmd_cutwords)
p = sub.add_parser("tts"); p.add_argument("text"); p.add_argument("out"); p.add_argument("--lang", default="uz", choices=list(VOICES))
p.add_argument("--gender", default="female", choices=["female", "male"]); p.add_argument("--voice"); p.add_argument("--rate", default="+0%")
p.add_argument("--srt"); p.set_defaults(f=cmd_tts)
p = sub.add_parser("voices"); p.set_defaults(f=cmd_voices)

if __name__ == "__main__":
    a = ap.parse_args(); a.f(a)
