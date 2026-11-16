"""Words with times in any spoken language, plus the sounds a transcriber hides and suspect spans.

    ./pal transcribe <ep> [--lang fa] [--source mic] [--quick] [--prompt "names, terms"]
    ./pal transcribe show <ep> [--raw] [--from 60] [--to 120] [--words]
    ./pal transcribe file <media> -o <json> [--lang en] [--quick] [--prompt "…"]

Whisper large-v3 (faster-whisper, int8, CPU; MIT) with word times trimmed to the voiced audio.
`--quick` uses a small model: about 4x faster, good for a first look, wrong more often.
The language is `--lang`, else channel.json languages.spoken, else detected. Fillers are kept
("um", "uh"); `--prompt` lists names and terms so they are spelled right.

<ep> writes transcript.raw.json (timeline "source") from the audio master in sources.json
(`--source <id>` picks another). Besides "words" it holds "sounds" (voiced audio with no word on it:
um / breath / noise), "flags" (repeat-suspect = a phrase looping or words over silence, a Whisper
hallucination; speed-suspect = impossible speed) and "segments" (sentences). Never cut from a flag
without listening. Results are cached on the audio's hash, model, language and prompt.

`show` prints one line per sentence, the view to read instead of the JSON:
    s12 w210-228 1:02.4 +0.9 | text ⟨um 0.4⟩ ⚑repeat-suspect
(+0.9 = the pause after it). Without --raw it reads transcript.json (the edited timeline).
Models live in $EDITPAL_CACHE (default ~/.cache/editpal) and are downloaded there once if missing.
Long files take a while (large-v3 runs about real time on 4 cores): run them in the background.
"""
import argparse
import os
import re
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

CODE_VERSION = 3
END_MARKS = (".", "?", "!", "؟", "…", "۔")
PROMPTS = {
    "en": "Um, uh, so, like, you know, I mean, well... Yeah, okay.",
    "fa": "آم... اِ... خب، یعنی، چیز، مثلاً... آره، باشه.",
}
HOP = 160  # 10 ms at 16 kHz


# ---------------------------------------------------------------- audio

def load16k(path):
    """Any media file -> float32 mono 16 kHz array, decoded by ffmpeg (not by faster-whisper)."""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not r.stdout:
        C.die(f"ffmpeg could not read audio from {path}: " + r.stderr.decode(errors="replace")[-200:])
    return np.frombuffer(r.stdout, dtype="<f4").copy()


def envelope(y):
    """Per-10 ms level in dB, a voiced mask, and the zero-crossing rate of each frame."""
    n = len(y) // HOP
    fr = y[: n * HOP].reshape(n, HOP)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    zcr = (np.diff(np.signbit(fr), axis=1) != 0).mean(axis=1) if n else np.zeros(0)
    floor = max(float(np.percentile(db, 10)) + 10, float(np.percentile(db, 90)) - 32, -55.0) if n else -55.0
    voiced = db > floor
    # close gaps shorter than 30 ms (stop consonants) so one word is one stretch
    idx = np.flatnonzero(voiced)
    for a, b in zip(idx[:-1], idx[1:]):
        if 1 < b - a <= 3:
            voiced[a:b] = True
    return db, voiced, zcr


