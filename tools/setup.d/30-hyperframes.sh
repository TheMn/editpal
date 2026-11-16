# Graphics: HyperFrames (pinned in package.json, installed by 10-core), a headless Chrome for it, PyYAML.
echo "· graphics"
pipi .venv/bin/python pyyaml==6.0.3     # MIT: reads brand/frame.md
[ -x node_modules/.bin/hyperframes ] || echo "! HyperFrames is missing: run npm install"
if .venv/bin/python tools/hf.py --which | grep -q "none found"; then
  echo "! no headless Chrome found for HyperFrames (looked in /opt/pw-browsers, ~/.cache/ms-playwright, ~/.cache/puppeteer)."
  echo "  Install one with: npx playwright install chromium-headless-shell   (needs cdn.playwright.dev)"
  echo "  or ./pal hf browser ensure   (needs storage.googleapis.com), or set HYPERFRAMES_BROWSER_PATH."
fi
