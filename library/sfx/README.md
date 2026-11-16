# Sound effects

Made by `tools/sfx.py` (`./pal sfx build`); released CC0. Nothing here was downloaded or sampled:
every sound is synthesized (filtered noise sweeps, short sine and triangle blips, a light reverb
tail) with fixed random seeds, so rebuilding gives the same files.

| id | What it is | Length |
| --- | --- | --- |
| `whoosh` | soft swell, for a scene or plate entering | 1.0 s |
| `whoosh-short` | quick version for small movements | 0.5 s |
| `pop` | round blip, for an element appearing | 0.3 s |
| `click` | tiny dry click | 0.1 s |
| `tick` | high light tick, for counters and lists | 0.1 s |
| `impact` | low soft thump, for a title or a hard cut | 1.2 s |
| `riser` | 2 s noise and tone rise into a moment | 2.0 s |
| `sparkle` | bright rising chime, for a highlight | 1.3 s |
| `swipe` | short downward sweep, for wipes | 0.4 s |

Use them in `plan.json`: a beat's `"sfx": [{"id": "whoosh", "at": 0.0}]` (`at` is seconds after
the beat starts). `./pal mix` places them; effects are never ducked under the voice.

`./pal sfx list` shows what is in this folder. To add one, add its recipe to `tools/sfx.py`
(a new name at the end of `NAMES`, so the others keep their seeds).
