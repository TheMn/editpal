"""Another language's voice track in the speaker's cloned voice, timed to the original.

    ./pal dub init <ep> --to en [--speaker host]    translation.<to>.json from transcript.json
    ./pal dub check <ep> --to en                    untranslated lines; lines too long for their time
    ./pal dub voice <ep> --to en [--engine ...]     voice every line, place it, write the stem
    ./pal dub verify <ep> --to en                   read the stem back; list lines that were misread

init: one segment per sentence of transcript.json (edited timeline): "src" filled, "text" empty for
  the language model to fill. If the creator's own subtitles are in build/source/ (.srt .vtt .sbv),
  the cues in the target language, joined into sentences, become "text" and set the timing.
  Existing translations are kept when you run it again.
check: lines that still have no text, and lines too long for their slot at this voice's speaking
  rate (words per second measured by ./pal voice test; a default until then). Shorten those.
voice: each line is voiced (cached, so only changed lines are redone) and placed at its sentence's
  start, or just after the previous line if that ran long. A line may run up to 1.5 s into the next
  sentence's time (the drift is caught up at the next pause). A line that is too long gets two more
  takes with other seeds (the shortest wins), then at most x1.15 speed-up; if it is still too long
  it is listed in build/dub/report.txt. Writes build/dub/voice.<to>.wav (48 kHz mono, as long as
  the edited video): the voice only, no music (./pal mix does that), and build/dub/lines.json.
verify: transcribes the stem and compares each line's words; writes build/dub/verify.txt.
"""
import argparse
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import voice as V  # noqa: E402

MIN_GAP = 0.15
MAX_DRIFT = 1.5
MAX_TEMPO = 1.15
SUBS = (".srt", ".vtt", ".sbv")


def tpath(ep, to):
    return os.path.join(ep, f"translation.{to}.json")


def script_of(text):
    """'ar' for Arabic-script text (Persian), else 'latin'."""
    return "ar" if len(re.findall(r"[؀-ۿ]", text)) > len(re.findall(r"[A-Za-z]", text)) else "latin"


def read_subs(path):
    """[(start, end, text)] from .srt / .vtt / .sbv."""
    def secs(x):
        parts = (["0", "0"] + x.strip().replace(",", ".").split(":"))[-3:]
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    cues = []
    for block in re.split(r"\n\s*\n", open(path, encoding="utf-8-sig").read().replace("\r", "")):
        lines = [x for x in block.split("\n") if x.strip()]
        for i, x in enumerate(lines):
            m = re.match(r"\s*([\d:.,]+)\s*(?:-->|,)\s*([\d:.,]+)", x)
            if m and ("-->" in x or path.endswith(".sbv")):
                text = re.sub(r"<[^>]+>", "", " ".join(lines[i + 1:])).strip()
                if text:
                    cues.append((round(secs(m.group(1)), 3), round(secs(m.group(2)), 3), text))
                break
    return cues


def sentences(cues, max_len=20.0):
    """Join cues until a sentence ends (. ? ! … ؟), so one spoken line gets the time of all its cues."""
    out, cur = [], None
    for a, b, text in cues:
        if cur and a - cur[1] < 0.6 and b - cur[0] <= max_len and not re.search(r"[.?!…؟:;]['\"”)]*$", cur[2]):
            cur = (cur[0], b, cur[2] + " " + text)
        else:
            out += [cur] if cur else []
            cur = (a, b, text)
    return out + ([cur] if cur else [])


def subtitle_cues(ep, to):
    """Cues in the target language from build/source/ subtitle files, or []."""
    d = os.path.join(ep, "build", "source")
    want = script_of("x" if to == "en" else "ا")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.lower().endswith(SUBS):
            cues = read_subs(os.path.join(d, f))
            if cues and sum(script_of(c[2]) == want for c in cues) > len(cues) / 2:
                return cues
    return []


