"""Chatterbox worker (runs in .venv-voice; tools/voice.py starts it). English voice cloning.

Usage: python chatterbox_worker.py <model folder> <turbo|nano>
One JSON request per stdin line: {"text", "ref", "out", "seed", "temperature"}; writes a WAV to
"out" and answers one JSON line {"ok": true, "sr": ...} or {"ok": false, "error": "..."}.
The model loads once and each reference clip is prepared once.
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
from chatterbox.tts_turbo import ChatterboxTurboTTS  # noqa: E402

torch.set_num_threads(int(os.environ.get("VOICE_THREADS", "2")))
model = ChatterboxTurboTTS.from_local(sys.argv[1], "cpu", nano=(sys.argv[2] == "nano"))
ready_ref = None
print(json.dumps({"ok": True, "ready": True}), file=out, flush=True)
for line in sys.stdin:
    try:
        r = json.loads(line)
        if r["ref"] != ready_ref:
            model.prepare_conditionals(r["ref"])
            ready_ref = r["ref"]
        torch.manual_seed(int(r.get("seed", 1)))
        wav = model.generate(r["text"], temperature=float(r.get("temperature", 0.8)))[0].numpy()
        sf.write(r["out"], wav, model.sr)
        print(json.dumps({"ok": True, "sr": model.sr}), file=out, flush=True)
    except Exception as e:  # report and keep serving
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}), file=out, flush=True)
