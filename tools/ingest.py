"""Probe every file in build/source/, guess what each is, conform it, make proxies and contact sheets.

    ./pal ingest <ep> [--roles camA=a-roll,mic=mic] [--force]

Reads every file under <ep>/build/source/ (folders included). Roles: a-roll (the longest video with
speech), screen, mic (long audio only), b-roll, image, music (audio in a "music" folder),
voice-clip (short audio named voice/sample), subtitles (.srt .vtt .sbv), script (.txt .md .docx).
Roles already in sources.json are kept on a re-run; `--roles id=role,…` corrects a guess.
The project frame rate is channel.json video.fps when the master is within 0.5 of it, else the
nearest of 24/25/30/50/60. Each video is conformed to build/conform/<id>.mp4 (constant frame rate,
HDR tone-mapped to SDR, upright, yuv420p, x264 CRF 16, a keyframe every second, AAC 48 kHz); each
source with sound also gets build/conform/<id>.wav (48 kHz mono). Also build/proxy/<id>.mp4 (960 px
wide) and build/sheets/<id>.jpg (timestamped contact sheet). Writes sources.json; finished sources
are skipped on a re-run (--force redoes them). Long recordings take a while: run in the background.
"""
import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

VERSION = 2
VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".m2ts", ".mxf", ".mpg", ".mpeg", ".3gp"}
AUDIO = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aif", ".aiff", ".wma"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif", ".bmp", ".tif", ".tiff"}
TEXTS = {".srt": "subtitles", ".vtt": "subtitles", ".sbv": "subtitles",
         ".txt": "script", ".md": "script", ".docx": "script"}
ROLES = {"a-roll", "screen", "mic", "b-roll", "image", "music", "voice-clip", "subtitles", "script", "other"}
FPS_CHOICES = (24, 25, 30, 50, 60)
CAMERA_RATIOS = (16 / 9, 9 / 16, 4 / 3, 3 / 4, 1.0, 3 / 2, 2 / 3, 21 / 9)
PREFIX = {"a-roll": "cam", "screen": "screen", "mic": "mic", "b-roll": "b", "image": "img", "music": "music",
          "voice-clip": "voice", "subtitles": "subs", "script": "script", "other": "file"}


def threads():
    """ffmpeg thread options from EDITPAL_THREADS (default: ffmpeg decides)."""
    n = os.environ.get("EDITPAL_THREADS")
    return ["-threads", n] if n else []


def ratio(s):
    """'30000/1001' -> 29.97."""
    try:
        a, b = s.split("/")
        return float(a) / float(b) if float(b) else 0.0
    except (ValueError, AttributeError):
        return 0.0


# ---------------------------------------------------------------- probing

def find_files(src_dir):
    """All files under build/source/, relative paths, sorted; hidden files and partial downloads skipped."""
    out = []
    for d, dirs, files in os.walk(src_dir):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        out += [os.path.join(d, f) for f in sorted(files) if not f.startswith(".") and not f.endswith(".part")]
    return out


def probe_media(path):
    """Facts about one media file: duration, size (upright), fps, vfr, hdr, rotation, audio."""
    p = C.probe(path)
    v = next((s for s in p["streams"] if s["codec_type"] == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in p["streams"] if s["codec_type"] == "audio"), None)
    info = {"duration": round(float(p["format"].get("duration") or 0), 3), "audio": a is not None, "video": v is not None}
    if v:
        rot = int(v.get("tags", {}).get("rotate", 0) or 0)
        for sd in v.get("side_data_list", []):
            if "rotation" in sd:
                rot = int(sd["rotation"])
        rot %= 360
        w, h = int(v["width"]), int(v["height"])
        if rot in (90, 270):
            w, h = h, w
        r, avg = ratio(v.get("r_frame_rate")), ratio(v.get("avg_frame_rate"))
        info.update(size=[w, h], fps_in=round(avg or r, 3), rotation=rot,
                    vfr=bool(avg and r and abs(r - avg) / r > 0.005),
                    hdr=v.get("color_transfer") in ("smpte2084", "arib-std-b67"),
                    transfer=v.get("color_transfer", ""), primaries=v.get("color_primaries", ""))
        info["frames"] = int(v.get("nb_frames") or 0)
        info["still"] = os.path.splitext(path)[1].lower() in IMAGE
    return info


