# Voices (skipped by `sh tools/setup.sh --no-voice`): .venv-voice holds the speech engines with CPU PyTorch;
# the pinned models are Chatterbox Nano (English cloning), MOSS-TTS-Nano (Persian and English cloning)
# and Kokoro (stock English voice), about 3 GB in all.
echo "· .venv-voice: speech engines"
venv .venv-voice
.venv-voice/bin/python -c 'import torch' 2>/dev/null || pipi .venv-voice/bin/python torch==2.6.0 torchaudio==2.6.0 --index-url $TORCH_CPU
pipi .venv-voice/bin/python -r tools/requirements-voice-engines.txt
.venv-voice/bin/python -c 'import chatterbox' 2>/dev/null ||
  pipi .venv-voice/bin/python --no-deps "chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox.git@ab55923c27757c90cfcc407baa57dc25a7d25217"
.venv-voice/bin/python -c 'import onnx_tts_runtime' 2>/dev/null ||
  pipi .venv-voice/bin/python --no-deps "moss-tts-nano @ git+https://github.com/OpenMOSS/MOSS-TTS-Nano.git@8b7bcc9341b3b4ef3a3a58ba1338a7d85ff133eb"
# spaCy's small English model (MIT) for Kokoro's text front end; the wheel is named for pip's rules
.venv-voice/bin/python -c 'import en_core_web_sm' 2>/dev/null || {
  fetch https://huggingface.co/spacy/en_core_web_sm/resolve/8fb6f8155286360bf5486fe399e2738d1df7ded2/en_core_web_sm-any-py3-none-any.whl \
    "$CACHE/spacy/en_core_web_sm-3.7.1-py3-none-any.whl"
  pipi .venv-voice/bin/python --no-deps "$CACHE/spacy/en_core_web_sm-3.7.1-py3-none-any.whl"; }
echo "· voice models"
model voice-chatterbox-nano
model voice-moss-nano tts
model voice-moss-nano codec
model voice-kokoro
