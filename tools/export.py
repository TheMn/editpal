"""Export the A-cut as a timeline an editor can open (DaVinci Resolve, Premiere, Final Cut).

  ./pal export <ep> --fcpxml | --edl | --otio

Writes build/out/<episode>.fcpxml (FCPXML 1.9), .edl (CMX 3600) or .otio. The timeline refers to
the ORIGINAL source files by file name (sources.json "file"), so the editor relinks them and can
keep cutting: one video track, one audio track, cuts only, a marker named after each cut id.
The file is read back and checked (clip count, total length) before the path is printed.
"""
import argparse
import json
import os
import re
import xml.etree.ElementTree as ET

import common as C
import cut as K


def rational(fps):
    """(numerator, denominator) of the frame rate: 25/1, 30000/1001 ..."""
    for n, d in ((24000, 1001), (30000, 1001), (60000, 1001)):
        if abs(fps - n / d) < 0.01:
            return n, d
    return int(round(fps)), 1


def model(ep):
    """The A-cut as events: picture (V) and sound (A) clips with frame positions on the timeline."""
    rec = K.Rec(ep)
    e = K.load_edit(ep)
    if e.get("adopted"):
        C.die("this episode uses the creator's own A-cut (adopted): there is no cut to export.", 3)
    fps = rec.fps
    fr = lambda t: int(round(t * fps))
    cutat = {round(r["out"], 3): r for r in K.active(e)}
    ev, rec_in = [], 0
    for k in e["keep"]:
        dur = fr(k["out"]) - fr(k["in"])
        label = None
        r = cutat.get(round(k["in"], 3))
        if r:
            label = f"{r['id']} {r['kind']}"
        pic = k.get("angle") or rec.master
        if rec.has_video:
            ev.append({"kind": "V", "sid": pic, "src_in": fr(k["in"] + rec.off(pic)), "dur": dur, "rec_in": rec_in, "label": label, "keep": k["id"]})
        lead, tail = k.get("audio_lead", 0) or 0, k.get("audio_tail", 0) or 0
        a_in, a_dur = fr(k["in"] + lead), dur + fr(k["out"] + tail) - fr(k["out"]) - (fr(k["in"] + lead) - fr(k["in"]))
        sep = rec.vid != rec.master or not rec.has_video
        ev.append({"kind": "A", "sid": rec.vid, "src_in": fr(k["in"] + lead + rec.voff), "dur": a_dur, "rec_in": rec_in + (a_in - fr(k["in"])),
                   "label": label if not rec.has_video or sep else None, "keep": k["id"], "mute_pic": False})
        rec_in += dur
    return rec, e, ev, rec_in


def fname(rec, sid):
    s = rec.src[sid]
    return os.path.basename(s.get("file") or s.get("conform"))


def tcode(frames, fps, start_hours=1):
    """Frames -> HH:MM:SS:FF (non-drop), starting at 01:00:00:00."""
    n = int(round(fps))
    frames += start_hours * 3600 * n
    return f"{frames // (3600 * n):02d}:{frames // (60 * n) % 60:02d}:{frames // n % 60:02d}:{frames % n:02d}"


def write_edl(ep, rec, ev, total, slug):
    """CMX 3600: video events on V, sound on A, the cut ids as comments."""
    lines = [f"TITLE: {slug}", "FCM: NON-DROP FRAME", ""]
    n = 0
    for kind in ("V", "A"):
        for x in [x for x in ev if x["kind"] == kind]:
            n += 1
            reel = re.sub(r"[^A-Za-z0-9]", "", os.path.splitext(fname(rec, x["sid"]))[0]).upper()[:8] or "AX"
            ch = "V" if kind == "V" else "A"
            lines.append(f"{n:03d}  {reel:<8} {ch:<5} C        {tcode(x['src_in'], rec.fps, 0)} {tcode(x['src_in'] + x['dur'], rec.fps, 0)} "
                         f"{tcode(x['rec_in'], rec.fps)} {tcode(x['rec_in'] + x['dur'], rec.fps)}")
            lines.append(f"* FROM CLIP NAME: {fname(rec, x['sid'])}")
            if x["label"]:
                lines.append(f"* LOC: {tcode(x['rec_in'], rec.fps)} YELLOW  {x['label']}")
            lines.append("")
    return "\n".join(lines)


