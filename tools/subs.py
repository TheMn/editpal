"""Subtitles: build .srt/.vtt from the transcript or a translation, check them, burn them in.

    ./pal subs make <ep> [--lang fa,en]       subs/<lang>.srt and .vtt (default: channel.json languages.subtitles)
    ./pal subs lint <file.srt|file.vtt>       one line per problem; exit 1 if any
    ./pal subs burn <video> <srt> -o <mp4> [--style brand|plain] [--pos bottom|middle]
    ./pal subs file <media> --lang fa -o <dir> [--quick]  subtitles for any finished video (no episode needed)

The spoken language is built from the words of transcript.json (edited timeline); other languages
from the segments of translation.<lang>.json (`read` when present, else `text`; `skip` is left out).
Rules: 2 lines at most; 42 characters per line (37 for Persian); at most 17 characters per second
(a cue is stretched into the gap after it, up to 7 s); 1 to 7 s long; 2 frames between cues; lines
break at phrase boundaries; a cue does not run over a sentence end when it can be avoided.
Persian stays in logical order; a line that starts with Latin letters or digits gets U+200F so players
right-align it. `burn` uses libass with the fonts in brand/fonts/ and the caption style of
brand/frame.md (white text with a dark outline when that is missing).
"""
import argparse
import os
import re
import subprocess
import sys

import common

MAX_LINES = 2
LINE_CHARS = {"fa": 37, "ar": 37, "en": 42}
DEFAULT_CHARS = 42
MAX_CPS = 17.0
MIN_DUR, MAX_DUR = 1.0, 7.0
GAP_FRAMES = 2
RTL = ("fa", "ar", "he", "ur")
RLM = "‏"
INVISIBLE = "‌‎‏‪‫‬"
END_MARKS = ".!?؟…۔"
CLOSERS = "\"')]»”’"
BEFORE = {  # a good place to start a new line
    "en": {"and", "but", "or", "so", "because", "that", "which", "who", "when", "while", "if", "with",
           "of", "to", "in", "on", "for", "from", "by", "as", "at", "than", "then", "where"},
    "fa": {"و", "که", "اما", "ولی", "یا", "تا", "از", "در", "با", "به", "برای", "چون", "اگر", "زیرا", "چرا"},
}
AFTER = {"fa": {"را"}}


def vlen(s):
    """Visible length: direction marks and the zero-width non-joiner do not count."""
    return len([c for c in s if c not in INVISIBLE])


def limit(lang):
    """Characters per line for a language."""
    return LINE_CHARS.get(lang, DEFAULT_CHARS)


def is_end(tok):
    """True when a token ends a sentence."""
    return tok.rstrip(CLOSERS)[-1:] in END_MARKS if tok.rstrip(CLOSERS) else False


def is_soft(tok):
    return tok.rstrip(CLOSERS)[-1:] in ",;:،؛—–-"


# ---- line breaking ----------------------------------------------------------------------------

def wrap(words, lang):
    """Break a list of words into 1-2 balanced lines at the best phrase boundary; None if they do not fit."""
    lim = limit(lang)
    text = " ".join(words)
    if vlen(text) <= lim:
        return [text]
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if vlen(a) > lim or vlen(b) > lim:
            continue
        score = abs(vlen(a) - vlen(b)) / lim
        if is_end(words[i - 1]):
            score -= 0.5
        elif is_soft(words[i - 1]) or words[i - 1] in AFTER.get(lang, ()):
            score -= 0.3
        if words[i].lower() in BEFORE.get(lang, BEFORE["en"]):
            score -= 0.2
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1] if best else None


# ---- cues from timed tokens --------------------------------------------------------------------

def split_tokens(toks, lang):
    """Split a sentence (list of {"w","start","end"}) until each part fits two lines and 7 s."""
    words = [t["w"] for t in toks]
    dur = toks[-1]["end"] - toks[0]["start"]
    if len(toks) < 2 or (wrap(words, lang) and dur <= MAX_DUR - 0.5):
        return [toks]
    total = sum(vlen(w) + 1 for w in words)
    best = None
    run = 0
    for i in range(1, len(toks)):
        run += vlen(words[i - 1]) + 1
        score = abs(run / total - 0.5)
        if is_end(words[i - 1]):
            score -= 0.4
        elif is_soft(words[i - 1]) or words[i - 1] in AFTER.get(lang, ()):
            score -= 0.3
        if words[i].lower() in BEFORE.get(lang, BEFORE["en"]):
            score -= 0.15
        score -= min(toks[i]["start"] - toks[i - 1]["end"], 0.5) * 0.4
        if best is None or score < best[0]:
            best = (score, i)
    i = best[1]
    return split_tokens(toks[:i], lang) + split_tokens(toks[i:], lang)


