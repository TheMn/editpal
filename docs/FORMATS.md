# File formats

Every file editpal reads or writes. Text files are in git; media is in `build/` and Drive.
All times are seconds. Times in `edit.json` and `plan.json` sit on the project's frame grid.

## The channel

`channel.json` (written by `/setup`):

```json
{
  "name": "", "youtube": "", "instagram": "",
  "drive": "https://drive.google.com/drive/folders/…",
  "upload": { "env": "EDITPAL_UPLOAD_URL", "folder": "editpal-out" },
  "languages": { "spoken": "en", "dub": [], "subtitles": ["en"], "graphics": "en" },
  "formats": ["talking-head"],
  "review": "standard",
  "video": { "fps": 30, "draft_height": 1080 },
  "loudness": { "long": -16, "short": -14, "true_peak": -1.5 },
  "music": { "moods": [], "allow": ["CC0", "PD", "own"] },
  "voices": { "host": "voices/host" },
  "cue_word": ""
}
```

- `languages.spoken`: what is said in recordings (`fa`, `en`, …). `dub`: languages that get a
  cloned-voice track. `graphics`: language of on-screen text (`en`, `fa`, or `per-language` to
  render the picture once per language).
- `review`: `careful` (every gate stops) · `standard` (paper edit, storyboard, draft) · `fast`
  (storyboard only).
- `cue_word`: a word the creator says after a flub ("again"); the take before it is dropped.

`channel.md`: niche, audience, tone, **names and terms** (spelling, pronunciation, translation),
**standing preferences** learned from notes.

## An episode: `episodes/<yyyy-mm>-<slug>/`

| File | Holds |
| --- | --- |
| `episode.md` | stage, the gate it waits at, decisions, what was delivered (the resume point) |
| `brief.md`, `script.md` | the one idea; the script with line ids (`L01 …`) |
| `sources.json` | every media file, its role, how it was conformed, sync offsets |
| `transcript.raw.json` | words on the **source** timeline |
| `edit.json` | the A-cut |
| `transcript.json` | words on the **edited** timeline (same word ids) |
| `translation.<lang>.json` | the translation used by both the dub and the subtitles |
| `plan.json` | beats, plates, captions, music, effects, chapters |
| `subs/<lang>.srt`, `.vtt` | subtitles on the final timeline |
| `hf/` | HyperFrames source of this episode's plates (code; its media is not in git) |
| `package.md`, `credits.md`, `notes.md` | metadata; licence ledger; the creator's notes and what was done |
| `build/` | `source/` `conform/` `proxy/` `cut/` `audio/` `dub/` `plates/` `chunks/` `sheets/` `review/` `out/` `jobs/` |

### `sources.json`

```json
{
  "v": 1, "fps": 30, "size": [1920, 1080], "master": "camA", "audio_master": "mic",
  "sources": {
    "camA": { "role": "a-roll", "file": "build/source/IMG_0012.MOV", "drive_id": "1AbC…",
              "conform": "build/conform/camA.mp4", "proxy": "build/proxy/camA.mp4",
              "duration": 612.4, "size": [3840, 2160], "fps_in": 29.97,
              "vfr": true, "hdr": false, "rotation": 0, "audio": true, "offset": 0.0 },
    "mic":  { "role": "mic", "file": "build/source/mic.wav", "conform": "build/conform/mic.wav",
              "duration": 615.0, "offset": 1.384, "drift": 0.004 }
  }
}
```

- Roles: `a-roll` `screen` `mic` `b-roll` `image` `music` `voice-clip` `subtitles` `script` `other`.
- **Master time** is time in the `master` source. For any other source,
  `time in that source = master time + offset`. `drift` is how much the offset changes from the
  start to the end of the recording.
- `conform` files are constant frame rate at the project `fps`, SDR, upright, with a keyframe
  every second; everything downstream reads them, never `file`.
- A generated video has `"master": null` and no `a-roll`.

### `transcript.raw.json` / `transcript.json`

```json
{
  "language": "fa", "duration": 612.4, "model": "large-v3", "source": "mic", "timeline": "source",
  "words":    [{ "id": "w1", "w": "سلام", "start": 0.52, "end": 0.91, "p": 0.98 }],
  "sounds":   [{ "id": "u1", "kind": "um", "start": 3.10, "end": 3.52 }],
  "segments": [{ "id": "s1", "start": 0.52, "end": 4.20, "first": "w1", "last": "w9", "text": "…" }],
  "flags":    [{ "start": 2006.0, "end": 2010.5, "kind": "repeat-suspect" }]
}
```

- `sounds`: voiced audio with no word on it (`um`, `breath`, `noise`): what the transcriber hides.
- `flags`: spans the transcriber probably got wrong (a line repeated over silence, impossible
  speed); never cut from them without listening.
- Never read these files whole. `./pal transcribe show <episode>` prints one line per sentence:
  `s12 w210-228 1:02.4 +0.9 | text ⟨um 0.4⟩` (`+0.9` = pause after it).

### `edit.json`: the A-cut

