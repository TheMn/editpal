"""Make or list the sound-effects palette in library/sfx/ (synthesized, deterministic, CC0).

Usage:
  ./pal sfx build [--dir <folder>]   regenerate every effect (whoosh, pop, click, riser, ...)
  ./pal sfx list                     the effects, their lengths and sizes

Writes library/sfx/<id>.mp3 (mono, 44.1 kHz, each under 60 kB). The sounds are made here from
filtered noise and short sine blips with a light reverb tail and a fixed random seed, so the
same code always gives the same files. They are released CC0; nothing is downloaded.
`./pal mix` uses them by id: {"sfx": [{"id": "whoosh", "at": 0.0}]} in a beat of plan.json.
"""
import math
import os
import sys

import numpy as np

import common

SR = 44100
OUT = os.path.join(common.ROOT, "library", "sfx")
LICENSE_LINE = "CC0"


def env(n, attack, decay_s, curve=3.0):
    """Amplitude envelope: linear attack, then exponential decay over decay_s seconds."""
    t = np.arange(n) / SR
    a = np.minimum(1.0, t / max(attack, 1e-4))
    d = np.exp(-curve * np.maximum(0.0, t - attack) / max(decay_s, 1e-3))
    return a * d


def sweep_noise(rng, dur, f0, f1, q=1.2, peak=0.5):
    """White noise through a band-pass whose centre moves from f0 to f1 Hz (state-variable filter)."""
    n = int(dur * SR)
    x = rng.standard_normal(n)
    fc = np.geomspace(f0, f1, n)
    g = 2.0 * np.sin(np.pi * np.minimum(fc, SR * 0.45) / SR)
    k = 1.0 / q
    low = band = 0.0
    out = np.empty(n)
    for i in range(n):
        low += g[i] * band
        high = x[i] - low - k * band
        band += g[i] * high
        out[i] = band
    return out * peak / (np.abs(out).max() + 1e-9)


