---
name: script
description: Turn an idea, notes or a pasted transcript into a brief and a script in the creator's voice (Persian or English), with line ids and a teleprompter text; also keeps the idea backlog. Use for "/script <idea>", "write a script about …", "here is my transcript", "I have an idea", "what should I make next", "teleprompter", "tighten this script", and before a generated video with no footage.
argument-hint: <the idea, or paste the text>
---

# Idea → brief → script

1. **Where it starts.**
   - An idea in a sentence: add it to `ideas.md` (one line, date). Asked "what next?": show the
     backlog with one line each on why now.
   - Notes or a finished text from the creator: keep their wording. Your job is structure and
     clean-up, and you list every change you made to their words.
   - A long recording they want as a short piece: write the tight script from its transcript
     (`./pal transcribe show <ep> --raw`) in their own phrases; they record it again.
2. **Brief (gate 1)** → `episodes/<yyyy-mm>-<slug>/brief.md`, shown in the chat:
   the one idea in one sentence; who it is for; the one thing they should remember; format
   (from `formats/`) and length; language(s); recorded by the creator or generated; what gets
   delivered. At most 5 questions, each with the default you will use. Wait for `ok`.
3. **Facts.** Anything stated as fact needs a source the creator gave or one you found and
   list in the script's "Sources". Uncertain → marked, or left out. Never invent a number, a
   quote or a date. Heavy research: a subagent per question, in parallel.
4. **Generated videos only: three storylines first.** Three different ways to tell it (each a
   different world, device and form: `../video/hyperframes/story.md`), a few lines each, your
   recommendation first. The creator picks one, or a mix. Build nothing before that.
5. **Write `script.md`** in the spoken language, in the creator's voice (`voices/<speaker>/VOICE.md`,
   `channel.md`):
   - a hook in the first two sentences: the question, the claim or the result, not a greeting;
   - one idea per section; each section opens with what the viewer gets from it;
   - written to be said: short sentences, about 150 words a minute in English (about 130 in
     Persian); read it against the target length and cut to fit;
   - **one line per row with an id**, and what is seen beside what is said:

     ```
     ## S1 The hook
     L01 | Every program you use started as a drawing.        | see: a flowchart being drawn
     L02 | And most beginners skip that step.                 | see: the creator, to camera
     ```

     Optional per line: `say: …` (how a voice should pronounce a name, year or acronym),
     `speaker: …`.
   - sponsor or call-to-action lines marked `[protect]` so the cut never trims them.
6. **Gate: the script.** Show it with its spoken length. Notes change only the lines named.
7. **Teleprompter** (when the creator records): `script.teleprompter.txt`: only the spoken
   words, one short line per breath, blank line between sections, read time at the top. Offer
   the recording tips in `docs/RECORDING-TIPS.md` (they make the cut cleaner).
8. **Next.** Recorded: they put the recording in the Drive folder and run `/video`. Generated:
   continue with the `video` skill (`stages/generate.md`).

Record in the episode's `episode.md`: the brief's answers, the storyline picked, changes made to
the creator's wording.
