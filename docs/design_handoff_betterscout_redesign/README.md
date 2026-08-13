# Handoff: BetterScout Redesign

## Overview

BetterScout is BetterCricket's standalone recruiting and player-tracking tenant: a **Scout Org** (recruiting agency, premier club scouting its junior pathway, state selector) logs in separately from any club, searches any Australian club's roster built from Cricket Australia's public data, filters and sorts it on performance, and tracks players on Kanban watchlists with recruiting-specific detail.

This bundle redesigns BetterScout so it (a) wears the same module chrome as every other Better module instead of its own one-off top-tab shell, and (b) does more of the scouting job: a pipeline overview, a deeper player profile, a proper head-to-head comparison, a milestones page and a settings page.

Two design files:

| File | What it is |
| --- | --- |
| `BetterScout Today.dc.html` | **Reference only.** A faithful recreation of all 11 screens as they exist in `frontend/src/scout/*` on `main`. Use it to diff old against new. |
| `BetterScout Redesign.dc.html` | **The target.** Six screens: `1a` Overview, `1b` Discover, `1c` Player profile, `1d` Compare, `1e` Milestones, `1f` Settings. |

`BUILD_PLAN.md`, alongside this file, is the engineering companion: what already exists in the repo, what is new, which endpoints and tables each screen needs, and what is deliberately **not** being built.

## About the Design Files

The `.dc.html` files are **design references written in HTML** — prototypes showing intended layout, styling and content. They are not production code and should not be shipped or copied wholesale.

The target codebase is the existing BetterCricket SPA: **React 18 + Vite + React Router + Tailwind**, with the Press Box theme tokens in `frontend/src/styles/theme.css` and `frontend/tailwind.config.js`. Recreate these designs there, using the codebase's own patterns:

- Tailwind utility classes and the `pb-*` token classes (`bg-pb-surface`, `border-pb-hairline`, `text-pb-dim`, `pb-card`, `font-mono`), **not** the inline styles in these prototypes. The prototypes are inline-styled only because of how they were authored.
- The existing `Icon` component (`frontend/src/pages/admin/betterselect/ui.jsx`), the existing `ModuleLockup` / `ModuleSwitcher`, the existing `Avatar` pattern.
- The scout API wrappers in `frontend/src/scout/lib/scoutApi.js`.

Every colour, glyph and threshold in the prototypes was lifted from a real repo file. Where a prototype shows something the repo cannot supply yet, it is called out here and in `BUILD_PLAN.md`.

## Fidelity

**High fidelity.** Final colours, typography, spacing and layout. Recreate pixel-for-pixel using the codebase's own token classes. Screens were designed at a 1440px-wide desktop frame; the sidebar collapses to a drawer below `lg`, exactly as `ModuleLayout` already does.

## Design Tokens

All from `frontend/src/styles/theme.css` unless noted. Dark theme values shown; every token has a light-theme counterpart under `[data-theme="light"]`, and the design must work in both (`bg-pb-*` / `text-pb-*` classes handle this automatically).

### Surfaces and text (dark)

| Token | Hex | Use |
| --- | --- | --- |
| `--pb-bg` | `#0a0d14` | page background |
| `--pb-surface` | `#10141d` | cards, sidebar, header |
| `--pb-surface2` | `#161b27` | inputs, chips, inset rows |
| `--pb-hairline` | `#1d2331` | 1px dividers, card borders |
| `--pb-hairline2` | `#262d3d` | secondary button borders |
| `--pb-text` | `#e6e8ef` | primary text |
| `--pb-dim` | `#8a90a2` | secondary text |
| `--pb-faint` | `#5b6072` | tertiary / mono labels |
| `--pb-faintest` | `#3a3f50` | disabled, captions |

### Module brand

BetterScout's accent is **magenta-violet `#C026D3`**, `accentRgb` `192 38 211`. It is new — add it to `MODULE_BRAND` in `frontend/src/lib/moduleBrand.js` under key `scout` (aliases `betterscout`, `scout`). BetterIQ keeps `#A855F7`; the two are deliberately in the same violet family (analytical cousins) but distinct.

