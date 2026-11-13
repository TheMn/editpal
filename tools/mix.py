"""The sound of a video: one music-and-effects bed, then one finished mix per language.

    ./pal mix <ep> [--lang fa,en] [--short]

Bed (build/audio/bed.wav, rendered once, 48 kHz stereo): the `music` cues of plan.json
({"track": "library:<id>" or a source id of sources.json, "t": [from, to], "gain_db": -20, "duck": true,
 optional "in": seconds into the track}; 1 s fades, looped with a crossfade when the cue is longer
than the track) plus every beat's `sfx` ({"id": "whoosh", "at": 0.0}, seconds after the beat starts;
files from library/sfx/). With no music cues the bed is effects only.
Mix per language (build/audio/mix.<lang>.wav and .m4a, AAC 192k): the voice stem (the spoken language:
build/cut/voice.wav or build/audio/voice.<lang>.wav; a dub: build/dub/voice.<lang>.wav) plus the bed.
The music is ducked under THAT language's voice (it sits `gain_db` under the voice while it speaks and
rises 6 dB in pauses longer than 1 s; effects are not ducked), then the result goes through two-pass
loudnorm to channel.json loudness (`long`, or `short` with --short; `true_peak`). The mix has the
length of the voice stem. Measured loudness and true peak are printed. Results are cached on the inputs.
"""
import argparse
import json
import os
import re
import subprocess
import sys

import numpy as np
import soundfile as sf

import common

SR = 48000
VERSION = 1
FADE = 1.0
REF_DB = -20.0         # the bed's music is levelled to this RMS; per-language gain is relative to the voice
DUCK_UP_DB = 6.0
ATTACK, RELEASE = 0.15, 0.5
GRID = 100             # gain curves are computed at 100 Hz
FX_DB = -12.0          # effects level (sfx files peak near -3 dBFS)


def decode(path, start=0.0, dur=None):
    """Any audio file -> float32 array (n, 2) at 48 kHz."""
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start)]
    if dur:
        cmd += ["-t", str(dur)]
    cmd += ["-i", path, "-vn", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        common.die(f"cannot read {path}: {r.stderr.decode()[-200:]}")
    return np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, 2).copy()


def rms_db(x):
    """RMS level in dBFS of the non-silent part of x."""
    m = np.abs(x).max(axis=1) if x.ndim > 1 else np.abs(x)
    live = x[m > 10 ** (-60 / 20)]
    if len(live) == 0:
        return -90.0
    return 10 * np.log10(np.mean(live.astype(np.float64) ** 2) + 1e-12)


