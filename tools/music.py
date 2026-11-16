"""The free music library: list, download, preview and add tracks (CC0 / public domain only).

Usage:
  ./pal music list [--mood calm]            tracks with mood, length, licence
  ./pal music get <id>                      download (checked by SHA-1) into $EDITPAL_CACHE/music/; prints the path
  ./pal music preview <id|file> <out.mp3>   30 s from the middle, faded in and out
  ./pal music add <commons-file-url> --mood <mood> --id <id> [--use "…"] [--performer "…"]
                                            reads the file's page through the Wikimedia Commons API and
                                            adds it to library/music/library.json, but only if its licence is
                                            CC0 or public domain; then run ./pal music get <id> to check it

Moods: calm, warm, upbeat, driving, playful, tense, ambient. Rules and what to do about a wrong
Content ID claim: library/music/README.md. Tracks the creator owns can be dropped in Drive
brand/music/ with a licence note instead.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import common

LIB = os.path.join(common.ROOT, "library", "music", "library.json")
MOODS = ["calm", "warm", "upbeat", "driving", "playful", "tense", "ambient"]
API = "https://commons.wikimedia.org/w/api.php"
UA = "editpal-tools/1.0 (open-source video toolkit)"
OK_LICENSE = re.compile(r"^(cc0|cc[- ]zero|public domain|pd\b|pdm|no restrictions)", re.I)


def tracks():
    """All library entries (a list of dicts)."""
    return common.load(LIB, default=[])


def find(tid):
    """One entry by id, or a helpful error."""
    for t in tracks():
        if t["id"] == tid:
            return t
    common.die(f"no track '{tid}' in the library. ./pal music list shows the ids", 2)


def http(url, params=None, binary=False, tries=6):
    """GET with back-off (Wikimedia answers 429 to bursts); returns parsed JSON, or bytes if binary."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    wait = 3.0
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            return data if binary else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or k == tries - 1:
                common.die(f"{url[:90]} answered {e.code}")
            ra = float(e.headers.get("Retry-After") or 0)
            if ra > 120:
                common.die(f"Wikimedia asks for a pause of {ra / 60:.0f} minutes (too many downloads from this "
                           "address): run the command again after that", 3)
            wait = max(wait, ra)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if k == tries - 1:
                common.die(f"cannot reach {url[:90]}: check the network")
        time.sleep(wait)
        wait = min(wait * 2, 60)


def get_path(tid):
    """Local file of a track, downloading and verifying it the first time."""
    tid = tid[8:] if tid.startswith("library:") else tid
    t = find(tid)
    ext = os.path.splitext(urllib.parse.urlparse(t["url"]).path)[1] or ".ogg"
    path = os.path.join(common.CACHE, "music", tid + ext)
    if os.path.exists(path) and sha1_of(path) == t["sha1"]:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = http(t["url"], binary=True)
    import hashlib
    got = hashlib.sha1(data).hexdigest()
    if got != t["sha1"]:
        common.die(f"{tid}: the downloaded file does not match the recorded SHA-1 "
                   f"({got[:10]}… vs {t['sha1'][:10]}…): the file on Commons changed; check {t['page']}")
    with open(path + ".part", "wb") as f:
        f.write(data)
    os.replace(path + ".part", path)
    return path


def sha1_of(path):
    import hashlib
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def preview(tid, out):
    """30 s from the middle of the track, faded, as MP3. `tid` is a library id (or library:<id>) or an audio file."""
    tid = tid[8:] if tid.startswith("library:") else tid
    src = tid if os.path.isfile(tid) else get_path(tid)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    total = common.duration(src)
    start = max(0.0, total / 2 - 15)
    common.run(["ffmpeg", "-ss", f"{start:.2f}", "-t", "30", "-i", src, "-af",
                "afade=t=in:d=1,afade=t=out:st=29:d=1", "-c:a", "libmp3lame", "-b:a", "128k", out])
    common.say(f"✓ {out} ({min(30, total):.0f} s from {common.tc(start)})")


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def commons_info(title):
    """imageinfo + licence metadata of one Commons file title ('File:…')."""
    d = http(API, dict(action="query", format="json", titles=title, prop="imageinfo",
                       iiprop="url|sha1|size|mime|mediatype|extmetadata|metadata", formatversion=2))
    page = d["query"]["pages"][0]
    if page.get("missing") or "imageinfo" not in page:
        common.die(f"{title}: no such file on Commons")
    return page["title"], page["imageinfo"][0]


