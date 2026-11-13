"""Graphics plates: short HyperFrames clips laid over the A-cut (or one whole generated piece).

    ./pal plates time <ep>                       recompute every beat's time from its word anchors
    ./pal plates stills <ep> [--lang en] [--only B03,B04]       pose every beat on the real frame -> build/review/stills/
    ./pal plates render <ep> [--only P03,P07] [--draft] [--lang en] [--range 0-30]
    ./pal plates kit <name> --vars '{"name":"Ana"}' [--alpha] [--lang fa] [--dur 5] -o out.mov
    ./pal plates kits                            list the kit pieces and their variables

`plan.json` (docs/FORMATS.md) lists beats; each beat with a `plate` becomes one clip. A `kit` plate
is a composition from brand/kit/ filled with the beat's text and the colours and fonts of
brand/frame.md; a `custom` plate is a file a plate-maker wrote (plate.src). Plates render one after
another, alone, at the project size and frame rate: transparent ones as ProRes 4444 .mov, opaque
ones as .mp4. Unchanged plates (same source, text, brand) are skipped.
Writes <ep>/hf/ (HyperFrames project), build/plates/<id>.<lang>.<ext> and build/plates/index.json,
build/review/stills/<beat>.jpg. For "mode": "project" plans, render renders hf/index.html whole.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import common
import hf

KIT = os.path.join(common.ROOT, "brand", "kit")
FONTS = os.path.join(common.ROOT, "brand", "fonts")
FRAME_MD = os.path.join(common.ROOT, "brand", "frame.md")
GSAP_TAG = '<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>'
RANGES = {  # unicode-range of the subset files (same values as the fontsource packages)
    "latin": "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,"
             "U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD",
    "arabic": "U+0600-06FF,U+0750-077F,U+0870-088E,U+0890-0891,U+0897-08E1,U+08E3-08FF,U+200C-200E,"
              "U+2010-2011,U+204F,U+2E41,U+FB50-FDFF,U+FE70-FE74,U+FE76-FEFC",
}
MIN_PLATE = 2.0
LEAD = 0.15


# ---------------------------------------------------------------- brand

def read_frame(path=FRAME_MD):
    """brand/frame.md as a dict (its YAML frontmatter)."""
    import yaml
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        common.die(f"{common.rel(common.ROOT, path)} has no YAML frontmatter between --- lines")
    return yaml.safe_load(m.group(1))


def _fontfaces(b):
    css = []
    for key, fam in (("latin", "EPLatin"), ("persian", "EPPersian")):
        t = b["typography"][key]
        for f in t["files"]:
            ext = os.path.splitext(f["file"])[1].lower()
            fmt = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}[ext]
            rng = RANGES.get(f.get("range", ""), f.get("range"))
            css.append(f'@font-face{{font-family:"{fam}";src:url("assets/fonts/{f["file"]}") format("{fmt}");'
                       f'font-weight:{f.get("weight", "100 900")};font-style:normal;'
                       + (f"unicode-range:{rng};" if rng else "") + "}")
    return "\n".join(css)


def font_files(b):
    """Font file names the brand uses (copied into every HyperFrames project)."""
    return sorted({f["file"] for k in ("latin", "persian") for f in b["typography"][k]["files"]})


def brand_css(b, lang, W, H):
    """The CSS every kit piece starts with: @font-face rules and the brand as custom properties."""
    c, ty, sp, mo = b["colors"], b["typography"], b["spacing"], b["motion"]
    fa = lang == "fa"
    fam = ('"EPPersian","EPLatin"' if fa else '"EPLatin","EPPersian"') + ",sans-serif"
    cap = b["captions"]
    props = {f"--c-{k}": v for k, v in c.items()}
    props.update({
        "--u": f"{H / 100:.4f}px", "--w": f"{W / 100:.4f}px", "--font-text": fam,
        "--display-weight": ty["persian" if fa else "latin"]["display-weight"],
        "--text-weight": ty["persian" if fa else "latin"]["text-weight"],
        "--tracking": "0em" if fa else f'{ty["tracking"]}em', "--lh": max(ty["line-height"], 1.32) if fa else ty["line-height"],
        "--margin": sp["margin"], "--gap": sp["gap"], "--radius": sp["radius"],
    })
    props.update({f"--s-{k}": v for k, v in ty["scale"].items()})
    props.update({f"--cap-{k}": v for k, v in cap.items() if isinstance(v, (int, float, str))})
    body = ";".join(f"{k}:{v}" for k, v in props.items())
    return _fontfaces(b) + f"\n#root{{{body}}}"


def tokens(b, lang, W, H, dur, comp_id):
    """Values substituted for {{name}} in a kit file."""
    mo = b["motion"]
    return {"id": comp_id, "dur": f"{dur:g}", "W": str(W), "H": str(H), "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr", "ease_in": mo["ease-in"], "ease_out": mo["ease-out"],
            "enter": str(mo["enter"]), "exit": str(mo["exit"]), "stagger": str(mo["stagger"]),
            "cap_max_words": str(b["captions"]["max-words"]), "cap_font": b["captions"]["font"],
            "cap_bg": str(b["captions"]["background"]), "cap_highlight": b["captions"]["highlight"],
            "cap_color": b["captions"]["color"], "video": "", "media_start": "0"}


def kit_info(name):
    """brand/kit/<name>/kit.json (about, alpha, dur, vars, layouts)."""
    p = os.path.join(KIT, name, "kit.json")
    if not os.path.exists(p):
        have = ", ".join(sorted(os.listdir(KIT))) if os.path.isdir(KIT) else ""
        common.die(f"no kit piece '{name}' in brand/kit/ (have: {have})", 2)
    return common.load(p)


def render_kit_file(name, b, lang, W, H, dur, comp_id, extra=None):
    """Source text of one instantiated kit composition (extra: more {{tokens}}, e.g. video)."""
    with open(os.path.join(KIT, name, f"{name}.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace("/*BRAND*/", brand_css(b, lang, W, H))
    tk = tokens(b, lang, W, H, dur, comp_id)
    tk.update(extra or {})
    for k, v in tk.items():
        html = html.replace("{{" + k + "}}", v)
    return html


# ---------------------------------------------------------------- projects

def stage_project(proj, b):
    """Create <proj>/{compositions,assets/fonts} and copy the brand's fonts."""
    os.makedirs(os.path.join(proj, "compositions"), exist_ok=True)
    fd = os.path.join(proj, "assets", "fonts")
    os.makedirs(fd, exist_ok=True)
    for f in font_files(b):
        src = os.path.join(FONTS, f)
        if not os.path.exists(src):
            common.die(f"font {f} (named in brand/frame.md) is not in brand/fonts/", 3)
        if not os.path.exists(os.path.join(fd, f)):
            shutil.copy(src, fd)
    with open(os.path.join(proj, "hyperframes.json"), "w") as fh:
        json.dump({"paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
                   "media": {"autoProxy": False}}, fh)


