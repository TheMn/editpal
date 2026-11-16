"""The picture: plates, B-roll, zoom-ins, hidden areas and captions laid over the A-cut.

Usage:
  ./pal composite <ep> --draft [--range a-b] [--lang xx]   small copy with timecode and beat ids burned in
  ./pal composite <ep> --final [--range a-b] [--lang xx]   full resolution, clean, one audio file per language
  --range a-b   only that span in seconds (the pilot, 30-60 s) -> build/out/pilot.mp4
  --jobs N      pieces rendered at the same time (default and maximum 2)

Writes build/out/draft.mp4, or build/out/<slug>.mp4 and <slug>.<lang>.m4a, or build/out/pilot.mp4.
The video is rendered in pieces of about a minute (cut at a seam of the A-cut when there is one)
and every piece is remembered: change one plate and only its piece is rendered again.
Inputs: build/cut/acut.mp4 (none = a plain frame, for generated videos), plan.json,
build/plates/<id>.<lang>.mov|mp4, sources.json (B-roll), subs/<lang>.srt (when captions burn),
build/audio/mix.<lang>.wav (falls back to build/cut/voice.wav).
"""
import argparse
import concurrent.futures as cf
import glob
import os
import re
import subprocess
import sys
import time

import board
import common

VERSION = 1
PIECE = 60.0
DARK = "1c1c20"
FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# ---------------------------------------------------------------- inputs

def frame_md():
    """Colours and font families from brand/frame.md (light parse; any part may be missing)."""
    p = os.path.join(common.ROOT, "brand", "frame.md")
    txt = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    g = re.search(r'ground:\s*"?#([0-9A-Fa-f]{6})', txt)
    lat = re.search(r"latin:\s*\n(?:.*\n)*?\s+family:\s*(\S+)", txt)
    per = re.search(r"persian:\s*\n(?:.*\n)*?\s+family:\s*(\S+)", txt)
    return {"ground": g.group(1) if g else DARK, "latin": lat.group(1) if lat else "DejaVu Sans",
            "persian": per.group(1) if per else "Vazirmatn"}


def parse_srt(path):
    """[(start, end, text)] from an .srt file."""
    out = []
    if not os.path.exists(path):
        return out
    for block in re.split(r"\n\s*\n", open(path, encoding="utf-8-sig").read().strip()):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", block)
        if m:
            g = [int(x) for x in m.groups()]
            a, b = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
            out.append((a, b, "\n".join(block[m.end():].strip("\n").splitlines())))
    return out


def srt_time(t):
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d},{int(round(t % 1 * 1000)) % 1000:03d}"


def find_plate(E, plate, lang, graphics):
    """File of a plate: the language's, else the graphics language's, else any."""
    pid = plate.get("id")
    langs = [lang, graphics, "en"]
    for lg in [x for x in langs if x and x != "per-language"]:
        for ext in ("mov", "mp4"):
            p = E.p("build/plates", f"{pid}.{lg}.{ext}")
            if os.path.exists(p):
                return p
    for ext in ("mov", "mp4"):
        for p in sorted(glob.glob(E.p("build/plates", f"{pid}.*{ext}")) + glob.glob(E.p("build/plates", f"{pid}.{ext}"))):
            return p
    idx = E.j("build/plates/index.json") or {}
    ent = idx.get(pid) if isinstance(idx, dict) else None
    if isinstance(ent, dict) and ent.get("file") and os.path.exists(E.p(ent["file"])):
        return E.p(ent["file"])
    return None


def stamp(path):
    st = os.stat(path)
    return [os.path.basename(path), st.st_size, st.st_mtime_ns]


# ---------------------------------------------------------------- pieces

def seams_of(E):
    """A-cut times where one kept range ends and the next begins."""
    t, out = 0.0, []
    for k in (E.edit or {}).get("keep", [])[:-1]:
        t += k["out"] - k["in"]
        out.append(t)
    return out