def vad_mask(y, n):
    """Boolean per 10 ms: Silero VAD (bundled in faster_whisper) says speech."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    opts = VadOptions(threshold=0.5, min_speech_duration_ms=60, min_silence_duration_ms=100, speech_pad_ms=0)
    m = np.zeros(n, dtype=bool)
    for s in get_speech_timestamps(y, opts):
        m[s["start"] // HOP: s["end"] // HOP + 1] = True
    return m


# ---------------------------------------------------------------- models

def model_paths(key):
    """(models.json entry, folder in the cache) for 'transcribe' or 'transcribe-quick'."""
    m = C.load(os.path.join(C.ROOT, "tools", "models.json"))[key]
    return m, os.path.join(C.CACHE, m["dir"])


def ensure_model(key):
    """Folder of the pinned model; downloads its files there first if any is missing."""
    import requests
    m, folder = model_paths(key)
    missing = [f for f in m["files"]
               if not os.path.exists(os.path.join(folder, f)) or os.path.getsize(os.path.join(folder, f)) == 0]
    if missing:
        print(f"· downloading {m['repo']} to {folder} (once; model.bin is large)", file=sys.stderr)
    for f in missing:
        url = f"https://huggingface.co/{m['repo']}/resolve/{m['revision']}/{f}"
        dest = os.path.join(folder, f)
        os.makedirs(folder, exist_ok=True)
        with requests.get(url, stream=True, timeout=60) as r:
            if r.status_code != 200:
                C.die(f"could not download {url} (HTTP {r.status_code}). Check the network, then run "
                      f"./pal transcribe again; or run sh tools/setup.sh")
            with open(dest + ".part", "wb") as out:
                for chunk in r.iter_content(1 << 20):
                    out.write(chunk)
        os.replace(dest + ".part", dest)
    return folder


def load_model(quick, threads):
    """The faster-whisper model (int8, CPU)."""
    from faster_whisper import WhisperModel
    folder = ensure_model("transcribe-quick" if quick else "transcribe")
    return WhisperModel(folder, device="cpu", compute_type="int8", cpu_threads=threads)


# ---------------------------------------------------------------- words

def run_whisper(y, lang, prompt, quick, threads):
    """Whisper on the audio array -> (language, word dicts without ids)."""
    model = load_model(quick, threads)
    dur = len(y) / 16000
    t0 = time.time()
    segs, info = model.transcribe(
        y, language=lang or None, initial_prompt=prompt or None, word_timestamps=True,
        beam_size=1 if quick else 5, condition_on_previous_text=False,
        hallucination_silence_threshold=2.0, vad_filter=False)
    words, last_report = [], 0.0
    for seg in segs:
        for w in seg.words or []:
            text = w.word.strip()
            if not text:
                continue
            if not re.search(r"\w", text) and words:      # lone punctuation sticks to the word before
                words[-1]["w"] += text
                continue
            words.append({"w": text, "start": float(w.start), "end": float(w.end),
                          "p": round(float(w.probability), 2)})
        if seg.end - last_report >= 300:
            last_report = seg.end
            print(f"· {C.tc(seg.end)} of {C.tc(dur)} ({seg.end / max(time.time() - t0, 1e-6):.1f}x real time)",
                  file=sys.stderr, flush=True)
    return info.language, words


def trim_words(words, voiced):
    """Pull each word's edges in to the voiced audio and keep the words in order, never overlapping."""
    n = len(voiced)
    prev_end = 0.0
    for w in words:
        a, b = int(w["start"] * 100), min(n, int(w["end"] * 100) + 1)
        v = np.flatnonzero(voiced[a:b]) if b > a else []
        if len(v):
            w["start"], w["end"] = (a + v[0]) / 100, (a + v[-1] + 1) / 100
        w["start"] = max(w["start"], prev_end)
        w["end"] = max(w["end"], w["start"] + 0.02)
        prev_end = w["end"]
    for w in words:
        w["start"], w["end"] = round(w["start"], 2), round(w["end"], 2)
    return words


def find_sounds(words, db, voiced, zcr, vad, min_len=0.15):
    """Voiced stretches with no word on them: um (speech-like, >= 0.2 s), breath (noisy, short), noise."""
    n = len(voiced)
    covered = np.zeros(n, dtype=bool)
    for w in words:
        covered[max(0, int(w["start"] * 100) - 2): int(w["end"] * 100) + 3] = True
    free = voiced & ~covered
    sounds, i = [], 0
    while i < n:
        if not free[i]:
            i += 1
            continue
        j = i
        while j < n and free[j]:
            j += 1
        d = (j - i) / 100
        if d >= min_len:
            speechy = vad[i:j].mean() >= 0.5
            noisy = float(np.median(zcr[i:j])) >= 0.12
            kind = "um" if speechy and d >= 0.2 else "breath" if noisy and d < 0.8 else "noise"
            sounds.append({"kind": kind, "start": round(i / 100, 2), "end": round(j / 100, 2)})
        i = j
    for k, s in enumerate(sounds, 1):
        s["id"] = f"u{k}"
    return [{"id": s["id"], "kind": s["kind"], "start": s["start"], "end": s["end"]} for s in sounds]


def norm(w):
    return re.sub(r"[^\w]+", "", w["w"].lower())


