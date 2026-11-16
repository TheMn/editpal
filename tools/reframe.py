"""Make a 9:16 video from a 16:9 one: follow the speaker's face, centre-crop, or stack screen and face.

Usage:
  ./pal reframe <video> -o <out.mp4> [--mode track|center|stack] [--from a] [--to b] [--size 1080x1920]

  track   (default) a tall crop that follows the speaker's face; it moves smoothly and only when the
          face leaves a small dead zone. No face found: falls back to center and says so.
  center  a fixed crop of the middle of the picture.
  stack   for a screen recording with a face camera: the whole screen on top, the face below.
--from / --to  seconds; only that span is made. The sound is kept.
Faces are found with the YuNet detector (tools/models.json, key face-yunet; ./pal doctor checks it).
"""
import argparse
import os
import subprocess
import sys

import numpy as np

import common

MODEL = os.path.join(common.CACHE, "face-yunet", "face_detection_yunet_2023mar.onnx")
SAMPLE_HZ = 4.0


def detect_faces(path, t0, t1):
    """Face boxes sampled SAMPLE_HZ times a second: (times, [(cx, cy, w, h) or None, ...])."""
    import cv2
    if not os.path.exists(MODEL):
        common.die("face model missing: run sh tools/setup.sh (model face-yunet)")
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    sw, sh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    k = min(1.0, 640.0 / sw)
    dw, dh = max(32, int(sw * k)), max(32, int(sh * k))
    det = cv2.FaceDetectorYN.create(MODEL, "", (dw, dh), 0.7, 0.3, 500)
    times, boxes, prev = [], [], None
    t = t0
    while t < t1:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, img = cap.read()
        if not ok:
            break
        if k < 1.0:
            img = cv2.resize(img, (dw, dh))
        _, faces = det.detect(img)
        best = None
        if faces is not None and len(faces):
            cand = [(f[0] + f[2] / 2, f[1] + f[3] / 2, f[2], f[3]) for f in faces]
            cand = [(a / k, b / k, c / k, d / k) for a, b, c, d in cand]
            big = max(cand, key=lambda c: c[2] * c[3])
            best = big
            if prev is not None:   # keep the same person unless another face is clearly larger
                near = min(cand, key=lambda c: abs(c[0] - prev[0]))
                if big[2] * big[3] < 1.6 * near[2] * near[3]:
                    best = near
            prev = best
        times.append(t - t0)
        boxes.append(best)
        t += 1.0 / SAMPLE_HZ
    cap.release()
    return np.array(times), boxes, (sw, sh, fps)