def blip(freq, dur, shape="sine", f_end=None, decay=0.08):
    """A short tone with a fast decay; shape sine or triangle; optional pitch glide."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = freq if f_end is None else np.geomspace(freq, f_end, n)
    ph = 2 * np.pi * np.cumsum(np.broadcast_to(f, (n,))) / SR
    w = np.sin(ph) if shape == "sine" else (2 / np.pi) * np.arcsin(np.sin(ph))
    return w * env(n, 0.002, decay)


def reverb(x, rng, tail=0.35, wet=0.25):
    """Light reverb: convolve with exponentially decaying, softened noise."""
    n = int(tail * SR)
    ir = rng.standard_normal(n) * np.exp(-6.0 * np.arange(n) / n)
    ir = np.convolve(ir, np.ones(8) / 8, mode="same")   # dull the highs
    ir[0] = 0
    size = len(x) + n
    wetsig = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)
    wetsig *= np.abs(x).max() / (np.abs(wetsig).max() + 1e-9)
    dry = np.pad(x, (0, size - len(x)))
    return dry + wet * wetsig


def add(a, b, at=0.0):
    """a plus b starting `at` seconds in (b is cut if it would run past the end of a)."""
    o = int(at * SR)
    m = max(0, min(len(b), len(a) - o))
    a[o:o + m] += b[:m]
    return a


def fade_out(x, ms=30):
    n = min(len(x), int(ms / 1000 * SR))
    x = x.copy()
    x[-n:] *= np.linspace(1, 0, n)
    return x


def make(name, rng):
    """The samples (float, mono) of one effect."""
    if name == "whoosh":
        d = 0.7
        x = sweep_noise(rng, d, 300, 3500, q=1.0)
        n = len(x)
        t = np.arange(n) / n
        x *= np.sin(np.pi * t) ** 2          # swell in, swell out
        return reverb(x, rng, 0.3, 0.2) * 0.8
    if name == "whoosh-short":
        x = sweep_noise(rng, 0.28, 600, 5000, q=1.0)
        x *= np.sin(np.pi * np.arange(len(x)) / len(x)) ** 2
        return reverb(x, rng, 0.2, 0.15) * 0.7
    if name == "pop":
        x = blip(520, 0.14, "sine", f_end=180, decay=0.05)
        add(x, 0.25 * blip(1040, 0.05, "sine", f_end=400, decay=0.02))
        return reverb(x, rng, 0.15, 0.12) * 0.8
    if name == "click":
        n = int(0.05 * SR)
        x = rng.standard_normal(n) * env(n, 0.0005, 0.008)
        x = x - np.convolve(x, np.ones(6) / 6, mode="same") * 0.9    # keep the highs, then soften below
        x = np.convolve(x, np.ones(3) / 3, mode="same")
        add(x, 0.5 * blip(1800, 0.03, "sine", decay=0.008))
        return x / np.abs(x).max() * 0.6
    if name == "tick":
        x = blip(2400, 0.06, "triangle", decay=0.012)
        add(x, 0.3 * blip(4800, 0.03, "sine", decay=0.006))
        return x / np.abs(x).max() * 0.5
    if name == "impact":
        x = blip(95, 0.7, "sine", f_end=42, decay=0.22)
        n = int(0.12 * SR)
        add(x, rng.standard_normal(n) * env(n, 0.001, 0.03) * 0.15)
        return reverb(x, rng, 0.45, 0.25) * 0.9
    if name == "riser":
        d = 2.0
        x = sweep_noise(rng, d, 200, 6000, q=1.4)
        n = len(x)
        t = np.arange(n) / n
        x *= t ** 2.2
        tone = np.sin(2 * np.pi * np.cumsum(np.geomspace(220, 880, n)) / SR) * t ** 3 * 0.25
        x = x + tone
        return fade_out(x, 60) * 0.75
    if name == "sparkle":
        out = np.zeros(int(0.9 * SR))
        for i, f in enumerate([1568, 2093, 2637, 3136, 3951]):
            s = blip(f, 0.35, "sine", decay=0.12) * (0.9 - 0.12 * i)
            o = int((0.05 * i + rng.uniform(0, 0.015)) * SR)
            add(out, s, o / SR)
        return reverb(out, rng, 0.4, 0.3) * 0.35
    if name == "swipe":
        x = sweep_noise(rng, 0.22, 2500, 700, q=1.2)
        x *= np.sin(np.pi * np.arange(len(x)) / len(x)) ** 1.5
        return reverb(x, rng, 0.15, 0.12) * 0.6
    raise KeyError(name)


NAMES = ["whoosh", "whoosh-short", "pop", "click", "tick", "impact", "riser", "sparkle", "swipe"]


def write_mp3(x, path):
    """Normalise to a gentle peak, 10 ms fade-in, write mono MP3 through ffmpeg."""
    x = np.asarray(x, dtype=np.float64)
    x = x / (np.abs(x).max() + 1e-9) * 0.7
    n = int(0.003 * SR)
    x[:n] *= np.linspace(0, 1, n)
    x = fade_out(x, 20)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    import subprocess
    tmp = path + ".part.mp3"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-",
                        "-c:a", "libmp3lame", "-b:a", "96k", "-ar", str(SR), "-map_metadata", "-1",
                        "-write_xing", "0", "-id3v2_version", "0", tmp],
                       input=pcm, capture_output=True)
    if r.returncode:
        common.die("ffmpeg failed: " + r.stderr.decode()[-200:])
    os.replace(tmp, path)


def build(out=OUT):
    """Write every effect; each has its own seed so adding one never changes the others."""
    os.makedirs(out, exist_ok=True)
    for i, name in enumerate(NAMES):
        rng = np.random.default_rng(1000 + i)
        write_mp3(make(name, rng), os.path.join(out, name + ".mp3"))
    common.say(f"✓ {len(NAMES)} effects in {os.path.relpath(out, common.ROOT)}")
    return list_(out)


def list_(out=OUT):
    """Print id, length, size."""
    rows = []
    for name in NAMES:
        p = os.path.join(out, name + ".mp3")
        if os.path.exists(p):
            rows.append(f"  {name:<13} {common.duration(p):4.2f}s  {os.path.getsize(p) / 1000:4.0f} kB")
        else:
            rows.append(f"  {name:<13} missing: run ./pal sfx build")
    common.say(*rows)
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    if argv[0] == "list":
        return list_()
    if argv[0] == "build":
        out = argv[argv.index("--dir") + 1] if "--dir" in argv else OUT
        return build(out) or 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
