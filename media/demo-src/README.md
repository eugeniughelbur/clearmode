# Demo source

`../clearcheck.gif` renders from `index.html`, a HyperFrames composition (HTML plus a paused GSAP timeline, captured frame by frame). Nothing generative, so the demo is reproducible and costs nothing to rebuild.

Needs Node 22 and ffmpeg.

## The font is not in this repo

The composition letters in Bradley Hand, which is a licensed Apple and ITC font. It is not redistributable, so it is gitignored. To rebuild the demo, drop your own copy at `assets/font/bradley.ttf`, or edit the `@font-face` rule in `index.html` to any hand-drawn font you have a licence for. The rendered GIF is unaffected.

```bash
npx --yes hyperframes@0.6.114 render --format gif --fps 15 --gif-loop 0 -o renders/clearcheck.gif
cp renders/clearcheck.gif ../clearcheck.gif
```

Everything on screen is real. The sentences are lifted from `tests/fixtures/bad.md` and `tests/fixtures/good.md`, the underlines mark phrases the checker actually flags, and the badge numbers are the two files' real scores: 41 and 98. If the rule pack changes any of that, update the composition.
