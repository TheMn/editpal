"""Thumbnails: find sharp, expressive frames, then compose 1280x720 options with big text.

Usage:
  ./pal thumb <ep>                                   the 12 best candidate frames + a contact sheet
  ./pal thumb <ep> --make f3 --text "THREE WORDS" [--side left|right] -o T1.jpg
  --make   a candidate (f3 or 3) or any image file
  --text   at most 3 words, any language (Persian is shaped and set right-to-left)
  --side   where the text goes; default: the side away from the face
Writes build/out/thumbs/frames/f<N>.jpg, contact.jpg and frames.json; the options go to
build/out/thumbs/<name>.jpg (under 2 MB). Colours and fonts come from brand/frame.md.
A frame is chosen for: sharpness, a large face, even exposure; times are spread out.
"""
import argparse
import json
import os
import re
import sys

import numpy as np

import board
import common
import reframe

N_BEST = 12


def thumbs_dir(ep, *parts):
    return common.build(ep, "out", "thumbs", *parts)


def source_video(E):
    """The A-cut, else the master conform file."""
    if E.has("build/cut/acut.mp4"):
        return E.p("build/cut/acut.mp4")
    master = ((E.sources or {}).get("sources") or {}).get((E.sources or {}).get("master")) or {}
    f = master.get("conform") or master.get("file")
    return E.p(f) if f and os.path.exists(E.p(f)) else None


def sample_times(E, total):
    """About 70 moments: dense in the first 3 minutes, every beat's start, then every ~20 s."""
    ts = set(np.arange(1.0, min(total, 180.0), 3.0))
    for b in (E.plan or {}).get("beats", []):
        t = E.beat_t(b)
        if t and t[0] + 0.5 < total:
            ts.add(t[0] + 0.5)
    ts |= set(np.arange(180.0, total, 20.0))
    ts = sorted(t for t in ts if t < total - 0.5)
    if len(ts) > 80:
        ts = ts[:: int(np.ceil(len(ts) / 80))]
    return ts


def score_frames(path, times):
    """For each time: (sharpness, face box or None, brightness, image)."""
    import cv2
    cap = cv2.VideoCapture(path)
    sw, sh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    k = min(1.0, 640.0 / sw)
    det = cv2.FaceDetectorYN.create(reframe.MODEL, "", (int(sw * k), int(sh * k)), 0.75, 0.3, 50)
    out = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, img = cap.read()
        if not ok:
            continue
        small = cv2.resize(img, (int(sw * k), int(sh * k))) if k < 1 else img
        _, faces = det.detect(small)
        box = None
        if faces is not None and len(faces):
            f = max(faces, key=lambda f: f[2] * f[3])
            box = [float(f[0]) / small.shape[1], float(f[1]) / small.shape[0], float(f[2]) / small.shape[1], float(f[3]) / small.shape[0]]
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        if box:   # sharpness where it matters: on the face
            x, y, w, h = [int(v * s) for v, s in zip(box, (small.shape[1], small.shape[0], small.shape[1], small.shape[0]))]
            roi = gray[max(0, y):y + max(8, h), max(0, x):x + max(8, w)]
            sharp = float(cv2.Laplacian(roi if roi.size else gray, cv2.CV_64F).var())
        else:
            sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        out.append({"t": float(t), "sharp": sharp, "face": box, "bright": float(gray.mean())})
    cap.release()
    return out


def pick_best(rows, n=N_BEST):
    """Rank (sharpness by rank, big face, good exposure) and take the best n at least 4 s apart."""
    if not rows:
        return []
    order = np.argsort(np.argsort([r["sharp"] for r in rows])) / max(1, len(rows) - 1)
    for r, s in zip(rows, order):
        face = min(1.0, (r["face"][2] * r["face"][3]) / 0.05) if r["face"] else 0.0
        expo = 1.0 - min(1.0, abs(r["bright"] - 115) / 115)
        r["score"] = round(0.45 * float(s) + 0.4 * face + 0.15 * expo, 4)
    chosen = []
    for r in sorted(rows, key=lambda r: -r["score"]):
        if all(abs(r["t"] - c["t"]) >= 4.0 for c in chosen):
            chosen.append(r)
        if len(chosen) == n:
            break
    return sorted(chosen, key=lambda r: r["t"])


