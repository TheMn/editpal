# Your Drive folder

editpal reaches exactly one folder of your Google Drive, and nothing else.

## Reading: share one folder

1. Make a folder for the channel. Inside it, one subfolder per video, named however you like
   (`2026-12 Recursion`). Put everything for that video in it: camera files, screen recordings,
   microphone audio, B-roll, notes, a script, your own subtitle files.
   Optional: a `brand/` subfolder (logo, reference frames, music you own).
2. Share the channel folder: Share → General access → **Anyone with the link** → Viewer.
   Give the link to `/setup` (it is stored in `channel.json`).

Anyone who has the link can view the folder, so treat the link like a password. Files you never
put in this folder cannot be reached.

## Writing: the upload link (once, about five minutes)

Finished videos are large, so they are written straight into your Drive. This uses a small
script that runs under **your** Google account and can only add files to **one** folder that it
creates itself (`editpal-out`). It never hands out a login, and it cannot read, change or delete
anything else in your Drive.

1. Open <https://script.google.com> → **New project**.
2. Delete what is there and paste the contents of [`tools/drive-upload.gs`](../tools/drive-upload.gs).
3. **Deploy** → New deployment → type **Web app** → Execute as **Me** → Who has access
   **Anyone** → Deploy. Approve the permission it asks for (creating files in your Drive).
4. Copy the **Web app URL**.
5. In Claude Code on the web: the environment menu → Edit → add a secret (or environment
   variable) named `EDITPAL_UPLOAD_URL` with that URL as its value. Do not paste the URL in the chat.
6. Start a new session. `./pal doctor` shows "upload link: set".

Results now appear in `editpal-out/<video>/` in your Drive, and you get their links in the chat.
Without the upload link everything still works; files are sent in the chat instead.

Treat the URL like a password too: whoever has it can add files to that one folder. To revoke
it: script.google.com → your project → Deploy → Manage deployments → Archive.

## Cost and space

Google charges nothing for any of this. Files count against your normal Drive storage (15 GB
free): delete old drafts from `editpal-out` when a video is published.

> This upload route has not been tested end to end yet (see `docs/PILOT.md`). If it fails, send
> Claude the error it printed; the fallback is delivery in the chat.
