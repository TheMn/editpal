"""The two helpers chapters.py imports from the upstream project's yt-edit folder (not copied with it).

Written fresh for editpal: load(path) -> [(start, end, text), ...] from .srt, .vtt or a Whisper-style
.json; parse_ts("00:01:02,500") -> seconds.
"""
import json
import re


def parse_ts(s):
    """'1:02.5', '00:01:02,500' or '62.5' to seconds."""
    parts = s.strip().replace(",", ".").split(":")
    t = 0.0
    for p in parts:
        t = t * 60 + float(p)
    return t


def load(path):
    """Cues as (start, end, text) from .srt / .vtt / .json (segments or words with start and end)."""
    if path.lower().endswith(".json"):
        d = json.load(open(path, encoding="utf-8"))
        items = d.get("segments") or d.get("words") or d if isinstance(d, dict) else d
        return [(float(x["start"]), float(x["end"]), (x.get("text") or x.get("w") or "").strip()) for x in items]
    text = open(path, encoding="utf-8-sig").read().replace("\r", "")
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            m = re.match(r"\s*([\d:.,]+)\s*-->\s*([\d:.,]+)", ln)
            if m:
                body = " ".join(lines[i + 1:]).strip()
                if body:
                    cues.append((parse_ts(m.group(1)), parse_ts(m.group(2)), re.sub(r"<[^>]+>", "", body)))
                break
    return cues
