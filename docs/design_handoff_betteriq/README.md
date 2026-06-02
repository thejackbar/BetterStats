# Handoff: BetterIQ — UX/UI review package

## What this is
A self-contained package describing **BetterIQ**, the analytics + scouting module
of **BetterStats**, so a designer (Claude Design) can do a **UX/UI review of what
already exists**. Unlike the sibling `docs/design_handoff_betterselect/` package
(which was a redesign *spec* with mock prototypes), this documents the **live,
shipped module** — every screen, its purpose, layout, data, states and copy — and
bundles the **actual source** so you can read the real markup and styling without
the repo.

> **This is a review, not a rebuild.** The goal is a critique: information
> architecture, visual consistency, hierarchy, density, flows, empty/loading/error
> states, mobile, accessibility, and where the experience can be sharpened. A list
> of observations I already have for you is in **§10 — Suggested review focus**.

It targets the repo **`thejackbar/BetterStats`** → `frontend/` (React + Vite +
Tailwind) and `backend/` (FastAPI + SQLAlchemy + PostgreSQL). The module lives
under `/admin/betteriq/*`. Root `CLAUDE.md` has the deep architectural notes (the
"BetterIQ —" sections); this package is the design-facing summary.

### What's in the bundle
```
docs/design_handoff_betteriq/
  README.md                  ← this document (the review brief)
  screens/                   ← byte-identical snapshots of the live screens (read-only)
    IQLayout.jsx               module chrome: sidebar nav + header + the violet theme override
    BetterIQHome.jsx           Overview / landing
    OppositionScout.jsx        "Opposition club" — the flagship scouting report
    KeyPlayersCard.jsx         the danger-player showcase card used by the scout
    OppPlayerProfile.jsx       shared opponent-player profile + scouting-tag editor
    OppositionPlayer.jsx       "Opposition player" — club → player search
    SelectionAnalysis.jsx      analyse a saved BetterSelect XI
    PlayerTrends.jsx           our players' trajectories + deep dives
    TeamAnalysis.jsx           our team self-analysis (tabbed)
    MatchReview.jsx            post-match read of a completed game
    MatchPreview.jsx           pre-game one-pager for an upcoming fixture
    CheatSheet.jsx             print-ready captain's cheat sheet (intentionally off-theme)
  system/
    theme.css                  the pb-* design tokens (light + dark)
    shared-ui.jsx              the shared atom kit (Icon/Btn/Tag/Search/Segmented/Empty…)
    iq-router.py               the full backend API surface (endpoint → service map)
```
Snapshots are **read-only copies** — the canonical files live at the paths given
in §11. Don't edit the copies.

---

## 1. What BetterIQ is

BetterStats is a white-label platform for **community / grassroots cricket clubs**:
it ingests a club's full match history from Cricket Australia, reconciles it into
clean stats, and powers a public site + admin tools. It's sold in **Good / Better /
Best** tiers, with bolt-on modules (BetterSelect, BetterSocials, BetterFees,
BetterIQ).

**BetterIQ is the "analytics brain" — the top (Best) tier module.** Its pitch
(verbatim from the landing hero):

> *"Your club's analytics brain. The deep-dive most clubs — and plenty of pro
> teams — don't have. BetterIQ reads the data the Core already holds and pulls
> opponent data live from the same source, no manual entry."*

It turns a club's scorecard history into **selector- and captain-grade intelligence**:
scout an upcoming opponent, justify/critique a team selection, track player
development, understand how the club itself wins and loses, preview a match and
review it afterwards.

**Who uses it:** club admins, selectors and captains — *not* the general public.
It's gated twice (see §2). Think "the analyst's room," not a fan-facing page.

