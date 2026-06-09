# BetterSelect — Selection Index (matchday board) redesign

Drop-in prototype of the redesigned **Selection landing page** — the screen that
lists all upcoming team selections by fixture and links into the builder.

## Files
- `BetterSelect Selection Index.html` — entry point. Theme tokens (`pb-*`), all CSS,
  and the script load order. Open it directly in a browser to run.
- `selection/data.js` — the shared squad pool + domain helpers (`roleLine`, `formOf`,
  availability map). Plain JS, loaded first.
- `selection/shared.jsx` — the atom kit (Icon, Avatar, Dot, Tag, FormChip, etc.).
- `selection/landing.jsx` — the index itself: the weekend's fixtures, the
  `summarize()` health/status deriver, compact rows, matchday grouping, search +
  status filters, and the expandable peek panel.

Runs on in-browser Babel (dev only). In your real app it's just normal JSX in the
Vite build.

## What it does
- **Dense matchday board** — one compact row per team (grade badge, opponent,
  time/venue, `n/11` count, worst health flag, status pill). Scales to ~15 teams.
- **Grouped by matchday** with sticky day headers + per-day attention counts.
- **Search + status filters** (All / Needs attention / In progress / Ready) with
  live counts and a "N of M" tally.
- **Click a row to open** the builder; **chevron to peek** — expands inline to
  balance, captain/keeper, flags, availability breakdown, and the full XI where a
  roster exists.
- Status is color-coded on the left edge. Light + dark themes, responsive to mobile.

## Wiring notes (for the real app)
- Replace the mock `FIXTURES` in `landing.jsx` with the real upcoming-fixtures +
  selection summaries. Each row only needs: squad, grade, opponent, home/away,
  venue, date/time, target, picked count, balance `{BAT,ALL,BWL,WKT}`, captain/keeper
  names, and an availability tally. A full `players[]` is optional — it powers the
  XI peek where present.
- `summarize()` derives status + flags from those fields; keep it or move the logic
  server-side.
- Point the row click + `Edit/Review/Build XI` CTA at `/admin/betterselect/select/:fixtureId`.
- Reuse your real `pb-*` tokens, the BetterSelect atom kit, and `availability.js`
  rather than the inlined copies here.
