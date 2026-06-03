# Handoff: BetterIQ — premium analytics tier

## Overview
**BetterIQ** is the highest-paid tier of the Better ecosystem — a club's "analytics brain". It turns the scorecard data a club already holds (and live opponent form pulled from the same source) into broadcast-grade scouting, selection and trend analysis. The goal is for it to feel like the analytics suite of an international sports team, not a community-cricket admin tool.

This handoff covers the **full 8-screen module** plus the cross-cutting systems built on top of it (a global Season/Team filter context, a signature data-viz kit, a printable cheat sheet, and a live availability→best-XI loop).

It supersedes the original `docs/design_handoff_betteriq/` package — that was the brief; this is the realised design.

## About the design files
The files in `code/` are a **design reference** built as a React app that runs in the browser via Babel-standalone (so it opens with no build step). **They are not meant to be shipped as-is.** The task is to **recreate these designs inside the BetterStats codebase**, using its established stack:
- React + `react-router-dom` (the original `IQLayout.jsx` already imported `Link/useLocation/useNavigate` and `useAuth`).
- Tailwind with the existing **`pb-*` "Press Box" CSS variables** (preflight disabled — see Buttons note below).
- The module lives at routes under the BetterIQ section; reuse the app's existing auth/layout shell rather than the prototype's `IQLayout` if one already exists.

Treat the prototype components as the **specification of layout, tokens, behaviour and copy** — port them to real components, real routing, and real data wiring.

## Fidelity
**High-fidelity.** Colours, typography, spacing, radii, animations, chart geometry and copy are all final. Recreate the UI pixel-faithfully using the codebase's libraries. Where the prototype hand-rolls an SVG chart (radar, wagon-wheel, area, gauge, heatmap), port the geometry exactly or swap for an equivalent in the app's chart lib while preserving the look.

---

