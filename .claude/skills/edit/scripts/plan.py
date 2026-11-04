"""Run a montaj plan: the director (rejissor) writes the order of work, this runs it step by step.

usage:
  python3 plan.py fns                         every function a step can use, with its agent
  python3 plan.py check  out/<name>/plan.json
  python3 plan.py run    out/<name>/plan.json [--from N] [--to N]
  python3 plan.py done   out/<name>/plan.json N [--out <file the agent made>]
  python3 plan.py status out/<name>/plan.json

plan.json:
{
  "name": "shoxsaroy-01",                 # output folder: out/<name>/
  "src": "inbox/clip.mp4",                # the raw video (or a slides spec for slides.video)
  "client": "shoxsaroy",
  "goal": "45 s Reel, luxury look, Uzbek + Russian subtitles",
  "steps": [
    {"agent": "ovozchi",    "fn": "voice.transcript"},
    {"agent": "montaj",     "fn": "reel.cut",       "args": {"max": 45}},
    {"agent": "montaj",     "fn": "vtool.grade",    "args": {"preset": "luxury"}},
    {"agent": "subtitrchi", "fn": "reel.captions",  "args": {"color": "#FFD400", "size": 56}},
    {"agent": "subtitrchi", "fn": "task", "task": "Translate captions.srt to Russian, keep timings", "makes": "captions.ru.srt"},
    {"agent": "montaj",     "fn": "vtool.export",   "args": {"preset": "reel"}}
  ]
}
Each video step works on the previous step's video. "in": "@src" or "@3" (step 3's output) picks another input.
Args become flags (--key value); in values, "@src", "@3" and "@dir" (= out/<name>) are replaced with paths.
A "task" step stops the run: the named agent does it by hand, then `plan.py done <plan> N`, then `run` again.
"""
import argparse, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.abspath(os.path.join(HERE, "..", ".."))                         # .claude/skills
PY = sys.executable or "python3"
VT = os.path.join(SK, "edit", "scripts", "vtool.py")
VO = os.path.join(SK, "voice", "scripts", "voice.py")

# fn: (agent, script, sub-command, kind)  kind: video = makes the next video | file = makes a side file | dir = a folder
FNS = {
    "voice.detect":     ("ovozchi", VO, "detect", "file"),
    "voice.transcript": ("ovozchi", VO, "transcript", "dir"),
    "voice.clean":      ("ovozchi", VO, "clean", "video"),
    "voice.textcut":    ("ovozchi", VO, "textcut", "video"),
    "voice.cutwords":   ("ovozchi", VO, "cutwords", "video"),
    "voice.tts":        ("ovozchi", VO, "tts", "file"),
    "reel.cut":         ("montaj", os.path.join(SK, "reel", "scripts", "cut.py"), None, "video"),
    "reel.captions":    ("subtitrchi", os.path.join(SK, "reel", "scripts", "captions.py"), None, "video"),
    "reel.frames":      ("montaj", os.path.join(SK, "reel", "scripts", "frames.py"), None, "file"),
    "pixel.cover":      ("montaj", os.path.join(SK, "pixel", "scripts", "thumbnail.py"), None, "file"),
    "slides.video":     ("taqdimotchi", os.path.join(SK, "slides-video", "scripts", "slides2video.py"), None, "video"),
    "task":             (None, None, None, "task"),
}
for c in ("trim", "cut", "vertical", "speed", "grade", "cinematic", "stabilize", "denoise", "sharpen", "zoom", "fade",
          "text", "logo", "broll", "music", "audio", "export"):
    FNS[f"vtool.{c}"] = ("subtitrchi" if c == "text" else "montaj", VT, c, "video")
