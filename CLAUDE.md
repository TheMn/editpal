# editpal: this channel's video studio

This repository makes one channel's videos: script, edit, generated videos, dub, subtitles,
graphics, Shorts, packaging. The creator types a short request; a skill in `.claude/skills/` says
everything that happens next. **Find the skill and follow it to the end; stop only at its gates.**

| The creator asks | Skill |
| --- | --- |
| set up / change the channel, brand, voice, formats | `setup` |
| a new video: from a recording in Drive, or from a script with no footage | `video` |
| an idea, a brief, a script, a teleprompter text | `script` |
| another language's audio track in the cloned voice (or a fix to one) | `dub` |
| subtitles for a finished video | `subtitles` |
| Shorts / Reels | `shorts` |
| titles, thumbnail, description, chapters, tags | `package` |
| a note on anything already made ("C12 stays", "B07 pip", "3:12 too fast") | `notes` |

Before working: read `channel.json`, `channel.md`, and the episode's `episode.md` (the resume
point: stage, the gate it waits at, decisions). Update `episode.md` as you go and commit the
episode's text files at every gate. A new session must be able to continue from the files alone.

If `channel.json` has no `name`, the channel is not set up: run `setup` first.

## Show before build (the rule that matters most)

Nothing expensive is made before the creator has seen and accepted the cheap version of it.

| Gate | What they see (`./pal board …`) | They answer |
| --- | --- | --- |
| 1 Brief | in chat: the one idea, format, length, languages, deliverables, ≤ 5 questions with defaults | `ok` |
| 2 Paper edit | `paper`: the transcript with cuts struck through, the A-cut to listen to | `keep C12` · `cut C45` · `C7 looser` · `cut 3:41-3:55` · `lock` |
| 3 Storyboard | `story`: lanes, one card per beat on the real frame, music options | `B07 pip` · `B09 drop` · `M2` · `no sfx` · `go` |
| 4 Pilot | the first 30–60 s, finished | notes by time · `go` |
| 5 Draft | the whole video at 1080p with timecode; `draft`: check results | `3:12 too fast` · `final` |

`channel.json → review`: `careful` stops at every gate; `standard` at 2, 3 and 5; `fast` at 3
only. Gate 3 always stops unless the creator said "no stops". The pilot (gate 4) is also made the
first time a channel uses a format, whatever the setting.

Showing a page: build it with `./pal board <kind> <ep>`, then send
`build/review/<kind>.html` to the creator the best way this session offers (a rendered file in
the chat; else a published private page; else its path). Say in one line what to look at and
the reply words. Then stop and wait.

A note changes only what it names. Redo that piece, re-show that piece, keep everything else.

## Rules

- **Free and safe for a monetised channel.** Code and model weights MIT/Apache/BSD; music and
  images CC0/public domain or the creator's own. No paid services, no sign-ins, no accounts.
  Every outside item gets a row in the episode's `credits.md` before it is used.
- **Keep the creator's meaning and wording.** List every change you make to their words.
  On screen and in metadata: only facts from the recording, the script or the brief.
- **Languages** come from `channel.json → languages`: what is spoken, which languages get a
  cloned-voice track, which get subtitles, and the language of on-screen text. Persian text is
  right-to-left; code, numbers in code and Latin names stay left-to-right.
- **Media never goes in git.** It arrives from the Drive folder (`./pal drive get`) and results
  go back with `./pal drive put` (exit code 3 = no upload link: send the file in the chat and
  point to `docs/DRIVE.md`). Text files of an episode are committed; `build/` is not.
- **Tools.** Everything is `./pal <command>` ([docs/TOOLS.md](docs/TOOLS.md)); formats are in
  [docs/FORMATS.md](docs/FORMATS.md). HyperFrames only through `./pal hf` and `./pal plates`.
  Editing decisions are written in ids (words `w…`, cuts `C…`, beats `B…`); the tools own all times.
- **Stay small.** Never read a transcript file whole: `./pal transcribe show`. Look at contact
  sheets and seam strips, not at many single frames. Give one `logger` subagent each source file.
- **Long jobs** (transcription, voices, renders) run in the background; do other work meanwhile.
  They are cached: running a command again only redoes what changed.
- **Staying current.** When `./pal doctor` says a pin in `tools/versions.json` was checked more
  than 30 days ago, re-read that project's release notes before relying on what you remember,
  update the pin and what depends on it, run `./pal test`, set the new date.
- **It learns.** Log every note in the episode's `notes.md` with what was done. When the same
  kind of note appears in three episodes, propose a line for `channel.md` → "Standing
  preferences" and add it when the creator agrees.

## Layout

| Path | Holds |
| --- | --- |
| `channel.json`, `channel.md`, `ideas.md` | the channel: links, Drive folder, languages, review depth; tone, terms, preferences; the backlog |
| `brand/` | `frame.md` (colours, fonts, caption style), `kit/` (reusable graphics), `fonts/`, `reference/` |
| `formats/` | the kinds of video this channel makes; `_library/` holds all presets |
| `voices/<speaker>/` | cloned-voice reference clips and how each person speaks |
| `library/` | free music (`music/library.json`) and effects (`sfx/`) |
| `episodes/<yyyy-mm>-<slug>/` | one video: its text files, and `build/` for media |
| `tools/` | the `./pal` commands, `setup.sh`, pinned models and versions |
| `docs/` | how it works, formats, tools, Drive, recording tips, publishing |

## Setup

`sh tools/setup.sh` (the cloud environment runs it when a session starts), then `./pal doctor`.
