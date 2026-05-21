# Cricket Scorecards — S1 · S2 · S3

Three 1920×1080 full-match scorecards (broadcast / brutalist / dashboard) rendered from a single data shape.

## Files

| File | Purpose |
|---|---|
| `Cricket Scorecards.html` | Entry point — open in a browser |
| `app.jsx` | Wires data into the three scorecards + Tweaks toggle |
| `scorecards.jsx` | **The three scorecards** (S1 Broadcast, S2 Brutalist, S3 Dashboard) |
| `scorecard-data.jsx` | Sample data — 2023 ICC World Cup Final (India v Australia) |
| `fx.jsx` | Visual primitives — `ClubLogo`, `GrainSVG`, `Halftone`, `Stripes` |
| `design-canvas.jsx` | Pan/zoom artboard host — drop in your own canvas if you don't need it |
| `tweaks-panel.jsx` | Floating control panel for the dark/light toggle |

## Run

Open `Cricket Scorecards.html` in any modern browser. No build step — everything is in-browser Babel.

## Embed a single scorecard

The components are global. Once the scripts are loaded, mount any one directly:

```jsx
<SC1_Broadcast match={window.SAMPLE_FULL_MATCH} dark={true} />
<SC2_Brutalist match={window.SAMPLE_FULL_MATCH} dark={false} />
<SC3_Dashboard match={window.SAMPLE_FULL_MATCH} dark={false} />
```

Each renders at exactly **1920×1080** — wrap in a scaled container if you need it responsive.

## Data shape

See `scorecard-data.jsx` for the full schema. The key blocks:

```js
{
  meta: { competition, round, format, overs, venue, date, toss, result, series, motm },
  home: {
    name, short, color, monogram, total, overs, wickets, runRate,
    batting: [{ num, first, last, r, b, fours, sixes, sr, out, notOut?, didNotBat?, role? }, ...],
    extras: { total, b, lb, nb, wd },
    fow:    [{ score, wkt, bat, over }, ...],
    partnerships: [...],
    bowling: [{ first, last, o, m, r, w, econ }, ...],
  },
  away: { /* same shape */ },
}
```

Swap in your own match by replacing `window.SAMPLE_FULL_MATCH` in `scorecard-data.jsx`.
