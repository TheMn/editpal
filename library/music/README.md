# Music library

Only music that is **free for commercial use without conditions**: CC0 or public domain, where the
*recording itself* is free (a free composition played on a copyrighted recording is not enough).
CC-BY (credit required), and anything NC, ND or SA are not allowed here. `library.json` holds one
entry per track: `{id, mood, title, performer, use, seconds, license, page, url, sha1}`. The files
are not in git: `./pal music get <id>` downloads one into `$EDITPAL_CACHE/music/` and checks its SHA-1.

Moods: `calm` `warm` `upbeat` `driving` `playful` `tense` `ambient`.

```
./pal music list [--mood warm]
./pal music preview <id> /tmp/p.mp3      # 30 s from the middle
./pal music get <id>
```

Use a track in `plan.json`: `{"track": "library:<id>", "t": [0, 90], "gain_db": -20, "duck": true}`.
Every track used gets a row in the episode's `credits.md` (page URL and licence).

## Add a track

1. Find a recording on Wikimedia Commons whose file page shows CC0 or "Public domain" for the
   recording. Prefer ambient, electronic, lo-fi, acoustic guitar and jazz; classical under a modern
   video often sounds wrong (a few CC0 piano and orchestral recordings are here as `calm`/`ambient`).
2. `./pal music add <file-page-url> --mood calm --id short-name --use "quiet explainer bed"`.
   It reads the licence from the Commons API and refuses anything but CC0 / public domain.
3. Read the file page yourself: the licence box must be about the recording, and the uploader
   must be its performer or the rights holder. Then `./pal music preview <id> out.mp3` and listen.
   A track is only trusted after a person has listened to it once.

Wikimedia rate-limits bursts of downloads from one address (HTTP 429, "retry in 10 minutes"):
download only the tracks the episode uses.

## If YouTube shows a Content ID claim

A claim on a CC0 or public-domain track is usually a mistake (another uploader registered the same
recording). Dispute it and give the track's Commons page (the `page` field), the licence name and
the date you downloaded it; claims on public-domain tracks are normally released within days. Keep
the page URL in `credits.md`. If a claim stays, replace the track with another one.

## The creator's own music

A creator can drop tracks they own into their Drive folder `brand/music/` with a short licence note
next to each (who made it, that it is theirs, or the licence). They are used as music sources in
`sources.json` and listed in `credits.md`; they are not added to this shared library.