def speaker_name(a):
    ch = C.channel()
    return a.speaker or os.path.basename((ch.get("voices") or {}).get("host", "voices/host")) or "host"


def cmd_init(a):
    ep = C.episode(a.episode)
    tr = C.load(os.path.join(ep, "transcript.json"), default={})
    cues = subtitle_cues(ep, a.to)
    if not tr and not cues:
        C.die("no transcript.json (run ./pal transcribe and ./pal cut remap) and no subtitle file in build/source/", 3)
    src_segs = [(s["start"], s["end"], s["text"]) for s in tr.get("segments", [])]
    if cues:
        base = [(x, y, t, "") for x, y, t in sentences(cues)]
    else:
        base = [(x, y, "", t) for x, y, t in src_segs]
    segs = []
    for i, (x, y, text, src) in enumerate(base, 1):
        if text:      # the creator's own wording: find the spoken sentence it overlaps
            over = [t for sx, sy, t in src_segs if min(y, sy) - max(x, sx) > 0.5 * min(y - x, sy - sx)]
            src = " ".join(over)
        segs.append({"id": i, "start": x, "end": y, "src": src, "text": text, "read": "", "note": "", "skip": False})
    old = C.load(tpath(ep, a.to), default={})
    kept = 0
    for s in segs:      # keep earlier work on a re-run
        for o in old.get("segments", []):
            if abs(o["start"] - s["start"]) < 0.05 and (o.get("text") or o.get("skip")):
                s.update(text=o["text"], read=o.get("read", ""), note=o.get("note", ""), skip=o.get("skip", False))
                kept += 1
                break
    dur = tr.get("duration") or (max(s["end"] for s in segs) if segs else 0)
    C.save(tpath(ep, a.to), {"v": 1, "from": tr.get("language", "fa"), "to": a.to, "voice": speaker_name(a), "duration": dur,
                             "glossary": old.get("glossary", {}), "segments": segs})
    todo = sum(1 for s in segs if not s["text"] and not s["skip"])
    C.say(f"✓ {len(segs)} segments -> translation.{a.to}.json ({kept} kept from before, "
          f"{'from the creator subtitles' if cues else 'from the transcript'}); {todo} still need {a.to} text")
    return 0


def window(segs, i, prev_end, total):
    """(start, seconds allowed) for line i."""
    start = max(segs[i]["start"], prev_end + MIN_GAP)
    limit = segs[i + 1]["start"] + MAX_DRIFT if i + 1 < len(segs) else total
    return start, max(0.3, min(limit, total) - start)


def cmd_check(a):
    ep = C.episode(a.episode)
    d = C.load(tpath(ep, a.to))
    spk = V.speaker(d["voice"]) if d.get("voice") else None
    wps = V.rate_for(spk, V.engine_name(spk, a.to), a.to) if spk else 2.7
    missing, tight, prev = [], [], -1.0
    segs = d["segments"]
    for i, s in enumerate(segs):
        if s.get("skip"):
            continue
        if not s["text"].strip():
            missing.append(s["id"])
            continue
        start, allowed = window(segs, i, prev, d["duration"])
        need = len(V.words_of(s["text"])) / wps + 0.1
        if need > allowed * MAX_TEMPO:
            tight.append(f"  #{s['id']} {C.tc(s['start'])}: ~{need:.1f} s of speech, {allowed:.1f} s available: {s['text']}")
        prev = start + min(max(allowed, need / MAX_TEMPO), need)
    C.say(f"{len(segs)} segments; {len(missing)} without text; {len(tight)} likely too long (at {wps} words/s)",
          *(["  no text: " + ", ".join(map(str, missing[:40]))] if missing else []), *tight[:20])
    return 0 if not missing and not tight else 3


