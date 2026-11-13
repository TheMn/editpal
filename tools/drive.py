"""Get recordings from the channel's shared Google Drive folder, and send results back.

    ./pal drive list
    ./pal drive get <folder> <ep> [--only "*.mov"] [--force]
    ./pal drive put <ep> <file>…

`list` shows every file in the shared folder (channel.json "drive"), by subfolder, with sizes.
No login is needed: the folder is shared as "anyone with the link can view".
`get` downloads one subfolder (any unique part of its name; "." = files at the top level) into <ep>/build/source/ and records each
file's Drive id in build/source/.drive.json (so `./pal restore` can fetch them again). It refuses,
with exit 3, when less than 2.2x the download size is free on disk (the conform needs room); --force
skips that check. Finished files are skipped; interrupted ones resume.
`put` uploads files to the creator's output folder (Drive "<upload.folder>/<episode>/") through
the upload link kept in the environment variable named by channel.json upload.env, and prints a
link for each file. Without that link it exits 3: follow docs/DRIVE.md.
"""
import argparse
import fnmatch
import json
import mimetypes
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

DL = "https://drive.usercontent.google.com/download"
CHUNK = 32 * 1024 * 1024
SPACE_FACTOR = 2.2


# ---------------------------------------------------------------- listing

def folder_id():
    """The shared folder's id from channel.json, or exit 3."""
    link = C.channel().get("drive", "")
    m = re.search(r"/folders/([\w-]+)", link) or re.fullmatch(r"([\w-]{20,})", link or "")
    if not m:
        C.die("channel.json has no Drive folder link. Run /setup (or put the 'anyone with the link' "
              "folder link in channel.json → drive). See docs/DRIVE.md.", 3)
    return m.group(1)


def list_files():
    """[{id, path}] for every file in the shared folder (path is relative to it)."""
    import gdown
    try:
        got = gdown.download_folder(id=folder_id(), skip_download=True, quiet=True, remaining_ok=True, use_cookies=False)
    except Exception as e:  # gdown raises plain exceptions for private or missing folders
        C.die(f"could not read the Drive folder ({e}). Is it shared as 'anyone with the link'? See docs/DRIVE.md.", 3)
    if got is None:
        C.die("the Drive folder could not be listed. Is it shared as 'anyone with the link'? See docs/DRIVE.md.", 3)
    return sorted(({"id": g.id, "path": g.path.replace(os.sep, "/")} for g in got), key=lambda f: f["path"].lower())


def file_size(fid):
    """Size in bytes from the download headers (None when Drive does not say)."""
    try:
        with requests.get(DL, params={"id": fid, "export": "download", "confirm": "t"}, stream=True, timeout=30) as r:
            if r.status_code != 200 or "text/html" in r.headers.get("content-type", ""):
                return None
            return int(r.headers["content-length"]) if "content-length" in r.headers else None
    except requests.RequestException:
        return None


def with_sizes(files):
    """Add 'size' to each file (looked up in parallel)."""
    with ThreadPoolExecutor(8) as ex:
        for f, n in zip(files, ex.map(lambda f: file_size(f["id"]), files)):
            f["size"] = n
    return files


def gb(n):
    return f"{(n or 0) / 1e9:.2f} GB" if (n or 0) >= 1e8 else f"{(n or 0) / 1e6:.1f} MB"


def cmd_list(argv):
    """`drive list`."""
    files = with_sizes(list_files())
    if not files:
        print("the Drive folder is empty")
        return 0
    rows, last = [], None
    for f in files:
        top, _, rest = f["path"].partition("/")
        if not rest:
            top, rest = "(top level)", f["path"]
        if top != last:
            rows.append(f"{top}/")
            last = top
        rows.append(f"  {rest}  {gb(f['size']) if f['size'] else '?'}")
    out = os.path.join(C.CACHE, "drive-list.txt")
    os.makedirs(C.CACHE, exist_ok=True)
    C.say(*rows, limit=30)
    if len(rows) > 30:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(rows) + "\n")
        print(f"full list: {out}")
    return 0


# ---------------------------------------------------------------- download

