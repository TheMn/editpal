"""Make the A-cut: remove pauses, fillers, false starts and retakes so the recording still sounds natural.

  ./pal cut propose <ep> [--tight|--natural|--loose]   propose the cut -> edit.json, build/review/cuts.md
  ./pal cut apply <ep> <ops.json> [--by llm|creator]   apply decisions written in word ids / cut ids
  ./pal cut render <ep> [--preview] [--force]          the A-cut video, the cleaned voice (+ raw voice)
  ./pal cut verify <ep> [--transcript <json>] [--full] transcribe the A-cut again (quick model); check every seam
  ./pal cut remap <ep>                                 transcript.json on the edited timeline
  ./pal cut lock <ep>                                  picture lock (hash of the keep list)
  ./pal cut adopt <ep> <file>                          use the creator's own A-cut
  ./pal cut table <ep> [--all]                         the cut list as a table

Reads sources.json (the conform files; the audio_master carries the voice) and transcript.raw.json.
A pause is shortened toward the speaker's own rhythm (measured from the recording), never by less than
0.25 s; a cut lands at the quietest spot of the gap; no kept piece is shorter than 0.4 s.
Writes edit.json, build/review/cuts.md, build/cut/{voice.wav,voice.raw.wav,acut.mp4,acut-preview.mp4}.
Operations for apply: remove, remove_time, keep, loosen, tighten, move, protect, suggest (docs/TOOLS.md).
"""
import argparse
import bisect
import copy
import difflib
import math
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import soundfile as sf

import common as C

SR = 48000
HOP = 0.01
MIN_KEEP = 0.4
MIN_CUT = 0.25
XFADE = 0.020
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".opus")
FILLERS = {
    "en": {"um", "uh", "uhm", "umm", "uhh", "uhhh", "er", "erm", "ehm", "hmm", "hm", "mm", "mmm"},
    "fa": {"ام", "امم", "اممم", "اوم", "اووم", "اوووم", "اا", "ااا", "ا"},
}
STUTTER = {"the", "a", "an", "i", "to", "and", "of", "in", "it", "is", "that", "we", "you", "so", "but", "if",
           "و", "که", "در", "به", "از", "را", "این", "من"}
SLATE_WORDS = {"take", "scene", "slate", "rolling", "action", "clap", "recording", "ready", "testing"}
TAIL_WORDS = {"cut", "stop", "recording"}
SENT_END = ".?!؟…"
PRIORITY = ["slate", "retake", "false-start", "repeat", "off-script", "tangent", "filler", "pause"]


# ---------------------------------------------------------------- the recording

def norm(w):
    """A word reduced to its letters, for comparing takes."""
    w = w.lower().replace("ي", "ی").replace("ك", "ک")
    return "".join(ch for ch in w if ch.isalnum())


def runs(b):
    """(value, start, end) runs of a boolean array."""
    if len(b) == 0:
        return []
    idx = np.flatnonzero(np.diff(b.astype(np.int8))) + 1
    st = np.concatenate(([0], idx))
    en = np.concatenate((idx, [len(b)]))
    return [(bool(b[s]), int(s), int(e)) for s, e in zip(st, en)]


def envelope(x):
    """10 ms energy envelope in dB (smoothed over 3 frames)."""
    n = len(x) // 480
    p = np.empty(n)
    for s in range(0, n, 4000):
        blk = x[s * 480:min(n, s + 4000) * 480].astype(np.float64).reshape(-1, 480)
        p[s:s + len(blk)] = (blk ** 2).mean(1)
    ps = p.copy()
    if n > 2:
        ps[1:-1] = .25 * p[:-2] + .5 * p[1:-1] + .25 * p[2:]
    return 10 * np.log10(ps + 1e-10)


def make_quiet(env):
    """Boolean per frame: True where only room tone is heard. Returns (quiet, floor_db)."""
    valid = env[env > -90]
    floor, top = np.percentile(valid, 5), np.percentile(valid, 95)
    thr = max(min(floor + 10, top - 20), floor + 5)
    q = env < thr
    for val, fill, n in ((False, True, 3), (True, False, 6)):   # blips < 30 ms, quiet dips < 60 ms
        for v, s, e in runs(q):
            if v == val and e - s < n and s > 0 and e < len(q):
                q[s:e] = fill
    return q, float(floor)