def sentences(toks):
    """Group tokens into sentences: after an end mark or a pause of 0.8 s."""
    out, cur = [], []
    for k, t in enumerate(toks):
        cur.append(t)
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        if is_end(t["w"]) or nxt is None or nxt["start"] - t["end"] > 0.8:
            out.append(cur)
            cur = []
    return out


def merge_short(pieces, lang):
    """Join a piece that is too short to read with its neighbour when the two fit together."""
    def ok(a, b):
        toks = a + b
        return (toks[-1]["end"] - toks[0]["start"] <= MAX_DUR - 0.5
                and wrap([t["w"] for t in toks], lang) is not None)
    i = 0
    while i < len(pieces):
        p = pieces[i]
        short = p[-1]["end"] - p[0]["start"] < MIN_DUR - 0.2 and vlen(" ".join(t["w"] for t in p)) < 20
        if short and i + 1 < len(pieces) and pieces[i + 1][0]["start"] - p[-1]["end"] < 1.5 and ok(p, pieces[i + 1]):
            pieces[i:i + 2] = [p + pieces[i + 1]]
        elif short and i > 0 and p[0]["start"] - pieces[i - 1][-1]["end"] < 1.5 and ok(pieces[i - 1], p):
            pieces[i - 1:i + 1] = [pieces[i - 1] + p]
        else:
            i += 1
    return pieces


def mark_direction(line, lang):
    """RTL languages: a line that starts with Latin text or digits gets U+200F so it right-aligns."""
    if lang in RTL and re.match(r"[A-Za-z0-9]", line):
        return RLM + line
    return line


def build_cues(toks, lang, fps=30.0):
    """Timed tokens -> cues [{"start","end","lines"}] obeying the rules in the module help."""
    pieces = []
    for s in sentences(toks):
        pieces += split_tokens(s, lang)
    pieces = merge_short(pieces, lang)
    gap = GAP_FRAMES / fps
    cues = []
    for p in pieces:
        lines = wrap([t["w"] for t in p], lang) or [" ".join(t["w"] for t in p)]
        cues.append({"start": p[0]["start"], "end": p[-1]["end"],
                     "lines": [mark_direction(x, lang) for x in lines]})
    for k, c in enumerate(cues):
        nxt = cues[k + 1]["start"] - gap if k + 1 < len(cues) else float("inf")
        chars = vlen(" ".join(c["lines"]))
        want = max(c["end"], c["start"] + MIN_DUR, c["start"] + chars / MAX_CPS)
        c["end"] = min(want, c["start"] + MAX_DUR, nxt)
        c["start"] = common.snap(c["start"], fps)
        c["end"] = max(common.snap(c["end"] + 0.5 / fps, fps), c["start"] + 1 / fps)
        if k + 1 < len(cues) and c["end"] > nxt:
            c["end"] = common.snap(nxt - 0.5 / fps, fps)
    return cues


def tokens_from_words(words):
    """Transcript words -> tokens."""
    return [{"w": w["w"].strip(), "start": float(w["start"]), "end": float(w["end"])}
            for w in words if w.get("w", "").strip()]


def tokens_from_segments(segs):
    """Translation segments -> tokens, the time of each segment shared among its words by length."""
    toks = []
    for s in segs:
        if s.get("skip"):
            continue
        text = (s.get("read") or s.get("text") or "").strip()
        words = text.split()
        if not words:
            continue
        t0, t1 = float(s["start"]), float(s["end"])
        total = sum(vlen(w) + 1 for w in words)
        run = 0
        for w in words:
            a = t0 + (t1 - t0) * run / total
            run += vlen(w) + 1
            toks.append({"w": w, "start": a, "end": t0 + (t1 - t0) * run / total})
    return toks


# ---- files ---------------------------------------------------------------------------------------

