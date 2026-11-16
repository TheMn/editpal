"""Delete an episode's media that can be rebuilt, to free disk.

    ./pal clean <ep> [--all] [--dry]

Default: build/cut, plates, chunks, review, jobs, sheets, proxy and any half-finished `.part` files.
`--all`: everything in build/ except out/ (the finished files); the sources can then be fetched
again with `./pal restore`, so it refuses (exit 3) when a source has no Drive id. `--dry` only
says what would go. Text files of the episode are never touched.
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

REBUILDABLE = ("cut", "plates", "chunks", "review", "jobs", "sheets", "proxy")


def size_of(path):
    """Bytes in a file or folder."""
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(path) for f in fs
               if os.path.exists(os.path.join(d, f)))


def main(argv):
    """Entry point for ./pal clean."""
    ap = argparse.ArgumentParser(prog="pal clean")
    ap.add_argument("ep")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    ep = C.episode(a.ep)
    b = os.path.join(ep, "build")
    if not os.path.isdir(b):
        print("✓ nothing in build/")
        return 0
    if a.all:
        srcs = C.load(os.path.join(ep, "sources.json"), default={}).get("sources", {})
        lost = [sid for sid, s in srcs.items() if not s.get("drive_id")
                and os.path.exists(os.path.join(ep, s["file"]))]
        if lost:
            print(f"✗ {', '.join(lost)} exist only on this machine (no Drive id). Upload them to the Drive "
                  "folder and ./pal drive get again, or use plain `clean` (without --all).", file=sys.stderr)
            return 3
        targets = [os.path.join(b, n) for n in sorted(os.listdir(b)) if n != "out"]
    else:
        targets = [os.path.join(b, n) for n in REBUILDABLE if os.path.exists(os.path.join(b, n))]
        targets += [os.path.join(d, f) for d, _, fs in os.walk(b) for f in fs if f.endswith(".part")
                    and not os.path.relpath(d, b).startswith("out")]
    total, rows = 0, []
    for t in targets:
        if not os.path.exists(t):
            continue
        n = size_of(t)
        total += n
        rows.append(f"  {C.rel(ep, t)}  {n / 1e6:.0f} MB")
        if not a.dry:
            shutil.rmtree(t) if os.path.isdir(t) else os.remove(t)
    C.say(f"✓ {'would free' if a.dry else 'freed'} {total / 1e9:.2f} GB", *rows)
    if a.all and not a.dry:
        print(f"  rebuild with: ./pal restore {os.path.basename(ep)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