Derived values used in the design:

- Active nav / accent text on dark: `#e879f9` (the ink-safe lighter step — implement via the existing `.pb-ink` / `--pb-accent-ink` mechanism, not a hardcode).
- Accent tint for nav rows and chips: `rgba(192,38,211,0.10)` background, `rgba(192,38,211,0.18)` for filled badges.
- Text on an accent fill: `#0a0d14` (matches `.pb-btn-primary`).

### Semantic + series colours

| Token | Hex | Use |
| --- | --- | --- |
| `--pb-positive` / `--pb-accent` (house green) | `#16c784` | positive delta, "match dated" badge |
| `--pb-negative` / `--pb-red` | `#ef5b5b` | destructive actions, at-cap warnings |
| `--pb-amber` | `#f5b542` | stale warnings, "billing not collecting" badge |
| `--pb-chart-wickets` | `#3b82f6` | wickets series in the season chart |
| Best cell | bg `rgba(34,197,94,0.14)`, text `#86efac` | comparison best value |
| Worst cell | bg `rgba(239,68,68,0.14)`, text `#fca5a5` | comparison worst value |

Comparison per-player identity colours are `PLAYER_COLORS` from `frontend/src/pages/PlayerComparison.jsx`, unchanged: `#3b82f6`, `#8b5cf6`, `#10b981`, `#f59e0b`, `#ef4444`.

Milestone category chips follow `frontend/src/pages/admin/AdminMilestones.jsx`: batting `#60a5fa`, bowling `#34d399`, fielding `#fbbf24`, matches `#c084fc`, each on a 10% tint with a 20% border.

### Typography

Per `tailwind.config.js`: `font-display` and `font-sans` → `var(--pb-font-display/body)` (Geist), `font-mono` → `var(--pb-font-mono)` (JetBrains Mono). All numbers, stat figures and eyebrow labels are mono; prose is Geist.

| Role | Spec |
| --- | --- |
| Screen title (`h1`) | 19px / 700 / `-0.01em`, `font-display` |
| Screen caption under title | mono 10.5px / uppercase / `0.08em` / `text-pb-faint` |
| Panel eyebrow | mono 10.5px / uppercase / `0.12em` / `text-pb-dim` |
| Table column header | mono 9–10px / uppercase / `0.1–0.14em` / `text-pb-faintest` |
| Body / table cell | 13.5px |
| Stat figure (profile) | mono 21px / 700 |
| Stat figure (comparison cell) | mono 14px / 700 |
| Big stat (overview tiles) | mono 24px / 700 |
| Sidebar nav item | 13.5px, 11px gap to a 17px icon |
| Chip / tag | 11.5–12px, `border-radius: 9999px` |

### Geometry

- Cards: `border-radius: 10px`, 1px `--pb-hairline`, `--pb-surface` background (this is `.pb-card`).
- Buttons: `border-radius: 8px`, padding `8px 14px`, 13px text (`.pb-btn`); small variants `6px 12px` / 12px.
- Inputs and selects: `border-radius: 6px`, padding `7–8px 10px`, `--pb-surface2` fill, 1px `--pb-hairline`.
- Sidebar: 232px fixed, 1px right hairline, `--pb-surface`; active nav row has a 2px right border in the accent plus the accent tint.
- Screen header: sticky, `--pb-surface`, bottom hairline, padding `14px 20px`.
- Main content padding: `20–22px 24px 28px`; two-column screens use `grid-template-columns: 1fr 372px` (Overview), `1fr 356px` (Profile), `1fr 1fr` (Settings), gap 20px.
- Panel internal gaps: 20px between cards, 12–16px inside them.
- Avatars: circular, 30/32/34/36/44px depending on context, initials centred at ~0.36× diameter, white on the identity colour.
- Progress bars: 6px tall, `border-radius: 9999px`, `--pb-surface2` track, accent fill.

