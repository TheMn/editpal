#!/usr/bin/env python3
"""./pal <command> [arguments]: every tool in tools/ is one command.

    ./pal                    list the commands
    ./pal <command> --help   what one command does and how to call it

A command is a file tools/<command>.py with a main(argv) function; its docstring is its help.
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SKIP = {"pal", "common"}


def commands():
    return sorted(f[:-3] for f in os.listdir(HERE)
                  if f.endswith(".py") and f[:-3] not in SKIP and not f.startswith("_"))


def first_line(name):
    try:
        with open(os.path.join(HERE, name + ".py"), encoding="utf-8") as f:
            src = f.read()
        doc = src.split('"""')[1] if '"""' in src else ""
        return doc.strip().splitlines()[0] if doc.strip() else ""
    except OSError:
        return ""


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print("editpal tools. Usage: ./pal <command> [arguments]   (./pal <command> --help)\n")
        for c in commands():
            print(f"  {c:<11} {first_line(c)}")
        return 0
    name = args[0].replace("-", "_")
    if name not in commands():
        print(f"no command '{args[0]}'. Run ./pal to list them.", file=sys.stderr)
        return 2
    mod = importlib.import_module(name)
    if len(args) > 1 and args[1] in ("-h", "--help"):
        print((mod.__doc__ or "").strip())
        return 0
    return mod.main(args[1:]) or 0


if __name__ == "__main__":
    sys.exit(main())