def loop_to(x, n, xf):
    """Repeat x with a crossfade until it has n samples."""
    if len(x) >= n:
        return x[:n]
    xf = int(min(xf, len(x) // 4))
    out = x
    fade = np.linspace(0, 1, xf, dtype=np.float32)[:, None]
    while len(out) < n:
        out[-xf:] = out[-xf:] * (1 - fade) + x[:xf] * fade
        out = np.concatenate([out, x[xf:]])
    return out[:n]


def fades(x, secs):
    """Linear fade in and out."""
    k = min(int(secs * SR), len(x) // 2)
    if k > 0:
        ramp = np.linspace(0, 1, k, dtype=np.float32)[:, None]
        x[:k] *= ramp
        x[-k:] *= ramp[::-1]
    return x


def put(buf, x, at):
    """Add x into buf at `at` seconds (clipped to the buffer)."""
    o = int(round(at * SR))
    if o >= len(buf) or o + len(x) <= 0:
        return
    a, b = max(0, -o), min(len(x), len(buf) - o)
    buf[o + a:o + b] += x[a:b]


def track_path(ep, track):
    """Local file of a music cue's track: library:<id> or a source id of sources.json."""
    if track.startswith("library:"):
        import music
        return music.get_path(track.split(":", 1)[1])
    src = common.load(os.path.join(ep, "sources.json"), default={}).get("sources", {}).get(track)
    if not src:
        common.die(f"music track '{track}' is neither library:<id> nor a source in sources.json")
    for key in ("conform", "file"):
        p = os.path.join(ep, src.get(key, "")) if src.get(key) else ""
        if p and os.path.exists(p):
            return p
    common.die(f"source '{track}' has no file in build/: run ./pal ingest")


def sfx_path(name):
    p = os.path.join(common.ROOT, "library", "sfx", name + ".mp3")
    if not os.path.exists(p):
        common.die(f"no effect '{name}' in library/sfx/: ./pal sfx list (./pal sfx build makes them)")
    return p


def bed_key(ep, plan):
    """Hash of everything the bed depends on."""
    parts = [VERSION, plan.get("music", []), [(b.get("t"), b.get("sfx")) for b in plan.get("beats", [])]]
    for c in plan.get("music", []):
        if c["track"].startswith("library:"):
            import music
            parts.append(music.find(c["track"].split(":", 1)[1])["sha1"])
        else:
            parts.append(common.file_sha(track_path(ep, c["track"])))
    for b in plan.get("beats", []):
        for s in b.get("sfx", []):
            parts.append(common.file_sha(sfx_path(s["id"])))
    return common.sha(*parts)


def render_bed(ep, plan, dur):
    """Render the music part (levelled to REF_DB, no gain), its gain curve, and the effects part."""
    n = int(dur * SR)
    music = np.zeros((n, 2), dtype=np.float32)
    fx = np.zeros((n, 2), dtype=np.float32)
    gcurve = np.zeros(int(dur * GRID) + 2, dtype=np.float32)
    duck = np.zeros(len(gcurve), dtype=bool)
    mask = np.zeros(len(gcurve), dtype=bool)
    for c in sorted(plan.get("music", []), key=lambda c: c["t"][0]):
        a = float(c["t"][0])
        b = float(c["t"][1]) if len(c["t"]) > 1 and c["t"][1] is not None else dur
        b = min(b, dur)
        if b <= a:
            continue
        path = track_path(ep, c["track"])
        x = decode(path, start=float(c.get("in", 0)))
        x = x * np.float32(10 ** ((REF_DB - rms_db(x)) / 20))
        x = fades(loop_to(x, int((b - a) * SR), 3 * SR), FADE)
        put(music, x, a)
        i0, i1 = int(a * GRID), int(b * GRID)
        gcurve[i0:i1] = float(c.get("gain_db", -20))
        duck[i0:i1] = bool(c.get("duck", True))
        mask[i0:i1] = True
    for beat in plan.get("beats", []):
        t0 = beat.get("t", [0])[0] if beat.get("t") else None
        for s in beat.get("sfx", []):
            if t0 is None:
                continue
            x = decode(sfx_path(s["id"]))
            put(fx, x * np.float32(10 ** ((FX_DB + float(s.get("gain_db", 0))) / 20)), t0 + float(s.get("at", 0)))
    return music, fx, gcurve, duck, mask


def voice_activity(v):
    """(active bool per GRID step, speech level dBFS): pauses shorter than 1 s count as speaking."""
    mono = v.mean(axis=1).astype(np.float64)
    step = SR // GRID
    k = len(mono) // step
    rms = np.sqrt((mono[:k * step].reshape(k, step) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    thr = max(np.percentile(db, 95) - 25, -65)
    act = db > thr
    level = float(10 * np.log10(np.mean(rms[act] ** 2) + 1e-12)) if act.any() else -30.0
    i = 0
    while i < k:                      # fill pauses shorter than one second
        if act[i]:
            i += 1
            continue
        j = i
        while j < k and not act[j]:
            j += 1
        if (j - i) < GRID and i > 0 and j < k:
            act[i:j] = True
        i = j
    return act, level


def duck_curve(act, gcurve, duck, level):
    """dB gain per GRID step: gain_db under the voice while it speaks, +6 dB in long pauses; smoothed."""
    n = min(len(act), len(gcurve))
    target = np.where(act[:n], 0.0, np.where(duck[:n], DUCK_UP_DB, 0.0))
    target = target + gcurve[:n] + level - REF_DB     # music is at REF_DB; end up `gain_db` under the voice
    out = np.empty(n)
    cur = target[0] if n else 0.0
    ka, kr = np.exp(-1 / (ATTACK * GRID)), np.exp(-1 / (RELEASE * GRID))
    for i in range(n):
        k = ka if target[i] < cur else kr           # going down = ducking = attack
        cur = k * cur + (1 - k) * target[i]
        out[i] = cur
    return out


def loudnorm_pass(wav, i, tp, lra=11.0, measured=None):
    """Run ffmpeg loudnorm; returns the measurement dict (pass 1) or the output filter string for pass 2."""
    f = f"loudnorm=I={i}:TP={tp}:LRA={lra}"
    if measured:
        f += (f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
              f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
              f":offset={measured['target_offset']}:linear=true")
    return f + ":print_format=json"


def measure(path, i=-16, tp=-1.5):
    """Integrated loudness and true peak of a file (loudnorm analysis)."""
    r = common.run(["ffmpeg", "-v", "info", "-hide_banner", "-nostats", "-i", path, "-af",
                    loudnorm_pass(path, i, tp), "-f", "null", "-"])
    return json.loads(re.findall(r"\{[^{}]*\}", r.stderr)[-1])


def finish(pre_wav, out_wav, out_m4a, target, tp, dur):
    """Two-pass loudnorm in linear mode, then the AAC copy; returns the measurement of the result."""
    m = measure(pre_wav, target, tp)
    flt = loudnorm_pass(pre_wav, target, tp, measured=m)
    common.run(["ffmpeg", "-v", "info", "-hide_banner", "-nostats", "-i", pre_wav, "-af", flt + ",aresample=48000",
                "-t", f"{dur:.4f}", "-c:a", "pcm_s24le", out_wav])
    common.run(["ffmpeg", "-i", out_wav, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_m4a])
    return measure(out_wav, target, tp)


def voice_stem(ep, lang, spoken):
    """The voice file of a language, or None."""
    cands = ([("cut", "voice.wav"), ("audio", f"voice.{lang}.wav")] if lang == spoken
             else [("dub", f"voice.{lang}.wav"), ("audio", f"voice.{lang}.wav")])
    for d, f in cands:
        p = os.path.join(ep, "build", d, f)
        if os.path.exists(p):
            return p
    return None


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    ap = argparse.ArgumentParser(prog="pal mix")
    ap.add_argument("ep")
    ap.add_argument("--lang")
    ap.add_argument("--short", action="store_true")
    a = ap.parse_args(argv)
    ep = common.episode(a.ep)
    ch = common.channel()
    spoken = (common.load(os.path.join(ep, "transcript.json"), default={}).get("language")
              or ch.get("languages", {}).get("spoken", "en"))
    langs = a.lang.split(",") if a.lang else [spoken] + list(ch.get("languages", {}).get("dub", []))
    stems = {l: voice_stem(ep, l, spoken) for l in langs}
    missing = [l for l, p in stems.items() if not p]
    if missing and a.lang:
        common.die(f"no voice stem for {', '.join(missing)}: run ./pal cut render (spoken) or ./pal dub voice")
    stems = {l: p for l, p in stems.items() if p}
    if not stems:
        common.die("no voice stem found: ./pal cut render, ./pal voice script or ./pal dub voice first")
    lo = ch.get("loudness", {})
    target = float(lo.get("short" if a.short else "long", -14 if a.short else -16))
    tp = float(lo.get("true_peak", -1.5))
    plan = common.load(os.path.join(ep, "plan.json"), default={})
    outdir = common.build(ep, "audio")
    cache = common.load(os.path.join(outdir, "mix.cache.json"), default={})
    dur = max(common.duration(p) for p in stems.values())
    bkey = common.sha(bed_key(ep, plan), round(dur, 2))
    bed_ready = all(os.path.exists(os.path.join(outdir, f)) for f in ("bed.wav", "bed.music.wav", "bed.fx.wav"))
    music = fx = gcurve = duck = mask = None
    if cache.get("bed") != bkey or not bed_ready:
        music, fx, gcurve, duck, mask = render_bed(ep, plan, dur)
        gdb = np.interp(np.arange(len(music)) / SR * GRID, np.arange(len(gcurve)), gcurve)
        unducked = music * (10 ** (gdb / 20))[:, None].astype(np.float32) + fx
        sf.write(os.path.join(outdir, "bed.wav"), unducked, SR, subtype="PCM_24")
        sf.write(os.path.join(outdir, "bed.music.wav"), music, SR, subtype="FLOAT")
        sf.write(os.path.join(outdir, "bed.fx.wav"), fx, SR, subtype="FLOAT")
        np.savez(os.path.join(outdir, "bed.curves.npz"), gain=gcurve, duck=duck, mask=mask)
        cache["bed"] = bkey
        cache.pop("mix", None)
        common.save(os.path.join(outdir, "mix.cache.json"), cache)
        common.say(f"✓ bed: {len(plan.get('music', []))} music cues, "
                   f"{sum(len(b.get('sfx', [])) for b in plan.get('beats', []))} effects → build/audio/bed.wav")
    report = []
    for lang, stem in stems.items():
        key = common.sha(bkey, common.file_sha(stem), target, tp, VERSION)
        out_wav = os.path.join(outdir, f"mix.{lang}.wav")
        if cache.get("mix", {}).get(lang) == key and os.path.exists(out_wav):
            m = measure(out_wav, target, tp)
            report.append(f"= {lang}: cached, {float(m['input_i']):.1f} LUFS, true peak {float(m['input_tp']):.1f} dBTP")
            continue
        if music is None:
            music = sf.read(os.path.join(outdir, "bed.music.wav"), dtype="float32")[0]
            fx = sf.read(os.path.join(outdir, "bed.fx.wav"), dtype="float32")[0]
            z = np.load(os.path.join(outdir, "bed.curves.npz"))
            gcurve, duck, mask = z["gain"], z["duck"], z["mask"]
        v = decode(stem)
        n = int(dur * SR)
        v = np.pad(v, ((0, max(0, n - len(v))), (0, 0)))[:n]
        act, level = voice_activity(v)
        db = duck_curve(act, gcurve, duck, level)
        db = np.interp(np.arange(n) / SR * GRID, np.arange(len(db)), db)
        has = np.interp(np.arange(n) / SR * GRID, np.arange(len(gcurve)), mask.astype(float))
        mixed = v + music * (10 ** (db / 20) * (has > 0.01)).astype(np.float32)[:, None] + fx
        pre = os.path.join(outdir, f"pre.{lang}.wav")
        sf.write(pre, mixed, SR, subtype="FLOAT")
        m = finish(pre, out_wav, os.path.join(outdir, f"mix.{lang}.m4a"), target, tp, dur)
        os.remove(pre)
        cache.setdefault("mix", {})[lang] = key
        common.save(os.path.join(outdir, "mix.cache.json"), cache)
        ok = abs(float(m["input_i"]) - target) <= 1.0 and float(m["input_tp"]) <= tp + 0.1
        report.append(f"{'✓' if ok else '!'} {lang}: {float(m['input_i']):.1f} LUFS (target {target:g}), "
                      f"true peak {float(m['input_tp']):.1f} dBTP (max {tp:g}), {dur:.1f} s")
    common.say(*report)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
