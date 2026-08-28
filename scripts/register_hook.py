#!/usr/bin/env python3
"""Register (or remove) the clearmode Stop hook in ~/.claude/settings.json.

The hook scores Claude's finished reply and makes it rewrite anything that
breaks CLEAR-100, so the standard applies to what Claude says, not only to
files it writes.

  python3 scripts/register_hook.py            # add it
  python3 scripts/register_hook.py --remove   # take it out
  python3 scripts/register_hook.py --dry-run  # show what would change
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK_DEST = Path.home() / ".claude" / "hooks" / "clearmode" / "check_reply.py"
MARKER = "clearmode/check_reply.py"


def entry() -> dict:
    return {
        "matcher": "",
        "hooks": [{"type": "command", "command": f"python3 {HOOK_DEST}", "timeout": 25}],
    }


def has_hook(stop: list) -> bool:
    return any(MARKER in h.get("command", "") for g in stop for h in g.get("hooks", []))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not SETTINGS.parent.is_dir():
        print("no ~/.claude directory, nothing to do")
        return 0

    data = json.loads(SETTINGS.read_text()) if SETTINGS.is_file() else {}
    stop = data.setdefault("hooks", {}).setdefault("Stop", [])
    present = has_hook(stop)

    if args.remove:
        if not present:
            print("hook not registered, nothing to remove")
            return 0
        data["hooks"]["Stop"] = [
            g for g in stop
            if not any(MARKER in h.get("command", "") for h in g.get("hooks", []))
        ]
        action = "removed"
    else:
        if present:
            print(f"already registered in {SETTINGS}")
            return 0
        stop.append(entry())
        action = "registered"

    if args.dry_run:
        print(f"would be {action} in {SETTINGS}")
        return 0

    if SETTINGS.is_file():
        shutil.copy(SETTINGS, SETTINGS.with_suffix(".json.clearmode-backup"))
    SETTINGS.write_text(json.dumps(data, indent=2) + "\n")
    print(f"{action} in {SETTINGS}")
    print("restart Claude Code for it to take effect")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
