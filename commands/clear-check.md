---
description: Score a file or pasted text against CLEAR-100 on four axes (Plain, Human, Structured, Dense) and list every finding with the fix. Read-only, changes nothing.
---

# /clear-check

Score text. Report. Do not edit anything.

## Steps

1. Resolve the target. A path in the argument wins. No path means the text pasted in the message, or the file currently open.
2. Pick the profile from what the text is:
   - `social` for an X post, a LinkedIn post, a DM, an ad
   - `general` for a blog post, a newsletter, a landing page, an email
   - `technical` for a README, docs, an architecture note, a PR description
   - `agent` for a system prompt, a skill file, or instructions another agent reads
3. Run the checker:
   ```bash
   python3 scripts/clearcheck.py <file> --profile <profile>
   ```
   For pasted text, write it to a temp file first, or pipe it with `--stdin`.
4. Report in this order:
   - The score, the band, and the verdict, on one line
   - The four axis scores
   - Every `error` finding, with the line and the fix
   - The three highest-value `warn` findings, no more
   - One sentence naming the single biggest problem
5. Stop. Do not rewrite unless the user asks.

## Rules

- Never claim a score you did not get from the checker. Run it.
- If the checker exits 2, say what is wrong with the input instead of guessing a score.
- Do not pad the report with the findings the checker already summarized. Point at the count.
