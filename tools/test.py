"""Build a small generated clip and run the whole toolchain on it, with assertions.

    ./pal test [--full] [--rebuild] [--keep-going]

The clip (tests/fixture.py) is 56 s of stock-voice speech with planted defects, a camera, a
microphone 0.740 s later, a b-roll and a synthetic music file, in tests/build/episode/. The default
run (about 5 minutes on 4 cores, quick transcription model) covers ingest, sync, transcribe, cut,
subtitles, plates, mix, the review pages, composite, qc and export. `--full` adds the slow parts:
voice prepare, dub, a generated video with no footage in English and Persian, reframe, thumb and
brand check. One line per assertion (ok or FAIL); exit code 1 if any failed. `--rebuild` throws away
tests/build/ first.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

import common

TESTS = os.path.join(common.ROOT, "tests")
sys.path.insert(0, TESTS)
OUT = os.path.join(TESTS, "build")
EP = os.path.join(OUT, "episode")
PAL = os.path.join(common.ROOT, "pal")

passed, failed = [], []


def ck(ok, msg, detail=""):
    """Record and print one assertion."""
    (passed if ok else failed).append(msg)
    print(("✓ " if ok else "✗ ") + msg + (f"  [{detail}]" if detail and not ok else ""), flush=True)
    return ok


def pal(*args, ep=EP, expect=0, timeout=1500):
    """Run ./pal with the test episode path as the first argument after the command. Returns (rc, output)."""
    t0 = time.time()
    cmd = [PAL] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "") + (r.stderr or "")
    print(f"  · ./pal {' '.join(str(a) for a in args if not str(a).startswith(OUT))[:70]}  {time.time() - t0:.0f}s", flush=True)
    return r.returncode, out


def jl(path, default=None):
    return common.load(os.path.join(EP, path), default=default if default is not None else {})


def dur(path):
    return common.duration(path if os.path.isabs(path) else os.path.join(EP, path))


def vdur(path, kind):
    """Duration of one stream kind (v or a)."""
    p = path if os.path.isabs(path) else os.path.join(EP, path)
    for s in common.probe(p)["streams"]:
        if s["codec_type"] == ("video" if kind == "v" else "audio") and s.get("duration"):
            return float(s["duration"])
    return 0.0


def size_mb(path):
    return os.path.getsize(path) / 1e6


def loudness(path):
    """Integrated loudness (LUFS) of a media file by ffmpeg's ebur128."""
    r = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else None


# ---------------------------------------------------------------- the steps

def step_ingest(truth):
    print("1. ingest, sync")
    rc, out = pal("ingest", EP)
    src = jl("sources.json")["sources"]
    roles = {k: v.get("role") for k, v in src.items()}
    ck(rc == 0 and roles.get("camA") == "a-roll" and roles.get("mic") == "mic"
       and roles.get("b1") == "b-roll" and "music" in roles.values(), "ingest guesses a-roll, mic, b-roll, music", str(roles))
    rc, out = pal("sync", EP)
    off = jl("sources.json")["sources"]["mic"].get("offset", 99)
    ck(abs(off - truth["mic_offset"]) <= 0.04, f"sync finds the microphone offset ({off:+.3f} vs +0.740)")


def step_transcribe(truth):
    print("2. transcribe")
    rc, out = pal("transcribe", EP, "--quick")
    t = jl("transcript.raw.json")
    ck(rc == 0 and t.get("words") and t.get("segments") and "sounds" in t and "flags" in t
       and t.get("timeline") == "source" and all({"id", "w", "start", "end"} <= set(w) for w in t["words"]),
       "transcript.raw.json has the contract format", f"{len(t.get('words', []))} words")
    rc, out = pal("transcribe", "show", EP, "--raw")
    ck(rc == 0 and len(out.strip().splitlines()) <= 30, "transcribe show prints at most 30 lines",
       f"{len(out.strip().splitlines())} lines")


