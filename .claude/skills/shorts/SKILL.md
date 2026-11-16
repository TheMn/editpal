---
name: shorts
description: Cut YouTube Shorts and Instagram Reels (9:16) from a finished video or its A-cut, with a hook, burned-in captions and one file per language. Use for "/shorts <episode>", "make shorts", "reels", "clip this", "repurpose this video", "find the best moments".
argument-hint: <episode> [how many]
---

# Shorts and Reels

Input: an episode with a locked cut (`transcript.json`; the dub's voice stem if a language is
dubbed). Specs for each platform are in `formats/_library/short.md`.

1. **Find moments.** Read `./pal transcribe show <ep>`. A moment works alone when it:
   - opens on a complete thought (not "as I said", not a pronoun with no owner);
   - has a turn: a claim and then the proof, the catch or the surprise;
   - ends on a line, not a trail-off;
   - fits the length the format allows, and is not inside a `protect` range.
   Long video: give a `logger` subagent the transcript in halves and let each return candidates.
   Write the best 5–8 to `build/review/shorts.json` with a still each
   (`./pal sheet frames <ep>/build/cut/acut.mp4 --at … -o <ep>/build/review/shorts/`).
2. **Gate: which ones.** `./pal board shorts <ep>`, show it, wait (`S1 S3`, or `you choose`:
   take the best three).
3. **For each pick, write:**
   - the hook: on-screen text for the first 2 seconds, at most 6 words, **not** the spoken line;
   - the caption and hashtags for YouTube and for Instagram, per language;
   - the end: the last frame holds a beat, or loops back to the first.
4. **Build 9:16.**
   - Reframe: `./pal reframe <ep>/build/cut/acut.mp4 --from a --to b -o …` (`--mode track` follows
     the face; `--mode stack` for a screen recording with a face camera; content wider than the
     crop: stack it, never squeeze).
   - Captions and hook: a HyperFrames project per Short (`plan.json`-style beats in
     `mode: "project"`, the reframed clip as the base, the kit's `caption` piece fed with the
     words in that span, the hook as a `callout`). Read `../video/hyperframes/OVERRIDES.md`,
     then `types/vertical.md` and `captions.md`: nothing in the top 168 px or below 1330 px of
     1080×1920, captions low in that band, never over the face.
   - One file per language: the original voice, and the dub's span of the voice stem with
     captions in that language.
   - Sound: `./pal mix` with `--short` (louder target); music only if the format says so.
5. **Check** each: first frame is not black and shows the hook; captions readable at phone size
   and in sync; ends on the line; `./pal qc`.
6. **Deliver** with `./pal drive put <ep> …` and paste each Short's caption text.

Record in `episode.md`: which moments, their times, hooks, what was delivered.