## Tech the prototype uses (and how to map it)
| Prototype | Map to in BetterStats |
|---|---|
| Babel-standalone, global components via `Object.assign(window,…)` | Real ES modules / React components |
| In-app `route` state + `switch` in `App.jsx` | `react-router-dom` routes |
| `iq/iq-theme.css` `pb-*` variables | The existing Press Box theme tokens (extend, don't duplicate) |
| `useTweaks` (theme/font/card toggles) | Dev-only; not required in prod unless you want the theme switch |
| `IQ_*` mock objects in `data.jsx` / `data2.jsx` | Real API/query layer — shapes documented below |
| Tailwind via CDN | The app's existing Tailwind build |

---

## Design system / tokens

### Identity
- **Module accent ("the brain"): violet.** Deep `#5b46d6`, core `#8b7cf6`, bright `#b3a4ff`. This is BetterIQ's signature, distinct from club green. Exposed as `--pb-accent` within `.iq-root`.
- **Results stay semantic, never themed away:** win `#1fd693`, loss `#ff6363`, draw/amber `#f5b542` (dark). Light: win `#0fae73`, loss `#e0484b`, amber `#d99412`.
- **Chart series:** runs/green `#1fd693`, wickets/blue `#4f9dff`, amber `#f5b542`, pink `#f472b6`, cyan `#22d3ee`.

### Surfaces (dark — default)
```
--pb-bg #07090f   --pb-bg2 #04050a
--pb-surface #0d1019   --pb-surface2 #141926   --pb-surface3 #1b2233
--pb-hairline #1b2130   --pb-hairline2 #2a3346
--pb-text #eef0f6   --pb-dim #9aa1b4   --pb-faint #646b80   --pb-faintest #3d4356
```
### Surfaces (light)
```
--pb-bg #f3f3f6   --pb-surface #ffffff   --pb-surface2 #f4f5f8   --pb-surface3 #eceef3
--pb-hairline #e6e7ec   --pb-hairline2 #d6d8e0
--pb-text #13151c   --pb-dim #565d70   --pb-faint #8a90a2   --pb-faintest #b4b9c6
--pb-accent #6d5de6 (light variant)
```
Theme flips via `[data-theme="dark|light"]` on the `.iq-root`. A subtle violet radial glow sits behind the page (`--iq-glow`).

### Typography
- **Display / headlines / big numbers:** **Archivo** (variable; the prototype uses weight 800, slight expand `font-stretch:112%`, `letter-spacing:-0.015em`, `line-height:0.98` for the broadcast "headline" class). Body also Archivo.
- **Labels, eyebrows, figures:** **JetBrains Mono**. Eyebrow = 10px, uppercase, `letter-spacing:0.22em`, `--pb-faint`.
- All numbers use `font-variant-numeric: tabular-nums`.
- Font scale floor: card titles 17px, body 13–14.5px, big hero numbers `clamp(34px,4vw,52px)`.

### Shape & motion
- Radius: cards `14px`, controls `10px`, chips `6px`.
- Card shadow only in "glass"/elevated mode; default cards are hairline-bordered.
- Motion: entrances `iq-rise` (10px up + fade, 620ms `cubic-bezier(.22,.61,.36,1)`), numbers count up (`CountUp`, easeOutCubic ~1s), charts draw in (stroke-dashoffset / scale). **All gated so reduced-motion and print show the end state.**

### Buttons — IMPORTANT
Tailwind **preflight is disabled**, so a bare `<button>` inherits the native grey face. The prototype resets this in `iq-theme.css` (`.iq-root button { background:transparent; border:none; … }`). In the real app, ensure every button sets an explicit background **or** a global button reset exists. This was a real bug we fixed twice.

### Cricket conventions (also in project CLAUDE.md)
- **Averages always render to 2 decimals** (`52.30`, `16.20`). Helper `a2(v)=Number(v).toFixed(2)`.
- Dense tables may use `runs@avg` / `Nw@avg`; cards/lists use a clean two-line figure (value + unit, then `avg X.XX`).

---

## Global systems

### 1. Navigation & shell (`Layout.jsx`)
Left sidebar, grouped:
- **Overview**
- **Scout the opposition** — Match preview · Opposition club · Opposition player
- **Know your club** — Selection · Player trends · Team analysis · Match review

Sticky 64px header: page eyebrow + title (left), page actions + theme toggle + user chip (right). Active nav item: violet text, 12%-tint pill, 3px left bar. Mobile: drawer.

### 2. Global Season + Team context (`Context.jsx`) — required on all applicable pages
A **sticky filter bar directly under the header** (`top:64px`, blurred surface, bottom hairline). It shows `Showing` + a **Team** pill + a **Season** pill, and the active filters persist across pages via a shared `ctx` object in `App`.

`ctx` shape:
```js
{ team: '1st Grade',
  season: { mode: 'single'|'range', from: '2024/25', to: '2024/25' } }
```
- **Team picker:** dropdown of `1st/2nd/3rd Grade`, `All grades`.
- **Season picker:** a popover with a **Single | Compare** segmented toggle and a **season timeline** — a horizontal track of season nodes (oldest→newest, labels `20/21…24/25`). Single mode: click one node. Compare mode: click two nodes to set a range (span highlights violet between the endpoints) + quick presets ("This + last", "Last 3", "All seasons"). The pill label reads `2024/25` (single) or `2023/24 → 2024/25` / `All seasons` (range), with a "Comparing N seasons" tag.
- **Per-route capability** comes from `ROUTE_FILTERS[route]`:
  - `overview` team + single-season
  - `preview`, `selection`: team + **locked "current season" chip** (these are inherently this-week)
  - `opposition`, `opposition-player`, `trends`, `team`, `review`: team + **season range** allowed
- **Range-aware screens recompute:** Player trends shows a runs/avg delta over the range and dims out-of-range seasons; Team analysis shows a "win rate over time" comparison across the span; Overview reflects the chosen season label. Single-season pages show the locked chip.

Pass `ctx` into any new screen that should respect the filters.

### 3. Signature data-viz kit (`viz.jsx` + chart atoms in `ui.jsx`)
Port these exactly — they're what make it feel broadcast-grade:
- **Radar** — 6-axis player profile vs a grade-average baseline ring (dashed at 50). Optional second overlaid series for compare. Batter axes: Volume, Average, Strike rate, Consistency, Conversion, Match impact. Bowler axes: Wickets, Average, Economy, Strike rate, Big hauls, Top-order. Values normalised 0–100. Animates by scaling from centre.
- **WagonWheel** — scoring-zones wheel (batter's view, 8 sectors: Straight, Cover, Point, Third man, Fine leg, Sq leg, Mid-wkt, Long-on). Wedge radius/opacity ∝ % of runs; strongest sector solid. Scout-entered metadata. Pitch marker in centre.
- **AreaChart** — gridded line+area with y-axis ticks and x labels; draws in.
- **Heatmap** — bowler×batter dismissal matrix (in `ui.jsx`); cell intensity = dismissals, vertical batter labels, sticky bowler column.
- **Gauge** / **DonutStat** — win-rate arc / percentage ring with centred count-up figure.
- **PhaseStrip** — innings phases (Powerplay/Middle/Death) as a proportional bar + 3 stat tiles. **Always label phase splits as scorecard-level estimates** (no ball-by-ball data exists).
- **Sparkline, Bar, SplitBar, StackedBar, ResultPills, CountUp, Delta** — supporting atoms.

### 4. Atoms (`ui.jsx`)
`Card` (eyebrow/title/right slot), `Stat`, `Tag` (tones: accent/win/amber/red/faint), `Btn` (primary/soft/ghost), `Segmented`, `Tabs` (underline), `Search`, `Initials`, `KV`, `PageIntro`, `Note`, `Icon` (inline SVG set). Keep the eyebrow/title rhythm — it carries the whole system.

---

## Screens

> Data shapes for every screen are in `code/iq/data.jsx` and `code/iq/data2.jsx`. Treat those object shapes as the API contract.

### 1. Overview (hub) — `Overview.jsx`
A true hub that surfaces the best insight from every area.
- **Hero** (violet accent card, 2-col): left = positioning statement + "Scout <next opp>" / "Match preview" CTAs; right = next fixture (date, H/A, venue) + head-to-head W/L + recent form pills.
- **Club pulse row:** `ClubPulse` card (win-rate **DonutStat**, last-10 **ResultPills**, net runs, **AreaChart** points trajectory) + a stacked `LastResult` card (links to Match review) + `WeeklyLoop` (Preview→Select→Match day→Review, each with state: ready/needs-you/upcoming/after-match, clickable to its route).
- **Scout next opponent:** 4 fixture cards (click → full dossier).
- **Club MVPs** (0–100 blended impact, ranked bars) + **Form movers** teaser + clickable **capability** cards.

### 2. Match preview — `Preview.jsx`
A 60-second pre-game one-pager (instant data only). Fixture bar with **Cheat sheet** + **Full scout** actions. "The lean" (4 numbered takeaways), ladder position, head-to-head, their danger players + our edge (clean two-line `PerfStat`s), and a par-score callout. Links to the full scout and to Selection.

### 3. Opposition club / Scout (flagship) — `Scout.jsx` + `KeyPlayers.jsx`
Picker (upcoming fixtures + searchable opponent list) → two-phase dossier:
- **CommandStrip:** win-rate **Gauge**, all-time W/L/D, recent form, last meeting.
- **GamePlan** (one-liner + remove-early/see-off/target tiles + watch/edge).
- **KeyPlayersCard ×2** — the signature "flick-through" showcase (segmented player switch → featured count-up figure, draw-in sparkline, analyst read, risk/confidence). One for danger batters, one for bowlers.
- **Threat radars** (top bat + top bowl), **our record vs them**, **by-venue**, **bowler×batter Heatmap** (matrix/list toggle), how-they-win/lose, dismissal **StackedBar**, partnership "wobble" bars, innings-phase **PhaseStrip** (estimate), full squad tables.

### 4. Opposition player — `OppPlayer.jsx`
Club → searchable squad list → profile: **Radar**, **WagonWheel** scoring zones (scout-entered, with notes), batting/bowling stat clusters, dismissal breakdown, record vs us, and **editable scouting tags** (hand, bowl type, role, keeper, danger flag, free-text notes).

### 5. Selection — `Selection.jsx` (live availability→best-XI loop)
Ties to BetterSelect. **Availability manager**: every squad player has a tri-state toggle (In / ? / Out). Changing it **rebuilds the best-available XI instantly** via `buildXI()` — a role-template selection (1 keeper, 3 bowlers, 2 all-rounders, 5 bats, top-up by value) over the available+optional-maybe pool, respecting eligibility. Shows: verdict, the ordered XI with "In" badges, coming-in/dropping-out diff vs the saved XI, a live **balance** readout (bats/all/bowlers/pace-spin/keeper/openers) and dynamic warnings (e.g. <2 spinners), plus "Send XI to BetterSelect". Selection logic (scores, spinner set, balance rules) is documented in the file header.

### 6. Player trends — `Trends.jsx`
Form movers surfaced first (rising/sliding bat & bowl with **Delta**), emerging players, then a player deep-dive with tabs: **Trajectory** (AreaChart of runs/season + table; range-aware delta + highlight), **Deep dive** (player **Radar**, reliability percentiles, milestones, conversion, selection value), **Compare** (pick two players → overlaid radar + head-to-head stat table, stronger value highlighted).

### 7. Team analysis — `Team.jsx`
The opposition lens pointed at us. Tabs: Overview (how we win/lose, bat-first vs chase, par + score bands, by venue; **when a season range is active, a "win rate over time" comparison card**), Batting, Bowling, Players.

### 8. Match review — `Review.jsx`
Recent-games list → auto post-match read: scoreline, the turning point (synthesised), top performers, best partnership, key collapse. Labelled as scorecard-derived.

### Cheat sheet (overlay) — `CheatSheet.jsx`
Opened from Preview/Scout. A self-contained **landscape one-pager in a fixed LIGHT palette** (independent of app theme) so **Print / Save PDF** is clean — print isolation via `@media print` rules in `iq-theme.css` (`.iq-print-area` visible, everything else hidden, `@page { size: landscape }`). Sections: H2H strip, the plan, three columns (Get these out / New-ball threat / Our edge), toss footer.

---

## State management
- **`ctx`** (season + team) — app-level, persists across routes; pass to season/team-aware screens. Drives recomputation on Trends/Team/Overview.
- **Route** — use `react-router`. Prototype also tracks a transient `selection` (which opponent the Scout is showing) and `cheat` (overlay open).
- **Selection screen** — local `availMap` (id→status), `includeMaybe`, `sent`; XI + balance are `useMemo` derived. In production, seed `availMap` from BetterSelect and write changes back.
- **Scout** — two-phase: instant head-to-head, then a short "building dossier" state before the deep data (mock ~1.7s; replace with the real fetch).
- Theme/card/font are dev "tweaks" only.

## Data / API contract
All screens read from the `IQ_*` mock objects — **these object shapes are the contract** for the real query layer:
`IQ_UPCOMING, IQ_OPPONENTS, IQ_REPORT` (head_to_head, our_performers, last_meeting, venues, matchups), `IQ_DOSSIER` (game_plan, danger_batters/bowlers, how_they_win/lose, dismissal_breakdown, partnerships, batting/bowling, coverage), `IQ_MVP`, `IQ_SQUAD`, `IQ_PREVIEW`, `IQ_SELECTION`, `IQ_TRENDS`, `IQ_TEAM`, `IQ_REVIEW_GAMES`, `IQ_GAME_REVIEW`, `IQ_OPP_PLAYER`, `IQ_CLUB_FORM`, `IQ_VIZ` (radar/zones/phases). Data ceiling is **scorecard-level — no ball-by-ball**; strike rates, economies and phase splits are innings-level estimates and must be labelled as such.

## Assets
None external beyond Google Fonts (**Archivo**, **JetBrains Mono**) and inline SVG icons (`ICONS` map in `ui.jsx`). No raster assets. Use the app's existing icon set if preferred, matching stroke weight ~1.6.

## Files (in `code/`)
- `BetterIQ.html` — entry; font + Tailwind config (maps `pb-*` to CSS vars) + script load order.
- `iq/iq-theme.css` — all tokens, themes, motion, print rules, button reset.
- `iq/ui.jsx` — atoms + chart atoms (Heatmap, Gauge, Sparkline, CountUp, Tabs, etc.).
- `iq/viz.jsx` — Radar, WagonWheel, AreaChart, PhaseStrip, DonutStat.
- `iq/Context.jsx` — Season/Team filter bar, season-range picker, `ROUTE_FILTERS`.
- `iq/Layout.jsx` — sidebar + header shell.
- `iq/data.jsx`, `iq/data2.jsx` — mock data (API shapes).
- `iq/Overview.jsx`, `Preview.jsx`, `Scout.jsx`, `KeyPlayers.jsx`, `OppPlayer.jsx`, `Selection.jsx`, `Trends.jsx`, `Team.jsx`, `Review.jsx`, `CheatSheet.jsx` — the screens.
- `iq/App.jsx` — router + ctx + tweaks wiring.
- `iq/tweaks-panel.jsx` — dev theme/font toggles (optional in prod).

## Build order (suggested)
1. Tokens + button reset + Archivo/JetBrains Mono.
2. Atoms (`ui.jsx`) then viz (`viz.jsx`) — everything depends on these.
3. Shell + routing (`Layout.jsx`) and the **global ctx** (`Context.jsx`) early, since screens read it.
4. Screens in value order: Overview → Scout → Preview → Selection → Trends → Team → Opposition player → Review.
5. Cheat sheet overlay + print CSS last.
6. Swap mock `IQ_*` for real queries, keeping the documented shapes.
