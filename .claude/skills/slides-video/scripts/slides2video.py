"""Presentation → cinematic video: slides with Ken Burns motion, animated text, transitions, color grade, film grain,
voice-over (uz / ru / en), music and subtitles. Free: ffmpeg + Pillow (+ edge-tts for the voice).

usage:
  python3 slides2video.py <slides.json> <out.mp4>
  python3 slides2video.py --pdf deck.pdf  <out.mp4> [--size 1080x1920] [--seconds 4]    a ready PDF deck
  python3 slides2video.py --pptx deck.pptx <out.mp4> [...]                              PowerPoint (needs LibreOffice)
  python3 slides2video.py --images folder/ <out.mp4> [...]                              photos → slideshow

slides.json:
{
  "size": "1080x1920", "fps": 30,
  "theme": {"bg": "#0E0E12", "bg2": "#2A2216", "accent": "#C9A86A", "text": "#FFFFFF", "grade": "luxury", "grain": 6, "bars": false},
  "voice": {"lang": "uz", "gender": "male", "rate": "+0%"},          # or null for no voice-over
  "music": "inbox/music/calm.mp3",                                    # or "auto" (generated ambient pad) or null
  "music_volume": 0.16, "subtitles": true, "transition": "fade", "transition_dur": 0.7,
  "slides": [
    {"layout": "title",   "title": "Shoxsaroy Towers", "subtitle": "Premium turar-joy", "image": "inbox/biz/shoxsaroy/1.jpg", "say": "…"},
    {"layout": "bullets", "title": "Atrofda", "bullets": ["2 ta metro", "10 ta bog'cha", "3 ta park"], "say": "…"},
    {"layout": "number",  "number": "20%", "caption": "boshlang'ich to'lov", "say": "…"},
    {"layout": "image",   "image": "…", "caption": "…"},
    {"layout": "quote",   "text": "…", "author": "…"},
    {"layout": "cta",     "title": "Uyingizni band qiling", "subtitle": "Direct'ga yozing", "button": "DM → NARX"}
  ]
}
Per slide optional: "duration" (s; default 3.5, longer when the voice line is longer), "motion" (in | out | left | right | none),
"transition" (to the next slide). Prints one JSON line.
"""
import argparse, glob, json, math, os, re, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageOps
HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(SK, "edit", "scripts")); sys.path.insert(0, os.path.join(SK, "reel", "scripts"))
import vtool  # noqa: E402
from media import FFMPEG, norm_text, probe, report, run  # noqa: E402

VOICE = os.path.join(SK, "voice", "scripts", "voice.py")
PY = sys.executable or "python3"


def rgb(h, a=255):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


# ---------------- drawing ----------------

def background(sl, th, W, H):
    """The moving layer: a photo (cover-cropped, darkened for text) or a soft gradient with a glow."""
    img = sl.get("image")
    if img and os.path.isfile(img) and sl.get("fit"):          # a deck page: whole page visible, blurred copy behind
        src = Image.open(img).convert("RGB")
        im = ImageOps.fit(src, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40)).point(lambda v: int(v * 0.55))
        fg = ImageOps.contain(src, (int(W * 0.94), int(H * 0.94)), Image.LANCZOS); im.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
        return im
    if img and os.path.isfile(img):
        im = ImageOps.fit(Image.open(img).convert("RGB"), (W, H), Image.LANCZOS)
        if sl.get("layout") != "image" or sl.get("caption"):
            shade = Image.new("L", (1, H))
            for y in range(H):                       # darker at the bottom and the top, where the text sits
                f = y / H; shade.putpixel((0, y), int(255 * (0.55 * max(0, f - 0.35) / 0.65 + 0.35 * max(0, 0.25 - f) / 0.25 + 0.18)))
            dark = Image.new("RGB", (W, H), (0, 0, 0)); im = Image.composite(dark, im, shade.resize((W, H)))
        return im
    a, b, acc = rgb(th["bg"])[:3], rgb(th.get("bg2", th["bg"]))[:3], rgb(th["accent"])[:3]
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        f = y / max(1, H - 1); grad.putpixel((0, y), tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3)))
    im = grad.resize((W, H))
    glow = Image.new("L", (W, H), 0); g = ImageDraw.Draw(glow); r = int(min(W, H) * 0.55)
    cx, cy = (int(W * 0.78), int(H * 0.22)) if hash(sl.get("title", "")) % 2 else (int(W * 0.2), int(H * 0.78))
    g.ellipse((cx - r, cy - r, cx + r, cy + r), fill=70); glow = glow.filter(ImageFilter.GaussianBlur(r * 0.45))
    im = Image.composite(Image.new("RGB", (W, H), acc), im, glow)
    return im