def contact_sheet(files, labels, out):
    """3 x 4 grid with the frame names, so a person can choose by name."""
    from PIL import Image, ImageDraw
    w, h, cols = 320, 180, 4
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (20, 20, 22))
    for i, (f, lab) in enumerate(zip(files, labels)):
        im = Image.open(f).convert("RGB").resize((w, h))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 120, 22], fill=(0, 0, 0))
        d.text((5, 4), lab, fill=(255, 255, 255))
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(out, quality=85)


def candidates(E):
    """./pal thumb <ep>"""
    import cv2
    src = source_video(E)
    if not src:
        common.die(f"no video to take frames from: make the A-cut first (./pal cut render {E.slug})", 3)
    if not os.path.exists(reframe.MODEL):
        common.die("face model missing: run sh tools/setup.sh")
    total = common.duration(src)
    rows = pick_best(score_frames(src, sample_times(E, total)))
    d = thumbs_dir(E.ep, "frames")
    for old in os.listdir(d):
        if re.match(r"f\d+\.jpg$", old):
            os.remove(os.path.join(d, old))
    meta, files = {}, []
    cap = cv2.VideoCapture(src)
    for i, r in enumerate(rows, 1):
        cap.set(cv2.CAP_PROP_POS_MSEC, r["t"] * 1000.0)
        ok, img = cap.read()
        p = os.path.join(d, f"f{i}.jpg")
        if ok:
            cv2.imwrite(p, img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        meta[f"f{i}"] = {k: r[k] for k in ("t", "score", "face", "sharp")}
        files.append(p)
    cap.release()
    common.save(os.path.join(d, "frames.json"), meta)
    contact_sheet(files, [f"f{i}  {common.tc(r['t'])}" for i, r in enumerate(rows, 1)], os.path.join(d, "contact.jpg"))
    lines = [f"✓ {len(rows)} candidates in {common.rel(E.ep, d)} (contact sheet: contact.jpg)"]
    lines += [f"  f{i}  {common.tc(r['t'])}  score {r['score']:.2f}  {'face ' + format(r['face'][2] * 100, '.0f') + '% wide' if r['face'] else 'no face'}" for i, r in enumerate(rows, 1)]
    lines.append(f"next: ./pal thumb {E.slug} --make f3 --text \"THREE WORDS\" -o T1.jpg")
    common.say(*lines)
    return 0


# ---------------------------------------------------------------- composing

def brand():
    """Accent / ink colours and font files from brand/frame.md, with safe fallbacks."""
    p = os.path.join(common.ROOT, "brand", "frame.md")
    txt = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    col = lambda k, d: "#" + (re.search(k + r':\s*"?#([0-9A-Fa-f]{6})', txt).group(1) if re.search(k + r':\s*"?#([0-9A-Fa-f]{6})', txt) else d)
    fonts = os.path.join(common.ROOT, "brand", "fonts")
    return {"accent": col("accent", "FFD600"), "fonts": fonts}


def pick_font(text, fonts):
    """A heavy font file for this text: Persian -> Vazirmatn Bold, else Inter / any bold, else DejaVu."""
    arabic = re.search(r"[؀-ۿ]", text)
    cands = ["Vazirmatn-Bold.ttf"] if arabic else ["InterVariable.ttf", "Inter-Bold.ttf", "JetBrainsMono-Bold.ttf"]
    for c in cands:
        if os.path.exists(os.path.join(fonts, c)):
            return os.path.join(fonts, c)
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def load_font(path, size):
    from PIL import ImageFont
    try:
        f = ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        f = ImageFont.truetype(path, size)
    try:   # heavy weight on variable fonts: set the weight axis, keep the others at their default
        axes = f.get_variation_axes()
        f.set_variation_by_axes([min(a["maximum"], 800) if (a["name"].decode() if isinstance(a["name"], bytes) else a["name"]).lower() == "weight" else a["default"] for a in axes])
    except Exception:
        pass
    return f


def find_face(img_path, meta_face):
    """Face box (fractions) from frames.json, or detect it again."""
    if meta_face:
        return meta_face
    import cv2
    img = cv2.imread(img_path)
    if img is None or not os.path.exists(reframe.MODEL):
        return None
    h, w = img.shape[:2]
    det = cv2.FaceDetectorYN.create(reframe.MODEL, "", (w, h), 0.7, 0.3, 50)
    _, faces = det.detect(img)
    if faces is None or not len(faces):
        return None
    f = max(faces, key=lambda f: f[2] * f[3])
    return [f[0] / w, f[1] / h, f[2] / w, f[3] / h]


def make(E, frame, text, side, out):
    """./pal thumb <ep> --make"""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    words = text.split()
    if not 1 <= len(words) <= 3:
        common.die("--text wants one to three words (a thumbnail is read at a glance)", 2)
    meta = common.load(os.path.join(thumbs_dir(E.ep, "frames"), "frames.json"), default={})
    fid = frame if frame.startswith("f") else f"f{frame}"
    path = frame if os.path.exists(frame) else os.path.join(thumbs_dir(E.ep, "frames"), f"{fid}.jpg")
    if not os.path.exists(path):
        common.die(f"no frame '{frame}': run ./pal thumb {E.slug} first", 2)
    face = find_face(path, (meta.get(fid) or {}).get("face") if path.endswith(f"{fid}.jpg") else None)
    if side not in ("left", "right"):
        side = "right" if (face and face[0] + face[2] / 2 < 0.5) else "left"
    W, H = 1280, 720
    im = Image.open(path).convert("RGB")
    zoom = 1.18 if face else 1.0
    s = max(W / im.width, H / im.height) * zoom
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    fx = (face[0] + face[2] / 2) * im.width if face else im.width / 2
    fy = (face[1] + face[3] / 2) * im.height if face else im.height / 2
    want = 0.70 if side == "left" else 0.30      # the face sits on the side away from the text
    x0 = int(min(max(fx - want * W, 0), im.width - W))
    y0 = int(min(max(fy - 0.42 * H, 0), im.height - H))
    im = im.crop((x0, y0, x0 + W, y0 + H))
    im = ImageEnhance.Color(ImageEnhance.Contrast(im).enhance(1.12)).enhance(1.2)
    shade = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(shade)
    for x in range(W // 2):
        a = int(150 * (1 - x / (W / 2)) ** 1.5)
        sd.line([(x if side == "left" else W - 1 - x, 0), (x if side == "left" else W - 1 - x, H)], fill=a)
    im = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), im, shade)
    b = brand()
    fpath = pick_font(text, b["fonts"])
    rtl = bool(re.search(r"[؀-ۿ]", text))
    lines = [w if rtl else w.upper() for w in words]
    box_w, box_h = int(W * 0.47), int(H * 0.82)
    size = 260
    while size > 40:
        f = load_font(fpath, size)
        widths = [f.getlength(t) for t in lines]
        lh = size * 1.12
        if max(widths) <= box_w and lh * len(lines) <= box_h:
            break
        size -= 6
    stroke = max(3, size // 12)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, sdw = ImageDraw.Draw(layer), ImageDraw.Draw(shadow)
    total_h = lh * len(lines)
    y = (H - total_h) / 2
    pad = int(W * 0.04)
    for i, t in enumerate(lines):
        w = f.getlength(t)
        x = pad if side == "left" else W - pad - w
        fill = "#" + b["accent"].lstrip("#") if i == len(lines) - 1 else "#FFFFFF"
        sdw.text((x + stroke, y + stroke * 1.5), t, font=f, fill=(0, 0, 0, 200), stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
        d.text((x, y), t, font=f, fill=fill, stroke_width=stroke, stroke_fill="#000000")
        y += lh
    im = Image.alpha_composite(im.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(stroke)))
    im = Image.alpha_composite(im, layer).convert("RGB")
    dest = out if os.path.dirname(out) else os.path.join(thumbs_dir(E.ep), out)
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    for q in (92, 86, 80, 70):
        im.save(dest, "JPEG", quality=q, optimize=True)
        if os.path.getsize(dest) < 2e6:
            break
    common.say(f"✓ {dest}  {os.path.getsize(dest) / 1e3:.0f} kB  text on the {side}, font size {size}")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog="thumb", add_help=False)
    ap.add_argument("ep")
    ap.add_argument("--make")
    ap.add_argument("--text")
    ap.add_argument("--side")
    ap.add_argument("-o", "--out")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    E = board.Ep(common.episode(a.ep))
    if a.make:
        if not a.text or not a.out:
            print(__doc__.strip(), file=sys.stderr)
            return 2
        return make(E, a.make, a.text, a.side, a.out)
    return candidates(E)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
