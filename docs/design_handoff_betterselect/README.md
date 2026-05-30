# Handoff: BetterSelect redesign (cleaner module + Players & Squads)

## Overview
This package redesigns the **BetterSelect** module of BetterStats — the weekly,
forward-looking team-selection workflow (availability → squads → pick the XI).
It cleans up every screen, adds a **Players** profile page (replacing the cramped
edit modal at `/admin/players`), reframes "Teams" as **Squads** (selection pools)
with bulk assignment, and threads a shared **squad assignment** model through
Players → Squads → Selection so the right players are suggested first.

It targets the existing repo: **`thejackbar/BetterStats`** → `frontend/` (React +
Vite + Tailwind) and `backend/` (FastAPI + SQLAlchemy + PostgreSQL). Routes live
under `/admin/betterselect/*`. Read `docs/betterselect.md` and root `CLAUDE.md`
first — this handoff assumes that architecture.

## About the design files
The files in `prototype/` are **design references built in HTML/JSX (React via
in-browser Babel)** — they show intended look, layout, copy and behaviour. They
are **not** production code to copy verbatim. The task is to **recreate these
designs inside the existing BetterStats frontend**, reusing its established
patterns: the `pb-*` Tailwind tokens, `lib/presskit.jsx` components, `lib/availability.js`,
`lib/filters.jsx`, `BetterSelectLayout`, and the `api.*` client. Match the
prototype's visuals pixel-for-pixel while using real components and the live API.

The prototype mounts everything inside a `design-canvas.jsx` pan/zoom wrapper for
side-by-side review — **ignore that wrapper**; it is presentation scaffolding only.
The live, interactive module is the `<BSModule>` component in `bs-app.jsx`.

## Fidelity
**High-fidelity.** Final colours, typography, spacing, states and interactions are
all specified. Recreate pixel-perfectly with the codebase's existing libraries.
All data in the prototype is **mock** (`bs-data.jsx`) — wire to the real API.

---

## Design system / tokens (already in the codebase)
Use the existing theme-aware CSS variables from `frontend/src/styles/theme.css`
and the Tailwind `pb-*` mappings in `frontend/tailwind.config.js`. **Do not
hard-code hex** — use the tokens. Values (dark theme, for reference only):

| Token | Var | Dark value |
|---|---|---|
| Background | `--pb-bg` | `#0a0d14` |
| Surface | `--pb-surface` | `#10141d` |
| Surface 2 | `--pb-surface2` | `#161b27` |
| Hairline | `--pb-hairline` | `#1d2331` |
| Hairline 2 | `--pb-hairline2` | `#262d3d` |
| Text | `--pb-text` | `#e6e8ef` |
| Dim | `--pb-dim` | `#8a90a2` |
| Faint | `--pb-faint` | `#5b6072` |
| Faintest | `--pb-faintest` | `#3a3f50` |
| Accent (brand) | `--pb-accent` | `#16c784` |
| Red / negative | `--pb-red` | `#ef5b5b` |
| Amber | `--pb-amber` | `#f5b542` |
| Chart blue (bowling) | `--pb-chart-wickets` | `#3b82f6` |

- **`--pb-accent` is the club's white-label colour** — keep everything that's
  "accent" bound to it (it is not always green).
- **Fonts**: `font-display` (Geist), `font-body` (Geist), `font-mono` (JetBrains Mono).
- **Radii**: cards `10px` (prototype) — match the codebase's `.pb-card` (`6px`) OR
  bump `.pb-card` to 10px if approved; chips/pills `8px`/`999px`; status cells `7px`.
- **Mono micro-labels** ("eyebrows"): JetBrains Mono, 10px, `letter-spacing .14em`,
  uppercase, `--pb-faint`. Used **sparingly** — section eyebrows and stat units only.
- **Availability identity** is the single source of truth in `lib/availability.js`:
  - AVAILABLE ✓ accent · MAYBE ? amber (`#f5b542`) · NO_RESPONSE – faintest (hollow dot) · UNAVAILABLE ✕ red. Sort rank: AVAILABLE 0, MAYBE 1, NO_RESPONSE 2, UNAVAILABLE 3.

