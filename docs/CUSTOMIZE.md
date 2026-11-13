# Make it yours

`/setup` writes all of this for you. Everything is a plain file you can edit, or ask Claude to
change ("make the accent colour orange", "add a format for my weekly Q&A").

| You want to change | Where | Then |
| --- | --- | --- |
| channel facts, Drive folder, languages, how often it stops for review, draft size | `channel.json` | nothing |
| tone, names and terms (spelling, pronunciation, translation), standing preferences | `channel.md` | nothing |
| colours, fonts, caption style | `brand/frame.md` | `./pal brand test`, look, `./pal brand check --approve` |
| a reusable graphic (lower third, title card, end card, …) | `brand/kit/<name>/` | the same |
| a kind of video: how tight the cut, how many graphics, music, what follows | `formats/<name>.md` | nothing |
| a new kind of video | copy the closest file in `formats/_library/` to `formats/` | nothing |
| your cloned voice | `/setup` → "here is my voice" | listen to the test |
| music | add a track: `./pal music add <its Wikimedia Commons page>`; or put tracks you own in Drive `brand/music/` | nothing |

## Languages

`channel.json → languages`:

- `spoken`: what you say in recordings (`fa`, `en`).
- `dub`: languages that get an extra audio track in your cloned voice (`["en"]`).
- `subtitles`: languages that get subtitle files.
- `graphics`: the language of on-screen text: `en`, `fa`, or `per-language` to render the
  picture once per language (two videos instead of one video with two audio tracks).

## Review depth

`channel.json → review`: `careful`, `standard` or `fast` (see `docs/HOW-IT-WORKS.md`). You can
also say it per video: "no stops on this one", "show me every step".

## Getting improvements

This copy came from the editpal template. To take its later improvements without touching your
channel's files: `./pal update` (it changes `tools/`, `.claude/`, `docs/`, `formats/_library/`
and the kit's code, and never `channel.*`, `brand/frame.md`, `formats/*.md`, `voices/`,
`episodes/`).

## Keep private things private

Your copy is private. Your voice clip, scripts and unreleased episodes live in it. Do not make
it public, and do not push it back to the public template.
