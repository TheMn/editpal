"""A small generated recording with a known correct answer, for ./pal test. Nothing copyrighted.

    python3 tests/fixture.py [--force]      builds tests/build/ (git-ignored) and prints its paths

Speech comes from the stock voice (./pal voice say stock). The script is read with planted defects
whose positions (seconds on the camera's own timeline) are written to tests/build/truth.json:
room tone at the start, one long silence inside a sentence, one between sentences, a false start,
a whole-sentence retake, an "um", and a silent tail.

Files: build/episode/build/source/{cam.mp4 (picture + the speech: the camera), mic.wav (the same
speech band-limited and 0.740 s later), broll/clip.mp4, music/synth.wav}, build/episode/episode.md.
"""
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "build")
EP = os.path.join(OUT, "episode")
SRC = os.path.join(EP, "build", "source")
SR = 48000
MIC_DELAY = 0.740
VERSION = 3          # change when the recipe changes, to rebuild

# (id, text) in reading order; planted defects are marked in PLAN below.
SENTENCES = {
    "s1": "Today we will look at how a recursive function calls itself.",
    "s2a": "A function is recursive when it solves a problem",
    "s2b": "by solving a smaller copy of the same problem.",
    "s3": "Every recursive function needs a base case, otherwise it never stops.",
    "s4": "Let me show you a simple example.",
    "s4_start": "Let me show you",
    "s5": "The factorial of five is five times the factorial of four.",
    "s6_take1": "The stack grows with each call.",
    "s6": "The stack grows with every call.",
    "um": "Umm.",
    "s7": "Each call waits for the call below it to finish.",
    "s8": "When the base case is reached, the answers flow back up the stack.",
    "s9": "That is all there is to it.",
}
# kind of item: ("say", id) | ("gap", seconds, label or None)
PLAN = [
    ("gap", 4.0, "room_tone"),
    ("say", "s1"), ("gap", 0.45, None),
    ("say", "s2a"), ("gap", 2.6, "silence_mid_sentence"), ("say", "s2b"), ("gap", 0.45, None),
    ("say", "s3"), ("gap", 0.5, None),
    ("say", "s4_start", "false_start"), ("gap", 0.7, "false_start"), ("say", "s4"), ("gap", 0.45, None),
    ("say", "s5"), ("gap", 0.45, None),
    ("say", "s6_take1", "retake"), ("gap", 0.9, "retake"), ("say", "s6"), ("gap", 0.4, None),
    ("say", "um", "um"), ("gap", 0.2, None), ("say", "s7"), ("gap", 3.2, "silence_between"),
    ("say", "s8"), ("gap", 0.45, None),
    ("say", "s9"), ("gap", 3.0, "tail"),
]


def sh(cmd):
    """Run a command list; die with its error text."""
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"fixture: {cmd[0]} failed: {r.stderr.strip()[-400:]}")
    return r


def say(text, out):
    """One line from the stock voice (cached by ./pal voice say)."""
    if not os.path.exists(out):
        sh([os.path.join(ROOT, "pal"), "voice", "say", "stock", "--lang", "en", "--text", text, "-o", out])


def read48(path):
    """A wav as 48 kHz mono float32."""
    tmp = path + ".48.wav"
    if not os.path.exists(tmp):
        sh(["ffmpeg", "-i", path, "-ac", "1", "-ar", SR, tmp])
    x, _ = sf.read(tmp, dtype="float32")
    return x


def build_speech(lines_dir):
    """The planted speech: (samples, truth list). Room tone under everything at about -56 dBFS."""
    parts, truth, t = [], [], 0.0
    pending = {}
    for item in PLAN:
        if item[0] == "say":
            x = read48(os.path.join(lines_dir, item[1] + ".wav"))
            x = x * (0.5 / max(0.05, float(np.abs(x).max())))
            parts.append(x)
            dur = len(x) / SR
            if len(item) > 2:
                pending[item[2]] = pending.get(item[2], t)
                if item[2] == "um":
                    truth.append({"kind": "um", "start": round(t, 3), "end": round(t + dur, 3)})
            t += dur
        else:
            _, g, label = item
            parts.append(np.zeros(int(g * SR), dtype="float32"))
            if label == "room_tone":
                truth.append({"kind": "room_tone", "start": 0.0, "end": g})
            elif label in ("silence_mid_sentence", "silence_between"):
                truth.append({"kind": label, "start": round(t, 3), "end": round(t + g, 3)})
            elif label == "tail":
                truth.append({"kind": "tail", "start": round(t, 3), "end": round(t + g, 3)})
            elif label in ("false_start", "retake"):
                truth.append({"kind": label, "start": round(pending[label], 3), "end": round(t + g, 3)})
            t += g
    x = np.concatenate(parts)
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(len(x)).astype("float32")
    # a gentle low-pass by moving average gives a rumble-ish room tone
    k = np.ones(8, dtype="float32") / 8
    noise = np.convolve(noise, k, mode="same") * 0.0045
    return (x + noise).astype("float32"), truth