### Shared atoms (prototype → codebase mapping)
The prototype's `bs-shared.jsx` reimplements primitives that **already exist** in
`lib/presskit.jsx` — use the real ones:
- `Btn` (variants: primary / ghost / soft / danger; `sm`), `Search` input, `Chip`
  (toggle pill), `Segmented` (segmented control), `Avatar` (initials fallback,
  keeper = amber ring), status `Dot`, `RoleChips` (mono BAT/BWL/ALL/WK tags),
  `AvailSummary` (stacked bar + legend).
- `Icon` — simple line glyphs; use the codebase's existing icon set.

---

## Navigation change
`BetterSelectLayout.jsx` holds the sidebar `NAV` array. **Add a "Players" item with
a single-person icon, positioned right after "Overview"**, and **rename "Teams" →
"Squads"** (keep its route/key `teams`, keep the icon). Final order:

`Overview · Players · Fixtures · Squads · Availability · Selection · Ladders`

New route: `/admin/betterselect/players` (gated by `CAP.MANAGE_SELECTIONS`).
Keep the existing `/admin/players` admin entry too (both surfaces).

---

## Screens

### 1. Overview  (`bs-overview.jsx`)  — route `/admin/betterselect`
Landing dashboard centred on "this weekend".
- **Hero card** (`pb-card`, subtle accent gradient `linear-gradient(120deg, rgba(22,199,132,.10), transparent 55%)`, 1px accent-25% border): eyebrow "THIS WEEKEND · ROUND 9"; `font-display` 800 30px "1st XI vs Nedlands"; meta row (date/time, venue (H), grade) at 13.5px dim with small icons; an `AvailSummary` (stacked availability bar + legend) max-width 460. Right side: primary **Pick this team** (→ selection), soft **Review availability** (→ availability), and "N still to respond".
- **Pulse stats** strip (`pb-card`, 5 equal cells split by hairlines): Responded `13/15`, Available, Maybe, Unavailable, To select `11`. Numbers `font-display` 700 26px, coloured by status.
- **Needs attention** card: header "Needs attention" + count badge; rows (each a clickable button → relevant screen): risk (red dot) "Your likely keeper **Cooper Nguyen** hasn't confirmed", warn (amber) "**N players** haven't set their availability", info "**3 of 4** weekend teams still need an XI". Each row: dot + text + accent action label + chevron.
- **Upcoming fixtures**: 4 cards (grid). Each: eyebrow "R9 · 6 Jun" (truncates) + "THIS WK" badge on current; `font-display` 700 17px opponent; thin availability bar; "10 / 15 available" + "11 named"/"Not picked"; footer status + arrow. Card is a `<button>` → selection (give it explicit `color: var(--pb-text)`; a bare button inherits black).

### 2. Players  (`bs-players.jsx`)  — route `/admin/betterselect/players`  ★ replaces the modal
**Master–detail layout** (chosen over a full-page variant): `grid` `minmax(420px,1fr) 1.35fr`.

**Left — list** (`pb-card`): header has `Search` + role chips (Batter/Bowler/All-R/Wicketkeeper) + "Show inactive" chip + count. Rows (clickable → select): checkbox · **avatar (clickable → opens profile; accent ring when active)** · name (+ C tag, + "OS" amber tag if overseas) · style sub ("RHB · Right-arm fast") · **assigned squad** mono tag · role chips · availability `Dot` · contact present (check/×) · active dot or "INACTIVE" pill. Inactive rows render at 0.6 opacity. **Bulk bar** appears when rows are ticked: "N selected · set squad ▾ · Apply · Mark inactive · Clear".

