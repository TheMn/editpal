# Stage: finish (build, draft, final)

The storyboard is approved. Build exactly that.

1. **Plates.** `./pal plates render <ep>` in the background (one after another; unchanged
   plates are skipped).
2. **Meanwhile:** the dub for each language in `channel.json → languages.dub` (the `dub`
   skill), and the package text (`package` skill, text only).
3. **Sound.** `./pal mix <ep>`: the bed (music + effects) once, then one mix per language over
   the same bed, at the channel's loudness.
4. **Draft.** `./pal composite <ep> --draft` (1080p, timecode and beat ids burned in), then
   `./pal qc build/out/draft.mp4 --ep <ep>`. Fix what it finds before anyone watches: a flash
   frame, a black gap, clipping, loudness off target. Make a contact sheet of the draft
   (`./pal sheet contact <ep>/build/out/draft.mp4 -o <ep>/build/review/draft-sheet.jpg --every 10`) and give
   it with the plan to a `fresh-eyes` subagent; fix its real findings.
5. **Gate 5: the draft.** `./pal drive put <ep> build/out/draft.mp4`,
   `./pal board draft <ep>`, show the link and the page. Say what the checks measured and what
   nobody checked (you measured the sound, you did not hear it). Stop.
   - Notes: the `notes` skill. Only the named piece is redone and only its part of the draft
     re-renders.
6. **Final** on `final`: `./pal composite <ep> --final` (full quality at the source size, clean),
   `./pal qc build/out/<slug>.mp4 --ep <ep>`, and it must pass.
7. Back to the `video` skill, "After the final".

Record in `episode.md`: check results, notes and what was done about each, render times (they
make the next estimate honest).
