---
description: Explain one CLEAR-100 rule: what it catches, why it exists, the fix, and a before-and-after. Use when a finding looks wrong or a rule needs a defense.
---

# /clear-explain

Explain a rule, or defend it.

## Steps

1. Run `python3 scripts/clearcheck.py --explain <RULE_ID>`. Never paraphrase a rule from memory.
2. Give the reason first, then the fix, then the before-and-after.
3. If the user thinks the rule is wrong on their line, decide honestly:
   - The rule is right: show the fix on their exact sentence.
   - The rule is wrong here: tell them to suppress it inline with `clear: ignore <RULE_ID>`.
   - The rule is wrong in general: edit `rules/clear-100.json`, then run
     `python3 scripts/compile_targets.py`. The rule pack is the argument, not the chat.
4. With no rule id, list the axes and the error-severity rules, nothing more.
