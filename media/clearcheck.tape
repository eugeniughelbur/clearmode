Output clearcheck.gif

Set FontSize 16
Set Width 1100
Set Height 560
Set Padding 18
Set TypingSpeed 28ms
Set Theme "Catppuccin Mocha"

Hide
Type `cd ~/Projects/personal/clearmode && clear`
Enter
Sleep 1s
Show

Type `# a paragraph a model wrote`
Enter
Sleep 700ms
Type `python3 scripts/clearcheck.py tests/fixtures/bad.md --max-findings 5`
Sleep 400ms
Enter
Sleep 5s

Type `clear`
Enter
Sleep 400ms

Type `# same point, rewritten by a person`
Enter
Sleep 700ms
Type `python3 scripts/clearcheck.py tests/fixtures/good.md --max-findings 5`
Sleep 400ms
Enter
Sleep 5s
