# Stage: plan (storyboard, then pilot)

The cut is locked (or the voice is made). Now decide everything that goes on top of it, and show
it as stills **before animating anything**.

1. **Read** the edited text (`./pal transcribe show <ep>`), `brief.md`, `log.md`, the format,
   `brand/README.md` (the kit: what is cheap and consistent), and `channel.md` → "Standing
   preferences".
2. **Sections** → `plan.json → sections`: where the topic changes. They become chapter cards
   (if the format uses them) and the YouTube chapters.
3. **Beats.** A beat earns its place when the picture helps the words: a number, a name (the
   first time a person or product is named), a list, a process, a comparison, a term being
   defined, a place, a quote, the start of a section, the moment on a screen recording where
   something happens. Not decoration.
   - How many: the format's density. Nothing over a sponsor read except the sponsor's own material.
   - **Keep the speaker.** Prefer `lower-third`, `over` and `pip`; use `full` only when the
     graphic needs the whole frame, and not for long. Creators dislike disappearing behind
     full-screen graphics.
   - **Prefer the kit** (`"type": "kit"`): it renders fast and always matches the brand. A
     `custom` plate is for what the kit cannot say; mark why.
   - Anchor each beat to the word that names it (`anchor`, `until`); write its `text` for every
     language the picture is rendered in.
   - B-roll and screen moments come from the sources the log describes. A picture you would want
     but do not have goes in as a beat with `"status": "outline"` and a `needs` note: the
     storyboard lists these as "shots to collect".
   - Things on a screen recording that look private (keys, emails, addresses) → `redact`.
4. **Sound.** Effects only on entrances that deserve one, soft; none if the channel prefers.
   Music: three options that fit the format's moods (`./pal music list`; make previews with
   `./pal music preview <id> build/review/music/M1.mp3`), or none if that is the channel's
   default. Calm classical under a modern talking video usually sounds wrong: offer it only if
   the channel asked for it.
5. **Captions.** Long videos: subtitle files, no burn-in, unless the format says otherwise.
   Vertical pieces: burned in.
6. **Write `plan.json`**, `./pal plates time <ep>`, then the custom plates: one `plate-maker`
   subagent per plate, all at once; each writes its composition and poses it, none renders.
7. **Stills.** `./pal plates stills <ep>` and look at them: nothing over the face, text readable
   at phone size, nothing outside the safe area, Persian shaped and ordered correctly. A
   `fresh-eyes` subagent gets the stills and the plan only and returns ranked problems. Fix.
8. **Dub sample.** If a language is dubbed: voice the first 20 s into
   `build/review/voice-sample.<lang>.mp3` so the creator hears it at this gate.
9. **Gate 3: the storyboard.** `./pal board story <ep>`, show it, give the total render
   estimate, stop. Notes change `plan.json`; re-pose and re-show only the cards that changed.
10. **Gate 4: the pilot** (when the review setting or a first use of this format calls for it).
    Render only what the first 45 s need: `./pal plates render <ep> --only <ids>`,
    `./pal mix <ep>`, `./pal composite <ep> --range 0-45`, upload `build/out/pilot.mp4`, stop.
    This is the editor's trial: if the look, pace or sound is wrong, it is fixed here, once,
    before the whole video is built that way.

Record in `episode.md`: beats by kind, the music chosen, caption decision, shots still to
collect, the creator's notes at each gate. Commit `plan.json`. Then `stages/finish.md`.
