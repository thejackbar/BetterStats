# Handoff: BetterSelect → Votes redesign

## Overview

A glow-up of the **Votes** section of BetterSelect (Brownlow-style best-player
vote collection) plus the public voting page it feeds. It replaces the current
three-tab admin screen and the step-by-step player ballot.

The brief was: simple and slick at the same time, easy to share with the team,
clean leaderboard views, quick voting — and *keep every piece of functionality
that exists today*. This is a replacement for club spreadsheets, so legibility
and navigation matter more than novelty.

Three things change:

1. **Games hub** (was the "Fixtures" tab) — composable filters (status × grade ×
   round × search), per-fixture ballot progress, multi-select bulk open/lock/nudge,
   and one sharing surface.
2. **Leaderboard** — podium for the top three, rank movement, a form sparkline, a
   cumulative "race" chart, and a full-screen **presentation mode** that reveals
   the count one round at a time for awards night.
3. **Public ballot** — one screen instead of a stepper: three slots (3/2/1) above
   the team list, tap three names, submit.

Everything is theme-token driven, so **light and dark mode both work**, and a
club's white-label accent still applies (the module override to BetterSelect blue
is unchanged).

## About the design files

The files in `design/` are **design references created in HTML** — prototypes
showing the intended look and behaviour. They are not production code.

The files in `code/` **are** intended as production starting points: they are
written as React + Tailwind against this repo's existing conventions
(`frontend/src/pages/admin/betterselect/`), reuse the existing atom kit
(`./ui.jsx` → `Btn`, `Icon`, `Chip`, `Search`, `Segmented`, `Avatar`), the
existing contexts (`AuthContext`, `ToastContext`), the existing `api` client and
the existing `pb-*` Tailwind colour tokens. Drop them in, then wire the new API
fields described in `API_CONTRACT.md`.

Read `API_CONTRACT.md` first — several screens need new (additive) response
fields, and three new endpoints.

## Fidelity

**High fidelity.** Colours, type sizes, spacing, radii and states are final and
listed below. Recreate pixel-for-pixel using the existing token system — do not
introduce new hex values beyond the two noted in *Design tokens*.

---

## Screens / views

### 1. Games hub — `?tab=hub` (default)

**Purpose:** answer "what needs me?" in one glance, then act on it in bulk.

