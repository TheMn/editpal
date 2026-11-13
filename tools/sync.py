"""Line up every source that has sound against the master by its audio; report drift.

    ./pal sync <ep> [--max-lag 600]

Reads sources.json (run `./pal ingest` first). For each a-roll, screen and mic source other than the
master, it cross-correlates band-limited speech (8 kHz) with the master's own sound in a window
near the start and one near the end, and writes `offset` (time in that source = master time +
offset) and `drift` (how much the offset changes from start to end, seconds) into sources.json.
When the master has no sound the audio master is the reference. Warns when drift is over 0.04 s
or the correlation peak is weak. Offsets are accurate to a few milliseconds. `--max-lag` is how
far apart (seconds) two recordings may have started.
"""
import argparse
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

SR = 8000
WINDOW = 40.0          # seconds of speech compared
WEAK = 0.25            # normalised correlation below this is not trusted
DRIFT_WARN = 0.04
SYNC_ROLES = ("a-roll", "screen", "mic")


def load8k(path):
    """Audio file -> float32 mono 8 kHz, band-limited to the speech band (150 Hz – 3.4 kHz)."""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-af", "highpass=f=150,lowpass=f=3400",
           "-ar", str(SR), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not r.stdout:
        C.die(f"ffmpeg could not read {path}: " + r.stderr.decode(errors="replace")[-200:])
    return np.frombuffer(r.stdout, dtype="<f4").copy()


def loudest(y, lo, hi, length):
    """Start (samples) of the loudest `length` window whose start lies in [lo, hi] (5 s steps)."""
    best, at = -1.0, lo
    for s in range(int(lo), int(max(lo, min(hi, len(y) - length))) + 1, 5 * SR):
        e = float(np.sqrt(np.mean(y[s: s + length] ** 2))) if len(y[s: s + length]) else 0.0
        if e > best:
            best, at = e, s
    return at


def xcorr(query, target):
    """Normalised cross-correlation of `query` along `target` (FFT).
    Returns (best index in target where the query starts, peak 0..1, second-best peak elsewhere)."""
    n, m = len(target), len(query)
    if n < m or m < SR:
        return 0, 0.0, 0.0
    size = 1 << int(np.ceil(np.log2(n + m)))
    q = query - query.mean()
    f = np.fft.rfft(target, size) * np.conj(np.fft.rfft(q, size))
    cc = np.fft.irfft(f, size)[: n - m + 1]
    csum = np.concatenate([[0.0], np.cumsum(target.astype(np.float64))])
    csq = np.concatenate([[0.0], np.cumsum(target.astype(np.float64) ** 2)])
    seg_sum = csum[m:] - csum[:-m]
    seg_var = (csq[m:] - csq[:-m]) - seg_sum ** 2 / m
    ncc = cc / (np.sqrt(np.maximum(seg_var, 1e-9)) * np.sqrt(float((q ** 2).sum()) + 1e-9))
    k = int(np.argmax(ncc))
    far = np.abs(np.arange(len(ncc)) - k) > SR // 20
    return k, float(ncc[k]), float(ncc[far].max()) if far.any() else 0.0


def measure(ref, other, a, length, max_lag):
    """Offset (other time minus reference time) from the reference window starting at sample `a`."""
    lag = int(max_lag * SR)
    t0 = max(0, a - lag)
    target = other[t0: a + length + lag]
    k, peak, second = xcorr(ref[a: a + length], target)
    return (t0 + k - a) / SR, peak, second


def measure_reverse(ref, other, length, max_lag):
    """When the reference window is not inside the other source: take the window from the other
    source and look for it in the reference. Returns the offset in the same sense."""
    a = loudest(other, 0, len(other), length)
    k, peak, second = xcorr(other[a: a + length], ref[: len(ref)])
    return (a - k) / SR, peak, second


def sync_source(ref, other, max_lag):
    """(offset, drift, peak, note) for one source against the reference array."""
    length = int(min(WINDOW, len(ref) / SR * 0.35, len(other) / SR * 0.35) * SR)
    if length < 5 * SR:
        return None, None, 0.0, "too short to compare"
    half = len(ref) // 2
    starts = loudest(ref, 0, min(180 * SR, max(0, half - length)), length)
    ends = loudest(ref, max(half, len(ref) - 180 * SR - length), len(ref) - length, length)
    o1, p1, s1 = measure(ref, other, starts, length, max_lag)
    o2, p2, s2 = measure(ref, other, ends, length, max_lag) if ends >= starts + length else (o1, p1, s1)
    if max(p1, p2) < WEAK:
        o1, p1, s1 = measure_reverse(ref, other, length, max_lag)
        return o1, 0.0, p1, "recordings only partly overlap" if p1 >= WEAK else "no match found"
    if p1 < WEAK:
        o1, p1 = o2, p2
    if p2 < WEAK:
        o2 = o1
    note = ""
    if abs(o2 - o1) > 5:
        note = "start and end disagree by seconds: check by ear"
    return round(o1, 3), round(o2 - o1, 3), round(min(p1, p2) if p2 >= WEAK else p1, 2), note


def main(argv):
    """Entry point for ./pal sync."""
    ap = argparse.ArgumentParser(prog="pal sync", description="line up sources by their sound")
    ap.add_argument("ep")
    ap.add_argument("--max-lag", type=float, default=600.0)
    a = ap.parse_args(argv)
    ep = C.episode(a.ep)
    path = os.path.join(ep, "sources.json")
    sj = C.load(path, default={})
    srcs = sj.get("sources", {})
    if not srcs:
        C.die("no sources.json yet. Run ./pal ingest <episode> first.")
    master = sj.get("master")
    ref_id = master if master and srcs[master].get("wav") else sj.get("audio_master")
    if not ref_id or not srcs.get(ref_id, {}).get("wav"):
        C.die("no source with sound to line the others up against. Is there a recording with audio?", 3)
    ref = load8k(os.path.join(ep, srcs[ref_id]["wav"]))
    rows = [f"reference: {ref_id} (offset 0)", "id        offset     drift   peak  status"]
    srcs[ref_id]["offset"], srcs[ref_id]["drift"] = 0.0, 0.0
    bad = 0
    for sid, s in srcs.items():
        if sid == ref_id or s.get("role") not in SYNC_ROLES:
            continue
        if not s.get("wav"):
            rows.append(f"{sid:<9} {'-':>7} {'-':>8} {'-':>5}  no sound: place it by hand if it must line up")
            continue
        off, drift, peak, note = sync_source(ref, load8k(os.path.join(ep, s["wav"])), a.max_lag)
        if off is None:
            rows.append(f"{sid:<9} {'-':>7} {'-':>8} {'-':>5}  {note}")
            continue
        s["offset"], s["drift"] = off, drift
        status = note or "ok"
        if peak < WEAK:
            status, bad = "WEAK match: check by ear (or --roles)", bad + 1
        elif abs(drift) > DRIFT_WARN:
            status = f"drift {drift:+.3f} s over the recording: the cut tool will warp or re-sync"
        rows.append(f"{sid:<9} {off:>+7.3f} {drift:>+8.3f} {peak:>5.2f}  {status}")
    C.save(path, sj)
    C.say(("! " if bad else "✓ ") + "sync done", *rows, "  time in a source = master time + offset")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