class Rec:
    """One episode's recording: sources, words on the master timeline, energy, quiet spots."""

    def __init__(self, ep):
        self.ep = ep
        sj = C.load(os.path.join(ep, "sources.json"))
        self.src = sj.get("sources", {})
        self.fps = float(sj.get("fps") or C.fps_of(ep))
        self.master = sj.get("master") or sj.get("audio_master")
        self.vid = sj.get("audio_master") or self.master
        if self.master not in self.src or self.vid not in self.src:
            C.die("sources.json has no master source to cut. Run ./pal ingest first.", 3)
        self.voff = self.off(self.vid)
        self.has_video = not self.path(self.master).lower().endswith(AUDIO_EXT)
        self._tr = None
        self._ready = False
        dm = self.src[self.master].get("duration") or C.duration(self.path(self.master))
        dv = (self.src[self.vid].get("duration") or C.duration(self.path(self.vid))) - self.voff
        self.t_end = round(math.floor(min(dm, dv) * self.fps + 1e-6) / self.fps, 4)

    def off(self, sid):
        return 0.0 if sid == self.master else float(self.src.get(sid, {}).get("offset") or 0.0)

    def path(self, sid):
        s = self.src[sid]
        p = s.get("conform") or s.get("file")
        return p if os.path.isabs(p) else os.path.join(self.ep, p)

    def transcript(self):
        if self._tr is None:
            tr = C.load(os.path.join(self.ep, "transcript.raw.json"))
            toff = self.off(tr.get("source")) if tr.get("source") in self.src else 0.0
            self._tr = tr
            self.lang = (tr.get("language") or "en")[:2]
            self.words = [dict(id=w["id"], w=w["w"], s=w["start"] - toff, e=w["end"] - toff, p=w.get("p", 1.0),
                               tok=norm(w["w"])) for w in tr["words"]]
            self.idx = {w["id"]: i for i, w in enumerate(self.words)}
            self.sounds = [dict(kind=s["kind"], s=s["start"] - toff, e=s["end"] - toff) for s in tr.get("sounds", [])]
            self.flags = [(f["start"] - toff, f["end"] - toff, f.get("kind", "")) for f in tr.get("flags", [])]
            segs = {s.get("last") for s in tr.get("segments", [])}
            self.seg_last = {self.idx[i] for i in segs if i in self.idx}
        return self._tr

    # --- sound
    def voice_file(self):
        """The voice source decoded once to 48 kHz mono float WAV."""
        p = self.path(self.vid)
        out = os.path.join(bdir(self.ep, "cut"), "voice-src.wav")
        key = C.sha(p, os.path.getsize(p), int(os.path.getmtime(p)))
        if not (os.path.exists(out) and open(out + ".key").read() == key if os.path.exists(out + ".key") else False):
            C.run(["ffmpeg", "-i", p, "-vn", "-ac", "1", "-ar", SR, "-c:a", "pcm_f32le", out])
            open(out + ".key", "w").write(key)
        return out

    def pcm(self):
        if not hasattr(self, "x"):
            self.x, _ = sf.read(self.voice_file(), dtype="float32")
        return self.x

    def prep(self):
        """Energy, quiet spots, voiced edges of every word, gaps, and the speaker's rhythm."""
        if self._ready:
            return self
        self.transcript()
        self.env = envelope(self.pcm())
        self.quiet, self.floor = make_quiet(self.env)
        for sd in self.sounds:                       # a breath is not speech: the gap includes it
            if sd["kind"] == "breath":
                self.quiet[max(0, self.fi(sd["s"])):self.fi(sd["e"]) + 1] = True
        self.vr = [(s, e) for v, s, e in runs(self.quiet) if not v]
        self._vs = [s for s, _ in self.vr]
        W = self.words
        n = len(W)
        self.vend, self.vstart = [0.0] * n, [0.0] * n
        for i, w in enumerate(W):
            nxt = W[i + 1]["s"] if i + 1 < n else w["e"] + 1.0
            self.vstart[i] = self.v_start(w["s"], w["e"], nxt)
            self.vend[i] = self.v_end(w["e"], self.vstart[i])
        self._ready = True
        return self

    def fi(self, t):
        return int(round((t + self.voff) / HOP))

    def ft(self, i):
        return i * HOP - self.voff

    def q(self, i):
        return bool(self.quiet[min(max(i, 0), len(self.quiet) - 1)])

    def run_at(self, f):
        """Index of the voiced run containing frame f, or None."""
        k = bisect.bisect_right(self._vs, f) - 1
        return k if k >= 0 and self.vr[k][1] > f else None

    def v_start(self, s, e, nxt):
        """Where the word really starts to sound. The transcriber often stretches a word's start back over a
        pause (so the frame at `s` is the previous word's tail); then the next voiced run is the word."""
        f, lim = self.fi(s), self.fi(max(e, nxt))
        k = self.run_at(f)
        if k is not None:
            rs, re = self.vr[k]
            if rs >= f - 3:
                return self.ft(f)
            j = k + 1
            if re < self.fi(e) - 5 and j < len(self.vr) and self.vr[j][0] <= lim and self.vr[j][0] - re >= 15:
                return self.ft(self.vr[j][0])
            return self.ft(f)
        j = bisect.bisect_left(self._vs, f)
        if j < len(self.vr) and self.vr[j][0] <= lim:
            return self.ft(self.vr[j][0])
        return self.ft(f)

    def v_end(self, e, vs):
        """Where the word stops sounding: the end of the voiced run it sits in (never the next word's run)."""
        f, fs = self.fi(e), self.fi(vs)
        k = self.run_at(f)
        if k is not None and self.vr[k][0] < f - 3:
            re = self.vr[k][1]
            return self.ft(re if re - f <= 25 else f)
        j = bisect.bisect_right(self._vs, f - 1) - 1       # last run starting before e
        if k is not None and j > 0:
            j -= 1                                           # run at e belongs to the next word
        if j >= 0 and self.vr[j][1] > fs:
            return self.ft(self.vr[j][1])
        k = self.run_at(fs)
        return self.ft(self.vr[k][1]) if k is not None else self.ft(max(f, fs))

    def level(self, t0, t1):
        """Mean energy (dB) of the voice between two master times."""
        a, b = max(0, self.fi(t0)), max(1, self.fi(t1))
        return float(self.env[a:b].mean()) if b > a and a < len(self.env) else -100.0

    def place(self, t, lo, hi, span=0.06):
        """The frame-grid time near t (within [lo, hi]) where the room is quietest."""
        fr = 1 / self.fps
        lo, hi = max(lo, t - span), min(hi, t + span)
        ks = range(math.ceil(lo * self.fps - 1e-6), math.floor(hi * self.fps + 1e-6) + 1)
        if not ks:
            return round(min(max(round(t * self.fps) / self.fps, hi - 1e-9), lo + 1e-9), 4)
        best = min(ks, key=lambda k: self.level(k * fr - .02, k * fr + .02) + 30 * abs(k * fr - t))
        return round(best * fr, 4)

    # --- words
    def sent_end(self, i):
        t = self.words[i]["w"].rstrip("\"'”’)»] ")
        return i in self.seg_last or (t[-1:] in SENT_END)

    def question(self, i):
        return self.words[i]["w"].rstrip("\"'”’)»] ")[-1:] in "?؟"

    def unit_start(self, i):
        return i == 0 or self.sent_end(i - 1) or self.vstart[i] - self.vend[i - 1] >= 0.5

    def rhythm(self):
        """The speaker's own pauses: inside a sentence, between sentences, the long beat."""
        W, n = self.words, len(self.words)
        ins, bet = [], []
        for i in range(n - 1):
            g = self.vstart[i + 1] - self.vend[i]
            (bet if self.sent_end(i) else ins).append(g)
        ins = [g for g in ins if g >= .06]
        bet = [g for g in bet if g >= .1]
        m_in = float(np.median(ins)) if len(ins) >= 5 else 0.14
        m_bt = float(np.median(bet)) if len(bet) >= 5 else 0.42
        beat = float(np.percentile(bet, 80)) if len(bet) >= 8 else 1.8 * m_bt
        beat = min(max(beat, 1.3 * m_bt), 1.5)
        return {"in_sentence": round(m_in, 3), "between": round(m_bt, 3), "beat": round(beat, 3),
                "noise_floor_db": round(self.floor, 1)}

    def inside_word(self, t, margin=0.03):
        """The word whose voiced core contains time t (or None)."""
        for i, w in enumerate(self.words):
            if self.vstart[i] + margin < t < self.vend[i] - margin:
                return i
        return None


def targets(rh, mode):
    """The silence left after a cut, by context, from the speaker's own medians."""
    s = {"tight": .75, "natural": 1.0, "loose": 1.4}[mode]
    cl = lambda v, lo, hi: min(max(v, lo), hi)
    return {"in": cl(1.6 * rh["in_sentence"] * s, .22, .6), "between": cl(1.3 * rh["between"] * s, .32, .9),
            "beat": cl(rh["beat"] * s, .5, 1.4), "section_gap": max(2.2 * rh["between"], 1.5)}


def pick_k(rec, T, p, g, unit_first):
    """The pause (seconds) to leave after word p when its gap g is cut."""
    if p is not None and rec.question(p):
        return T["beat"]
    if p is not None and (rec.sent_end(p) or unit_first):
        return T["beat"] if g >= T["section_gap"] else T["between"]
    return T["in"]


def make_cut(rec, a, b, K, cs=None, ce=None):
    """The removal [r0, r1] inside the silence between voiced edges a and b, leaving about K seconds.
    cs..ce is content (a filler, a retake) that must go too. Returns (r0, r1, left) or None."""
    head = min(max(.32 * K, .06), .12)
    r0, r1 = a + K - head, b - head
    lo0, hi1 = a + .02, b - .02
    hi0 = r1 - .1
    if cs is not None:
        hi0, r0 = min(hi0, cs + .04), min(r0, cs - .02)
        r1 = max(r1, ce + .02)
    r0, r1 = max(r0, lo0), min(r1, hi1)
    if r1 - r0 < .1:
        return None
    r0 = rec.place(r0, lo0, max(lo0, hi0))
    lo1 = max(r0 + .1, (ce - .04) if ce is not None else 0)
    r1 = rec.place(r1, min(lo1, hi1), hi1)
    if r1 - r0 < .08:
        return None
    return r0, r1, round((r0 - a) + (b - r1), 3)


def subtract(spans, cut):
    """spans minus the interval cut ((a, b) pairs)."""
    out = []
    for a, b in spans:
        if cut[1] <= a or cut[0] >= b:
            out.append((a, b))
            continue
        if a < cut[0]:
            out.append((a, cut[0]))
        if cut[1] < b:
            out.append((cut[1], b))
    return out


# ---------------------------------------------------------------- edit.json

def bdir(ep, *parts):
    """<episode>/build/<parts>/ , created."""
    p = os.path.join(ep, "build", *parts)
    os.makedirs(p, exist_ok=True)
    return p


def edit_path(ep):
    return os.path.join(ep, "edit.json")


def load_edit(ep):
    e = C.load(edit_path(ep), default={})
    if not e:
        C.die("no edit.json yet. Run: ./pal cut propose <ep>", 3)
    return e


def active(e):
    return [r for r in e["removed"] if r["kind"] != "suggest" and r.get("ok", True) is not False]


def num(i):
    return int(re.sub(r"\D", "", i) or 0)


def rebuild(e, rec):
    """Derive `keep` from the active removals; keep ids and extras of old keeps where they overlap."""
    old = e.get("keep", [])
    spans = sorted((r["in"], r["out"]) for r in active(e))
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    pieces, t = [], 0.0
    for a, b in merged:
        if a > t + 1e-6:
            pieces.append((t, a))
        t = max(t, b)
    if rec.t_end - t > 1e-6:
        pieces.append((t, rec.t_end))
    used, nxt, out = set(), max([num(k["id"]) for k in old] + [0]) + 1, []
    for a, b in pieces:
        best, ov = None, 0.0
        for j, k in enumerate(old):
            o = min(b, k["out"]) - max(a, k["in"])
            if o > ov and k["id"] not in used:
                best, ov = j, o
        k = {"id": None, "src": rec.master, "in": a, "out": b, "first": None, "last": None}
        rank = None
        if best is not None:
            ok = old[best]
            used.add(ok["id"])
            k["id"], rank = ok["id"], best
            for x in ("angle", "audio_lead", "audio_tail", "section"):
                if x in ok:
                    k[x] = ok[x]
        else:
            k["id"], nxt = f"K{nxt:03d}", nxt + 1
        ids = [w["id"] for w in rec.words if a <= (w["s"] + w["e"]) / 2 < b]
        if ids:
            k["first"], k["last"] = ids[0], ids[-1]
        out.append((rank, k))
    ranks = [r for r, _ in out]
    if ranks != sorted(r for r in ranks if r is not None) and None not in ranks or \
            (old and [k["id"] for k in old] != sorted(k["id"] for k in old) and None not in ranks):
        pass
    last = -1
    order = []
    for n_, (r, k) in enumerate(out):
        last = r if r is not None else last
        order.append((last, n_, k))
    order.sort(key=lambda z: (z[0], z[1]))
    e["keep"] = [k for _, _, k in order]
    return [k for k in e["keep"] if k["out"] - k["in"] < MIN_KEEP - 2e-3]


