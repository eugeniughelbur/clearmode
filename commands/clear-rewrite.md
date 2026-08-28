---
description: Rewrite text to pass CLEAR-100. Plain words, human voice, real structure, no filler. Runs the checker in a loop until the score clears the gate, then shows the before and after.
---

# /clear-rewrite

Rewrite until it passes. Show the work.

## Steps

1. Run `/clear-check` first. You need the baseline score before you touch a word.
2. Fix in this order. The order matters, because each pass makes the next one cheaper.

   1. **Cut.** Delete every sentence that fails the delete test (D1, D3, D4). Do this before rewriting anything. Half the findings disappear here.
   2. **Unslop.** Replace every H-axis hit with the specific thing it stood in for. If nothing specific is behind it, the sentence was already deleted in step 1.
   3. **Plain.** Split long sentences. Swap long words for short ones. Gloss each term of art once. Put the actor before the verb.
   4. **Structure.** Turn parallel items into lists, sequences into numbered steps, comparisons into tables. Break walls.
   5. **Rhythm.** Read it out loud. Put a short sentence next to a long one. This is the last pass, never the first.

3. Re-run the checker. Repeat from the highest remaining severity. Stop at the gate, or after four passes.
4. If four passes do not clear the gate, say so and name what is blocking. Do not fake the score.

## Output

- The rewritten text in full, in a fenced block, ready to paste.
- One line: `before X/100 -> after Y/100`, with the axis that moved most.
- A short list of what you cut and why. Cuts are the part a user will want to argue with.

## Hard limits

- Never change a claim, a number, a name, or a link. Clarity work only. If a claim is wrong, say so separately.
- Never touch code, code blocks, quoted material, or another person's words.
- Never remove a technical term that is the subject. Gloss it once instead.
- Never add a claim the source did not make to satisfy the density axis.
