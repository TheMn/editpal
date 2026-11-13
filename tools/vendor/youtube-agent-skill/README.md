# From youtube-agent-skill

`title.py` (title + thumbnail-text linter) and `chapters.py` (chapters checked against YouTube's
rules) are copied unchanged from
[Jakeschincariol/youtube-agent-skill](https://github.com/Jakeschincariol/youtube-agent-skill)
@ `a2feb21`, MIT licence (`LICENSE`). Plain Python 3, no dependencies. English text only.
Used by the `package` skill.

```bash
python3 tools/vendor/youtube-agent-skill/title.py --title "…" --thumb "…"
python3 tools/vendor/youtube-agent-skill/chapters.py subs/en.srt --target 8
```