## Screens / Views

Route prefix is `/betterscout/app`. All six sit inside the new module shell.

### Shell (all screens)

**Purpose:** make BetterScout read as a Better module.

**Sidebar (232px), top to bottom:**

1. **Org block** (padding 16px, bottom hairline): 32px rounded-5px tile with the org initial on an accent tint, then org name (14px/700) and a mono 10px `SCOUT ORG · 2026/27` line in `--pb-faintest`. Below it, on a 12px gap, the module lockup: 26px mark + "Better" + "Scout" in the accent. **The BetterScout mark does not exist upstream** — the prototype uses an accent tile with an "S". Produce a `betterscout.svg` in `frontend/src/assets/modules/` in the style of the four bundled marks and wire it through `moduleBrand`.
2. **Nav** (`padding: 8px 0`), each row `display:flex; align-items:center; gap:11px; padding:9px 16px`, 13.5px, inactive `text-pb-faint`, active = accent ink + accent tint + 2px accent right border. Icons are `Icon` names from the existing set:

   | Item | Route | Icon | Badge |
   | --- | --- | --- | --- |
   | Overview | `/betterscout/app` (exact) | `overview` | — |
   | Discover clubs | `/betterscout/app/discover` | `search` | — |
   | Watchlists | `/betterscout/app/watchlists` | `cols` | — |
   | My players | `/betterscout/app/players` | `teams` | tracked count, amber tint |
   | Compare | `/betterscout/app/compare` | `ladders` | — |
   | Milestones | `/betterscout/app/milestones` | `selection` | in-reach count, accent tint |
   | Settings | `/betterscout/app/settings` | `settings` | — |

   Then a mono 10px `NOT BUILT YET` heading and two disabled rows in `--pb-faintest`: **Player name search** (`search`) and **Hot form feed** (`bolt`). These are deliberately visible and dead — see `BUILD_PLAN.md`.
3. **Footer** (top hairline, `padding: 11px 12px`): mono 9px `SWITCH MODULE` label, then the compact `ModuleSwitcher` pills (14px mark, 4px radius, 6px gap, `4px 8px` padding, 999px radius, 11.5px label; active pill = brand colour at 14% background / 38% border). Below a hairline, a 24px initials avatar and the signed-in user's name, plus the log-out control.

**Header:** title + mono caption on the left, right-aligned stat readouts and the primary action. Overview shows `IN PIPELINE 11` and `OFFER OUT 3` readouts and a `Find players` primary button.

### 1a — Overview

**Purpose:** answer "who should I contact this week?" instead of listing four links.

Left column (`1fr`):

- **Form movers** card. Header: eyebrow `FORM MOVERS` + 12px explainer "last season vs. the two before, among players you track" + right-aligned `See all 38 →`. Rows (padding `12px 16px`, hairline between): 36px avatar; name 14px/600 with a 12px `Club · Grade · Role` line; a 5-bar sparkline (7px wide bars, 3px gap, 34px tall, `--pb-hairline2` for seasons outside the window, `--pb-dim` for the previous one, accent for the last two); right-aligned mono 14px figure with a `▲/▼ delta` in green and a mono 10px metric label; an `Open` ghost button.
- **Going stale** card. Header explainer "tracked, but no stats refresh or note in 6+ weeks" and a `Refresh all 5` ghost button. Rows: 30px avatar, name + `Club · stage · watchlist` line, an amber mono note (`stats 9 wks old`, `no note, 11 wks`), and a per-row `Refresh` / `Add note` / `Edit` action. Manual players get a dashed-border avatar and the mono note `manual entry` (nothing to refresh).

Right column (372px):

