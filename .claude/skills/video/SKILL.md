---
name: video
description: Make a video end to end, from a recording in the Drive folder or from a script with no footage, through the review gates (brief, paper edit, storyboard, pilot, draft) to the final file, subtitles and delivery. Use for "/video <Drive folder or episode>", "new video", "edit the recording in …", "cut the pauses and retakes", "make the video from this script", "continue <episode>".
argument-hint: <Drive folder name, or an episode>
---

# Make a video

You are the editor. The creator sees and accepts the cheap version of every step before the
expensive one is made (`CLAUDE.md`, "Show before build"). Read `GLOSSARY.md` once if a word here
is unfamiliar, and use those words with the creator.

## 1. Find or start the episode

- An existing episode (`episodes/*<name>*`): read its `episode.md` and continue from the stage
  and gate written there. Do not redo finished stages.
- New: `episodes/<yyyy-mm>-<slug>/` (this month, short English slug) copied from
  `episodes/_template/`. Fill the top of `episode.md`.
- Pick the format: the one in `formats/` that fits (ask only if two fit equally). Its file sets
  this video's defaults: how tight the cut is, how many graphics, layouts, captions, music, which
  outputs follow. A choice in the brief overrides the format; a line in `channel.md` → "Standing
  preferences" overrides both.

## 2. Which path

| The episode has | Stages, in order (read each file when you reach it) |
| --- | --- |
| a recording (camera, screen, or narration audio) | `stages/ingest.md` → `stages/rough-cut.md` → `stages/plan.md` → `stages/finish.md` |
| no footage: a script or an idea only | skill `script` (until the script is approved) → `stages/generate.md` → `stages/plan.md` → `stages/finish.md` |
| "just cut the pauses" / "only the A-cut" | `stages/ingest.md` → `stages/rough-cut.md`, deliver the A-cut, stop |

Graphics are written with the reference files in `hyperframes/`. **Read
`hyperframes/OVERRIDES.md` first**; it wins over anything in the other files there.

## 3. Do two things at once

Long jobs run in the background and are cached. While one runs, do the next thing that does not
depend on it:

| While this runs | Do this |
| --- | --- |
| download, transcription | the brief (gate 1); look at the contact sheets (`logger` subagents, one per source) |
| A-cut full-quality render | the plan: sections, beats, music options |
| plate renders | the translation and dub (`dub` skill, from step "Translate"); subtitles |
| draft render | the package text (`package` skill, text only) |

Several custom plates: one `plate-maker` subagent per plate, all at once (they only write files);
`./pal plates render` then renders them one after another.

## 4. After the final

1. `./pal subs make <ep>` and `./pal subs lint` on each file.
2. Deliver with `./pal drive put <ep> …`: the final video, each extra language's `.m4a`, every
   `.srt`/`.vtt`. Paste the links.
3. `credits.md` has a row for every outside item; `episode.md` says what was delivered.
4. Commit the episode's text files. Tag the delivery `<slug>-v1`.
5. Run `package`. Then `shorts` if the format says Shorts follow, else offer it in one line.

## Done when

The creator said `final`, the files are in their Drive folder (or sent in the chat), checks are
clean or their exceptions are listed, and `episode.md` would let a new session answer "what was
made, what was decided, what is left" without asking.
