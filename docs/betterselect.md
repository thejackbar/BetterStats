# BetterSelect — module overview

_Background for a design handoff. Accurate as of v7.28.2 Beta (May 2026)._

BetterSelect is the **team-selection workflow** inside the BetterStats club-admin
app. Where the rest of admin is about historical **stats and data**, BetterSelect
is the forward-looking, weekly-cadence side: _who's playing this weekend, and who
do we pick?_ It runs as its own module surface (its own sidebar + layout) so
selectors aren't wading through the stats admin "noise".

It lives under `/admin/betterselect/*` and is gated by two capabilities:
- **`manage_fixtures`** — sync / add upcoming fixtures.
- **`manage_selections`** — teams, availability, selection (the bulk of it).

Everything is **multi-tenant**: every screen and API call is scoped to the
logged-in user's club (organisation).

---

## The surfaces (screens)

All wrapped by `BetterSelectLayout` (`frontend/src/components/admin/BetterSelectLayout.jsx`)
— a left sidebar (club logo + name + nav) and a sticky header (page title +
actions + user). The layout is **white-labelled**: it pulls the club's theme and
applies it via `useClubTheme`, so the accent colour, logo and name are the
club's, not generic BetterStats green.

| Screen | Route | File | Purpose |
|---|---|---|---|
| **Overview** | `/admin/betterselect` | `BetterSelectHome.jsx` | Landing/launchpad for the module. |
| **Fixtures** | `/admin/betterselect/fixtures` | `AdminFixtures.jsx` | The upcoming match list — synced from Cricket Australia, plus manual add/edit. The source of the dates everything else hangs off. |
| **Teams** | `/admin/betterselect/teams` | `AdminTeams.jsx` | The club's squads/teams (1st XI, 2nds…), squad membership, and linking a team to its CA grade. |
| **Availability** | `/admin/betterselect/availability` | `AdminAvailability.jsx` | The big one: a players × upcoming-dates grid where admins record who's available. Plus bulk-set and **availability periods**. |
| **Selection (overview)** | `/admin/betterselect/selection` | `AdminSelectionOverview.jsx` | Lists upcoming fixtures to pick a side for; entry point to the board. |
| **Selection (board)** | `/admin/betterselect/select/:fixtureId` | `AdminSelection.jsx` (+ `selection/`) | Pick the XI for one fixture: a filtered/sorted pool on the right, a drag-orderable team sheet on the left. |
| **Ladders** | `/admin/betterselect/ladders` | `AdminLadders.jsx` | League standings per grade (read-only, synced). |

### Selection board is decomposed
`AdminSelection.jsx` is the container (state, data, handlers). The presentational
pieces live in `pages/admin/betterselect/selection/`:
- `shared.jsx` — status meta, row tints, `Avatar` / `roleText` / `rowState`.
- `SelectionFilters.jsx` — the facet panel.
- `TeamSheet.jsx` — the picked XI (drag-reorder, captain/keeper/remove).
- `PlayerPool.jsx` — the available pool (row-tinted, click to add).

---

## The two core flows

### 1. Availability
The matrix is **all active players (rows) × upcoming fixture dates (columns)**.
Each cell is a status the admin clicks to cycle:

- ✓ **Available** (accent) · ✕ **Unavailable** (red) · ? **Maybe** (amber) · – **No response** (faint)

Important model quirk: **availability is keyed on the DATE, not the fixture** —
one answer covers every fixture that day. A two-day game shows both its weekends
(D1 / D2).

Three ways to set it:
1. **Click a cell** to cycle a single player/date.
2. **Bulk** — tick several players, set them all to one status across one or all
   shown dates.
3. **Periods** _(new, v7.28.1)_ — mark a player un/available across a **date
   range** with an optional reason ("injured 1 Jun–15 Jul"; blank end =
   open-ended). A period auto-fills every fixture in its span; an explicit cell
   click always overrides it. Period-driven cells render with a **dashed border**.

Players are filtered by a bar (search, roster scope, squad, role, skill,
response). "**Dormant**" = hasn't appeared within the club's dormancy window
(default 24 months) — an auto-archive bucket so selection works off the current
squad, not decades of history.

### 2. Selection
For one fixture, build the XI:
- **Pool** (right): the club's players annotated with their availability for that
  fixture's date, squads, recency, and skill attributes. Sorted available-first.
  A facet **filter panel** (squads / roles / availability / batting / bowling /
  activity) narrows it. **Clash detection** flags anyone already picked in
  another XI that same date (blocked from being added).
- **Team sheet** (left): click a pool row to add; **drag to reorder** the batting
  order; toggle **(C)** captain / **(WK)** keeper; remove.
- **Format / team size**: 11 (default) / 12 / 13 / no-limit. Persisted as a club
  default. A non-blocking banner warns if the XI count ≠ the format.
- **Share team sheet** hands off to the existing social-post generator.

---

## Design system

