# What editpal is built on

The rule: everything here is free and may be used in monetised videos. Code and model weights are
under permissive licences; music and images are CC0 or public domain, or your own. No paid
service, no account, no sign-in. If you add something, it must meet the same rule and be listed.

editpal itself is MIT-licensed ([LICENSE](../LICENSE)).

## Software

| What | Used for | Licence |
| --- | --- | --- |
| [HyperFrames](https://github.com/heygen-com/hyperframes) (pinned in `package.json`) | rendering graphics from HTML | Apache-2.0. Its telemetry, update checks and account commands are switched off (`tools/hf.py`, `.claude/settings.json`). Reference files copied unchanged are in `.claude/skills/video/hyperframes/` with a `NOTICE` |
| [GSAP](https://gsap.com) | animation inside graphics | free for commercial use under GSAP's standard licence |
| ffmpeg (installed on the machine) | all cutting, mixing, encoding | LGPL/GPL build, used as a separate program |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | transcription | MIT |
| [gdown](https://github.com/wkentaro/gdown) | listing a shared Drive folder | MIT |
| OpenCV (headless), NumPy, SoundFile, Pillow, PyYAML, Requests | picture and sound processing | Apache-2.0 / BSD / HPND / MIT |
| [youtube-agent-skill](https://github.com/Jakeschincariol/youtube-agent-skill) (`tools/vendor/`) | title and chapter checks | MIT, copied unchanged with its licence |
| PyTorch (CPU), ONNX Runtime, spaCy, misaki | running the voice models | BSD / MIT / MIT / Apache-2.0 |
| num2words (pulled in by misaki) | spelling numbers for the stock voice | LGPL-2.1, used unmodified as a library. The one package here that is not MIT/Apache/BSD; it does not affect what you may do with the audio |

Exact versions: `package-lock.json` and `tools/requirements*.txt`.

## Models (downloaded by `tools/setup.sh`, pinned in `tools/models.json`)

| Model | Used for | Licence of the weights |
| --- | --- | --- |
| Whisper large-v3 and small (faster-whisper builds) | transcription | MIT |
| Chatterbox Nano | your cloned voice in English | MIT. Its audio carries an inaudible watermark marking it as machine-made |
| MOSS-TTS-Nano and its audio codec | cloned voice in Persian and other languages | Apache-2.0 |
| Kokoro 82M | a stock English voice | Apache-2.0 |
| YuNet | finding the face when reframing to vertical | MIT |

What was measured about each voice model, and which were rejected and why: [VOICES.md](VOICES.md).

## Media that ships with the template

| What | Where | Licence |
| --- | --- | --- |
| Fonts: Inter, Vazirmatn, JetBrains Mono | `brand/fonts/` | SIL Open Font License 1.1 (texts beside the files) |
| Sound effects | `library/sfx/` | made by `tools/sfx.py`; CC0 |
| Music | listed in `library/music/library.json`, downloaded on demand | each recording is CC0 or public domain, with its proof page recorded |

## Your videos

Every outside item a video uses gets a row in that video's `credits.md` (what, where, source
page, licence). If a platform claims a public-domain or CC0 recording by mistake, dispute the
claim with that page.

A cloned voice is a recording of a person. Clone only your own voice, or someone's who agreed.
Platforms may ask you to disclose synthetic or altered audio: see [PUBLISH.md](PUBLISH.md).
