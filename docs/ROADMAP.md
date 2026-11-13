# Roadmap

What editpal does not do yet. Each line says what is missing and how the files already allow for it.

## Next: the pilot

Proving the studio on real footage: [PILOT.md](PILOT.md).

## Not built

| | What is missing | Already in place |
| --- | --- | --- |
| **Automatic camera switching** | choosing the camera by who is speaking | sources are synced by sound; `edit.json` carries an `angle` per kept range, set by hand today |
| **Several speakers on one microphone** | telling voices apart on a single track (for separate clones and lower thirds) | one clone per speaker works when each has their own track |
| **Removing music from an old video's sound** | separating voice and music when only a mixed file exists | new videos keep voice and music as separate files from the start |
| **Dubbing into languages other than English** | a free cloned-voice engine per language | the translation, timing and subtitle steps are language-neutral |
| **Uploading for you** | YouTube and Instagram uploads through their APIs (each needs the creator's own app approval) | `package.md` is paste-ready; `docs/PUBLISH.md` has the clicks |
| **Learning from results** | reading a channel's analytics to suggest what to make next | `ideas.md`, `notes.md` and standing preferences |
| **Finding private things on screen by itself** | detecting keys, emails and faces in a screen recording | the `logger` flags what it sees on contact sheets; blurring is one line in the plan |
| **Finding free B-roll** | searching public-domain archives for a picture the plan asks for | "shots to collect" on the storyboard; the licence ledger |
| **Series** | shared overrides for a recurring show (its own title card, colours, segments) | formats are files; copy one per series today |
| **Many old videos at once** | one command that turns a back catalogue into Shorts or dubs | each video is one command; a workflow can fan them out |
| **Generated images and video** | free local models are too slow on a CPU machine | graphics are drawn in code; the creator's own images are used |
| **Colour grading** | looks, log footage, matching two cameras | exposure and white balance are left as recorded |

## Ideas, not promises

A scrolling teleprompter page; a weekly "what to make next" note; sending ideas from a chat app;
a hand-off to a human editor that carries the graphics as well as the cut.
