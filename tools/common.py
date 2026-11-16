"""Shared helpers for every ./pal command: paths, JSON, ffmpeg, the frame grid, short output.

Rules every command follows (docs/TOOLS.md):
  - an episode argument is its folder or any unique part of its name ("recursion");
  - media lives in <episode>/build/ (never in git), text files next to it (in git);
  - times in JSON are seconds on the frame grid of the project (sources.json "fps");
  - print at most ~30 lines; write long tables to a file and print its path;
  - exit codes: 0 done, 1 failed, 2 wrong usage, 3 needs something from the creator.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.expanduser(os.environ.get("EDITPAL_CACHE", "~/.cache/editpal"))
EPISODES = os.path.join(ROOT, "episodes")


def die(msg, code=1):
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(code)


def say(*lines, limit=30):
    """Print lines, at most `limit`; the rest is counted, not shown (keeps agent context small)."""
    lines = [ln for block in lines for ln in str(block).splitlines()]
    for ln in lines[:limit]:
        print(ln)
    if len(lines) > limit:
        print(f"… {len(lines) - limit} more lines not shown")


def load(path, default=None):
    if not os.path.exists(path):
        if default is not None:
            return default
        die(f"missing {os.path.relpath(path, ROOT)}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def channel():
    """channel.json (written by /setup). Missing keys fall back to the template's defaults."""
    return load(os.path.join(ROOT, "channel.json"), default={})


def episode(arg):
    """Resolve 'episodes/2026-12-recursion', '2026-12-recursion' or 'recursion' to the folder."""
    if os.path.isdir(arg) and os.path.exists(os.path.join(arg, "episode.md")):
        return os.path.abspath(arg).rstrip("/")
    names = sorted(n for n in os.listdir(EPISODES)
                   if os.path.isdir(os.path.join(EPISODES, n)) and not n.startswith("_"))
    key = os.path.basename(arg.rstrip("/")).lower()
    hits = [n for n in names if n.lower() == key] or [n for n in names if key in n.lower()]
    if len(hits) == 1:
        return os.path.join(EPISODES, hits[0])
    die(f"no episode matches '{arg}'" if not hits else f"'{arg}' matches several: {', '.join(hits)}", 2)


def build(ep, *parts):
    """Path inside <episode>/build/, with its folder created."""
    p = os.path.join(ep, "build", *parts)
    os.makedirs(p if not os.path.splitext(p)[1] else os.path.dirname(p), exist_ok=True)
    return p


def rel(ep, path):
    return os.path.relpath(path, ep)


def resolve(ep, path):
    """A file named in a command: as given, else relative to the episode folder (build/out/draft.mp4)."""
    if os.path.exists(path):
        return path
    alt = os.path.join(ep, path)
    return alt if os.path.exists(alt) else path


def run(cmd, quiet=True, **kw):
    """Run a command (list). ffmpeg/ffprobe get -v error and -y. Dies with the tool's own message."""
    cmd = [str(c) for c in cmd]
    if cmd[0] == "ffmpeg" and "-v" not in cmd:
        cmd = ["ffmpeg", "-v", "error", "-y"] + cmd[1:]
    r = subprocess.run(cmd, capture_output=quiet, text=True, **kw)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-6:] if quiet else []
        die(f"{cmd[0]} failed: " + " | ".join(tail))
    return r


def probe(path):
    """ffprobe as a dict: {"format": {...}, "streams": [...]}."""
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    return json.loads(r.stdout)


def duration(path):
    return float(probe(path)["format"]["duration"])


def snap(t, fps):
    """A time on the frame grid."""
    return round(round(float(t) * fps) / fps, 4)


def fps_of(ep):
    return float(load(os.path.join(ep, "sources.json"), default={}).get("fps")
                 or channel().get("video", {}).get("fps", 30))


def sha(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, ensure_ascii=False).encode() if not isinstance(p, bytes) else p)
    return h.hexdigest()[:16]


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def free_gb(path=ROOT):
    return shutil.disk_usage(path).free / 1e9


def tc(t):
    """Seconds -> m:ss.s for people (1:02.4)."""
    t = max(0.0, float(t))
    return f"{int(t // 60)}:{t % 60:04.1f}"