```json
{
  "v": 1, "fps": 30, "locked": null, "adopted": false,
  "rhythm": { "in_sentence": 0.14, "between": 0.42, "beat": 0.75, "noise_floor_db": -58 },
  "keep": [
    { "id": "K001", "src": "camA", "in": 12.433, "out": 19.167, "first": "w31", "last": "w52", "section": "hook" },
    { "id": "K002", "src": "camA", "in": 24.900, "out": 31.300, "first": "w70", "last": "w88",
      "angle": "camB", "audio_lead": -0.2, "audio_tail": 0.25 }
  ],
  "removed": [
    { "id": "C002", "in": 19.167, "out": 24.900, "kind": "retake", "text": "If you're a brand, if you-",
      "why": "restarted; the next take is complete", "by": "tool", "ok": true,
      "seam": { "gap": 0.40, "flag": null } }
  ],
  "protect": [{ "first": "w410", "last": "w520", "kind": "sponsor" }]
}
```

- `keep` in order **is** the timeline; reordering is moving an entry. `in`/`out` are master time.
- `angle`: take the picture from another synced source for this range. `audio_lead`/`audio_tail`:
  the sound starts before / ends after the picture (J and L cuts).
- `removed[].kind`: `slate` `pause` `filler` `false-start` `retake` `tangent` `repeat`
  `off-script` `suggest`. A `suggest` is only an idea: it is not cut until the creator says so.
  `ok: false` keeps the material (the creator said `keep C002`).
- `protect`: ranges that are never trimmed and never clipped into Shorts.
- `locked`: a hash set by `./pal cut lock` at picture lock; a later change clears it.
- `adopted: true`: the creator brought their own A-cut; `keep` is one range over that file.

### `translation.<lang>.json`

```json
{
  "v": 1, "from": "fa", "to": "en", "voice": "host", "duration": 560.2,
  "glossary": { "الگوریتم": "algorithm" },
  "segments": [
    { "id": 1, "start": 0.52, "end": 4.20, "src": "…", "text": "Hi, and welcome back.",
      "read": "", "note": "", "skip": false }
  ]
}
```

- Times are on the **edited** timeline. `text` is what the voice says; `read` (optional) is the
  fuller wording for subtitles when `text` had to be shortened to fit its time.
- `voice: null` means subtitles only, no dub. `skip: true`: not voiced (a filler line).

### `plan.json`

```json
{
  "v": 1, "edit": "<edit.json locked hash>", "mode": "plates",
  "sections": [{ "id": "S2", "anchor": "w96", "title": "Why pauses matter" }],
  "beats": [
    { "id": "B03", "anchor": "w96", "until": "w120", "t": [41.2, 47.0], "layout": "pip",
      "plate": { "id": "P03", "type": "custom", "src": "hf/compositions/p03.html", "alpha": false },
      "text": { "en": { "title": "Pauses carry meaning" }, "fa": { "title": "مکث معنا دارد" } },
      "sfx": [{ "id": "whoosh", "at": 0.0 }], "est_render_s": 45, "status": "posed" },
    { "id": "B04", "anchor": "w140", "t": [52.0, 56.5], "layout": "lower-third",
      "plate": { "id": "P04", "type": "kit", "kit": "lower-third", "alpha": true },
      "text": { "en": { "name": "Sara Moradi", "role": "Host" } } },
    { "id": "B05", "anchor": "w171", "until": "w190", "layout": "punch", "punch": { "scale": 1.15 } },
    { "id": "B06", "t": [70.0, 76.0], "layout": "b-roll", "broll": { "src": "b1", "in": 3.0 } }
  ],
  "captions": { "burn": false, "style": "brand", "emphasis": ["w120"] },
  "music": [{ "id": "M1", "track": "library:<id>", "t": [0.0, 41.2], "gain_db": -20, "duck": true }],
  "redact": [{ "t": [130.0, 142.0], "rect": [0.60, 0.10, 0.30, 0.05] }]
}
```

- `mode`: `plates` (graphics laid over the A-cut) or `project` (the whole piece is one
  HyperFrames project: Shorts, generated videos under ~3 minutes).
- A beat is anchored to **word ids**; `t` is derived from them by `./pal plates time` and is
  recomputed after any re-cut. A beat with only `t` (B-roll over a pause) stays where it is.
- `layout`: `full` (plate covers the frame) · `pip` (plate full frame, speaker in a corner) ·
  `split` · `lower-third` · `over` (transparent graphic over the speaker) · `punch` (zoom on the
  speaker) · `b-roll` · `card` (chapter card).
- `plate.type`: `kit` (a `brand/kit/` composition filled with `text`) or `custom` (written for
  this beat by a `plate-maker`). `alpha: true` renders with a transparent background.
- `status`: `outline` → `posed` (still approved on the storyboard) → `rendered`.
- `redact.rect`: `[x, y, w, h]` as fractions of the frame.

### Voices: `voices/<speaker>/`

`voice.json`: `{ "name": "", "engine": "", "language": "en", "speed": 1.0, "seed": 1,
"reference": { "en": "en.wav", "fa": "fa.wav" } }`, plus the clips (`<lang>.wav`, 6–10 s) and
their exact words (`<lang>.txt`). A line in a language without its own clip borrows another and
may carry its accent. `VOICE.md`: how this person talks and writes.

### `credits.md`: the licence ledger

One row per outside item used: what, where in the video, source page, licence, credit line (if
the licence asks for one). Nothing enters a video without a row.
