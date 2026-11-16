"""Pull improvements from the editpal template into this copy, keeping the channel's own files.

    ./pal update            show what would change
    ./pal update --apply    take the template's version of the studio's own files

Takes from the template: tools/, .claude/, docs/, formats/_library/, brand/kit/, library/,
tests/, pal, package.json, package-lock.json, CLAUDE.md, GLOSSARY.md.
Never touches: channel.json, channel.md, ideas.md, brand/frame.md, brand/fonts/, brand/reference/,
formats/*.md (your formats), voices/, episodes/, README.md.
The template's address is `git remote get-url template` (added on first run from --from, default
https://github.com/TheMn/editpal). Review the result with `git diff --staged`, then commit.
"""
import argparse
import subprocess
import sys

from common import ROOT, die, say

DEFAULT = "https://github.com/TheMn/editpal"
TAKE = ["tools", ".claude", "docs", "formats/_library", "formats/README.md", "brand/kit", "brand/README.md",
        "library", "tests", "pal", "package.json", "package-lock.json", "CLAUDE.md", "GLOSSARY.md", ".gitignore"]


def git(*args, check=True):
    """Run git in the repository and return its stdout."""
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"git {' '.join(args)}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'failed'}")
    return r.stdout


def main(argv):
    ap = argparse.ArgumentParser(prog="./pal update", add_help=False)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--from", dest="url", default=None)
    ap.add_argument("--branch", default="main")
    a = ap.parse_args(argv)

    remotes = git("remote").split()
    if "template" not in remotes:
        git("remote", "add", "template", a.url or DEFAULT)
    elif a.url:
        git("remote", "set-url", "template", a.url)
    git("fetch", "--quiet", "template", a.branch)
    ref = f"template/{a.branch}"

    # only paths that exist in the template
    paths = [p for p in TAKE if git("ls-tree", "--name-only", ref, p, check=False).strip()]
    changed = git("diff", "--stat", "HEAD", ref, "--", *paths).strip()
    if not changed:
        say("already up to date with the template.")
        return 0
    if not a.apply:
        say(changed, "", "nothing changed yet. To take these: ./pal update --apply")
        return 0
    if git("status", "--porcelain", "--", *paths).strip():
        die("you have uncommitted changes in the studio's own files; commit or discard them first", 3)
    git("checkout", ref, "--", *paths)
    say(changed, "", "taken from the template and staged. Next: sh tools/setup.sh, ./pal test,",
        "then look at `git diff --staged` and commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