### The single most important design constraint — the data ceiling
The club holds **scorecard-level data, not ball-by-ball.** So BetterIQ can do
runs / wickets / averages / strike-rate / dismissal-type / by-position /
by-opposition / by-venue / partnerships / form — but **cannot** do phase analysis,
ball-by-ball matchups, pressure/win-probability, or dot-ball %. The product is
**honest about this**: most screens carry a faint "coverage note" footer spelling
out what the numbers can and can't say. Preserving that honesty (without it
becoming visual clutter) is a real UX tension to weigh.

### Identity: the violet "brain" accent
Every other surface in BetterStats inherits the **club's** white-label accent
(often green, sometimes an alarming red). BetterIQ deliberately **overrides
`--pb-accent` to a fixed violet `#8b7cf6`** for the whole module (set once on the
`IQLayout` root, inherited by every child). This is the module's signature — it
reads as a distinct "BetterStats product" surface, not the club's site. See
`screens/IQLayout.jsx` lines 75–82.

---

## 2. How to reach it (gating + entry points)
- **Module entitlement**: the club's subscription must include the `iq` module
  (bundled at the **Best** tier). Enforced where the router is mounted
  (`require_module("iq")`) and on the route (`<ProtectedRoute requireModule="iq">`).
- **Capability**: the signed-in user needs the **`MANAGE_IQ`** capability
  (`club_admin` / `super_admin` have all caps). Every `/iq/*` API route is gated on it.
- **Dashboard tile**: on `/admin`, the admin dashboard renders a **BetterIQ tile**
  (`MODULE_INFO` in `lib/modules.js`) — *"AI + stats deep-dive: opposition scouting,
  selection analysis, trends."* When the module is `built: true` (it is), the tile
  opens the module; otherwise it shows "Coming soon."
- **Within the module**: a persistent left **sidebar** (the `IQLayout`) with its own
  nav, plus a "← Back to admin" link.

---

## 3. Design system & chrome

BetterIQ reuses BetterStats' **"Press Box" theme** and the BetterSelect **atom kit** —
it does *not* introduce its own component library (with one deliberate exception,
the print cheat sheet).

### 3.1 Tokens (`system/theme.css`)
Theme-aware CSS variables (the app flips light/dark via a `data-theme` attribute).
**Never hard-code hex — use the tokens.** Dark values shown for reference:

| Token | Var | Dark |
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
| **Accent** (module-overridden to violet) | `--pb-accent` | `#8b7cf6` in BetterIQ |
| Brand green (results = win) | `--pb-brand` | `#16c784` |
| Red / negative / loss | `--pb-red` | `#ef5b5b` |
| Amber / caution / draw | `--pb-amber` | `#f5b542` |
| Chart blue (bowling/wickets) | `--pb-chart-wickets` | `#3b82f6` |

- **Accent vs result colours**: a deliberate split worth noting. The module
  *accent* is violet (`--pb-accent`), but **match results stay semantic** — wins use
  `--pb-brand` green, losses `--pb-red`, draws/ties `--pb-amber`. So a screen mixes
  violet (UI chrome / "our bars") with green/red (outcomes). Review whether that
  dual palette ever reads ambiguously.
- **Fonts**: `font-display` (Geist, used for headings + big numbers), `font-body`
  (Geist), `font-mono` (JetBrains Mono, used for "eyebrow" micro-labels + tabular
  figures). `.pb-num` = tabular-nums, applied to almost every stat.
- **Card**: `.pb-card` = `--pb-surface` + 1px `--pb-hairline` + **6px radius**.
  Accent-bordered cards use `color-mix(... var(--pb-accent) 30% ...)`.
- **Eyebrows**: mono, ~10px, uppercase, wide tracking, `--pb-faint` — used for
  section kickers and stat units.

### 3.2 Module chrome — `IQLayout` (`screens/IQLayout.jsx`)
Wraps every screen. Desktop: fixed 240px left sidebar (club logo + "BetterIQ"
wordmark, nav list, back-to-admin) + sticky header (page title left; optional
`actions` slot + user/logout right). Mobile (`< md`): sidebar collapses behind a
`☰` button into an overlay drawer. Main content is capped at `max-w-[1400px]`.
Active nav item = accent text + accent left/right bar + tinted bg.

