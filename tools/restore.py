"""Rebuild an episode's media from Drive: download the sources again, then conform, proxy, sheets.

    ./pal restore <ep>

For a fresh checkout or after `./pal clean --all`. Every source in sources.json that is missing
from build/source/ is downloaded again by its Drive id (recorded by `./pal drive get`), then
`./pal ingest` redoes whatever in build/conform, build/proxy and build/sheets is missing. Exits 3
when a missing source has no Drive id (it must be uploaded again) or the disk would be too small.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import drive  # noqa: E402
import ingest  # noqa: E402


def main(argv):
    """Entry point for ./pal restore."""
    if len(argv) != 1 or argv[0].startswith("-"):
        print(__doc__.strip())
        return 2
    ep = C.episode(argv[0])
    srcs = C.load(os.path.join(ep, "sources.json"), default={}).get("sources", {})
    if not srcs:
        C.die("no sources.json for this episode: nothing to restore. Start with ./pal drive get.")
    missing = {sid: s for sid, s in srcs.items() if not os.path.exists(os.path.join(ep, s["file"]))}
    lost = [sid for sid, s in missing.items() if not s.get("drive_id")]
    if lost:
        print(f"✗ no Drive id for {', '.join(lost)}: upload them to the Drive folder again, "
              "then ./pal drive get.", file=sys.stderr)
        return 3
    sized = {sid: drive.file_size(s["drive_id"]) for sid, s in missing.items()}
    need = sum(n or 0 for n in sized.values()) * drive.SPACE_FACTOR
    if need > C.free_gb(ep if os.path.isdir(ep) else C.ROOT) * 1e9:
        print(f"✗ restoring needs about {drive.gb(need)}; not enough free disk.", file=sys.stderr)
        return 3
    for sid, s in missing.items():
        print(f"· downloading {s['file']}", file=sys.stderr, flush=True)
        drive.download(s["drive_id"], os.path.join(ep, s["file"]), sized[sid])
    code = ingest.main([ep])
    if not code:
        print(f"✓ restored {len(missing)} source file(s)")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