def covered(d, edit, tol=0.25):
    """Fraction of a planted defect (seconds, camera time) that is removed or suggested."""
    lo, hi = d["start"], d["end"]
    got = 0.0
    for r in edit["removed"]:
        if r.get("ok") is False:
            continue
        a, b = max(lo, r["in"]), min(hi, r["out"])
        got += max(0.0, b - a)
    return got / max(0.01, hi - lo)


def step_cut(truth):
    print("3. the A-cut")
    rc, out = pal("cut", "propose", EP)
    edit = jl("edit.json")
    found = {}
    for d in truth["defects"]:
        frac = covered(d, edit)
        # a retake or false start counts when its spoken part is gone; pauses when most of the gap is
        need = 0.6 if d["kind"] in ("silence_mid_sentence", "silence_between", "tail", "room_tone") else 0.8
        found[d["kind"]] = frac >= need
        ck(frac >= need, f"cut propose finds the planted {d['kind'].replace('_', ' ')} ({frac * 100:.0f}% of it)")
    rc, out = pal("cut", "render", EP, "--preview")
    ck(rc == 0 and os.path.exists(os.path.join(EP, "build/cut/acut-preview.mp4")), "cut render --preview")
    rc, out = pal("cut", "render", EP)
    kept = sum(k["out"] - k["in"] for k in edit["keep"])
    va = vdur("build/cut/voice.wav", "a")
    ck(abs(va - kept) <= 1 / 30, f"cleaned voice length = sum of kept ranges ({va:.3f} vs {kept:.3f})")
    v, a = vdur("build/cut/acut.mp4", "v"), vdur("build/cut/acut.mp4", "a")
    ck(abs(v - a) <= 1 / 30 and abs(v - kept) <= 1 / 30, f"A-cut video and audio lengths agree ({v:.3f} / {a:.3f})")
    rc, out = pal("cut", "verify", EP)
    ck(rc in (0, 1) and os.path.exists(os.path.join(EP, "build/review/seams.json")), "cut verify runs and writes seams.json")
    rc, out = pal("cut", "remap", EP)
    tj = jl("transcript.json")
    ck(rc == 0 and tj.get("timeline") == "edited" and tj.get("words"), "cut remap writes the edited transcript")
    rc, out = pal("cut", "lock", EP)
    ck(rc == 0 and jl("edit.json").get("locked"), "cut lock sets the picture-lock hash")


FA = [
    "سلام، امروز درباره تابع بازگشتی صحبت می‌کنیم.",
    "تابع بازگشتی مسئله را کوچک‌تر می‌کند.",
    "هر تابع بازگشتی یک حالت پایه می‌خواهد.",
    "فاکتوریل 5 برابر است با 5 ضرب در فاکتوریل 4.",
    "هر فراخوانی منتظر فراخوانی بعدی می‌ماند.",
    "ممنون که تماشا کردید، Python را فراموش نکنید.",
]


def write_translation():
    """translation.fa.json by hand: six lines spread over the edited timeline, one with English and digits."""
    tj = jl("transcript.json")
    segs = tj["segments"][:len(FA)]
    out = []
    for i, (s, text) in enumerate(zip(segs, FA), 1):
        out.append({"id": i, "start": s["start"], "end": s["end"], "src": s.get("text", ""), "text": text,
                    "read": "", "note": "", "skip": False})
    common.save(os.path.join(EP, "translation.fa.json"),
                {"v": 1, "from": "en", "to": "fa", "voice": None, "duration": tj.get("duration"), "glossary": {},
                 "segments": out})


def step_subs():
    print("4. subtitles")
    write_translation()
    ch = os.path.join(common.ROOT, "channel.json")
    rc, out = pal("subs", "make", EP, "--lang", "en,fa")
    files = [f"subs/{l}.{e}" for l in ("en", "fa") for e in ("srt", "vtt")]
    ck(rc == 0 and all(os.path.exists(os.path.join(EP, f)) and os.path.getsize(os.path.join(EP, f)) > 20 for f in files),
       "subs make writes en and fa .srt and .vtt", out.strip()[-120:])
    rc, out = pal("subs", "lint", os.path.join(EP, "subs/fa.srt"))
    ck(rc == 0, "subs lint passes on the Persian file", out.strip()[-160:])


