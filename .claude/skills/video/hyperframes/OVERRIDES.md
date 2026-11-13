# Overrides: read this first; it wins over every other file in this folder

The files here are HyperFrames' own guidance, copied unchanged. editpal uses HyperFrames in a fixed
way. Where a file says otherwise, follow this page.

## Running it

- Always `./pal hf <command>` (never `npx hyperframes`). It pins the local version, switches off
  telemetry, update checks and auto-install, and refuses `auth`, `cloud`, `lambda`, `cloudrun`,
  `publish`, `feedback`, `events`, `upgrade`, `skills` and `media-use generate`.
- Ignore every "usage beacon", `events`, `usage`, `feedback --rating`, "Framey", "HyperFrames
  desktop app", Studio preview/`preview` and `open`/`catch-up` instruction. Never sign in; never use
  HeyGen, cloud rendering, publishing or the desktop app.
- Render plates with `./pal plates render <ep>` (one plate at a time, alone, cached), never with a
  bare `hyperframes render`. Look at frames with `./pal hf snapshot --at t1,t2` (all times in one run);
  `./pal plates stills <ep>` poses every beat on the real A-cut frame. `check` is `./pal hf check`
  (run it on `<ep>/hf`); fix every error. Warnings `film_silent` and `dead_stretch` are expected for a plate.
- Storyboards, approvals and "show the person" happen on editpal's review pages (`./pal board story <ep>`),
  not in HyperFrames Studio. Skip `story.md` storyline pitching unless the creator asked for options.

## Where things come from

- The look is `brand/frame.md` (read it, quote values exactly); fonts are in `brand/fonts/`.
  Prefer a piece from `brand/kit/` (`./pal plates kits`); write a custom plate only when no kit piece fits.
- Media comes only from the episode's own sources, `library/` and `brand/`. Every outside item
  (image, clip, sound, font) gets a row in the episode's `credits.md` before use. No downloads at
  render time, no network at all: no CDN fonts, no remote images, no `capture` of websites.
- Do not use the registry (`catalog`, `add`), `media-use`, `tts`, `transcribe`, `remove-background`:
  voices, words and cut-outs come from the other `./pal` commands.

## Rules learned by measuring (see docs/RENDERING.md)

- Fonts: never name Inter, Montserrat etc. by family name (HyperFrames then fetches them from Google
  Fonts at render time). Declare your own family with `@font-face` to `assets/fonts/<file>`; the kit
  uses `EPLatin` and `EPPersian`. The GSAP tag stays `https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js`:
  the renderer serves it from node_modules, no request is made.
- Text goes in variables (`data-variable-values` on the host, read with `window.__hyperframes.getVariables()`),
  so one composition renders Persian and English. A sub-composition does not see the root's variables.
- A plate is a scene file in `<ep>/hf/compositions/<id>.html`; `./pal plates` writes `hf/solo/<id>.html`
  (a root that mounts only that scene) and renders it with `-c`. Keep every root-level `.html` out of
  the project except `index.html` (extra roots fail lint `multiple_root_compositions`).
- Transparent plates: the root and `html, body` background stay `transparent`; no full-frame fill
  unless the plate is meant to be opaque. Output format is chosen by `./pal plates`, not by you.
- Footage inside a plate (`<video>`): `muted`, timed on the video itself, encoded with a keyframe every second.
- Everything on screen is a pure function of timeline time. No timers, no `Math.random()`.

## Right-to-left (Persian) rules, verified by rendering

- Set `lang="fa" dir="rtl"` on the scene root. Use logical CSS (`inset-inline-start`, `padding-inline`,
  `text-align: start`) so layouts mirror; multiply horizontal slide distances by -1 for rtl.
- One font family, two files: Vazirmatn Arabic-script file and its Latin file, each with its
  `unicode-range`, so Persian letters, Persian digits, Latin words and digits each find their glyphs.
- Latin words and digits inside Persian text keep their own left-to-right order by themselves. A
  standalone number or Latin snippet in an rtl box: `direction: ltr; unicode-bidi: isolate`.
- `letter-spacing: 0` for Persian (tracking breaks the joined letters); `line-height` 1.3 or more
  (1.08 clips the dots and marks and fails `check` with `text_box_overflow`).
- Split text into words, never into letters (letter spans break the joining). Word spans are safe.