def split_pieces(a, b, seams, fps):
    """Cut [a, b) into pieces near PIECE seconds, preferring a seam within +-20 % of the target."""
    cuts, t = [], a
    while b - t > PIECE * 1.5:
        want = t + PIECE
        near = [s for s in seams if abs(s - want) <= PIECE * 0.2 and s > t + 5]
        nxt = min(near, key=lambda s: abs(s - want)) if near else want
        nxt = common.snap(nxt, fps)
        cuts.append((t, nxt))
        t = nxt
    cuts.append((t, b))
    return cuts


def zoom_expr(punches, c0):
    """Expressions (scale factor, centre x, centre y) of t for the zoom-ins in a piece."""
    z, cx, cy = "1", "0.5", "0.4"
    for a, b, s, c in reversed(punches):
        a, b = a - c0, b - c0
        u = f"clip(min((t-{a:.3f})/0.3,({b:.3f}-t)/0.3),0,1)"
        z = f"({z}+({s}-1)*{u}*{u}*(3-2*{u}))"
        cx = f"if(between(t,{a:.3f},{b:.3f}),{c[0]},{cx})"
        cy = f"if(between(t,{a:.3f},{b:.3f}),{c[1]},{cy})"
    return z, cx, cy


def esc_path(p):
    """A path inside a filter option."""
    return p.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def build_piece(ctx, i, c0, c1):
    """Describe one piece: its ffmpeg inputs, filtergraph and a hash of everything that touches it."""
    E, W, H, fps, draft = ctx["E"], ctx["W"], ctx["H"], ctx["fps"], ctx["draft"]
    n = round((c1 - c0) * fps)
    ln = n / fps
    inputs, chains, warn = [], [], []
    if ctx["acut"]:
        inputs += ["-ss", f"{c0:.4f}", "-t", f"{ln:.4f}", "-i", ctx["acut"]]
        chains.append(f"[0:v]setpts=PTS-STARTPTS,fps={fps:g},scale={W}:{H}:flags=bicubic,setsar=1[v0]")
    else:
        inputs += ["-f", "lavfi", "-i", f"color=c=0x{ctx['ground']}:s={W}x{H}:r={fps:g}:d={ln:.4f}"]
        chains.append("[0:v]setsar=1[v0]")
    cur, nin = "v0", 1
    hit = [b for b in ctx["beats"] if b["_t"] and b["_t"][0] < c1 and b["_t"][1] > c0]
    punches = [(max(b["_t"][0], c0), min(b["_t"][1], c1), (b.get("punch") or {}).get("scale", 1.15),
                (b.get("punch") or {}).get("center") or (0.5, 0.4)) for b in hit if b.get("layout") == "punch"]
    stamps = []
    if punches:
        z, cx, cy = zoom_expr(punches, c0)
        chains.append(f"[{cur}]scale=w='trunc(iw*{z}/2)*2':h='trunc(ih*{z}/2)*2':eval=frame:flags=bicubic,"
                      f"crop={W}:{H}:x='clip(({cx})*iw-{W}/2,0,iw-{W})':y='clip(({cy})*ih-{H}/2,0,ih-{H})'[vp]")
        cur = "vp"
    for j, r in enumerate(r for r in ctx["redact"] if r["t"][0] < c1 and r["t"][1] > c0):
        x, y, w, h = r["rect"]
        px, py, pw, ph = (int(x * W) // 2 * 2, int(y * H) // 2 * 2, max(2, int(w * W) // 2 * 2), max(2, int(h * H) // 2 * 2))
        rad = max(1, min(pw, ph) // 8)
        a, b = max(r["t"][0], c0) - c0, min(r["t"][1], c1) - c0
        chains.append(f"[{cur}]split[ra{j}][rb{j}];[rb{j}]crop={pw}:{ph}:{px}:{py},boxblur={rad}:3[rc{j}];"
                      f"[ra{j}][rc{j}]overlay={px}:{py}:enable='between(t,{a:.3f},{b:.3f})'[vr{j}]")
        cur = f"vr{j}"
    # B-roll covers the picture; plates replace it or sit over it (in plan order: later on top)
    for b in sorted(hit, key=lambda b: (b.get("layout") in ("over", "lower-third"), b["_t"][0])):
        lay = b.get("layout")
        a, e = max(b["_t"][0], c0), min(b["_t"][1], c1)
        if lay == "b-roll":
            br = b.get("broll") or {}
            src = ((ctx["sources"].get("sources") or {}).get(br.get("src")) or {})
            f = src.get("conform") or src.get("file")
            f = E.p(f) if f else None
            if not f or not os.path.exists(f):
                warn.append(f"{b['id']}: B-roll file for '{br.get('src')}' not found; the speaker stays on screen")
                continue
            inputs += ["-ss", f"{br.get('in', 0) + (a - b['_t'][0]):.4f}", "-t", f"{e - a:.4f}", "-i", f]
            stamps.append(stamp(f))
            chains.append(f"[{nin}:v]fps={fps:g},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
                          f"setpts=PTS-STARTPTS+{a - c0:.4f}/TB[bv{nin}]")
        elif b.get("plate") and lay in ("full", "pip", "split", "card", "over", "lower-third"):
            f = find_plate(E, b["plate"], ctx["lang"], ctx["graphics"])
            if not f:
                warn.append(f"{b['id']}: plate {b['plate'].get('id')} not rendered yet (./pal plates render)")
                continue
            inputs += ["-ss", f"{a - b['_t'][0]:.4f}", "-t", f"{e - a:.4f}", "-i", f]
            stamps.append(stamp(f))
            chains.append(f"[{nin}:v]fps={fps:g},scale={W}:{H},setsar=1,setpts=PTS-STARTPTS+{a - c0:.4f}/TB[bv{nin}]")
        else:
            continue
        chains.append(f"[{cur}][bv{nin}]overlay=0:0:eof_action=pass:format=auto:enable='between(t,{a - c0:.3f},{e - c0:.3f})'[vo{nin}]")
        cur = f"vo{nin}"
        nin += 1
    srt_body = ""
    if ctx["captions"]:
        cues = [(max(a, c0) - c0, min(b, c1) - c0, t) for a, b, t in ctx["captions"] if a < c1 and b > c0]
        if cues:
            sp = os.path.join(ctx["work"], f"cap-{ctx['mode']}-{i:03d}.srt")
            srt_body = "".join(f"{k + 1}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n" for k, (a, b, t) in enumerate(cues))
            open(sp, "w", encoding="utf-8").write(srt_body)
            fn = ctx["font_name"]
            style = (f"FontName={fn},FontSize={max(10, round(H * 0.052))},PrimaryColour=&HFFFFFF&,OutlineColour=&H202020&,"
                     f"BorderStyle=1,Outline={max(1, round(H / 270))},Shadow=0,Alignment=2,MarginV={round(H * 0.07)},Bold=1")
            chains.append(f"[{cur}]subtitles=filename='{esc_path(sp)}':fontsdir='{esc_path(ctx['fonts'])}':original_size={W}x{H}:force_style='{style}'[vc]")
            cur = "vc"
    if draft:
        fs = max(12, H // 36)
        base = f"fontfile='{esc_path(ctx['font'])}':fontsize={fs}:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=4"
        t0 = c0
        tcs = f"{int(t0 // 3600):02d}\\:{int(t0 % 3600 // 60):02d}\\:{int(t0 % 60):02d}\\:{int(round(t0 % 1 * fps)) % int(round(fps)):02d}"
        chains.append(f"[{cur}]drawtext={base}:timecode='{tcs}':rate={fps:g}:x=10:y=10[vt]")
        cur = "vt"
        for k, b in enumerate(hit):
            a, e = max(b["_t"][0], c0) - c0, min(b["_t"][1], c1) - c0
            chains.append(f"[{cur}]drawtext={base}:text='{b['id']}':x=w-tw-10:y=10+{k % 2}*{fs + 12}:enable='between(t,{a:.3f},{e:.3f})'[vb{k}]")
            cur = f"vb{k}"
    chains.append(f"[{cur}]format=yuv420p[out]")
    key = common.sha([VERSION, ctx["mode"], W, H, fps, c0, c1, ctx["acut_stamp"], ctx["ground"], inputs, chains, stamps, srt_body, ctx["bar"]])
    return {"i": i, "c0": c0, "c1": c1, "n": n, "inputs": inputs, "graph": ";".join(chains), "key": key, "warn": warn}


def render_piece(ctx, pc):
    """Run ffmpeg for one piece unless its cached file exists. Returns (path, reused)."""
    out = os.path.join(ctx["chunks"], f"{ctx['mode']}-{pc['i']:03d}-{pc['key']}.mp4")
    if os.path.exists(out):
        return out, True
    for old in glob.glob(os.path.join(ctx["chunks"], f"{ctx['mode']}-{pc['i']:03d}-*.mp4")):
        os.remove(old)
    gp = out + ".graph"
    open(gp, "w").write(pc["graph"])
    fps = ctx["fps"]
    enc = (["-preset", "veryfast", "-crf", "23"] if ctx["draft"] else ["-preset", "slow", "-crf", "17"])
    cmd = (["ffmpeg", "-v", "error", "-y", "-threads", "2"] + pc["inputs"] + ["-filter_complex_script", gp, "-map", "[out]",
           "-frames:v", str(pc["n"]), "-an", "-c:v", "libx264"] + enc +
           ["-g", str(round(fps)), "-keyint_min", str(round(fps)), "-sc_threshold", "0", "-x264-params", "open-gop=0",
            "-r", f"{fps:g}", "-pix_fmt", "yuv420p", out + ".part.mp4"])
    r = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(gp)
    if r.returncode != 0:
        raise RuntimeError(f"piece {pc['i']} ({common.tc(pc['c0'])}-{common.tc(pc['c1'])}): " + " | ".join(r.stderr.strip().splitlines()[-4:]))
    os.replace(out + ".part.mp4", out)
    return out, False


# ---------------------------------------------------------------- main

def pick_audio(E, lang):
    """Audio for a language's mix: mix.<lang>.wav, else the cleaned voice, else the A-cut's own sound."""
    for f in (f"build/audio/mix.{lang}.wav", "build/cut/voice.wav", "build/cut/acut.mp4"):
        if E.has(f):
            return E.p(f), f.startswith("build/audio")
    return None, False


def main(argv):
    ap = argparse.ArgumentParser(prog="composite", add_help=False)
    ap.add_argument("ep")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--range")
    ap.add_argument("--lang")
    ap.add_argument("--jobs", type=int, default=2)
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    if a.draft == a.final:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    t_start = time.time()
    E = board.Ep(common.episode(a.ep))
    ch = E.ch
    spoken = (ch.get("languages") or {}).get("spoken", "en")
    lang = a.lang or spoken
    graphics = (ch.get("languages") or {}).get("graphics", "en")
    plan = E.plan or {}
    acut = E.p("build/cut/acut.mp4") if E.has("build/cut/acut.mp4") else None
    if not acut and not (E.sources and E.sources.get("master") is None) and plan.get("mode") != "project":
        common.die(f"no A-cut (build/cut/acut.mp4). Make it with ./pal cut render {E.slug}", 3)
    fps = common.fps_of(E.ep)
    if acut:
        vs = next(s for s in common.probe(acut)["streams"] if s["codec_type"] == "video")
        SW, SH = int(vs["width"]), int(vs["height"])
    else:
        SW, SH = (E.sources or {}).get("size") or [1920, 1080]
    if a.draft:
        H = min(int((ch.get("video") or {}).get("draft_height", 1080)), SH)
        W = round(SW * H / SH / 2) * 2
        H = H // 2 * 2
    else:
        W, H = SW, SH
    audio, _ = pick_audio(E, lang)
    if acut:
        total = common.duration(acut)
    elif audio:
        total = common.duration(audio)
    else:
        total = max([(E.beat_t(b) or [0, 0])[1] for b in plan.get("beats", [])] + [(E.tr or {}).get("duration", 0), 1.0])
    r0, r1 = 0.0, total
    if a.range:
        m = re.match(r"^([\d.]+)-([\d.]+)$", a.range)
        if not m:
            common.die("--range wants seconds like 0-30", 2)
        r0, r1 = common.snap(float(m[1]), fps), min(total, common.snap(float(m[2]), fps))
        if r1 <= r0:
            common.die("--range is empty (the video is %.1f s long)" % total, 2)
    r1 = r0 + int(round((r1 - r0) * fps)) / fps
    beats = []
    for b in plan.get("beats", []):
        b = dict(b)
        b["_t"] = E.beat_t(b)
        if not b["_t"]:
            common.say(f"! {b['id']} has no time yet (./pal plates time {E.slug}); skipped")
            continue
        beats.append(b)
    fm = frame_md()
    cap_on = bool((plan.get("captions") or {}).get("burn"))
    srt = E.p("subs", f"{lang}.srt")
    if cap_on and not os.path.exists(srt):
        common.say(f"! captions should burn but subs/{lang}.srt is missing (./pal subs make {E.slug}); none burned")
    font_name = fm["persian"] if lang in ("fa", "ar") else fm["latin"]
    mono = os.path.join(common.ROOT, "brand", "fonts", "JetBrainsMono-Bold.ttf")
    ctx = {"E": E, "W": W, "H": H, "fps": fps, "draft": a.draft, "mode": "draft" if a.draft else "final", "acut": acut,
           "acut_stamp": stamp(acut) if acut else None, "ground": fm["ground"], "beats": beats, "redact": plan.get("redact", []),
           "sources": E.sources or {}, "lang": lang, "graphics": graphics, "bar": 0,
           "captions": parse_srt(srt) if cap_on else [], "font_name": font_name,
           "fonts": os.path.join(common.ROOT, "brand", "fonts"), "font": mono if os.path.exists(mono) else FALLBACK_FONT,
           "chunks": common.build(E.ep, "chunks"), "work": common.build(E.ep, "chunks")}
    pieces = [build_piece(ctx, i, c0, c1) for i, (c0, c1) in enumerate(split_pieces(r0, r1, seams_of(E), fps))]
    for pc in pieces:
        for w in pc["warn"]:
            common.say("! " + w)
    jobs = max(1, min(2, a.jobs))
    done = {}
    try:
        with cf.ThreadPoolExecutor(jobs) as ex:
            futs = {ex.submit(render_piece, ctx, pc): pc for pc in pieces}
            for f in cf.as_completed(futs):
                done[futs[f]["i"]] = f.result()
    except RuntimeError as e:
        common.die(str(e))
    reused = sum(1 for _, r in done.values() if r)
    outdir = common.build(E.ep, "out")
    name = "pilot.mp4" if a.range else ("draft.mp4" if a.draft else f"{E.slug}.mp4")
    out = os.path.join(outdir, name)
    lst = os.path.join(ctx["chunks"], f"{ctx['mode']}.txt")
    open(lst, "w").write("".join(f"file '{done[i][0]}'\n" for i in range(len(pieces))))
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst]
    extra_audio = []
    if audio:
        cmd += ["-ss", f"{r0:.4f}", "-t", f"{r1 - r0:.4f}", "-i", audio]
        cmd += ["-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    else:
        cmd += ["-map", "0:v", "-c:v", "copy"]
        common.say("! no audio found (build/audio/mix.%s.wav or build/cut/voice.wav): the video is silent" % lang)
    if a.final and not a.range:
        cmd += ["-movflags", "+faststart"]
    common.run(cmd + [out + ".part.mp4"])
    os.replace(out + ".part.mp4", out)
    if a.final and not a.range:
        for lg in [x for x in dict.fromkeys([spoken, lang] + list((ch.get("languages") or {}).get("dub", []))) if x != lang]:
            mp = E.p("build/audio", f"mix.{lg}.wav")
            if os.path.exists(mp):
                o = os.path.join(outdir, f"{E.slug}.{lg}.m4a")
                common.run(["ffmpeg", "-i", mp, "-vn", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", o])
                extra_audio.append(os.path.basename(o))
    lines = [f"✓ {common.rel(E.ep, out)}  {common.tc(common.duration(out))}  {W}x{H} @ {fps:g}",
             f"  pieces: {len(pieces) - reused} rendered, {reused} reused; took {time.time() - t_start:.0f} s"]
    if extra_audio:
        lines.append("  also: " + ", ".join(extra_audio))
    common.say(*lines)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