def length(e):
    return sum(k["out"] - k["in"] for k in e["keep"])


def words_between(rec, a, b):
    return [w for w in rec.words if a <= (w["s"] + w["e"]) / 2 < b]


def short_text(s, n=110):
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 1] + "…"


def assign_ids(removed):
    """C001… for entries without an id, filling the smallest unused numbers in time order."""
    used = {num(r["id"]) for r in removed if r.get("id")}
    k = 1
    for r in sorted(removed, key=lambda r: r["in"]):
        if not r.get("id"):
            while k in used:
                k += 1
            r["id"] = f"C{k:03d}"
            used.add(k)
    removed.sort(key=lambda r: r["in"])


def table_lines(e):
    rows = ["| id | at | len | kind | by | removed text / why |", "| --- | --- | --- | --- | --- | --- |"]
    for r in e["removed"]:
        st = "" if r["kind"] == "suggest" else (" (kept)" if r.get("ok") is False else "")
        txt = (r.get("text") or "").replace("|", "/")
        why = r.get("why", "").replace("|", "/")
        rows.append(f"| {r['id']} | {C.tc(r['in'])} | {r['out'] - r['in']:.2f} | {r['kind']}{st} | {r.get('by', '')} "
                    f"| {short_text(txt, 70) + ' — ' if txt else ''}{why} |")
    return rows


def write_cuts_md(ep, e, rec):
    rows = table_lines(e)
    by = {}
    for r in active(e):
        by[r["kind"]] = by.get(r["kind"], 0) + 1
    head = [f"# A-cut: {C.tc(rec.t_end)} -> {C.tc(length(e))}", "",
            "Cuts by kind: " + (", ".join(f"{k} {v}" for k, v in sorted(by.items())) or "none"),
            f"Rhythm: {e.get('rhythm')}", ""]
    path = C.build(ep, "review", "cuts.md")
    open(path, "w", encoding="utf-8").write("\n".join(head + rows) + "\n")
    return path


def save_edit(ep, e):
    C.save(edit_path(ep), e)



# ---------------------------------------------------------------- repeats the transcript cannot see

_FB = None


def cepstra(x):
    """Speech features (10 cepstra, 32 ms window, 10 ms hop) and the level of every frame in dB."""
    global _FB
    if _FB is None:
        f = np.fft.rfftfreq(2048, 1 / SR)
        mel = lambda h: 2595 * np.log10(1 + h / 700)
        pts = 700 * (10 ** (np.linspace(mel(100), mel(6000), 34) / 2595) - 1)
        fb = np.zeros((32, len(f)))
        for i in range(32):
            a, b, c = pts[i:i + 3]
            fb[i] = np.clip(np.minimum((f - a) / (b - a), (c - f) / (c - b)), 0, None)
        _FB = (fb, np.cos(np.pi * np.outer(np.arange(1, 11), np.arange(32) + .5) / 32))
    w, h = 1536, 480
    n = (len(x) - w) // h + 1
    if n < 3:
        return None, None
    sp = np.abs(np.fft.rfft(x[np.arange(w)[None, :] + h * np.arange(n)[:, None]] * np.hanning(w), 2048)) ** 2
    return np.log(sp @ _FB[0].T + 1e-9) @ _FB[1].T, 10 * np.log10(sp.sum(1) + 1e-12)


def dtw(A, B):
    """Distance between two speech snippets: A against the start of B, time-warped (0.5x-2x), loud frames count most."""
    (fa, la), (fb, _) = A, B
    n, m = len(fa), len(fb)
    wa = np.where(la > np.percentile(la, 10) + 12, 1.0, 0.1)
    c = np.sqrt(((fa[:, None, :] - fb[None, :, :]) ** 2).mean(2)) * wa[:, None]
    D = np.full((n, m), np.inf)
    D[0, :min(m, 16)] = c[0, :min(m, 16)]
    for i in range(1, n):
        p = D[i - 1]
        best = p.copy()
        best[1:] = np.minimum(best[1:], p[:-1])
        best[2:] = np.minimum(best[2:], p[:-2])
        D[i] = c[i] + best
    lo, hi = int(.6 * n), min(m, int(1.6 * n) + 1)
    return float(D[n - 1, lo:hi].min() / wa.sum()) if hi > lo else 99.0


