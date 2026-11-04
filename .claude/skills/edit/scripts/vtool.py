"""Video tools for the montaj agents: everything an editor does, one command each, all on free ffmpeg + Pillow.

usage: python3 vtool.py <command> <in> <out> [options]      (run `python3 vtool.py fns` for the full list)

  info      <in>                                   length, size, fps, audio
  trim      <in> <out> --start 2 --end 14.5         keep one part
  cut       <in> <out> --remove "3-5.2,10-11"       drop parts   (or --keep "0-4,6-9")
  split     <in> <outdir> --every 60                 equal parts (Instagram story = 60 s)
  concat    <out> a.mp4 b.mp4 ... --transition fade --dur 0.5
  vertical  <in> <out> --mode crop|blur|fit --size 1080x1920
  speed     <in> <out> --factor 1.25
  grade     <in> <out> --preset cinematic|warm|cool|vivid|bw|vintage|matte|luxury|natural|teal-orange
                       [--brightness 0.02 --contrast 1.1 --saturation 1.1 --gamma 1.0 --warmth 0.3 --lut file.cube]
  looks     <in> <out.jpg> [--at 3]                 one frame in every preset, to choose a grade
  cinematic <in> <out> [--bars 2.39] [--grain 8] [--vignette]
  stabilize <in> <out>
  denoise   <in> <out> [--strength 4]
  sharpen   <in> <out> [--amount 0.8]
  zoom      <in> <out> --to 1.15 [--mode in|out] [--start 0 --end <len>]
  fade      <in> <out> [--in 0.5] [--out 0.8]
  text      <in> <out> --text "20% boshlang'ich to'lov" --start 1 --end 4 [--pos top|center|bottom] [--size 80] [--color #FFD400] [--box]
  logo      <in> <out> --image logo.png [--pos tr|tl|br|bl] [--scale 0.18] [--opacity 0.9]
  broll     <in> <out> --clip b.mp4 --at 5 [--dur 3]   cover the picture, keep the voice
  music     <in> <out> --music song.mp3 [--volume 0.18] [--no-duck]
  audio     <in> <out> [--replace voice.mp3 | --add voice.mp3 --volume 1.0 | --mute | --gain 3]
  subs      <in> <out> --srt captions.ru.srt [--size 60] [--color #FFFFFF] [--y 0.78] [--box] [--upper]
  export    <in> <out> --preset reel|story|post|youtube|telegram
  frame     <in> <out.jpg> --at 3.5
Every command prints one JSON line. Nothing is uploaded.
"""
import argparse, json, math, os, re, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
REEL = os.path.join(HERE, "..", "..", "reel", "scripts")
sys.path.insert(0, REEL)
from media import FFMPEG, norm_text, probe, report, run  # noqa: E402

FONT = os.path.join(REEL, "fonts", "Geist.ttf")
PRESET = os.environ.get("EDIT_PRESET", "veryfast")


