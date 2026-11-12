# Tools: `./pal <command>`

One entry point. `./pal` lists the commands; `./pal <command> --help` prints the full usage.
`<ep>` is an episode folder or any unique part of its name (`recursion`).

Rules all commands follow: media goes to `<ep>/build/`; at most ~30 lines of output (long tables
go to a file whose path is printed); results are cached, so running a command again only redoes
what changed; exit code `3` means "needs something from the creator" (the message says what).

## Media in

| Command | Does | Writes |
| --- | --- | --- |
| `drive list` | every file in the channel's shared folder, by subfolder, with sizes | — |
| `drive get <folder> <ep>` | downloads that subfolder (refuses when it would not fit on disk; `--only <pattern>`) | `build/source/` |
| `drive put <ep> <file>…` | uploads to the creator's output folder; prints the link. Exit 3 when no upload link is set | Drive `editpal-out/<episode>/` |
| `ingest <ep>` | probes each source, guesses roles, conforms (constant frame rate, SDR, upright, project fps), makes proxies and contact sheets. `--roles camA=a-roll,mic=mic` corrects a guess | `sources.json`, `build/conform/` `proxy/` `sheets/` |
| `sync <ep>` | lines up every source that has sound against the master by its audio; reports drift | `sources.json` offsets |
| `transcribe <ep>` | words with times in the spoken language, plus the sounds a transcriber hides (`um`, breaths) and suspect spans. `--lang`, `--source`, `--quick` | `transcript.raw.json` |
| `transcribe show <ep>` | compact view, one line per sentence. `--raw` (source timeline) / default edited; `--from 60 --to 120`; `--words` | — |
| `transcribe file <media> -o <json>` | the same for any file | the JSON |
| `restore <ep>` | re-downloads the sources by Drive id and rebuilds `conform/` and `proxy/` | `build/` |
| `clean <ep>` | deletes caches that can be rebuilt (`--all`: everything in `build/` except `out/`) | — |

## The A-cut

| Command | Does | Writes |
| --- | --- | --- |
| `cut propose <ep>` | proposes the cut: slate, long pauses, fillers, false starts, retakes. `--tight` / `--natural` (default) / `--loose` | `edit.json`, `build/review/cuts.md` |
| `cut apply <ep> <ops.json>` | applies decisions written in ids (below); validates, snaps to quiet points and the frame grid | `edit.json` |
| `cut render <ep>` | renders the A-cut and the cleaned voice stem; `--preview` makes a small fast copy | `build/cut/acut.mp4`, `voice.wav`, `acut-preview.mp4` |
| `cut verify <ep>` | transcribes the A-cut again and compares with the kept words; checks every seam | `build/review/seams.json`, flags in `edit.json` |
| `cut remap <ep>` | the transcript on the edited timeline | `transcript.json` |
| `cut lock <ep>` | picture lock | `edit.json.locked` |
| `cut adopt <ep> <file>` | use the creator's own A-cut instead | `edit.json` (`adopted`) |
| `cut table <ep>` | the cut list as a table | — |

Operations for `cut apply` (a JSON list):

```json
[{ "op": "remove", "from": "w210", "to": "w228", "kind": "retake", "why": "restarted" },
 { "op": "remove_time", "from": 221.0, "to": 235.0, "kind": "tangent", "why": "…" },
 { "op": "keep", "id": "C012" },
 { "op": "loosen", "id": "C007", "by": 0.15 },
 { "op": "tighten", "id": "C031", "by": 0.10 },
 { "op": "move", "keep": "K030", "after": "K002" },
 { "op": "protect", "from": "w410", "to": "w520", "kind": "sponsor" },
 { "op": "suggest", "from": "w600", "to": "w655", "why": "repeats the point made at 2:10" }]
```

## Looking at footage

| Command | Does |
| --- | --- |
| `sheet contact <media> -o <jpg>` | timestamped contact sheet (`--every 20`, `--cols 6`) |
| `sheet frames <media> --at 12.5,40 -o <dir>` | single frames |
| `sheet seams <ep>` | one strip per cut: frames either side, waveform, the words (`--flagged`: only flagged ones) |
| `sheet reel <ep>` | one audio file with ±1.5 s around every cut, numbered |

## Review pages

`board <kind> <ep>` writes a self-contained page to `build/review/<kind>.html` (images and audio
inside the file, every item with a visible id, a "copy my notes" button).