### 3.3 The shared atom kit (`system/shared-ui.jsx`)
Imported from BetterSelect's `ui.jsx`. The pieces BetterIQ uses:
- `Icon` — simple line glyphs (`overview, fixtures, teams, player, selection,
  ladders, search, check, share, bolt, back, info, list…`). All `stroke=currentColor`.
- `Btn` (variants `primary / ghost / soft / danger`, `sm`, optional `icon`),
  `Tag` (tones `accent / amber / faint`), `Search` (input), `Segmented` (control),
  `Empty` (muted placeholder). `Avatar` / `Dot` exist but BetterIQ leans on text.

### 3.4 Recurring composition patterns (NOT shared — see §10)
Almost every screen **re-declares its own local** `Card({title,right,children,accent})`,
`Stat({label,value,sub,tone})`, `Note({children})` (footnote), and `num()/fmt2()`
formatters. They're near-identical copies. Visually the module is consistent
*because* these are faithfully duplicated — but it's a real consistency risk and a
review point. The common page skeleton:

```
IQLayout(title)
  → optional intro <p> (one sentence, text-pb-faint, max-w-2xl)
  → picker/filter row
  → grid of pb-card "Card"s (1 col mobile → lg:grid-cols-2/3)
      each Card: bold display title + optional right-side meta/segmented
      content: Stat clusters, thin accent progress bars, dense tables, or bullet lists
  → faint "coverage note" footer (what the data can't say)
```

