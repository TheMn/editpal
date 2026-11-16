"""Kokoro worker (runs in .venv-voice; tools/voice.py starts it). Stock English voices, no cloning.

Usage: python kokoro_worker.py <model folder>
Request: {"text", "out", "voice": "af_heart", "speed": 1.0, "say": optional phonemes override};
answer: {"ok": true, "sr": 24000} or {"ok": false, "error"}.
Text becomes phonemes with misaki's own dictionary (no espeak, which is GPL), then Kokoro's ONNX
model speaks them. Kokoro weights Apache-2.0; misaki Apache-2.0; spaCy and its small English model MIT.
"""
import json
import os
import re
import sys
import warnings

out = sys.stdout
sys.stdout = sys.stderr
warnings.filterwarnings("ignore")
import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402
import soundfile as sf  # noqa: E402
from misaki import en  # noqa: E402

folder = sys.argv[1]
opts = ort.SessionOptions()
opts.intra_op_num_threads = int(os.environ.get("VOICE_THREADS", "2"))
session = ort.InferenceSession(os.path.join(folder, "onnx", "model.onnx"), opts, providers=["CPUExecutionProvider"])
vocab = json.load(open(os.path.join(folder, "tokenizer.json")))["model"]["vocab"]
g2p = {"us": en.G2P(trf=False, british=False, fallback=None), "gb": en.G2P(trf=False, british=True, fallback=None)}
voices = {}


def phonemes(text, voice):
    """Text -> Kokoro phoneme string; unknown words (marked ❓) are dropped."""
    ps, _ = g2p["gb" if voice[0] == "b" else "us"](text)
    return re.sub("❓", "", ps)


def speak(ps, voice, speed):
    """Phoneme string -> float32 samples at 24 kHz (long input is cut at punctuation, 500 tokens max)."""
    if voice not in voices:
        voices[voice] = np.fromfile(os.path.join(folder, "voices", voice + ".bin"), dtype=np.float32).reshape(-1, 256)
    chunks, cur = [], ""
    for part in re.split(r"(?<=[.!?;:,])\s+", ps):
        if len(cur) + len(part) > 400 and cur:
            chunks.append(cur)
            cur = ""
        cur = (cur + " " + part).strip()
    chunks.append(cur)
    wavs = []
    for c in chunks:
        ids = [vocab[ch] for ch in c if ch in vocab][:510]
        style = voices[voice][min(len(ids), len(voices[voice]) - 1)][None]
        w = session.run(None, {"input_ids": np.array([[0, *ids, 0]], dtype=np.int64), "style": style.astype(np.float32),
                               "speed": np.array([speed], dtype=np.float32)})[0][0]
        wavs += [w, np.zeros(int(0.12 * 24000), dtype=np.float32)]
    return np.concatenate(wavs[:-1])


print(json.dumps({"ok": True, "ready": True}), file=out, flush=True)
for line in sys.stdin:
    try:
        r = json.loads(line)
        voice = r.get("voice") or "af_heart"
        ps = r["say_phonemes"] if r.get("say_phonemes") else phonemes(r["text"], voice)
        sf.write(r["out"], speak(ps, voice, float(r.get("speed", 1.0))), 24000)
        print(json.dumps({"ok": True, "sr": 24000}), file=out, flush=True)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}), file=out, flush=True)
