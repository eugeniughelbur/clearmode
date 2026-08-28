---
description: Install CLEAR-100 into the current repo or agent. Writes the rule block into AGENTS.md, CLAUDE.md, Cursor rules, or a Vale config, and adds a CI gate. Idempotent.
---

# /clear-init

Wire the standard into wherever this project's agents read from.

## Steps

1. Detect what is already here:
   - `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/`, `.vale.ini`, `.github/workflows/`
2. For each one found, install the matching target from `targets/`. Insert between the
   `<!-- CLEAR-100 begin -->` and `<!-- CLEAR-100 end -->` markers. If the markers are
   already there, replace what is between them and change nothing else.
3. If nothing is found, create `AGENTS.md` with the block, and a one-line `CLAUDE.md`
   that reads `@AGENTS.md`.
4. Offer the CI gate. Do not add it without a yes:
   ```yaml
   - run: python3 scripts/clearcheck.py $(git diff --name-only origin/main -- '*.md') --gate 80
   ```
5. Print what you touched, one line per file.

## Rules

- Idempotent. Running twice changes nothing the second time.
- Never overwrite a file outside the markers.
- Never edit a generated target by hand. Change `rules/clear-100.json` and run
  `python3 scripts/compile_targets.py`.
