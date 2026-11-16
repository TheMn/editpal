"""Brand test and drift check: does the channel's look still render the same?

    ./pal brand test [--no-video]     render a 10 s piece (sting, lower third, callout, caption, end card)
    ./pal brand check [--approve]     re-render the 5 reference stills and compare with the stored ones

`test` writes brand/reference/test.mp4 (git-ignored) and the stills brand/reference/<piece>.jpg, in the
channel's graphics language; when Persian (fa) is one of the channel's languages it also writes
test.fa.mp4 and fa-<piece>.jpg. `check` compares fresh stills with the stored ones (SSIM for shape,
PSNR of the colour planes, both through ffmpeg) and names the frames that drifted (exit 1);
`--approve` stores the new stills as the reference. Run `check` after any change to brand/.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

import common
import hf
import plates

REF = os.path.join(common.ROOT, "brand", "reference")
PIECES = [  # (name, kit piece, start, duration, still offset)
    ("sting", "sting", 0.0, 1.5, 0.95), ("lower-third", "lower-third", 1.5, 3.0, 1.6),
    ("callout", "callout", 4.5, 2.0, 1.5), ("caption", "caption", 6.5, 2.0, 1.2), ("end-card", "end-card", 8.5, 1.5, 1.2)]
TEXT = {
    "en": {"sting": {"mark": "Channel"}, "lower-third": {"name": "Sara Moradi", "role": "Host, 12 Rules Show"},
           "callout": {"text": "One idea at a time"}, "end-card": {"title": "Thanks for watching", "sub": "Next: pick a video"},
           "caption": {"words": [("Every", .1, .4), ("word", .4, .7), ("is", .7, .85), ("timed", .85, 1.4), ("on", 1.4, 1.55), ("screen.", 1.55, 2.0)]}},
    "fa": {"sting": {"mark": "کانال"}, "lower-third": {"name": "سارا مرادی", "role": "مجری، برنامه ۱۲ قانون"},
           "callout": {"text": "هر بار فقط یک ایده"}, "end-card": {"title": "ممنون که دیدید", "sub": "ویدیوی بعدی را انتخاب کنید"},
           "caption": {"words": [("هر", .1, .3), ("کلمه", .3, .7), ("با", .7, .85), ("Python", .85, 1.4), ("زمان‌بندی", 1.4, 1.7), ("می‌شود.", 1.7, 2.0)]}},
}
PLANE = "#8B9099"  # neutral stand-in for footage


def languages():
    """The language(s) to render: the graphics language, plus Persian when the channel uses it."""
    ch = common.channel().get("languages", {})
    langs = plates.graphics_langs(None)[:1]
    used = {ch.get("spoken")} | set(ch.get("dub", [])) | set(ch.get("subtitles", [])) | {ch.get("graphics")}
    if "fa" in used and "fa" not in langs:
        langs.append("fa")
    return langs


def build(lang):
    """Stage the test project for a language; returns (project dir, size, fps, still times)."""
    b = plates.read_frame()
    W, H = 1920, 1080
    fps = int(common.channel().get("video", {}).get("fps", 30))
    proj = os.path.join(common.CACHE, f"brand-test-{lang}")
    shutil.rmtree(os.path.join(proj, "compositions"), ignore_errors=True)
    plates.stage_project(proj, b)
    hosts, stills = [], []
    for name, kit, t0, dur, off in PIECES:
        cid = "t_" + name.replace("-", "_")
        vals = dict(TEXT[lang][name])
        if "words" in vals:
            vals["words"] = [{"w": w, "start": s, "end": e} for w, s, e in vals["words"]]
        html = plates.render_kit_file(kit, b, lang, W, H, dur, cid)
        with open(os.path.join(proj, "compositions", f"{cid}.html"), "w", encoding="utf-8") as f:
            f.write(html)
        hosts.append(dict(id=cid, start=t0, dur=dur, values=vals, src=f"compositions/{cid}.html", track=1 + len(hosts)))
        stills.append(round(t0 + off, 3))
    with open(os.path.join(proj, "index.html"), "w", encoding="utf-8") as f:
        f.write(plates.index_html(hosts, W, H, 10.0, bg=PLANE))
    return proj, fps, stills


def snap(proj, stills, outdir, prefix):
    """Snapshot the 5 reference moments into outdir/<prefix><piece>.jpg."""
    tmp = os.path.join(proj, ".snap")
    shutil.rmtree(tmp, ignore_errors=True)
    r = hf.run(["snapshot", proj, "--at", ",".join(f"{t:g}" for t in stills), "--no-end", "-o", tmp], capture=True)
    pngs = sorted(glob.glob(os.path.join(tmp, "frame-*.png")))
    if r.returncode != 0 or len(pngs) != len(PIECES):
        common.die("snapshot failed: " + " | ".join((r.stderr or r.stdout).strip().splitlines()[-3:]))
    os.makedirs(outdir, exist_ok=True)
    for png, (name, *_rest) in zip(pngs, PIECES):
        plates.to_jpg(png, os.path.join(outdir, f"{prefix}{name}.jpg"))
    shutil.rmtree(tmp, ignore_errors=True)


def ffstat(a, b, flt):
    """ffmpeg filter result text (stderr) for two images."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", a, "-i", b, "-lavfi", flt, "-f", "null", "-"],
                       capture_output=True, text=True)
    return r.stderr