def draw_lines(d, lines, fnt, x0, y, W, color, align, lh):
    for ln in lines:
        w = fnt.getlength(ln); x = (W - w) / 2 if align == "center" else x0
        d.text((x + 3, y + 4), ln, font=fnt, fill=(0, 0, 0, 120)); d.text((x, y), ln, font=fnt, fill=color); y += lh
    return y


def text_layer(sl, th, W, H):
    """The text, on its own transparent layer, so it can fade and rise over the moving picture."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    u = min(W, H) / 1080; M = int(80 * u); maxw = W - 2 * M
    col, acc = rgb(th["text"]), rgb(th["accent"]); lay = sl.get("layout", "title")
    T = lambda s: norm_text(str(s or ""))
    if lay == "number":
        f1 = vtool.font(int(300 * u), 850); f2 = vtool.font(int(64 * u), 600)
        num = T(sl.get("number")); w = f1.getlength(num); y = H * 0.36
        d.text(((W - w) / 2, y), num, font=f1, fill=acc)
        draw_lines(d, vtool.wrap(T(sl.get("caption")), f2, maxw), f2, M, y + 330 * u, W, col, "center", int(78 * u))
    elif lay == "bullets":
        f1 = vtool.font(int(92 * u), 820); f2 = vtool.font(int(60 * u), 560); y = H * 0.22
        y = draw_lines(d, vtool.wrap(T(sl.get("title")), f1, maxw), f1, M, y, W, col, "left", int(104 * u)) + 40 * u
        d.rectangle((M, y, M + 120 * u, y + 8 * u), fill=acc); y += 70 * u
        for b in sl.get("bullets", []):
            d.ellipse((M, y + 24 * u, M + 22 * u, y + 46 * u), fill=acc)
            y = draw_lines(d, vtool.wrap(T(b), f2, maxw - 50 * u), f2, M + 50 * u, y, W, col, "left", int(74 * u)) + 26 * u
    elif lay == "quote":
        f0 = vtool.font(int(220 * u), 800); f1 = vtool.font(int(70 * u), 560); f2 = vtool.font(int(46 * u), 500)
        d.text((M, H * 0.24), "“", font=f0, fill=acc)
        y = draw_lines(d, vtool.wrap(T(sl.get("text")), f1, maxw), f1, M, H * 0.36, W, col, "left", int(88 * u)) + 40 * u
        draw_lines(d, ["— " + T(sl.get("author"))] if sl.get("author") else [], f2, M, y, W, acc, "left", int(60 * u))
    elif lay == "image":
        if sl.get("caption"):
            f2 = vtool.font(int(62 * u), 650)
            draw_lines(d, vtool.wrap(T(sl.get("caption")), f2, maxw), f2, M, H * 0.80, W, col, "center", int(76 * u))
    elif lay == "cta":
        f1 = vtool.font(int(100 * u), 840); f2 = vtool.font(int(56 * u), 520); f3 = vtool.font(int(58 * u), 760)
        y = draw_lines(d, vtool.wrap(T(sl.get("title")), f1, maxw), f1, M, H * 0.34, W, col, "center", int(112 * u)) + 30 * u
        y = draw_lines(d, vtool.wrap(T(sl.get("subtitle")), f2, maxw), f2, M, y, W, col, "center", int(70 * u)) + 70 * u
        if sl.get("button"):
            bt = T(sl["button"]); bw = f3.getlength(bt) + 120 * u; bx = (W - bw) / 2
            d.rounded_rectangle((bx, y, bx + bw, y + 120 * u), radius=int(60 * u), fill=acc)
            d.text((bx + 60 * u, y + 28 * u), bt, font=f3, fill=rgb(th["bg"]))
    else:   # title
        f1 = vtool.font(int(118 * u), 850); f2 = vtool.font(int(58 * u), 520)
        lines = vtool.wrap(T(sl.get("title")), f1, maxw); y = H * (0.62 if H > W else 0.52)
        y = draw_lines(d, lines, f1, M, y, W, col, "left", int(128 * u)) + 20 * u
        d.rectangle((M, y, M + 140 * u, y + 9 * u), fill=acc); y += 50 * u
        draw_lines(d, vtool.wrap(T(sl.get("subtitle")), f2, maxw), f2, M, y, W, col, "left", int(72 * u))
    return im


# ---------------- motion ----------------

MOTIONS = ["in", "right", "out", "left"]


def slide_clip(bg_png, txt_png, dur, motion, W, H, fps, out):
    n = max(2, int(round(dur * fps))); Z = 1.12
    if motion == "in": z, x, y = f"1+{Z - 1}*on/{n}", "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"
    elif motion == "out": z, x, y = f"{Z}-{Z - 1}*on/{n}", "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"
    elif motion == "left": z, x, y = f"{Z}", f"(iw-iw/zoom)*(1-on/{n})", "ih/2-ih/zoom/2"
    elif motion == "right": z, x, y = f"{Z}", f"(iw-iw/zoom)*on/{n}", "ih/2-ih/zoom/2"
    else: z, x, y = "1", "0", "0"
    parts = [f"[0:v]scale={W * 2}:{H * 2},zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={fps},setsar=1[b]",
             f"[1:v]format=rgba,fade=t=in:st=0.25:d=0.7:alpha=1[t]",
             f"[b][t]overlay=0:'max(0,(1.0-t)*{int(70 * min(W, H) / 1080)})':shortest=1,format=yuv420p[v]"]
    vtool.graph(["-i", bg_png, "-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", txt_png], parts, ["[v]"], out, crf=17)


def ambient(out, seconds):
    """A free, generated ambient pad (A minor), when there is no music file."""
    expr = "+".join(f"{a}*sin(2*PI*{f}*t)*(0.6+0.4*sin(2*PI*{m}*t))" for a, f, m in
                    [(0.10, 110, 0.07), (0.07, 164.81, 0.05), (0.06, 220, 0.09), (0.05, 261.63, 0.06), (0.03, 329.63, 0.11)])
    run(["-f", "lavfi", "-i", f"aevalsrc='{expr}|{expr}':s=48000:d={seconds + 2:.1f}",
         "-af", "lowpass=f=1400,aecho=0.8:0.6:120|240:0.3|0.2,afade=t=in:d=2,volume=1.6", "-c:a", "libmp3lame", "-q:a", "4", out])


# ---------------- inputs ----------------

def slides_from_images(paths, seconds):
    return [{"layout": "image", "image": p, "duration": seconds, "motion": MOTIONS[i % 4]} for i, p in enumerate(paths)]


def pdf_pages(pdf, d):
    if shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-r", "150", "-png", pdf, os.path.join(d, "p")], check=True)
        return sorted(glob.glob(os.path.join(d, "p*.png")))
    try:
        import fitz
        doc = fitz.open(pdf); out = []
        for i, pg in enumerate(doc):
            p = os.path.join(d, f"p{i:03d}.png"); pg.get_pixmap(dpi=150).save(p); out.append(p)
        return out
    except ImportError:
        raise SystemExit(json.dumps({"tool": "slides2video", "error": "need pdftoppm (poppler) or PyMuPDF to read a PDF"}))


def pptx_to_pdf(pptx, d):
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        raise SystemExit(json.dumps({"tool": "slides2video", "error": "PowerPoint needs LibreOffice; or export the deck to PDF and use --pdf"}))
    subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", d, pptx], check=True, capture_output=True)
    return os.path.join(d, os.path.splitext(os.path.basename(pptx))[0] + ".pdf")


# ---------------- main ----------------

def build(spec, out, work):
    W, H = (int(x) for x in spec.get("size", "1080x1920").split("x")); fps = int(spec.get("fps", 30))
    th = {"bg": "#0E0E12", "bg2": "#24201A", "accent": "#C9A86A", "text": "#FFFFFF", "grade": "luxury", "grain": 6, "bars": False}
    th.update(spec.get("theme") or {})
    slides = spec["slides"]; td = float(spec.get("transition_dur", 0.7)); voice = spec.get("voice")
    # 1) voice lines first: they decide how long each slide stays
    vfiles, vlen, notes = [], [], []
    for i, sl in enumerate(slides):
        vf, L = None, 0.0
        if voice and sl.get("say"):
            vf = os.path.join(work, f"v{i:02d}.mp3")
            p = subprocess.run([PY, VOICE, "tts", sl["say"], vf, "--lang", voice.get("lang", "uz"), "--gender", voice.get("gender", "male"),
                                "--rate", voice.get("rate", "+0%")], capture_output=True, text=True)
            try: res = json.loads(p.stdout.strip().splitlines()[-1])
            except Exception: res = {"error": p.stderr[-200:]}
            if res.get("error") or not os.path.isfile(vf):
                notes.append(f"slide {i + 1}: no voice ({res.get('error', '')[:80]})"); vf = None
            else:
                L = probe(vf)["duration"]
        vfiles.append(vf); vlen.append(L)
    durs = [max(float(sl.get("duration", 3.5)), L + 0.9 + (td if 0 < i < len(slides) - 1 else 0)) for i, (sl, L) in enumerate(zip(slides, vlen))]
    # 2) each slide: background + text layer → a moving clip
    clips = []
    for i, sl in enumerate(slides):
        bgp, txp, cp = (os.path.join(work, f"{k}{i:02d}.png") for k in ("bg", "tx", "c"))
        background(sl, th, W, H).save(bgp); text_layer(sl, th, W, H).save(txp)
        cp = os.path.join(work, f"c{i:02d}.mp4")
        slide_clip(bgp, txp, durs[i], sl.get("motion") or MOTIONS[i % 4], W, H, fps, cp); clips.append(cp)
    # 3) join with transitions
    joined = os.path.join(work, "joined.mp4")
    vtool.c_concat(argparse.Namespace(out=joined, files=clips, transition=spec.get("transition", "fade"), dur=td,
                                      size=f"{W}x{H}", fps=fps, mode="crop"))
    starts, t = [], 0.0
    for i, dd in enumerate(durs):
        starts.append(t); t += dd - td
    total = probe(joined)["duration"]
    # 4) look: grade, grain, vignette, optional bars
    graded = os.path.join(work, "graded.mp4")
    f = [vtool.GRADES.get(th["grade"], "null")] if th.get("grade") else []
    if th.get("grain"): f.append(f"noise=alls={int(th['grain'])}:allf=t")
    if th.get("bars"):
        bh = int(H * 0.06) if H > W else max(0, int((H - W / 2.39) / 2))
        f.append(f"drawbox=0:0:iw:{bh}:black:t=fill,drawbox=0:ih-{bh}:iw:{bh}:black:t=fill")
    f.append("fade=t=in:st=0:d=0.6"); f.append(f"fade=t=out:st={total - 0.8:.3f}:d=0.8")
    vtool.simple(joined, graded, vf=",".join(f), af=None)
    cur = graded
    # 5) voice track: each line starts a moment after its slide begins
    vo = [(starts[i] + 0.35, vf) for i, vf in enumerate(vfiles) if vf]
    if vo:
        inputs, parts = ["-i", cur], []
        for k, (st, vf) in enumerate(vo):
            inputs += ["-i", vf]; ms = int(st * 1000)
            parts.append(f"[{k + 1}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms}[d{k}]")
        parts.append("".join(f"[d{k}]" for k in range(len(vo))) + f"amix=inputs={len(vo)}:normalize=0,apad,atrim=0:{total:.3f}[a]")
        parts.append("[0:v]null[v]")
        nxt = os.path.join(work, "voiced.mp4"); vtool.graph(inputs, parts, ["[v]", "[a]"], nxt); cur = nxt
    # 6) music under it (ducked under the voice)
    mus = spec.get("music")
    if mus == "auto":
        mus = os.path.join(work, "ambient.mp3"); ambient(mus, total)
    if mus and os.path.isfile(mus):
        nxt = os.path.join(work, "music.mp4")
        vtool.c_music(argparse.Namespace(src=cur, out=nxt, music=mus, volume=float(spec.get("music_volume", 0.16)), no_duck=not vo)); cur = nxt
    elif mus:
        notes.append(f"music file not found: {mus}")
    # 7) subtitles from the voice lines
    if spec.get("subtitles", True) and vo:
        items = []
        for i, sl in enumerate(slides):
            if not vfiles[i]: continue
            words = norm_text(sl["say"]).split(); chunks = [" ".join(words[k:k + 5]) for k in range(0, len(words), 5)]
            tot = sum(len(c) for c in chunks) or 1; t0 = starts[i] + 0.35
            for c in chunks:
                l = vlen[i] * len(c) / tot; items.append((t0, t0 + l, c)); t0 += l
        with tempfile.TemporaryDirectory() as d:
            pngs = []
            for k, (s, e, c) in enumerate(items):
                p = os.path.join(d, f"s{k:04d}.png"); vtool.text_png(c, W, H, int(54 * min(W, H) / 1080), "#FFFFFF", 0.90 if H > W else 0.88, True, False, p, 650)
                pngs.append((s, e, p))
            nxt = os.path.join(work, "subs.mp4"); vtool.overlay_timeline(cur, nxt, pngs, W, H); cur = nxt
    vtool.mkdir_for(out); shutil.copyfile(cur, out)
    return {"seconds": round(probe(out)["duration"], 2), "slides": len(slides), "voice": bool(vo), "music": bool(mus and os.path.isfile(mus)), "notes": notes}


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("spec", nargs="?"); ap.add_argument("out")
ap.add_argument("--pdf"); ap.add_argument("--pptx"); ap.add_argument("--images")
ap.add_argument("--size", default="1080x1920"); ap.add_argument("--seconds", type=float, default=4.0)
ap.add_argument("--music"); ap.add_argument("--grade", default="luxury")

if __name__ == "__main__":
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as work:
        if a.spec and not (a.pdf or a.pptx or a.images):
            spec = json.load(open(a.spec, encoding="utf-8"))
            base = os.path.dirname(os.path.abspath(a.spec))
            for sl in spec["slides"]:                     # image paths may be relative to the project or to slides.json
                if sl.get("image") and not os.path.isfile(sl["image"]) and os.path.isfile(os.path.join(base, sl["image"])):
                    sl["image"] = os.path.join(base, sl["image"])
        else:
            if a.pptx: a.pdf = pptx_to_pdf(a.pptx, work)
            if a.pdf: imgs = pdf_pages(a.pdf, work)
            else: imgs = sorted(p for p in glob.glob(os.path.join(a.images, "*")) if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
            spec = {"size": a.size, "theme": {"grade": a.grade, "grain": 5}, "music": a.music, "voice": None, "slides": slides_from_images(imgs, a.seconds)}
            if a.pdf:                                    # a deck page must stay readable: no crop, gentle motion
                for sl in spec["slides"]: sl["motion"] = "in"; sl["fit"] = True
        res = build(spec, a.out, work)
    report(tool="slides2video", out=a.out, **res)
