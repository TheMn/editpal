"""Run the pinned local HyperFrames with telemetry, updates and account commands switched off.

    ./pal hf <hyperframes arguments>        e.g.  ./pal hf check   ./pal hf snapshot --at 2,5
    ./pal hf --which                        print the browser and the CLI that would be used

HyperFrames is installed by `npm install` (node_modules/.bin/hyperframes, version pinned in
package.json). This wrapper sets DO_NOT_TRACK and the HYPERFRAMES_* opt-outs, points it at an
installed headless Chromium (no download), adds --skip-skills to `init`, and refuses everything that
signs in, publishes or sends data: auth, cloud, lambda, cloudrun, publish, feedback, events,
upgrade, skills, `media-use generate`. Run it inside a HyperFrames project folder (or pass one).
Other modules call run(args, cwd).
"""
import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "node_modules", ".bin", "hyperframes")
REFUSED = {"auth", "cloud", "lambda", "cloudrun", "publish", "feedback", "events", "upgrade", "skills"}
OFF = {"DO_NOT_TRACK": "1", "HYPERFRAMES_NO_TELEMETRY": "1", "HYPERFRAMES_NO_UPDATE_CHECK": "1",
       "HYPERFRAMES_NO_AUTO_INSTALL": "1", "HYPERFRAMES_SKIP_SKILLS": "1"}
BROWSER_GLOBS = [
    "/opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
    "~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
    "~/.cache/puppeteer/chrome-headless-shell/*/chrome-headless-shell-*/chrome-headless-shell",
    "~/.cache/hyperframes/chrome-headless-shell/*/chrome-headless-shell-*/chrome-headless-shell",
    "/opt/pw-browsers/chromium-*/chrome-linux64/chrome",
]


def browser():
    """Path of a Chrome HyperFrames can drive: $HYPERFRAMES_BROWSER_PATH, else an installed
    headless shell (its fast capture path), else '' (HyperFrames then looks for a system Chrome)."""
    given = os.environ.get("HYPERFRAMES_BROWSER_PATH", "")
    if given and os.path.exists(given):
        return given
    for pattern in BROWSER_GLOBS:
        hits = sorted(glob.glob(os.path.expanduser(pattern)))
        if hits:
            return hits[-1]
    return ""


def env():
    """The environment HyperFrames runs in."""
    e = dict(os.environ)
    e.update(OFF)
    b = browser()
    if b:
        e["HYPERFRAMES_BROWSER_PATH"] = b
    return e


def refusal(args):
    """Why these arguments are not allowed, or '' when they are."""
    if not args:
        return ""
    if args[0] in REFUSED:
        return f"'{args[0]}' signs in, publishes or sends data: editpal never uses it."
    if args[0] == "media-use" and "generate" in args[1:]:
        return "'media-use generate' needs a HeyGen account: editpal never uses it."
    return ""


def argv(args):
    """The full command line for these arguments."""
    args = list(args)
    if args and args[0] == "init" and "--skip-skills" not in args:
        args.append("--skip-skills")
    return [CLI] + args


def run(args, cwd=None, capture=False, extra_env=None):
    """Run HyperFrames; returns the CompletedProcess (stdout/stderr text when capture=True).
    Refused arguments return code 2 with the reason in stderr."""
    why = refusal(args)
    if why:
        return subprocess.CompletedProcess(args, 2, "", why)
    if not os.path.exists(CLI):
        return subprocess.CompletedProcess(args, 1, "", "HyperFrames is not installed: run `sh tools/setup.sh`.")
    e = env()
    e.update(extra_env or {})
    return subprocess.run(argv(args), cwd=cwd, env=e, text=True, capture_output=capture)


def main(argv_):
    """./pal hf entry point."""
    if not argv_ or argv_[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if argv_[0] == "--which":
        print(f"cli:     {CLI}\nbrowser: {browser() or '(none found: HyperFrames will look for a system Chrome)'}")
        return 0
    why = refusal(argv_)
    if why:
        print(f"✗ {why}", file=sys.stderr)
        return 2
    return run(argv_).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