def venc(crf=18):
    return ["-c:v", "libx264", "-preset", PRESET, "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def has_audio(src):
    return "Audio:" in subprocess.run([FFMPEG, "-hide_banner", "-i", src], capture_output=True, text=True).stderr


def has_filter(name):
    return f" {name} " in subprocess.run([FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True).stdout


def mkdir_for(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)


def simple(src, out, vf=None, af=None, extra=None, crf=18):
    """Re-encode with a video filter and/or audio filter; audio copied when untouched."""
    mkdir_for(out)
    args = ["-i", src]
    if vf: args += ["-vf", vf]
    if af and has_audio(src): args += ["-af", af, "-c:a", "aac", "-b:a", "160k"]
    else: args += ["-c:a", "copy"]
    run(args + (extra or []) + venc(crf) + [out])


def ranges(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if part:
            s, e = part.split("-"); out.append((float(s), float(e)))
    return sorted(out)


def keep_ranges(src, keep, out):
    has_a = has_audio(src); parts, labels = [], ""
    for i, (s, e) in enumerate(keep):
        parts.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{i}]")
        if has_a: parts.append(f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels += f"[v{i}]" + (f"[a{i}]" if has_a else "")
    parts.append(f"{labels}concat=n={len(keep)}:v=1:a={int(has_a)}[v]" + ("[a]" if has_a else ""))
    graph(src_inputs=["-i", src], parts=parts, maps=["[v]"] + (["[a]"] if has_a else []), out=out)


def graph(src_inputs, parts, maps, out, crf=18, audio_copy=None):
    """Run a filter_complex written to a script file (long graphs stay off the command line)."""
    mkdir_for(out)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(";\n".join(parts)); script = f.name
    args = src_inputs + ["-filter_complex_script", script]
    for m in maps: args += ["-map", m]
    if audio_copy is not None: args += ["-map", audio_copy, "-c:a", "copy"]
    elif any(m.startswith("[a") for m in maps): args += ["-c:a", "aac", "-b:a", "160k"]
    try:
        run(args + venc(crf) + [out])
    finally:
        os.unlink(script)


def frame_filter(mode, W, H, tag=""):
    """Filter that turns any picture into W x H: crop (fill), blur (blurred background) or fit (black bars)."""
    if mode == "crop":
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    if mode == "fit":
        return f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    t = tag
    return (f"split[bg{t}][fg{t}];[bg{t}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:3,eq=brightness=-0.08[b{t}];"
            f"[fg{t}]scale={W}:{H}:force_original_aspect_ratio=decrease[f{t}];[b{t}][f{t}]overlay=(W-w)/2:(H-h)/2,setsar=1")


GRADES = {
    "natural":     "eq=contrast=1.05:saturation=1.08",
    "cinematic":   "colorbalance=rs=-0.05:gs=-0.02:bs=0.08:rh=0.08:gh=0.02:bh=-0.06,eq=contrast=1.12:saturation=0.9:gamma=0.97,vignette=PI/5",
    "teal-orange": "colorbalance=rs=-0.12:gs=-0.03:bs=0.14:rm=0.06:bm=-0.04:rh=0.12:gh=0.03:bh=-0.10,eq=contrast=1.1:saturation=1.05",
    "warm":        "colorbalance=rm=0.06:gm=0.02:bm=-0.06:rh=0.04:bh=-0.04,eq=saturation=1.1",
    "cool":        "colorbalance=rm=-0.05:bm=0.07:bh=0.04,eq=saturation=1.0:contrast=1.04",
    "vivid":       "eq=contrast=1.1:saturation=1.35,unsharp=5:5:0.6",
    "bw":          "hue=s=0,eq=contrast=1.2:gamma=0.95",
    "vintage":     "curves=preset=vintage,noise=alls=8:allf=t,vignette=PI/4",
    "matte":       "curves=all='0/0.08 0.5/0.5 1/0.94',eq=saturation=0.88:contrast=0.98",
    "luxury":      "colorbalance=rh=0.05:gh=0.02:bh=-0.03:bs=0.03,eq=contrast=1.08:saturation=1.05:gamma=0.98,vignette=PI/6",
}


def grade_filter(a):
    f = [GRADES[a.preset]] if a.preset else []
    eq = {k: getattr(a, k) for k in ("brightness", "contrast", "saturation", "gamma") if getattr(a, k) is not None}
    if eq: f.append("eq=" + ":".join(f"{k}={v}" for k, v in eq.items()))
    if a.warmth:
        w = max(-1.0, min(1.0, a.warmth)) * 0.1
        f.append(f"colorbalance=rm={w:.3f}:bm={-w:.3f}:rh={w * 0.6:.3f}:bh={-w * 0.6:.3f}")
    if a.lut: f.append(f"lut3d=file='{a.lut}'")
    return ",".join(f) or "null"


def font(size, weight=800):
    f = ImageFont.truetype(FONT, size)
    try: f.set_variation_by_axes([weight])
    except Exception: pass
    return f


def wrap(text, fnt, max_w):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if fnt.getlength(t) <= max_w or not cur: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines


def text_png(text, W, H, size, color, y_frac, box=False, upper=False, path=None, weight=800):
    """Full-frame transparent PNG with centred, wrapped, outlined text (Uzbek latin, Cyrillic and English)."""
    text = norm_text(text); text = text.upper() if upper else text
    fnt = font(size, weight); lines = wrap(text, fnt, W * 0.86)
    lh = int(size * 1.18); th = lh * len(lines)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    y = int(H * y_frac - th / 2); y = max(int(size * 0.3), min(H - th - int(size * 0.3), y))
    col = tuple(int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    for i, ln in enumerate(lines):
        w = fnt.getlength(ln); x = (W - w) / 2; yy = y + i * lh
        if box:
            pad = size * 0.28
            d.rounded_rectangle((x - pad, yy - pad * 0.35, x + w + pad, yy + lh - pad * 0.1), radius=int(size * 0.25), fill=(0, 0, 0, 170))
            d.text((x, yy), ln, font=fnt, fill=col)
        else:
            d.text((x, yy), ln, font=fnt, fill=col, stroke_width=max(3, size // 12), stroke_fill=(0, 0, 0, 255))
    if path: im.save(path)
    return im


def parse_subs(path):
    txt = open(path, encoding="utf-8").read().replace("\r", "")
    cues = []
    for m in re.finditer(r"(\d+:)?(\d+):(\d+)[.,](\d+) --> (\d+:)?(\d+):(\d+)[.,](\d+)[^\n]*\n(.+?)(?:\n\n|\Z)", txt, re.S):
        g = m.groups()
        s = int((g[0] or "0:")[:-1]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
        e = int((g[4] or "0:")[:-1]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
        cues.append((s, e, " ".join(re.sub(r"<[^>]+>", "", g[8]).split())))
    return cues


def overlay_timeline(src, out, items, W, H):
    """Burn timed full-frame PNGs [(start, end, png)] over the video in one pass (an ffconcat image stream)."""
    with tempfile.TemporaryDirectory() as d:
        blank = os.path.join(d, "blank.png"); Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
        lst, t = ["ffconcat version 1.0"], 0.0
        for s, e, png in items:
            if s > t + 0.001: lst += [f"file '{blank}'", f"duration {s - t:.3f}"]
            lst += [f"file '{png}'", f"duration {max(0.04, e - max(s, t)):.3f}"]; t = max(t, e)
        lst += [f"file '{blank}'", "duration 1", f"file '{blank}'"]
        lp = os.path.join(d, "list.txt"); open(lp, "w").write("\n".join(lst))
        has_a = has_audio(src)
        graph(["-i", src, "-f", "concat", "-safe", "0", "-i", lp],
              ["[1:v]format=rgba[s]", "[0:v][s]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v]"],
              ["[v]"], out, audio_copy="0:a?" if has_a else None)


# ---------------- commands ----------------

def c_info(a):
    i = probe(a.src); report(tool="vtool.info", src=a.src, audio=has_audio(a.src), **{k: round(v, 3) if isinstance(v, float) else v for k, v in i.items()})


def c_trim(a):
    end = a.end if a.end is not None else probe(a.src)["duration"]
    keep_ranges(a.src, [(a.start, end)], a.out); report(tool="vtool.trim", out=a.out, seconds=round(end - a.start, 2))


def c_cut(a):
    dur = probe(a.src)["duration"]
    if a.keep: keep = ranges(a.keep)
    else:
        keep, t = [], 0.0
        for s, e in ranges(a.remove or ""):
            if s > t: keep.append((t, s))
            t = max(t, e)
        if t < dur: keep.append((t, dur))
    keep = [(s, min(e, dur)) for s, e in keep if min(e, dur) - s > 0.05]
    keep_ranges(a.src, keep, a.out)
    report(tool="vtool.cut", out=a.out, before=round(dur, 2), after=round(sum(e - s for s, e in keep), 2), parts=len(keep))


def c_split(a):
    dur = probe(a.src)["duration"]; os.makedirs(a.out, exist_ok=True)
    n = max(1, math.ceil(dur / a.every - 0.02)); outs = []
    base = os.path.splitext(os.path.basename(a.src))[0]
    for i in range(n):
        s = i * dur / n; e = (i + 1) * dur / n; o = os.path.join(a.out, f"{base}-{i + 1:02d}.mp4")
        keep_ranges(a.src, [(s, e)], o); outs.append(o)
    report(tool="vtool.split", parts=outs, seconds_each=round(dur / n, 2))


def c_concat(a):
    files = a.files; infos = [probe(f) for f in files]
    W, H = (int(x) for x in a.size.split("x")) if a.size else (infos[0]["width"], infos[0]["height"])
    fps = a.fps; d = a.dur if a.transition != "none" else 0
    inputs, parts = [], []
    for i, f in enumerate(files):
        inputs += ["-i", f]
        parts.append(f"[{i}:v]{frame_filter(a.mode, W, H, tag=str(i))},fps={fps},format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v{i}]")
        if has_audio(f):
            parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}]")
        else:
            parts.append(f"aevalsrc=0|0:d={infos[i]['duration']:.3f}:s=48000[a{i}]")
    if d <= 0:
        parts.append("".join(f"[v{i}][a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=1:a=1[v][a]")
    else:
        off, prev_v, prev_a = 0.0, "v0", "a0"
        for i in range(1, len(files)):
            off += infos[i - 1]["duration"] - d
            nv, na = f"x{i}", f"y{i}"
            parts.append(f"[{prev_v}][v{i}]xfade=transition={a.transition}:duration={d}:offset={off:.3f}[{nv}]")
            parts.append(f"[{prev_a}][a{i}]acrossfade=d={d}[{na}]")
            prev_v, prev_a = nv, na
        parts.append(f"[{prev_v}]null[v]"); parts.append(f"[{prev_a}]anull[a]")
    graph(inputs, parts, ["[v]", "[a]"], a.out)
    report(tool="vtool.concat", out=a.out, clips=len(files), transition=a.transition, seconds=round(probe(a.out)["duration"], 2))


def c_vertical(a):
    W, H = (int(x) for x in a.size.split("x"))
    simple(a.src, a.out, vf=frame_filter(a.mode, W, H)); report(tool="vtool.vertical", out=a.out, size=a.size, mode=a.mode)


def c_speed(a):
    f = a.factor; at, x = [], f
    while x > 2.0: at.append("atempo=2.0"); x /= 2.0
    while x < 0.5: at.append("atempo=0.5"); x /= 0.5
    at.append(f"atempo={x:.4f}")
    simple(a.src, a.out, vf=f"setpts=PTS/{f}", af=",".join(at)); report(tool="vtool.speed", out=a.out, factor=f)


def c_grade(a):
    vf = grade_filter(a); simple(a.src, a.out, vf=vf); report(tool="vtool.grade", out=a.out, preset=a.preset, filter=vf)


def c_looks(a):
    i = probe(a.src); at = a.at if a.at is not None else i["duration"] / 2
    tw = 360; th = int(tw * i["height"] / max(1, i["width"])); names = ["original"] + list(GRADES)
    cols = 4; rows = math.ceil(len(names) / cols); sheet = Image.new("RGB", (cols * (tw + 10) + 10, rows * (th + 46) + 10), (14, 14, 18))
    dr = ImageDraw.Draw(sheet); fnt = font(24, 600)
    for k, n in enumerate(names):
        vf = f"scale={tw}:{th}" + ("" if n == "original" else "," + GRADES[n])
        raw = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", a.src, "-frames:v", "1", "-vf", vf,
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        if len(raw) < tw * th * 3: continue
        x, y = 10 + (k % cols) * (tw + 10), 10 + (k // cols) * (th + 46)
        sheet.paste(Image.frombuffer("RGB", (tw, th), raw), (x, y)); dr.text((x, y + th + 8), n, font=fnt, fill=(240, 240, 240))
    mkdir_for(a.out); sheet.save(a.out, quality=88); report(tool="vtool.looks", out=a.out, presets=names, at=round(at, 2))


def c_cinematic(a):
    i = probe(a.src); W, H = i["width"], i["height"]; f = []
    if a.grain: f.append(f"noise=alls={a.grain}:allf=t")
    if a.vignette: f.append("vignette=PI/5")
    if a.bars:
        if W >= H:
            bh = max(0, int((H - W / a.bars) / 2)); f.append(f"drawbox=0:0:iw:{bh}:black:t=fill,drawbox=0:ih-{bh}:iw:{bh}:black:t=fill")
        else:   # vertical video: thin cinematic bars top and bottom
            bh = int(H * 0.06); f.append(f"drawbox=0:0:iw:{bh}:black:t=fill,drawbox=0:ih-{bh}:iw:{bh}:black:t=fill")
    simple(a.src, a.out, vf=",".join(f) or "null"); report(tool="vtool.cinematic", out=a.out, bars=a.bars, grain=a.grain, vignette=a.vignette)


def c_stabilize(a):
    if has_filter("vidstabdetect"):
        with tempfile.TemporaryDirectory() as d:
            trf = os.path.join(d, "t.trf")
            run(["-i", a.src, "-vf", f"vidstabdetect=shakiness=6:accuracy=12:result={trf}", "-f", "null", "-"])
            simple(a.src, a.out, vf=f"vidstabtransform=input={trf}:smoothing=20:zoom=3,unsharp=5:5:0.6")
        method = "vidstab"
    else:
        simple(a.src, a.out, vf="deshake"); method = "deshake"
    report(tool="vtool.stabilize", out=a.out, method=method)


def c_denoise(a):
    s = a.strength; simple(a.src, a.out, vf=f"hqdn3d={s}:{s * 0.75:.2f}:{s * 1.5:.2f}:{s * 1.1:.2f}"); report(tool="vtool.denoise", out=a.out, strength=s)


def c_sharpen(a):
    simple(a.src, a.out, vf=f"unsharp=5:5:{a.amount}:3:3:0.0"); report(tool="vtool.sharpen", out=a.out, amount=a.amount)


def c_zoom(a):
    i = probe(a.src); W, H = i["width"], i["height"]; s = a.start; e = a.end if a.end is not None else i["duration"]
    z0, z1 = (1.0, a.to) if a.mode == "in" else (a.to, 1.0)
    z = f"({z0}+({z1}-{z0})*min(1,max(0,(t-{s})/{max(0.1, e - s)})))"
    vf = (f"scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,crop={W}:{H}:(iw-{W})/2:(ih-{H})/2,setsar=1")
    simple(a.src, a.out, vf=vf); report(tool="vtool.zoom", out=a.out, mode=a.mode, to=a.to)


def c_fade(a):
    dur = probe(a.src)["duration"]; vf, af = [], []
    if a.fin: vf.append(f"fade=t=in:st=0:d={a.fin}"); af.append(f"afade=t=in:st=0:d={a.fin}")
    if a.fout: vf.append(f"fade=t=out:st={dur - a.fout:.3f}:d={a.fout}"); af.append(f"afade=t=out:st={dur - a.fout:.3f}:d={a.fout}")
    simple(a.src, a.out, vf=",".join(vf) or "null", af=",".join(af) or None); report(tool="vtool.fade", out=a.out)


def c_text(a):
    i = probe(a.src); W, H = i["width"], i["height"]; end = a.end if a.end is not None else i["duration"]
    y = {"top": 0.16, "center": 0.5, "bottom": 0.80}[a.pos]
    with tempfile.TemporaryDirectory() as d:
        png = os.path.join(d, "t.png"); text_png(a.text, W, H, a.size, a.color, y, a.box, a.upper, png)
        fi = 0.3; parts = [f"[1:v]format=rgba,fade=t=in:st={a.start}:d={fi}:alpha=1,fade=t=out:st={max(a.start, end - fi):.3f}:d={fi}:alpha=1[t]",
                           f"[0:v][t]overlay=0:0:shortest=1:enable='between(t,{a.start},{end})',format=yuv420p[v]"]
        graph(["-i", a.src, "-loop", "1", "-framerate", str(round(i["fps"] or 30)), "-i", png], parts, ["[v]"], a.out,
              audio_copy="0:a?" if has_audio(a.src) else None)
    report(tool="vtool.text", out=a.out, text=a.text, start=a.start, end=round(end, 2))


def c_logo(a):
    i = probe(a.src); W, H = i["width"], i["height"]; m = int(min(W, H) * 0.04); lw = int(W * a.scale)
    pos = {"tr": (f"W-w-{m}", f"{m}"), "tl": (f"{m}", f"{m}"), "br": (f"W-w-{m}", f"H-h-{m}"), "bl": (f"{m}", f"H-h-{m}")}[a.pos]
    parts = [f"[1:v]scale={lw}:-1,format=rgba,colorchannelmixer=aa={a.opacity}[l]", f"[0:v][l]overlay={pos[0]}:{pos[1]},format=yuv420p[v]"]
    graph(["-i", a.src, "-i", a.image], parts, ["[v]"], a.out, audio_copy="0:a?" if has_audio(a.src) else None)
    report(tool="vtool.logo", out=a.out, pos=a.pos)


def c_broll(a):
    i = probe(a.src); W, H = i["width"], i["height"]; dur = a.dur or probe(a.clip)["duration"]
    parts = [f"[1:v]trim=0:{dur},setpts=PTS-STARTPTS+{a.at}/TB,{frame_filter('crop', W, H, tag='x')}[b]",
             f"[0:v][b]overlay=0:0:eof_action=pass:enable='between(t,{a.at},{a.at + dur})',format=yuv420p[v]"]
    graph(["-i", a.src, "-i", a.clip], parts, ["[v]"], a.out, audio_copy="0:a?" if has_audio(a.src) else None)
    report(tool="vtool.broll", out=a.out, at=a.at, seconds=round(dur, 2))


def c_music(a):
    dur = probe(a.src)["duration"]; fo = min(2.0, dur / 4)
    m = f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={a.volume},afade=t=in:st=0:d=1,afade=t=out:st={dur - fo:.3f}:d={fo:.2f},atrim=0:{dur:.3f}[m]"
    if has_audio(a.src):
        parts = [m, "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit[v1][sc]"]
        if a.no_duck: parts.append("[v1][m]amix=inputs=2:duration=first:normalize=0[a]"); parts[1] = "[0:a]aformat=sample_rates=48000:channel_layouts=stereo[v1]"
        else: parts += ["[m][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md]", "[v1][md]amix=inputs=2:duration=first:normalize=0[a]"]
    else:
        parts = [m, "[m]anull[a]"]
    parts.append("[0:v]null[v]")
    graph(["-i", a.src, "-stream_loop", "-1", "-i", a.music], parts, ["[v]", "[a]"], a.out)
    report(tool="vtool.music", out=a.out, volume=a.volume, ducking=not a.no_duck)


def c_audio(a):
    if a.mute:
        mkdir_for(a.out); run(["-i", a.src, "-an", "-c:v", "copy", a.out])
    elif a.replace:
        mkdir_for(a.out); run(["-i", a.src, "-i", a.replace, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", a.out])
    elif a.add:
        if has_audio(a.src):
            parts = [f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={a.volume}[x]",
                     "[0:a]aformat=sample_rates=48000:channel_layouts=stereo[o]", "[o][x]amix=inputs=2:duration=first:normalize=0[a]", "[0:v]null[v]"]
            graph(["-i", a.src, "-i", a.add], parts, ["[v]", "[a]"], a.out)
        else:
            mkdir_for(a.out); run(["-i", a.src, "-i", a.add, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", a.out])
    else:
        mkdir_for(a.out); run(["-i", a.src, "-af", f"volume={a.gain}dB", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", a.out])
    report(tool="vtool.audio", out=a.out)


def c_subs(a):
    i = probe(a.src); W, H = i["width"], i["height"]; cues = parse_subs(a.srt)
    with tempfile.TemporaryDirectory() as d:
        items = []
        for k, (s, e, t) in enumerate(cues):
            png = os.path.join(d, f"c{k:04d}.png"); text_png(t, W, H, a.size, a.color, a.y, a.box, a.upper, png, weight=700); items.append((s, e, png))
        overlay_timeline(a.src, a.out, items, W, H)
    report(tool="vtool.subs", out=a.out, cues=len(cues), srt=a.srt)


EXPORTS = {
    "reel":     {"size": "1080x1920", "mode": "crop", "crf": 20, "max": None},
    "story":    {"size": "1080x1920", "mode": "blur", "crf": 20, "max": 60},
    "post":     {"size": "1080x1350", "mode": "blur", "crf": 20, "max": None},
    "youtube":  {"size": "1920x1080", "mode": "fit",  "crf": 19, "max": None},
    "telegram": {"size": "1080x1920", "mode": "crop", "crf": 24, "max": None},
}


def c_export(a):
    p = EXPORTS[a.preset]; W, H = (int(x) for x in p["size"].split("x")); mkdir_for(a.out)
    with tempfile.TemporaryDirectory() as d:
        tmp = os.path.join(d, "e.mp4")
        run(["-i", a.src, "-vf", frame_filter(p["mode"], W, H) + ",fps=30", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
             "-maxrate", "10M", "-bufsize", "20M"] + venc(p["crf"]) + [tmp])
        dur = probe(tmp)["duration"]
        if p["max"] and dur > p["max"] + 0.5:
            outdir = os.path.splitext(a.out)[0] + "-parts"
            ns = argparse.Namespace(src=tmp, out=outdir, every=p["max"]); c_split(ns); return
        shutil.move(tmp, a.out)
    report(tool="vtool.export", out=a.out, preset=a.preset, size=p["size"], seconds=round(dur, 2))


def c_frame(a):
    mkdir_for(a.out); run(["-ss", f"{a.at}", "-i", a.src, "-frames:v", "1", "-q:v", "2", a.out]); report(tool="vtool.frame", out=a.out, at=a.at)


def c_fns(a):
    report(tool="vtool.fns", commands=sorted(k for k in CMDS if k != "fns"), grades=sorted(GRADES), exports=sorted(EXPORTS),
           transitions=["fade", "fadeblack", "fadewhite", "dissolve", "wipeleft", "wiperight", "slideleft", "slideright", "slideup",
                        "circleopen", "circleclose", "radial", "smoothleft", "smoothup", "zoomin", "pixelize", "none"])


CMDS = {}
ap = argparse.ArgumentParser(description="video tools", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
sp = ap.add_subparsers(dest="cmd", required=True)


def add(name, fn, io=True):
    p = sp.add_parser(name); CMDS[name] = fn; p.set_defaults(f=fn)
    if io: p.add_argument("src"); p.add_argument("out")
    return p


add("info", c_info, io=False).add_argument("src")
p = add("trim", c_trim); p.add_argument("--start", type=float, default=0); p.add_argument("--end", type=float)
p = add("cut", c_cut); p.add_argument("--remove"); p.add_argument("--keep")
p = add("split", c_split); p.add_argument("--every", type=float, default=60)
p = add("concat", c_concat, io=False); p.add_argument("out"); p.add_argument("files", nargs="+"); p.add_argument("--transition", default="fade")
p.add_argument("--dur", type=float, default=0.5); p.add_argument("--size"); p.add_argument("--fps", type=int, default=30); p.add_argument("--mode", default="blur", choices=["crop", "blur", "fit"])
p = add("vertical", c_vertical); p.add_argument("--mode", default="crop", choices=["crop", "blur", "fit"]); p.add_argument("--size", default="1080x1920")
p = add("speed", c_speed); p.add_argument("--factor", type=float, required=True)
p = add("grade", c_grade); p.add_argument("--preset", choices=sorted(GRADES))
for k in ("brightness", "contrast", "saturation", "gamma", "warmth"): p.add_argument(f"--{k}", type=float)
p.add_argument("--lut")
p = add("looks", c_looks); p.add_argument("--at", type=float)
p = add("cinematic", c_cinematic); p.add_argument("--bars", type=float, default=2.39); p.add_argument("--grain", type=int, default=7); p.add_argument("--vignette", action="store_true")
add("stabilize", c_stabilize)
p = add("denoise", c_denoise); p.add_argument("--strength", type=float, default=4)
p = add("sharpen", c_sharpen); p.add_argument("--amount", type=float, default=0.8)
p = add("zoom", c_zoom); p.add_argument("--to", type=float, default=1.15); p.add_argument("--mode", choices=["in", "out"], default="in")
p.add_argument("--start", type=float, default=0); p.add_argument("--end", type=float)
p = add("fade", c_fade); p.add_argument("--in", dest="fin", type=float, default=0.5); p.add_argument("--out", dest="fout", type=float, default=0.8)
p = add("text", c_text); p.add_argument("--text", required=True); p.add_argument("--start", type=float, default=0); p.add_argument("--end", type=float)
p.add_argument("--pos", choices=["top", "center", "bottom"], default="top"); p.add_argument("--size", type=int, default=80); p.add_argument("--color", default="#FFFFFF")
p.add_argument("--box", action="store_true"); p.add_argument("--upper", action="store_true")
p = add("logo", c_logo); p.add_argument("--image", required=True); p.add_argument("--pos", choices=["tr", "tl", "br", "bl"], default="tr")
p.add_argument("--scale", type=float, default=0.18); p.add_argument("--opacity", type=float, default=0.9)
p = add("broll", c_broll); p.add_argument("--clip", required=True); p.add_argument("--at", type=float, required=True); p.add_argument("--dur", type=float)
p = add("music", c_music); p.add_argument("--music", required=True); p.add_argument("--volume", type=float, default=0.18); p.add_argument("--no-duck", action="store_true")
p = add("audio", c_audio); p.add_argument("--replace"); p.add_argument("--add"); p.add_argument("--volume", type=float, default=1.0)
p.add_argument("--mute", action="store_true"); p.add_argument("--gain", type=float, default=0)
p = add("subs", c_subs); p.add_argument("--srt", required=True); p.add_argument("--size", type=int, default=60); p.add_argument("--color", default="#FFFFFF")
p.add_argument("--y", type=float, default=0.78); p.add_argument("--box", action="store_true"); p.add_argument("--upper", action="store_true")
p = add("export", c_export); p.add_argument("--preset", choices=sorted(EXPORTS), default="reel")
p = add("frame", c_frame); p.add_argument("--at", type=float, default=0)
add("fns", c_fns, io=False)

if __name__ == "__main__":
    a = ap.parse_args(); a.f(a)
