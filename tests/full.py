"""The slow parts of ./pal test --full: voice, dub, a generated video with no footage, reframe, thumb, brand.

Called by tools/test.py with its helpers. A stand-in speaker "zz-test" (stock-voice speech) is made
under voices/ and removed again at the end.
"""
import json
import os
import shutil
import subprocess

import common

SCRIPT = """L01 | stock: Recursion is a function that calls itself.
L02 | stock: It needs a base case so that it can stop.

L03 | stock: Each call waits for the one below it.
L04 | stock: Then the answers come back up.
"""


def standin(ck, pal, OUT):
    """voice prepare on a clip of stock speech, as if it were a person."""
    lines = os.path.join(OUT, "lines")
    clip = os.path.join(OUT, "standin.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + sum([["-i", os.path.join(lines, f"{k}.wav")] for k in ("s1", "s3", "s5", "s8")], [])
                   + ["-filter_complex", "[0][1][2][3]concat=n=4:v=0:a=1", clip], check=True)
    shutil.rmtree(os.path.join(common.ROOT, "voices", "zz-test"), ignore_errors=True)
    rc, out = pal("voice", "prepare", "zz-test", clip, "--lang", "en")
    vd = os.path.join(common.ROOT, "voices", "zz-test")
    ck(rc == 0 and os.path.exists(os.path.join(vd, "en.wav")) and os.path.exists(os.path.join(vd, "voice.json")),
       "voice prepare picks a reference clip", out.strip()[-120:])


def dub(ck, pal, jl, dur, loudness, EP):
    """dub init/check/voice/verify into Persian from the hand-written lines; both mixes at the target."""
    tp = os.path.join(EP, "translation.fa.json")
    rc, out = pal("dub", "init", EP, "--to", "fa", "--speaker", "zz-test")
    t = common.load(tp)
    kept = [s for s in t["segments"] if s.get("text")]
    ck(rc == 0 and len(kept) == 6 and t["voice"] == "zz-test", "dub init keeps the six hand-written lines", out.strip()[-120:])
    for s in t["segments"]:
        s["skip"] = not s.get("text")          # the other lines are not voiced
    common.save(tp, t)
    rc, out = pal("dub", "check", EP, "--to", "fa")
    ck(rc == 0 and "0 without text" in out, "dub check: every voiced line has text", out.strip()[-120:])
    rc, out = pal("dub", "voice", EP, "--to", "fa")
    stem = os.path.join(EP, "build/dub/voice.fa.wav")
    ck(rc == 0 and os.path.exists(stem) and abs(dur(stem) - dur("build/cut/acut.mp4")) <= 0.1,
       "dub voice writes a stem as long as the video", out.strip()[-120:])
    rc, out = pal("dub", "verify", EP, "--to", "fa")
    ck(rc == 0 and os.path.exists(os.path.join(EP, "build/dub/verify.txt")), "dub verify writes verify.txt", out.strip()[-120:])
    rc, out = pal("mix", EP, "--lang", "en,fa")
    en, fa = (os.path.join(EP, f"build/audio/mix.{l}.wav") for l in ("en", "fa"))
    le, lf = (loudness(p) if os.path.exists(p) else None for p in (en, fa))
    ck(rc == 0 and le is not None and lf is not None and abs(le + 16) <= 1 and abs(lf + 16) <= 1 and abs(le - lf) <= 1,
       f"mix --lang: both mixes within 1 LU of the target ({le}, {lf})", out.strip()[-160:])