def licence_ok(meta):
    """(ok, short licence name, why not). CC0 / public domain only; attribution-required is out."""
    g = lambda k: strip_html((meta.get(k) or {}).get("value", ""))
    lic = g("LicenseShortName")
    if not OK_LICENSE.match(lic):
        return False, lic, f"licence is '{lic or 'unknown'}', only CC0 or public domain are allowed"
    if g("AttributionRequired").lower() == "true":
        return False, lic, "the page asks for attribution"
    if re.search(r"\b(NC|ND|SA|BY)\b", lic):
        return False, lic, f"licence '{lic}' has conditions"
    return True, ("CC0" if re.match(r"cc", lic, re.I) else "PD"), ""


def seconds_of(info):
    for m in info.get("metadata") or []:
        if m.get("name") in ("length", "playtime_seconds") and m.get("value"):
            try:
                return round(float(m["value"]))
            except (TypeError, ValueError):
                pass
    return None


def add(url, mood, tid, use="", performer=""):
    """Add one Commons file to library.json if (and only if) its licence is CC0 / public domain."""
    if mood not in MOODS:
        common.die(f"mood must be one of: {', '.join(MOODS)}", 2)
    name = urllib.parse.unquote(url.split("/wiki/", 1)[-1].split("?")[0].split("#")[0]).replace("_", " ")
    if not name.startswith("File:"):
        common.die("give the file's page, like https://commons.wikimedia.org/wiki/File:Name.ogg", 2)
    if any(t["id"] == tid for t in tracks()):
        common.die(f"id '{tid}' is already in the library", 2)
    title, info = commons_info(name)
    if info.get("mediatype") != "AUDIO":
        common.die(f"{title} is not an audio file ({info.get('mediatype')})")
    meta = info.get("extmetadata") or {}
    ok, lic, why = licence_ok(meta)
    if not ok:
        common.die(f"refused: {why}. Page: https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}", 1)
    secs = seconds_of(info)
    entry = {"id": tid, "mood": mood,
             "title": strip_html((meta.get("ObjectName") or {}).get("value")) or title[5:].rsplit(".", 1)[0],
             "performer": performer or strip_html((meta.get("Artist") or {}).get("value")),
             "use": use, "seconds": secs, "license": lic,
             "page": "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"),
             "url": info["url"].split("?")[0], "sha1": info["sha1"]}
    lib = tracks()
    lib.append(entry)
    common.save(LIB, lib)
    if secs is None:                        # no length in the metadata: measure after download
        entry["seconds"] = round(common.duration(get_path(tid)))
        common.save(LIB, lib)
    common.say(f"✓ added {tid}: {entry['title']} ({entry['performer'] or 'unknown performer'}), "
               f"{entry['seconds']} s, {lic}",
               "  check on the page that the RECORDING itself is CC0/PD (not only the composition), then listen.")


def list_(mood=None):
    """Print the library as a table, by mood."""
    rows = [t for t in tracks() if not mood or t["mood"] == mood]
    if not rows:
        common.say("no tracks" + (f" with mood '{mood}'" if mood else ""))
        return 0
    out = []
    for m in MOODS:
        for t in (x for x in rows if x["mood"] == m):
            out.append(f"{m:<8} {t['id']:<20} {t['seconds'] or 0:>4}s {t['license']:<4} "
                       f"{t['title'][:34]} — {t['performer'][:24]}")
    common.say(*out, limit=60)
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    p = argparse.ArgumentParser(prog="pal music " + cmd, add_help=False)
    if cmd == "list":
        p.add_argument("--mood")
        a = p.parse_args(rest)
        return list_(a.mood)
    if cmd == "get":
        p.add_argument("id")
        common.say(get_path(p.parse_args(rest).id))
        return 0
    if cmd == "preview":
        p.add_argument("id")
        p.add_argument("out")
        a = p.parse_args(rest)
        preview(a.id, a.out)
        return 0
    if cmd == "add":
        p.add_argument("url")
        p.add_argument("--mood", required=True)
        p.add_argument("--id", required=True)
        p.add_argument("--use", default="")
        p.add_argument("--performer", default="")
        a = p.parse_args(rest)
        add(a.url, a.mood, a.id, a.use, a.performer)
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
