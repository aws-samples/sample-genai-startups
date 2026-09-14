#!/usr/bin/env python3
"""Validate Gateway/MCP tool names vs the 64-char Converse limit; suggest aliases.
Gateway exposes tools as '<target>___<tool>'.
Exits non-zero if any name is invalid so it can gate a deploy.
Usage: validate_tool_names.py NAME [NAME ...] | --file names.txt (one per line)"""
import re, sys

LIMIT = 64
def sanitize(name):
    short = re.sub(r"[^a-zA-Z0-9_-]", "_", name.split("___")[-1])
    return short[:LIMIT] or "tool"

def load(argv):
    if argv and argv[0] == "--file":
        return [l.strip() for l in open(argv[1]) if l.strip()]
    return argv

def main(argv):
    names = load(argv)
    if not names:
        sys.exit("provide tool names or --file names.txt")
    used, bad = set(), 0
    for n in names:
        if len(n) <= LIMIT and re.fullmatch(r"[a-zA-Z0-9_-]+", n or ""):
            print(f"OK   ({len(n):>3}) {n}"); continue
        bad += 1
        alias = sanitize(n)
        while alias in used:
            alias = (alias[:LIMIT - 2] + "_" + str(len(used)))[:LIMIT]
        used.add(alias)
        print(f"FAIL ({len(n):>3}) {n}\n        -> alias: {alias} ({len(alias)} chars)")
    print(f"\n{bad} of {len(names)} need an alias (limit {LIMIT}).")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main(sys.argv[1:])
