# The pilot: proving it on real footage

The studio is built and its tools pass their checks on a generated clip. None of it has edited a
real video yet. This page is the plan for the first real ones, and the list of things to measure
and tune while doing them.

## Before you start

1. Merge the build into `main`; on GitHub tick **Settings → Template repository**.
2. **Use this template** → your own private copy for one channel.
3. Open the copy in Claude Code on the web, with the `editpal` environment.
4. `/setup` (three rounds of questions, the brand test, the voice test).
5. The Drive upload link, once ([DRIVE.md](DRIVE.md)).

## Four runs, in this order

| # | Run | With | It proves |
| --- | --- | --- | --- |
| 1 | `/video <folder>` | one real raw recording, 5–15 minutes, mistakes left in | the A-cut on natural speech; the paper-edit page; the storyboard; the pilot minute; the draft |
| 2 | `/dub <folder>` | the same recording, or a published video with its subtitles | Persian → English in the cloned voice: likeness, accent, timing; the mix |
| 3 | `/script <idea>` then `/video` | a Persian idea, nothing recorded | Persian voice quality; right-to-left graphics; a generated piece end to end |
| 4 | `/subtitles <folder>` and `/shorts <episode>` | the video from run 1 | subtitle rules in both languages; face-following reframe; captions on vertical |

Run each with review depth `careful`, so every gate shows.

## What to measure and tune

**The cut (the part most likely to need work)**
- Of the cuts proposed, how many did you reverse (`keep …`)? Aim: under 1 in 10.
- Seams you can hear on the seam reel. Aim: under 1 in 20.
- Retakes it missed; pauses it made too tight or left too long.
- Tune: the pause targets and padding in `tools/cut.py`, the filler lists per language, the cue word.

**Voice**
- English from a Persian clip vs from an English clip: which did you pick, and why.
- Persian synthetic voice: usable for a whole video, or narration only by recording?
- Lines that had to be shortened to fit; lines misread.

**Graphics and picture**
- Render times on the cloud machine (per plate, per minute of draft, the final).
- Storyboard: did the stills match what was rendered?
- Persian on screen: joined letters, order, digits, mixed lines.

**Footage the tools have not met**
- A phone recording (HEVC, variable frame rate, HDR, portrait).
- A long one: a 10 GB source, and a session that restarts halfway (`./pal restore`).
- A separate microphone that drifts.

**Delivery**
- The Drive upload link end to end with a file over 1 GB.
- How large a file the chat can deliver without it.

**Music**
- Does the library have a track you would actually use? Add non-classical CC0 recordings until
  each mood has at least three.

## After the pilot

Every fix goes back into the template, with the numbers above recorded in `docs/RENDERING.md`
and `docs/VOICES.md`. Then the status line in `README.md` changes.
