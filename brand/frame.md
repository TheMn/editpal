---
version: 1
name: Editpal default
description: >
  A neutral, confident default: a cool white ground, one graphite ink, one vermilion accent.
  Flat planes and hard edges, no glow, no gradients, no glass. Replace the values below with the
  channel's own (run /setup); every kit piece reads only this file.

colors:
  ground: "#F4F5F7"      # light planes, cards
  ink: "#12161C"         # text on light; dark planes
  accent: "#F2542D"      # the one accent: bars, highlight word, numbers
  accent-ink: "#12161C"  # text on the accent
  muted: "#5A6472"       # secondary text on light
  panel: "#FFFFFF"       # lists and callout surfaces
  line: "#D5D9DF"        # hairlines
  scrim: "#000000"       # shadow behind captions over footage

typography:
  latin:                 # Latin text; files live in brand/fonts/
    family: Inter
    files: [{ file: Inter-latin-variable.woff2, range: latin }]
    display-weight: 800
    text-weight: 500
  persian:               # Persian text (right-to-left); load both files so English words and digits work
    family: Vazirmatn
    files:
      - { file: Vazirmatn-arabic-variable.woff2, range: arabic }
      - { file: Vazirmatn-latin-variable.woff2, range: latin }
    display-weight: 800
    text-weight: 500
  scale:                 # sizes in % of the frame height (landscape 1080 -> 1% = 10.8 px)
    display: 9.5         # chapter and title cards
    headline: 6.0        # callouts, list points
    name: 4.4            # lower-third name
    body: 3.4            # roles, labels
    stat: 16.0           # big numbers
  tracking: -0.02        # em, display sizes only (Latin)
  line-height: 1.08

spacing:                 # % of the frame width (height for vertical gaps in portrait)
  margin: 5.2            # outer margin; text stays inside it
  gap: 1.6
  radius: 0.5            # corner radius of surfaces; 0 = square

motion:                  # seconds; eases are GSAP names
  enter: 0.5
  exit: 0.28
  stagger: 0.09
  ease-in: expo.out      # things land on a long tail
  ease-out: power3.in    # and leave quickly

captions:                # burned-in word captions (Shorts, ./pal subs burn)
  font: latin            # latin | persian (Persian text always uses persian)
  size: 5.4              # % of the frame height
  weight: 800
  color: "#FFFFFF"
  highlight: "#FFD23F"   # the spoken word
  background: none       # none | a colour: a box behind each line
  outline: 0.35          # % of frame height, drawn in scrim colour
  position: 24           # % of the frame height from the bottom to the baseline of the last line
  max-words: 4
  max-width: 82          # % of the frame width

components:
  lower-third:  { surface: ink, text: ground, bar: accent, role: muted-on-ink }
  title-card:   { surface: accent, text: accent-ink, kicker: ink }
  callout:      { surface: ink, text: ground, accent: accent }
  stat:         { surface: ink, number: accent, label: ground }
  list:         { surface: ground, text: ink, marker: accent }
  pip-frame:    { surface: ground, text: ink, radius: 1.4, border: ink }
  sting:        { surface: accent, mark: accent-ink }
  end-card:     { surface: ink, text: ground, accent: accent }
---

# Editpal default

## What this look is for

A starting point that is already usable: informational videos, talking-head lessons and Shorts. It
reads clearly on top of footage and on its own. The accent marks the single thing to look at.

## Do

- One accent per frame: a bar, a number or the spoken word, never all three.
- Flat colour planes with hard edges; type does the work. Land, then hold still.
- Keep text inside the margin (5% of the width) and out of the speaker's face.
- Persian text is right-to-left with Vazirmatn; Latin words inside it stay left-to-right.

## Don't

- No glow, bloom, gradients, glass cards, drop-shadow haze or particles.
- No logo in a corner, no frame borders, no looping or breathing motion on text.
- No more than 12 words on a card; cut words rather than shrinking type.

## Changing it

Edit the values above; nothing else needs to change. Then run `./pal brand check --approve` to
accept the new look as the reference. To use another font, add its files to `brand/fonts/`
(open licences only) and name them under `typography`.