### 3.5 State conventions
- **Loading**: a `pb-card` with `animate-pulse` + grey text ("Loading…", "Crunching
  our games…", "Analysing the XI…"). The live dossier additionally shows a **violet
  spinner** card while building.
- **Empty**: `<Empty>` muted message, often with a CTA.
- **Error**: a `pb-card` with `<Empty>` and a recovery hint ("…try Refresh in a
  moment").
- **Async dossier**: poll-driven `building → ready/error/unavailable` (see §9.3).

---

## 4. Information architecture & navigation

The sidebar `NAV` (in `IQLayout.jsx`) — order as shipped:

| # | Label | Route | Icon | Screen file |
|---|---|---|---|---|
| 1 | Overview | `/admin/betteriq` | overview | `BetterIQHome.jsx` |
| 2 | Match preview | `/admin/betteriq/preview` | fixtures | `MatchPreview.jsx` |
| 3 | Opposition club | `/admin/betteriq/opposition` | search | `OppositionScout.jsx` |
| 4 | Opposition player | `/admin/betteriq/opposition-player` | ladders | `OppositionPlayer.jsx` |
| 5 | Selection | `/admin/betteriq/selection` | selection | `SelectionAnalysis.jsx` |
| 6 | Player trends | `/admin/betteriq/trends` | ladders | `PlayerTrends.jsx` |
| 7 | Team | `/admin/betteriq/team` | teams | `TeamAnalysis.jsx` |
| 8 | Match review | `/admin/betteriq/review` | overview | `MatchReview.jsx` |

Plus two routes **not** in the sidebar (reached contextually):
- `/admin/betteriq/opposition/cheatsheet` → `CheatSheet.jsx` (from a "Cheat sheet"
  button on the scout / preview).
- `OppPlayerProfile.jsx` is not a route — it's the shared profile component embedded
  in both Opposition screens.

> **IA note for review:** the **Overview** page frames the module as **5
> "capabilities"** (Opposition analysis, Selection analysis, Player trends, Team
> analysis, NL Q&A) — but the **sidebar has 8 items** and splits/refactors those
> differently (two Opposition entries; Match preview + Match review are first-class
> in the nav but not presented as "capabilities" on the home page). The mental model
> the landing page sets up and the one the nav presents don't line up. See §10.

---

## 5. Screen-by-screen

Notation: **Route** · **Entry** (how you get here) · **Purpose** · **Layout** ·
**States** · **Data** (API). All screens are wrapped in `IQLayout`.

### 5.1 Overview — `BetterIQHome.jsx`
- **Route** `/admin/betteriq` · **Entry** dashboard tile / nav "Overview".
- **Purpose** orient + jump off: scout the next opponent, see club MVPs, enter a capability.
- **Layout** (single column):
  1. **Hero** — accent-tinted `pb-card`, bolt icon, "Your club's analytics brain" + the pitch sentence.
  2. **"Scout your next opponent"** — up to 4 upcoming fixtures as clickable cards
     (opponent, date, H/A, team, venue; a `History`/`New` tag); click → Opposition
     scout pre-seeded. Empty state points to BetterSelect/Opposition.
  3. **Club MVPs** — a blended 0–100 player-impact board: rank, name, role, an accent
     progress bar, the score + `r/w/f` line; rows deep-link to Player trends. A
     `Note` explains it's a whole-season value measure (not current form).
  4. **Capabilities** — 2-col grid of the 5 capability cards (`Live` tag, or `SOON`
     for NL Q&A which renders at 60% opacity).
- **States** skeleton while fixtures/MVP load; graceful empties.
- **Data** `iqListOpponents()` (`.upcoming`), `iqTeamMvp()`.

### 5.2 Opposition club — `OppositionScout.jsx`  ★ flagship, most complex
- **Route** `/admin/betteriq/opposition?fixture=…|opponent=…` · **Entry** nav,
  Overview cards, Match preview. URL-stateful (deep-linkable).
- **Purpose** a full scouting dossier on one opponent club: who they are, how we've
  fared, their current squad & danger men, and a "how to beat them" plan.
- **Two-phase data model** (important UX behaviour):
  - **Instant report** (`iqOppositionReport`) — from data we *already hold*; renders
    immediately: head-to-head, our record vs them, last meeting, venue record,
    bowler match-ups.
  - **Live dossier** (`iqOppositionDossier`) — *fetched live* from the opponent's
    recent scorecards; **built in the background** and **polled** (2.5s) → shows a
    "Building their dossier…" spinner (can take up to ~a minute first time), then
    fills in: game plan, danger batters/bowlers, win/lose, dismissal + partnership
    maps, full squad tables. A **Refresh** button forces a rebuild.
- **Layout** is two distinct views:
  - **Picker** (no opponent chosen): "Upcoming" fixture chips (with a **Match club**
    affordance for fixtures whose free-text opponent name didn't auto-resolve to a
    club — opens a modal to link them) + searchable "All opponents" grid (`Synced` tag
    on rich-history clubs).
  - **Report** (opponent chosen): opponent header (mono "Scouting report" eyebrow +
    big name) + **Cheat sheet** / **Refresh** actions. Then, top→bottom: Head-to-head
    + Our record (2-col) · Last meeting · Venue + Bowler match-ups (2-col, with a
    **Matrix/List toggle** — the match-up matrix is a bowler×batter dismissal
    heatmap) · a **Team selector** (whole-club vs each of their grades) that re-scopes
    the live dossier · the game-plan card · **Key players** showcase cards (danger
    batters/bowlers, see 5.3) · **Scout a player** (embedded search → `OppPlayerDetail`) ·
    How they win/lose · How-they-get-out + partnership "where they wobble" · historically
    dangerous players · the full **Squad** table (Batting/Bowling segmented) · coverage note.
- **States** picker-loading; "no history matched" banner (with Match-club CTA);
  dossier building/unavailable/error each have their own card.
- **Data** `iqListOpponents`, `iqOppositionReport`, `iqOppositionDossier` (poll),
  `iqRefreshDossier`, `iqMatchOpponent`.

### 5.3 KeyPlayersCard — `KeyPlayersCard.jsx` (component, used by 5.2)
A "showcase" card adapted from a Uiverse crypto-card: a **segmented toggle** (top 5
players, sliding pill) → a featured panel (name, headline runs/wkts, avg/SR or
avg/econ, record vs us) → an **animated SVG sparkline** of recent form → a rule-based
scouting note with **Danger / "Paper tiger?"** alert badges, a recommended **Plan**,
a **risk** badge and a **confidence** chip. The most visually "designed" element in the
module — worth a close look for whether its richness fits the surrounding density.

### 5.4 Opposition player — `OppositionPlayer.jsx` (+ `OppPlayerProfile.jsx`)
- **Route** `/admin/betteriq/opposition-player` · **Entry** nav.
- **Purpose** scout one opponent **player** across a club: pick an opponent club →
  search their players → full profile.
- **Layout** club combobox → (builds the same live dossier, polled) → player
  combobox → `OppPlayerDetail`: this-season batting + bowling mini-stats, recent
  form, dismissal-type chips, **their record vs us** (red/violet tinted blocks), and
  an **editable scouting-tag** panel (handedness, bowling arm/type, role, keeper,
  danger flag, free-text notes — persisted via `iqOpponentTags`/`iqSaveOpponentTag`).
  Vocab mirrors our own players' editor.
- **Note for review:** this overlaps the **"Scout a player"** block embedded inside
  5.2. Same `OppPlayerDetail` component, two entry points. Is the standalone page
  earning its sidebar slot, or should it fold into the scout?
- **Data** `iqListOpponents`, `iqOppositionDossier` (poll), `iqOpponentTags`, `iqSaveOpponentTag`.

### 5.5 Selection analysis — `SelectionAnalysis.jsx`
- **Route** `/admin/betteriq/selection?fixture=…` · **Entry** nav.
- **Purpose** "BetterSelect picks the team — BetterIQ checks the balance and justifies
  the pick." Analyse a **saved BetterSelect XI** for a fixture.
- **Layout** picker (fixtures with a saved lineup; "needs selecting" hint when none) →
  report: a one-line **verdict**; **XI balance** (Stat cluster: batters/all-round/bowlers/
  pace-spin/keeper/openers/LH-RH, amber/red when light) + **Selection check** warnings;
  the **XI table** (order, role, last-5 form, form avg, vs-opponent, availability dot,
  with up/down-a-grade + ineligibility flags); **Promote** (in-form, eligible, left out)
  vs **Watch** (ineligible/out of form); a **Suggested best available XI** (chips +
  consider-adding / picked-but-not-in-best). Coverage note.
- **Data** `iqSelectionLineups`, `iqSelectionAnalysis`. (Reuses BetterSelect's
  eligibility pool so suggestions match the selection board exactly.)

### 5.6 Player trends — `PlayerTrends.jsx`  (largest after the scout)
- **Route** `/admin/betteriq/trends?player=…` · **Entry** nav, Overview MVP rows.
- **Purpose** individual development + a deep statistical dive.
- **Two views**:
  - **Overview**: a current-season **player search** combobox + squad filter; **Form
    movers** (this season vs career-before-it, 4 quadrants: batting/bowling × rising/
    declining, deltas coloured); an **Emerging — ones to watch** shelf.
  - **Detail** (player chosen): trend verdict tags; **Career** strip; **Recent form**
    (sparklines) + **Career shape** (peak seasons, consistency σ); **Closing in on**
    milestones (with ETA); **Season by season** table (with per-row runs bars). Then a
    **"Deep dive"** divider → starts & conversion, how-they-get-out, **reliability**
    (floor/median/ceiling percentiles), batting style, by-match-situation, **selection
    value** (team win% with vs without), **similar players**, by-position, by-opposition,
    at-venues. Then a **"Bowling deep dive"** divider → bowling profile, wicket quality
    (set/new), who-catches-for-them, discipline.
- **Note for review:** the detail view is **very long** (a dozen+ stacked cards). Strong
  candidate for sectioning/tabs/progressive disclosure — see §10.
- **Data** `iqTrendsOverview`, `iqTrendsPlayers`, `iqTrendsPlayer`, `iqPlayerDeepDive`,
  `iqBowlerDeepDive`.

### 5.7 Team analysis — `TeamAnalysis.jsx`
- **Route** `/admin/betteriq/team` · **Entry** nav.
- **Purpose** "the opposition lens, pointed at us" — how *we* win and lose.
- **Layout** prominent **Season** + **Team (grade)** dropdowns (defaults to latest
  season) → **tabbed** content (this is the one screen that already uses tabs):
  - **Overview**: Record · How we win / How we lose · Bat-first vs chase · "What score
    wins" (with a **par** score) + score-band win rates · By venue.
  - **Batting**: batting profile (+ where-runs-come-from bar) · our starts · partnerships
    by wicket · **best partnership pairs** · **collapse analysis**.
  - **Bowling**: bowling summary · **attack structure** (pace/spin mix + per-bowler
    roles) · **discipline** (extras) · **wicket-taking** quality.
  - **Players**: **captaincy** record · **role-adjusted batting** · **all-rounders** ·
    top fielders / keepers.
  Each add-on card carries a `Note` footnote explaining the method.
- **Data** `iqTeamSeasons`, `iqTeamGrades`, `iqTeamOverview(season,grade)`. (Backend
  wraps every optional card in a `_safe()` so one heavy/timing-out query can't blank
  the page — i.e. the page is designed to degrade gracefully.)

### 5.8 Match review — `MatchReview.jsx`
- **Route** `/admin/betteriq/review?game=…` · **Entry** nav.
- **Purpose** an automatic post-match read of a completed game.
- **Layout** a simple **list** of recent games (result dot, vs opponent, grade, date) →
  detail: scoreline (Us vs Them), **"What changed the game"** synthesis, top batting /
  top bowling tables, best partnership / extras / collapse trio. Coverage note.
- **Data** `iqReviewGames`, `iqGameReview`.

### 5.9 Match preview — `MatchPreview.jsx`
- **Route** `/admin/betteriq/preview?fixture=…|opponent=…` · **Entry** nav.
- **Purpose** a fast **pre-game one-pager** (uses the *instant* report, not the slow
  live dossier — so it's quick).
- **Layout** picker (upcoming fixtures + opponent search) → **The lean** (a synthesised
  bullet list) · Ladder (our row + theirs) + Head-to-head (2-col) · Last meeting ·
  Their danger players + Our edge (2-col) · links out to the **full scout** and the
  **cheat sheet**.
- **Data** `iqOppositionReport`, `iqOpponentLadder`, `iqTeamOverview` (for par/record).

### 5.10 Captain's cheat sheet — `CheatSheet.jsx`  ⚠ intentionally off-theme
- **Route** `/admin/betteriq/opposition/cheatsheet?opponent=…&fixture=…&team=…` ·
  **Entry** "Cheat sheet" button on the scout / preview.
- **Purpose** a **print-ready A4 one-pager** a captain can take onto the field.
- **Layout** a **light-themed** sheet (white paper, dark ink, violet accent) — composed
  entirely from the report + dossier already built (no new backend). Toolbar (Back +
  **Print / Save as PDF**) is `@media print`-hidden; the sheet has a header (opponent,
  record), a game-plan banner, and two columns (danger batters/bowlers + plans · our
  match-ups / win-lose / our edge).
- **Note for review:** this screen **deliberately ignores the pb-* dark system** and
  uses inline light-theme styles, because it's built to print. It's the one place the
  module steps outside its own design language — verify it still feels "of" BetterIQ
  and that the print output is clean. Polls the dossier (up to ~30s) like the scout.
- **Data** `iqOppositionReport`, `iqOppositionDossier` (poll).

---

## 6. Component inventory (notable)
- **Layout/chrome**: `IQLayout` (sidebar + header + violet override).
- **Repeated locally on most pages**: `Card`, `Stat`, `Note`, `num/fmt2`. *(Not shared —
  see §10.)*
- **Bespoke**: `KeyPlayersCard` (segmented showcase + animated sparkline + alerts);
  `MatchupMatrix`/`buildMatrix` (bowler×batter heatmap, in the scout); `Sparkline`
  (bar) in trends + `sparkPath` (SVG line) in KeyPlayersCard — **two different
  sparkline implementations**; `OppPlayerDetail` + `ScoutingTags` + `TagBadges`
  (shared opponent profile, `OppPlayerProfile.jsx`); `MatchOpponentModal` (link a
  fixture to a club); thin **accent progress bars** (used everywhere for shares/rates);
  segmented "stacked" bars (`How they get out`, conversion, where-runs-come-from).
- **From the atom kit**: `Icon, Btn, Tag, Search, Segmented, Empty`.

---

## 7. Backend / API surface (`system/iq-router.py`)
All under `/iq`, all gated on `MANAGE_IQ`. The reviewer doesn't need the Python, but
the shape explains the UX (what's instant vs async vs filtered):

| Endpoint | Drives | Notes |
|---|---|---|
| `GET /opposition/opponents` | scout/preview pickers, Overview | opponents + upcoming fixtures |
| `GET /opposition/report` | scout (instant), preview, cheat sheet | from held data — fast |
| `GET /opposition/dossier` | scout (live), opp-player, cheat sheet | **async + polled**; `team=` scopes to a grade |
| `POST /opposition/dossier/refresh` | scout Refresh | force rebuild (bypass 7-day TTL) |
| `POST /opposition/match` | "Match club" modal | persist fixture→club alias |
| `GET /opposition/ladder` | preview | live grade ladder (our row + theirs) |
| `GET /opposition/player-tags` · `PUT …/{id}` | opp-player scouting tags | manual metadata |
| `GET /selection/lineups` · `GET /selection/analysis` | Selection | analyses a saved BetterSelect XI |
| `GET /trends/overview` · `/trends/players` · `/trends/player/{id}` · `…/deep` · `…/bowling-deep` | Player trends | overview + detail + two deep dives |
| `GET /team/seasons` · `/team/grades` · `/team/overview` · `/team/mvp` | Team + Overview MVP | season/grade filtered |
| `GET /review/games` · `/review/game/{id}` | Match review | list + per-game read |

Services live in `backend/app/services/iq*.py` (≈4,700 lines total) — `iq.py`
(instant report + opponents + ladder + tags), `iq_opponent.py` (the live dossier
builder + cache), `iq_selection.py`, `iq_trends.py`, `iq_team.py`, `iq_review.py`.

---

## 8. Cross-cutting UX patterns
- **Picker → detail**: every analytical screen is a list/search picker that swaps to a
  detail view, with a "← Change / All …" action in the header `actions` slot. State is
  reflected in the **URL query** (deep-linkable, back-button friendly).
- **Instant vs live**: opposition surfaces render held data immediately and *layer in*
  live-fetched data behind a poll. The preview deliberately uses **only** the instant
  layer to stay fast; the scout/cheat-sheet pay the live cost.
- **Honest coverage notes**: faint footers stating what the data can't support — the
  product's integrity move, and a density trade-off.
- **Method footnotes (`Note`)**: blended/derived ratings (MVP, all-rounders, collapse,
  reliability, role ratings…) carry a one-line "how this is worked out."
- **Graceful degradation**: the team page wraps each heavy card so a slow query can't
  blank the screen.

---

## 9. Behavioural details worth knowing for the review
1. **Result colour semantics** are fixed (green win / red loss / amber draw) and sit
   *alongside* the violet accent — see §3.1.
2. **Mobile**: sidebar → drawer; wide tables use `overflow-x-auto`. The module is
   **desktop-first** (it's an analyst tool) — but selectors/captains will open it on a
   phone, so the mobile read of the dense tables + the showcase cards deserves scrutiny.
3. **Dossier latency**: first live build is ~10–40s (CA-proxy politeness + scorecard
   fetches), then cached 7 days. The "Building…" spinner state is therefore a
   *frequent* first impression for a new opponent — not an edge case.
4. **Two sparkline styles** and **N copies of `Card`/`Stat`** mean small visual drift is
   possible across screens; check for it.

---

## 10. Suggested review focus (my observations — not prescriptions)
Hand these to the designer as starting prompts; all are things I noticed, not settled decisions:
1. **IA mismatch (§4):** the Overview's "5 capabilities" model vs the sidebar's 8-item
   model. Should the nav be grouped (e.g. *Opposition* ▸ club / player / preview / cheat
   sheet; *Our club* ▸ team / trends / selection / review)? Are two Opposition entries +
   an embedded player scout (5.2/5.4) one too many doors to the same data?
2. **Player-trends detail length (5.6):** a dozen+ stacked cards in one scroll. Tabs /
   progressive disclosure / a summary-then-expand pattern?
3. **Density vs honesty (§1, §8):** every screen carries coverage notes + method
   footnotes. Right balance, or can some move to tooltips / an info affordance?
4. **The showcase card (5.3) vs the tables around it:** the `KeyPlayersCard` is far more
   "designed" than its neighbours. Does it elevate the page or clash? Should its visual
   language spread, or be reined in?
5. **Cheat sheet (5.10):** the one off-system, light-themed screen. Print fidelity +
   whether it still reads as BetterIQ.
6. **Loading as a first impression (§9.3):** the live-dossier build is slow and common.
   Is the spinner card enough, or should we show the instant report more prominently
   "while we fetch the rest," skeletonise the eventual cards, or set expectations better?
7. **Consistency debt (§3.4, §6):** `Card/Stat/Note` duplicated per file; two sparkline
   implementations. A shared `iq/ui` kit would lock visual consistency — worth it?
8. **Mobile (§9.2):** the dense tables and the segmented showcase card on a phone.
9. **Accessibility:** colour-only status (dots/bars), the heatmap intensity encoding,
   focus states on the custom comboboxes/segments, and contrast of `--pb-faintest` text.
10. **The empty / new-club story:** a club with little history (few opponents, no saved
    lineups, sparse trends). How does the module feel on day one vs for Applecross (52
    seasons)?

---

## 11. Canonical source paths (for the live files)
The `screens/` and `system/` copies are snapshots. The real files:
- `frontend/src/components/admin/IQLayout.jsx`
- `frontend/src/pages/admin/betteriq/{BetterIQHome,OppositionScout,KeyPlayersCard,OppositionPlayer,OppPlayerProfile,SelectionAnalysis,PlayerTrends,TeamAnalysis,MatchReview,MatchPreview,CheatSheet}.jsx`
- `frontend/src/styles/theme.css` · `frontend/src/pages/admin/betterselect/ui.jsx`
- `frontend/src/lib/{modules,capabilities}.js` · `frontend/src/lib/api.js` (the `iq*` client, ~line 915)
- `frontend/src/App.jsx` (routes, ~line 198) · `frontend/src/components/ProtectedRoute.jsx`
- `backend/app/routers/iq.py` · `backend/app/services/iq*.py`

## 12. Reference docs
- **North-star vision**: `docs/community-cricket-analytics-brief.md` — the full "digital
  cricket analyst" roadmap (the "Community Cricket Analytics Platform Brief", 21
  sections). BetterIQ implements the **scorecard-reachable subset**; the brief's
  ball-by-ball items (phases, win-probability, pressure, ball-level matchups — §1.3,
  §2.3, §15.1–15.2, §16.7) are explicitly out of reach and were *not* built. Useful for
  understanding intent and the deliberate scope line.
- **Architecture/decisions**: root `CLAUDE.md`, the "BetterIQ —" sections (v2.0 → v2.16),
  document how each feature was reasoned to the scorecard ceiling.
- **Sibling precedent**: `docs/design_handoff_betterselect/` — the format this package mirrors.