| Kind | Shows |
| --- | --- |
| `paper` | the transcript with removed parts struck through and tagged, lengths, the A-cut audio, the seam reel, raw vs cleaned voice |
| `story` | lanes, one card per beat, caption sample, music previews, effects, shots to collect, render estimate |
| `draft` | check results, the beat list with times, where the draft file is |
| `shorts` | candidate moments with stills and first lines |
| `thumbs` | thumbnail options at feed size |

## Voice, dub, subtitles, sound

| Command | Does | Writes |
| --- | --- | --- |
| `voice prepare <speaker> <media>` | picks the best 6–10 s of clean speech as the clone's reference (`--lang`, `--from/--to`) | `voices/<speaker>/` |
| `voice test <speaker>` | speaks test lines from each reference clip and engine, to listen and choose | `voices/<speaker>/test/` |
| `voice say <speaker> --lang en --text "…" -o <wav>` | one line | the file |
| `voice script <ep>` | voices `script.md` line by line (generated videos) and times every word | `build/audio/voice.<lang>.wav`, `transcript.json` |
| `dub init <ep> --to en` | the translation file from the transcript, or from the creator's own subtitles if they are in `build/source/` | `translation.en.json` |
| `dub check <ep> --to en` | lines with no translation or too long for their time | — |
| `dub voice <ep> --to en` | voices every line in the clone, timed to the original; only changed lines are redone | `build/dub/voice.en.wav`, `report.txt` |
| `dub verify <ep> --to en` | transcribes the dub and lists lines that were misread | `build/dub/verify.txt` |
| `subs make <ep>` | subtitles for every language in `channel.json` (spoken from the transcript, others from the translation) | `subs/<lang>.srt`, `.vtt` |
| `subs lint <file>` | line length, reading speed, duration, overlaps | — |
| `subs burn <video> <srt> -o <mp4>` | burned-in copy in the brand's caption style (right-to-left safe) | the file |
| `subs file <media> --lang fa -o <dir>` | subtitles for any finished video, without an episode | `.srt`, `.vtt`, transcript |
| `music list` / `get <id>` / `preview <id> <mp3>` / `add` | the free music library | cache |
| `mix <ep>` | the bed (music + effects from `plan.json`) and one mix per language at the loudness target (`--lang`, `--short`) | `build/audio/bed.wav`, `mix.<lang>.wav` |

## Graphics and the final picture

| Command | Does | Writes |
| --- | --- | --- |
| `hf <arguments>` | HyperFrames with telemetry, update checks and account commands switched off | — |
| `plates time <ep>` | recomputes every beat's time from its word anchors | `plan.json` |
| `plates stills <ep>` | poses every beat on the real frame and snapshots them all in one run | `build/review/stills/` |
| `plates render <ep>` | renders the plates one after another; only changed ones (`--only P03,P07`, `--draft`) | `build/plates/` |
| `brand test` | the 10 s brand test (sting, lower third, caption, end card) | `brand/reference/test.mp4` |
| `brand check` | the approved reference frames still look the same (`--approve` to accept a new look) | — |
| `composite <ep> --draft` | plates, B-roll, punch-ins, redactions and captions over the A-cut, with timecode and beat ids burned in; 1080p | `build/out/draft.mp4` |
| `composite <ep> --final` | the same at source resolution, clean; one audio file per language | `build/out/<slug>.mp4`, `<slug>.<lang>.m4a` |
| `reframe <video> -o <mp4>` | 9:16 from 16:9: follows the face, or stacks screen and face (`--mode track|center|stack`, `--from/--to`) | the file |
| `thumb <ep>` | sharp, expressive frame candidates; renders thumbnail options at 1280×720 | `build/out/thumbs/` |
| `qc <video>` | flash, black and frozen frames, loudness, clipped audio, duration (`--ep` adds seam and caption checks) | report |
| `export <ep> --fcpxml` | the cut as a timeline for DaVinci Resolve, Premiere or Final Cut (`--edl`, `--otio`) | `build/out/<slug>.fcpxml` |

## Upkeep

| Command | Does |
| --- | --- |
| `doctor` | checks the machine (ffmpeg, Python, Node, models, disk, fonts), the channel files and how old the upstream pins in `tools/versions.json` are |
| `test` | builds a small generated clip and runs the whole toolchain on it with assertions |
| `update` | pulls improvements from the editpal template into this copy, keeping the channel's own files |