def mean_volume(path, seconds=120):
    """Mean level in dB over the first minutes (ffmpeg volumedetect); None when it cannot be told."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-t", str(seconds), "-i", path, "-vn", "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else None


def fingerprint(path):
    """Size plus the hash of the first and last megabyte: enough to tell a changed file, and fast."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(1 << 20)
        f.seek(max(0, size - (1 << 20)))
        tail = f.read(1 << 20)
    return C.sha(size, head, tail)


# ---------------------------------------------------------------- roles

def is_camera_size(size):
    """True when the picture has a shape cameras make (not a 16:10 laptop screen)."""
    r = size[0] / size[1]
    return any(abs(r / c - 1) < 0.02 for c in CAMERA_RATIOS)


def guess_roles(files, infos):
    """{path: role} by the rules in the module docstring."""
    roles = {}
    vids = [p for p in files if infos[p].get("video") and not infos[p].get("still")]
    talk = [p for p in vids if infos[p]["audio"] and (infos[p].get("level") or -99) > -50
            and not re.search(r"screen|capture|display", os.path.basename(p), re.I)
            and is_camera_size(infos[p]["size"])]
    main = max(talk, key=lambda p: infos[p]["duration"], default=None)
    for p in files:
        ext, name, i = os.path.splitext(p)[1].lower(), os.path.basename(p).lower(), infos[p]
        parts = [x.lower() for x in p.split(os.sep)]
        if ext in TEXTS:
            roles[p] = TEXTS[ext]
        elif ext in IMAGE or i.get("still"):
            roles[p] = "image"
        elif i.get("video"):
            if p == main:
                roles[p] = "a-roll"
            elif re.search(r"screen|capture|display", name) or not is_camera_size(i["size"]) or \
                    (not i["audio"] and i["duration"] > 60):
                roles[p] = "screen"
            elif main and p in talk and i["duration"] >= 0.6 * infos[main]["duration"]:
                roles[p] = "a-roll"                                  # a second angle of the same talk
            else:
                roles[p] = "b-roll"
        elif ext in AUDIO:
            if "music" in parts[:-1]:
                roles[p] = "music"
            elif i["duration"] < 20 and re.search(r"voice|sample|ref", name):
                roles[p] = "voice-clip"
            elif i["duration"] >= 20:
                roles[p] = "mic"
            else:
                roles[p] = "other"
        else:
            roles[p] = "other"
    return roles


def new_id(role, taken):
    """camA, camB… for a-roll; screen, screen2…; mic, mic2…; b1, b2…; img1…"""
    pre = PREFIX[role]
    if role == "a-roll":
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if pre + ch not in taken:
                return pre + ch
    if role in ("screen", "mic") and pre not in taken:
        return pre
    n = 2 if role in ("screen", "mic") else 1
    while f"{pre}{n}" in taken:
        n += 1
    return f"{pre}{n}"


def pick_fps(master_fps):
    """The project frame rate: the channel's if the master is within 0.5 of it, else the nearest standard one."""
    want = float(C.channel().get("video", {}).get("fps", 30))
    if not master_fps or abs(master_fps - want) <= 0.5:
        return want
    return float(min(FPS_CHOICES, key=lambda f: abs(f - master_fps)))


# ---------------------------------------------------------------- conforming

TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
           "zscale=t=bt709:m=bt709:r=tv")


