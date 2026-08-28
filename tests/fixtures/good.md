# Clearmode cut our docs from grade 14 to grade 8

Our docs scored grade 14. Support tickets about setup dropped 31% in the six weeks after we got them to grade 8.

The checker reads one JSON rule pack and scores four things:

- Plain: can a non-specialist read it once
- Human: does it read like a person who did the work
- Structured: does the page shape match the information shape
- Dense: does every sentence carry a fact

Install takes three steps.

1. Clone the repo.
2. Copy `SKILL.md` into your agent's skills folder.
3. Run `python3 scripts/clearcheck.py README.md`.

The loader validates the config before it starts the run. If the config is bad, it exits 2 and prints the line number.

## What it does not do

It can't tell you if a claim is true. It only tells you if a reader can follow it.
