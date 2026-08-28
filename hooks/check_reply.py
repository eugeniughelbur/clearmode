#!/usr/bin/env python3
"""Stop hook: score Claude's finished reply against CLEAR-100 and block on errors.

Reads the hook payload on stdin, pulls the last assistant message out of the
transcript, strips code and quoted output, and runs the installed clearcheck.
Blocks only on errors, never on warnings, so it cannot nag forever.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path.home() / ".claude" / "skills" / "clearmode" / "scripts" / "clearcheck.py"
PROFILE = "general"
MIN_WORDS = 40          # one-liners are fine as they are
MAX_BLOCKED_ERRORS = 6  # a huge dump means something else is wrong, let it through


def last_assistant_text(transcript: Path) -> str:
    text = ""
    for line in transcript.read_text(errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("type") != "assistant":
            continue
        content = row.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        if any(p.strip() for p in parts):
            text = "\n".join(parts)
    return text


def prose_only(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)   # fenced code
    text = re.sub(r"^\s*[>|].*$", "", text, flags=re.M)  # quotes and table rows
    text = re.sub(r"`[^`]+`", "X", text)                 # inline code becomes a token
    text = re.sub(r"https?://\S+", "X", text)
    return text.strip()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    if payload.get("stop_hook_active"):   # already retrying, do not loop
        return 0
    if not CHECKER.exists():
        return 0

    transcript = Path(payload.get("transcript_path", ""))
    if not transcript.is_file():
        return 0

    prose = prose_only(last_assistant_text(transcript))
    if len(prose.split()) < MIN_WORDS:
        return 0

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
        fh.write(prose)
        tmp = fh.name

    try:
        run = subprocess.run(
            [sys.executable, str(CHECKER), tmp, "--profile", PROFILE, "--json"],
            capture_output=True, text=True, timeout=20,
        )
        report = json.loads(run.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return 0
    finally:
        Path(tmp).unlink(missing_ok=True)

    if isinstance(report, list):
        report = report[0] if report else {}
    errors = [f for f in report.get("findings", []) if f.get("severity") == "error"]
    if not errors or len(errors) > MAX_BLOCKED_ERRORS:
        return 0

    lines = [
        "Your reply broke the CLEAR-100 rules the user reads by. Rewrite the reply, then finish.",
        "Do not mention this check, do not show a score, and do not apologise. Just say it better.",
        "",
    ]
    for f in errors:
        note = f.get("note") or f.get("fix", "")
        lines.append(f"- {f['rule']} {f['title']}: {note}")
        if f.get("match"):
            lines.append(f"    in: {f['match'][:90]}")

    print(json.dumps({"decision": "block", "reason": "\n".join(lines)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