def find_flags(words, vad):
    """Spans the transcriber probably got wrong: looping phrases, words over silence, impossible speed."""
    flags, toks = [], [norm(w) for w in words]
    i = 0
    while i < len(words):                                   # a 3+ word phrase repeated 3+ times in a row
        hit = None
        for n in range(3, 9):
            if i + 3 * n > len(toks):
                break
            ph = toks[i: i + n]
            if not any(ph):
                continue
            reps = 1
            while toks[i + reps * n: i + (reps + 1) * n] == ph:
                reps += 1
            if reps >= 3:
                hit = (n, reps)
                break
        if hit:
            last = i + hit[0] * hit[1] - 1
            flags.append({"start": words[i]["start"], "end": words[last]["end"], "kind": "repeat-suspect"})
            i = last + 1
        else:
            i += 1
    run = []                                               # words where VAD found no speech
    for w in words + [None]:
        cov = vad[int(w["start"] * 100): int(w["end"] * 100) + 1].mean() if w and w["end"] > w["start"] else 1
        if w and cov < 0.2:
            run.append(w)
            continue
        if len(run) >= 2 or (run and run[0]["end"] - run[0]["start"] >= 0.8):
            flags.append({"start": run[0]["start"], "end": run[-1]["end"], "kind": "repeat-suspect"})
        run = []
    k = 8                                                  # more than 8 words per second
    for i in range(len(words) - k + 1):
        span = words[i + k - 1]["end"] - words[i]["start"]
        if span > 0 and k / span > 8.0:
            flags.append({"start": words[i]["start"], "end": words[i + k - 1]["end"], "kind": "speed-suspect"})
    flags.sort(key=lambda f: (f["start"], f["kind"]))
    merged = []
    for f in flags:
        if merged and merged[-1]["kind"] == f["kind"] and f["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], f["end"])
        else:
            merged.append(dict(f))
    return merged


# ---------------------------------------------------------------- sentences

def split_long(ws, max_len, min_words):
    """Cut a run of words longer than max_len at its widest inner pause (punctuation preferred)."""
    if ws[-1]["end"] - ws[0]["start"] <= max_len or len(ws) < 2 * min_words:
        return [ws]
    best, score = None, -1.0
    for i in range(min_words, len(ws) - min_words + 1):
        gap = ws[i]["start"] - ws[i - 1]["end"]
        s = gap + (0.3 if ws[i - 1]["w"].endswith(END_MARKS) else 0.15 if ws[i - 1]["w"].endswith((",", "،")) else 0)
        s -= abs((ws[i]["start"] - ws[0]["start"]) - (ws[-1]["end"] - ws[0]["start"]) / 2) * 0.01
        if s > score:
            best, score = i, s
    return split_long(ws[:best], max_len, min_words) + split_long(ws[best:], max_len, min_words)


def make_segments(words, max_len=14.0, min_words=3):
    """Sentences: split at a pause >= 0.45 s, or at sentence punctuation followed by a pause >= 0.15 s;
    each under ~14 s; a piece under 3 words joins its nearer neighbour unless it stands alone."""
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        gap = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 99.0
        if gap >= 0.45 or (w["w"].endswith(END_MARKS) and gap >= 0.15):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    groups = [p for g in groups for p in split_long(g, max_len, min_words)]
    i = 0
    while i < len(groups):
        g = groups[i]
        if len(g) < min_words and len(groups) > 1:
            before = g[0]["start"] - groups[i - 1][-1]["end"] if i > 0 else 99.0
            after = groups[i + 1][0]["start"] - g[-1]["end"] if i + 1 < len(groups) else 99.0
            if min(before, after) < 0.45:
                j = i - 1 if before <= after else i + 1
                a, b = sorted((i, j))
                if groups[b][-1]["end"] - groups[a][0]["start"] <= max_len:
                    groups[a] = groups[a] + groups[b]
                    del groups[b]
                    i = max(0, a)
                    continue
        i += 1
    return [{"id": f"s{k}", "start": g[0]["start"], "end": g[-1]["end"], "first": g[0]["id"],
             "last": g[-1]["id"], "text": " ".join(w["w"] for w in g)} for k, g in enumerate(groups, 1)]


# ---------------------------------------------------------------- the whole job

def transcribe_audio(y, lang, prompt, quick, threads, source):
    """Audio array -> the transcript dict of FORMATS.md (without caching)."""
    db, voiced, zcr = envelope(y)
    vad = vad_mask(y, len(voiced))
    language, words = run_whisper(y, lang, prompt, quick, threads)
    words = trim_words(words, voiced)
    for k, w in enumerate(words, 1):
        w["id"] = f"w{k}"
    words = [{"id": w["id"], "w": w["w"], "start": w["start"], "end": w["end"], "p": w["p"]} for w in words]
    return {"language": language, "duration": round(len(y) / 16000, 3),
            "model": "small" if quick else "large-v3", "source": source, "timeline": "source",
            "words": words, "sounds": find_sounds(words, db, voiced, zcr, vad),
            "flags": find_flags(words, vad), "segments": make_segments(words)}


def transcribe_media(media, lang, prompt, quick, source, threads, announce=True):
    """Transcript of one audio/video file, cached in $EDITPAL_CACHE/transcripts on the file's hash."""
    key = C.sha(C.file_sha(media), bool(quick), lang or "", prompt or "", CODE_VERSION)
    cache = os.path.join(C.CACHE, "transcripts", key + ".json")
    if os.path.exists(cache):
        out = C.load(cache)
        out["source"] = source
        if announce:
            print("· same audio, model, language and prompt as before: reusing the transcript", file=sys.stderr)
        return out
    out = transcribe_audio(load16k(media), lang, prompt, quick, threads, source)
    C.save(cache, out)
    return out


def summary(t):
    """One line telling what was found."""
    kinds = [s["kind"] for s in t.get("sounds", [])]
    return (f"{t['language']} · {C.tc(t['duration'])} · {t['model']} · {len(t['words'])} words · "
            f"{len(t['segments'])} sentences · {kinds.count('um')} um, {kinds.count('breath')} breath, "
            f"{kinds.count('noise')} noise · {len(t['flags'])} flags")


# ---------------------------------------------------------------- show

def show_lines(t, t_from=None, t_to=None, with_words=False):
    """The compact view of a transcript, one line per sentence."""
    words = {w["id"]: i for i, w in enumerate(t["words"])}
    segs, sounds, flags = t["segments"], t.get("sounds", []), t.get("flags", [])
    lines = [f"# {summary(t)} · timeline {t.get('timeline', 'source')}"]
    for k, s in enumerate(segs):
        if t_from is not None and s["end"] < t_from or t_to is not None and s["start"] > t_to:
            continue
        nxt = segs[k + 1]["start"] if k + 1 < len(segs) else None
        pause = (nxt - s["end"]) if nxt is not None else 0.0
        limit = nxt if nxt is not None else float("inf")
        lo = 0.0 if k == 0 else s["start"]
        mine = [u for u in sounds if lo <= u["start"] < limit]
        ws = t["words"][words[s["first"]]: words[s["last"]] + 1]
        parts, rest = [], sorted(mine, key=lambda u: u["start"])
        for w in ws:
            while rest and rest[0]["start"] < w["start"]:
                u = rest.pop(0)
                parts.append(f"⟨{u['kind']} {u['end'] - u['start']:.1f}⟩")
            parts.append(w["w"])
        parts += [f"⟨{u['kind']} {u['end'] - u['start']:.1f}⟩" for u in rest]
        fl = sorted({f["kind"] for f in flags if f["start"] < s["end"] and f["end"] > s["start"]})
        ids = s["first"] if s["first"] == s["last"] else f"{s['first']}-{s['last'][1:]}"
        lines.append(f"{s['id']} {ids} {C.tc(s['start'])} +{pause:.1f} | {' '.join(parts)}"
                     + "".join(f" ⚑{x}" for x in fl))
        if with_words:
            lines += [f"    {w['id']} {w['start']:.2f}-{w['end']:.2f} {w['w']}" for w in ws]
    return lines


def cmd_show(argv):
    """`transcribe show <ep>`."""
    ap = argparse.ArgumentParser(prog="pal transcribe show", description="compact transcript view")
    ap.add_argument("ep")
    ap.add_argument("--raw", action="store_true", help="the source timeline (transcript.raw.json)")
    ap.add_argument("--from", dest="t_from", type=float)
    ap.add_argument("--to", dest="t_to", type=float)
    ap.add_argument("--words", action="store_true", help="one line per word with id and times")
    a = ap.parse_args(argv)
    if os.path.isfile(a.ep) and a.ep.endswith(".json"):
        path = a.ep
    else:
        ep = C.episode(a.ep)
        path = os.path.join(ep, "transcript.raw.json" if a.raw else "transcript.json")
        if not a.raw and not os.path.exists(path):
            print("· no transcript.json yet (no edit): showing transcript.raw.json", file=sys.stderr)
            path = os.path.join(ep, "transcript.raw.json")
    if not os.path.exists(path):
        C.die(f"{os.path.basename(path)} not found. Run ./pal transcribe <episode> first.")
    for ln in show_lines(C.load(path), a.t_from, a.t_to, a.words):
        print(ln)
    return 0


# ---------------------------------------------------------------- commands

def common_args(ap):
    """Options shared by the episode and file forms."""
    ap.add_argument("--lang", help="spoken language code (fa, en, …); default channel.json, else detected")
    ap.add_argument("--quick", action="store_true", help="small fast model, for a first look")
    ap.add_argument("--prompt", default="", help="names and terms to spell right")
    ap.add_argument("--threads", type=int, default=int(os.environ.get("EDITPAL_THREADS", os.cpu_count() or 4)))


def build_prompt(lang, extra):
    """Initial prompt: the creator's terms, then the hesitation words that keep fillers in."""
    base = PROMPTS.get((lang or "")[:2], "")
    return (extra.strip() + (". " if extra.strip() and base else "") + base).strip()


def finish(t, started):
    """Print the one-line result with the speed."""
    speed = t["duration"] / max(time.time() - started, 1e-6)
    C.say("✓ " + summary(t), f"  {speed:.1f}x real time")


def cmd_ep(argv):
    """`transcribe <ep>`."""
    ap = argparse.ArgumentParser(prog="pal transcribe", description="transcribe an episode's audio master")
    ap.add_argument("ep")
    ap.add_argument("--source", help="source id to transcribe (default: the audio master)")
    common_args(ap)
    a = ap.parse_args(argv)
    ep = C.episode(a.ep)
    src = C.load(os.path.join(ep, "sources.json"), default={})
    sid = a.source or src.get("audio_master") or src.get("master")
    if not sid or sid not in src.get("sources", {}):
        C.die("no audio source yet. Run ./pal ingest <episode> first (or pass --source <id>).")
    media = os.path.join(ep, src["sources"][sid].get("conform") or src["sources"][sid]["file"])
    if not os.path.exists(media):
        C.die(f"{C.rel(ep, media)} is missing. Run ./pal ingest <episode> (or ./pal restore <episode>).")
    lang = a.lang or C.channel().get("languages", {}).get("spoken") or None
    started = time.time()
    t = transcribe_media(media, lang, build_prompt(lang, a.prompt), a.quick, sid, a.threads)
    C.save(os.path.join(ep, "transcript.raw.json"), t)
    finish(t, started)
    for f in t["flags"][:5]:
        print(f"  ⚑ {f['kind']} {C.tc(f['start'])}-{C.tc(f['end'])}")
    print("  next: ./pal transcribe show " + os.path.basename(ep) + " --raw")
    return 0


def cmd_file(argv):
    """`transcribe file <media> -o <json>`."""
    ap = argparse.ArgumentParser(prog="pal transcribe file", description="transcribe any media file")
    ap.add_argument("media")
    ap.add_argument("-o", "--out", help="output JSON (default: <media>.transcript.json)")
    common_args(ap)
    a = ap.parse_args(argv)
    if not os.path.exists(a.media):
        C.die(f"{a.media} not found", 2)
    lang = a.lang or C.channel().get("languages", {}).get("spoken") or None
    started = time.time()
    t = transcribe_media(a.media, lang, build_prompt(lang, a.prompt), a.quick, os.path.basename(a.media), a.threads)
    out = a.out or os.path.splitext(a.media)[0] + ".transcript.json"
    C.save(out, t)
    finish(t, started)
    print(f"  wrote {out}")
    return 0


def main(argv):
    """Entry point for ./pal transcribe."""
    if not argv:
        print(__doc__.strip())
        return 2
    if argv[0] == "show":
        return cmd_show(argv[1:])
    if argv[0] == "file":
        return cmd_file(argv[1:])
    return cmd_ep(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
