"""MOSS-TTS-Nano worker (runs in .venv-voice; tools/voice.py starts it). Cloning in 20 languages.

Usage: python moss_worker.py <folder holding the two model folders>
Request: {"text", "ref", "out", "seed"}; answer: {"ok": true, "sr": 48000} or {"ok": false, "error"}.
ONNX on CPU, no PyTorch needed at run time. Code and weights Apache-2.0 (OpenMOSS).
"""
import json
import os
import sys
import tempfile

out = sys.stdout
sys.stdout = sys.stderr
import soundfile as sf  # noqa: E402
from onnx_tts_runtime import OnnxTtsRuntime  # noqa: E402

rt = OnnxTtsRuntime(model_dir=sys.argv[1], thread_count=int(os.environ.get("VOICE_THREADS", "2")),
                    output_dir=tempfile.gettempdir())
print(json.dumps({"ok": True, "ready": True}), file=out, flush=True)
for line in sys.stdin:
    try:
        r = json.loads(line)
        rt.synthesize(text=r["text"], prompt_audio_path=r["ref"], output_audio_path=r["out"],
                      seed=int(r.get("seed", 1)), enable_wetext=False)
        print(json.dumps({"ok": True, "sr": sf.info(r["out"]).samplerate}), file=out, flush=True)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}), file=out, flush=True)
