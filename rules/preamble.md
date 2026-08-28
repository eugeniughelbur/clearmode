# CLEAR-100

**Clear Language for Every Actual Reader.** 43 rules on 4 axes for text produced with AI, aimed at the person who has to read it.

## Why it exists

In the 1980s the European aerospace industry wrote [ASD-STE100 Simplified Technical English](https://www.asd-ste100.org/) because an ambiguous line in a maintenance manual is a safety problem. A mechanic under a wing cannot ask the author a follow-up question. STE fixed that with 53 rules and about 900 approved words: one meaning per word, active voice, short sentences, one instruction at a time.

STE works. It also reads like a machine, on purpose. It bans contractions, bans the semicolon, and cares nothing about whether a human enjoys the page, because a human enjoying the page was never the goal.

Two things changed. Most text is now drafted by a model, which means the failure mode is no longer ambiguity. It is filler that scans as competent. And most of that text is read by people outside the field it came from, on a phone, deciding in one screen whether to keep going.

So CLEAR-100 keeps the STE discipline and adds what STE never needed:

- A **human** axis, because text that reads synthetic gets discounted before it gets read.
- A **structured** axis, because the shape of a page decides whether it gets read at all.
- A **dense** axis, because the real complaint about AI writing is not vocabulary. It is that nothing is being said.

## What it is not

- Not a detector. It does not guess whether a model wrote something. It measures whether a person can read it.
- Not a compliance claim against ASD-STE100. That standard's approved-word dictionary is ASD's copyright and is not reproduced here.
- Not a style opinion. Every rule states its failure mode and its fix. Disagree with a rule by changing the rule pack, not by ignoring the output.

## How to use it

The standard is data, not prose. `rules/clear-100.json` is the single source of truth. The checker reads it, and every agent target is compiled from it, so a rule change propagates everywhere in one command.

```bash
python3 scripts/clearcheck.py FILE --profile general
python3 scripts/compile_targets.py
```

Four axes, weighted into one score out of 100. Default gate is 80.
