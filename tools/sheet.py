"""Look at footage without watching it: contact sheets, single frames, seam strips, a seam reel.

  ./pal sheet contact <media> -o <jpg> [--every 20] [--cols 6] [--width 320]   timestamped tiles
  ./pal sheet frames <media> --at 12.5,40 -o <dir>                             single frames (jpg)
  ./pal sheet seams <ep> [--flagged] [--only C007]    one PNG per cut: 3 frames before and after the join,
                                                      the waveform across +-1.5 s, the words with their ids
  ./pal sheet reel <ep>                               one audio file: +-1.5 s around every cut, a tick between

Seam strips are written to build/review/seams/, the reel to build/review/seam-reel.m4a (+ .json mapping
reel time -> cut id). Needs build/cut/acut.mp4 (or acut-preview.mp4) and voice.wav from ./pal cut render.
"""
import argparse
import math
import os

import numpy as np
import soundfile as sf

import common as C
import cut as K

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SR = 48000


def contact(media, out, every, cols, width):
    """Tiles every `every` seconds, each stamped with its time."""
    dur = C.duration(media)
    n = max(1, int(dur // every) + 1)
    rows = math.ceil(n / cols)
    vf = (f"fps=1/{every},scale={width}:-2,drawtext=fontfile={FONT}:text='%{{pts\\:hms}}':x=6:y=h-th-6:"
          f"fontcolor=white:fontsize=18:box=1:boxcolor=black@0.6:boxborderw=3,tile={cols}x{rows}")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    C.run(["ffmpeg", "-i", media, "-vf", vf, "-frames:v", 1, "-q:v", 3, out])
    C.say(f"contact sheet: {n} tiles ({every:g} s apart) -> {out}")


def frames(media, at, outdir):
    """One jpg per time."""
    os.makedirs(outdir, exist_ok=True)
    made = []
    for t in at:
        p = os.path.join(outdir, f"frame-{t:08.2f}.jpg")
        C.run(["ffmpeg", "-ss", f"{t:.3f}", "-i", media, "-frames:v", 1, "-q:v", 2, p])
        made.append(p)
    C.say(*[f"  {p}" for p in made])


def seam_rows(ep):
    """The joins of the A-cut: edited time, the cut id between the two pieces, and the two keep ids."""
    e = K.load_edit(ep)
    rows, T = [], 0.0
    for n, (a, b) in enumerate(zip(e["keep"], e["keep"][1:]), 1):
        T += a["out"] - a["in"]
        cid = next((r["id"] for r in K.active(e) if abs(r["in"] - a["out"]) < .002 and abs(r["out"] - b["in"]) < .002), None)
        rows.append({"n": n, "t": T, "cut": cid, "before": a["id"], "after": b["id"]})
    return e, rows


def cut_video(ep):
    for n in ("acut.mp4", "acut-preview.mp4"):
        p = os.path.join(ep, "build", "cut", n)
        if os.path.exists(p):
            return p
    return None


def wave_img(x, t, half=1.5, w=960, h=110):
    """Waveform of x around time t (min/max per pixel column) with the join marked in red."""
    from PIL import Image, ImageDraw
    a, b = int((t - half) * SR), int((t + half) * SR)
    seg = np.zeros(b - a, np.float32)
    src = x[max(a, 0):max(b, 0)]
    seg[max(0, -a):max(0, -a) + len(src)] = src
    peak = max(float(np.abs(seg).max()), 1e-4)
    im = Image.new("RGB", (w, h), (24, 24, 28))
    d = ImageDraw.Draw(im)
    cols = np.array_split(seg, w)
    for i, c in enumerate(cols):
        if len(c):
            lo, hi = float(c.min()) / peak, float(c.max()) / peak
            d.line([(i, h / 2 - hi * (h / 2 - 3)), (i, h / 2 - lo * (h / 2 - 3))], fill=(120, 200, 255))
    d.line([(w // 2, 0), (w // 2, h)], fill=(255, 70, 70), width=2)
    return im


def word_line(ew, t, n=5):
    """The words just before and just after the join, with ids."""
    before = [w for w in ew if w["ee"] <= t + .05][-n:]
    after = [w for w in ew if w["es"] >= t - .05][:n]
    f = lambda ws: " ".join(f"{w['w']}[{w['id']}]" for w in ws)
    return f(before), f(after)


def seams(ep, flagged, only):
    """One strip per cut."""
    from PIL import Image, ImageDraw, ImageFont
    e, rows = seam_rows(ep)
    video = cut_video(ep)
    voice = os.path.join(ep, "build", "cut", "voice.wav")
    if not os.path.exists(voice):
        C.die("no build/cut/voice.wav. Run ./pal cut render first.", 3)
    x, _ = sf.read(voice, dtype="float32")
    rec = K.Rec(ep)
    rec.transcript()
    ew = [w for w in K.edited_words(rec, e)]
    flags = {s["n"]: s for s in C.load(os.path.join(ep, "build", "review", "seams.json"), default=[])}
    fps = rec.fps
    outdir = K.bdir(ep, "review", "seams")
    font = ImageFont.truetype(FONT, 14)
    made = []
    for r in rows:
        fl = flags.get(r["n"], {})
        if only and r["cut"] != only and f"{r['before']}|{r['after']}" != only:
            continue
        if flagged and not fl.get("flag"):
            continue
        tiles = []
        for i in range(-3, 3):
            tile = os.path.join(outdir, f".t{i}.jpg")
            if video:
                t = max(0.0, r["t"] + (i + .5) / fps)
                C.run(["ffmpeg", "-ss", f"{t:.4f}", "-i", video, "-frames:v", 1, "-vf", "scale=160:-2", "-q:v", 3, tile])
                tiles.append(Image.open(tile).convert("RGB"))
        W = 960
        tw, th = (tiles[0].size if tiles else (160, 90))
        im = Image.new("RGB", (W, th + 110 + 70), (16, 16, 18))
        d = ImageDraw.Draw(im)
        for k, ti in enumerate(tiles):
            im.paste(ti, (k * (W // 6) + (W // 6 - tw) // 2, 0))
            d.rectangle([k * (W // 6), 0, (k + 1) * (W // 6) - 1, th - 1], outline=(255, 70, 70) if k == 3 else (60, 60, 60))
        im.paste(wave_img(x, r["t"], w=W), (0, th))
        b, a = word_line(ew, r["t"])
        title = f"seam {r['n']}  {r['cut'] or r['before'] + '|' + r['after']}  at {C.tc(r['t'])}" + (f"  FLAG: {fl.get('flag')}" if fl.get("flag") else "")
        d.text((6, th + 112), title, fill=(255, 220, 120), font=font)
        d.text((6, th + 132), "before: " + b[-120:], fill=(220, 220, 220), font=font)
        d.text((6, th + 150), "after:  " + a[:120], fill=(220, 220, 220), font=font)
        p = os.path.join(outdir, f"seam-{r['n']:03d}-{r['cut'] or 'move'}.png")
        im.save(p)
        made.append(p)
    for i in range(-3, 3):
        try:
            os.remove(os.path.join(outdir, f".t{i}.jpg"))
        except OSError:
            pass
    C.say(f"{len(made)} seam strip(s) in {C.rel(ep, outdir)}/", *[f"  {os.path.basename(p)}" for p in made[:12]])


def reel(ep):
    """+-1.5 s around every join, a short tick between clips, and a json that maps reel time to cut id."""
    e, rows = seam_rows(ep)
    voice = os.path.join(ep, "build", "cut", "voice.wav")
    if not os.path.exists(voice):
        C.die("no build/cut/voice.wav. Run ./pal cut render first.", 3)
    x, _ = sf.read(voice, dtype="float32")
    tick = (0.3 * np.sin(2 * np.pi * 1000 * np.arange(int(.05 * SR)) / SR)).astype(np.float32)
    gap = np.zeros(int(.35 * SR), np.float32)
    parts, index, pos = [], [], 0.0
    for r in rows:
        a, b = max(0, int((r["t"] - 1.5) * SR)), min(len(x), int((r["t"] + 1.5) * SR))
        clip = x[a:b]
        index.append({"n": r["n"], "cut": r["cut"], "reel_start": round(pos, 3), "reel_join": round(pos + (r["t"] - a / SR), 3),
                      "edited_t": round(r["t"], 3)})
        parts += [clip, np.zeros(int(.1 * SR), np.float32), tick, gap]
        pos += (len(clip) + len(tick) + len(gap) + int(.1 * SR)) / SR
    if not parts:
        C.die("the A-cut has no joins.", 1)
    wav = C.build(ep, "review", "seam-reel.wav")
    sf.write(wav, np.concatenate(parts), SR)
    out = os.path.join(os.path.dirname(wav), "seam-reel.m4a")
    C.run(["ffmpeg", "-i", wav, "-c:a", "aac", "-b:a", "96k", out])
    os.remove(wav)
    C.save(os.path.join(os.path.dirname(out), "seam-reel.json"), index)
    C.say(f"seam reel: {len(rows)} joins, {C.tc(pos)} -> {C.rel(ep, out)} (+ seam-reel.json)")


def main(argv):
    ap = argparse.ArgumentParser(prog="sheet", description=__doc__.splitlines()[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("contact")
    p.add_argument("media")
    p.add_argument("-o", required=True)
    p.add_argument("--every", type=float, default=20)
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--width", type=int, default=320)
    p = sp.add_parser("frames")
    p.add_argument("media")
    p.add_argument("--at", required=True)
    p.add_argument("-o", required=True)
    p = sp.add_parser("seams")
    p.add_argument("ep")
    p.add_argument("--flagged", action="store_true")
    p.add_argument("--only")
    sp.add_parser("reel").add_argument("ep")
    try:
        a = ap.parse_args(argv)
    except SystemExit as x:
        return 2 if x.code else 0
    if a.cmd == "contact":
        contact(a.media, a.o, a.every, a.cols, a.width)
    elif a.cmd == "frames":
        frames(a.media, [float(t) for t in a.at.split(",")], a.o)
    elif a.cmd == "seams":
        seams(C.episode(a.ep), a.flagged, a.only)
    else:
        reel(C.episode(a.ep))
    return 0