def check_edl(text, rec, ev):
    rows = re.findall(r"^\d{3}\s+\S+\s+\S+\s+C\s+(\S+) (\S+) (\S+) (\S+)$", text, re.M)
    fps = int(round(rec.fps))
    tf = lambda s: sum(int(v) * m for v, m in zip(s.split(":"), (3600 * fps, 60 * fps, fps, 1)))
    assert len(rows) == len(ev), "event count"
    for (a, b, c, d), x in zip(rows, sorted(ev, key=lambda x: x["kind"] == "A")):
        assert tf(b) - tf(a) == tf(d) - tf(c) == x["dur"], "event length"


def write_fcpxml(ep, rec, ev, total, slug):
    """FCPXML 1.9: a spine of picture clips with the sound as connected clips (lane -1)."""
    num, den = rational(rec.fps)
    t = lambda fr_: f"{fr_ * den}/{num}s" if fr_ else "0s"
    size = (rec.src[rec.master].get("size") or [1920, 1080]) if rec.has_video else [1920, 1080]
    root = ET.Element("fcpxml", version="1.9")
    res = ET.SubElement(root, "resources")
    ET.SubElement(res, "format", id="r1", name=f"FFVideoFormat{size[1]}p{int(round(rec.fps))}", frameDuration=f"{den}/{num}s",
                  width=str(size[0]), height=str(size[1]))
    assets = {}
    for x in ev:
        if x["sid"] not in assets:
            s = rec.src[x["sid"]]
            aid = f"r{len(assets) + 2}"
            assets[x["sid"]] = aid
            isv = x["kind"] == "V"
            span = int(round(float(s.get("duration") or 3600) * rec.fps)) + 1
            ET.SubElement(res, "asset", id=aid, name=os.path.splitext(fname(rec, x["sid"]))[0], start="0s", duration=t(span),
                          hasVideo="1" if isv else "0", hasAudio="0" if (isv and s.get("audio") is False) else "1",
                          format="r1" if isv else "", src="file:///" + fname(rec, x["sid"]),
                          audioSources="1", audioChannels="1" if not isv else "2", audioRate="48000")
            if not isv:
                del res[-1].attrib["format"]
    lib = ET.SubElement(root, "library")
    evn = ET.SubElement(lib, "event", name=slug)
    proj = ET.SubElement(evn, "project", name=slug)
    seq = ET.SubElement(proj, "sequence", format="r1", duration=t(total), tcStart="0s", tcFormat="NDF", audioLayout="mono", audioRate="48k")
    spine = ET.SubElement(seq, "spine")
    sound = [x for x in ev if x["kind"] == "A"]
    pics = [x for x in ev if x["kind"] == "V"] or sound
    for p in pics:
        c = ET.SubElement(spine, "asset-clip", ref=assets[p["sid"]], offset=t(p["rec_in"]), name=os.path.splitext(fname(rec, p["sid"]))[0],
                          start=t(p["src_in"]), duration=t(p["dur"]), format="r1" if p["kind"] == "V" else "", tcFormat="NDF")
        if p["kind"] == "A":
            del c.attrib["format"]
        if p["label"]:
            ET.SubElement(c, "marker", start=t(p["src_in"]), duration=f"{den}/{num}s", value=p["label"])
        if p["kind"] == "V" and sound:
            a = next(x for x in sound if x["keep"] == p["keep"])
            if rec.vid != rec.master:
                ET.SubElement(c, "adjust-volume", amount="-96dB")
            ac = ET.SubElement(c, "asset-clip", ref=assets[a["sid"]], lane="-1", offset=t(p["src_in"] + a["rec_in"] - p["rec_in"]),
                               name=os.path.splitext(fname(rec, a["sid"]))[0], start=t(a["src_in"]), duration=t(a["dur"]))
            ac.set("audioRole", "dialogue")
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + ET.tostring(root, encoding="unicode") + "\n"


def check_fcpxml(text, ev, total, rec):
    root = ET.fromstring(text.split("<!DOCTYPE fcpxml>\n", 1)[1])
    num, den = rational(rec.fps)
    fr = lambda s: 0 if s == "0s" else int(s[:-1].split("/")[0]) // den
    spine = root.find(".//spine")
    clips = spine.findall("asset-clip")
    assert sum(fr(c.get("duration")) for c in clips) == total, "total length"
    assert len(clips) == len([x for x in ev if x["kind"] == "V"] or ev), "clip count"
    assert all(c.get("ref") in {a.get("id") for a in root.iter("asset")} for c in root.iter("asset-clip")), "asset refs"