def generated(ck, pal, OUT):
    """A video with no footage: script -> voice -> plates over the brand ground, in English and in Persian."""
    G = os.path.join(OUT, "gen")
    shutil.rmtree(G, ignore_errors=True)
    os.makedirs(G)
    with open(os.path.join(G, "episode.md"), "w") as f:
        f.write("# Generated test episode\n\n**Stage:** generate\n")
    with open(os.path.join(G, "script.md"), "w") as f:
        f.write(SCRIPT)
    common.save(os.path.join(G, "sources.json"), {"v": 1, "fps": 30, "size": [1280, 720], "master": None,
                                                 "audio_master": None, "sources": {}})
    rc, out = pal("voice", "script", G, "--speaker", "stock")
    tj = common.load(os.path.join(G, "transcript.json"), default={})
    ck(rc == 0 and os.path.exists(os.path.join(G, "build/audio/voice.en.wav")) and len(tj.get("segments", [])) == 4,
       "voice script voices the 4 lines and times them", out.strip()[-120:])
    s = tj.get("segments", [{"first": "w1", "last": "w2"}] * 4)
    plan = {"v": 1, "mode": "plates", "beats": [
        {"id": "B01", "anchor": s[0]["first"], "until": s[1]["last"], "layout": "full",
         "plate": {"id": "P01", "type": "kit", "kit": "title-card", "alpha": False},
         "text": {"en": {"kicker": "Part one", "title": "Recursion", "wipe": "0"},
                  "fa": {"kicker": "بخش 1", "title": "بازگشت", "wipe": "0"}}},
        {"id": "B02", "anchor": s[2]["first"], "until": s[3]["last"], "layout": "full",
         "plate": {"id": "P02", "type": "kit", "kit": "list", "alpha": False},
         "text": {"en": {"title": "The call stack", "items": ["Call", "Wait", "Return"]},
                  "fa": {"title": "پشته فراخوانی", "items": ["فراخوانی", "انتظار", "بازگشت"]}}}],
        "music": [], "redact": []}
    common.save(os.path.join(G, "plan.json"), plan)
    pal("plates", "time", G)
    rc, out = pal("plates", "render", G, "--draft", "--lang", "en,fa")
    pal("mix", G, "--lang", "en")
    outs = {}
    for lang in ("en", "fa"):
        rc, out = pal("composite", G, "--draft", "--lang", lang)
        p = os.path.join(G, "build/out/draft.mp4")
        keep = os.path.join(G, f"build/out/draft.{lang}.mp4")
        if os.path.exists(p):
            shutil.copy(p, keep)
        outs[lang] = keep
    for lang, p in outs.items():
        d = common.duration(p) if os.path.exists(p) else 0
        ck(os.path.exists(p) and abs(d - tj.get("duration", 10.0)) <= 0.2,
           f"generated video renders with {'English' if lang == 'en' else 'Persian'} text ({d:.1f} s)")
    if all(os.path.exists(p) for p in outs.values()):
        # the two languages must really differ on the title card
        import hashlib
        def frame(p):
            return hashlib.md5(subprocess.run(["ffmpeg", "-v", "error", "-ss", "2", "-i", p, "-frames:v", "1", "-f", "image2pipe",
                                               "-c:v", "bmp", "-"], capture_output=True).stdout).hexdigest()
        ck(frame(outs["en"]) != frame(outs["fa"]), "the English and Persian pictures differ")


def run(ck, pal, jl, dur, loudness, EP, OUT):
    """Everything in --full."""
    try:
        standin(ck, pal, OUT)
        dub(ck, pal, jl, dur, loudness, EP)
        generated(ck, pal, OUT)
    finally:
        shutil.rmtree(os.path.join(common.ROOT, "voices", "zz-test"), ignore_errors=True)
    draft = os.path.join(EP, "build/out/draft.mp4")
    vert = os.path.join(EP, "build/out/vert.mp4")
    rc, out = pal("reframe", draft, "-o", vert, "--from", "0", "--to", "8")
    ok = os.path.exists(vert) and abs(dur(vert) - 8) <= 0.2
    ck(rc == 0 and ok, "reframe makes 8 s of 9:16", out.strip()[-120:])
    rc, out = pal("thumb", EP)
    frames = os.path.join(EP, "build/out/thumbs/frames/frames.json")
    ck(rc == 0 and os.path.exists(frames), "thumb finds candidate frames", out.strip()[-120:])
    rc, out = pal("thumb", EP, "--make", "f1", "--text", "BASE CASE", "-o", "T1.jpg")
    t1 = os.path.join(EP, "build/out/thumbs/T1.jpg")
    ck(rc == 0 and os.path.exists(t1) and os.path.getsize(t1) < 2e6, "thumb --make composes a 1280x720 option", out.strip()[-120:])
    rc, out = pal("board", "thumbs", EP)
    ck(rc == 0 and os.path.exists(os.path.join(EP, "build/review/thumbs.html")), "board thumbs shows it")
    rc, out = pal("brand", "check")
    ck(rc == 0, "brand check: the look has not drifted", out.strip()[-160:])
