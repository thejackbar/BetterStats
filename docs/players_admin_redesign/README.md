# BetterStats — Players admin (redesign prototype)

A high-fidelity, interactive prototype of the redesigned **Players** admin page,
built in the existing Press Box design language (Geist + JetBrains Mono, `--pb-*`
tokens, brand-green accent). Open `BetterSelect Players.html` in a browser — no build step.

## What it addresses
- **Alphabet breakdown** — range tabs (A–E · F–J · K–O · P–T · U–Z) with live counts,
  sticky per-letter headers, and an A–Z jump rail that auto-switches range and scrolls.
- **Prominent scrollbar** — high-contrast, always-visible (a "subtle" option is in Tweaks).
- **No PHQ / UUID clutter** — replaced with a useful role · batting/bowling line, a squad
  tag, and Overseas / Inactive badges.
- **Player modal** — the detail view kept as-is, plus prev/next player navigation
  (arrows or ← → keys) and a position counter.

## Files
- `BetterSelect Players.html` — entry: theme tokens, all CSS, script load order.
- `players/data.js` — ~256 mock players spanning A–Z + domain helpers. **Reference data
  shape only** — wire to the real roster on build.
- `players/ui.jsx` — shared atoms (Icon, Avatar, Btn, Seg, form inputs, Toggle).
- `players/modal.jsx` — the player detail modal.
- `players/app.jsx` — page shell, list, alphabet grouping, jump rail, Tweaks panel.
- `players/tweaks-panel.jsx` — the in-page Tweaks controls (prototype-only).

## Notes for production
- Runs on in-browser Babel (dev only) — in-app this is just normal JSX in the Vite build.
- Default config: Tabs + rail · regular density · prominent scrollbar · role line + squad
  tag on · dark. The Tweaks panel is a prototype affordance; drop it when porting.
- The modal renders via a portal, so the theme tokens live on `:root` / `<html data-theme>`
  (not on an inner wrapper) — keep that if you lift the markup.
