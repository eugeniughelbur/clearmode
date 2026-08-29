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
LOG = Path.home() / ".claude" / "hooks" / "clearmode" / "log.txt"
LOG_KEEP = 400  # lines

# Which rules are worth interrupting a turn for.
#
# A Stop hook fires after the reply is already on the reader's screen, so a
# block shows them the draft AND the rewrite. That double message costs more
# attention than a loose sentence saves. So this list holds only the rules
# where the first version is genuinely bad, never a style nitpick.
#
# Cut from 19 to 5 on 2026-08-29 after the doubles got annoying in practice.
# Dropped: P1 P5 P7 H3 H8 H15 H16 S1 S4 S7 S9 D3 D5. Those still lower the
# score on documents; they no longer interrupt a chat turn.
BLOCK_ON = {
    "H1",   # slop vocabulary: delve, robust, seamless, leverage
    "H2",   # slop phrases: "in today's fast-paced"
    "H4",   # em-dashes
    "H12",  # assistant voice: "hope this helps", "great question"
    "H14",  # model self-reference
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
    """Strip what is not the assistant's own prose.

    Blockquotes are NOT stripped. The user asks for drafts (Slack messages,
    emails, posts) delivered in blockquotes, so a blockquote is usually the
    text he is about to send. That is the text that most needs checking.
    """
    text = re.sub(r"```.*?```", "", text, flags=re.S)      # fenced code
    text = re.sub(r"^\s*\|.*$", "", text, flags=re.M)       # table rows
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)        # unwrap blockquotes, keep the words
    text = re.sub(r"`[^`]+`", "X", text)                   # inline code becomes a token
    text = re.sub(r"https?://\S+", "X", text)
    return text.strip()


def log(verdict: str, detail: str = "") -> None:
    """One line per check, so the user can watch what the hook actually did."""
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        LOG.parent.mkdir(parents=True, exist_ok=True)
        old = LOG.read_text().splitlines() if LOG.is_file() else []
        old.append(f"{stamp}  {verdict:<6} {detail}".rstrip())
        LOG.write_text("\n".join(old[-LOG_KEEP:]) + "\n")
    except OSError:
        pass


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
    words = len(prose.split())
    if words < MIN_WORDS:
        log("skip", f"{words}w, under the {MIN_WORDS}-word floor")
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
    score = report.get("score")
    findings = report.get("findings", [])
    hits = [f for f in findings if f.get("rule") in BLOCK_ON]
    advisory = len(findings) - len(hits)

    if not hits:
        log("pass", f"{words}w, score {score}, {advisory} advisory")
        return 0
    if len(hits) > MAX_BLOCKING:
        log("pass", f"{words}w, {len(hits)} hits looks like a bad parse, let through")
        return 0

    log("BLOCK", f"{words}w, score {score}, " + ", ".join(
        f"{f['rule']}({(f.get('match') or '')[:24]})" for f in hits))

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