def smooth_path(times, xs, span, n_frames, fps):
    """A gentle camera path: median filter, dead zone, speed limit, two moving averages -> one value per frame."""
    xs = np.array(xs, dtype=float)
    ok = ~np.isnan(xs)
    xs = np.interp(times, times[ok], xs[ok])
    pad = np.pad(xs, 2, mode="edge")
    xs = np.array([np.median(pad[i:i + 5]) for i in range(len(xs))])
    dead, vmax, dt = 0.10 * span, 0.35 * span, 1.0 / SAMPLE_HZ
    cam, c, far = [], xs[0], 0
    for x in xs:
        d = x - c
        far = far + 1 if abs(d) > 0.8 * span else 0
        if far >= 2:      # the picture itself cut to another layout: cut with it, do not pan across
            c, far = x, 0
        elif abs(d) > dead:
            tgt = x - np.sign(d) * dead * 0.5
            c += float(np.clip(tgt - c, -vmax * dt, vmax * dt))
        cam.append(c)
    cam = np.array(cam)
    per = np.interp(np.arange(n_frames) / fps, times, cam)
    for w in (int(fps * 1.0) | 1, int(fps * 0.5) | 1):
        p = np.pad(per, w // 2, mode="edge")
        per = np.convolve(p, np.ones(w) / w, mode="valid")
    return per


def parse_size(s):
    try:
        w, h = s.lower().split("x")
        return int(w) // 2 * 2, int(h) // 2 * 2
    except ValueError:
        common.die("--size wants WIDTHxHEIGHT, like 1080x1920", 2)


def build_graph(mode, sw, sh, ow, oh, cx, cy, cw, ch, cmdfile, top_h):
    """The ffmpeg filter graph; the crop position is set per frame through sendcmd."""
    if mode == "stack":
        k = ow / cw
        bh = oh - top_h
        return (f"[0:v]split[a][b];[a]scale={ow}:{top_h}:flags=lanczos,setsar=1[top];"
                f"[b]scale=iw*{k:.6f}:ih*{k:.6f}:flags=lanczos,sendcmd=f='{cmdfile}',crop@c={ow}:{bh}:0:0,setsar=1[bot];"
                f"[top][bot]vstack,format=yuv420p[out]")
    k = oh / sh
    if mode == "center":
        x = int(round((sw * k - ow) / 2)) // 2 * 2
        return f"[0:v]scale=iw*{k:.6f}:ih*{k:.6f}:flags=lanczos,crop={ow}:{oh}:{x}:0,setsar=1,format=yuv420p[out]"
    return (f"[0:v]scale=iw*{k:.6f}:ih*{k:.6f}:flags=lanczos,sendcmd=f='{cmdfile}',crop@c={ow}:{oh}:0:0,setsar=1,format=yuv420p[out]")


def main(argv):
    ap = argparse.ArgumentParser(prog="reframe", add_help=False)
    ap.add_argument("video")
    ap.add_argument("-o", "--out")
    ap.add_argument("--mode", default="track", choices=["track", "center", "stack"])
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float)
    ap.add_argument("--size", default="1080x1920")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    if not a.out or not os.path.exists(a.video):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    ow, oh = parse_size(a.size)
    dur = common.duration(a.video)
    t0, t1 = a.t0, min(a.t1 if a.t1 else dur, dur)
    if t1 <= t0:
        common.die(f"--from/--to is empty (the video is {dur:.1f} s long)", 2)
    mode, note = a.mode, ""
    sw = sh = 0
    cmds, cw, ch, top_h = None, 0, 0, 0
    fps = 25.0
    if mode != "center":
        times, boxes, (sw, sh, fps) = detect_faces(a.video, t0, t1)
        found = [b for b in boxes if b]
        if len(found) < max(2, len(boxes) * 0.1):
            mode, note = "center", "no face found, used a centre crop"
        else:
            n = int(round((t1 - t0) * fps))
            if mode == "track":
                cw, ch = sh * ow / oh, sh
                xs = [b[0] if b else np.nan for b in boxes]
                px = smooth_path(times, xs, cw, n, fps)
                px = np.clip(px - cw / 2, 0, max(0, sw - cw)) * (oh / sh)
                py = np.zeros(n)
            else:
                top_h = int(round(ow * sh / sw / 2)) * 2
                bh = oh - top_h
                fw = float(np.median([b[2] for b in found]))
                cw = min(sw, max(fw * 4.0, 64))
                ch = cw * bh / ow
                if ch > sh:
                    ch, cw = sh, sh * ow / bh
                xs = [b[0] if b else np.nan for b in boxes]
                ys = [b[1] if b else np.nan for b in boxes]
                k = ow / cw
                px = np.clip(smooth_path(times, xs, cw, n, fps) - cw / 2, 0, max(0, sw - cw)) * k
                py = np.clip(smooth_path(times, ys, ch, n, fps) - ch / 2, 0, max(0, sh - ch)) * k
            cmds = "".join(f"{i / fps:.4f} crop@c x {int(round(px[i])) // 2 * 2}, crop@c y {int(round(py[i])) // 2 * 2};\n" for i in range(n))
    if mode == "center" and not sw:
        vs = next(s for s in common.probe(a.video)["streams"] if s["codec_type"] == "video")
        sw, sh = int(vs["width"]), int(vs["height"])
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    cmdfile = os.path.abspath(a.out) + ".cmds"
    if cmds:
        open(cmdfile, "w").write(cmds)
    graph = build_graph(mode, sw, sh, ow, oh, 0, 0, cw, ch, cmdfile.replace(":", "\\:"), top_h)
    gfile = os.path.abspath(a.out) + ".graph"
    open(gfile, "w").write(graph)
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", a.video,
           "-filter_complex_script", gfile, "-map", "[out]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "20", "-threads", "2", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", a.out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    for f in (cmdfile, gfile):
        if os.path.exists(f):
            os.remove(f)
    if r.returncode != 0:
        common.die("ffmpeg failed: " + " | ".join(r.stderr.strip().splitlines()[-4:]))
    common.say(f"✓ {a.out}  {common.tc(common.duration(a.out))}  {ow}x{oh}  mode {mode}" + (f"  ({note})" if note else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
