"""Check the machine, the channel files and how old the upstream pins are.

    ./pal doctor

One line per check, ✓ or ✗ with what to do. Checks ffmpeg (libass, zscale, libx264, prores_ks),
Node 22+, the Python environment (.venv, pinned packages), every model in tools/models.json,
free disk, channel.json (name, Drive link, languages), brand fonts, the upload link variable,
and the age of each pin in tools/versions.json (older than 30 days: re-check it). Exit 1 if a
required check fails.
"""
import datetime
import importlib.metadata
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

MIN_FREE_GB = 10
STALE_DAYS = 30
VENV_PY = os.path.join(C.ROOT, ".venv", "bin", "python")
OPTIONAL = {"upload", "fonts"}


def out(cmd):
    """Text output of a command, or '' when it cannot run."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.stdout + r.stderr
    except (OSError, subprocess.SubprocessError):
        return ""


def check_ffmpeg():
    """ffmpeg and the parts editpal needs."""
    if not out(["ffmpeg", "-version"]):
        return False, "ffmpeg is missing: install ffmpeg 6+ (apt-get install ffmpeg)"
    filters, enc = out(["ffmpeg", "-hide_banner", "-filters"]), out(["ffmpeg", "-hide_banner", "-encoders"])
    miss = [n for n, ok in (("libass", " ass " in filters), ("zscale", "zscale" in filters),
                            ("libx264", "libx264" in enc), ("prores_ks", "prores_ks" in enc)) if not ok]
    ver = out(["ffmpeg", "-version"]).split()[2]
    return (not miss, f"ffmpeg {ver}" if not miss else f"ffmpeg {ver} lacks {', '.join(miss)}: install a full build")


def check_node():
    """Node 22 or newer."""
    v = out(["node", "--version"]).strip()
    m = re.match(r"v(\d+)", v)
    return bool(m and int(m.group(1)) >= 22), f"node {v}" if m and int(m.group(1)) >= 22 else \
        f"node {v or 'missing'}: HyperFrames needs Node 22+ (install it, e.g. from nodejs.org)"


def pins(path):
    """{package: version} from the `name==version` lines of a requirements file."""
    found = {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            m = re.match(r"\s*([A-Za-z0-9_.\-]+)==([\w.\-+]+)", ln)
            if m:
                found[m.group(1)] = m.group(2)
    return found


def check_python():
    """The .venv exists and has the pinned packages."""
    if not os.path.exists(VENV_PY):
        return False, ".venv is missing: run sh tools/setup.sh"
    want = {}
    for f in ("requirements.txt", "requirements-media.txt"):
        want.update(pins(os.path.join(C.ROOT, "tools", f)))
    code = ("import importlib.metadata as m,sys,json;r={}\nfor n in json.loads(sys.argv[1]):\n try: r[n]=m.version(n)\n"
            " except Exception: r[n]=None\nprint(json.dumps(r))")
    import json
    try:
        have = json.loads(out([VENV_PY, "-c", code, json.dumps(list(want))]).strip().splitlines()[-1])
    except (ValueError, IndexError):
        return False, ".venv does not run: delete it and run sh tools/setup.sh"
    bad = [f"{n} {have[n] or 'missing'} (want {v})" for n, v in want.items() if have.get(n) != v]
    return (not bad), (f"python packages: {len(want)} pinned, all present" if not bad
                       else "python packages differ: " + ", ".join(bad[:4]) + ". Run sh tools/setup.sh")


def model_parts(entry):
    """[(folder name, files)] of a models.json entry, whether flat or in parts."""
    if "files" in entry:
        return [(entry["dir"], entry["files"])]
    return [(p["dir"], p["files"]) for p in entry.values() if isinstance(p, dict) and "files" in p]


def check_models():
    """One result per model in tools/models.json: all its files in the cache."""
    res = []
    for key, entry in C.load(os.path.join(C.ROOT, "tools", "models.json"), default={}).items():
        miss = [f for d, fs in model_parts(entry) for f in fs
                if not os.path.exists(os.path.join(C.CACHE, d, f))]
        res.append((key, not miss, f"model {key}" if not miss else
                    f"model {key}: {len(miss)} file(s) missing in {C.CACHE}. Run sh tools/setup.sh"))
    return res


def check_disk():
    """Free disk."""
    g = C.free_gb()
    return g >= MIN_FREE_GB, f"disk {g:.0f} GB free" if g >= MIN_FREE_GB else \
        f"disk {g:.0f} GB free: need {MIN_FREE_GB}+; ./pal clean <episode> --all frees the most"


def check_channel():
    """channel.json has the facts the tools need."""
    ch = C.channel()
    miss = [n for n, v in (("name", ch.get("name")), ("drive link", ch.get("drive")),
                           ("languages.spoken", ch.get("languages", {}).get("spoken"))) if not v]
    return (not miss), "channel.json filled in" if not miss else f"channel.json lacks {', '.join(miss)}: run /setup"


def check_fonts():
    """Brand fonts present."""
    d = os.path.join(C.ROOT, "brand", "fonts")
    n = len([f for f in os.listdir(d) if f.lower().endswith((".ttf", ".otf", ".woff", ".woff2"))]) if os.path.isdir(d) else 0
    return n > 0, f"brand/fonts: {n} font file(s)" if n else "brand/fonts is empty: run /setup (brand) to add the channel's fonts"


def check_upload():
    """The upload link variable."""
    env = C.channel().get("upload", {}).get("env", "EDITPAL_UPLOAD_URL")
    ok = bool(os.environ.get(env))
    return ok, f"${env} set (./pal drive put works)" if ok else \
        f"${env} not set: ./pal drive put cannot upload; follow docs/DRIVE.md"


def check_versions():
    """Age of each pin in tools/versions.json; stale ones come with the file's own instruction."""
    j = C.load(os.path.join(C.ROOT, "tools", "versions.json"), default={})
    res, today, stale = [], datetime.date.today(), False
    for name, e in j.get("checked", {}).items():
        try:
            age = (today - datetime.date.fromisoformat(e["date"])).days
        except (KeyError, ValueError):
            age = 9999
        old = age > STALE_DAYS
        stale |= old
        res.append((f"pin {name}", not old, f"pin {name} {e.get('pin', '?')} checked {e.get('date', '?')} "
                    f"({age} days ago)" + (f" - OLD: see {e.get('source', 'its release notes')}" if old else "")))
    if stale and j.get("$comment"):
        res.append(("pin-help", True, "  → " + j["$comment"]))
    return res


def main(argv):
    """Entry point for ./pal doctor."""
    if argv:
        print(__doc__.strip())
        return 2
    rows = [("ffmpeg",) + check_ffmpeg(), ("node",) + check_node(), ("python",) + check_python()]
    rows += check_models()
    rows += [("disk",) + check_disk(), ("channel",) + check_channel(), ("fonts",) + check_fonts(),
             ("upload",) + check_upload()] + check_versions()
    lines, failed = [], 0
    for key, ok, msg in rows:
        if key == "pin-help":
            lines.append(msg)
            continue
        lines.append(("✓ " if ok else "✗ ") + msg)
        failed += (not ok) and key not in OPTIONAL
    lines.append("all required checks pass" if not failed else f"{failed} required check(s) failed")
    C.say(*lines, limit=40)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
