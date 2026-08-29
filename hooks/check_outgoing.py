#!/usr/bin/env python3
"""PreToolUse hook: check text before it is written to a file or sent to a person.

The reply hook covers what Claude says in chat. This covers everything else:
a Slack message, an email, a GitHub review, a draft saved to disk. Those reach
other people, so they get the same rules.

Blocks the tool call and hands back the broken rules. Claude rewrites and
retries, so nothing wrong ever leaves.
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
LOG = Path.home() / ".claude" / "hooks" / "clearmode" / "log.txt"
LOG_KEEP = 400
MIN_WORDS = 25
MAX_BLOCKING = 14

# Same five as the reply hook, plus the ones worth a retry when the text is
# going to another human and a rewrite costs nothing they will see.
BLOCK_ON = {"H1", "H2", "H3", "H4", "H6", "H8", "H12", "H14", "H16", "D5"}

# tool name -> input fields that carry prose a person will read
FIELDS = {
    "mcp__claude_ai_Gmail__send_message": ("body",),
    "mcp__claude_ai_Gmail__create_draft": ("body",),
    "mcp__claude_ai_Gmail__reply": ("body",),
    "mcp__claude_ai_Gmail__forward": ("body",),
    "mcp__gmail-personal__send_email": ("body",),
    "mcp__gmail-personal__draft_email": ("body",),
    "mcp__claude_ai_Slack__slack_send_message": ("text", "markdown_text"),
    "mcp__claude_ai_Slack__slack_send_message_draft": ("text", "markdown_text"),
    "mcp__claude_ai_Slack__slack_schedule_message": ("text", "markdown_text"),
    "mcp__singlegrain-gateway__slack_post_message": ("text",),
    "mcp__claude_ai_Linear__save_comment": ("body",),
    "mcp__claude_ai_Linear__save_issue": ("description",),
    "mcp__claude_ai_Linear__save_document": ("content",),
    "Artifact": ("description",),
}

# file writes worth checking: prose destinations, not code
PROSE_SUFFIX = {".md", ".mdx", ".txt"}
SKIP_PATH = ("/log", "/logs/", "CHANGELOG", "/node_modules/", "/.git/")


def log(verdict: str, detail: str = "") -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        old = LOG.read_text().splitlines() if LOG.is_file() else []
        old.append(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {verdict:<6} {detail}".rstrip())
        LOG.write_text("\n".join(old[-LOG_KEEP:]) + "\n")
    except OSError:
        pass


def prose_only(text: str) -> str:
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)  # frontmatter
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"^\s*\|.*$", "", text, flags=re.M)
    text = re.sub(r"`[^`]+`", "X", text)
    text = re.sub(r"https?://\S+", "X", text)
    return text.strip()


def target(tool: str, data: dict) -> tuple[str, str] | None:
    """Return (label, text) if this call carries prose worth checking."""
    if tool in FIELDS:
        parts = [str(data.get(f, "")) for f in FIELDS[tool] if data.get(f)]
        if parts:
            return tool.split("__")[-1], "\n".join(parts)
        return None

    if tool in ("Write", "Edit"):
        path = str(data.get("file_path", ""))
        if Path(path).suffix.lower() not in PROSE_SUFFIX:
            return None
        if any(s in path for s in SKIP_PATH):
            return None
        body = data.get("content") or data.get("new_string") or ""
        if body:
            return Path(path).name, str(body)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if not CHECKER.exists():
        return 0

    tool = payload.get("tool_name", "")
    found = target(tool, payload.get("tool_input", {}) or {})
    if not found:
        return 0
    label, raw = found

    prose = prose_only(raw)
    words = len(prose.split())
    if words < MIN_WORDS:
        return 0

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
        fh.write(prose)
        tmp = fh.name
    try:
        run = subprocess.run(
            [sys.executable, str(CHECKER), tmp, "--profile", "general", "--json"],
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
        log("pass", f"{label}, {words}w, score {report.get('score')}")
        return 0

    log("BLOCK", f"{label}, {words}w, " + ", ".join(
        f"{f['rule']}({(f.get('match') or '')[:24]})" for f in hits))

    lines = [
        f"This text goes to a person. It breaks the CLEAR-100 rules {label} has to meet.",
        "Rewrite the text and call the tool again. Do not mention this check.",
        "",
    ]
    for f in hits[:8]:
        lines.append(f"- {f['rule']} {f['title']}: {f.get('note') or f.get('fix','')}")
        if f.get("match"):
            lines.append(f"    in: {f['match'][:90]}")

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "\n".join(lines),
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