def write_otio(ep, rec, ev, total, slug):
    """OpenTimelineIO JSON (Timeline.1 / Track.1 / Clip.1) with one video and one audio track."""
    rate = rec.fps
    rt = lambda v: {"OTIO_SCHEMA": "RationalTime.1", "rate": rate, "value": float(v)}
    tr = lambda a, d: {"OTIO_SCHEMA": "TimeRange.1", "start_time": rt(a), "duration": rt(d)}
    tracks = []
    for kind, label in (("V", "Video"), ("A", "Audio")):
        kids, pos = [], 0
        for x in [x for x in ev if x["kind"] == kind]:
            if x["rec_in"] > pos:
                kids.append({"OTIO_SCHEMA": "Gap.1", "name": "", "source_range": tr(0, x["rec_in"] - pos), "metadata": {}, "effects": [], "markers": [], "enabled": True})
            pos = x["rec_in"] + x["dur"]
            kids.append({"OTIO_SCHEMA": "Clip.1", "name": fname(rec, x["sid"]), "source_range": tr(x["src_in"], x["dur"]),
                         "media_reference": {"OTIO_SCHEMA": "ExternalReference.1", "target_url": fname(rec, x["sid"]), "available_range": None,
                                             "name": fname(rec, x["sid"]), "metadata": {}},
                         "markers": [{"OTIO_SCHEMA": "Marker.2", "name": x["label"], "color": "YELLOW", "comment": "",
                                      "marked_range": tr(x["src_in"], 1), "metadata": {}}] if x["label"] else [],
                         "effects": [], "enabled": True, "metadata": {"keep": x["keep"]}})
        tracks.append({"OTIO_SCHEMA": "Track.1", "name": f"{label} 1", "kind": label, "children": kids, "source_range": None,
                       "effects": [], "markers": [], "enabled": True, "metadata": {}})
    doc = {"OTIO_SCHEMA": "Timeline.1", "name": slug, "global_start_time": None, "metadata": {},
           "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "children": tracks, "source_range": None, "effects": [], "markers": [],
                      "enabled": True, "metadata": {}}}
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def check_otio(text, ev, total):
    doc = json.loads(text)
    for trk in doc["tracks"]["children"]:
        want = [x for x in ev if x["kind"] == trk["kind"][0]]
        clips = [c for c in trk["children"] if c["OTIO_SCHEMA"] == "Clip.1"]
        assert len(clips) == len(want), "clip count"
        assert sum(c["source_range"]["duration"]["value"] for c in clips) == sum(x["dur"] for x in want), "length"


def main(argv):
    ap = argparse.ArgumentParser(prog="export", description=__doc__.splitlines()[0])
    ap.add_argument("ep")
    g = ap.add_mutually_exclusive_group(required=True)
    for k in ("fcpxml", "edl", "otio"):
        g.add_argument("--" + k, action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit as x:
        return 2 if x.code else 0
    ep = C.episode(a.ep)
    rec, e, ev, total = model(ep)
    slug = os.path.basename(ep)
    kind = "fcpxml" if a.fcpxml else "edl" if a.edl else "otio"
    text = {"fcpxml": write_fcpxml, "edl": write_edl, "otio": write_otio}[kind](ep, rec, ev, total, slug)
    try:
        {"fcpxml": lambda: check_fcpxml(text, ev, total, rec), "edl": lambda: check_edl(text, rec, ev),
         "otio": lambda: check_otio(text, ev, total)}[kind]()
    except (AssertionError, ET.ParseError, ValueError) as ex:
        C.die(f"the {kind} I wrote did not read back correctly ({ex}); nothing saved.")
    out = os.path.join(os.path.dirname(C.build(ep, "out", f"{slug}.{kind}")), f"{slug}.{kind}")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    files = sorted({fname(rec, x["sid"]) for x in ev})
    C.say(f"{kind}: {len(ev)} clips, {total / rec.fps:.2f} s, read back OK -> {C.rel(ep, out)}",
          "  relink these original files in the editor: " + ", ".join(files),
          "  markers: " + ", ".join(x["label"] for x in ev if x["label"] and x["kind"] == ("V" if rec.has_video else "A"))[:200])
    return 0