def download(fid, dest, size):
    """Stream one file to dest.part, resuming a partial one, then rename. Dies on an HTML error page."""
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(1, 6):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with requests.get(DL, params={"id": fid, "export": "download", "confirm": "t"}, headers=headers,
                              stream=True, timeout=60) as r:
                if "text/html" in r.headers.get("content-type", ""):
                    C.die("Drive sent a web page instead of the file (quota exceeded or not shared). "
                          "Wait an hour or check the sharing, then run the command again.", 3)
                if r.status_code == 416 and size and have == size:
                    break
                if r.status_code not in (200, 206):
                    raise requests.RequestException(f"HTTP {r.status_code}")
                if r.status_code == 200:
                    have = 0
                with open(part, "ab" if have else "wb") as out:
                    for chunk in r.iter_content(1 << 20):
                        out.write(chunk)
            break
        except requests.RequestException as e:
            print(f"! download interrupted ({e}); retry {attempt}/5", file=sys.stderr)
            time.sleep(2 * attempt)
    else:
        C.die(f"could not finish {os.path.basename(dest)}; run the same command again to resume.")
    if size and os.path.getsize(part) != size:
        C.die(f"{os.path.basename(dest)} is {os.path.getsize(part)} bytes, expected {size}; run again to resume.")
    os.replace(part, dest)


def pick_folder(files, name):
    """Files of the subfolder whose name equals or uniquely contains `name`."""
    tops = sorted({f["path"].split("/")[0] for f in files if "/" in f["path"]})
    hit = [t for t in tops if t.lower() == name.lower()] or [t for t in tops if name.lower() in t.lower()]
    if len(hit) != 1:
        C.die(f"'{name}' " + ("matches no folder" if not hit else "matches several: " + ", ".join(hit))
              + (f". Folders: {', '.join(tops)}" if tops else ". The Drive folder has no subfolders."), 2)
    return hit[0]


def cmd_get(argv):
    """`drive get <folder> <ep>`."""
    ap = argparse.ArgumentParser(prog="pal drive get")
    ap.add_argument("folder")
    ap.add_argument("ep")
    ap.add_argument("--only", help="only files whose name matches this pattern (e.g. '*.mov')")
    ap.add_argument("--force", action="store_true", help="download even if the disk may be too small")
    a = ap.parse_args(argv)
    ep = C.episode(a.ep)
    files = list_files()
    if a.folder == ".":                                   # files lying directly in the shared folder
        top, mine = "(top level)", [dict(f, rel=f["path"]) for f in files if "/" not in f["path"]]
    else:
        top = pick_folder(files, a.folder)
        mine = [dict(f, rel=f["path"][len(top) + 1:]) for f in files if f["path"].startswith(top + "/")]
    if a.only:
        pat = a.only if any(c in a.only for c in "*?[") else f"*{a.only}*"
        mine = [f for f in mine if fnmatch.fnmatch(os.path.basename(f["rel"]).lower(), pat.lower())]
    if not mine:
        C.die(f"nothing to download in '{top}'" + (f" matching {a.only}" if a.only else ""))
    with_sizes(mine)
    src = os.path.join(ep, "build", "source")
    os.makedirs(src, exist_ok=True)
    todo = [f for f in mine if not (f["size"] and os.path.exists(os.path.join(src, f["rel"]))
                                    and os.path.getsize(os.path.join(src, f["rel"])) == f["size"])]
    total = sum(f["size"] or 0 for f in todo)
    free = C.free_gb(src) * 1e9
    if not a.force and total * SPACE_FACTOR > free:
        print(f"✗ '{top}' is {gb(total)}; {gb(free)} free. Conforming needs {SPACE_FACTOR}x the download "
              f"({gb(total * SPACE_FACTOR)}). Free some space, or --force.", file=sys.stderr)
        return 3
    ids_path = os.path.join(src, ".drive.json")
    ids = C.load(ids_path, default={})
    for f in mine:
        ids[f"build/source/{f['rel']}"] = f["id"]
    C.save(ids_path, ids)
    print(f"· {len(todo)} of {len(mine)} files to download ({gb(total)}) from '{top}'", file=sys.stderr)
    for f in todo:
        dest = os.path.join(src, f["rel"])
        print(f"· {f['rel']} ({gb(f['size']) if f['size'] else '?'})", file=sys.stderr, flush=True)
        download(f["id"], dest, f["size"])
    C.say(f"✓ {len(mine)} files in {C.rel(ep, src)}/ ({gb(sum(f['size'] or 0 for f in mine))})",
          *[f"  {f['rel']}" for f in mine[:20]], f"  next: ./pal ingest {os.path.basename(ep)}")
    return 0