- **Plan usage**: eyebrow `GROWTH PLAN`, mono `38 / 100`, 6px progress bar, 12px caption "Priced by players actively tracked. 62 slots left — archive someone to free one up."
- **Clubs you've looked at**: four rows, club name 13.5px/600 + mono 11px `47 players · cached 3 days ago`, right-aligned `Open roster →` in accent ink. A stale cache shows the mono line in amber and the action becomes `Rebuild →`.
- **Not built yet** card, dashed `--pb-hairline2` border: mono `NOT BUILT YET` eyebrow, "Search a player by name, anywhere in Australia", the explanation, a dead search field (`--pb-bg` fill, `--pb-faintest` placeholder), and a closing line noting the same applies to a country-wide hot-form feed.

### 1b — Discover

**Purpose:** browse and cut a club's roster.

Header carries the club name and a mono caption `47 players · 6 grades · built from Cricket Australia records, 3 days ago`, plus a "Search another club…" field and a `Rebuild roster` ghost button.

- **Window row**: mono `WINDOW` label + a 4-segment control (`1 SEASON` / `2 SEASONS` / `5 SEASONS` / `FULL`) in a single 8px-radius bordered group, active segment filled accent with `#0a0d14` text; a 12px caption "2024–2025 only". This is the existing `WINDOW_OPTIONS` from `seasonRollup.js`, restyled.
- **Presets row** (right-aligned): mono `PRESETS` + pill filters `Bat avg 35+`, `Bowl avg <25`, `SR 85+`, `All-rounders`, `10+ matches`. Active pill = accent border + accent ink.
- **Filter bar** card: mono `FILTERS` label, then applied filters as removable chips (`Avg 35 – ∞`), then dashed "+ Runs / + SR / + Wkts / + Bowl avg / + Econ" add-buttons, then a right-aligned mono `9 OF 47 PLAYERS` and an underlined `Clear`. This replaces today's 7×(min,max) input grid — same fields, far less chrome.
- **Roster table**: columns Player, Form, Mat, Runs, Avg, SR, Wkts, Bowl, Econ, action. Header cells mono 10px uppercase; the sorted column is accent with a `↓`. Body rows 13.5px, all figures mono and right-aligned. The Player cell is a 32px avatar + name/600 + mono 10.5px `1ST GRADE · RHB TOP ORDER · 24y`. The Form cell is a 5-bar 20px sparkline of the sorted metric. Action is either a filled accent `Track` button or accent-ink `Tracked ✓`.
- **Expanded row** (clicking a row), `--pb-surface2` background: a 78×96 dashed **photo slot** (avatar + mono `NO PHOTO IN CA DATA`), a 5-across stat grid (High score, 50s/100s, Best figures, Catches, Grades played), a per-season table **including a Grade column**, and a 196px action stack: `Open full profile` (primary), `Add to watchlist ▾`, `Add to compare`, and a mono `ON 2 WATCHLISTS` line.
- Footer caption, mono 10.5px `--pb-faintest`: "FORM COLUMN = LAST 5 SEASONS, THE SORTED METRIC · GREY BARS FALL OUTSIDE THE CHOSEN WINDOW".

### 1c — Player profile

**Purpose:** everything a recruiting decision needs on one screen.

Header: 76×92 dashed **photo slot** (avatar + mono `DROP PHOTO OR PASTE URL`), name 22px/700, `Club · Grade · Competition`, then attribute chips (role, batting hand, bowling, region) in `--pb-surface2` and scout tags (`priority`, `visa ok`) as accent-outlined chips. Right side: `Refresh stats` / `Share profile` ghost buttons + `Compare` primary; underneath, a mono `UK 2026/27 STAGE` label and a 4-segment stage control (`LONGLIST` / `CONTACTED` / `OFFER OUT` / `SIGNED`) with the current stage filled accent.

Left column:

