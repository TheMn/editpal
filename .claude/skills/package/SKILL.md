---
name: package
description: Write and render everything around a video for YouTube and Instagram, in each of the channel's languages - titles, thumbnail options, description, chapters, tags, pinned comment, Instagram caption and cover. Use for "/package <episode>", "title ideas", "thumbnail", "description", "chapters", "tags", "metadata", "package this video".
argument-hint: <episode>
---

# Package a video

Input: the final timeline (`transcript.json`, `plan.json → sections`, each
`translation.<lang>.json`). Output: `package.md`, every block ready to paste, per language.
Only what is in the video: never promise, in a title or thumbnail, something it does not deliver.

Two languages: write each as its own parallel Sonnet subagent (this file, the edited text,
`channel.md`, `voices/<speaker>/VOICE.md`), then pick, check and merge yourself.

1. **Title and thumbnail are one pairing.** Write 10 titles, keep 3.
   - at most 60 characters (40 keeps the subject visible on phones); the subject first;
   - a number, a name or a concrete promise instead of adjectives; at most 2 words in capitals;
   - thumbnail text: at most 3 words, **different words** from the title, the same promise.
   - check English ones: `python3 tools/vendor/youtube-agent-skill/title.py --title "…" --thumb "…"`.
2. **Thumbnails.** `./pal thumb <ep>` lists sharp, expressive frames. Make three options that
   differ in idea, not in colour: `./pal thumb <ep> --make <frame> --text "…" -o T1.jpg` (and
   T2, T3). Look at each at feed size: can the words be read, is the face or the subject clear?
   `./pal board thumbs <ep>`.
3. **Description.** First two lines: what the viewer gets, in the words they would search.
   Then links and resources; chapters; a short summary; credits that licences require (from
   `credits.md`). Write the three searches this video should be found by and check the title
   and first two lines contain their words.
4. **Chapters** from `plan.json → sections` on the final timeline: first at `00:00`, at least
   three, each at least 10 s, 3–5 words that promise what the section gives. Check:
   `python3 tools/vendor/youtube-agent-skill/chapters.py subs/en.srt`.
5. **Tags** (at most 15): spellings, tool and concept names, abbreviations, every language.
   **Pinned comment:** one question the video makes the viewer want to answer.
6. **Instagram:** caption (the first 125 characters carry it; up to 5 hashtags), cover frame
   that still reads when cropped to the centre square.
7. **Disclosures** as a checklist the creator ticks: paid promotion; altered or synthetic
   content (a cloned voice speaking a translation may count: they decide, with the platform's
   current wording); music credits.
8. Extra language on the same video: the translated title and description go under YouTube
   Studio → Languages (`docs/PUBLISH.md`).

**Gate.** Show the pairings and thumbnails (`thumbs` page) and the paste-ready blocks, then one
question: **ship it, or change it?**

Record in `episode.md`: the pairing chosen, what was delivered.