def write_plan():
    """plan.json by the test: kit beats, punch, b-roll, redact, music cue, two effects."""
    tj = jl("transcript.json")
    segs = tj["segments"]
    w = lambda i: segs[i]["first"]
    wl = lambda i: segs[i]["last"]
    plan = {
        "v": 1, "edit": jl("edit.json").get("locked"), "mode": "plates",
        "sections": [{"id": "S1", "anchor": w(0), "title": "Intro"}],
        "beats": [
            {"id": "B01", "anchor": w(0), "until": wl(0), "layout": "lower-third",
             "plate": {"id": "P01", "type": "kit", "kit": "lower-third", "alpha": True},
             "text": {"en": {"name": "Test Host", "role": "Presenter"}, "fa": {"name": "مجری آزمون", "role": "Presenter"}},
             "sfx": [{"id": "pop", "at": 0.0}]},
            {"id": "B02", "anchor": w(3), "layout": "full",
             "plate": {"id": "P02", "type": "kit", "kit": "title-card", "alpha": False},
             "text": {"en": {"kicker": "Part one", "title": "The base case", "wipe": "0"},
                      "fa": {"kicker": "بخش 1", "title": "حالت پایه", "wipe": "0"}},
             "sfx": [{"id": "whoosh", "at": 0.0}]},
            {"id": "B03", "anchor": w(5), "until": wl(5), "layout": "punch", "punch": {"scale": 1.15}},
            {"id": "B04", "t": [24.0, 27.0], "layout": "b-roll", "broll": {"src": "b1", "in": 2.0}},
        ],
        "captions": {"burn": False, "style": "brand", "emphasis": []},
        "music": [{"id": "M1", "track": "music1", "t": [0.0, 30.0], "gain_db": -20, "duck": True}],
        "redact": [{"t": [12.0, 14.0], "rect": [0.60, 0.10, 0.30, 0.10]}],
    }
    common.save(os.path.join(EP, "plan.json"), plan)


