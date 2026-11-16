# Helpers shared by the setup parts (sourced, not run).
CACHE=${EDITPAL_CACHE:-$HOME/.cache/editpal}
TORCH_CPU=https://download.pytorch.org/whl/cpu
export DO_NOT_TRACK=1 HYPERFRAMES_NO_TELEMETRY=1 HYPERFRAMES_NO_UPDATE_CHECK=1 HYPERFRAMES_NO_AUTO_INSTALL=1 HYPERFRAMES_SKIP_SKILLS=1

# venv <dir>: create a Python 3.12 environment if it is not there
venv() { [ -x "$1/bin/python" ] || { if command -v uv >/dev/null; then uv venv -q --python 3.12 "$1"; else python3 -m venv "$1"; fi; }; }
# pipi <python> <pip arguments>: install into that environment
pipi() { py=$1; shift; if command -v uv >/dev/null; then uv pip install -q --python "$py" "$@"; else "$py" -m pip install -q "$@"; fi; }
# fetch <url> <file>: download once, atomically
fetch() { [ -s "$2" ] && return 0; mkdir -p "$(dirname "$2")"; curl -fsSL --retry 3 -o "$2.part" "$1" && mv "$2.part" "$2"; }
# model <key> [<part>]: download the pinned files of one tools/models.json entry into $CACHE/<dir>
model() {
  node -e 'const j=require("./tools/models.json"), [k,p]=process.argv.slice(1), m=p?j[k][p]:j[k];
           for (const f of m.files) console.log(m.repo, m.revision, m.dir, f)' "$@" |
  while read -r repo rev dir f; do fetch "https://huggingface.co/$repo/resolve/$rev/$f" "$CACHE/$dir/$f" || exit 1; done
}
