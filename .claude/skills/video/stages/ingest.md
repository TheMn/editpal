# Stage: ingest (get the footage in and understand it)

Nothing here needs the creator except the brief at the end.

1. **Download.** `./pal drive get "<Drive folder>" <ep>`. Exit code 3 = it would not fit on
   disk: show the sizes it printed and ask which files to leave out (`--only`). No Drive link in
   `channel.json`, or nothing found: say which folder name you looked for and stop.
2. **Ingest.** `./pal ingest <ep>`. It guesses each file's role and conforms phone footage
   (variable frame rate, HDR, rotation) so everything downstream is exact. Read its table. A
   doubtful guess (two cameras, a screen recording marked as B-roll): fix it with `--roles`; ask
   the creator only when you cannot tell from the contact sheets.
3. **Sync.** More than one source with sound (camera + separate microphone, two cameras):
   `./pal sync <ep>`. A drift warning means the two devices ran at slightly different speeds:
   tell the creator once, continue (the tools compensate up to a point).
4. **Transcribe** in the background: `./pal transcribe <ep>` (about real time). Names and
   terms from `channel.md` go in with `--prompt`.
5. **Log the footage** while it transcribes. One `logger` subagent per video source, all at once:
   each gets the source id and its contact sheet (`build/sheets/<id>.jpg`) and, when the
   transcript is ready, the compact transcript. They write what the footage *shows* into
   `log.md`. One short source: do it yourself.
6. **Brief (gate 1).** Write `brief.md` from what the creator said, any notes or script in the
   Drive folder, the log and the format: the one idea, who it is for, target length, languages,
   what will be delivered (video, extra audio tracks, subtitles, Shorts, package), and anything
   you need to know that you cannot find, as at most 5 questions, each with the default you will
   use. Show it in the chat.
   - A recording much longer than the wanted result (10 minutes for a 60 s piece): say plainly
     that picking a short film out of a long ramble rarely works, and offer the better route:
     the `script` skill writes a tight script from what they said, they record it again.

Record in `episode.md`: sources and roles, project size and frame rate, sync result, the brief's
answers. Then `stages/rough-cut.md`.