def solo_html(comp_id, dur, W, H, values, src=None, extra=""):
    """A root file that mounts exactly one composition at time 0 (the way a plate renders alone)."""
    src = src or f"compositions/{comp_id}.html"
    vals = json.dumps(values, ensure_ascii=False).replace("'", "&#39;")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width={W}, height={H}">
{GSAP_TAG}
<style>*{{margin:0;padding:0;box-sizing:border-box}}html,body{{width:{W}px;height:{H}px;overflow:hidden;background:transparent}}</style>
</head><body>
<div id="root" data-composition-id="solo-{comp_id}" data-start="0" data-duration="{dur:g}" data-width="{W}" data-height="{H}">
{extra}<div id="{comp_id}" data-composition-id="{comp_id}" data-composition-src="{src}" data-start="0" data-duration="{dur:g}" data-track-index="1" data-width="{W}" data-height="{H}" data-variable-values='{vals}'></div>
</div>
<script>window.__timelines=window.__timelines||{{}};window.__timelines["solo-{comp_id}"]=gsap.timeline({{paused:true}});</script>
</body></html>
"""


def host_html(h, W, H):
    """One composition host line for index.html: {id, start, dur, values, src}."""
    vals = json.dumps(h.get("values", {}), ensure_ascii=False).replace("'", "&#39;")
    return (f'<div id="{h["id"]}" data-composition-id="{h["id"]}" data-composition-src="{h["src"]}" '
            f'data-start="{h["start"]:g}" data-duration="{h["dur"]:g}" data-track-index="{h.get("track", 1)}" '
            f'data-width="{W}" data-height="{H}" data-variable-values=\'{vals}\'></div>')


def index_html(hosts, W, H, total, base=None, base_in=0.0, bg=None):
    """index.html that mounts several compositions on one timeline over an optional base video
    (the A-cut proxy). Used for stills, checks and whole-piece (project mode) renders."""
    vid = (f'<video id="base" class="clip" src="{base}" data-start="0" data-duration="{total:g}" '
           f'data-media-start="{base_in:g}" data-track-index="0" muted playsinline style="position:absolute;left:0;top:0;'
           f'width:{W}px;height:{H}px;object-fit:cover"></video>\n') if base else ""
    if bg:
        vid = f'<div style="position:absolute;inset:0;background:{bg}"></div>\n' + vid
    body = "\n".join(host_html(h, W, H) for h in hosts)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width={W}, height={H}">
{GSAP_TAG}
<style>*{{margin:0;padding:0;box-sizing:border-box}}html,body{{width:{W}px;height:{H}px;overflow:hidden;background:{'#000' if base else 'transparent'}}}</style>
</head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{total:g}" data-width="{W}" data-height="{H}">
{vid}{body}
</div>
<script>window.__timelines=window.__timelines||{{}};window.__timelines["main"]=gsap.timeline({{paused:true}});</script>
</body></html>
"""


