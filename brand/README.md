# brand/

`frame.md` is the channel's look (colours, fonts, sizes, motion, caption style). `kit/` holds the
reusable graphics; they read only `frame.md`. `fonts/` holds the font files. `reference/` holds the
approved test stills (`./pal brand check` compares against them).

## The kit (`./pal plates kits`, `./pal plates kit <name> --vars '{…}' -o out.mov`)

| Piece | For | Variables | Output |
| --- | --- | --- | --- |
| `lower-third` | name and role under the speaker | `name`, `role` | alpha, 5 s |
| `title-card` | chapter or section card | `kicker`, `title`, `wipe` (0 = opaque from frame 1) | alpha or opaque, 4 s |
| `callout` | one short phrase beside the speaker | `text`, `side` | alpha, 4 s |
| `stat` | a number that counts up, with a label | `value`, `label` | alpha, 4 s |
| `list` | title and up to 4 points, one by one (pip/split) | `title`, `items` | opaque, 6 s |
| `caption` | word-timed captions for Shorts | `words` = `[{w,start,end}]` | alpha, any length |
| `pip-frame` | graphic area with the speaker as rounded picture-in-picture | `title`, `text` (+ footage) | opaque, 6 s |
| `sting` | 1.5 s intro mark | `mark` | alpha, 1.5 s |
| `end-card` | 10 s end card with rooms for YouTube end-screen elements | `title`, `sub` | opaque, 10 s |

Every piece works left-to-right and right-to-left (`--lang fa` renders `dir="rtl"` with the Persian
font and mirrored motion). Text in a plan beat goes in `text.<lang>` with these variable names.
`plan.json` beats use them as `"plate": {"type": "kit", "kit": "callout", "alpha": true}`.

## Restyle

Edit the values in `frame.md` only (`/setup` does this): colours, the two font roles (add font files
to `fonts/`, open licences only), `scale` sizes in % of the frame height, `spacing`, `motion`,
`captions`. Then `./pal brand test`, look at `reference/*.jpg`, and `./pal brand check --approve`.
Later edits to `brand/` are caught by `./pal brand check` (names the stills that drifted).

## Add a piece

1. `brand/kit/<name>/kit.json`: `about`, `alpha`, `dur`, `layouts`, `still` (seconds at which it reads
   best), `vars` (defaults), `"video": true` if it shows footage.
2. `brand/kit/<name>/<name>.html`: a scene file (`<template>` with style, a root `#root` and script).
   Put `/*BRAND*/` first in the `<style>`; use `{{id}}` to prefix every id and class, `{{dur}}`, `{{dir}}`,
   `{{W}}`, `{{H}}`, `{{enter}}`, `{{exit}}`, `{{ease_in}}`, `{{ease_out}}`, `{{stagger}}`. Colours and
   sizes only as `var(--c-ink)`, `calc(var(--u) * var(--s-name))` (`--u` is 1% of the frame height,
   `--w` 1% of the width), fonts as `var(--font-text)`. Use logical CSS properties and `S = rtl ? -1 : 1`
   for slides. One paused GSAP timeline registered as `window.__timelines["{{id}}"]`, `fromTo` only.
3. Read the rules in `.claude/skills/video/hyperframes/OVERRIDES.md`; test with
   `./pal plates kit <name> --check -o /tmp/x.mov` in English and `--lang fa`.
