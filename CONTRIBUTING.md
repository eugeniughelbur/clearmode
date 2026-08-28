# Contributing to clearmode

clearmode has 43 rules and exactly one place to change them. The most useful thing you can send is a sentence the checker gets wrong.

## The one rule about editing

`rules/clear-100.json` is the single source of truth. Everything under `targets/` is generated from it.

Change the JSON, then recompile. Never hand-edit a target, because the next compile overwrites your work.

```bash
python3 scripts/compile_targets.py          # rebuild all 18 targets
python3 scripts/compile_targets.py --check  # fail if any target is stale
python3 -m unittest discover tests -v       # 57 tests
```

## Disputing a rule

Open an issue with the `rule_dispute` template. Include three things:

1. The rule ID from the report, for example `H1` or `P5` or `D1`
2. The exact sentence
3. Which way it is wrong: a false positive that should pass, or a false negative that should fail

One concrete sentence beats a paragraph of reasoning. It becomes a test case.

## Adding a word to a lexicon

Slop words, jargon glosses, and substitutions live in `rules/clear-100.json` under `slop_words`, `jargon`, and `substitutions`. Each entry needs a plain-word replacement, not just a ban.

A word earns a place on the slop list if a reader would notice it as filler. A word earns a jargon gloss if someone outside the field would look it up.

## Pull requests

Run the three commands above before you open one. CI runs the same checks plus a prose gate: the repo's own documentation has to score 85 or higher against its own standard.

```bash
python3 scripts/clearcheck.py README.md CLEAR-100.md AGENTS.md --profile technical --gate 85
```

If you add prose to the repo, it has to pass too. That is the point.

## Scope

clearmode measures readability. It does not check facts, detect authorship, or rewrite for you outside the `/clear-rewrite` command. Feature requests that pull it toward AI detection will be declined, because that is a different and much less useful product.