BetterSelect uses the shared BetterStats system — **Tailwind** with
CSS-variable-backed `pb-*` tokens (so themes/white-label swap at runtime).

**Colour tokens** (`frontend/tailwind.config.js`, values are CSS vars):
`pb-bg`, `pb-surface`, `pb-surface2`, `pb-hairline`, `pb-hairline2`, `pb-text`,
`pb-dim`, `pb-faint`, `pb-faintest`, `pb-accent`, `pb-red`, `pb-amber`,
`pb-positive`, `pb-negative`, plus chart tokens (`pb-runs`, `pb-wickets`,
`pb-milestone`). **`pb-accent` is the club's brand colour** under white-label.

**Type**: `font-display` (Geist / Barlow Condensed — headings), `font-body`
(Geist / Inter), `font-mono` (JetBrains Mono — labels, micro-copy, stats). Lots
of small uppercase mono labels with `tracking-wide2/3`.

**Shared components** (`frontend/src/lib/presskit.jsx`): `Card`, `Btn`, `Field`,
`Input`, `Select`, `ResultPill`, `Kpi`, `Skeleton`, `PageHeader`, `PbSpinner`,
`TabBar`, plus stat bits (`AnimatedNum`, `Sparkline`, `MiniBars`, `Ticker`).

**BetterSelect-specific shared bits**:
- `frontend/src/lib/availability.js` — **single source of truth** for the four
  availability statuses' glyph / chip colour / dot / label / sort rank. Both the
  matrix and the selection board read from it so they can't drift.
- `frontend/src/lib/filters.jsx` — shared filter primitives (`FilterSelect`
  dropdown, `FilterGroup` + `FilterCheck` facet checkboxes).

**Theming / white-label**: `useClubTheme(club)` injects a `<style>` of the club's
palette built from `club.theme_config`; the club sets colours/logo in main admin
Settings. Light/dark is handled by `ThemeContext`.

---

## Data model (the concepts a designer should know)

- **Organisation** (club) — branding (`primary_color`, `theme_config`,
  `logo_url`), `dormancy_months`, `default_team_size`.
- **Player** (roster) — `display_name`, `player_role`, `skill_positions`
  (BAT/BWL/ALL/WKT), `batting_hand`, `bowling_action`, `bowling_type`,
  `is_opening_batsman`, `status` (active/inactive), `photo_url`.
- **Team** (squad) — `name`, `short_name`, `sequence`, linked `grade_id`.
- **Fixture** — opponent, `home_away`, `played_on` / `end_on` (two-day), venue,
  round; synced from CA or added manually.
- **player_availability** — `(player, date) → status + note` (explicit answer).
- **player_availability_periods** — `(player, start_date, end_date?, status,
  reason)` — the date-range layer; resolved _under_ explicit answers.
- **fixture_lineups** — the selected XI per fixture (ordered, captain, keeper).
- **Grade / Season** — competition structure, synced from CA; drives ladders.

Backend routers (FastAPI): `availability.py`, `selection.py`, `fixtures.py`,
`teams.py`, `ladders.py`, and club settings in `club_admin.py`. All scoped via
`get_current_club`; writes gated by `require_cap(...)`.

---

## Status / recent work

Current version **v7.28.2 Beta**. Recent BetterSelect changes:
- **Availability Periods** (v7.28.1) — date-range un/availability + reason.
- **White-label the BetterSelect layout** (v7.28.2) — club colours + logo.
- **Lineup size** now defaults to 11 and persists as a club setting (v7.28.2).
- Internal: shared `lib/availability.js` + `lib/filters.jsx`; selection board
  decomposed into `selection/*`.

Per-release notes live in `frontend/src/data/changelog/` (one file per version;
`SITE_VERSION` derives from the highest `sortKey`).

---

## Design opportunities / open questions

Honest list of rough edges worth a designer's eye:

1. **Filter UX is inconsistent** between screens — Selection uses checkbox
   **facets** in a collapsible panel; Availability uses inline **dropdowns**.
   They now share primitives (`lib/filters.jsx`) but not a pattern. A unified
   filtering model would help.
2. **Availability matrix scales awkwardly** — many upcoming dates × a big roster
   = a wide, dense grid (sticky first column today). Worth rethinking for lots of
   players / long horizons, and on mobile.
3. **Selection board is dense** — pool + team sheet + filters + legend + size
   warning + share all on one screen. Lots of micro-mono labels. Room for visual
   hierarchy / breathing space.
4. **Period-derived cells** use only a dashed border to distinguish "from a
   period" vs an explicit answer — subtle; could be clearer (and the reason is
   tooltip-only).
5. **Two overview-ish surfaces** — the module **Overview** and the **Selection**
   overview. Possible consolidation / clearer roles.
6. **Empty / onboarding states** — first-run (no fixtures synced, no
   availability yet) could guide the user more.
7. **Mobile** — it's responsive but designed desktop-first; the grid and the
   two-column selection board are the hard cases.

---

_For deployment, architecture and gotchas, see `CLAUDE.md` at the repo root._
