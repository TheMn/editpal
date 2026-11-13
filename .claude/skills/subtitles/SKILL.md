---
name: subtitles
description: Make subtitles for a finished video, in the spoken language and in translation (Persian and English), as .srt and .vtt files and optionally burned into the picture. Works on an episode or on any video file in the Drive folder. Use for "/subtitles <Drive folder or episode>", "add subtitles", "captions for this video", "English subtitles", "Persian subtitles", "burn the subtitles in", "fix the subtitle at 2:10".
argument-hint: <Drive folder name, or an episode> [languages]
---

# Subtitles

Languages come from `channel.json → languages.subtitles` unless the creator names others.

1. **The video.**
   - An episode made here: `transcript.json` and any `translation.<lang>.json` already exist.
   - Any finished video: make the episode folder, `./pal drive get "<folder>" <ep>`,
     `./pal ingest <ep>`, `./pal transcribe <ep>`, `./pal cut adopt <ep> <file>` (the timeline
     is the video as it is).
2. **Check the words** before timing anything. Read `./pal transcribe show <ep>` once: names,
   product and technical terms, numbers. Use the spellings in `channel.md`; add the ones you
   had to fix. A span the transcriber flagged as suspect: listen through the surrounding lines'
   sense, never guess a sentence into existence; mark what you could not make out.
3. **Translation** for each other language: `./pal dub init <ep> --to <lang>` makes the file;
   translate as the `dub` skill says (step "Translate"). If the video is also dubbed, this is
   the same file, so the voice and the subtitles say the same thing. Subtitles are read, not
   spoken: where the dub needed a shorter line, the fuller sentence goes in `read`.
4. **Make and check.** `./pal subs make <ep>`, then `./pal subs lint` on every file. It checks
   line length, two lines at most, reading speed, time on screen, overlaps. Fix what it lists by
   rewording or splitting the sentence, not by shrinking time.
5. **Burned in** (only when asked, or for vertical pieces):
   `./pal subs burn <video> subs/<lang>.srt -o build/out/<slug>.<lang>.subbed.mp4`, then look at
   three frames (`./pal sheet frames`): readable at phone size, not over a face or on-screen
   text, Persian joined and right-to-left.
6. **Deliver.** `./pal drive put <ep> subs/*.srt subs/*.vtt` (and the burned copy). Point to
   `docs/PUBLISH.md` → "Add subtitles".

A fix ("the subtitle at 2:10 is wrong"): change the word in the transcript or the line in the
translation, then steps 4–6 for that language.

Record in `episode.md`: languages made, terms corrected, anything unclear in the audio.
