# Default fonts

Three families, all under the SIL Open Font License 1.1 (free for commercial use, embedding in
video, and redistribution; the licence text sits next to the files as `OFL-*.txt`).

| Family | Used for | Files | Source |
| --- | --- | --- | --- |
| Inter (variable) | Latin text: titles, captions, UI | `InterVariable.ttf`, `Inter-latin-variable.woff2` | https://github.com/rsms/inter (ttf); npm `@fontsource-variable/inter` 5.3.0 (woff2) |
| Vazirmatn | Persian (also covers Latin acceptably) | `Vazirmatn-Regular.ttf`, `Vazirmatn-Bold.ttf`, `Vazirmatn-arabic-variable.woff2`, `Vazirmatn-latin-variable.woff2` | https://github.com/rastikerdar/vazirmatn (ttf); npm `@fontsource-variable/vazirmatn` 5.3.0 (woff2) |
| JetBrains Mono | code | `JetBrainsMono-Regular.ttf`, `JetBrainsMono-Bold.ttf`, `JetBrainsMono-latin-*.woff2` | https://github.com/JetBrains/JetBrainsMono (ttf); npm `@fontsource/jetbrains-mono` 5.3.0 (woff2) |

- `.ttf` is what burned-in subtitles use (libass via `./pal subs burn`; it reads this folder).
  `.woff2` is for HyperFrames pages (`@font-face`); those files are subsets (Latin, or Arabic
  script for Vazirmatn), so load both Vazirmatn files for Persian text with English words.
- Keep this folder under about 3 MB. To use another font, add its files here, name its licence
  in this table, and set it in `brand/frame.md`. Only open licences (OFL, Apache-2.0).
