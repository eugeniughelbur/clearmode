# AGENTS.md

clearmode is the CLEAR-100 writing standard, 43 rules on 4 axes, plus the checker that scores them. These are the rules for any agent editing this repo.

## The one rule that matters

`rules/clear-100.json` is the single source of truth. Every other rule-bearing file in this repo is generated from it.

Generated, never hand-edited:

- `SKILL.md`
- `CLEAR-100.md`
- `references/rules.md`
- `references/lexicons.md`
- everything under `targets/`

To change a rule, a threshold, a word list, or a gloss:

1. Edit `rules/clear-100.json`.
2. Run `python3 scripts/compile_targets.py`.
3. Run `python3 -m unittest discover tests -v`.
4. Commit the JSON and the regenerated targets together.

A pull request that edits a generated file by hand gets closed.

## Layout

| Path | What it is |
|---|---|
| `rules/clear-100.json` | every rule, threshold, and lexicon |
| `rules/preamble.md` | hand-written intro that heads `CLEAR-100.md` |
| `scripts/clearcheck.py` | the checker, stdlib only |
| `scripts/compile_targets.py` | rule pack in, 18 targets out |
| `commands/` | slash commands |
| `tests/` | unittest suite and fixtures |
| `install.sh` | detects your agents and installs the right target |

## Constraints

- **Stdlib only.** No pip, no npm, no lockfile. If a feature needs a dependency, the feature is wrong.
- **Python 3.10+.** Type hints welcome, not required.
- **Deterministic.** Same input, same score, every run. No model calls in the checker.
- **No em-dashes in prose.** The standard bans them, so this repo cannot use them. `tests/fixtures/bad.md` is the exception: it exists to contain tells.
- **No emoji.** Anywhere.
- **Every rule states its failure mode.** A rule with no `why` and no `fix` does not ship.

## Adding a rule

1. Add the object to `rules.rules[]` in the JSON: `id`, `axis`, `title`, `severity`, `detector`, `weight`, `why`, `fix`, and a `bad` and `good` pair.
2. If the detector is `regex`, that is all. Otherwise add a `_detector` method on `Checker` and dispatch it from `run()`.
3. Add a fixture case that the rule catches and one it must not.
4. Recompile and test.

Severity means something. `error` blocks a ship. `warn` needs a stated reason to keep. `review` is a prompt to look, and never gates CI.

## Dogfood

This repo passes its own standard. Before any commit that touches prose:

```bash
python3 scripts/clearcheck.py README.md CLEAR-100.md --profile technical --gate 90
python3 scripts/compile_targets.py --check
```

## What not to do

- Do not add a rule that cannot be stated as a failure mode. Taste is not a rule.
- Do not ban a word without adding its replacement to `substitutions`.
- Do not raise a `review` rule to `warn` without a fixture proving the false-positive rate is near zero.
- Do not claim ASD-STE100 compliance. The approved-word dictionary is ASD's copyright and is not in this repo.
- Do not add telemetry, network calls, or an install step.
