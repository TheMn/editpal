# How it works

## The idea: show before build

The usual trouble with AI editing is that you find out what it did only when you watch the
finished video. By then the time is spent. editpal works like an editor you trust: every step
shows you its cheap version first, and builds the expensive one only after you say yes.

| # | Gate | You see | Costs | You answer |
| --- | --- | --- | --- | --- |
| 1 | **Brief** | one paragraph: the idea, format, length, languages, what you will get | seconds | `ok` |
| 2 | **Paper edit** | your transcript with the removed parts struck through and labelled; the cut to listen to | minutes | `keep C12` · `cut C45` · `C7 looser` · `lock` |
| 3 | **Storyboard** | the layers of the edit; a still for every graphic on your real frame; music to choose | minutes | `B07 pip` · `B09 drop` · `M2` · `go` |
| 4 | **Pilot** | the first 30–60 seconds, finished | ~10 min | notes · `go` |
| 5 | **Draft** | the whole video at 1080p with a running clock on it | render time | `3:12 too fast` · `final` |

Each review page opens from the chat, on a phone or a computer. Every item has a short id;
tap what you want changed and press "Copy my notes", or just type.

How often it stops is your choice (`/setup` → review depth): `careful` (every gate), `standard`
(paper edit, storyboard, draft), `fast` (storyboard only). It always stops at the storyboard.

## What happens between the gates

**From a recording**

1. *Ingest.* Your files come from Drive. Phone footage is made regular (frame rate, HDR,
   rotation), a separate microphone is lined up with the camera by its sound, everything is
   transcribed.
2. *Rough cut.* A tool removes long pauses, "um"s, false starts and repeated takes, cutting in
   the quiet between words and matching your own rhythm. Then Claude reads the whole thing like
   an editor and finds what a tool cannot. Removing a mistake is done; removing something you
   *said* is only ever a suggestion. → gate 2. When you say `lock`, the cut is final ("picture lock").
3. *Plan.* Where a number, a name, a list or a diagram would help, a "beat" is planned and
   posed on your real frame. → gate 3, then the pilot.
4. *Finish.* Graphics are rendered as short clips ("motion plates") and laid over the cut;
   music and effects are mixed under your voice; the draft is checked automatically for flash
   frames, black gaps and loudness. → gate 5. `final` makes the full-quality file.

**From an idea, with nothing recorded**

`/script` turns the idea into a brief, three ways to tell it, and a script. A voice (your cloned
voice, a stock voice, or your own narration recorded as audio) reads it, and every picture is
built to land on the word that names it. The storyboard, pilot and draft gates are the same.
Persian and English are both supported, on screen and in the voice.

**Two languages**

After the cut is locked, the transcript is translated once. That one translation feeds both the
second voice track (in your cloned voice, timed to the original) and the subtitles, so they
agree. Voice and music are kept as separate files, so each language's voice goes over the same
music.

## Changing your mind

A note changes only what it names. `B07 pip` re-poses one card. `3:12 too fast` finds what is at
3:12, fixes it, and re-renders that minute, not the film. A new logo or colour is one edit to
`brand/frame.md` and a re-render. Every note is kept in the video's `notes.md`; when the same
kind of note keeps coming, it becomes a standing preference so you stop having to say it.

## What it cannot do

It does not watch or listen like a person. It reads transcripts, looks at sampled frames and
measures sound. It will tell you what it measured and what nobody checked. Pacing, humour and
whether a take *feels* right are yours to judge, which is what the gates are for.

It works on a small cloud machine with no graphics card: transcription takes about as long as
the recording, a cloned voice about three times the length of the speech, graphics about five
times their length. Long jobs run in the background.
