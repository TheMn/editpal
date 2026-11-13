# Stage: generate (a video with no footage)

For a script or an idea with nothing recorded, in Persian or English. This stage replaces ingest
and the rough cut; the storyboard, pilot and draft gates are the same.

Needs: `script.md` approved by the creator, with line ids (`L01 | …`). No script yet: the
`script` skill first.

1. **Sources.** Write `sources.json` with `"master": null`, the project size and frame rate
   (1920×1080 unless the format says vertical), and any images, screen captures or music the
   creator put in the Drive folder (`./pal drive get`, `./pal ingest`).
2. **The voice.** Which one is set in `channel.json → voices` and was approved in the voice
   test at setup:
   - a cloned or stock voice: `./pal voice script <ep>` (background). It voices each line,
     writes the voice stem and a `transcript.json` with the time of every word. Pronunciation
     problems (names, years, acronyms): add `say: …` to that line in `script.md` and run it
     again; only that line is re-voiced.
   - the creator narrates: they record the teleprompter text as audio, put it in the Drive
     folder, and it goes through `stages/ingest.md` and `stages/rough-cut.md` like any recording.
   Listen with the tools before going on: read `./pal transcribe show <ep>` against the script;
   a line the voice misread gets reworded or a `say:` override.
3. **Second language.** If the channel dubs or renders per language, translate now (the `dub`
   skill from "Translate"); the second voice is laid on the first one's timeline.
4. **Whole project or plates.** Up to about 3 minutes: one HyperFrames project
   (`plan.json → "mode": "project"`). Longer: each scene is a full-frame plate over the brand's
   ground colour (`"mode": "plates"`), so a note re-renders one scene, not the film.
5. **On-screen language** follows `channel.json → languages.graphics`. Persian text is
   right-to-left with the brand's Persian font; put all text in each beat's `text` per language,
   never inside the composition, so the same picture renders in Persian and English.

The voice is the clock: every visual lands on the word that names it. Only facts from the script
or the brief on screen; a number the script does not give is not shown.

Then `stages/plan.md`. Record in `episode.md`: the voice used, lines given a `say:` override,
the mode chosen.