# ---------------------------------------------------------------- one plate

def sh_size(W, H, cap=(1920, 1080)):
    """Plate size: the project size, never above 1920x1080 on its long side (composite scales up)."""
    k = min(1.0, cap[0] / max(W, H) if W >= H else cap[1] / max(W, H))
    return int(W * k) // 2 * 2, int(H * k) // 2 * 2


def render_plate(proj, comp_id, dur, W, H, fps, alpha, out, draft=False, log=None):
    """Render solo/<comp_id>.html alone. Transparent: PNG frames then lossless ARGB .mov (about 12x
    faster than HyperFrames' own ProRes encode); opaque: .mp4. Returns (ok, seconds, message)."""
    t0 = time.time()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    args = ["render", proj, "-c", f"solo/{comp_id}.html", "-f", str(fps), "-q", "draft" if draft else "looks",
            "--quiet", "--no-wait"]
    if alpha:
        seq = os.path.join(proj, ".seq", comp_id)
        shutil.rmtree(seq, ignore_errors=True)
        r = hf.run(args + ["--format", "png-sequence", "-o", seq], capture=True)
        if r.returncode == 0 and os.path.isdir(seq):
            e = subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", os.path.join(seq, "frame_%06d.png"),
                                "-c:v", "qtrle", "-pix_fmt", "argb", "-threads", "2", out + ".part.mov"],
                               capture_output=True, text=True)
            if e.returncode == 0:
                os.replace(out + ".part.mov", out)
            else:
                r = e
        shutil.rmtree(seq, ignore_errors=True)
    else:
        r = hf.run(args + ["--format", "mp4", "-o", out], capture=True)
    ok = r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0
    msg = "" if ok else " | ".join((r.stderr or r.stdout or "no output").strip().splitlines()[-3:])
    return ok, round(time.time() - t0, 1), msg


def hf_check(proj):
    """hyperframes check on a project; returns (ok, last lines)."""
    r = hf.run(["check", proj, "--no-cache"], capture=True)
    lines = [ln for ln in (r.stdout or "").splitlines() if "✗" in ln or "Fix:" in ln]
    return r.returncode == 0, lines[:6]


def to_jpg(png, jpg, width=960):
    """Downscale a still to a JPEG of at most `width` pixels."""
    common.run(["ffmpeg", "-i", png, "-vf", f"scale='min({width},iw)':-2", "-q:v", "3", jpg])


# ---------------------------------------------------------------- kit command

def parse_size(s):
    w, h = s.lower().split("x")
    return int(w), int(h)


