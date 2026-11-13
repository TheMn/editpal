# Voice engines: what we measured

Measured on a 4-core cloud machine with no GPU (2 threads per engine, other jobs running), reference clips
synthetic (a Kokoro line; a Persian line made by MOSS from it). Word errors = faster-whisper large-v3
reading the output back against the text, 4 test lines per language (English: a year, a number, a technical
term; Persian: 4 sentences). "x" = seconds of compute per second of speech. Accent and likeness to a real
person can only be judged by ear: `./pal voice test <speaker>` writes mp3s to listen to.

| Engine | Weights licence (model card) | Speaks | Speed | Read-back errors |
| --- | --- | --- | --- | --- |
| Chatterbox Nano 110M | MIT, [ResembleAI/chatterbox-nano](https://huggingface.co/ResembleAI/chatterbox-nano) | en, clones | 2.0-2.8x | en 1/50 (2%); en from a Persian clip 0/50 |
| Chatterbox Turbo 350M | MIT, [ResembleAI/chatterbox-turbo](https://huggingface.co/ResembleAI/chatterbox-turbo) | en, clones | 3.9x | en 1/50 (2%) |
| MOSS-TTS-Nano 100M (ONNX) | Apache-2.0, [MOSS-TTS-Nano-100M-ONNX](https://huggingface.co/OpenMOSS-Team/MOSS-TTS-Nano-100M-ONNX) and [codec](https://huggingface.co/OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX) | 20 languages, clones | 3.2x en, 2.6x fa | en 1/50; fa 4/36 (11%); en from a Persian clip 0/50 |
| Kokoro 82M (ONNX) | Apache-2.0, [onnx-community/Kokoro-82M-v1.0-ONNX](https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX) | en stock voices only | well under 1x (about 0.5x with start-up) | en 1/50 |

## What is pinned

- **English clone: Chatterbox Nano.** Same read-back accuracy as Turbo in our test, faster (2.8x against 3.9x), 1.9 GB
  against 2.8 GB on disk. Turbo was downloaded, measured and deleted; if it sounds better by ear it works with
  `chatterbox-tts==0.1.7` from PyPI and the same worker (`nano=False`). Both mark their output with Resemble's
  inaudible Perth watermark. Upstream `resemble-ai/chatterbox` is retired but public; Nano needs its master branch,
  so it is pinned by commit `ab55923` (PyPI 0.1.7 has no Nano).
- **Persian speech: MOSS-TTS-Nano**, cloning from a clip (the language is taken from the text). 11% of words
  came back wrong, and a long Persian sentence read back as partly garbled: fine for short lines, listen to everything.
- **English from a Persian reference clip** stays intelligible with both Nano and MOSS (0 of 50 words wrong).
  Whether it keeps a Persian accent, and how close it sounds to the speaker, is for ears.
- **Stock English voice: Kokoro**, no clip needed (`./pal voice say stock ...`). Text goes through the `misaki`
  dictionary (Apache-2.0) and spaCy (MIT); espeak-ng, which is GPL, is not used. Words missing from the
  dictionary are skipped. `misaki` itself requires `num2words` (LGPL-2.1, used as an unmodified library): the one
  non-MIT/Apache/BSD package in the voice environment; our own code does not use it.

## Persian stock voice: none that is clean

Piper has five Persian voices (`rhasspy/piper-voices`, `fa_IR`: amir, ganji, ganji_adabi, reza_ibrahim, gyro).
Four model cards give the data licence as CC0; gyro's says "See URL". All are fine-tuned from the English
`lessac` voice, whose training data licence we did not check. But Piper 1.x is GPL-3.0 and Persian text needs
espeak-ng (GPL-3.0) to become phonemes, so no Persian Piper voice can be used under the licence rule. Not installed,
not measured. Persian generated videos use MOSS cloned from a clip the creator provides (their own, or a synthetic one).

## Disk and speed

Models in `~/.cache/editpal`: Chatterbox Nano 1.9 GB, MOSS 0.7 GB, Kokoro 0.3 GB.
`.venv-voice` (CPU PyTorch 2.6, chatterbox, ONNX runtime, spaCy): 1.9 GB. A minute of speech costs about 2-3 minutes
of compute in either clone engine, so a 10 minute dub is a 20-30 minute background job; lines are cached.
