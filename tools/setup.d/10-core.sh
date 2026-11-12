# Core: Node packages (HyperFrames, pinned) and the main Python environment.
echo "· node packages"
npm install --no-audit --no-fund --loglevel=error
echo "· .venv"
venv .venv
pipi .venv/bin/python -r tools/requirements.txt
command -v ffmpeg >/dev/null || echo "! ffmpeg is missing"
node -e 'process.exit(+process.versions.node.split(".")[0] >= 22 ? 0 : 1)' || echo "! HyperFrames needs Node 22+"
