# CutSlide renderer (Remotion)

One 1280x720 composition, `CutSlide`, renders a single cut slide
from data-only props. It is not one template per material: one
composition takes a list of material blocks.

## Props

- `cutId`: cut id (for example `s1c1`)
- `seconds`: cut length in seconds
- `preset`: layout preset name — `full`, `split_h` (left-right),
  `split_v` (top-bottom), `main_side`, `grid2x2`. Advisory: the
  boxes below carry the real layout.
- `blocks`: list of at most 4 blocks. Each block: `kind`, `box`
  `{x, y, w, h}` in 1280x720 pixels, `order` (paint order),
  `appear_s` (appear time in seconds), `reason` (why this block),
  optional `font_size`, and kind data:
  - `photo` / `generated` / `source_figure`: `file` (path under
    the public dir, aspect kept with contain fit)
  - `table`: `data.headers[]`, `data.rows[][]`,
    `data.reveal` (`rows` = one by one, `all` = at once)
  - `formula`: `data.lines[]` (TeX strings, KaTeX, one line at
    a time)
  - `chart`: `data.subtype` (`bar` or `line`), `data.labels[]`,
    `data.values[]` (checked numbers only)
  - `steps`: `data.items[]` (arrow chain, one at a time)
  - `text`: `data.lines[]`
- `onScreenText`: caption lines (at most 3)
- `guide`: Penn's style guide (`palette`, `fonts`)

Reveal pacing: table rows every 0.5 s, formula lines every
1.0 s, steps every 0.8 s. The code-side layout check
(`agents/_frame/schemas.py`, `REVEAL_STEP_S`) mirrors these
numbers; keep them in sync.

## Render one still

From this folder, after `npm install`:

```
npx remotion still CutSlide out.png --props="{\"cutId\":\"s1c1\",\"seconds\":20,...}" --public-dir=<assets> --frame=<seconds*30-1>
```

The still frame is the last frame of the cut, when all blocks
are visible. `render_slide` (agents/_frame/tools.py) runs this
per cut into the run folder.

## Licenses

- Remotion is proprietary software under its Free License (free
  for up to 3 people); it is NOT open source. Installed here via
  npm, never bundled into this repo.
- KaTeX is MIT licensed.
- React is MIT licensed.
