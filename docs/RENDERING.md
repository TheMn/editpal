# Rendering facts (HyperFrames 0.9.31, measured on the 4-core cloud machine, no GPU)

All numbers: 1920x1080, one render at a time, software GL. "Start-up" (Chrome launch, compile) is about 3-4 s of every figure.

| Spike | Result |
| --- | --- |
| a. 6 s lower third, transparent, `--format mov` (ProRes 4444) | 21.7 s, 11.9 MB; the ProRes encode alone is 13.6 s |
| `--format webm` (VP9 alpha) | 17.7 s, 45 KB, but colours shift (accent #F2542D came out #FF5E27) and ffmpeg needs `-c:v libvpx-vp9` to read the alpha: rejected |
| `--format png-sequence` | 8.9 s, 4.0 MB (180 RGBA frames), colours exact |
| png-sequence -> ffmpeg `qtrle` ARGB .mov | +1.4 s, 1.7 MB: **chosen** (about 10 s total). ffv1 5.4 s, png-in-mov 3.0 s, prores_ks 19 s |
| overlay of that clip on 1080p footage (ffmpeg, 6 s) | 2.7 s with qtrle, 3.9 s with ProRes; `overlay=format=auto` |
| b. one scene alone | `render <proj> -c solo/<id>.html`; the solo root mounts one scene via `data-composition-src` |
| c. opaque 6 s title card, mp4 | draft 12.2 s / 96 KB at 30 fps, 8.9 s at 25; looks 13.8 / 12.3 s; delivery 12.8 / 10.6 s (sizes 92-136 KB) |
| d. plate with a `<video>` (pip), 6 s, mp4 | 16.7 s, 258 KB, BeginFrame capture; no frozen frames (picture changes in every 0.2 s sample) with `-g 30` footage |
| e. `snapshot --at` 9 stills, one run | 9.7 s |
| g. batch | `--variables` and `--batch` work only on a root (or standalone) composition, also with png-sequence; each row renders separately (8 s for a 4 s clip): no speed-up, so `./pal plates` bakes values into the host instead |

## What I saw

- Alpha composite (qtrle and PNG and ProRes alike): the lower third lands on footage with a hard, clean edge, rounded corners smooth, no fringe, no dark halo; accent bar measured (244,83,45) / (240,83,43) against the brand (242,84,45).
- Persian (title card, caption, list, lower third, stat, end card): letters joined, lines run right to left, the Latin word "Python" and "AI" sit in the right place inside the sentence, Western and Persian digits both render, `(Pause)` brackets mirror correctly. The first list render failed `check` (`text_box_overflow`): Persian needs line-height 1.3+.

## Where HyperFrames differs from its docs, or surprises

- `render -c` docs say a `<template>` scene must be mounted from `index.html`: any root file that mounts it works, in any folder. But `check` and `snapshot` take only a project folder (no `-c`), and a second root-level `.html` with a composition id fails lint `multiple_root_compositions`: keep solo roots in `solo/`.
- Transparent formats always use screenshot capture (message "BeginFrame did not run"); opaque renders use BeginFrame when the headless shell is found.
- Any font family named without `@font-face` (even bundled ones like Inter) is fetched from fonts.googleapis.com at render time. Own family names plus `@font-face` files make no request.
- `--quiet` still prints many `[INFO]` lines; capture the output. A pipe closed early (`| head`) kills the render.
- Variables reach a scene only through its host's `data-variable-values`; `getVariables()` returns just those keys, so merge your defaults.

## Browser, telemetry, network

- Chrome: `HYPERFRAMES_BROWSER_PATH` (alias `PRODUCER_HEADLESS_SHELL_PATH`) points at the executable; `tools/hf.py` sets it to `/opt/pw-browsers/chromium_headless_shell-*/…/chrome-headless-shell`. Without it HyperFrames uses /usr/bin/google-chrome in the slower screenshot mode. A download (`browser ensure`) needs storage.googleapis.com, which this machine's proxy refuses (403).
- With the opt-out variables, `check` and `render` made no request to posthog or any account service (source: telemetry honours `DO_NOT_TRACK`; run with a Node request logger: only 127.0.0.1 config calls). With HTTPS_PROXY pointed at a dead port, check and render still succeeded and nothing was cached from the network. The proxy log shows no HyperFrames hosts (its only 403s are another process, mobile.events.data.microsoft.com).
- GSAP is served from node_modules (`gsap@3.15.0` must match the CDN tag in the file).

## Planning figures

Alpha plate about 1.6 s of work per second of plate + 4 s; opaque 2.3 s per second + 4 s; pip plate about 2.5 s per second. `./pal brand test` (check, 5 stills, a 10 s render) takes about 20 s.
