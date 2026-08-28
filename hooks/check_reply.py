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
import time
from pathlib import Path

CHECKER = Path.home() / ".claude" / "skills" / "clearmode" / "scripts" / "clearcheck.py"
PROFILE = "general"
MIN_WORDS = 40    # one-liners are fine as they are
MAX_SHOWN = 8     # never hand back a wall of findings
MAX_BLOCKING = 14 # more than this means a bad parse, let the reply through
SETTLE_TRIES = 6  # the reply is still being flushed to the transcript when Stop fires
SETTLE_WAIT = 0.35

# Which rules are worth interrupting a turn for. Severity in the rule pack is
# tuned for documents; a chat reply is a different contract, so the policy lives
# here rather than in the shared standard.
#
# Every rule below is deterministic: an exact match, a count, or a threshold.
# Judgement-call rules (D1 delete test, D4 horoscope, P6 jargon gloss, H11
# sources, S5 one topic) stay advisory, because they fire on good writing too.
BLOCK_ON = {
    # Human: the AI tells
    "H1",   # slop vocabulary: delve, robust, seamless, leverage
    "H2",   # slop phrases: "in today's fast-paced"
    "H3",   # canned openers: Furthermore, Moreover, Additionally
    "H4",   # em-dashes
    "H6",   # negative parallelism: "not just X but Y"
    "H8",   # "serves as" instead of "is"
    "H12",  # assistant voice: "hope this helps", "great question"
    "H14",  # model self-reference
    "H15",  # announcing that you are stopping
    "H16",  # hedge stacking
    # Plain: readable first time
    "P1",   # sentence over the length cap
    "P5",   # long word where a short one exists
    "P7",   # acronym never expanded
    # Structured: shape matches the content
    "S1",   # three parallel items that should be a list
    "S4",   # paragraph over the sentence cap
    "S7",   # Title Case headings
    "S9",   # emoji used as bullets or headings
    # Dense: says something
    "D3",   # opener with no number, name, or claim
    "D5",   # filler: very, really, basically, just, actually
}


def settled_assistant_text(transcript: Path) -> str:
    """The reply that just finished, once the transcript has caught up.

    Stop fires before the final message is flushed, so a single read returns the
    PREVIOUS turn and Claude gets told to fix text it is no longer writing. Poll
    until the tail stops changing.
    """
    text = last_assistant_text(transcript)
    for _ in range(SETTLE_TRIES):
        time.sleep(SETTLE_WAIT)
        fresh = last_assistant_text(transcript)
        if fresh == text:
            return text
        text = fresh
    return text


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

    prose = prose_only(settled_assistant_text(transcript))
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
    hits = [f for f in report.get("findings", []) if f.get("rule") in BLOCK_ON]
    if not hits or len(hits) > MAX_BLOCKING:
        return 0

    lines = [
        "Your reply broke the CLEAR-100 rules the user reads by. Rewrite the reply, then finish.",
        "Do not mention this check, do not show a score, and do not apologise. Just say it better.",
        "",
    ]
    for f in hits[:MAX_SHOWN]:
        note = f.get("note") or f.get("fix", "")
        lines.append(f"- {f['rule']} {f['title']}: {note}")
        if f.get("match"):
            lines.append(f"    in: {f['match'][:90]}")
    if len(hits) > MAX_SHOWN:
        lines.append(f"- and {len(hits) - MAX_SHOWN} more of the same kind")

    print(json.dumps({"decision": "block", "reason": "\n".join(lines)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
