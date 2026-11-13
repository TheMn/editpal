# Stage: rough cut (the A-cut)

Everything later sits on this. A cut that sounds wrong makes the whole video feel wrong, so the
standard is: it plays like one clean take.

**The creator brought their own A-cut** (a file named a-cut / acut, or they say so):
`./pal cut adopt <ep> <file>`, then step 6.

1. **The tool's pass.** `./pal cut propose <ep>` (`--tight`, `--natural` or `--loose` from the
   format). It removes the slate, long pauses (toward this speaker's own rhythm), fillers, false
   starts and plain retakes, and lists anything doubtful as a *suggestion*.
2. **Your pass: the editor's judgment.** Read the whole recording once with
   `./pal transcribe show <ep> --raw`. Find what a tool cannot know:
   - the same thing said twice in different words: keep the complete, fluent take (usually the last);
   - a sentence that trails off and is picked up later;
   - a weak start before the real opening line;
   - sections in a different order than `script.md`;
   - what must be protected: sponsor reads, a joke that needs its pause, a demo that runs in silence.

   Write your decisions as operations in ids (`docs/TOOLS.md`, "Operations") and apply them:
   `./pal cut apply <ep> ops.json --by llm`. **Removing a mistake is a cut. Removing content
   (a tangent, a repeated explanation) is a `suggest`** unless the brief asked for a tight
   selects cut: the creator decides what they meant to say.
3. **Listen with the tools.** `./pal cut render <ep> --preview`, then `./pal cut verify <ep>`.
   For every flagged seam look at its strip (`./pal sheet seams <ep> --flagged`) and fix the
   cause: `loosen` a cut that clips a word, move a cut that lands in a breath, restore a piece
   too short to keep. Repeat until clean, at most three rounds; what is still flagged is shown
   on the review page, never hidden.
4. **Cold read.** `./pal cut remap <ep>`, then a `fresh-eyes` subagent gets only
   `./pal transcribe show <ep>` (the edited text) and the brief: does it read as one continuous
   take? It returns ranked problems; fix the real ones.
5. **Gate 2: the paper edit.** `./pal sheet reel <ep>`, `./pal board paper <ep>`, upload the
   preview (`./pal drive put <ep> build/cut/acut-preview.mp4`), show the page. Say the length
   before → after and how many suggestions wait for a yes or no. Stop.
   - Notes come back as ids: turn them into operations (`--by creator`), render (only the
     touched segments re-encode), verify, and re-show **only what changed**.
6. **Picture lock** on `lock`: `./pal cut render <ep>` (full quality, background),
   `./pal cut lock <ep>`, commit `edit.json` and `transcript.json`. From here graphics, music and
   the dub are timed to this cut. If the creator also edits by hand, offer
   `./pal export <ep> --fcpxml` (opens in DaVinci Resolve, Premiere, Final Cut).

Record in `episode.md`: length before → after, counts by kind, suggestions accepted and
refused, seams still flagged and why they were left.
