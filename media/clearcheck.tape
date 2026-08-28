# Renders clearcheck.gif in this folder. Real terminal, real output, nothing staged.
#   brew install vhs && cd media && vhs clearcheck.tape

Output clearcheck.gif

Set FontSize 17
Set Width 1400
Set Height 580
Set Padding 22
Set TypingSpeed 26ms
Set Theme "Catppuccin Mocha"

Hide
Type `cd ~/Projects/personal/clearmode && clear`
Enter
Sleep 1s
Show

Sleep 1s
Type `# here is a paragraph a model wrote`
Enter
Sleep 1200ms
Type `head -4 tests/fixtures/bad.md`
Sleep 400ms
Enter
Sleep 6s

Type `clear`
Enter
Sleep 600ms

Type `# now score it`
Enter
Sleep 1200ms
Type `python3 scripts/clearcheck.py tests/fixtures/bad.md --max-findings 6`
Sleep 500ms
Enter
Sleep 11s

Type `clear`
Enter
Sleep 600ms

Type `# same points, rewritten by a person`
Enter
Sleep 1200ms
Type `python3 scripts/clearcheck.py tests/fixtures/good.md`
Sleep 500ms
Enter
Sleep 9s
