"""Cloned and stock voices: pick a reference clip, test engines, speak a line, voice a script.

    ./pal voice prepare <speaker> <media> [--lang fa] [--from 12.5 --to 40]
    ./pal voice test <speaker> [--engines chatterbox-nano,moss-nano] [--langs en,fa]
    ./pal voice say <speaker> --lang en --text "Hello." -o out.wav      (speaker "stock": a stock voice)
    ./pal voice script <ep> [--lang en] [--speaker host]

prepare: from any recording, the best 6-10 s of clean continuous speech (steady level, few pauses,
  far above the noise floor, no clipping, starting and ending at a pause) -> voices/<speaker>/<lang>.wav
  (mono, levelled), <lang>.txt (its exact words, from ./pal transcribe) and voice.json.
test: 4 fixed lines per output language, from every reference clip the speaker has, with every
  installed engine -> voices/<speaker>/test/<outlang>-from-<reflang>-<engine>.mp3; prints speed
  (seconds of compute per second of speech), word errors when read back, and words per second.
say: one line, cached. script: reads <ep>/script.md, lines like
    L01 | host: Text to say.            (the "speaker:" part is optional)
    L02 | 1453 | say: fourteen fifty-three   (or a following line "say: ..."): spoken wording only
  A blank line starts a new paragraph. Each line is voiced (cached on text, voice settings and
  reference hash; fixed seed), laid out with 0.45 s lead-in, 0.25 s gaps (0.6 s between paragraphs)
  -> build/audio/voice.<lang>.wav (48 kHz mono) and transcript.json (timeline "edited", one
  segment per script line with its id in "line"; word times by reading each line back).
Engines run in .venv-voice (sh tools/setup.sh). Everything is deterministic: same text, voice and seed
give the same audio. Speaker "stock" uses a stock English voice (Kokoro); no clip needed.
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

SR = 24000            # sample rate of cached lines
OUT_SR = 48000        # sample rate of the files handed to the mixer
CODE_VERSION = 1
DEFAULT_ENGINE = {"en": "chatterbox-nano", "fa": "moss-nano"}   # used when voice.json names none that speaks the language
ENGINES = {           # name: (models.json key, worker script, languages, clones a voice from a clip)
    "chatterbox-nano": ("voice-chatterbox-nano", "chatterbox_worker.py", ["en"], True),
    "moss-nano": ("voice-moss-nano", "moss_worker.py", ["en", "fa"], True),
    "kokoro": ("voice-kokoro", "kokoro_worker.py", ["en"], False),
}
STOCK = {"name": "stock", "engine": "kokoro", "language": "en", "voice": "af_heart", "speed": 1.0, "seed": 1, "reference": {}}
TEST_LINES = {
    "en": ["In 1453 the city fell, and the map of Europe changed.",
           "A recursive function calls itself until it reaches the base case.",
           "The server returned error 404, so we checked the HTTP headers again.",
           "Nobody expected the experiment to take three hours, but it did."],
    "fa": ["سلام، به این ویدیو خوش آمدید.", "امروز می‌خواهیم درباره تاریخ شهرهای قدیمی صحبت کنیم.",
           "این برنامه هر بار خودش را دوباره صدا می‌زند تا به پایان برسد.", "لطفاً تا آخر ویدیو با ما بمانید."],
}


# ---------------------------------------------------------------- audio helpers
def level(y, target_db=-20.0):
    """Even loudness (RMS) with the peak under -1 dBFS."""
    y = y * (10 ** (target_db / 20) / (np.sqrt((y ** 2).mean()) + 1e-9))
    peak = np.abs(y).max()
    return (y * 0.89 / peak if peak > 0.89 else y).astype(np.float32)


def decode(path, sr=SR):
    """Any media file -> mono float32 array at `sr` (ffmpeg)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode or not r.stdout:
        C.die(f"ffmpeg could not read audio from {path}: {r.stderr.decode(errors='replace')[-200:]}")
    return np.frombuffer(r.stdout, dtype="<f4").copy()


def filter_audio(y, af, sr=SR):
    """Run an ffmpeg audio filter chain (e.g. atempo) over an array."""
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.wav"), os.path.join(d, "b.wav")
        sf.write(a, y, sr, subtype="FLOAT")
        C.run(["ffmpeg", "-i", a, "-af", af, "-c:a", "pcm_f32le", b])
        return sf.read(b, dtype="float32")[0]


