# Media: faster-whisper (transcription), gdown (Drive listing) and the two pinned Whisper models.
echo "· media packages and transcription models"
venv .venv
pipi .venv/bin/python -r tools/requirements-media.txt
model transcribe
model transcribe-quick