def audio_repeats(rec, masked_time, extra, sugg_t):
    """A phrase said, a pause, then the same phrase again (a false start or retake the transcriber merged or
    dropped): compare the sound of the phrase before each pause with the start of what follows, against
    what unrelated phrases score. Clear matches become cuts, weaker ones suggestions."""
    x, vr = rec.pcm(), rec.vr
    starts = [r for r in range(1, len(vr)) if (vr[r][0] - vr[r - 1][1]) * HOP >= .3]
    ctrl = [vr[r][0] for r in range(0, len(vr), max(1, len(vr) // 6))][:6]
    vs_t = [rec.vstart[i] for i in range(len(rec.words))]
    for r in starts:
        r -= 1
        te = vr[r][1] * HOP - rec.voff                       # master time where the phrase ends
        b0 = vr[r + 1][0] * 480
        starts_ = {round(t, 3): rec.unit_start(i) for i, t in enumerate(vs_t)}
        starts_.update({round(rec.ft(vr[k][0]), 3): k == 0 or (vr[k][0] - vr[k - 1][1]) * HOP >= .15 for k in range(max(0, r - 6), r + 1)})
        cands = sorted(t for t in starts_ if te - 3.5 <= t <= te - .5)
        fb = cepstra(x[b0:b0 + int(2.2 * SR)])
        res = []
        for ta in cands:
            if masked_time(ta, te):
                continue
            a0 = int(round((ta + rec.voff) * SR))
            fa = cepstra(x[a0:vr[r][1] * 480])
            if fa[0] is None or fb[0] is None:
                continue
            res.append((dtw(fa, fb), ta, fa, (vr[r][1] * 480 - a0) / SR))
        if not res:
            continue
        dmin = min(v[0] for v in res)
        if os.environ.get('CUT_DEBUG') and dmin < 8:
            print('  cands', [(round(v[1], 2), round(v[0], 2)) for v in res])
        near = [v for v in res if v[0] <= dmin * 1.25 + .5]
        best = next((v for v in near if starts_[round(v[1], 3)]), near[0])
        best = (best[0], best[1], te, best[3], best[2], b0)
        d, ta, tb, L, fa, b0 = best
        others = [c for c in ctrl if abs(c * HOP - ta - rec.voff) > 4 and abs(c - b0 // 480) > 200][:3]
        cd = [dtw(fa, cepstra(x[c * 480:c * 480 + int(1.6 * L * SR)])) for c in others]
        cd = [v for v in cd if v < 90]
        if not cd:
            continue
        ratio = d / float(np.median(cd))
        if os.environ.get("CUT_DEBUG"):
            print(f"  audio pair at {ta:.2f}-{tb:.2f} L={L:.2f} d={d:.2f} controls={np.round(cd, 2)} ratio={ratio:.2f}")
        j = r + 1
        while j + 1 < len(vr) and (vr[j + 1][0] - vr[j][1]) * HOP < .25:
            j += 1
        lenB = (vr[j][1] - vr[r + 1][0]) * HOP
        kind = "false-start" if L < 1.5 and L < .8 * lenB else "retake"
        why = (f"the phrase is said again after a pause (sound match {1 - ratio:.0%}); the later take is kept"
               if kind == "retake" else f"restarted: the same opening is said again after {vr[r + 1][0] * HOP - vr[r][1] * HOP:.1f} s "
               f"(sound match {1 - ratio:.0%})")
        if ratio < .65:
            extra.append({"s": ta, "e": tb, "kind": kind, "why": why})
        elif ratio < .78:
            sugg_t.append((ta, tb, "possible " + kind + ": " + why))

# ---------------------------------------------------------------- propose

def find_slate(rec, mask):
    """A leading take announcement ("take three") and a trailing "cut"/"stop recording"."""
    n = len(rec.words)
    live = [i for i in range(n) if mask[i] is None]
    units = units_of(rec, live)
    if len(units) > 1:
        u = units[0]
        toks = {rec.words[i]["tok"] for i in u}
        if len(u) <= 5 and toks & SLATE_WORDS:
            for i in u:
                mask[i] = ("slate", f"slate: “{short_text(' '.join(rec.words[j]['w'] for j in u), 40)}”")
    live = [i for i in range(n) if mask[i] is None]
    units = units_of(rec, live)
    if len(units) > 1:
        u = units[-1]
        toks = {rec.words[i]["tok"] for i in u}
        if len(u) <= 5 and toks & TAIL_WORDS:
            for i in u:
                mask[i] = ("slate", "tail: the end-of-take call")


def units_of(rec, live):
    """Runs of live words split at sentence ends and pauses of 0.5 s or more."""
    if not live:
        return []
    units = [[live[0]]]
    for p, q in zip(live, live[1:]):
        if rec.sent_end(p) or rec.vstart[q] - rec.vend[p] >= 0.5:
            units.append([])
        units[-1].append(q)
    return units


def same(a, b):
    return a == b or (min(len(a), len(b)) > 3 and difflib.SequenceMatcher(None, a, b).ratio() >= .8)


def prefix_len(A, B):
    m = 0
    while m < min(len(A), len(B)) and same(A[m], B[m]):
        m += 1
    return m


def find_cue(rec, mask, cue):
    """The channel's cue word, said alone after a flub, cancels the take before it."""
    cue = norm(cue)
    if not cue:
        return
    live = [i for i in range(len(rec.words)) if mask[i] is None]
    units = units_of(rec, live)
    for k, u in enumerate(units):
        toks = [rec.words[i]["tok"] for i in u]
        if cue not in toks:
            continue
        if len(u) <= 2 and k > 0:
            victims = units[k - 1] + u
        elif toks[-1] == cue and len(u) > 2:
            victims = u
        else:
            continue
        for i in victims:
            mask[i] = ("retake", f"flubbed take cancelled by the cue word “{cue}”")


def find_retakes(rec, mask, sugg):
    """A sentence restarted (the earlier take is a prefix of the next) or said again; keep the last take."""
    live = [i for i in range(len(rec.words)) if mask[i] is None and rec.words[i]["tok"]]
    units = units_of(rec, live)
    toks = [[rec.words[i]["tok"] for i in u] for u in units]
    u = 0
    while u < len(units) - 1:
        hit = False
        for j in (u + 1, u + 2):
            if j >= len(units) or rec.vstart[units[j][0]] - rec.vend[units[u][-1]] > 12:
                break
            A, B = toks[u], toks[j]
            m = prefix_len(A, B)
            open_end = not rec.sent_end(units[u][-1])
            victims = None
            if m >= 2 and (m == len(A) or (m >= len(A) - 1 and open_end)) and len(A) <= len(B) + 1:
                kind = "false-start" if len(A) < .8 * len(B) else "retake"
                why = (f"restarted after {len(A)} words; the next take is complete" if kind == "false-start"
                       else "same sentence said again; the later take is kept")
                victims = (units[u:j], kind, why)
            elif min(len(A), len(B)) >= 4 and difflib.SequenceMatcher(None, A, B).ratio() >= .72:
                if rec.sent_end(units[u][-1]) and not rec.sent_end(units[j][-1]) and len(B) < .8 * len(A):
                    victims = ([units[j]], "retake", "later take is cut off; the earlier complete take is kept")
                else:
                    victims = (units[u:j], "retake", "same sentence said again; the later take is kept")
            if victims:
                vu, kind, why = victims
                idxs = [i for x in vu for i in x]
                if j == u + 2 and len(units[u + 1]) > 5 and vu[0] is units[u]:
                    sugg.append((idxs[0], idxs[-1], "repeats the opening of the take two sentences later"))
                else:
                    for i in idxs:
                        mask[i] = (kind, why)
                u = j if vu[0] is units[u] else u + 1
                hit = True
                break
        if not hit:
            u += 1


def find_repeats(rec, mask):
    """The same 2-8 words said twice in a row (a stumble), or a repeated small word; the first copy goes."""
    live = [i for i in range(len(rec.words)) if mask[i] is None and rec.words[i]["tok"]]
    tk = [rec.words[i]["tok"] for i in live]
    k = 0
    while k < len(live):
        hit = None
        for n in range(8, 0, -1):
            for g in (0, 1):
                if k + 2 * n + g > len(live):
                    continue
                A, B = tk[k:k + n], tk[k + n + g:k + 2 * n + g]
                if not all(same(x, y) for x, y in zip(A, B)):
                    continue
                if n == 1 and (g or A[0] not in STUTTER):
                    continue
                if n == 2 and len(set(A)) == 1:
                    continue
                if g and not (len(tk[k + n]) <= 3 or tk[k + n] not in B):
                    continue
                hit = (n, g)
                break
            if hit:
                break
        if hit:
            n, g = hit
            for i in live[k:k + n + g]:
                mask[i] = ("repeat", f"“{short_text(' '.join(tk[k:k + n]), 40)}” said twice in a row")
            k += n + g
        else:
            k += 1


def propose(ep, mode, extra_fillers=()):
    rec = Rec(ep).prep()
    W, n = rec.words, len(rec.words)
    if not n:
        C.die("transcript.raw.json has no words. Run ./pal transcribe first.", 3)
    old = C.load(edit_path(ep), default={})
    if old.get("adopted"):
        C.die("this episode uses the creator's own A-cut (adopted); nothing to propose.", 3)
    rh = rec.rhythm()
    T = targets(rh, mode)
    fill = FILLERS.get(rec.lang, set()) | FILLERS["en"] | {norm(x) for x in extra_fillers}
    protect = old.get("protect", [])
    pspans = [(W[rec.idx[p["first"]]]["s"], W[rec.idx[p["last"]]]["e"]) for p in protect
              if p["first"] in rec.idx and p["last"] in rec.idx]
    retained = [r for r in old.get("removed", []) if r.get("by") != "tool" or r.get("ok") is False]
    mask = [None] * n
    sugg = []                                                     # (first idx, last idx, why)
    for i, w in enumerate(W):
        if w["tok"] in fill:
            mask[i] = ("filler", f"filler “{w['w'].strip(' ,.')}”")
    find_slate(rec, mask)
    find_cue(rec, mask, C.channel().get("cue_word", ""))
    find_retakes(rec, mask, sugg)
    find_repeats(rec, mask)
    for i, w in enumerate(W):                                     # protect: never cut
        if mask[i] and any(a - .01 <= w["s"] and w["e"] <= b + .01 for a, b in pspans):
            mask[i] = None
    # suspect transcript spans: ideas, not cuts
    def flagged(t0, t1):
        return next((k for a, b, k in rec.flags if a < t1 and b > t0), None)
    i = 0
    while i < n:
        if mask[i] is None:
            i += 1
            continue
        j = i
        while j + 1 < n and mask[j + 1] is not None:
            j += 1
        fk = flagged(rec.vstart[i], rec.vend[j])
        if fk:
            sugg.append((i, j, f"suspect transcript ({fk}); would be a {mask[i][0]}: {mask[i][1]}"))
            for x in range(i, j + 1):
                mask[x] = None
        i = j + 1
    ums = [dict(s, kind="filler", why="um sound") for s in rec.sounds if s["kind"] == "um" and not flagged(s["s"], s["e"])]
    sugg_t = []
    if not old.get("no_audio_repeats"):
        word_masked = lambda a, b: sum(1 for i in range(n) if mask[i] and a <= W[i]["s"] < b) >= max(
            2, .5 * sum(1 for w in W if a <= w["s"] < b))
        audio_repeats(rec, word_masked, ums, sugg_t)
        for u_ in ums:                                       # words under a sound-matched repeat go with it
            if u_["kind"] != "filler":
                for i in range(n):
                    if mask[i] is None and u_["s"] - .03 <= rec.vstart[i] and rec.vend[i] <= u_["e"] + .03 and not any(
                            a - .01 <= W[i]["s"] and W[i]["e"] <= b + .01 for a, b in pspans):
                        mask[i] = (u_["kind"], u_["why"])
        ums = [u_ for u_ in ums if u_["kind"] == "filler"] + [u_ for u_ in ums if u_["kind"] != "filler"]
    kept = [i for i in range(n) if mask[i] is None]
    cuts = []
    if not kept:
        C.die("every word would be removed; check the transcript.", 1)
    pairs = [(None, kept[0])] + list(zip(kept, kept[1:])) + [(kept[-1], None)]
    for p, q in pairs:
        a = rec.vend[p] if p is not None else 0.0
        b = rec.vstart[q] if q is not None else rec.t_end
        rem = list(range((p + 1) if p is not None else 0, q if q is not None else n))
        sm = [s for s in ums if a < (s["s"] + s["e"]) / 2 < b]
        content = bool(rem or sm)
        cs = ce = None
        if content:
            cs = min([rec.vstart[i] for i in rem] + [s["s"] for s in sm])
            ce = max([rec.vend[i] for i in rem] + [s["e"] for s in sm])
        g = b - a
        if p is None:                                           # before the first kept word
            if not content and b - .15 < .5:
                continue
            r1 = rec.place(max(b - .15, (ce or 0) + .02), (ce or 0) + .01, b - .02)
            res = (0.0, r1, round(b - r1, 3)) if r1 > .3 else None
            kind, why = "slate", "room tone / talk before the first sentence"
        elif q is None:                                         # after the last kept word
            if not content and rec.t_end - (a + .45) < .5:
                continue
            r0 = rec.place(min(a + .45, cs - .02 if cs else 1e9), a + .02, cs - .01 if cs else rec.t_end)
            res = (r0, rec.t_end, round(r0 - a, 3)) if rec.t_end - r0 > .1 else None
            kind, why = "slate", "tail after the last word"
        else:
            K = pick_k(rec, T, p, g, bool(rem) and rec.unit_start(rem[0]))
            if not content and g - K < MIN_CUT:
                continue
            res = make_cut(rec, a, b, min(K, max(g - .04, .1)), cs, ce)
            kind, why = "pause", f"{g:.2f} s pause shortened to {K:.2f} s"
        if not res:
            continue
        if content:
            whys = []
            for i in rem:
                if mask[i] and mask[i][0:2] not in whys:
                    whys.append(mask[i][0:2])
            for s_ in sm:
                whys.append((s_["kind"], s_["why"]))
            kinds = [k for k, _ in whys]
            kind = min(kinds, key=PRIORITY.index) if kinds else kind
            why = "; ".join(dict.fromkeys(w for _, w in whys)) if whys else why
        text = " ".join(W[i]["w"] for i in rem)
        if sm and not rem:
            text = "um" if sm[0]["kind"] == "filler" else "(heard, not in the transcript)"
        cuts.append({"id": None, "in": res[0], "out": res[1], "kind": kind, "text": text, "why": why, "by": "tool",
                     "ok": True, "seam": {"gap": res[2], "flag": None}})
    # protect / earlier decisions: cut only what is free
    final = []
    for c in cuts:
        spans = [(c["in"], c["out"])]
        for cut in pspans + [(r["in"], r["out"]) for r in retained]:
            spans = subtract(spans, cut)
        spans = [s for s in spans if s[1] - s[0] >= (MIN_CUT if c["kind"] == "pause" else .1)]
        if spans and (c["kind"] != "pause" or len(spans) == 1) and (spans[0] == (c["in"], c["out"]) or c["kind"] == "pause"):
            s = max(spans, key=lambda z: z[1] - z[0])
            final.append(dict(c, **{"in": s[0], "out": s[1]}))
    cuts = fix_short(rec, final)
    for fi_, la, why in sugg:
        cuts.append({"id": None, "in": rec.vstart[fi_], "out": rec.vend[la], "kind": "suggest",
                     "text": " ".join(W[i]["w"] for i in range(fi_, la + 1)), "why": why, "by": "tool",
                     "ok": True, "seam": {"gap": None, "flag": None}})
    for a_, b_, why in sugg_t:
        cuts.append({"id": None, "in": a_, "out": b_, "kind": "suggest", "text": "", "why": why, "by": "tool",
                     "ok": True, "seam": {"gap": None, "flag": None}})
    removed = retained + cuts
    assign_ids(removed)
    e = {"v": 1, "fps": rec.fps, "locked": None, "adopted": False, "mode": mode, "rhythm": rh,
         "keep": old.get("keep", []) if old and not old.get("adopted") else [], "removed": removed, "protect": protect}
    short = rebuild(e, rec)
    save_edit(ep, e)
    path = write_cuts_md(ep, e, rec)
    by = {}
    for r in active(e):
        by[r["kind"]] = by.get(r["kind"], 0) + 1
    ns = sum(1 for r in removed if r["kind"] == "suggest")
    C.say(f"A-cut proposed ({mode}): {C.tc(rec.t_end)} -> {C.tc(length(e))}  ({len(e['keep'])} pieces, {len(active(e))} cuts)",
          "  " + ", ".join(f"{k} {v}" for k, v in sorted(by.items(), key=lambda z: PRIORITY.index(z[0]))),
          f"  suggestions (not cut): {ns}" if ns else "",
          f"  rhythm: in-sentence {rh['in_sentence']} s, between {rh['between']} s, beat {rh['beat']} s, floor {rh['noise_floor_db']} dB",
          f"  pauses are shortened to: in-sentence {T['in']:.2f} s, between {T['between']:.2f} s, after a question/section {T['beat']:.2f} s",
          f"  warning: {len(short)} kept piece(s) under {MIN_KEEP} s" if short else "",
          f"  full table: {C.rel(ep, path)}   (./pal cut table {os.path.basename(ep)})")


def kind_of(a, b):
    return min([a, b], key=PRIORITY.index)


def fix_short(rec, cuts):
    """No kept piece under 0.4 s: undo the smaller adjacent pause cut, or drop the fragment."""
    cuts = sorted(cuts, key=lambda c: c["in"])
    stuck = set()
    for _ in range(200):
        pieces = [(cuts[k - 1]["out"] if k else 0.0, cuts[k]["in"] if k < len(cuts) else rec.t_end)
                  for k in range(len(cuts) + 1)]
        bad = next((k for k, (a, b) in enumerate(pieces) if 1e-6 < b - a < MIN_KEEP - 2e-3 and round(a, 3) not in stuck), None)
        if bad is None:
            break
        a, b = pieces[bad]
        left = cuts[bad - 1] if bad else None
        right = cuts[bad] if bad < len(cuts) else None
        has = bool(words_between(rec, a, b))
        pa = [c for c in (left, right) if c and c["kind"] == "pause" and c.get("by") == "tool"]
        if has and pa:
            cuts.remove(min(pa, key=lambda c: c["out"] - c["in"]))
        elif left and right and left.get("by") == "tool" and right.get("by") == "tool":
            txt = " ".join(x for x in (left["text"], " ".join(w["w"] for w in words_between(rec, a, b)), right["text"]) if x)
            left.update({"out": right["out"], "text": txt, "kind": kind_of(left["kind"], right["kind"]),
                         "why": left["why"] + "; fragment under 0.4 s dropped"})
            cuts.remove(right)
        elif left and left.get("by") == "tool":
            left["out"] = rec.t_end if not right else b
        elif right and right.get("by") == "tool":
            right["in"] = 0.0 if not left else a
        else:
            stuck.add(round(a, 3))
    return cuts


# ---------------------------------------------------------------- apply

class OpError(Exception):
    pass


def resolve(rec, wid):
    if wid not in rec.idx:
        raise OpError(f"unknown word id {wid}")
    return rec.idx[wid]


def find_removal(e, cid):
    r = next((r for r in e["removed"] if r["id"] == cid), None)
    if not r:
        raise OpError(f"unknown cut id {cid}")
    return r


def in_active(e, t):
    return any(r["in"] <= t < r["out"] for r in active(e))


def add_removal(rec, e, r0, r1, kind, why, by, text, gap=None):
    """Add a removal; pauses it overlaps are absorbed; any other overlap is an error."""
    for r in list(active(e)):
        if r["out"] > r0 - 1e-6 and r["in"] < r1 + 1e-6:
            if r["kind"] == "pause":
                r0, r1 = min(r0, r["in"]), max(r1, r["out"])
                e["removed"].remove(r)
            else:
                raise OpError(f"overlaps {r['id']} ({r['kind']} at {C.tc(r['in'])}); use keep {r['id']} first")
    for p in e.get("protect", []):
        if p["first"] in rec.idx and p["last"] in rec.idx:
            a, b = rec.words[rec.idx[p["first"]]]["s"], rec.words[rec.idx[p["last"]]]["e"]
            if r0 < b and r1 > a:
                raise OpError(f"{C.tc(r0)}-{C.tc(r1)} is inside protected {p['first']}-{p['last']} ({p.get('kind', '')})")
    e["removed"].append({"id": None, "in": r0, "out": r1, "kind": kind, "text": text, "why": why, "by": by, "ok": True,
                         "seam": {"gap": gap, "flag": None}})
    return e["removed"][-1]


def op_remove(rec, e, op, by, T):
    i0, i1 = resolve(rec, op["from"]), resolve(rec, op["to"])
    if i1 < i0:
        raise OpError(f"{op['from']} comes after {op['to']}")
    W = rec.words
    keptw = [i for i in range(len(W)) if not in_active(e, (W[i]["s"] + W[i]["e"]) / 2) or i0 <= i <= i1]
    p = max((i for i in keptw if i < i0), default=None)
    q = min((i for i in keptw if i > i1), default=None)
    a = rec.vend[p] if p is not None else 0.0
    b = rec.vstart[q] if q is not None else rec.t_end
    cs, ce = rec.vstart[i0], rec.vend[i1]
    K = pick_k(rec, T, p, b - a, rec.unit_start(i0))
    if p is None or q is None:
        r0 = 0.0 if p is None else rec.place(a + .45, a + .02, cs - .01)
        r1 = rec.t_end if q is None else rec.place(b - .15, ce + .01, b - .02)
        res = (r0, r1, 0.0)
    else:
        res = make_cut(rec, a, b, min(K, max(b - a - .04, .1)), cs, ce)
    if not res:
        raise OpError(f"cannot cut {op['from']}-{op['to']} cleanly (no silence around it)")
    text = " ".join(W[i]["w"] for i in range(i0, i1 + 1))
    add_removal(rec, e, res[0], res[1], op.get("kind", "tangent"), op.get("why", ""), by, text, res[2])


def op_remove_time(rec, e, op, by, T):
    t0, t1 = float(op["from"]), float(op["to"])
    lo, hi = rec.place(t0, max(0, t0 - .12), t0 + .12, .12), rec.place(t1, t1 - .12, min(rec.t_end, t1 + .12), .12)
    for t, name in ((lo, "start"), (hi, "end")):
        w = rec.inside_word(t)
        if w is not None:
            raise OpError(f"the {name} ({C.tc(t)}) falls inside word {rec.words[w]['id']} “{rec.words[w]['w']}”; use word ids")
    if hi - lo < .1:
        raise OpError(f"{t0}-{t1} is too short")
    text = " ".join(w["w"] for w in words_between(rec, lo, hi))
    add_removal(rec, e, lo, hi, op.get("kind", "tangent"), op.get("why", ""), by, text)


def op_edge(rec, e, op, by, sign):
    """loosen (sign -1): cut less; tighten (sign +1): cut more. Seconds split over both edges."""
    r = find_removal(e, op["id"])
    d = float(op.get("by", 0.1)) / 2
    r0, r1 = r["in"] - sign * d, r["out"] + sign * d
    if sign > 0:                                    # do not eat into a neighbouring word
        for i, w in enumerate(rec.words):
            if rec.vstart[i] < r0 + .0 and rec.vend[i] > r["in"] - 1e-6 > rec.vstart[i] - 1e-6 and False:
                pass
        for i in range(len(rec.words)):
            if rec.vend[i] <= r["in"] + 1e-6 and rec.vend[i] > r0 - .01:
                r0 = rec.vend[i] + .02
            if rec.vstart[i] >= r["out"] - 1e-6 and rec.vstart[i] < r1 + .01:
                r1 = rec.vstart[i] - .02
    r0, r1 = round(r0 * rec.fps) / rec.fps, round(r1 * rec.fps) / rec.fps
    if r1 - r0 < .08:
        e["removed"].remove(r)
        return
    r["in"], r["out"], r["by"] = round(r0, 4), round(r1, 4), by
    if r["seam"].get("gap") is not None:
        r["seam"]["gap"] = round(r["seam"]["gap"] - sign * 2 * d, 3)
    r["seam"]["flag"] = None


def apply_ops(ep, ops, by):
    rec = Rec(ep).prep()
    e = copy.deepcopy(load_edit(ep))
    if e.get("adopted"):
        C.die("adopted cut: there is nothing to apply to.", 3)
    T = targets(e["rhythm"], e.get("mode", "natural"))
    before, errs, moves, done = length(e), [], [], []
    for n, op in enumerate(ops, 1):
        try:
            k = op.get("op")
            if k == "remove":
                op_remove(rec, e, op, by, T)
            elif k == "remove_time":
                op_remove_time(rec, e, op, by, T)
            elif k == "keep":
                r = find_removal(e, op["id"])
                r["ok"], r["by"] = False, by
            elif k == "loosen":
                op_edge(rec, e, op, by, -1)
            elif k == "tighten":
                op_edge(rec, e, op, by, +1)
            elif k == "move":
                moves.append(op)
            elif k == "protect":
                a, b = resolve(rec, op["from"]), resolve(rec, op["to"])
                if any(rec.words[a]["s"] < r["out"] and rec.words[b]["e"] > r["in"] for r in active(e)):
                    raise OpError("cuts already inside that range; use keep <id> first")
                e.setdefault("protect", []).append({"first": op["from"], "last": op["to"], "kind": op.get("kind", "protect")})
            elif k == "suggest":
                a, b = resolve(rec, op["from"]), resolve(rec, op["to"])
                e["removed"].append({"id": None, "in": rec.vstart[a], "out": rec.vend[b], "kind": "suggest",
                                     "text": " ".join(w["w"] for w in rec.words[a:b + 1]), "why": op.get("why", ""),
                                     "by": by, "ok": True, "seam": {"gap": None, "flag": None}})
            else:
                raise OpError(f"unknown operation “{k}”")
            done.append(k)
        except (OpError, KeyError) as ex:
            errs.append(f"op {n} ({op.get('op')}): {ex if isinstance(ex, OpError) else 'missing field ' + str(ex)}")
    assign_ids(e["removed"])
    short = rebuild(e, rec)
    for op in moves:
        try:
            ks = {k["id"]: k for k in e["keep"]}
            if op["keep"] not in ks or op["after"] not in ks:
                raise OpError(f"unknown keep id {op['keep'] if op['keep'] not in ks else op['after']}")
            k = ks[op["keep"]]
            e["keep"].remove(k)
            e["keep"].insert(e["keep"].index(ks[op["after"]]) + 1, k)
        except OpError as ex:
            errs.append(f"move: {ex}")
    for k in short:
        errs.append(f"{k['id']} would be only {k['out'] - k['in']:.2f} s (under {MIN_KEEP} s): loosen or drop a neighbouring cut")
    if errs:
        C.say("✗ nothing was changed:", *["  " + x for x in errs])
        return 1
    e["locked"] = None
    save_edit(ep, e)
    write_cuts_md(ep, e, rec)
    C.say(f"applied {len(done)} operation(s) by {by}: {C.tc(before)} -> {C.tc(length(e))}  ({len(e['keep'])} pieces)",
          "  the unlock is automatic: run ./pal cut render, then verify, then lock")
    return 0


# ---------------------------------------------------------------- render

def tone_bed(x, env, n):
    """About 2 s of the quietest room tone, looped (crossfaded) to n samples, at -12 dB."""
    w = 200
    if len(env) <= w:
        return np.zeros(n, np.float32)
    cs = np.concatenate(([0], np.cumsum(np.maximum(env, -90))))
    i = int(np.argmin(cs[w:] - cs[:-w]))
    seg = x[i * 480:(i + w) * 480].astype(np.float32)
    seg = seg - seg.mean()
    f = 4800
    ramp = np.linspace(0, 1, f, dtype=np.float32)
    loop = seg[:-f].copy()
    loop[:f] = loop[:f] * ramp + seg[-f:] * (1 - ramp)
    reps = int(math.ceil(n / len(loop))) + 1
    return (np.tile(loop, reps)[:n] * 0.25).astype(np.float32)


def build_voice(rec, e):
    """One voice track from the kept ranges: 20 ms equal-power crossfades over a room-tone bed."""
    x, fps = rec.pcm(), rec.fps
    keeps = e["keep"]
    pos, cum = [], 0
    for k in keeps:
        pos.append(int(round(cum / fps * SR)))
        cum += int(round((k["out"] - k["in"]) * fps))
    total = int(round(cum / fps * SR))
    pos.append(total)
    J = [0]
    for i in range(1, len(keeps)):                  # audio joint: L cut uses the earlier clip's tail, J cut the later lead
        tail, lead = keeps[i - 1].get("audio_tail", 0), keeps[i].get("audio_lead", 0)
        J.append(pos[i] + int(round((tail if tail else lead) * SR)))
    J.append(total)
    h = int(XFADE * SR / 2)
    out = np.zeros(total + 2 * h, np.float32)       # index = timeline sample + h
    for i, k in enumerate(keeps):
        a, b = J[i], J[i + 1]
        lo, hi = a - (h if i else 0), b + (h if i < len(keeps) - 1 else 0)
        s0 = int(round((k["in"] + rec.voff) * SR)) + (lo - pos[i])
        idx = np.arange(s0, s0 + (hi - lo))
        clip = np.zeros(hi - lo, np.float32)
        ok = (idx >= 0) & (idx < len(x))
        clip[ok] = x[idx[ok]]
        if i:
            clip[:2 * h] *= np.sin(np.linspace(0, np.pi / 2, 2 * h, dtype=np.float32))
        if i < len(keeps) - 1:
            clip[-2 * h:] *= np.cos(np.linspace(0, np.pi / 2, 2 * h, dtype=np.float32))
        out[lo + h:hi + h] += clip
    out = out[h:h + total] + tone_bed(x, rec.env, total)
    return out, total


def run_ff(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        C.die(f"{cmd[0]} failed: " + " | ".join((r.stderr or "").strip().splitlines()[-4:]))


def render(ep, preview=False, force=False):
    rec = Rec(ep)
    e = load_edit(ep)
    if e.get("adopted"):
        C.say("adopted cut: build/cut/acut.mp4 is the creator's file; nothing to render.")
        return 0
    t0 = time.time()
    keeps, fps = e["keep"], rec.fps
    if not keeps:
        C.die("edit.json has no kept ranges.", 1)
    cutdir = bdir(ep, "cut")
    kh = C.sha(keeps, [os.path.getmtime(rec.path(rec.vid)), rec.voff])
    vpath, rawp = os.path.join(cutdir, "voice.wav"), os.path.join(cutdir, "voice.raw.wav")
    stamp = os.path.join(cutdir, "voice.key")
    nframes = sum(int(round((k["out"] - k["in"]) * fps)) for k in keeps)
    if force or not (os.path.exists(vpath) and os.path.exists(stamp) and open(stamp).read() == kh):
        rec.prep()
        out, total = build_voice(rec, e)
        sf.write(rawp, out, SR, subtype="PCM_24")
        run_ff(["ffmpeg", "-v", "error", "-y", "-i", rawp, "-af", "highpass=f=80,afftdn=nr=8:nf=-45,alimiter=limit=0.89:level=false",
                "-ar", SR, "-ac", 1, "-c:a", "pcm_s24le", vpath])
        open(stamp, "w").write(kh)
        voice = "built"
    else:
        voice = "cached"
    info = sf.info(vpath)
    a_ms = (info.frames / SR - nframes / fps) * 1000
    lines = [f"voice: {voice}, {info.frames / SR:.3f} s = sum of kept ranges {nframes / fps:.3f} s ({a_ms:+.0f} ms)"]
    if not rec.has_video:
        run_ff(["ffmpeg", "-v", "error", "-y", "-i", vpath, "-c:a", "aac", "-b:a", "192k", os.path.join(cutdir, "acut.m4a")])
        C.say(*lines, "audio only: build/cut/acut.m4a", f"time {time.time() - t0:.0f} s")
        return 0
    segdir = os.path.join(cutdir, "seg")
    os.makedirs(segdir, exist_ok=True)
    q = {"h": 540, "preset": "veryfast", "crf": 28} if preview else {"h": 0, "preset": "medium", "crf": 18}
    jobs = []
    for k in keeps:
        sid = k.get("angle") or rec.master
        p = rec.path(sid)
        n = int(round((k["out"] - k["in"]) * fps))
        ss = k["in"] + rec.off(sid)
        h = C.sha(p, os.path.getsize(p), int(os.path.getmtime(p)), round(ss, 4), n, fps, q)
        jobs.append((os.path.join(segdir, h + ".mp4"), p, ss, n))
    todo = [j for j in jobs if not os.path.exists(j[0])]

    def enc(j):
        out, p, ss, n = j
        vf = f"fps={fps}" + (f",scale=-2:{q['h']}" if q["h"] else "")
        run_ff(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(ss, 0):.4f}", "-i", p, "-frames:v", n, "-an", "-sn", "-vf", vf,
                "-c:v", "libx264", "-preset", q["preset"], "-crf", q["crf"], "-g", int(round(fps)), "-keyint_min",
                int(round(fps)), "-sc_threshold", 0, "-bf", 0, "-pix_fmt", "yuv420p", "-threads", 2, "-f", "mp4", out + ".part"])
        os.replace(out + ".part", out)

    with ThreadPoolExecutor(2) as ex:
        list(ex.map(enc, todo))
    lst = os.path.join(cutdir, "concat.txt")
    open(lst, "w").write("".join(f"file '{j[0]}'\n" for j in jobs))
    final = os.path.join(cutdir, "acut-preview.mp4" if preview else "acut.mp4")
    run_ff(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-i", vpath, "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "96k" if preview else "192k", "-movflags", "+faststart", final])
    pr = C.probe(final)
    vs = next(s for s in pr["streams"] if s["codec_type"] == "video")
    ast = next(s for s in pr["streams"] if s["codec_type"] == "audio")
    vd, ad = float(vs.get("duration") or pr["format"]["duration"]), float(ast.get("duration") or 0)
    lines.append(f"video: {C.rel(ep, final)}  {vd:.3f} s, {len(todo)} segment(s) encoded, {len(jobs) - len(todo)} cached; "
                 f"A/V length difference {(ad - vd) * 1000:+.0f} ms, video vs sum of kept {(vd - nframes / fps) * 1000:+.0f} ms")
    C.say(*lines, f"time {time.time() - t0:.0f} s")
    return 0


# ---------------------------------------------------------------- verify / remap / lock / adopt / table

def edited_words(rec, e):
    """Kept words with their times on the edited timeline, in order."""
    out, T = [], 0.0
    for k in e["keep"]:
        for w in rec.words:
            m = (w["s"] + w["e"]) / 2
            if k["in"] <= m < k["out"]:
                out.append(dict(w, es=T + max(w["s"], k["in"]) - k["in"], ee=T + min(w["e"], k["out"]) - k["in"], keep=k["id"]))
        T += k["out"] - k["in"]
    return out


def verify(ep, tfile=None, full=False):
    rec = Rec(ep).prep()
    e = load_edit(ep)
    cutdir = os.path.join(ep, "build", "cut")
    voice, raw = os.path.join(cutdir, "voice.wav"), os.path.join(cutdir, "voice.raw.wav")
    if not os.path.exists(voice):
        C.die("no build/cut/voice.wav. Run ./pal cut render first.", 3)
    tfile = tfile or os.path.join(cutdir, "voice.transcript.json")
    if not tfile.startswith(cutdir) or not os.path.exists(tfile) or os.path.getmtime(tfile) < os.path.getmtime(voice):
        if tfile.startswith(cutdir):
            r = subprocess.run([sys.executable, os.path.join(C.ROOT, "tools", "pal.py"), "transcribe", "file", voice, "-o", tfile] + ([] if full else ["--quick"]),
                               capture_output=True, text=True)
            if r.returncode:
                C.die("could not transcribe the A-cut: " + (r.stderr or r.stdout).strip()[-200:])
    act = [(norm(w["w"]), w["start"]) for w in C.load(tfile)["words"] if norm(w["w"])]
    exp = [w for w in edited_words(rec, e) if w["tok"]]
    near_ok = lambda a, b: a == b or (len(a) >= 3 and (a in b or b in a)) or difflib.SequenceMatcher(None, a, b).ratio() >= .75
    miss = set()
    for i, w in enumerate(exp):                  # is the word heard within 1.5 s of where it should be?
        heard = [t for t, st in act if abs(st - w["es"]) <= 1.5]
        cands = heard + [x + y for x, y in zip(heard, heard[1:])]
        if not any(near_ok(w["tok"], c) for c in cands):
            miss.add(i)
    seams, T = [], 0.0
    xr, _ = sf.read(raw, dtype="float32") if os.path.exists(raw) else (None, 0)
    for n, (k, k2) in enumerate(zip(e["keep"], e["keep"][1:]), 1):
        T += k["out"] - k["in"]
        flags, det = [], []
        near = [i for i in miss if abs(exp[i]["es"] - T) <= 1.0 or abs(exp[i]["ee"] - T) <= 1.0]
        if near:
            flags.append("clipped-word")
            det.append("missing/changed: " + ", ".join(f"{exp[i]['id']} “{exp[i]['w']}”" for i in near[:4]))
        if xr is not None:
            a, b = int((T - .04) * SR), int(T * SR)
            lv = lambda s: 10 * math.log10(float(np.mean(xr[max(s[0], 0):s[1]] ** 2)) + 1e-10)
            j = lv((b, b + int(.04 * SR))) - lv((a, b))
            if abs(j) > 12:
                flags.append("level-jump")
                det.append(f"{j:+.0f} dB across the join")
        sid = k2.get("angle") or rec.master
        if not rec.q(rec.fi(k["out"] - .005)) or not rec.q(rec.fi(k2["in"] + .005)):
            flags.append("mid-voice")
            det.append("a cut point is on voiced audio")
        for kk in (k, k2):
            if kk["out"] - kk["in"] < MIN_KEEP - 2e-3:
                flags.append("short-piece")
                det.append(f"{kk['id']} is {kk['out'] - kk['in']:.2f} s")
        cid = next((r["id"] for r in active(e) if abs(r["in"] - k["out"]) < .002 and abs(r["out"] - k2["in"]) < .002), None)
        seams.append({"n": n, "cut": cid, "t": round(T, 3), "before": k["id"], "after": k2["id"], "src_out": k["out"],
                      "src_in": k2["in"], "flag": flags[0] if flags else None, "flags": flags, "detail": "; ".join(det)})
    for r in e["removed"]:
        s = next((s for s in seams if s["cut"] == r["id"]), None)
        r.setdefault("seam", {})["flag"] = s["flag"] if s else None
    save_edit(ep, e)
    C.save(C.build(ep, "review", "seams.json"), seams)
    bad = [s for s in seams if s["flag"]]
    C.say(f"{len(seams)} seams checked, {len(bad)} flagged; {len(miss)} of {len(exp)} kept words missing or changed in the A-cut",
          *[f"  seam {s['n']} {s['cut'] or s['before'] + '|' + s['after']} at {C.tc(s['t'])}: {', '.join(s['flags'])} {s['detail']}" for s in bad[:20]])
    return 1 if any(s["flag"] == "clipped-word" for s in seams) else 0


def segments_of(words, gap=0.7):
    """Rebuild sentence segments from edited words."""
    segs, cur = [], []
    for w in words:
        if cur and (cur[-1]["_end"] or w["start"] - cur[-1]["end"] >= gap):
            segs.append(cur)
            cur = []
        cur.append(w)
    if cur:
        segs.append(cur)
    return [{"id": f"s{n}", "start": s[0]["start"], "end": s[-1]["end"], "first": s[0]["id"], "last": s[-1]["id"],
             "text": " ".join(w["w"] for w in s)} for n, s in enumerate(segs, 1)]


def remap(ep):
    rec = Rec(ep).prep()
    e = load_edit(ep)
    tr = C.load(os.path.join(ep, "transcript.raw.json"))
    ew = edited_words(rec, e)
    words = []
    for w in ew:
        src = next(x for x in tr["words"] if x["id"] == w["id"])
        words.append(dict(id=w["id"], w=w["w"], start=round(w["es"], 3), end=round(w["ee"], 3), p=src.get("p", 1.0),
                          _end=rec.sent_end(rec.idx[w["id"]])))
    segs = segments_of(words)
    for w in words:
        w.pop("_end")
    sounds, T = [], 0.0
    for k in e["keep"]:
        for s in tr.get("sounds", []):
            if k["in"] <= (s["start"] + s["end"]) / 2 - rec.off(tr.get("source")) < k["out"]:
                sounds.append(dict(s, start=round(T + s["start"] - k["in"], 3), end=round(T + s["end"] - k["in"], 3)))
        T += k["out"] - k["in"]
    out = dict(tr, timeline="edited", duration=round(length(e), 3), words=words, segments=segs, sounds=sounds, flags=[])
    C.save(os.path.join(ep, "transcript.json"), out)
    C.say(f"transcript.json: {len(words)} words in {len(segs)} segments on the edited timeline ({C.tc(length(e))})")


def lock(ep):
    e = load_edit(ep)
    e["locked"] = C.sha(e["keep"])
    save_edit(ep, e)
    C.say(f"picture lock: {e['locked']}  ({len(e['keep'])} pieces, {C.tc(length(e))}). Any later cut clears it.")


def adopt(ep, f):
    """Conform the creator's own A-cut to build/cut/acut.mp4 + voice.wav; edit.json says adopted."""
    if not os.path.exists(f):
        C.die(f"no such file: {f}", 2)
    fps = C.fps_of(ep)
    d = bdir(ep, "cut")
    has_v = any(s["codec_type"] == "video" and s.get("codec_name") not in ("mjpeg", "png") for s in C.probe(f)["streams"])
    run_ff(["ffmpeg", "-v", "error", "-y", "-i", f, "-vn", "-ac", 1, "-ar", SR, "-c:a", "pcm_s24le", os.path.join(d, "voice.wav")])
    if has_v:
        run_ff(["ffmpeg", "-v", "error", "-y", "-i", f, "-i", os.path.join(d, "voice.wav"), "-map", "0:v:0", "-map", "1:a", "-vf", f"fps={fps}",
                "-c:v", "libx264", "-crf", 18, "-g", int(fps), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", os.path.join(d, "acut.mp4")])
    dur = sf.info(os.path.join(d, "voice.wav")).frames / SR
    e = {"v": 1, "fps": fps, "locked": None, "adopted": True, "rhythm": {}, "removed": [], "protect": [],
         "keep": [{"id": "K001", "src": "adopted", "in": 0.0, "out": round(dur, 3), "first": None, "last": None}]}
    save_edit(ep, e)
    C.say(f"adopted {os.path.basename(f)}: {C.tc(dur)}. build/cut/acut.mp4 and voice.wav are ready.",
          "next: ./pal ingest, ./pal transcribe, then ./pal cut remap (the adopted file is the master: its words are the edited transcript)")


def table(ep, show_all):
    e = load_edit(ep)
    rows = table_lines(e)
    if not show_all and len(rows) > 28:
        C.say(*rows[:28], f"… {len(rows) - 28} more rows: build/review/cuts.md (or --all)")
    else:
        C.say(*rows, limit=10 ** 6 if show_all else 30)


def main(argv):
    ap = argparse.ArgumentParser(prog="cut", description=__doc__.splitlines()[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("propose")
    p.add_argument("ep")
    g = p.add_mutually_exclusive_group()
    for m in ("tight", "natural", "loose"):
        g.add_argument("--" + m, dest="mode", action="store_const", const=m)
    p = sp.add_parser("apply")
    p.add_argument("ep")
    p.add_argument("ops")
    p.add_argument("--by", default="llm", choices=["llm", "creator"])
    p = sp.add_parser("render")
    p.add_argument("ep")
    p.add_argument("--preview", action="store_true")
    p.add_argument("--force", action="store_true")
    p = sp.add_parser("verify")
    p.add_argument("ep")
    p.add_argument("--transcript")
    p.add_argument("--full", action="store_true", help="use the accurate (slow) model instead of the quick one")
    for c in ("remap", "lock"):
        sp.add_parser(c).add_argument("ep")
    p = sp.add_parser("adopt")
    p.add_argument("ep")
    p.add_argument("file")
    p = sp.add_parser("table")
    p.add_argument("ep")
    p.add_argument("--all", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit as x:
        return 2 if x.code else 0
    ep = C.episode(a.ep)
    if a.cmd == "propose":
        propose(ep, a.mode or "natural", C.channel().get("fillers", []))
    elif a.cmd == "apply":
        return apply_ops(ep, C.load(a.ops), a.by)
    elif a.cmd == "render":
        return render(ep, a.preview, a.force)
    elif a.cmd == "verify":
        return verify(ep, a.transcript, a.full)
    elif a.cmd == "remap":
        remap(ep)
    elif a.cmd == "lock":
        lock(ep)
    elif a.cmd == "adopt":
        adopt(ep, a.file)
    elif a.cmd == "table":
        table(ep, a.all)
    return 0
