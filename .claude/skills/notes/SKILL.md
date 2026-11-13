---
name: notes
description: Apply the creator's notes to something already made, at any gate or after delivery, changing only what the note names. Use when the creator replies to a review page or a draft with things like "keep C12", "C7 looser", "cut 3:41-3:55", "B07 pip", "B09 drop", "M2", "no sfx", "3:12 too fast", "line 34 should say …", "the music is too loud", "make it shorter", or "change this in the published video".
---

# Apply notes

A note changes what it names and nothing else. Then you show the changed piece, not everything.

1. **Log first.** Append each note to the episode's `notes.md` with the date and the gate.
2. **Translate the note into the file it belongs to:**

   | The note is about | Change | Then |
   | --- | --- | --- |
   | a cut (`C…`, a time range, "restore …") | operations for `./pal cut apply <ep> ops.json --by creator` | `cut render --preview`, `cut verify`, `cut remap` |
   | a beat (`B…`: layout, drop, move, text) | `plan.json`, then `./pal plates time <ep>` | `plates stills` for those beats; after the storyboard gate also `plates render --only …` |
   | music, effects, loudness | `plan.json → music` / beats' `sfx` | `./pal mix <ep>` |
   | a dubbed line ("line 34 should say …", "too fast at 3:12") | that segment's `text` in `translation.<lang>.json` | `./pal dub check`, `dub voice`, `dub verify`, `mix` |
   | a subtitle | `translation.<lang>.json` (`read`) or the transcript's word | `./pal subs make`, `subs lint` |
   | a time on the draft ("3:12 too fast") | find the beat or cut at that time (`plan.json`, `./pal cut table`), then as above | — |
   | the look ("I don't like this font") | `brand/frame.md` (it is a channel change: say so) | `./pal brand test`, then re-render plates |

   A note you cannot place ("make it punchier"): ask one question that offers two concrete
   readings, each with what it would change.
3. **A change before picture lock is cheap; after it, say the cost in one line** before doing it
   (a cut moved after lock re-times beats, the dub and the subtitles; the tools do it, it takes
   a render).
4. **Rebuild only what the change touches**, then re-show only that: the changed cards, the
   changed seconds (`./pal composite <ep> --draft` re-renders only the affected part), with the
   list of what you did against each note.
5. **Record** in `notes.md` what was done for each note. If this kind of note has now come up in
   three episodes, propose one line for `channel.md` → "Standing preferences".

## After delivery

A note on a delivered video makes version 2: same steps, final render again, deliver as
`<slug>-v2`, tag it, and tell the creator what to replace on the platform (a re-upload loses the
video's views and comments; subtitles, audio tracks, thumbnails, titles and descriptions can be
replaced in place).