def tempo(y, factor):
    """Speed a line up (factor > 1) or down without changing pitch."""
    return y if abs(factor - 1) < 1e-3 else filter_audio(y, f"atempo={factor:.4f}")


def frame_db(y, hop=0.01):
    h = int(SR * hop)
    n = len(y) // h
    return 20 * np.log10(np.sqrt((y[: n * h].reshape(n, h) ** 2).mean(axis=1)) + 1e-9)


def voiced_span(y, thresh_db=-40.0):
    """(start, end) in seconds of the voiced part of a line, so gaps are laid out by us."""
    v = np.where(frame_db(y) > thresh_db)[0]
    return (0.0, len(y) / SR) if len(v) == 0 else (max(0.0, v[0] * 0.01 - 0.03), min(len(y) / SR, (v[-1] + 1) * 0.01 + 0.06))


def trim(y):
    a, b = voiced_span(y)
    return y[int(a * SR): int(b * SR)]


# ---------------------------------------------------------------- words, errors, read-back
FOLD = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "‌": " ", "ً": None, "ٌ": None, "ٍ": None, "َ": None,
                      "ُ": None, "ِ": None, "ّ": None, "ْ": None, **{chr(0x6F0 + i): str(i) for i in range(10)}})


ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen").split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def spell(n):
    """English words for 0..999999999 (read-back comparison only: 'and' is left out)."""
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")
    for size, name in ((10 ** 6, "million"), (1000, "thousand"), (100, "hundred")):
        if n >= size:
            return spell(n // size) + " " + name + (" " + spell(n % size) if n % size else "")


def spell_year(n):
    """1453 -> fourteen fifty three; 1905 -> nineteen oh five; 2000 -> two thousand."""
    hi, lo = divmod(n, 100)
    if n % 1000 == 0 or hi % 10 == 0 and n > 2000 or n < 1100:
        return spell(n)
    return spell(hi) + " " + ("hundred" if lo == 0 else "oh " + ONES[lo] if lo < 10 else spell(lo))


def tokens(text, lang="en"):
    """Comparable words: lower case, punctuation out, digits spoken (1453 -> fourteen fifty three)."""
    text = text.lower().translate(FOLD).replace("-", " ").replace("’", "'")
    out = []
    for w in re.findall(r"\d+|[^\W\d_]+(?:'[^\W\d_]+)*", text):
        if w.isdigit() and lang == "en":
            n = int(w)
            out += spell_year(n).split() if 1100 <= n <= 2099 else spell(n).split()
        else:
            out.append(w)
    return out


def edit_distance(ref, hyp):
    d = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        p, d[0] = d[0], i
        for j in range(1, len(hyp) + 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (ref[i - 1] != hyp[j - 1]))
    return d[len(hyp)]


_asr = {}


def asr_words(y16, lang):
    """Whisper reads an audio array (16 kHz) back: [(word, start, end)]. Model loaded once."""
    import transcribe as T
    if "m" not in _asr:
        _asr["m"] = T.load_model(False, int(os.environ.get("VOICE_THREADS", "2")))
    segs, _ = _asr["m"].transcribe(y16, language=lang, beam_size=1, word_timestamps=True, condition_on_previous_text=False)
    return [(w.word.strip(), float(w.start), float(w.end)) for s in segs for w in (s.words or []) if w.word.strip()]


def read_back(path_or_array, lang):
    y = decode(path_or_array, 16000) if isinstance(path_or_array, str) else filter_audio(path_or_array, "aresample=16000")
    return asr_words(y.astype(np.float32), lang)


# ---------------------------------------------------------------- speakers and references
def speaker(name):
    """voices/<name>/voice.json with defaults filled in; "stock" is built in. Adds _dir."""
    if name == "stock":
        return dict(STOCK, _dir=None)
    d = os.path.join(C.ROOT, "voices", name)
    if not os.path.isdir(d):
        C.die(f"no voices/{name}/ yet: run ./pal voice prepare {name} <recording>", 3)
    v = {"name": name, "engine": "", "language": "en", "speed": 1.0, "seed": 1, "reference": {}}
    v.update(C.load(os.path.join(d, "voice.json"), default={}))
    v["_dir"] = d
    return v


def pick_reference(spk, lang):
    """(language of the clip used, wav path, its words); a missing language borrows another clip (and its accent)."""
    refs = spk["reference"]
    if not refs:
        C.die(f"voices/{spk['name']} has no reference clip: ./pal voice prepare {spk['name']} <recording>", 3)
    rl = lang if lang in refs else (spk.get("language") if spk.get("language") in refs else sorted(refs)[0])
    wav = os.path.join(spk["_dir"], refs[rl])
    txt = os.path.splitext(wav)[0] + ".txt"
    return rl, wav, open(txt, encoding="utf-8").read().strip() if os.path.exists(txt) else ""


def engine_name(spk, lang, override=None):
    """The engine for a line: the override, else the speaker's, else the default for the language."""
    for name in (override, spk.get("engine")):
        if name in ENGINES and lang in ENGINES[name][2]:
            return name
    return DEFAULT_ENGINE.get(lang) or C.die(f"no voice engine speaks '{lang}'")


def model_dir(engine):
    m = C.load(os.path.join(C.ROOT, "tools", "models.json"))[ENGINES[engine][0]]
    return m, os.path.join(C.CACHE, m["tts"]["dir"].split("/")[0] if "tts" in m else m["dir"])


def installed(engine):
    m, d = model_dir(engine)
    parts = [m["tts"], m["codec"]] if "tts" in m else [m]
    ok = all(os.path.exists(os.path.join(C.CACHE, p["dir"], f)) for p in parts for f in p["files"][:3])
    return ok and os.path.exists(os.path.join(C.ROOT, ".venv-voice", "bin", "python"))


class Worker:
    """One persistent engine process (its own Python environment); JSON lines in and out."""

    def __init__(self, engine):
        if not installed(engine):
            C.die(f"voice engine {engine} is not installed: run sh tools/setup.sh", 1)
        m, d = model_dir(engine)
        args = [d] + (["nano"] if engine.startswith("chatterbox") else [])
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_workers", ENGINES[engine][1])
        self.p = subprocess.Popen([os.path.join(C.ROOT, ".venv-voice", "bin", "python"), "-I", script] + args,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                  env=dict(os.environ, TQDM_DISABLE="1", VOICE_THREADS=os.environ.get("VOICE_THREADS", "2")))
        if not self.reply().get("ok"):
            C.die(f"{engine} worker did not start (run its worker by hand to see why)")

    def reply(self):
        for line in self.p.stdout:
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except ValueError:
                    pass
        return {"ok": False, "error": "worker stopped"}

    def ask(self, req):
        self.p.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        r = self.reply()
        if not r.get("ok"):
            C.die(f"voice engine: {r.get('error')}")


_workers = {}
STATS = {}   # engine -> [seconds computed, seconds of speech], for the measured speed


def synth(text, lang, spk, engine=None, seed=None, speed=None, say=None, quiet=False):
    """Path of the cached, levelled 24 kHz WAV for one line (made now if not cached)."""
    eng = engine_name(spk, lang, engine)
    seed = int(spk.get("seed", 1) if seed is None else seed)
    speed = float(spk.get("speed", 1.0) if speed is None else speed)
    spoken = say or text
    rl = rwav = None
    if ENGINES[eng][3]:
        rl, rwav, _ = pick_reference(spk, lang)
    m = C.load(os.path.join(C.ROOT, "tools", "models.json"))[ENGINES[eng][0]]
    rev = m["tts"]["revision"] if "tts" in m else m["revision"]
    key = C.sha(CODE_VERSION, eng, rev, spoken, lang, seed, speed, spk.get("voice", ""), C.file_sha(rwav) if rwav else "")
    path = os.path.join(C.CACHE, "voice", "lines", key + ".wav")
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if eng not in _workers:
        _workers[eng] = Worker(eng)
    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw.wav")
        t0 = time.time()
        _workers[eng].ask({"text": spoken, "ref": rwav, "out": raw, "seed": seed, "voice": spk.get("voice"),
                           "speed": speed if eng == "kokoro" else 1.0})
        took = time.time() - t0
        y = decode(raw)
    if speed != 1.0 and eng != "kokoro":
        y = tempo(y, speed)
    STATS.setdefault(eng, [0.0, 0.0])
    STATS[eng][0] += took
    STATS[eng][1] += len(y) / SR
    sf.write(path + ".part.wav", level(y), SR)
    os.replace(path + ".part.wav", path)
    if not quiet:
        print(f"  voiced [{eng}/{lang}] {took / max(len(y) / SR, 0.1):.1f}s per s: {spoken[:50]}", file=sys.stderr)
    return path


def load_line(path):
    return sf.read(path, dtype="float32")[0]


# ---------------------------------------------------------------- prepare
def best_window(y, lo=6.0, hi=10.0, target=8.0):
    """(start, end, score) of the best run of whole phrases lasting lo-hi seconds, or None."""
    db = frame_db(y)
    noise = float(np.percentile(db, 10))
    thresh = max(noise + 10, float(np.percentile(db, 90)) - 30, -55.0)
    best = None
    for gap in (0.3, 0.18):
        spans, start, quiet = [], None, 0
        for i, v in enumerate(db > thresh):
            if v:
                start, quiet = (i if start is None else start), 0
            elif start is not None:
                quiet += 1
                if quiet * 0.01 >= gap:
                    spans.append((start * 0.01, (i - quiet + 1) * 0.01))
                    start, quiet = None, 0
        if start is not None:
            spans.append((start * 0.01, len(db) * 0.01))
        spans = [s for s in spans if s[1] - s[0] >= 0.25]
        for i in range(len(spans)):
            for j in range(i, len(spans)):
                a, b = max(0.0, spans[i][0] - 0.12), min(len(y) / SR, spans[j][1] + 0.18)
                if b - a > hi:
                    break
                seg = db[int(a * 100): int(b * 100)]
                v = seg[seg > thresh]
                if b - a < lo or len(v) < 50:
                    continue
                clip = float(np.mean(np.abs(y[int(a * SR): int(b * SR)]) > 0.985))
                score = (min(float(np.median(v)) - noise, 45) / 10 - float(np.std(v)) / 6 - abs(b - a - target) / 3
                         - max(0.0, 0.65 - len(v) / len(seg)) * 6 - clip * 400)
                if best is None or score > best[2]:
                    best = (a, b, score)
        if best:
            return best
    return None


def cmd_prepare(argv):
    ap = argparse.ArgumentParser(prog="pal voice prepare")
    ap.add_argument("speaker")
    ap.add_argument("media")
    ap.add_argument("--lang", help="language of the recording (default: detected)")
    ap.add_argument("--from", dest="t0", type=float)
    ap.add_argument("--to", dest="t1", type=float)
    a = ap.parse_args(argv)
    import transcribe as T
    if not os.path.exists(a.media):
        C.die(f"{a.media} not found", 2)
    y = decode(a.media)
    if a.t0 is not None or a.t1 is not None:
        span = (a.t0 or 0.0, min(a.t1 or 1e9, len(y) / SR))
        cand = (span[0], span[1], 99.0)
    else:
        cand = best_window(y)
        if cand is None:
            C.die("no 6-10 s run of clear speech found. Give a span with --from/--to, or a cleaner recording", 3)
    clip = filter_audio(y[int(cand[0] * SR): int(cand[1] * SR)], "highpass=f=60")
    clip = level(clip)
    d = os.path.join(C.ROOT, "voices", a.speaker)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "_clip.wav")
    sf.write(tmp, clip, SR, subtype="PCM_16")
    t = T.transcribe_media(tmp, a.lang, None, False, "voice-clip", 2, announce=False)
    lang = a.lang or t["language"]
    os.replace(tmp, os.path.join(d, f"{lang}.wav"))
    words = " ".join(w["w"] for w in t["words"])
    open(os.path.join(d, f"{lang}.txt"), "w", encoding="utf-8").write(words + "\n")
    vj = os.path.join(d, "voice.json")
    v = C.load(vj, default={"name": a.speaker, "engine": "", "language": lang, "speed": 1.0, "seed": 1, "reference": {}})
    v["reference"][lang] = f"{lang}.wav"
    C.save(vj, v)
    C.say(f"✓ voices/{a.speaker}/{lang}.wav  {cand[1] - cand[0]:.1f} s from {C.tc(cand[0])} to {C.tc(cand[1])}",
          f"  words: {words}", "  Check the words against what is said; fix voices/%s/%s.txt if Whisper misheard." % (a.speaker, lang))
    return 0