def stamp(t, sep):
    """Seconds -> 00:00:00,000 (srt) or 00:00:00.000 (vtt)."""
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def write_files(cues, base):
    """Write base.srt and base.vtt (UTF-8, no BOM)."""
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    srt, vtt = [], ["WEBVTT", ""]
    for i, c in enumerate(cues, 1):
        body = "\n".join(c["lines"])
        srt += [str(i), f"{stamp(c['start'], ',')} --> {stamp(c['end'], ',')}", body, ""]
        vtt += [f"{stamp(c['start'], '.')} --> {stamp(c['end'], '.')}", body, ""]
    for ext, lines in (("srt", srt), ("vtt", vtt)):
        with open(f"{base}.{ext}", "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))


def make_one(ep, lang, spoken, tr):
    """Cues for one language of an episode, or None when its source file is missing."""
    fps = common.fps_of(ep)
    if lang == spoken:
        toks = tokens_from_words(tr["words"])
    else:
        path = os.path.join(ep, f"translation.{lang}.json")
        if not os.path.exists(path):
            return None
        toks = tokens_from_segments(common.load(path)["segments"])
    return build_cues(toks, lang, fps)


def make(argv):
    """subs make."""
    p = argparse.ArgumentParser(prog="pal subs make")
    p.add_argument("ep")
    p.add_argument("--lang")
    a = p.parse_args(argv)
    ep = common.episode(a.ep)
    tr = common.load(os.path.join(ep, "transcript.json"))
    spoken = tr.get("language") or common.channel().get("languages", {}).get("spoken", "en")
    langs = a.lang.split(",") if a.lang else (common.channel().get("languages", {}).get("subtitles") or [spoken])
    missing, lines = [], []
    for lang in langs:
        cues = make_one(ep, lang, spoken, tr)
        if cues is None:
            missing.append(lang)
            continue
        base = os.path.join(ep, "subs", lang)
        write_files(cues, base)
        bad = lint_file(base + ".srt")
        lines.append(f"✓ subs/{lang}.srt: {len(cues)} cues" + (f", {len(bad)} to look at (./pal subs lint)" if bad else ", clean"))
    common.say(*lines)
    if missing:
        common.say(f"✗ no translation.{'/'.join(missing)}.json: run ./pal dub init {a.ep} --to {missing[0]} first")
        return 3
    return 0


# ---- lint ----------------------------------------------------------------------------------------

def parse(path):
    """Read an .srt or .vtt into [{"start","end","lines"}]."""
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read().replace("\r\n", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        rows = block.split("\n")
        for k, row in enumerate(rows):
            m = re.match(r"(\d+):(\d\d):(\d\d)[,.](\d{3}) --> (\d+):(\d\d):(\d\d)[,.](\d{3})", row.strip())
            if m:
                g = [int(x) for x in m.groups()]
                cues.append({"start": g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000,
                             "end": g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000, "lines": rows[k + 1:]})
                break
    return cues


def lint_file(path, fps=30.0):
    """A list of problems (strings), one per problem."""
    lang = os.path.basename(path).split(".")[0]
    lim = limit(lang)
    out = []
    cues = parse(path)
    for i, c in enumerate(cues, 1):
        text = " ".join(x for x in c["lines"] if x.strip())
        dur = c["end"] - c["start"]
        tag = f"#{i} {common.tc(c['start'])}"
        if i > 1 and c["start"] < cues[i - 2]["end"]:
            out.append(f"{tag} overlaps the previous cue by {cues[i - 2]['end'] - c['start']:.2f} s")
        if not text.strip():
            out.append(f"{tag} empty cue")
            continue
        if len(c["lines"]) > MAX_LINES:
            out.append(f"{tag} {len(c['lines'])} lines (max {MAX_LINES})")
        for x in c["lines"]:
            if vlen(x) > lim:
                out.append(f"{tag} line of {vlen(x)} characters (max {lim}): {x[:30]}…")
        if dur < MIN_DUR - 0.01 or dur > MAX_DUR + 0.01:
            out.append(f"{tag} lasts {dur:.2f} s (allowed {MIN_DUR:g}-{MAX_DUR:g})")
        if dur > 0 and vlen(text) / dur > MAX_CPS + 0.4:
            out.append(f"{tag} reads at {vlen(text) / dur:.1f} characters/s (max {MAX_CPS:g})")
        if i > 1:
            gap = c["start"] - cues[i - 2]["end"]
            if 0 <= gap < GAP_FRAMES / fps - 0.004:
                out.append(f"{tag} only {gap * 1000:.0f} ms after the previous cue (need {GAP_FRAMES} frames)")
    return out


def lint(argv):
    """subs lint."""
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    if not os.path.exists(argv[0]):
        common.die(f"no such file {argv[0]}", 2)
    problems = lint_file(argv[0])
    common.say(*(problems or [f"✓ {argv[0]}: no problems ({len(parse(argv[0]))} cues)"]))
    return 1 if problems else 0


# ---- burn ----------------------------------------------------------------------------------------

def frame_captions():
    """The captions block and scrim colour of brand/frame.md (a tiny reader for its simple YAML)."""
    path = os.path.join(common.ROOT, "brand", "frame.md")
    cfg = {}
    if not os.path.exists(path):
        return cfg
    block = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^(\w[\w-]*):", line)
            if m:
                block = m.group(1)
                continue
            m = re.match(r"^\s+([\w-]+):\s*\"?([^\"#\n]*?)\"?\s*(#.*)?$", line)
            if m and block in ("captions", "colors"):
                cfg[f"{block}.{m.group(1)}"] = m.group(2).strip()
    return cfg


def ass_colour(hexcode, default):
    """'#RRGGBB' -> '&H00BBGGRR'."""
    m = re.match(r"#?([0-9a-fA-F]{6})$", hexcode or "")
    if not m:
        return default
    h = m.group(1)
    return "&H00" + h[4:6] + h[2:4] + h[0:2]


def burn(argv):
    """subs burn."""
    p = argparse.ArgumentParser(prog="pal subs burn")
    p.add_argument("video")
    p.add_argument("srt")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--style", choices=["brand", "plain"], default="brand")
    p.add_argument("--pos", choices=["bottom", "middle"], default="bottom")
    a = p.parse_args(argv)
    for f in (a.video, a.srt):
        if not os.path.exists(f):
            common.die(f"no such file {f}", 2)
    vs = [s for s in common.probe(a.video)["streams"] if s["codec_type"] == "video"][0]
    w, h = int(vs["width"]), int(vs["height"])
    with open(a.srt, encoding="utf-8-sig") as f:
        arabic = bool(re.search(r"[؀-ۿ]", f.read()))
    cfg = frame_captions() if a.style == "brand" else {}
    size_pct = float(cfg.get("captions.size") or 5.0)
    if size_pct > 5.0:   # house sizes are for word captions; sentence subtitles sit smaller
        size_pct = 5.0 if w >= h else 4.6
    size = round(h * size_pct / 100)
    outline = max(2, round(h * float(cfg.get("captions.outline") or 0.35) / 100 * 1.6))
    boxed = cfg.get("captions.background", "none") not in ("none", "")
    font = "Vazirmatn" if arabic or cfg.get("captions.font") == "persian" else "Inter Variable"
    style = {
        "FontName": font, "FontSize": size, "Bold": 1,
        "PrimaryColour": ass_colour(cfg.get("captions.color"), "&H00FFFFFF"),
        "OutlineColour": ass_colour(cfg.get("colors.scrim"), "&H00000000") if cfg else "&H00000000",
        "BackColour": ass_colour(cfg.get("captions.background"), "&H80000000") if boxed else "&H80000000",
        "BorderStyle": 3 if boxed else 1, "Outline": outline, "Shadow": 0 if boxed else 1,
        "Alignment": 2 if a.pos == "bottom" else 5,
        "MarginV": round(h * 0.07) if a.pos == "bottom" else 0,
        "MarginL": round(w * 0.08), "MarginR": round(w * 0.08), "WrapStyle": 2,
    }
    force = ",".join(f"{k}={v}" for k, v in style.items())
    fonts = os.path.join(common.ROOT, "brand", "fonts")
    srt = os.path.abspath(a.srt).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    vf = f"subtitles='{srt}':fontsdir='{fonts}':original_size={w}x{h}:force_style='{force}'"
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    common.run(["ffmpeg", "-i", a.video, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", a.out])
    common.say(f"✓ {a.out} ({font}, {size} px, {a.pos})")
    return 0


# ---- any video -----------------------------------------------------------------------------------

def file_(argv):
    """subs file."""
    p = argparse.ArgumentParser(prog="pal subs file")
    p.add_argument("media")
    p.add_argument("--lang", default=None)
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--quick", action="store_true", help="faster, less accurate transcription")
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    tjson = os.path.join(a.out, "transcript.json")
    cmd = [os.path.join(common.ROOT, "pal"), "transcribe", "file", a.media, "-o", tjson]
    if a.lang:
        cmd += ["--lang", a.lang]
    if a.quick:
        cmd.append("--quick")
    if not os.path.exists(tjson):
        r = subprocess.run(cmd)
        if r.returncode:
            return r.returncode
    tr = common.load(tjson)
    lang = a.lang or tr.get("language") or "en"
    cues = build_cues(tokens_from_words(tr["words"]), lang, 30.0)
    write_files(cues, os.path.join(a.out, lang))
    bad = lint_file(os.path.join(a.out, lang + ".srt"))
    common.say(f"✓ {a.out}/{lang}.srt and .vtt: {len(cues)} cues" + (f", {len(bad)} to look at" if bad else ", clean"))
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    fn = {"make": make, "lint": lint, "burn": burn, "file": file_}.get(argv[0])
    if not fn:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    return fn(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
