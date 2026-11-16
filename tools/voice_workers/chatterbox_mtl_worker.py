"""Chatterbox Multilingual worker (runs in .venv-voice; tools/voice.py starts it). Cloning in 23 languages.

Usage: python chatterbox_mtl_worker.py <model folder>
One JSON request per stdin line: {"text", "lang", "ref", "out", "seed", "temperature"}; writes a WAV to
"out" and answers one JSON line {"ok": true, "sr": ...} or {"ok": false, "error": "..."}.
The model loads once and each reference clip is prepared once. When the reference clip is in another
language than the text (a Persian clip, an Italian line), the result can carry the clip's accent.
Code and weights: Chatterbox by Resemble AI, MIT (see tools/models.json).
"""
import json
import os
import sys

out = sys.stdout
sys.stdout = sys.stderr          # library prints must never reach the protocol channel
os.environ.setdefault("TQDM_DISABLE", "1")
import torch  # noqa: E402
import soundfile as sf  # noqa: E402
from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # noqa: E402

torch.set_num_threads(int(os.environ.get("VOICE_THREADS", "2")))
model = ChatterboxMultilingualTTS.from_local(sys.argv[1], "cpu")
ready_ref = None
print(json.dumps({"ok": True, "ready": True}), file=out, flush=True)
for line in sys.stdin:
    try:
        r = json.loads(line)
        if r["ref"] != ready_ref:
            model.prepare_conditionals(r["ref"])
            ready_ref = r["ref"]
        torch.manual_seed(int(r.get("seed", 1)))
        wav = model.generate(r["text"], language_id=r["lang"], temperature=float(r.get("temperature", 0.8)))[0].numpy()
        sf.write(r["out"], wav, model.sr)
        print(json.dumps({"ok": True, "sr": model.sr}), file=out, flush=True)
    except Exception as e:  # report and keep serving
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}), file=out, flush=True)