FNS["vtool.subs"] = ("subtitrchi", VT, "subs", "video")
FNS["vtool.concat"] = ("montaj", VT, "concat", "concat")
FNS["vtool.split"] = ("montaj", VT, "split", "dir")
FNS["vtool.looks"] = ("montaj", VT, "looks", "file")
FNS["vtool.frame"] = ("montaj", VT, "frame", "file")
EXT = {"voice.detect": "json", "voice.tts": "mp3", "vtool.looks": "jpg", "vtool.frame": "jpg", "reel.frames": "jpg", "pixel.cover": "jpg"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def state_path(plan_path):
    return os.path.join(os.path.dirname(plan_path), "plan.state.json")


def load_state(plan_path):
    p = state_path(plan_path)
    return load(p) if os.path.isfile(p) else {"done": [], "outputs": {}, "video": None}


def save_state(plan_path, st):
    with open(state_path(plan_path), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def out_dir(plan, plan_path):
    return os.path.join("out", plan["name"]) if plan.get("name") else os.path.dirname(plan_path)


def resolve(v, plan, st, d):
    if isinstance(v, dict):
        return {k: resolve(x, plan, st, d) for k, x in v.items()}
    if isinstance(v, list):
        return [resolve(x, plan, st, d) for x in v]
    if not isinstance(v, str):
        return v
    v = v.replace("@src", plan.get("src", "")).replace("@dir", d)
    return re.sub(r"@(\d+)", lambda m: st["outputs"].get(m.group(1), m.group(0)), v)


def flags(args):
    out = []
    for k, v in (args or {}).items():
        key = "--" + k.replace("_", "-")
        if v is True: out.append(key)
        elif v is False or v is None: continue
        elif isinstance(v, list):
            for x in v: out += [key, str(x)]
        else: out += [key, str(v)]
    return out


def check(plan):
    errs = []
    if not plan.get("steps"): errs.append("no steps")
    for i, s in enumerate(plan.get("steps", []), 1):
        fn = s.get("fn")
        if fn not in FNS: errs.append(f"step {i}: unknown fn {fn!r}")
        elif fn == "task" and not s.get("task"): errs.append(f"step {i}: a task step needs \"task\" (what to do)")
        if not s.get("agent"): errs.append(f"step {i}: no agent named")
    if plan.get("src") and not os.path.exists(plan["src"]) and not plan.get("steps", [{}])[0].get("fn") == "slides.video":
        errs.append(f"src not found: {plan['src']}")
    return errs


def run_step(n, s, plan, st, d):
    fn = s["fn"]; agent, script, sub, kind = FNS[fn]
    args = resolve(dict(s.get("args") or {}), plan, st, d)
    inp = resolve(s.get("in"), plan, st, d) if s.get("in") else (st.get("video") or plan.get("src"))
    tag = f"{n:02d}-{fn.split('.')[-1]}"
    cmd = [PY, script] + ([sub] if sub else [])
    if kind == "video":
        out = os.path.join(d, tag + ".mp4")
        if fn == "slides.video": cmd += [inp, out]
        elif fn in ("voice.textcut",): cmd += [inp, args.pop("words"), args.pop("edited"), out]
        elif fn == "voice.cutwords": cmd += [inp, args.pop("words"), out]
        else: cmd += [inp, out]
        if fn == "reel.captions" and "srt" not in args: args["srt"] = os.path.join(d, "captions.srt")
    elif kind == "file":
        out = args.pop("out", None) or os.path.join(d, tag + "." + EXT.get(fn, "out"))
        if fn == "voice.detect": cmd += [inp, "--out", out]
        elif fn == "voice.tts": cmd += [args.pop("text"), out]
        else: cmd += [inp, out]
    elif kind == "dir":
        out = os.path.join(d, "transcript" if fn == "voice.transcript" else tag)
        cmd += [inp, out]
    elif kind == "concat":
        out = os.path.join(d, tag + ".mp4"); cmd += [out] + resolve(args.pop("files"), plan, st, d)
    cmd += flags(args)
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    last = (p.stdout.strip().splitlines() or [""])[-1]
    try: res = json.loads(last)
    except Exception: res = {"raw": last[-300:]}
    ok = p.returncode == 0 and "error" not in res and (os.path.exists(out) if kind != "concat" else os.path.exists(out))
    rec = {"step": n, "agent": s.get("agent") or agent, "fn": fn, "ok": ok, "seconds": round(time.time() - t0, 1), "out": out, "result": res}
    if not ok: rec["error"] = (res.get("error") or p.stderr.strip()[-600:] or "no output")
    with open(os.path.join(d, "plan.log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return ok, out, kind, rec


def c_run(a):
    plan = load(a.plan); errs = check(plan)
    if errs: print(json.dumps({"tool": "plan.run", "ok": False, "errors": errs}, ensure_ascii=False)); sys.exit(1)
    d = out_dir(plan, a.plan); os.makedirs(d, exist_ok=True); st = load_state(a.plan)
    steps = plan["steps"]; first = a.from_ or next((i for i in range(1, len(steps) + 1) if i not in st["done"]), len(steps) + 1); last = a.to or len(steps)
    done_now = []
    for n in range(first, last + 1):
        s = steps[n - 1]
        if n in st["done"] and not a.from_:
            continue
        if s["fn"] == "task":
            save_state(a.plan, st)
            print(json.dumps({"tool": "plan.run", "paused_at": n, "agent": s["agent"], "task": s["task"], "makes": s.get("makes"),
                              "video_so_far": st.get("video"), "done_now": done_now,
                              "next": f"after the task: python3 .claude/skills/edit/scripts/plan.py done {a.plan} {n} --out <file>, then run again"},
                             ensure_ascii=False)); return
        ok, out, kind, rec = run_step(n, s, plan, st, d)
        if not ok:
            save_state(a.plan, st)
            print(json.dumps({"tool": "plan.run", "failed_at": n, "agent": rec["agent"], "fn": s["fn"], "error": rec["error"], "done_now": done_now},
                             ensure_ascii=False)); sys.exit(1)
        st["outputs"][str(n)] = out; st["done"].append(n)
        if kind in ("video", "concat"): st["video"] = out
        done_now.append({"step": n, "agent": rec["agent"], "fn": s["fn"], "out": out, "seconds": rec["seconds"]})
        save_state(a.plan, st)
    final = None
    if st.get("video") and last == len(steps):
        final = os.path.join(d, "final.mp4"); shutil.copyfile(st["video"], final)
    print(json.dumps({"tool": "plan.run", "ok": True, "done_now": done_now, "final": final}, ensure_ascii=False))


def c_done(a):
    plan = load(a.plan); st = load_state(a.plan); n = a.n
    if a.out:
        st["outputs"][str(n)] = a.out
        if a.out.lower().endswith((".mp4", ".mov", ".mkv")): st["video"] = a.out
    if n not in st["done"]: st["done"].append(n)
    save_state(a.plan, st); print(json.dumps({"tool": "plan.done", "step": n, "out": a.out}, ensure_ascii=False))


def c_status(a):
    plan = load(a.plan); st = load_state(a.plan)
    rows = [{"step": i, "agent": s.get("agent"), "fn": s["fn"], "done": i in st["done"], "out": st["outputs"].get(str(i))}
            for i, s in enumerate(plan["steps"], 1)]
    print(json.dumps({"tool": "plan.status", "steps": rows, "video": st.get("video")}, ensure_ascii=False))


def c_check(a):
    errs = check(load(a.plan)); print(json.dumps({"tool": "plan.check", "ok": not errs, "errors": errs}, ensure_ascii=False))


def c_fns(a):
    by = {}
    for fn, (agent, _, _, kind) in FNS.items():
        by.setdefault(agent or "any agent", []).append(fn)
    print(json.dumps({"tool": "plan.fns", "by_agent": by,
                      "help": "args of each fn: python3 .claude/skills/edit/scripts/vtool.py <cmd> -h, voice.py <cmd> -h"}, ensure_ascii=False))


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sp = ap.add_subparsers(dest="cmd", required=True)
p = sp.add_parser("run"); p.add_argument("plan"); p.add_argument("--from", dest="from_", type=int); p.add_argument("--to", type=int); p.set_defaults(f=c_run)
p = sp.add_parser("done"); p.add_argument("plan"); p.add_argument("n", type=int); p.add_argument("--out"); p.set_defaults(f=c_done)
p = sp.add_parser("status"); p.add_argument("plan"); p.set_defaults(f=c_status)
p = sp.add_parser("check"); p.add_argument("plan"); p.set_defaults(f=c_check)
p = sp.add_parser("fns"); p.set_defaults(f=c_fns)

if __name__ == "__main__":
    a = ap.parse_args(); a.f(a)
