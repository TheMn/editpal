"""Check a finished video for flash, black and frozen frames, loudness, clipping and length.

  ./pal qc <video> [--ep <ep>] [--target -16] [--json]

Prints one line per finding with its time. P0 = fix before publishing (flash frame, black over
0.5 s mid-video, clipped audio, no audio, loudness more than 1.5 LU from the target, length
differing from the A-cut); P1 = look at it. With --ep it also compares the length with
edit.json and lists seams still flagged, and writes build/review/qc.json. Exit code 1 if any P0.
The loudness target comes from channel.json (loudness.long, or loudness.short under 60 s).
"""
import argparse
import re
import subprocess

import numpy as np

import common as C

SR = 48000


def ff(cmd):
    """Run ffmpeg and return its stderr text (the filters report there)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y"] + [str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode and "Output file is empty" not in r.stderr:
        C.die("ffmpeg failed: " + " | ".join(r.stderr.strip().splitlines()[-3:]))
    return r.stderr


def video_checks(path, fps):
    """Black stretches, frozen stretches and scene changes (for flash frames) in one pass at low resolution."""
    err = ff(["-i", path, "-an", "-vf",
              "scale=320:-2,blackdetect=d=0.1:pix_th=0.1,freezedetect=n=0.001:d=1.5,select=gt(scene\\,0.3),showinfo",
              "-f", "null", "-"])
    black = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]
    freeze = []
    for m in re.finditer(r"freeze_start: ([\d.]+)", err):
        freeze.append([float(m.group(1)), None])
    for i, m in enumerate(re.finditer(r"freeze_duration: ([\d.]+)", err)):
        if i < len(freeze):
            freeze[i][1] = float(m.group(1))
    changes = [float(t) for t in re.findall(r"pts_time:([\d.]+)", err)]
    return black, freeze, changes


def audio_checks(path):
    """Loudness (ebur128), true peak, loudness range, and the number of clipped runs."""
    err = ff(["-i", path, "-vn", "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-"])
    g = lambda pat: (float(m.group(1)) if (m := re.search(pat, err.split("Summary:")[-1])) else None)
    lufs, lra, tp = g(r"I:\s+(-?[\d.]+) LUFS"), g(r"LRA:\s+(-?[\d.]+) LU"), g(r"Peak:\s+(-?[\d.]+) dBFS")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    hot = np.abs(x) >= 0.9995
    starts = np.flatnonzero(hot[:-2] & hot[1:-1] & hot[2:]) if len(x) > 3 else np.array([])
    clips = [float(t) for t in (starts[np.concatenate(([True], np.diff(starts) > 480))] / SR)] if len(starts) else []
    return lufs, lra, tp, clips, len(x) / SR


def target_for(duration, override):
    if override is not None:
        return override
    ld = C.channel().get("loudness", {})
    return float(ld.get("short", -14) if duration < 60 else ld.get("long", -16))


def run_qc(video, ep=None, target=None):
    """All findings as dicts {sev, kind, t, msg}, plus the measurements."""
    pr = C.probe(video)
    vs = next((s for s in pr["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in pr["streams"] if s["codec_type"] == "audio"), None)
    dur = float(pr["format"]["duration"])
    f = []
    add = lambda sev, kind, t, msg: f.append({"sev": sev, "kind": kind, "t": None if t is None else round(t, 3), "msg": msg})
    info = {"duration": round(dur, 3)}
    fps = 25.0
    if vs:
        n, d = (vs.get("r_frame_rate") or "25/1").split("/")
        fps = float(n) / float(d or 1)
        info["fps"] = round(fps, 3)
        black, freeze, changes = video_checks(video, fps)
        for a, b in black:
            mid = a > 0.2 and b < dur - 0.2
            if b - a > 0.5 and mid:
                add("P0", "black", a, f"black for {b - a:.2f} s")
            elif b - a > 0.1:
                add("P1", "black", a, f"black for {b - a:.2f} s (start/end or short)")
        for a, ln in freeze:
            add("P1", "frozen", a, f"picture frozen for {ln or 0:.1f} s")
        for a, b in zip(changes, changes[1:]):
            if 0 < b - a < 3 / fps - 1e-4:
                add("P0", "flash-frame", a, f"a shot only {round((b - a) * fps)} frame(s) long")
    else:
        add("P1", "no-video", None, "no video stream (audio only)")
    if not au:
        add("P0", "no-audio", None, "the file has no audio")
    else:
        lufs, lra, tp, clips, adur = audio_checks(video)
        tgt = target_for(dur, target)
        info.update({"lufs": lufs, "lra": lra, "true_peak_dbfs": tp, "target_lufs": tgt, "audio_duration": round(adur, 3)})
        if lufs is None:
            add("P1", "loudness", None, "could not measure loudness (silent?)")
        elif abs(lufs - tgt) > 1.5:
            add("P0", "loudness", None, f"{lufs:.1f} LUFS, target {tgt:g} (off by {lufs - tgt:+.1f} LU)")
        else:
            add("P1" if abs(lufs - tgt) > .8 else "info", "loudness", None, f"{lufs:.1f} LUFS (target {tgt:g}), LRA {lra} LU")
        ceil = float(C.channel().get("loudness", {}).get("true_peak", -1.5))
        if tp is not None and tp > ceil + 0.05:
            add("P1", "true-peak", None, f"true peak {tp:.1f} dBFS is above {ceil:g}")
        for t in clips[:10]:
            add("P0", "clipping", t, "audio samples at full scale (clipped)")
        if vs and abs(adur - dur) > 0.1:
            add("P1", "av-length", None, f"audio {adur:.2f} s vs video {dur:.2f} s ({(adur - dur) * 1000:+.0f} ms)")
    if ep:
        import cut as K
        e = K.load_edit(ep)
        want = K.length(e)
        if abs(want - dur) > 1.5 / fps:
            add("P0", "length", None, f"video is {dur:.2f} s, the edit says {want:.2f} s ({(dur - want) * 1000:+.0f} ms)")
        for r in e["removed"]:
            if r.get("seam", {}).get("flag") and r["kind"] != "suggest" and r.get("ok", True) is not False:
                add("P1", "seam-open", r["in"], f"{r['id']} still flagged: {r['seam']['flag']}")
    return f, info


def main(argv):
    ap = argparse.ArgumentParser(prog="qc", description=__doc__.splitlines()[0])
    ap.add_argument("video")
    ap.add_argument("--ep")
    ap.add_argument("--target", type=float)
    a = ap.parse_args(argv)
    ep = C.episode(a.ep) if a.ep else None
    f, info = run_qc(a.video, ep, a.target)
    order = {"P0": 0, "P1": 1, "info": 2}
    f.sort(key=lambda x: (order[x["sev"]], x["t"] or 0))
    lines = [f"{x['sev']:<4} {C.tc(x['t']) if x['t'] is not None else '  -  ':>7}  {x['kind']}: {x['msg']}" for x in f]
    bad = sum(1 for x in f if x["sev"] == "P0")
    C.say(f"qc {a.video}: {info.get('duration')} s, {bad} P0, {sum(1 for x in f if x['sev'] == 'P1')} P1", *lines)
    if ep:
        C.save(C.build(ep, "review", "qc.json"), {"video": a.video, "info": info, "findings": f})
    return 1 if bad else 0