def fit(text, spk, slot, engine, lang):
    """A voiced line (trimmed) for a slot of `slot` seconds, and a note if it still does not fit."""
    take = lambda seed: V.trim(V.load_line(V.synth(text, lang, spk, engine, seed=seed, quiet=True)))
    y = take(None)
    if len(y) / V.SR > slot * 1.05:
        y = min([y] + [take(s) for s in (int(spk.get("seed", 1)) + 1, int(spk.get("seed", 1)) + 2)], key=len)
    note = ""
    if len(y) / V.SR > slot:
        f = min(MAX_TEMPO, len(y) / V.SR / slot)
        y = V.tempo(y, f)
        if len(y) / V.SR > slot + 0.05:
            note = f"{len(y) / V.SR:.1f} s for a {slot:.1f} s slot even at x{f:.2f}: shorten it"
    return y, note


def cmd_voice(a):
    ep = C.episode(a.episode)
    d = C.load(tpath(ep, a.to))
    if d.get("voice") is None:
        C.die("this translation has voice: null (subtitles only); set a speaker name to dub", 3)
    spk = V.speaker(d["voice"])
    segs, total = d["segments"], float(d["duration"])
    track = np.zeros(int(round(total * V.SR)) + V.SR, dtype=np.float32)
    lines, report, prev, drift = [], [], -1.0, 0.0
    for i, s in enumerate(segs):
        text = s["text"].strip()
        if s.get("skip") or not text:
            continue
        start, allowed = window(segs, i, prev, total)
        y, note = fit(text, spk, allowed, a.engine, a.to)
        k = int(round(start * V.SR))
        track[k: k + len(y)] += y[: max(0, len(track) - k)]
        prev = start + len(y) / V.SR
        drift = max(drift, start - s["start"])
        lines.append({"id": s["id"], "start": round(start, 3), "end": round(prev, 3), "text": text, "orig_start": s["start"]})
        if note:
            report.append(f"#{s['id']} {C.tc(s['start'])} {note}: {text}")
    out = C.build(ep, "dub", f"voice.{a.to}.wav")
    V.write48(out, track[: int(round(total * V.SR))])
    C.save(os.path.join(ep, "build", "dub", "lines.json"), lines)
    open(os.path.join(ep, "build", "dub", "report.txt"), "w", encoding="utf-8").write("\n".join(report) + ("\n" if report else ""))
    C.say(f"✓ {len(lines)} lines -> {C.rel(ep, out)} ({C.tc(total)}); max drift {drift:.1f} s; {len(report)} too long (build/dub/report.txt)",
          *report[:10])
    return 0


def cmd_verify(a):
    ep = C.episode(a.episode)
    lines = C.load(os.path.join(ep, "build", "dub", "lines.json"))
    heard = V.read_back(os.path.join(ep, "build", "dub", f"voice.{a.to}.wav"), a.to)
    bad, wrong, total = [], 0, 0
    for ln in lines:
        mine = " ".join(w for w, s, e in heard if ln["start"] - 0.3 <= (s + e) / 2 <= ln["end"] + 0.3)
        r, h = V.tokens(ln["text"], a.to), V.tokens(mine, a.to)
        dist = V.edit_distance(r, h)
        wrong += dist
        total += len(r)
        if len(r) >= 3 and dist / len(r) > 0.34:
            bad.append(f"#{ln['id']} {C.tc(ln['start'])}  said: {ln['text']}\n        heard: {mine}")
    rep = f"read-back word errors {wrong}/{total} ({wrong / max(total, 1):.1%}); {len(bad)} lines to listen to"
    open(os.path.join(ep, "build", "dub", "verify.txt"), "w", encoding="utf-8").write(rep + "\n" + "\n".join(bad) + "\n")
    C.say(rep, *bad[:10])
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog="pal dub", description=__doc__)
    ap.add_argument("cmd", choices=["init", "check", "voice", "verify"])
    ap.add_argument("episode")
    ap.add_argument("--to", default="en")
    ap.add_argument("--speaker")
    ap.add_argument("--engine")
    a = ap.parse_args(argv)
    return {"init": cmd_init, "check": cmd_check, "voice": cmd_voice, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
