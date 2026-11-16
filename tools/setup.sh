#!/bin/sh
# Install everything editpal needs on this machine. Safe to run again; the cloud environment runs
# it at the start of every session.   sh tools/setup.sh [--no-voice]
# Needs: Node 22+, uv (or Python 3.12), ffmpeg. All downloads are free and licensed for commercial
# use; models are pinned in tools/models.json and cached in $EDITPAL_CACHE (default ~/.cache/editpal).
set -e
cd "$(dirname "$0")/.."
. tools/setup.d/lib.sh
for part in tools/setup.d/[0-9]*.sh; do
  case "$part" in *voice*) [ "$1" = "--no-voice" ] && continue ;; esac
  . "$part"
done
echo "ready. Try: ./pal doctor"
