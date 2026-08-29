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
HOOKS_DIR = Path.home() / ".claude" / "hooks" / "clearmode"
MARKER = "hooks/clearmode/check_"

# event -> (script, matcher). Stop covers what Claude says in chat. PreToolUse
# covers what it writes to a file or sends to a person.
WIRING = {
    "Stop": ("check_reply.py", ""),
    "PreToolUse": ("check_outgoing.py", "Write|Edit|Artifact|mcp__.*(Gmail|gmail|Slack|slack|Linear).*"),
}


def entry(script: str, matcher: str) -> dict:
    return {
        "matcher": matcher,
        "hooks": [{"type": "command", "command": f"python3 {HOOKS_DIR / script}", "timeout": 25}],
    }


def has_hook(groups: list) -> bool:
    return any(MARKER in h.get("command", "") for g in groups for h in g.get("hooks", []))


def strip(groups: list) -> list:
    return [g for g in groups
            if not any(MARKER in h.get("command", "") for h in g.get("hooks", []))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not SETTINGS.parent.is_dir():
        print("no ~/.claude directory, nothing to do")
        return 0

    data = json.loads(SETTINGS.read_text()) if SETTINGS.is_file() else {}
    hooks = data.setdefault("hooks", {})
    changed = []

    for event, (script, matcher) in WIRING.items():
        groups = hooks.setdefault(event, [])
        if args.remove:
            if has_hook(groups):
                hooks[event] = strip(groups)
                changed.append(f"removed {event}")
        elif has_hook(groups):
            print(f"{event} already registered")
        else:
            groups.append(entry(script, matcher))
            changed.append(f"registered {event}")

    if not changed:
        print("nothing to change")
        return 0
    action = ", ".join(changed)

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