**Right — profile**:
- **Header** (subtle accent gradient): 56px avatar; name `font-display` 800 24px; chips: C, **"1st XI squad"** (accent), Overseas·Country (amber), Inactive; meta line: role · batting hand · bowling · OPENER badge. Top-right **Save changes** (enabled only when dirty; shows "Saved" briefly).
- **Two columns** (`1fr 1fr`, divided by hairline):
  - **Selection snapshot** (left): "Availability — next 4 weeks" (4 mini cards, this-week accent-bordered, date + `Dot`); "Squad & eligibility" (accent squad tag + "assigned · suggested first for {squad} fixtures"); **Recent form** — three labelled rows: `BATTING` last-5 score chips (≥50 accent, 0 red), `BOWLING` last-5 figures chips like "3/24" (≥3 wkts blue `--pb-chart-wickets`) shown **only for bowlers**, `CATCHES` count + "this season"; "Last picked" R8 · vs Cottesloe.
  - **Details** (right, inline-editable): fields in a wrapping flex (each ~half width): **Squad (selection pool)** select, Role select, Batting hand select, **Bowling** select (action+type merged — see below), Gender select, Email, Phone. Then toggles (custom switch): Opening batsman, Overseas player (+ country input when on), "Inactive — hide from availability & selection". **Tucked at the very bottom** in faint 10px: PlayHQ ID (truncated) and a "Non-player (coach/scorer)" checkbox.

**Bowling field merge**: the old separate `bowling_action` + `bowling_type` become one
"Bowling" dropdown with combined labels: `—`, Right-arm fast, Right-arm fast-medium,
Right-arm medium, Off spin, Leg spin, Left-arm fast, Left-arm medium, Left-arm
orthodox, Left-arm wrist spin. Persist back to `bowling_action` + `bowling_type`
(split the combined value) so existing selection filters keep working.

