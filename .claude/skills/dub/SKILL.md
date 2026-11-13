---
name: dub
description: Make another language's audio track for a video in the speaker's own cloned voice, timed to the original (typically Persian recording → English track), with matching subtitles and translated title and description. Works on a locked cut inside a new video or on an already published video from the Drive folder. Use for "/dub <Drive folder or episode>", "English version", "English audio track", "dub this", and fixes like "line 34 should say …" or "too fast at 3:12".
argument-hint: <Drive folder name, or an episode> [language, default en]
---

# Dub a video into another language

The picture is not touched. The result is one more audio track for the same video, in the
speaker's voice, plus subtitles in that language. Nothing here waits for approval: the creator
listens and sends fixes; only the lines they name are redone.

Needs a cloned voice for the speaker (`voices/<speaker>/`). None yet: the `setup` skill's
"Voice" step makes one from this very recording, then come back.

1. **The video.**
   - Inside a new video: the cut is locked; `transcript.json` exists. Go to step 2.
   - An already published video: make the episode folder, `./pal drive get "<folder>" <ep>`
     (the audio alone is enough; the creator's own subtitle files make it faster and better),
     `./pal ingest <ep>`, `./pal transcribe <ep>` (background), then
     `./pal cut adopt <ep> <the video or audio file>` so the timeline is the published one.
2. **The translation file.** `./pal dub init <ep> --to <lang>`. If the creator's own subtitles
   in the target language are in the folder, they become the script (their wording, their
   timing) and there is nothing to translate.
3. **Translate** the lines that are empty. Read the whole original first.
   - Spoken, plain language in the speaker's voice (`voices/<speaker>/VOICE.md`). Same meaning,
     nothing added, nothing dropped. Fix transcription errors from context and say so in `note`.
   - Code, identifiers, numbers and names stay as they are; standard terms go in `glossary`
     and in `channel.md` so every episode uses the same word.
   - Spell out what a voice would misread (symbols, slashes, units, years).
   - A filler-only line gets `"skip": true`.
   - More than ~120 lines: chunks of ~60 to parallel Sonnet subagents with one shared brief
     (these rules, the glossary, the errors you noticed), then one consistency pass yourself.
4. **Fit.** `./pal dub check <ep> --to <lang>`. A line too long for its time gets shorter
   wording with the same meaning; keep the fuller sentence in `read` (the subtitles use it).
5. **Voice** in the background: `./pal dub voice <ep> --to <lang>`. Shorten whatever is listed in
   `build/dub/report.txt` and run it again (finished lines are cached).
6. **Read it back.** `./pal dub verify <ep> --to <lang>`. Reword the lines that really were
   misread; voice again.
7. **Mix.** `./pal mix <ep> --lang <lang>`: the new voice over the same bed as the original.
   An already published video with music baked into its sound: there is no separate bed. Ask
   once: no music under the dub (default), a library track, or the bed file if the creator has it.
8. **Subtitles** in that language: `./pal subs make <ep> --lang <lang>`, `./pal subs lint`.
9. **Title and description** in that language (`package` skill, that language only).
10. **Deliver:** `./pal drive put <ep>` the `.m4a` and the `.srt`; paste the title and
    description; point to `docs/PUBLISH.md` → "Add an audio track".

## Fixes later

"Line N should say …" / "too fast at mm:ss": change those lines' `text` (find a line by time
with `./pal transcribe show <ep> --from … --to …`), then steps 4–7 for those lines only.

Record in `episode.md`: where the script came from (subtitles or translation), lines shortened,
lines still flagged, drift, loudness, what was delivered.
