---
name: dub
description: Make audio tracks in one or several other languages for a video, in each speaker's own cloned voice, timed to the original (typically a Persian recording → English, Italian, …; any language to any other), with matching subtitles and translated title and description. Works on a locked cut inside a new video or on an already published video from the Drive folder. Use for "/dub <Drive folder or episode>", "English version", "English audio track", "dub this", and fixes like "line 34 should say …" or "too fast at 3:12".
argument-hint: <Drive folder name, or an episode> [languages, default: the channel's]
---

# Dub a video into another language

The picture is not touched. The result is one more audio track for the same video, in the
speaker's voice, plus subtitles in that language. Nothing here waits for approval: the creator
listens and sends fixes; only the lines they name are redone.

**Languages:** the ones asked for, else `channel.json → languages.dub`. Each language is its
own run of steps 2–10 with its own `translation.<lang>.json`; translate them as parallel
subagents and voice them one after another. English uses the best English engine; 22 other
languages use the multilingual engine; the rest are unmeasured (`docs/VOICES.md`): say so before
voicing a language that is not on the list, and voice 20 seconds first for the creator to hear.

**Speakers:** needs a voice profile for each person who speaks (`voices/<name>/`). None yet:
the `setup` skill's "Voice" step makes one from this very recording (or from a sample the
creator put in Drive `voices/<name>/`), then come back. More than one person in the video:
find who says what (separate microphone tracks, or ask the creator once for the pattern: "the
guest answers, I ask"), and set `"speaker": "<name>"` on each segment that is not the default
speaker's. A person with no profile and no sample: ask whether to make a profile (they will
appear again), use the stock voice for their lines, or leave their lines in the original.

1. **The video.**
   - Inside a new video: the cut is locked; `transcript.json` exists. Go to step 2.
   - An already published video: make the episode folder, `./pal drive get "<folder>" <ep>`
     (the audio alone is enough; the creator's own subtitle files make it faster and better),
     `./pal ingest <ep>`, `./pal transcribe <ep>` (background), then
     `./pal cut adopt <ep> <the video or audio file>` and `./pal cut remap <ep>` so the timeline
     is the published one.
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