def compare(new, ref):
    """(ssim, chroma psnr in dB) of two stills."""
    ss = re.search(r"All:([0-9.]+)", ffstat(new, ref, "[0:v][1:v]ssim"))
    ps = ffstat(new, ref, "[0:v][1:v]psnr")
    u, v = (re.search(rf"{c}:([0-9.inf]+)", ps) for c in "uv")
    num = lambda m: 99.0 if not m or m.group(1).startswith("inf") else float(m.group(1))
    return (float(ss.group(1)) if ss else 0.0), min(num(u), num(v))


def cmd_test(argv):
    """brand test: render the test piece and write the reference stills."""
    ap = argparse.ArgumentParser(prog="brand test")
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(REF, exist_ok=True)
    for lang in languages():
        proj, fps, stills = build(lang)
        ok, lines = plates.hf_check(proj)
        if not ok:
            common.say(*lines); common.die(f"hyperframes check failed on the {lang} test piece")
        snap(proj, stills, REF, "" if lang == languages()[0] else f"{lang}-")
        if not a.no_video:
            out = os.path.join(REF, "test.mp4" if lang == languages()[0] else f"test.{lang}.mp4")
            r = hf.run(["render", proj, "-f", str(fps), "-q", "looks", "--quiet", "--no-wait", "-o", out], capture=True)
            if r.returncode != 0:
                common.die("render failed: " + " | ".join((r.stderr or r.stdout).strip().splitlines()[-3:]))
        common.say(f"✓ {lang}: 5 stills in brand/reference/" + ("" if a.no_video else f" and {os.path.basename(out)}"))
    return 0


def cmd_check(argv):
    """brand check [--approve]: compare fresh stills with the stored reference."""
    ap = argparse.ArgumentParser(prog="brand check")
    ap.add_argument("--approve", action="store_true")
    a = ap.parse_args(argv)
    if a.approve:
        return cmd_test(["--no-video"])
    bad, lines = [], []
    for i, lang in enumerate(languages()):
        prefix = "" if i == 0 else f"{lang}-"
        if not all(os.path.exists(os.path.join(REF, f"{prefix}{n}.jpg")) for n, *_ in PIECES):
            common.die("no reference stills yet: run ./pal brand test, look at them, then ./pal brand check --approve", 3)
        proj, fps, stills = build(lang)
        tmp = os.path.join(proj, "new")
        snap(proj, stills, tmp, prefix)
        for n, *_ in PIECES:
            s, p = compare(os.path.join(tmp, f"{prefix}{n}.jpg"), os.path.join(REF, f"{prefix}{n}.jpg"))
            lines.append(f"  {prefix}{n:<12} ssim {s:.4f}  chroma {p:.1f} dB")
            if s < 0.985 or p < 41:
                bad.append(f"{prefix}{n}")
        shutil.rmtree(tmp, ignore_errors=True)
    common.say(*lines)
    if bad:
        common.say(f"✗ the look drifted: {', '.join(bad)}. If the change is wanted: ./pal brand check --approve")
        return 1
    common.say("✓ the brand still looks the same")
    return 0


def main(argv):
    """./pal brand entry point."""
    cmds = {"test": cmd_test, "check": cmd_check}
    if not argv or argv[0] not in cmds:
        print(__doc__.strip()); return 2
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
