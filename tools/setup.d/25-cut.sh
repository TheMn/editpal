# A-cut: Pillow for the seam strips (numpy, soundfile and ffmpeg are already installed by the core part).
echo "· cut tools"
venv .venv
pipi .venv/bin/python -r tools/requirements-cut.txt