def build_video(path, wav, dur):
    """1280x720 30 fps test pattern with a running frame counter, the speech as its sound."""
    fc = "drawtext=text='frame %{frame_num}  t %{pts\\:hms}':x=40:y=h-80:fontsize=44:fontcolor=white:box=1:boxcolor=black@0.6"
    sh(["ffmpeg", "-f", "lavfi", "-i", f"testsrc2=s=1280x720:r=30:d={dur:.3f}", "-i", wav,
        "-vf", fc, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-g", 30, "-c:a", "aac", "-b:a", "160k", "-shortest", path])


def build_mic(path, wav):
    """The same speech through a telephone-like band, 0.740 s later (a leading stretch of room tone)."""
    sh(["ffmpeg", "-i", wav, "-af",
        f"highpass=f=300,lowpass=f=3400,volume=1.3,adelay={int(MIC_DELAY * 1000)}:all=1",
        "-ac", 1, "-ar", SR, path])


def build_broll(path):
    """A 10 s clip with a different pattern and no sound."""
    sh(["ffmpeg", "-f", "lavfi", "-i", "smptehdbars=s=1280x720:r=30:d=10",
        "-vf", "drawtext=text='B-ROLL %{pts\\:hms}':x=(w-text_w)/2:y=h/2:fontsize=80:fontcolor=white:box=1:boxcolor=black@0.5",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-an", path])


def build_music(path, seconds=40):
    """A synthetic pad: three sine chords, slow tremolo. Ours, so CC0."""
    t = np.arange(int(seconds * SR)) / SR
    chords = [(220.0, 277.18, 329.63), (196.0, 246.94, 293.66), (174.61, 220.0, 261.63), (196.0, 246.94, 293.66)]
    y = np.zeros_like(t, dtype="float64")
    for i, ch in enumerate(chords):
        m = ((t // 5) % 4 == i)
        for f in ch:
            y += m * np.sin(2 * np.pi * f * t)
    y *= 0.12 * (0.8 + 0.2 * np.sin(2 * np.pi * 0.25 * t))
    sf.write(path, np.stack([y, y * 0.97], axis=1).astype("float32"), SR, subtype="PCM_16")


def build(force=False):
    """Build everything under tests/build/ (skipped when the recipe version is unchanged). Returns truth."""
    marker = os.path.join(OUT, "fixture.version")
    truth_path = os.path.join(OUT, "truth.json")
    if not force and os.path.exists(marker) and open(marker).read().strip() == str(VERSION) \
            and os.path.exists(truth_path):
        return json.load(open(truth_path))
    os.makedirs(os.path.join(SRC, "broll"), exist_ok=True)
    os.makedirs(os.path.join(SRC, "music"), exist_ok=True)
    lines = os.path.join(OUT, "lines")
    os.makedirs(lines, exist_ok=True)
    for k, text in SENTENCES.items():
        say(text, os.path.join(lines, k + ".wav"))
    x, truth = build_speech(lines)
    speech = os.path.join(OUT, "speech.wav")
    sf.write(speech, x, SR, subtype="PCM_16")
    dur = len(x) / SR
    build_video(os.path.join(SRC, "cam.mp4"), speech, dur)
    build_mic(os.path.join(SRC, "mic.wav"), speech)
    build_broll(os.path.join(SRC, "broll", "clip.mp4"))
    build_music(os.path.join(SRC, "music", "synth.wav"))
    with open(os.path.join(EP, "episode.md"), "w", encoding="utf-8") as f:
        f.write("# Test episode\n\n- **Languages:** spoken en\n\n**Stage:** ingest\n")
    info = {"duration": round(dur, 3), "mic_offset": MIC_DELAY, "defects": truth,
            "sentences": SENTENCES}
    with open(truth_path, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    with open(marker, "w") as f:
        f.write(str(VERSION))
    return info


if __name__ == "__main__":
    info = build(force="--force" in sys.argv)
    print(f"fixture ready in {EP}: {info['duration']:.1f} s, {len(info['defects'])} planted defects")
    for d in info["defects"]:
        print(f"  {d['kind']:<22} {d['start']:6.2f} - {d['end']:6.2f}")