# ---------------------------------------------------------------- upload

def upload_url():
    """The creator's upload link from the environment, or exit 3."""
    env = C.channel().get("upload", {}).get("env", "EDITPAL_UPLOAD_URL")
    url = os.environ.get(env, "").strip()
    if not url:
        print(f"✗ no upload link: ${env} is not set. Follow docs/DRIVE.md (one-time, 5 minutes), or send the file "
              "in the chat.", file=sys.stderr)
        sys.exit(3)
    return url


def start_session(url, folder, path):
    """Ask the upload link for a resumable-upload session URL."""
    body = {"action": "start", "folder": folder, "name": os.path.basename(path), "size": os.path.getsize(path),
            "mime": mimetypes.guess_type(path)[0] or "application/octet-stream"}
    r = requests.post(url, data=json.dumps(body), headers={"Content-Type": "text/plain;charset=utf-8"}, timeout=120)
    try:
        sess = r.json().get("upload")
    except ValueError:
        sess = None
    if not sess:
        C.die(f"the upload link did not give an upload session (HTTP {r.status_code}). Is it deployed for "
              "'Anyone', and is it the /exec link? See docs/DRIVE.md.", 3)
    return sess


def sent_so_far(sess, size):
    """Bytes Drive already has for a session (0 when none), asking with an empty range PUT."""
    r = requests.put(sess, headers={"Content-Range": f"bytes */{size}", "Content-Length": "0"}, timeout=120)
    if r.status_code in (200, 201):
        return size, r
    m = re.search(r"bytes=0-(\d+)", r.headers.get("Range", ""))
    return (int(m.group(1)) + 1 if m else 0), None


def put_file(url, folder, path):
    """Upload one file in 32 MB chunks, resuming after a failure. Returns the Drive file id."""
    size = os.path.getsize(path)
    sess = start_session(url, folder, path)
    pos, tries, last = 0, 0, None
    with open(path, "rb") as f:
        while pos < size or last is None:
            f.seek(pos)
            data = f.read(CHUNK)
            end = pos + len(data) - 1
            rng = f"bytes {pos}-{end}/{size}" if size else "bytes */0"
            try:
                r = requests.put(sess, data=data, headers={"Content-Range": rng}, timeout=300)
                if r.status_code in (200, 201):
                    last = r
                    break
                if r.status_code != 308:
                    raise requests.RequestException(f"HTTP {r.status_code}")
                m = re.search(r"bytes=0-(\d+)", r.headers.get("Range", ""))
                pos = int(m.group(1)) + 1 if m else 0
                tries = 0
                print(f"  {pos * 100 // max(size, 1)}%", file=sys.stderr, flush=True)
            except requests.RequestException as e:
                tries += 1
                if tries > 6:
                    C.die(f"upload of {os.path.basename(path)} keeps failing ({e}); run the command again.")
                print(f"! upload interrupted ({e}); resuming ({tries}/6)", file=sys.stderr)
                time.sleep(3 * tries)
                try:
                    pos, done = sent_so_far(sess, size)
                    if done is not None:
                        last = done
                        break
                except requests.RequestException:
                    pass
    try:
        return last.json()["id"]
    except (ValueError, KeyError, AttributeError):
        C.die("Drive accepted the file but sent no id; look in the output folder.")


def cmd_put(argv):
    """`drive put <ep> <file>…`."""
    ap = argparse.ArgumentParser(prog="pal drive put")
    ap.add_argument("ep")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    ep = C.episode(a.ep)
    for p in a.files:
        if not os.path.isfile(p):
            C.die(f"{p} is not a file", 2)
    url = upload_url()
    lines = []
    for p in a.files:
        print(f"· uploading {os.path.basename(p)} ({gb(os.path.getsize(p))})", file=sys.stderr, flush=True)
        fid = put_file(url, os.path.basename(ep), p)
        lines.append(f"  {os.path.basename(p)}  https://drive.google.com/file/d/{fid}/view")
    C.say("✓ uploaded", *lines)
    return 0


def main(argv):
    """Entry point for ./pal drive."""
    cmds = {"list": cmd_list, "get": cmd_get, "put": cmd_put}
    if not argv or argv[0] not in cmds:
        print(__doc__.strip())
        return 2
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
