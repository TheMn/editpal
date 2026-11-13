---
name: setup
description: Set up this copy of editpal for one channel, or change part of the setup later - the channel's facts, the kinds of video it makes, languages, brand and caption style, the cloned voice, music taste, the Drive folder, review depth and the cloud environment. Use for "/setup", "set up my channel", "change my brand / colours / font", "here is my voice", "the voice sounds wrong", "add a format", "connect my Drive", "set up the environment".
---

# Set up the channel

Three short rounds of questions, then you write the channel's files and show two tests. Ask with
choices where you can; every question has a default; never more than four questions in a round.
Changing one thing later: do only that step.

## 0. The machine

`./pal doctor`. In a cloud session whose environment is missing hosts or has no setup script:
propose the change once (the hosts the tools download from: Hugging Face and its download hosts,
PyTorch's CPU index, Google Drive's two hosts, Wikimedia Commons, Google's script host for
uploads; setup script: `sh tools/setup.sh`). The creator approves it with one click; nothing is
installed on their computer.

## 1. Round one: the channel

Name and links (YouTube, Instagram); what it is about and for whom; how it sounds (three words,
or "like this video": they paste a link or a transcript); **languages**: what is spoken in
recordings, whether videos also get an extra audio track in another language in their cloned
voice, which subtitle languages, and whether on-screen text is English, Persian, or rendered
once per language.

## 2. Round two: what they make and how

Which kinds of video (several allowed), from `formats/_library/`:
`talking-head` (to camera, maybe with a screen or B-roll) · `screencast` (screen recording, with
or without a face) · `faceless` (script → voice → graphics, nothing recorded) · `podcast`
(two or more people or cameras) · `montage` (B-roll and music led) · `short` (made vertical).
For each chosen: typical length; how they record (camera, phone, separate microphone, screen
recorder); what always follows (subtitles, Shorts, an extra language). Copy each chosen preset to
`formats/<name>.md` and adjust its defaults to the answers.

## 3. Round three: look, sound, working style

- **Brand:** colours, fonts, logo. They have them → use them. They do not → derive a look from
  3–5 frames or thumbnails they put in the Drive folder `brand/`, or offer three directions in
  words and let them pick. Write `brand/frame.md` (every value the kit reads). Fonts must be
  free to embed (OFL); a Persian font is included when Persian appears on screen.
- **Captions:** clean line, or bold word-by-word (for vertical pieces); burned in or files only.
- **Music:** moods they like, or none; only free recordings from `library/music/` or tracks
  they own (they drop those in Drive `brand/music/` with a note saying where the licence is).
- **Review depth:** `careful` / `standard` / `fast` (explain in one line each).
- **Drive:** the shared folder's link ("anyone with the link can view"), one subfolder per
  video. Writing results back needs the upload link: walk them through `docs/DRIVE.md` (a
  one-time paste in the browser); until it exists, results are sent in the chat.

## 4. Write the files

`channel.json` (`docs/FORMATS.md`), `channel.md` (what it is about, audience, tone, names and
terms with spelling and translation, standing preferences: empty to start), `formats/`,
`brand/frame.md`, `voices/<speaker>/VOICE.md` (how they talk: sentence length, favourite words,
what they never say; from a transcript if they gave one). Commit.

## 5. Brand test (they approve)

`./pal brand test`: ten seconds showing the intro mark, a lower third, a callout, captions and
the end card in the new look (in Persian too if Persian appears on screen). Upload it or send it,
with five stills. Notes change `brand/frame.md`; run it again. On "looks right":
`./pal brand check --approve` (these frames now guard the look).

## 6. Voice (only if a voice is cloned or generated)

1. A recording of the speaker: any raw recording in the Drive folder works, in any language.
   `./pal voice prepare <speaker> <file>` picks the best 6–10 seconds by itself.
2. Optional, better for an English track from a Persian speaker: ask once for 15 seconds of
   them speaking English (phone is fine), `./pal voice prepare <speaker> <file> --lang en`.
3. `./pal voice test <speaker>`: the same lines from each clip and engine. Send the files;
   they pick by ear. Say plainly what to listen for: likeness, accent, steadiness.
4. Record the choice in `voices/<speaker>/voice.json`. The reference clip is committed (this
   copy of the repository is private); never commit it to a public repository.
A stock voice instead (no clone): play its test lines and record that choice.

## 7. Finish

`./pal doctor` passes. Show the creator the commands table from `README.md` and the first thing
to try: one real video through `/video`, with the pilot gate on.