**Layout** (max-width 1400px, inherited from `BetterSelectLayout`'s `<main>`):

1. **Counter strip** — 4 equal cells, `grid-cols-4` with `gap-px` on a
   `bg-pb-hairline` parent inside a `rounded-xl border` (so the dividers are
   hairlines, not borders). Each cell `px-5 py-3.5`.
   - Label: JetBrains Mono 10px, uppercase, `tracking-wide2`, `text-pb-faint`
   - Value: 26px/700, `tabular-nums`, coloured per meaning
     (open = `--pb-positive`, awaiting = `--pb-amber`, others = `--pb-text`)
   - Sub: 12px `text-pb-faint`
   - Content: `OPEN NOW 2 games` · `BALLOTS THIS ROUND 11 of 22 eligible` ·
     `AWAITING TEAM LIST 1 games` · `ROUNDS COUNTED 8 of 9`
2. **Filter row** — wraps, `gap-x-3.5 gap-y-2.5`:
   - Status: segmented control, `p-[3px]` on `bg-pb-surface2`, `rounded-[9px]`,
     `border-pb-hairline`. Buttons `px-2.5 py-1`, 12.5px/600, active
     `bg-pb-accent/15 text-pb-accent`, inactive `text-pb-faint`. Each carries a
     mono 10.5px count at 70% opacity. Options: **All · Open · Needs team · Closed**
     (Closed covers `closed` + `locked`).
   - 1px × 22px `bg-pb-hairline` divider.
   - Grade: existing `<Chip>` pills — `All grades` then one per grade.
   - Right-aligned: `<Search>` (210px, placeholder "Opponent or player…"), round
     select, season select. Selects: `h-[38px] px-2.5`, 13px, `bg-pb-surface2`,
     `rounded-[9px]`, `focus:border-pb-accent`.
3. **Bulk action bar** — only when ≥1 fixture is selected. `px-5 py-2.5`,
   `bg-pb-accent/10`, bottom border `border-pb-accent/25`. Left: "N games
   selected" 13px/600 accent. Buttons `px-2.5 py-1 rounded-lg` 12.5px:
   **Open voting** (solid `--pb-positive`, text `--pb-bg`), **Lock voting** and
   **Nudge non-voters** (`bg-pb-surface2` + `border-pb-hairline2`). Right:
   "Clear" `text-pb-faint`.
4. **Fixture table** — `rounded-xl border`, rows separated by hairlines. Grid:
   `36px | minmax(220px,1fr) | 140px | 210px | 120px | 96px`, `gap-4`,
   `px-5 py-3.5`, row hover `bg-pb-surface2/60`. Collapses to
   `36px | 1fr` under `md` (grade / progress / closes hidden).
   - **Checkbox**: 18px, `rounded-[5px]`. Unchecked `bg-pb-surface2` +
     `1px solid --pb-hairline2`; checked solid `--pb-accent` with a 12px
     `Icon name="check"` at `strokeWidth 3` in `--pb-bg`.
   - **Fixture**: "Round 9 · vs Melville" 14.5px/600 (`@` for away, matching the
     existing `home_away` convention); below, `Sat 7 Feb` 12px `text-pb-faint`.
   - **Grade**: 13px `text-pb-dim`.
   - **Ballots in**: `<BallotProgress>` — 6px bar, `rounded-full`,
     `bg-pb-surface2` track, fill coloured by completion (100% `--pb-positive`,
     ≥50% `--pb-accent`, else `--pb-amber`), 300ms width transition; then
     "8/11" mono 12px `tabular-nums`, 52px right-aligned.
   - **Closes**: 12.5px, `--pb-text` when open else `--pb-faint`.
   - **Status**: `<VoteStateBadge>` — mono 10px/700, `px-2 py-0.5 rounded-full`,
     `background: color-mix(in srgb, <token> 15%, transparent)`, text = token.
     OPEN `--pb-positive` · CLOSED `--pb-faint` · LOCKED `--pb-red` ·
     NO TEAM `--pb-amber` · UPCOMING `--pb-faintest`.
5. **Share + chase** — two cards side by side (share `flex-1`, chase 300px),
   stacking under `lg`.

### 2. Share panel (`ShareVotePanel`)

**Purpose:** get the link to the team in one tap, over the channel the club
already uses.

- Card: `pb-card px-4 py-4`. Title "Share this week's vote" 14.5px/700; right,
  the current scope in mono 10px uppercase `text-pb-faintest`.
- 5 target buttons, wrapping, `gap-2`: `px-3.5 py-2.5 rounded-[10px]`, 13px/500,
  `bg-pb-surface2` + `border-pb-hairline2`, hover `border-pb-accent`. Each has a
  7px dot: WhatsApp `--pb-positive`, SMS `--pb-accent`, Copy/QR `--pb-dim`,
  Post to socials `#EC4899` (the existing BetterSocials brand accent).
- **Editable message preview**: `rounded-[10px] border-dashed border-pb-hairline2`
  on `bg-pb-bg`, `px-3.5 py-3`. Mono 9.5px uppercase caption
  "Message preview · editable"; textarea 13.5px `leading-relaxed text-pb-dim`.
  Default copy:
  > Votes are open for **Round 9 v Melville**. 30 seconds, no login — pick your
  > 3, 2 and 1.
  > \<link\>
  > Closes Sat 14 Feb.
- QR (existing `qrcode` dependency): 96px, `rounded-lg bg-white p-1.5`.
- Footnote with an `Icon name="info"`: "Every link is pre-filtered to the team and
  round you're looking at, so nobody hunts through other grades."

**Link composition** (`voteUrl`) reuses the deep-link params the public page
already understands: `?fixture=` › `?team=` + `?round=`. Nothing new server-side.

If `settings.enabled` is false the panel collapses to the existing amber warning
instead of showing dead buttons.

### 3. Outstanding voters (`OutstandingVoters`)

- `pb-card`, title "Still to vote" 14.5px/700, sub "R9 v Melville · 3 of 11".
- Rows: existing `<Avatar size={28}>`, name 13.5px, mono 10px uppercase channel
  (`SMS` / `WHATSAPP`), separated by hairlines.
- Footer button full width `py-2.5 rounded-[10px]`, 13px/600, solid
  `--pb-amber` with `--pb-bg` text: "Nudge all 3".
- Empty state: "Everyone's in. Nice." in `--pb-positive`.

### 4. Leaderboard — "The Race" (`?tab=leaderboard`)

**Purpose:** read the count at a glance and see who is coming.

- **Header row**: "Best Player Count" 19px/700, hairline divider, grade chips,
  then right-aligned "AS AT" + through-round select + season select +
  **Presentation mode** button (`h-[34px] px-3.5 rounded-[9px]`, 13px/600, solid
  `--pb-accent`, text `--pb-bg`).
- **Podium**: 3 cards, `flex-1`, `gap-3.5`, stacking under `md`.
  - `rounded-[14px] p-[18px]`;
    `background: linear-gradient(160deg, color-mix(in srgb, <place> 9%, var(--pb-surface)) 0%, var(--pb-surface) 70%)`;
    `border: 1px solid color-mix(in srgb, <place> 32%, transparent)`.
  - Place accents: 1st `--pb-amber`, 2nd `--pb-dim`, 3rd `#c98b4a`.
  - Top row: place label mono 11px/700 `tracking-wide3`; right, movement
    `▲ 1` / `▼ 2` / `—` mono 11px (`--pb-positive` / `--pb-red` / `--pb-faintest`).
  - Body: 44px initials circle, name 19px/700 `tracking-tight`, grade 12px
    `text-pb-faint`; right, points **38px/800** `tabular-nums` in the place accent
    with a mono 9.5px "POINTS" caption.
  - Footer above a place-tinted top border: 3s / 2s / 1s / RAW — mono 9.5px
    labels, 15px/600 values.
- **Standings table**: grid
  `44px | minmax(190px,1fr) | 104px | 72px | 56px | 56px | 56px`, `gap-3`,
  `px-3.5 py-3`, hairline top borders. Top three rows get
  `color-mix(in srgb, var(--pb-amber) 3.5%, transparent)`.
  - Rank mono 13px/600 (amber for top 3, else `--pb-faint`), plus a 9px ▲/▼/—
    movement glyph. `=` for a tie (from `standing.tied`).
  - Player cell: 26px initials circle, name 14px/500 with
    `flex-1 min-w-0 truncate`, then a mono 9.5px grade tag that must be
    `shrink-0` — **this is the one place the layout is fragile**: without
    `min-w-0` on the name and `shrink-0` on the tag, long names collapse to one
    character.
  - Form sparkline: 5 bars, 8px wide, `rounded-[2px]`, height
    `4 + (v / max) * 18` px, colour
    `color-mix(in srgb, var(--pb-accent) 35–100%, transparent)`, empty rounds
    `--pb-hairline`.
  - Points 17px/700 `tabular-nums` (leader in `--pb-amber`); vote counts mono 13px.
- **Race card** (344px, `pb-card`): title 14.5px/700 + mono 10px
  "CUMULATIVE POINTS", a one-line caption, then `<RaceChart>` — a hand-rolled
  inline SVG (368 × 190 viewBox, plot inset x 34→356, y 12→168): 4 horizontal
  `--pb-hairline` gridlines with mono 9px labels, one polyline per player
  (leader 2.4px, others 1.6px), a 3.5r dot at the head of each line, and R1…Rn
  mono 9px ticks. Legend below: 10px × 3px colour swatch + surname, 12px
  `text-pb-dim`. Series colours come from `BRAND.chart_series`:
  `--pb-accent`, `--pb-positive`, `--pb-amber`, `#a855f7`, `#06b6d4`.
  Under it, a "what just happened" block: last round's label + fixture, then each
  scorer as a 22px `rounded-md bg-pb-accent/15 text-pb-accent` mono points chip +
  name.

**Why inline SVG and not Recharts:** five short polylines, no tooltip, no axis
formatting. Recharts would pull a chart runtime into a card that renders 40 nodes.

### 5. Leaderboard — Awards Night (presentation mode)

**Purpose:** run the count on a projector at the awards night, round by round.

- `fixed inset-0 z-50`, **forced dark** regardless of the app theme. The stage
  sets its own `--pb-*` dark values **and its own `color`** — `color` is
  inherited, so without re-declaring it every uncoloured child renders in the
  light theme's near-black text on the dark stage. (This was a real bug in the
  prototype; don't repeat it.)
- Header: club mark (30px, accent, `--pb-bg` text) + club name 15px/700 + mono
  10px `tracking-wide3` "BEST PLAYER 2025/26 · 1ST GRADE". Right: one 7px dot per
  counted round (revealed = `--pb-amber`, else `--pb-hairline`), "ROUND 8 OF 9"
  mono 11px, **Reveal next round** button (solid `--pb-amber`, `#07090f` text),
  and Exit.
- Left column (430px, vertically centred):
  - mono 11px `tracking-wide4` `--pb-amber` "LEADING THE COUNT"
  - Name **64px/800**, `leading-none tracking-tighter`
  - Points **84px/800** in `--pb-amber`, beside a mono "POINTS" caption and
    "+3 clear · 14 threes"
  - Three stat cells (`gap-px` on `--pb-hairline`, `rounded-[10px]`): THREES ·
    ROUNDS VOTED · MARGIN, mono 9.5px labels, 20px/700 values
- Right column: mono 10px "THE COUNT · AFTER ROUND 8", then up to 9 rows,
  `gap-1.5`, `px-4 py-2.5 rounded-[11px]`:
  - Row 1: `linear-gradient(90deg, color-mix(in srgb, var(--pb-amber) 14%, transparent) 0%, transparent 100%)`
    + `color-mix(… 35%)` border; rows 2–3 `--pb-surface` + `--pb-hairline`;
    rest transparent.
  - Rank mono 15px/700 (amber for 1st). Name 22px (1st) / 19px (2nd–3rd) / 17px,
    weight 600. Optional `+3` gain pill in `--pb-positive` at 14% tint.
    Points 26px (1st) / 21px, weight 800, `tabular-nums`.
- **Keyboard:** → or Space reveals the next round, ← goes back, Esc exits. Shown
  as a mono 10px hint.
- Each reveal re-fetches `votesLeaderboard({ through_round })` — the numbers on
  the projector are always the real replayed count, never interpolated.

### 6. Public ballot — one screen (`/vote/:token`)

**Purpose:** three taps and done, on a phone, standing in a car park.

Flow is unchanged: games list → identify (name + last-4 PIN, or type your name
if the club allows non-players) → ballot → done. Only the ballot step changes.

- **Slots row**: 3 equal buttons, `gap-2`, `rounded-xl px-2.5 py-2.5`.
  - Empty & next: `bg-pb-surface` + `1px dashed var(--pb-accent)`
  - Empty & later: same but `dashed var(--pb-hairline2)`
  - Filled: `color-mix(in srgb, var(--pb-accent) 12%, transparent)` +
    `1px solid color-mix(… 45%)`
  - Label mono 10px/700 "3 VOTES"; value 13.5px/600 truncated, or "Tap a name"
    in `--pb-faintest`.
  - Tapping a filled slot clears it.
- **Team list**: `rounded-xl border`, hairline-separated rows `px-4 py-3` — 44px+
  hit targets throughout. Each row: 32px initials circle (ring + text turn
  `--pb-accent` when chosen), name 15.5px/500, and a 26px right-hand marker —
  `1px dashed --pb-hairline2` showing the *next* value it would take, or solid
  `--pb-accent` with the assigned value in `--pb-bg`. Chosen rows get a 7%
  accent wash. Tapping a chosen name clears it.
- **Submit**: full width `py-4 rounded-2xl`, 15.5px/700. Incomplete →
  `bg-pb-surface2 text-pb-faintest`, label "Pick 2 more". Complete → solid
  `--pb-accent`, "Submit my votes" (or "Update my votes" if a ballot exists).
- Footnote 11.5px `--pb-faintest`: "Voting as Tom Fletcher. You can change your
  votes while voting stays open."
- The old separate review screen is gone — the slots row *is* the review.
- Header is now a compact horizontal lockup (40px logo + club name + "BEST-PLAYER
  VOTES" caption + "Not you?"), replacing the centred 64px stack, so the ballot
  starts above the fold on a small phone.

**Ballot length is still driven by `ballot_values`.** A 5-4-3-2-1 club gets five
slots; the row wraps. A single best-player club gets one slot.

## Interactions & behaviour

| Trigger | Behaviour |
| --- | --- |
| Status pill | Client-side filter so counts stay stable while flicking; grade/round/search hit the API |
| Grade chip | Sets `grade_id`, clears `round_key` (rounds are grade-scoped — existing rule) |
| Row checkbox | Toggles into `selected[]`; bar appears at ≥1 |
| Open/Lock voting (bulk) | `POST /api/votes/bulk-state`; toast "N games opened"; clears selection and reloads |
| Nudge non-voters | `POST /api/votes/nudge`; toast "Reminder sent to N players" |
| Fixture click | Opens `FixtureDetail` (managers only — read-only viewers see a static row, as today) |
| Share target | WhatsApp → `wa.me/?text=`; SMS → `sms:?&body=`; Copy → clipboard + toast; QR → inline render; Socials → BetterSocials post designer |
| Presentation mode | Mounts `AwardsNight` in place of the board; Esc exits |
| Reveal next round | `upto + 1`, re-fetches `through_round`; disabled at the last counted round |
| Tap player (public) | Fills the next empty slot; if already chosen, clears it |
| Submit (public) | Disabled until every slot is filled |

**Transitions:** progress bars `transition-[width] duration-300`; buttons and
chips use the existing `transition-colors`. No entrance animations — this is a
data screen, and the awards-night reveal is driven by the operator, not a timer.
Respect `prefers-reduced-motion` if you add anything.

**Responsive:** the hub table drops grade/progress/closes under `md`; podium
stacks under `md`; the race card drops below the table under `xl`; share/chase
stack under `lg`. The public page is unchanged at `max-w-md`.

**Loading:** existing `<PbSpinner>` / plain "Loading fixtures…" line.
**Errors:** existing `useToast().error`. **Empty:** "No fixtures match these
filters." / "No votes counted yet. Ballots appear here as soon as they're cast."

## State management

Local component state only — no store needed.

```
AdminVotes         tab (URL search param), openFixture
VotesHub           data, year, status, gradeId, roundKey, q, selected[], busy
VotesLeaderboard   board, year, gradeId, throughRound, presenting
AwardsNight        upto (rounds revealed), snapshot (replayed standings)
PublicVoting       step, landing, me, supporterName, fixture, picks[], pin, busy, error
```

`picks` on the public page is a fixed-length array (`ballot_values.length`) of
player ids or `null` — position is the ballot position, so submission needs no
transformation.

Data fetching: `VotesHub` reloads on year/grade/round/search change and after any
mutation. `AwardsNight` fetches once per reveal — **cache these server-side**, an
awards night will hit the same nine replays repeatedly.

## Design tokens

All existing (`frontend/src/lib/theme.js`, `tailwind.config.js`). Nothing here
needs a new token.

| Token | Dark | Light |
| --- | --- | --- |
| `--pb-bg` | `#0a0d14` | `#f5f6f8` |
| `--pb-surface` | `#10141d` | `#ffffff` |
| `--pb-surface2` | `#161b27` | `#eef0f3` |
| `--pb-hairline` | `#1d2331` | `#e1e4ea` |
| `--pb-hairline2` | `#262d3d` | `#d0d4dd` |
| `--pb-text` | `#e6e8ef` | `#1b1e27` |
| `--pb-dim` | `#8a90a2` | `#5b6072` |
| `--pb-faint` | `#5b6072` | `#8a90a2` |
| `--pb-faintest` | `#3a3f50` | `#b6bac6` |

Shared across themes: `--pb-accent` `#3B82F6` (BetterSelect module override from
`moduleBrand.js` — the club accent is deliberately overridden inside this
module), `--pb-positive` `#16c784`, `--pb-red` `#ef5b5b`, `--pb-amber` `#f5b542`.

**Two literal hexes are introduced**, both deliberate:
- `#c98b4a` — bronze for 3rd place. No existing token reads as bronze.
- `#07090f` — the awards-night stage background, one step darker than
  `--pb-bg` so the projector reads as black.

The prototype also uses `#EC4899` for the "Post to socials" dot — that is the
existing BetterSocials brand accent from `moduleBrand.js`, not a new colour.

**Type:** `font-display` / `font-body` = Geist; `font-mono` = JetBrains Mono. Sizes
used: 9.5 / 10 / 10.5 / 11 / 12 / 12.5 / 13 / 13.5 / 14 / 14.5 / 15 / 15.5 / 17 /
19 / 21 / 22 / 26 / 38 / 64 / 84 px. Tracking: `wide2` .08em, `wide3` .14em,
`wide4` .18em. All numeric columns `tabular-nums`.

**Radii:** 5 (checkbox) · 6 (segmented item) · 8/9 (control) · 10 (share button,
stat group) · 11 (awards row) · 12 (pb-card, list) · 14 (podium, step card) ·
16 (public submit) · `rounded-full` (chips, badges, bars, avatars).

**Spacing:** 4px scale throughout. Card padding 16px; table rows 14px vertical,
20px horizontal; screen gaps 20px.

**Shadows:** none. Depth comes from hairlines and surface steps — consistent with
the rest of the app.

## Assets

- `frontend/src/assets/modules/*.svg` — module marks, already in the repo. Used by
  the sidebar lockup and `ModuleSwitcher`; the prototypes reference copies of them.
- `qrcode` npm package — already a dependency, used by the current settings tab.
- No new images, and no hand-drawn SVG illustrations. The only SVG authored here
  is the data chart in `RaceChart.jsx` and the geometric glyphs already in
  `ui.jsx`'s `ICON_PATHS`.

## Files

### `code/` — implementation
```
frontend/src/pages/admin/betterselect/AdminVotes.jsx        rewritten shell (3 tabs)
frontend/src/pages/admin/betterselect/votes/
  votesTokens.js        state meta, filters, formatters, progress colour
  VoteStateBadge.jsx    OPEN / CLOSED / LOCKED / NO TEAM pill
  BallotProgress.jsx    bar + "8/11"
  VotesHub.jsx          counters, filters, bulk actions, fixture table
  ShareVotePanel.jsx    one sharing surface (+ voteUrl helper)
  OutstandingVoters.jsx who hasn't voted + nudge
  FixtureDetail.jsx     one game (carried over + progress/chase/share)
  VotesSettings.jsx     settings tab (carried over)
  VotesLeaderboard.jsx  podium + standings + race
  PodiumCard.jsx        top-3 card
  RaceChart.jsx         cumulative-points SVG
  AwardsNight.jsx       full-screen presentation mode
frontend/src/pages/PublicVoting.jsx                          one-screen ballot
```

Unchanged and still required: `components/admin/BetterSelectLayout.jsx`,
`components/admin/ModuleSwitcher.jsx`, `components/ModuleLockup.jsx`,
`pages/admin/betterselect/ui.jsx`, `lib/api.js`, `lib/capabilities.js`,
`lib/theme.js`, `lib/moduleBrand.js`, `lib/presskit.jsx`.

### `design/` — HTML references (open in a browser)
```
BetterSelect Votes current.dc.html   the CURRENT UI, recreated from source
                                     (screen switcher bottom-centre; light/dark toggle)
BetterSelect Votes v2.dc.html        the redesign — 1a hub, 1b race, 1c awards
                                     night, 1d one-screen ballot, 1e stepper
support.js                           runtime the two HTML files need
frontend/src/assets/modules/*.svg    module marks the mocks reference
```

`1e` in the v2 file is an **alternative** voting flow (the current stepper, sped
up: two-up cards, live progress rail, review folded into the last step). `1d` is
the recommended one and the only one implemented in `code/`. If you'd rather ship
`1e`, the slot logic in `PublicVoting.jsx` becomes a single `posIndex` cursor —
the submit payload is identical.

## Capabilities

Unchanged. `MANAGE_VOTES` gates the hub's write actions, bulk actions, nudges,
fixture detail and settings. `VIEW_VOTE_RESULTS` gates the leaderboard and
presentation mode. The nav item stays visible for either
(`anyCaps` in `BetterSelectLayout`). Tallies never appear on the public page.

## Suggested build order

1. `votesTokens.js`, `VoteStateBadge`, `BallotProgress` — no API work.
2. `VotesHub` against existing `votesFixtures`, with `voters_expected` and
   `summary` added server-side (item 1 in `API_CONTRACT.md`).
3. `ShareVotePanel` — pure client; ship this early, it's the highest-value change
   per line.
4. `bulk-state` endpoint + bulk bar.
5. Leaderboard `movement` / `form` / `cumulative` / `last_round`, then
   `PodiumCard` + `RaceChart`.
6. `AwardsNight` (needs nothing new beyond the above).
7. `PublicVoting` one-screen ballot — no API change at all.
8. `nudge` endpoint + `OutstandingVoters` (BetterComms policy review first).
9. Optional: leaderboard-card render for BetterSocials.

## Open question for the product owner

Players deliberately can't see the count. Should the `/vote` page at least show a
player their own past ballots ("you gave your 3 to Rahim in R8")? It's cheap —
`my_ballot` is already returned per fixture — but it changes the page from
write-only to a small history surface.