def step_picture(full):
    print("5. plates, mix, review pages, composite, qc")
    write_plan()
    rc, out = pal("plates", "time", EP)
    plan = jl("plan.json")
    ck(rc == 0 and all(b.get("t") for b in plan["beats"] if b.get("plate") or b.get("punch")), "plates time gives every beat a time", out.strip()[-120:])
    rc, out = pal("plates", "stills", EP)
    stills = [f for f in os.listdir(os.path.join(EP, "build/review/stills"))] if os.path.isdir(os.path.join(EP, "build/review/stills")) else []
    ck(rc == 0 and len(stills) >= 2, f"plates stills ({len(stills)} files)", out.strip()[-120:])
    rc, out = pal("plates", "render", EP, "--draft")
    idx = jl("build/plates/index.json").get("plates", {})
    ck(rc == 0 and len(idx) >= 2 and all(os.path.exists(os.path.join(EP, e["file"])) for e in idx.values()),
       f"plates render ({len(idx)} plates)", out.strip()[-160:])
    rc, out = pal("mix", EP, "--lang", "en")
    mixf = os.path.join(EP, "build/audio/mix.en.wav")
    lt = loudness(mixf) if os.path.exists(mixf) else None
    ck(rc == 0 and lt is not None and abs(lt - (-16)) <= 1.0 and abs(dur(mixf) - dur("build/cut/voice.wav")) <= 0.05,
       f"mix: loudness {lt} LUFS, length of the voice", out.strip()[-160:])
    rc, out = pal("sheet", "seams", EP, "--flagged")
    rc, out = pal("sheet", "reel", EP)
    ck(rc == 0 and os.path.exists(os.path.join(EP, "build/review/seam-reel.m4a")), "sheet reel makes the seam reel")
    for kind in ("paper", "story"):
        rc, out = pal("board", kind, EP)
        f = os.path.join(EP, f"build/review/{kind}.html")
        ok = os.path.exists(f) and size_mb(f) < 8
        missing = [ln for ln in out.splitlines() if re.search(r"missing|not found|no .* yet|run ./pal", ln, re.I)]
        if ok:
            missing += re.findall(r'class="miss">(.{0,100})', open(f, encoding="utf-8").read())
        ck(rc == 0 and ok and not missing, f"board {kind}: file under 8 MB, no missing-input notices"
           + (f" ({size_mb(f):.1f} MB)" if ok else ""), " | ".join(missing)[:200] or out[-120:])
    # the composite: a 20 s excerpt, then the whole draft
    rc, out = pal("composite", EP, "--draft", "--range", "0-20")
    pilot = os.path.join(EP, "build/out/pilot.mp4")
    ck(rc == 0 and os.path.exists(pilot) and abs(dur(pilot) - 20) <= 0.2, "composite --range 0-20 makes a 20 s pilot", out.strip()[-160:])
    rc, out = pal("composite", EP, "--draft")
    draft = os.path.join(EP, "build/out/draft.mp4")
    ck(rc == 0 and os.path.exists(draft) and abs(dur(draft) - dur("build/cut/acut.mp4")) <= 0.1, "composite --draft covers the A-cut", out.strip()[-160:])
    if os.path.exists(draft):
        rc, out = pal("qc", draft, "--ep", EP)
        ck(rc == 0 and not re.search(r"^P0 ", out, re.M), "qc on the draft reports no P0", out.strip()[-200:])
        bad = os.path.join(OUT, "flash.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", draft, "-vf",
                        "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(n,300,301)'", "-c:a", "copy",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", bad], check=False)
        rc, out = pal("qc", bad)
        ck(rc == 1 and re.search(r"P0.*flash", out, re.I) is not None, "qc catches an injected 2-frame flash", out.strip()[-200:])
    rc, out = pal("board", "draft", EP)
    f = os.path.join(EP, "build/review/draft.html")
    missing = [ln for ln in out.splitlines() if re.search(r"missing|not found|no .* yet|run ./pal", ln, re.I)]
    if os.path.exists(f):
        missing += re.findall(r'class="miss">(.{0,100})', open(f, encoding="utf-8").read())
    ck(rc == 0 and os.path.exists(f) and size_mb(f) < 8 and not missing, "board draft: file under 8 MB, no missing-input notices",
       " | ".join(missing)[:200])
    rc, out = pal("export", EP, "--fcpxml")
    fx = os.path.join(EP, f"build/out/{os.path.basename(EP)}.fcpxml")
    ck(rc == 0 and os.path.exists(fx) and "<fcpxml" in open(fx, encoding="utf-8").read(), "export --fcpxml reads back", out.strip()[-160:])


def step_full():
    print("7. slow parts (--full)")
    import full
    full.run(ck, pal, jl, dur, loudness, EP, OUT)


def main(argv):
    """./pal test entry point."""
    if "--rebuild" in argv and os.path.isdir(OUT):
        shutil.rmtree(OUT)
    full = "--full" in argv
    t0 = time.time()
    import fixture
    truth = fixture.build()
    ck(os.path.exists(os.path.join(EP, "build/source/cam.mp4")), "fixture built", f"{truth['duration']} s")
    for d in ("sources.json", "transcript.raw.json", "transcript.json", "edit.json", "plan.json", "subs", "build/cut",
              "build/conform", "build/proxy", "build/sheets", "build/plates", "build/audio", "build/out", "build/review", "hf"):
        p = os.path.join(EP, d)
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else (os.path.exists(p) and os.remove(p))
    step_ingest(truth)
    step_transcribe(truth)
    step_cut(truth)
    step_subs()
    step_picture(full)
    if full:
        step_full()
    print(f"\n{len(passed)} passed, {len(failed)} failed, {time.time() - t0:.0f} s")
    for f in failed:
        print("  ✗ " + f)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