- **Discipline card** with a tab bar (`BATTING` / `BOWLING` / `FIELDING` / `CAREER`, active = 2px accent underline, mono 11px) and, right-aligned inside the tab bar, window pills (`1 SEASON` / `5 SEASONS` / `FULL`).
- 6-across stat grid: Innings, Runs, Average (accent), Strike rate, High score, 50s/100s — mono 21px/700 figures over mono 9.5px uppercase labels.
- **Season chart**: 120px-tall paired bars per season, 22px wide, 4px apart, 26px between seasons — runs in accent, wickets in `#3b82f6`; seasons outside the active window at 55–80% opacity. Legend chips above; under each pair, the mono year and the **grade played that season** (current-grade seasons in `--pb-text`, lower grades in `--pb-faint`).
- **Season table**: Season, Grade, Mat, Runs, Avg, SR, HS, Wkts, Econ.

Right column (356px):

- **Recruiting** card: eyebrow + a mono `NEVER SHARED` badge; five labelled read/write fields (Visa / eligibility, Transfer preference, Availability, Fee expectations, Agent / contact) styled as `--pb-surface2` inputs; closing 11.5px note "These five fields stay internal — a shared profile carries stats, tags and notes only."
- **Scouting notes** card: eyebrow + `+ Add note`; each entry is a mono 10px `14 FEB 2026 · DAN WILSON · WATCHED LIVE` line over 13px prose.
- **On watchlists** card: one row per watchlist with a mono stage pill (current board's stage in accent tint, others neutral), and a `+ Add to another watchlist` action.

### 1d — Compare

**Purpose:** head to head, matching the club-side page scouts already know (`frontend/src/pages/PlayerComparison.jsx`).

- Header eyebrow `HEAD TO HEAD`, title "Compare players", right-aligned mono `UP TO 5 PLAYERS · GREEN = BEST · RED = WORST`.
- **Selection card**: one chip per selected player — 34px avatar, name in that player's identity colour, mono 9px `Role · Club` line, and a `×`. Then a 192px "Add tracked player…" search field.
- **Window bar**: mono `WINDOW` + preset buttons `ALL TIME` (active, accent fill) / `THIS SEASON` / `LAST SEASON` / `LAST 2 SEASONS` / `LAST 5 SEASONS`, with a right-aligned 12px caption explaining that BetterScout has season rollups, not ball-by-ball, so the club page's "last 3 games" presets are absent.
- **Comparison card**: tab bar `BATTING` / `BOWLING` / `FIELDING` / `GAMES` / `RECRUITING`. Table is `table-layout: fixed`, a 180px stat column plus one column per player, each column separated by a left hairline. Column headers are a 44px avatar + name in the identity colour + mono 9px `Role · age`. Rows: mono 10px stat label on the left; values mono 14px/700 centred; unique best/worst cells tinted green/red per `getRowHighlights` (ties unmarked).
- Footer: mono `GREEN = BEST · RED = WORST · ALL TIME · TIES UNMARKED`, plus `Export as one-page PDF` and `Share read-only link` ghost buttons.
- A dashed note card describes the `RECRUITING` tab: compares visa, availability, fee and stage, internal only, stripped from shares and exports.

### 1e — Milestones

**Purpose:** give a scout a reason to make contact — and a club a reason to talk.

Header caption: `6 in reach · 4 reached since your last visit · across 38 tracked players`. Filters in the header: status segments (`IN REACH` / `REACHED` / `ALL`), category segments (`ALL` / `BATTING` / `BOWLING` / `FIELDING` / `MATCHES`), and a player search field — same filter vocabulary as `AdminMilestones.jsx`.

- **Season counters**: four cards across — `FIFTIES, 2025/26 SO FAR` 31, `HUNDREDS` 6 (accent) with "2 by U21 players", `FIVE-WICKET HAULS` 9 with "best 6/31 — Ravi Doshi", `MILESTONE GAMES AHEAD` 3 with "100th, 150th and 200th caps".
- **Milestones in reach** table: Player (30px avatar + name + mono `CLUB · STAGE`), Category chip, Milestone (label + mono detail line), Progress (80px bar + mono %, with `147 / 150` beneath), To go (mono 14px/700, accent when genuinely imminent, `--pb-dim` when far), and an `Add note` action. Header explainer states the thresholds verbatim: "runs 500 then every 1,000; wickets 50 then every 100; games and catches every 50."
- **Reached recently** table: Player, Category, Milestone, Grade, When, Source. `When` is either an exact date (`7 Feb 2026`) or a season (`2025/26 season`). `Source` is a mono badge: green `MATCH DATED` or neutral `SEASON ONLY`. A footer note explains why: public CA data gives season totals, so a milestone can be placed in a season but not on a date; players at clubs already on BetterCricket get the exact match. Header carries `Mark all as seen`.
- A dashed **not built yet** card: real-time alerts need scheduled crawling; today the page recomputes on visit from the last refresh, and the cadence lives in Settings.

### 1f — Settings

**Purpose:** the org, the plan, the data rules, the sharing rules.

Header caption `Wilson Sports Management · growth plan · 3 seats`; right side shows "Last saved 2 minutes ago" and a `Save changes` primary button.

Left column:

- **Organisation**: 64px dashed logo slot, Organisation name field, and two selects — Org type (`Recruiting agency`) and Home region (`WA`). Footer note: org type only sets defaults, and scout orgs never see club-admin data.
- **Plan & usage**: amber mono badge `BILLING NOT COLLECTING YET`; "Growth — up to 100 tracked players" with mono `38 / 100` and a progress bar; three tier cards (`Starter 25 players`, `Growth · current 100 players` highlighted with an accent border and 6% tint, `Unlimited No cap`); note that caps are enforced today and a 101st player is blocked; `Request an upgrade` and `Archive players to free slots` buttons.
- **People**: rows for each `ScoutUser` (30px initials avatar, name + email, mono role pill `OWNER` in accent tint / `SCOUT` neutral) plus a pending invite row (dashed avatar, "Invited 3 days ago · read-only", `Resend`). Header has `+ Invite`.

Right column:

- **Data & refresh**: refresh cadence segmented control (`DAILY` / `WEEKLY` / `MANUAL`), "Call a player stale after" select (`6 WEEKS`) noted as driving the Overview panel, "Default career window" select (`LAST 2 SEASONS`), and a note that BetterScout pulls roughly ten seasons per player and says so wherever a total is shown.
- **Sharing defaults**: three toggles — include notes (on), include tags (on), include recruiting fields (off and visually disabled, with "Visa, fee, agent and availability never leave the org") — plus a share-expiry select (`90 DAYS`) and a live-links row (`4 links live now`, `Manage links`, red-outlined `Revoke all`). Toggle spec: 38×21px pill, accent when on, `--pb-surface2` + `--pb-hairline2` when off, 15px knob.
- **Milestone alerts**: weekly digest toggle (on) with "Monday morning: milestones reached, in reach, form movers", an "Alert me within" select (`HOUSE DEFAULT`), a "Only players on a watchlist" toggle (off), and a note that real-time alerts wait on scheduled crawling.
- **Danger zone**: red-tinted card — "Close this Scout Org", "Deletes watchlists, notes and share links. Cached club rosters stay — they aren't yours.", red-outlined `Close org`.

## Interactions & Behavior

- **Nav**: active state by route (`exact` for Overview). The two `NOT BUILT YET` rows are non-interactive and must not be links.
- **Discover**: window and preset changes are **client-side only** — `rollupSeasons()` in `frontend/src/scout/lib/seasonRollup.js` recombines each player's seasons from the raw counts already in the roster payload, so switching never refetches or rebuilds. Sorting is client-side, `desc` first, second click flips to `asc`, numbers before nulls in either direction. Row click toggles the expanded detail; the action button must `stopPropagation`.
- **Roster building**: first load of an uncached club returns `status: "building"`; poll every 2500ms, 60 polls max, then show a timeout error. Keep today's copy: "Building this club's roster from Cricket Australia's records — first load can take up to a minute…".
- **Track**: adding stays put — the scout keeps working down the same list; the row's action flips to `Tracked ✓` with a `View profile →` link. At the plan cap, the button is disabled with the tooltip "You've reached your plan's player limit." and the banner from today's screens appears at the top.
- **Stage control** (profile): optimistic move, reconcile on failure by reloading the board — same approach as today's `onDrop`.
- **Watchlist board** (unchanged from today, keep as-is): drag a card between columns, optimistic move, card lands at the end of the target column; inter-card reordering is not wired up.
- **Compare**: selection is held in the query string (`?players=id,id`) so a comparison is linkable. Fewer than two selected shows the empty state; one selected shows "Pick at least one more player to compare."
- **Milestones**: filters are client-side over one payload. `Mark all as seen` clears the "since your last visit" count.
- **Settings**: dirty-state tracking with the header `Save changes` button; destructive actions confirm.
- **Transitions**: 120ms ease on colour/background/border (matches `.pb-btn`); panels enter with the existing `ch-rise` keyframe (180ms).
- **Responsive**: sidebar becomes an off-canvas drawer behind `☰` below `lg`, per `ModuleLayout`. Two-column mains stack; tables scroll horizontally in a `overflow-x-auto` wrapper.
- **Loading / error / empty**: keep today's plain-text patterns (`Loading…` in `text-pb-dim`, errors in `--pb-negative`, empty states with an inline link to Discover).

## State Management

Per screen, on top of what `frontend/src/scout/pages/*` already holds:

- **Overview**: one fetch of an overview payload (form movers, stale players, recent clubs, usage). No local state beyond loading/error.
- **Discover**: existing state (`query`, `clubs`, `club`, `roster`, `addedPlayers`, `expandedId`, `windowN`, `clientSort`, `filters`) plus `activePresets` and the applied-filter chip list.
- **Profile**: `player`, `activeTab`, `windowN`, `refreshing`, notes list, watchlist memberships, and per-field dirty state for the recruiting panel.
- **Compare**: `players` (all tracked), selected ids from the query string, `activeTab`, `windowN`.
- **Milestones**: payload (`in_reach`, `reached`, `season_counters`), plus `status`, `category`, `search`.
- **Settings**: one settings object with a dirty flag, the user/invite list, and live-share-link count.

Data fetching stays in `scoutApi.js` — add the new endpoints listed in `BUILD_PLAN.md` there, and nowhere else.

## Assets

| Asset | Where it came from |
| --- | --- |
| `frontend/src/assets/modules/betterstats.svg`, `betterselect.svg`, `betteradmin.svg`, `betteriq.svg` | Copied verbatim from the repo; used at 14px in the sidebar switcher. |
| `betterscout.svg` | **Does not exist yet.** Needs designing in the same style; the prototype substitutes an accent tile with an "S". |
| Nav and UI glyphs | The existing `Icon` component's `ICON_PATHS` in `frontend/src/pages/admin/betterselect/ui.jsx` (`overview`, `search`, `cols`, `teams`, `ladders`, `selection`, `settings`, `bolt`). Nothing was drawn by hand — use the component, don't inline the paths. |
| Player photos | None exist in Cricket Australia's public data. Every player slot in the design is a reserved frame that falls back to an initials avatar; see `BUILD_PLAN.md` for the upload path. |
| Fonts | Geist + JetBrains Mono, already loaded by the app via `--pb-font-*`. |

## Files

- `BetterScout Redesign.dc.html` — the target design, screens `1a`–`1f`.
- `BetterScout Today.dc.html` — the current UI, for comparison.
- `support.js` — runtime for the two prototype files (not for production).
- `frontend/src/assets/modules/*.svg` — the four real module marks.
- `BUILD_PLAN.md` — what exists, what's new, and what is deliberately unbuilt.

Open either `.dc.html` in a browser to view it. Sample data throughout is Applecross Cricket Club and a fictional agency, "Wilson Sports Management".