### 3. Squads  (`bs-teams.jsx`)  — route `/admin/betterselect/teams` (rename label only)
The selection-pool manager (a kanban board).
- Header: "Squads" + subtitle "Selection pools — a player's squad drives who's suggested first when picking." Stats: N players, N squads. Availability legend top-right.
- **5 columns** (grid, equal): 1st XI · 2nd XI · 3rd XI · 4th XI · Veterans. Each column (`pb-card`): header with coloured square (per-squad tint), name, count, grade eyebrow, "no keeper" amber note when applicable, and an available-count (`Dot` + N). Body = member cards sorted **available-first**; each card draggable (grip), availability dot + tint background, avatar, name (+C), role chips. Footer "**+ Add players**" (dashed button).
- **Drag** a card between columns to reassign.
- **Bulk add modal** (per column footer): "Add players to {squad}", search, scrollable checkbox list of players **not** already in that squad (shows each player's current squad + roles), footer "N selected · Cancel · **+ Add N to {squad}**".
- Per-squad tints: 1st `#16c784`, 2nd `#3b82f6`, 3rd `#a855f7`, 4th `#f5b542`, Veterans `#06b6d4`.

### 4. Availability  (`bs-availability.jsx`)  — route `/admin/betterselect/availability`
Players × upcoming-dates matrix. (Keep the existing date-keyed model from `betterselect.md`.)
- **Filter bar** (one row): search; "Current squad / All" segmented; status filter chips; right-aligned **"Date range"** toggle.
- **Date range bar** (shown when toggled): "From ▾ → To ▾" week selects + a list of the games covered (round + opponent chips). In-range columns highlight; out-of-range columns **dim to 0.4**. This **replaces the old "Periods" feature**.
- **Matrix** (`pb-card`, scroll; sticky first column + sticky header): first column = player (checkbox, avatar, name +C/dormant, role chips). Each date column header is **clickable to select that week** (accent top-border + bg + radio dot); the **selected** week shows a "Pick XI →" button (→ selection). Column header also shows the date, fixture sub, a thin availability bar, and "N in".
- **Cells**: 38×30 rounded, status glyph (✓ ? – ✕), tinted bg, accent on click. **Clicking a cell opens the Quick-update modal** (below) — it no longer cycles.
- **Bulk bar** (when players ticked): "N selected · mark [segmented status] · **for [week ▾]** (single week) OR **across [From → To] · N games** (when a range is set) · Apply · Clear". Single-week target follows the selected column.

### 5. Selection  (`bs-selection-c.jsx` + `bs-selection-core.jsx`)  — route `/admin/betterselect/select/:fixtureId`
**"Batting-order slots"** model (chosen over two-column / single-list variants).
- Top **context bar**: fixture identity; "Side" 11/12/13 segmented; "N / 11 picked" pill (amber when off-count); **Share** (→ team-sheet modal); **Save XI** (enabled when dirty).
- **Team-balance strip**: role counts BAT/ALL/BWL/WK (amber when light/none); Captain & Keeper status pills (keeper amber if unnamed); "Light on bowling" warning; **"Fill from last week"** button (shows when slots empty).
- **Body** `grid 1.25fr 1fr`: **Pool on the LEFT (wider)**, **numbered batting-order slots on the RIGHT**.
  - **Pool**: search + role chips + "Available only"; rows sorted **fixture-squad-first, then availability, then name**; each row shows availability dot (click → quick-update modal), avatar, name, note, role chips, **squad tag (accent if it matches the fixture's squad)**, arrow. Click → fill focused/next slot. **Right-click → drop into next empty slot.** Drag → drop onto a slot. Clash players (already picked elsewhere that date) are blocked/dimmed with a ⛔ tag.
  - **Slots**: 11 (or format) rows, each with number + position hint (Opener/Top order/Finisher/All-rounder/Bowler). Filled = avatar, name, C/WK toggles, remove. Empty = focused slot shows "Suggested {best-fit available} + Add"; other empty slots show faint "Empty · try {name}". Focused slot has accent border.
- **Autofill ("Fill from last week")**: fills empty slots position-by-position from the **previous round's XI**, skipping anyone now unavailable/clashing, then tops up remaining gaps with the best-fit available player (squad-first, availability-first).
- **Team-sheet modal** (Share): formatted XI (numbered, C/WK, role chips, fixture header) + a **"Copy lineup as text"** button that writes a plain-text lineup to the clipboard (social posting is handled by the existing social-post generator — hand off to it, don't rebuild).

### 6. Fixtures  (`FixturesScreen` in `bs-app.jsx`)  — route `/admin/betterselect/fixtures`
**Whole-club, by-week** view. Grade filter segmented: "Whole club / 1st XI / 2nd XI / 3rd XI / 4th XI". Grouped by weekend (round) — each group a `pb-card` with a header (date, round, "THIS WEEKEND" badge on current, game count) and a row per grade's fixture: team name (colour-coded by grade), grade, vs/@ opponent, venue (H/A) · time, and a **Pick team** (current-week 1st XI, primary) / **Select** (others) action. Bye rendered as "Bye".

### 7. Ladders  (`bs-ladders.jsx`)  — route `/admin/betterselect/ladders`
Multi-grade standings. Grade segmented (A/B/C/D). Summary pill "Applecross sit **1st** of 8 · 6–2 · 30 pts". Table columns: # · Team · P · W · L · Pts · **Form** (last-5 W/L/D coloured squares). Our club row highlighted (accent + "US" tag). Accent left-bar on the top-two ("Top two qualify for finals").

### 8. Mobile quick-tasks  (in `bs-app.jsx`: `MobileAvailability`, `MobileTeamSheet`)
Two phone-width frames: **quick-mark availability** (big In/Maybe/Out 44px targets per player, sticky "N responded · Pick team") and a **named team sheet** (numbered XI, C/WK, share). Desktop-first overall; these are the two phone-critical tasks.

---

## Interactions & behaviour
- **Availability quick-update modal** (shared): opens from any availability **dot/cell** (matrix cells **and** dots on the Selection pool/sheet). Centred overlay (`position:absolute inset:0` within the screen root; dim `rgba(4,6,11,.62)` + blur). Shows player avatar + name + date, and four large status buttons (current one highlighted); picking saves instantly and closes. On the matrix it updates that `(player, date)`; on Selection it updates the player's availability for the fixture's date.
- **Shared squad store**: reassigning a player's squad on the **profile**, the **Squads board** (drag or bulk-add) updates one shared source; **Players list**, **Squads board**, and **Selection ordering** all reflect it immediately. (In production this is a player field + `PATCH`; invalidate the relevant queries.)
- **Save model**: profile fields are dirty-tracked with an explicit **Save changes**; squad/availability changes save immediately (optimistic).
- **Transitions**: 0.12–0.15s ease on hover/selection/dim changes; status cell press scale 0.88.

## State management
Per screen (local UI state): filters/search, selected player/week, ticked-for-bulk sets, dirty-tracking for the profile form, modal open state, drag source.
Server state (via the existing `api` client + your query layer):
- Players list + per-player profile; selection lineup per fixture; availability matrix; squads/membership; fixtures; ladders.

## API & data (existing — see `frontend/src/lib/api.js`, `docs/betterselect.md`)
Already present: `bsGetSelection`, `bsSetSelection`, `bsSelectionOverview`,
`bsListFixtures`, `bsListTeams`, `bsAvailabilityMatrix`, `bsSetAvailability`,
`bsBulkAvailability(items[])`, `bsAvailabilityPeriods` (+create/delete),
`bsGetPlayerProfile`, `bsUpdatePlayerProfile`, `adminListPlayers`,
`adminPatchPlayer`, `adminCreatePlayer`, `adminUploadPlayerPhoto`.
Player model fields (existing): `display_name(_override)`, `player_role`,
`skill_positions` (BAT/BWL/ALL/WKT), `batting_hand`, `bowling_action`,
`bowling_type`, `is_opening_batsman`, `status` (active/inactive), `gender`,
`is_player`, `is_overseas`/`overseas_country`, `photo_url`, `playhq_id`, email/phone.

### New backend work required (the genuinely new bits)
1. **Squad assignment (selection pool)** — a player's assigned squad distinct from
   historical Team membership. Add a nullable `squad`/`squad_id` to the player (or a
   `squad_memberships` table) + endpoints to read, set, and **bulk-set** (assign
   many players to a squad in one call). Surfaces on the profile, the Squads board,
   and bulk-add. `backend/app/routers/teams.py`.
2. **Selection ordering by squad** — `selection.py` pool builder should sort/flag
   players whose assigned squad == the fixture's team/grade first (then availability,
   then name). The UI already shows the squad tag and expects this order.
3. **Profile selection-snapshot data** — last-5 batting scores, last-5 bowling
   figures, season catches, and "last picked" fixture. Derive from existing
   `batting_innings` / `bowling_spells` / `fielding_stats` / `fixture_lineups`. A
   single `bsGetPlayerProfile` extension returning these is cleanest.
4. **Availability date-range bulk** — `bsBulkAvailability` already takes `items[]`;
   the date-range UI just expands the selected range to multiple `(player,date)`
   items client-side. No new endpoint needed (the old "periods" feature can be
   retired/migrated — confirm before removing data).

## Assets
No image assets — avatars are initials fallbacks (`photo_url` when present), icons
are simple line glyphs (use the codebase's icon set), flags via the existing
`countryFlagUrl` for overseas players. Club logo/name/accent come from the
white-label theme (`useClubTheme`).

## Files in this bundle (`prototype/`)
- `BetterSelect.html` — entry; loads React+Babel, tokens/fonts, and the scripts below.
- `bs-data.jsx` — **mock data** (roster, fixtures, availability, squads, prev XI). Replace with API.
- `bs-shared.jsx` — prototype atoms + the **shared availability/squad stores**, `BSShell` (sidebar+header = `BetterSelectLayout`), Quick-update modal.
- `bs-overview.jsx` · `bs-availability.jsx` · `bs-players.jsx` · `bs-teams.jsx` (Squads) · `bs-ladders.jsx` — the screens.
- `bs-selection-core.jsx` (shared selection logic: XI state, filters, context bar) + `bs-selection-c.jsx` (the slots board + team-sheet modal).
- `bs-app.jsx` — `BSModule` (the live nav-switching module), `FixturesScreen`, mobile frames, and the review-canvas assembly (ignore the canvas parts).
- `design-canvas.jsx` — review wrapper only; **not** part of the product.

To run the prototype: open `prototype/BetterSelect.html` in a browser (it's a single
self-contained design canvas; pan/zoom, and each artboard is interactive).