def conform_video(src, dst, info, fps):
    """Constant frame rate, SDR bt709, upright (ffmpeg rotates by itself), yuv420p, a keyframe every second."""
    vf = ([TONEMAP] if info["hdr"] else []) + [f"fps={fps:g}", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "format=yuv420p"]
    cmd = ["ffmpeg", "-i", src, "-map", "0:v:0", "-vf", ",".join(vf), "-fps_mode", "cfr",
           "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-g", f"{int(round(fps))}",
           "-keyint_min", f"{int(round(fps))}", "-sc_threshold", "0", "-pix_fmt", "yuv420p",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
    cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"] if info["audio"] else ["-an"]
    C.run(cmd + threads() + ["-movflags", "+faststart", dst + ".part.mp4"])
    os.replace(dst + ".part.mp4", dst)


def conform_wav(src, dst):
    """The sound as 48 kHz mono 16-bit WAV (what sync and transcribe read)."""
    C.run(["ffmpeg", "-i", src, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le"]
          + threads() + [dst + ".part.wav"])
    os.replace(dst + ".part.wav", dst)


def make_proxy(conform, dst, fps):
    """960 px wide copy for fast looking and editing."""
    g = f"{int(round(fps))}"
    C.run(["ffmpeg", "-i", conform, "-vf", "scale='min(960,iw)':-2", "-c:v", "libx264", "-crf", "26", "-preset", "veryfast",
           "-g", g, "-keyint_min", g, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k"] + threads()
          + ["-movflags", "+faststart", dst + ".part.mp4"])
    os.replace(dst + ".part.mp4", dst)


def font():
    """A font file for the time stamps (the brand's, else a system one), or None."""
    brand = os.path.join(C.ROOT, "brand", "fonts")
    pool = [os.path.join(brand, f) for f in sorted(os.listdir(brand))] if os.path.isdir(brand) else []
    pool += ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
             "/System/Library/Fonts/Supplemental/Arial.ttf", "C:/Windows/Fonts/arial.ttf"]
    return next((p for p in pool if p.lower().endswith((".ttf", ".otf")) and os.path.exists(p)), None)


def contact_sheet(media, dst, duration, cols=6, tiles=36):
    """One JPEG of evenly spaced frames, each stamped with its time."""
    every = max(2, int(duration / tiles + 0.999))
    ff = font()
    stamp = (f"drawtext=fontfile='{ff}':text='%{{pts\\:hms}}':x=4:y=h-th-4:fontsize=18:fontcolor=white:"
             "box=1:boxcolor=black@0.6") if ff else None
    rows = max(1, -(-int(duration / every + 0.999) // cols))
    vf = ",".join([f"fps=1/{every}", "scale=240:-2"] + ([stamp] if stamp else []) + [f"tile={cols}x{rows}"])
    C.run(["ffmpeg", "-i", media, "-vf", vf, "-frames:v", "1", "-q:v", "4"] + threads() + [dst])


# ---------------------------------------------------------------- the command

def main(argv):
    """Entry point for ./pal ingest."""
    ap = argparse.ArgumentParser(prog="pal ingest", description="probe, conform, proxy, contact sheets")
    ap.add_argument("ep")
    ap.add_argument("--roles", default="", help="id=role,id=role: correct a guess (roles: " + ", ".join(sorted(ROLES)) + ")")
    ap.add_argument("--force", action="store_true", help="redo finished sources")
    a = ap.parse_args(argv)
    ep = C.episode(a.ep)
    src_dir = os.path.join(ep, "build", "source")
    files = find_files(src_dir) if os.path.isdir(src_dir) else []
    if not files:
        C.die("build/source/ is empty. Download the recordings first: ./pal drive get <folder> <episode>", 3)
    sj_path = os.path.join(ep, "sources.json")
    old = C.load(sj_path, default={}).get("sources", {})
    drive = C.load(os.path.join(src_dir, ".drive.json"), default={})
    overrides = {}
    for pair in filter(None, a.roles.split(",")):
        k, _, v = pair.partition("=")
        if v not in ROLES:
            C.die(f"--roles: '{pair}' is not id=role with a role from: {', '.join(sorted(ROLES))}", 2)
        overrides[k.strip()] = v

    rels = {p: C.rel(ep, p) for p in files}
    by_file = {s["file"]: sid for sid, s in old.items() if "file" in s}
    infos = {}
    for p in files:
        ext = os.path.splitext(p)[1].lower()
        if ext in TEXTS:
            infos[p] = {"duration": 0, "audio": False, "video": False}
            continue
        if ext in IMAGE:
            try:
                infos[p] = probe_media(p)
            except SystemExit:
                infos[p] = {"duration": 0, "audio": False, "video": False}
            infos[p]["still"] = True
            infos[p]["audio"] = False
            continue
        try:
            infos[p] = probe_media(p)
        except SystemExit:
            print(f"! {os.path.basename(p)}: not readable media, kept as 'other'", file=sys.stderr)
            infos[p] = {"duration": 0, "audio": False, "video": False}
            continue
        if infos[p]["audio"]:
            infos[p]["level"] = mean_volume(p)
    guessed = guess_roles(files, infos)

    sources, taken = {}, set(by_file.values())
    for p in files:
        sid = by_file.get(rels[p])
        role = old[sid]["role"] if sid else guessed[p]
        if not sid:
            sid = new_id(role, taken)
            taken.add(sid)
        sources[sid] = {"role": role, "file": rels[p]}
        if rels[p] in drive:
            sources[sid]["drive_id"] = drive[rels[p]]
    for sid, role in overrides.items():
        if sid not in sources:
            C.die(f"--roles: no source '{sid}' (have: {', '.join(sources)})", 2)
        sources[sid]["role"] = role

    paths = {sid: os.path.join(ep, s["file"]) for sid, s in sources.items()}
    videos = {sid: probe_media(p) for sid, p in paths.items() if infos[p].get("video") and not infos[p].get("still")}
    arolls = [sid for sid, s in sources.items() if s["role"] == "a-roll" and sid in videos]
    pool = arolls or [sid for sid in videos if sources[sid]["role"] == "screen"] or list(videos)
    master = max(pool, key=lambda s: videos[s]["duration"]) if pool else None
    mics = [sid for sid, s in sources.items() if s["role"] == "mic"]
    audio_master = (mics[0] if mics else master if master and videos[master]["audio"] else None)
    fps = pick_fps(videos[master]["fps_in"] if master else 0)
    size = videos[master]["size"] if master else C.channel().get("video", {}).get("size", [1920, 1080])

    os.makedirs(os.path.join(ep, "build", "conform"), exist_ok=True)
    for sid, s in sources.items():
        p = paths[sid]
        info = infos[p]
        fp = fingerprint(p)
        prev = old.get(sid, {})
        s["sha"] = fp
        if info.get("video") and not info.get("still"):
            s.update({k: info[k] for k in ("duration", "size", "fps_in", "vfr", "hdr", "rotation", "audio")})
        elif info.get("audio"):
            s.update(duration=info["duration"], audio=True)
        done = (prev.get("sha") == fp and prev.get("v") == VERSION and prev.get("fps") == fps and not a.force
                and all(os.path.exists(os.path.join(ep, prev[k])) for k in ("conform", "proxy", "sheet", "wav") if k in prev)
                and "conform" in prev)
        if done or not (info.get("audio") or info.get("video")) or info.get("still"):
            if done:
                s.update({k: prev[k] for k in ("conform", "proxy", "sheet", "wav", "offset", "drift", "v", "fps") if k in prev})
            else:
                s["offset"] = prev.get("offset", 0.0)
            continue
        print(f"· {sid} ({s['role']}, {C.tc(info['duration'])}): conforming", file=sys.stderr, flush=True)
        wav = f"build/conform/{sid}.wav"
        if info["audio"]:
            conform_wav(p, os.path.join(ep, wav))
            s["wav"] = wav
        if info.get("video"):
            cm, px, sh = f"build/conform/{sid}.mp4", f"build/proxy/{sid}.mp4", f"build/sheets/{sid}.jpg"
            for d in (cm, px, sh):
                os.makedirs(os.path.dirname(os.path.join(ep, d)), exist_ok=True)
            conform_video(p, os.path.join(ep, cm), info, fps)
            make_proxy(os.path.join(ep, cm), os.path.join(ep, px), fps)
            contact_sheet(os.path.join(ep, px), os.path.join(ep, sh), info["duration"])
            s.update(conform=cm, proxy=px, sheet=sh)
        else:
            s["conform"] = wav
        s["offset"] = prev.get("offset", 0.0)
        s["v"], s["fps"] = VERSION, fps

    for s in sources.values():
        s.pop("v", None) if "conform" not in s else None
    out = {"v": 1, "fps": fps, "size": size, "master": master, "audio_master": audio_master, "sources": sources}
    C.save(sj_path, out)
    table(out)
    return 0


def table(out):
    """Print one line per source."""
    rows = ["id        role        length    picture          notes"]
    for sid, s in out["sources"].items():
        pic = f"{s['size'][0]}x{s['size'][1]} {s['fps_in']:g}" if "size" in s else "-"
        notes = [n for n, on in (("HDR→SDR", s.get("hdr")), ("variable fps→cfr", s.get("vfr")),
                                 (f"rotated {s.get('rotation')}", s.get("rotation")),
                                 ("no sound", s.get("size") and not s.get("audio")),
                                 ("MASTER", sid == out["master"]), ("audio master", sid == out["audio_master"])) if on]
        rows.append(f"{sid:<9} {s['role']:<11} {C.tc(s.get('duration', 0)):<9} {pic:<16} {', '.join(notes)}")
    C.say(f"✓ project {out['fps']:g} fps, {out['size'][0]}x{out['size'][1]}", *rows,
          "  wrong guess? ./pal ingest <episode> --roles id=role")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
