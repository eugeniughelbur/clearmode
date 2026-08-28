#!/usr/bin/env python3
"""
inject_block.py - put the CLEAR-100 block into a file without touching the rest.

    python3 scripts/inject_block.py AGENTS.md

Replaces whatever sits between the markers, or appends the block if the markers
are not there yet. Running it twice changes nothing.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BEGIN = "<!-- CLEAR-100 begin -->"
END = "<!-- CLEAR-100 end -->"


def block() -> str:
    raw = (ROOT / "targets" / "agents-md-snippet.md").read_text(encoding="utf-8")
    body = raw.split("<!-- CLEAR-100 begin. Paste this block into your AGENTS.md. -->", 1)[-1]
    body = body.replace(END, "").strip()
    return f"{BEGIN}\n{body}\n{END}\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    dest = pathlib.Path(argv[1])
    new = block()
    if dest.exists():
        text = dest.read_text(encoding="utf-8")
        if BEGIN in text and END in text:
            out = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), new.rstrip("\n"),
                         text, flags=re.S)
            action = "unchanged" if out == text else "updated"
        else:
            out = text.rstrip("\n") + "\n\n" + new
            action = "appended"
    else:
        out = new
        action = "created"
    if action != "unchanged":
        dest.write_text(out, encoding="utf-8")
    print(f"{action} {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
