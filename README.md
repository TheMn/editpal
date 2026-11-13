# editpal

A video studio that lives in a repository and is run by [Claude Code](https://claude.com/claude-code).
You bring an idea, a script or a raw recording; it does the editor's job: the cut, graphics,
music, an English track in your own voice, subtitles, Shorts, titles and thumbnails. In Persian
and English, for YouTube first and Instagram second.

**You see the plan before anything is built.** The cut arrives as a transcript with the removed
parts struck through. The graphics arrive as a storyboard on your real frames. You answer in a
few words (`keep C12`, `B07 pip`, `go`), and only then is the video made.

Everything it uses is free and safe for a monetised channel, and it runs in Claude's cloud:
nothing to install on your computer.

> Status: the studio is built and its tools pass their own checks on a generated test clip. It
> has **not yet been proven on real footage**; that is the pilot in [docs/PILOT.md](docs/PILOT.md).

## Start

1. **Use this template** (the green button on GitHub) → make your own **private** copy.
2. Open your copy in Claude Code on the web.
3. Type `/setup` and answer three short rounds of questions.

## Use

| You want | You type | You get |
| --- | --- | --- |
| a video from a recording | `/video 2026-12 Recursion` (your Drive folder's name) | cut → storyboard → draft → final, with subtitles |
| a video from an idea, nothing recorded | `/script why straits matter` then `/video straits` | script → storyboard → the whole video generated |
| a script to record yourself | `/script …` and say "I'll record it" | script and teleprompter text |
| an English track in your voice | `/dub <Drive folder>` | the audio track, subtitles, translated title and description |
| subtitles for a finished video | `/subtitles <Drive folder>` | `.srt` and `.vtt` in both languages |
| Shorts and Reels | `/shorts recursion` | vertical clips with captions |
| titles, thumbnail, description | `/package recursion` | paste-ready text and three thumbnails |
| to change something | just say it: `B07 pip`, `3:12 too fast`, `line 34 should say …` | only that part redone |

Plain sentences work too ("edit the recording in the Recursion folder").

**Your media** goes in one shared Google Drive folder, one subfolder per video, files named
however you like. Results come back to an `editpal-out` folder in the same place
([docs/DRIVE.md](docs/DRIVE.md)).

## Read more

- [GLOSSARY.md](GLOSSARY.md): the editor's words (A-cut, B-roll, motion plate, …), one line each
- [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md): the five review gates and what happens between them
- [docs/CUSTOMIZE.md](docs/CUSTOMIZE.md): your brand, formats, voice and preferences
- [docs/RECORDING-TIPS.md](docs/RECORDING-TIPS.md): six habits that make the cut cleaner
- [docs/PUBLISH.md](docs/PUBLISH.md): uploading, extra audio tracks, subtitles
- [docs/LICENSES.md](docs/LICENSES.md): what it is built on, and why it is safe to monetise
- [docs/ROADMAP.md](docs/ROADMAP.md): what is not built yet
- For Claude and the curious: [CLAUDE.md](CLAUDE.md), [docs/TOOLS.md](docs/TOOLS.md), [docs/FORMATS.md](docs/FORMATS.md)

Graphics are rendered with [HyperFrames](https://github.com/heygen-com/hyperframes) (Apache-2.0).
editpal itself is MIT-licensed.