def cmd_kit(argv):
    """plates kit <name> --vars JSON [--alpha] -o file: render one kit piece directly."""
    ap = argparse.ArgumentParser(prog="plates kit")
    ap.add_argument("name")
    ap.add_argument("--vars", default="{}")
    ap.add_argument("--alpha", action="store_true")
    ap.add_argument("--lang", default=None)
    ap.add_argument("--dur", type=float, default=None)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--fps", type=int, default=None)
    ap.add_argument("--video", default=None, help="footage for pip-frame (a file with a keyframe every second)")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--check", action="store_true", help="run hyperframes check first")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args(argv)
    b, info = read_frame(), kit_info(a.name)
    lang = a.lang or common.channel().get("languages", {}).get("graphics", "en")
    lang = "en" if lang == "per-language" else lang
    W, H = parse_size(a.size)
    fps = a.fps or int(common.channel().get("video", {}).get("fps", 30))
    dur = a.dur or info["dur"]
    vals = dict(info["vars"]); vals.update(json.loads(a.vars))
    key = common.sha(a.name, vals, lang, W, H, dur)
    proj = os.path.join(common.CACHE, "kit", f"{a.name}-{key}")
    stage_project(proj, b)
    cid = a.name.replace("-", "_")
    html = render_kit_file(a.name, b, lang, W, H, dur, cid)
    if info.get("video"):
        if not a.video:
            common.die(f"{a.name} needs --video <footage file>", 2)
        shutil.copy(a.video, os.path.join(proj, "assets", "footage.mp4"))
        html = html.replace('src=""', 'src="assets/footage.mp4"')
    with open(os.path.join(proj, "compositions", f"{cid}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    os.makedirs(os.path.join(proj, "solo"), exist_ok=True)
    with open(os.path.join(proj, "solo", f"{cid}.html"), "w", encoding="utf-8") as f:
        f.write(solo_html(cid, dur, W, H, vals))
    with open(os.path.join(proj, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html([dict(id=cid, start=0, dur=dur, values=vals, src=f"compositions/{cid}.html")], W, H, dur))
    if a.check:
        ok, lines = hf_check(proj)
        common.say(*lines)
        if not ok:
            return 1
    alpha = a.alpha or a.out.endswith(".mov")
    ok, secs, msg = render_plate(proj, cid, dur, W, H, fps, alpha, os.path.abspath(a.out), a.draft)
    if not ok:
        common.die(f"render failed: {msg}")
    common.say(f"✓ {a.out}  ({secs} s, {os.path.getsize(a.out) / 1e6:.1f} MB, {'alpha' if alpha else 'opaque'})")
    return 0


def cmd_kits(argv):
    """plates kits: list the kit pieces."""
    for n in sorted(os.listdir(KIT)):
        i = kit_info(n)
        common.say(f"{n:<12} {'alpha ' if i['alpha'] else 'opaque'} {i['dur']:>4g}s  vars: {', '.join(i['vars'])}\n             {i['about']}")
    return 0


# ---------------------------------------------------------------- episode commands

EXCLUSIVE = {"full", "pip", "split", "card", "b-roll"}


def graphics_langs(a_lang):
    """Languages to render: --lang, else channel languages.graphics (per-language: every language)."""
    if a_lang:
        return [x for x in a_lang.split(",") if x]
    ch = common.channel().get("languages", {})
    g = ch.get("graphics", "en")
    if g != "per-language":
        return [g]
    out = [ch.get("spoken", "en")] + list(ch.get("dub", [])) + list(ch.get("subtitles", []))
    return list(dict.fromkeys(out))


def load_plan(ep):
    return common.load(os.path.join(ep, "plan.json"))


def words_of(ep):
    t = common.load(os.path.join(ep, "transcript.json"))
    return {w["id"]: w for w in t["words"]}, t


def plate_beats(plan):
    return [b for b in plan.get("beats", []) if b.get("plate")]


def beat_text(beat, lang):
    """The beat's text in a language (falls back to any language that has it)."""
    t = beat.get("text") or {}
    return dict(t.get(lang) or next(iter(t.values()), {}))


def conflicts(a, b):
    """True when two beats that overlap in time cannot share the screen."""
    if a.get("layout") == b.get("layout"):
        return True
    return a.get("layout") in EXCLUSIVE or b.get("layout") in EXCLUSIVE


def cmd_time(argv):
    """plates time <ep>: recompute each beat's t from its anchor/until word ids."""
    ep = common.episode(argv[0]) if argv else common.die("usage: ./pal plates time <ep>", 2)
    plan, (words, tr), fps = load_plan(ep), words_of(ep), common.fps_of(ep)
    total = tr.get("duration") or max(w["end"] for w in words.values())
    moved = 0
    for beat in plan.get("beats", []):
        a = beat.get("anchor")
        if not a:
            continue
        if a not in words:
            common.die(f"beat {beat['id']}: anchor {a} is not in transcript.json")
        kit = beat.get("plate", {}).get("type") == "kit"
        default = kit_info(beat["plate"]["kit"])["dur"] if kit else 4.0
        old = beat.get("t")
        t0 = common.snap(max(0.0, words[a]["start"] - LEAD), fps)
        if beat.get("until") in words:
            t1 = common.snap(words[beat["until"]]["end"] + 0.25, fps)
        else:
            t1 = common.snap(t0 + ((old[1] - old[0]) if old else default), fps)
        t1 = max(t1, common.snap(t0 + min(MIN_PLATE, default), fps))
        if t1 > total:
            t1 = common.snap(total, fps)
            t0 = common.snap(max(0.0, min(t0, t1 - min(MIN_PLATE, default))), fps)
        moved += old != [t0, t1]
        beat["t"] = [t0, t1]
        if beat.get("plate"):
            beat["est_render_s"] = round(4 + (t1 - t0) * (1.6 if beat["plate"].get("alpha") else 2.3))
    bs = sorted((b for b in plan["beats"] if b.get("t")), key=lambda b: b["t"][0])
    for i, x in enumerate(bs):  # padding alone must not cause a clash: end a plate where the next one starts
        for y in bs[i + 1:]:
            if conflicts(x, y) and 0 < x["t"][1] - y["t"][0] <= 0.5 and y["t"][0] - x["t"][0] >= MIN_PLATE:
                x["t"][1] = y["t"][0]
    clash = [(x["id"], y["id"]) for i, x in enumerate(bs) for y in bs[i + 1:]
             if y["t"][0] < x["t"][1] - 1e-6 and conflicts(x, y)]
    common.save(os.path.join(ep, "plan.json"), plan)
    common.say(f"✓ {len(bs)} beats timed ({moved} changed)" + (f"; {len(clash)} collide:" if clash else "; no collisions"),
               *[f"  {x} overlaps {y} ({next(b for b in bs if b['id'] == x)['layout']}/{next(b for b in bs if b['id'] == y)['layout']})"
                 for x, y in clash[:10]])
    return 3 if clash else 0


def prepare_base(ep, proj, fps):
    """hf/assets/acut.mp4: the A-cut proxy at 960 px with a keyframe every second (HyperFrames seeks it)."""
    for n in ("acut-preview.mp4", "acut.mp4"):
        src = os.path.join(ep, "build", "cut", n)
        if os.path.exists(src):
            break
    else:
        return None
    dst = os.path.join(proj, "assets", "acut.mp4")
    stamp = os.path.join(proj, "assets", "acut.stamp")
    key = f"{src}:{os.path.getsize(src)}:{os.path.getmtime(src)}:{fps}"
    if not (os.path.exists(dst) and os.path.exists(stamp) and open(stamp).read() == key):
        common.run(["ffmpeg", "-i", src, "-vf", "scale=960:-2", "-r", fps, "-g", fps, "-keyint_min", fps, "-c:v", "libx264",
                    "-crf", "26", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an", dst])
        open(stamp, "w").write(key)
    return "assets/acut.mp4"


def instantiate(ep, proj, beat, lang, b, W, H, base):
    """Write compositions/<cid>.html for a beat; returns (cid, dur, values, source text) or None."""
    pl, (t0, t1) = beat["plate"], beat["t"]
    dur = round(t1 - t0, 3)
    cid = f"{pl['id'].lower()}_{lang}"
    vals = beat_text(beat, lang)
    if pl["type"] == "kit":
        name, info = pl["kit"], kit_info(pl["kit"])
        extra = {}
        if info.get("video"):
            if not base:
                common.die("pip plates need the A-cut: run ./pal cut render <ep> first", 3)
            extra = {"video": base, "media_start": f"{t0:g}"}
        if name == "caption" and "words" not in vals:
            words, _ = words_of(ep)
            vals["words"] = [{"w": w["w"], "start": round(w["start"] - t0, 3), "end": round(w["end"] - t0, 3)}
                             for w in words.values() if t0 - 0.01 <= w["start"] < t1]
        html = render_kit_file(name, b, lang, W, H, dur, cid, extra)
    else:
        src = os.path.join(ep, pl["src"])
        if not os.path.exists(src):
            common.die(f"beat {beat['id']}: plate source {pl['src']} does not exist")
        with open(src, encoding="utf-8") as f:
            html = f.read()
        m = re.search(r'data-composition-id="([^"]+)"', html)
        cid = m.group(1) if m else cid
    with open(os.path.join(proj, "compositions", f"{cid}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return cid, dur, vals, html


def project_for(ep):
    """<ep>/hf with the brand fonts staged; returns (proj, brand, frame text, W, H, fps)."""
    b = read_frame()
    proj = os.path.join(ep, "hf")
    stage_project(proj, b)
    src = common.load(os.path.join(ep, "sources.json"), default={})
    W, H = sh_size(*(src.get("size") or [1920, 1080]))
    plan = common.load(os.path.join(ep, "plan.json"), default={})
    if plan.get("size"):
        W, H = plan["size"]
    return proj, b, open(FRAME_MD, encoding="utf-8").read(), W, H, int(common.fps_of(ep))


def cmd_stills(argv):
    """plates stills <ep>: every beat posed over the real frame, snapshotted in one run."""
    ap = argparse.ArgumentParser(prog="plates stills")
    ap.add_argument("ep"); ap.add_argument("--lang", default=None); ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    ep = common.episode(a.ep)
    lang = graphics_langs(a.lang)[0]
    only = {x.strip().upper() for x in a.only.split(",") if x.strip()}
    plan = load_plan(ep)
    proj, b, _, W, H, fps = project_for(ep)
    base = prepare_base(ep, proj, fps)
    hosts, ats, names, end = [], [], [], 0.0
    for beat in plate_beats(plan):
        if only and beat["id"].upper() not in only and beat["plate"]["id"].upper() not in only:
            continue
        if not beat.get("t"):
            common.die(f"beat {beat['id']} has no time: run ./pal plates time {os.path.basename(ep)}", 3)
        cid, dur, vals, _ = instantiate(ep, proj, beat, lang, b, W, H, base)
        pl = beat["plate"]
        still = beat.get("still") or (kit_info(pl["kit"]).get("still") if pl["type"] == "kit" else None) or dur * 0.6
        still = min(still, max(dur - 0.3, 0.1))
        t0 = beat["t"][0]
        hosts.append(dict(id=cid, start=t0, dur=min(dur, still + 0.4), values=vals, src=f"compositions/{cid}.html", track=1 + len(hosts)))
        ats.append(round(t0 + still, 3)); names.append(beat["id"]); end = max(end, t0 + dur)
    if not hosts:
        common.say("no plate beats in plan.json"); return 0
    with open(os.path.join(proj, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html(hosts, W, H, end + 0.5, base=base))
    sdir = os.path.join(ep, "build", "review", "stills"); os.makedirs(sdir, exist_ok=True)
    tmp = os.path.join(proj, ".snap"); shutil.rmtree(tmp, ignore_errors=True)
    r = hf.run(["snapshot", proj, "--at", ",".join(f"{t:g}" for t in ats), "--no-end", "-o", tmp], capture=True)
    pngs = sorted(glob.glob(os.path.join(tmp, "frame-*.png")))
    if r.returncode != 0 or len(pngs) != len(names):
        common.die("snapshot failed: " + " | ".join((r.stderr or r.stdout).strip().splitlines()[-3:]))
    for png, n in zip(pngs, names):
        to_jpg(png, os.path.join(sdir, f"{n}.jpg"))
    shutil.rmtree(tmp, ignore_errors=True)
    common.say(f"✓ {len(names)} stills ({lang}) in {common.rel(ep, sdir)}/" + ("" if base else "  (no A-cut yet: plain background)"))
    return 0


def cmd_render(argv):
    """plates render <ep>: render the plates one after another; unchanged ones are skipped."""
    ap = argparse.ArgumentParser(prog="plates render")
    ap.add_argument("ep"); ap.add_argument("--only", default=""); ap.add_argument("--draft", action="store_true")
    ap.add_argument("--lang", default=None); ap.add_argument("--range", default=None)
    a = ap.parse_args(argv)
    ep = common.episode(a.ep)
    plan = load_plan(ep)
    proj, b, frame_text, W, H, fps = project_for(ep)
    base = prepare_base(ep, proj, fps)
    odir = os.path.join(ep, "build", "plates"); os.makedirs(odir, exist_ok=True)
    ipath = os.path.join(odir, "index.json")
    index = common.load(ipath, default={"v": 1, "plates": {}})
    langs = graphics_langs(a.lang)
    if plan.get("mode") == "project":
        return render_project(ep, proj, langs, a, index, ipath, odir, W, H, fps)
    only = {x.strip().upper() for x in a.only.split(",") if x.strip()}
    failed, done, skipped = [], 0, 0
    for lang in langs:
        for beat in plate_beats(plan):
            pid = beat["plate"]["id"]
            if only and pid.upper() not in only and beat["id"].upper() not in only:
                continue
            if not beat.get("t"):
                common.die(f"beat {beat['id']} has no time: run ./pal plates time {os.path.basename(ep)}", 3)
            cid, dur, vals, html = instantiate(ep, proj, beat, lang, b, W, H, base)
            alpha = bool(beat["plate"].get("alpha"))
            out = os.path.join(odir, f"{pid}.{lang}.{'mov' if alpha else 'mp4'}")
            vid = os.path.getmtime(os.path.join(proj, base)) if "assets/acut.mp4" in html and base else 0
            key = common.sha(html, vals, frame_text, W, H, fps, alpha, a.draft, vid)
            ent = index["plates"].get(f"{pid}.{lang}", {})
            if ent.get("hash") == key and os.path.exists(out):
                skipped += 1
            else:
                os.makedirs(os.path.join(proj, "solo"), exist_ok=True)
                with open(os.path.join(proj, "solo", f"{cid}.html"), "w", encoding="utf-8") as f:
                    f.write(solo_html(cid, dur, W, H, vals))
                ok, secs, msg = render_plate(proj, cid, dur, W, H, fps, alpha, out, a.draft)
                if not ok:
                    failed.append(f"{pid}: {msg}"); continue
                index["plates"][f"{pid}.{lang}"] = {"id": pid, "beat": beat["id"], "lang": lang, "file": common.rel(ep, out),
                    "alpha": alpha, "duration": dur, "hash": key, "seconds": secs, "quality": "draft" if a.draft else "looks"}
                done += 1
                print(f"  {pid}.{lang} {secs}s", flush=True)
            if beat.get("status") != "rendered":
                beat["status"] = "rendered"
    common.save(ipath, index); common.save(os.path.join(ep, "plan.json"), plan)
    common.say(f"✓ {done} rendered, {skipped} unchanged -> {common.rel(ep, odir)}/index.json", *[f"✗ {f}" for f in failed])
    return 1 if failed else 0


def render_project(ep, proj, langs, a, index, ipath, odir, W, H, fps):
    """mode "project": the whole hf/index.html as one video (Shorts, generated pieces)."""
    if not os.path.exists(os.path.join(proj, "index.html")):
        common.die("mode is 'project' but hf/index.html does not exist yet (the plate-maker writes it)", 3)
    for lang in langs:
        out = os.path.join(odir, f"project.{lang}.mp4")
        args = ["render", proj, "-f", str(fps), "-q", "draft" if a.draft else "looks", "--quiet", "--no-wait", "-o", out,
                "--variables", json.dumps({"lang": lang})]
        if a.range:
            s, e = a.range.split("-"); args += ["--start", s, "--end", e]
        t0 = time.time()
        r = hf.run(args, capture=True)
        if r.returncode != 0:
            common.die("render failed: " + " | ".join((r.stderr or r.stdout).strip().splitlines()[-3:]))
        index["plates"][f"project.{lang}"] = {"id": "project", "lang": lang, "file": common.rel(ep, out), "alpha": False,
            "seconds": round(time.time() - t0, 1), "quality": "draft" if a.draft else "looks"}
    common.save(ipath, index)
    common.say(f"✓ project rendered ({', '.join(langs)}) -> {common.rel(ep, odir)}/")
    return 0


def main(argv):
    """./pal plates entry point."""
    cmds = {"time": cmd_time, "stills": cmd_stills, "render": cmd_render, "kit": cmd_kit, "kits": cmd_kits}
    if not argv or argv[0] not in cmds:
        print(__doc__.strip()); return 2
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