# ---------------------------------------------------------------- say and test
def cmd_say(argv):
    ap = argparse.ArgumentParser(prog="pal voice say")
    ap.add_argument("speaker")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--text", required=True)
    ap.add_argument("--engine")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args(argv)
    p = synth(a.text, a.lang, speaker(a.speaker), a.engine)
    y = load_line(p)
    sf.write(a.out, y, SR)
    C.say(f"✓ {a.out}  {len(y) / SR:.1f} s")
    return 0


def cmd_test(argv):
    ap = argparse.ArgumentParser(prog="pal voice test")
    ap.add_argument("speaker")
    ap.add_argument("--engines", help="comma list (default: every installed engine)")
    ap.add_argument("--langs", default="en,fa", help="output languages")
    a = ap.parse_args(argv)
    spk = speaker(a.speaker)
    names = a.engines.split(",") if a.engines else [e for e in ENGINES if installed(e)]
    out = os.path.join(spk["_dir"] or os.path.join(C.ROOT, "voices", "stock"), "test")
    os.makedirs(out, exist_ok=True)
    rows, rates = [], {}
    for eng in names:
        for lang in a.langs.split(","):
            if lang not in ENGINES[eng][2]:
                continue
            for rl in (sorted(spk["reference"]) if ENGINES[eng][3] else [None]):
                s2 = dict(spk, reference={rl: spk["reference"][rl]}) if rl else spk
                t0, ys, bad, total, words = time.time(), [], 0, 0, 0
                for text in TEST_LINES[lang]:
                    p = synth(text, lang, s2, eng, quiet=True)
                    y = load_line(p)
                    ys.append(y)
                    ref, hyp = tokens(text, lang), tokens(" ".join(w for w, _, _ in read_back(p, lang)), lang)
                    bad += edit_distance(ref, hyp)
                    total += len(ref)
                    words += len(words_of(text))
                speech = sum(len(y) for y in ys) / SR
                name = f"{lang}-from-{rl or 'stock'}-{eng}"
                sf.write(os.path.join(out, name + ".wav"), np.concatenate([np.concatenate([y, np.zeros(SR // 2, "f4")]) for y in ys]), SR)
                C.run(["ffmpeg", "-i", os.path.join(out, name + ".wav"), "-b:a", "128k", os.path.join(out, name + ".mp3")])
                os.remove(os.path.join(out, name + ".wav"))
                spent = STATS.get(eng, [0, 0])
                rates.setdefault(eng, {})[lang] = round(words / speech, 2)
                rows.append(f"{name:<34} {speech:5.1f}s  {spent[0] / max(spent[1], 1e-9):4.2f}x compute  "
                            f"{bad}/{total} words wrong ({bad / max(total, 1):.0%})  {words / speech:.2f} words/s")
    C.save(os.path.join(out, "rate.json"), {"v": 1, "words_per_second": rates})
    open(os.path.join(out, "report.txt"), "w").write("\n".join(rows) + "\n")
    C.say(*rows, f"files in {os.path.relpath(out, C.ROOT)}/ (listen for accent and likeness; only ears can judge those)")
    return 0


def words_of(text):
    return re.findall(r"[^\W_]+(?:['’‌-][^\W_]+)*", text)


def rate_for(spk, engine, lang):
    """Words per second of this voice, as measured by `voice test` (a default if not measured yet)."""
    r = C.load(os.path.join(spk["_dir"] or "", "test", "rate.json"), default={}) if spk["_dir"] else {}
    return r.get("words_per_second", {}).get(engine, {}).get(lang) or {"en": 2.7, "fa": 2.4}.get(lang, 2.5)


# ---------------------------------------------------------------- script
def parse_script(path, default_speaker):
    """[{id, speaker, text, say, para}] from script.md."""
    lines, para, last = [], 0, None
    for raw in open(path, encoding="utf-8").read().splitlines():
        s = raw.strip()
        m = re.match(r"^(L\d+)\s*\|\s*(.*)$", s)
        if m:
            parts = [x.strip() for x in m.group(2).split("|")]
            text, say = parts[0], next((p[4:].strip() for p in parts[1:] if p.startswith("say:")), "")
            who = default_speaker
            mm = re.match(r"^([\w-]+):\s+(.*)$", text)
            if mm and (mm.group(1) == "stock" or os.path.isdir(os.path.join(C.ROOT, "voices", mm.group(1)))):
                who, text = mm.group(1), mm.group(2)
            last = {"id": m.group(1), "speaker": who, "text": text, "say": say, "para": para}
            lines.append(last)
        elif s.startswith("say:") and last:
            last["say"] = s[4:].strip()
        elif not s:
            para += 1 if last else 0
    return lines


def align(text, y, lang, key):
    """[(word, start, end)] for the script words of one line: heard words matched by position."""
    cache = os.path.join(C.CACHE, "voice", "align", key + ".json")
    if os.path.exists(cache):
        return C.load(cache)
    known, heard = text.split(), read_back(y, lang)
    kn, hn = [tokens(w, lang) for w in known], [tokens(h[0], lang) for h in heard]
    kflat = [" ".join(t) for t in kn]
    hflat = [" ".join(t) for t in hn]
    a, b = voiced_span(y)
    t0, t1 = (heard[0][1], heard[-1][2]) if heard else (a, b)
    times = [None] * len(known)
    for blk in difflib.SequenceMatcher(None, kflat, hflat, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            times[blk.a + k] = (heard[blk.b + k][1], heard[blk.b + k][2])
    # words with no match share the time between their matched neighbours, by length
    i = 0
    while i < len(known):
        if times[i] is None:
            j = i
            while j < len(known) and times[j] is None:
                j += 1
            lo = times[i - 1][1] if i else t0
            hi = times[j][0] if j < len(known) else t1
            wts = [len(w) + 1 for w in known[i:j]]
            t = lo
            for k in range(i, j):
                d = max(hi - lo, 0.02 * (j - i)) * wts[k - i] / sum(wts)
                times[k] = (t, t + d)
                t += d
        i += 1
    res = [(w, round(s, 3), round(e, 3)) for w, (s, e) in zip(known, times)]
    C.save(cache, res)
    return res


def cmd_script(argv):
    ap = argparse.ArgumentParser(prog="pal voice script")
    ap.add_argument("episode")
    ap.add_argument("--lang")
    ap.add_argument("--speaker")
    a = ap.parse_args(argv)
    ep = C.episode(a.episode)
    sp = os.path.join(ep, "script.md")
    if not os.path.exists(sp):
        C.die(f"{C.rel(C.ROOT, sp)} not found: write the script first (lines like 'L01 | text')", 3)
    ch = C.channel()
    lang = a.lang or ch.get("languages", {}).get("spoken") or "en"
    lang = lang[0] if isinstance(lang, list) else lang
    default = a.speaker or os.path.basename((ch.get("voices") or {}).get("host", "voices/host")) or "host"
    lines = parse_script(sp, default)
    if not lines:
        C.die("script.md has no lines like 'L01 | text'", 3)
    track, cursor, prev, words, segs = [], 0.45, None, [], []
    for ln in lines:
        spk = speaker(ln["speaker"])
        p = synth(ln["text"], lang, spk, say=ln["say"] or None)
        y = load_line(p)
        a0, b0 = voiced_span(y)
        y = y[int(a0 * SR): int(b0 * SR)]
        if prev is not None:
            cursor += 0.6 if ln["para"] != prev["para"] else 0.25
        key = C.sha(os.path.basename(p), ln["text"], lang, a0)
        ws = align(ln["text"], y, lang, key)
        first = len(words) + 1
        for w, s, e in ws:
            words.append({"id": f"w{len(words) + 1}", "w": w, "start": round(cursor + s, 3), "end": round(cursor + e, 3), "p": 1.0})
        segs.append({"id": f"s{len(segs) + 1}", "start": round(cursor, 3), "end": round(cursor + len(y) / SR, 3),
                     "first": f"w{first}", "last": f"w{len(words)}", "text": ln["text"], "line": ln["id"]})
        track.append((cursor, y))
        cursor += len(y) / SR
        prev = ln
    total = cursor + 0.5
    mix = np.zeros(int(round(total * SR)) + 1, dtype=np.float32)
    for t, y in track:
        i = int(round(t * SR))
        mix[i: i + len(y)] += y
    wav = C.build(ep, "audio", f"voice.{lang}.wav")
    write48(wav, mix[: int(round(total * SR))])
    C.save(os.path.join(ep, "transcript.json"), {
        "language": lang, "duration": round(total, 3), "model": "script-readback", "source": "voice", "timeline": "edited",
        "words": words, "sounds": [], "segments": segs, "flags": []})
    C.say(f"✓ {len(lines)} lines, {C.tc(total)} -> {C.rel(ep, wav)} and transcript.json")
    return 0


def write48(path, y24):
    """24 kHz mono array -> 48 kHz mono WAV (what the mixer takes)."""
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "a.wav")
        sf.write(a, y24, SR, subtype="FLOAT")
        C.run(["ffmpeg", "-i", a, "-ar", str(OUT_SR), "-ac", "1", "-c:a", "pcm_s16le", path])


def main(argv):
    cmds = {"prepare": cmd_prepare, "test": cmd_test, "say": cmd_say, "script": cmd_script}
    if not argv or argv[0] not in cmds:
        print(__doc__.strip().splitlines()[0] + "\nUsage: ./pal voice prepare|test|say|script (./pal voice --help)", file=sys.stderr)
        return 2
    return cmds[argv[0]](argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
