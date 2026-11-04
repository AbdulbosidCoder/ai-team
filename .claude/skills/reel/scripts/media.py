"""Small ffmpeg helpers shared by the tools. Only needs ffmpeg on PATH (set FFMPEG to use another binary)."""
import json, os, re, subprocess, sys
import numpy as np

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def run(args, **kw):
    """Run ffmpeg quietly; raise with its stderr if it fails."""
    p = subprocess.run([FFMPEG, "-hide_banner", "-y"] + args, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-2000:])
    return p


def probe(path):
    """Duration (s), width, height and fps of a video, read from ffmpeg's own banner."""
    err = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    v = re.search(r"Video: .*?(\d{2,5})x(\d{2,5})", err)
    f = re.search(r"([\d.]+) fps", err)
    if not d:
        raise RuntimeError(f"cannot read {path}")
    dur = int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3])
    return {"duration": dur, "width": int(v[1]) if v else 0, "height": int(v[2]) if v else 0, "fps": float(f[1]) if f else 30.0}


def audio(path, sr=16000):
    """Mono float32 audio samples of a media file."""
    raw = subprocess.run([FFMPEG, "-hide_banner", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def speech_segments(path, noise_db=-32, min_silence=0.45):
    """[(start, end)] of the non-silent parts, from ffmpeg's silencedetect."""
    err = run(["-i", path, "-vn", "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"]).stderr
    dur = probe(path)["duration"]
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    segs, t = [], 0.0
    for s, e in zip(starts, ends + [dur] * (len(starts) - len(ends))):
        if s > t + 0.05:
            segs.append((t, s))
        t = e
    if t < dur - 0.05:
        segs.append((t, dur))
    return segs


def report(**kw):
    """One JSON line on stdout, so the agent can read the result."""
    print(json.dumps(kw, ensure_ascii=False))
    sys.stdout.flush()


FILLERS = {"um", "uh", "erm", "er", "hmm", "ah", "uhm", "mm",
           "e", "ee", "eee", "eeee", "a", "aa", "aaa", "mmm", "xmm", "hm",          # o'zbekcha
           "э", "ээ", "эээ", "м", "мм", "ммм", "хм", "а", "аа", "ааа"}             # русский


def lang():
    """Speech language: WHISPER_LANG uz | ru | en, or auto (default) for Uzbek and Russian, even mixed in one clip."""
    v = os.environ.get("WHISPER_LANG", "auto").strip().lower()
    return None if v in ("", "auto", "uz+ru", "ru+uz", "mixed") else v


def elevenlabs_key():
    """The ElevenLabs API key when the cloud engine should be used (STT_ENGINE auto or elevenlabs)."""
    if os.environ.get("STT_ENGINE", "auto").strip().lower() not in ("auto", "elevenlabs"):
        return None
    return os.environ.get("ELEVENLABS_API_KEY", "").strip() or None


def elevenlabs_words(path):
    """[(word, start, end)] from ElevenLabs Scribe: strong on Uzbek and Russian, handles both in one clip.
    Sends only the clip's audio (16 kHz mono wav)."""
    import tempfile, urllib.error, urllib.request, uuid
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav"); write_wav(wav, audio(path), 16000)
        data = open(wav, "rb").read()
    fields = {"model_id": os.environ.get("ELEVENLABS_STT_MODEL", "scribe_v2"), "timestamps_granularity": "word",
              "tag_audio_events": "false"}
    if lang():
        fields["language_code"] = lang()
    b = uuid.uuid4().hex
    body = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
    body += f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
    body += data + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request("https://api.elevenlabs.io/v1/speech-to-text", data=body, method="POST",
                                 headers={"xi-api-key": elevenlabs_key() or "", "Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            js = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ElevenLabs {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")
    return [(w["text"].strip(), float(w["start"]), float(w["end"])) for w in js.get("words", [])
            if w.get("type", "word") == "word" and w.get("text", "").strip()]


def whisper_cpp():
    """(binary, model) of a whisper.cpp install, or None. Used on Android/Termux, where faster-whisper and
    sherpa-onnx have no wheels. Set WHISPER_CPP_MODEL (a ggml-*.bin file) and optionally WHISPER_CPP (binary)."""
    import shutil
    model = os.path.expanduser(os.environ.get("WHISPER_CPP_MODEL", ""))
    binary = shutil.which(os.path.expanduser(os.environ.get("WHISPER_CPP", "whisper-cli")))
    return (binary, model) if model and os.path.isfile(model) and binary else None


def write_wav(path, pcm, sr=16000):
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())


def whisper_cpp_run(wav, extra, out_prefix=None):
    """Run whisper-cli on a 16 kHz wav; returns stdout (or the JSON it wrote when out_prefix is given)."""
    binary, model = whisper_cpp()
    args = [binary, "-m", model, "-f", wav, "-l", lang() or "auto", "-np",
            "-t", os.environ.get("WHISPER_THREADS", str(min(4, os.cpu_count() or 2)))] + extra
    if out_prefix:
        args += ["-oj", "-of", out_prefix]
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("whisper.cpp: " + p.stderr[-800:])
    if out_prefix:
        with open(out_prefix + ".json", encoding="utf-8") as f:
            return json.load(f)
    return p.stdout


class STT:
    """Speech-to-text: ElevenLabs Scribe when ELEVENLABS_API_KEY is set, else local: whisper.cpp when WHISPER_CPP_MODEL
    is set (Android), else faster-whisper, else sherpa-onnx. Local models are multilingual (Uzbek + Russian)."""
    def __init__(self):
        if elevenlabs_key():
            self.fw = None; self.rec = None; self.engine = "elevenlabs"
            return
        if whisper_cpp():
            self.fw = None; self.rec = None; self.engine = "whisper.cpp"
            return
        try:
            from faster_whisper import WhisperModel
            self.fw = WhisperModel(os.environ.get("WHISPER_MODEL", "medium"), compute_type="int8"); self.engine = "faster-whisper"
        except ImportError:
            import sherpa_onnx
            here = os.path.dirname(os.path.abspath(__file__))
            d = os.environ.get("WHISPER_ONNX_DIR", os.path.join(here, "models", "sherpa-onnx-whisper-small"))
            pre = os.path.join(d, os.path.basename(d).replace("sherpa-onnx-whisper-", "") + "-")
            self.rec = sherpa_onnx.OfflineRecognizer.from_whisper(encoder=pre + "encoder.int8.onnx", decoder=pre + "decoder.int8.onnx", tokens=pre + "tokens.txt",
                                                                  language=lang() or "", task="transcribe", num_threads=2)
            self.fw = None; self.engine = "sherpa-onnx whisper"

    def text(self, pcm, sr=16000):
        """Transcript of a short piece of audio."""
        if self.engine == "elevenlabs":
            import tempfile
            with tempfile.TemporaryDirectory() as d:
                wav = os.path.join(d, "a.wav"); write_wav(wav, pcm, sr)
                return " ".join(w for w, _, _ in elevenlabs_words(wav))
        if self.engine == "whisper.cpp":
            import tempfile
            with tempfile.TemporaryDirectory() as d:
                wav = os.path.join(d, "a.wav"); write_wav(wav, pcm, sr)
                return " ".join(whisper_cpp_run(wav, ["-nt"]).split())
        if self.fw is not None:
            segs, _ = self.fw.transcribe(pcm, language=lang())
            return " ".join(x.text.strip() for x in segs)
        st = self.rec.create_stream(); st.accept_waveform(sr, pcm); self.rec.decode_stream(st)
        return st.result.text.strip()


KEEP = {"okay", "ok", "yes", "yeah", "no", "so", "right", "wow", "hi", "hey", "go", "now",
        "ha", "yo'q", "mana", "endi", "xo'p", "bor", "yo", "va", "u", "bu", "да", "нет", "вот", "так", "и", "у", "в", "с"}


def only_fillers(text, seconds=None):
    """True for "um", "uh"... A lone sound shorter than 0.55 s that is not a real short word counts too:
    small models often write a stray "um" as "armed" or "1"."""
    words = [re.sub(r"[^\w']", "", w.lower()).strip("'_") for w in text.split()]
    words = [w for w in words if w]
    if seconds is not None and seconds < 0.55 and len(words) <= 1 and not (words and words[0] in KEEP):
        return True
    return bool(words) and all(w in FILLERS for w in words)
