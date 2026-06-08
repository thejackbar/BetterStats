# Handoff: BetterSelect → Selection redesign

## Overview
A redesign of the **Selection** screen (`/admin/betterselect/select/:fixtureId`) — the team‑picking
"hero feature". It replaces the current squad‑left / smaller‑team‑right board with **two purpose‑built,
toggleable views over one shared selection state**:

- **Dual rail** (default) — *build the side*. Balanced two‑column flow: **Available pool ↔ Selected XI**.
- **Team sheet** — *finesse & assess*. A single numbered batting‑order spine you draft into from a pool grid.

It also fixes three specific problems with the current screen:
1. **Right→left drag was broken.** The new board is fully **bidirectional** (pool→XI, XI→pool to remove,
   drag‑to‑reorder within the XI) **plus tap/click‑to‑place**, which is the primary interaction on mobile.
2. **The batting‑order slots showed hardcoded positional hints** ("Opener", "First drop", …) from the
   `POS_HINTS` array. These are replaced with the player's **real role + style + a quiet form indicator**
   (e.g. `Opening bat · RHB · Hot`, `All‑rounder · RHB · Off spin · In form`, `Bowler · Right‑arm fast`).
3. **The layout balance felt off.** Both views now flow cleanly and are fully responsive.

## About the design files
The files in this bundle are **design references built in HTML/React+Babel** — a working, interactive
prototype showing intended look and behaviour. **They are not production code to copy in directly.**
The task is to **recreate these designs inside the existing BetterStats frontend** (Vite + React +
Tailwind, with the `pb-*` Press Box token system) using its established patterns — i.e. rebuild the
real `AdminSelection.jsx` to match this prototype, wired to the real selection API.

The prototype deliberately **reuses the project's own design language**: the `pb-*` CSS custom properties,
the BetterSelect atom kit (icon chips, availability dots, mono tags), the fixed brand‑green accent inside
BetterSelect, and the semantic green/amber/red availability colours. Where the prototype defines tokens or
atoms inline, **prefer the real ones already in the codebase** (see *Design tokens* and *Reusing existing code*).

## Fidelity
**High‑fidelity.** Final layout, colours (via tokens), typography, spacing, interactions, both light & dark
themes, and a full mobile pass are all specified. Recreate pixel‑for‑pixel using the codebase's existing
components and tokens.

---

## Reusing existing code (read these first)
| Real file | Use it for |
|---|---|
| `frontend/src/pages/admin/betterselect/AdminSelection.jsx` | The screen being replaced. Note the `POS_HINTS` array + `slotAccepts`/`fitsSlot` logic — `POS_HINTS` is **removed**; keep the slot/eligibility model if useful. |
| `frontend/src/pages/admin/betterselect/ui.jsx` | The atom kit — reuse its icon chips, availability dot, avatar, mono `Tag`, buttons rather than the prototype's reimplementations. |
| `frontend/src/pages/admin/betterselect/filters.jsx` | The existing unified filter pattern — extend it to cover the new dimensions below rather than inventing a parallel system. |
| `frontend/src/components/admin/BetterSelectLayout.jsx` | The sidebar + header chrome. The view toggle lives in this header. |
| `frontend/src/lib/availability.js` | **Single source of truth** for availability glyphs/colours — use it; do not hardcode. |
| `frontend/src/styles/theme.css` + `index.css` | The `pb-*` token definitions (light + `[data-theme="dark"]`). |
| `backend/app/services/selection_pool.py` | The pool assembler — **the data contract** (see *Data model*). |

---

## Screens / Views

### Shared chrome (both views)
- **Sidebar** (existing `BetterSelectLayout`): club identity, "Back to admin", nav with **Selection** active
  (accent text + `inset -2px 0 0 accent` rail). Off‑canvas under 760px behind a burger.
- **Header** (sticky, `backdrop-filter: blur(8px)`, 1px hairline bottom): page title **"Selection"**, then a
  vertical hairline divider, then the **view toggle** (see below). Right cluster: theme toggle (sun/moon, 34px
  square), **Share** (soft button), **Save XI (n)** (primary/accent button).
- **View toggle** — segmented control, two options each `icon + label`:
  `Dual rail` (two‑columns icon) · `Team sheet` (ruled‑list icon). Active pill = `surface` bg + accent text
  (light) / accent‑tint bg (dark). Persists to `localStorage['bs-view']`; default **`Dual rail`** ("B").
- **Fixture context bar** — accent‑tinted card: "← All teams", a fixture selector chip, then
  `<Us> vs <Opponent>` (Geist 700, ~23px) and `<date · time · venue (H/A) · round>` sub. On the right: a team‑size
  segmented control (`11 / 12 / 13 / No limit`) and a **pick pill** (`n / 11 picked`; accent when complete, amber while short).
  *(Team sheet folds this into its masthead instead — see below.)*
- **Balance strip** (quiet, kept understated per request) — one surface row:
  `BAT n · ALL n · BWL n · WK n` (the BWL count turns **amber** when `< 5` bowling options with ≥8 picked; the WK
  count turns amber when no keeper), a divider, the captain and keeper names (each prefixed by a `C` / `WK` mono tag),
  and an inline amber **"Light on bowling"** warning when applicable.

### View A — Dual rail (default; "build the side")
- **Layout:** CSS grid `minmax(0,1fr) 56px minmax(0,1fr)`, `align-items:start`. **Grid items must set `min-width:0`**
  (prevents the fixed‑width cards from blowing out the track — this was a real bug). Center column is a vertical
  **flow divider** with a circular accent arrow badge (→). Collapses to a single column under 920px (divider hidden).
- **Left — "Available pool":** card header with title, an availability mini‑bar (stacked green/amber/grey/red
  proportional strip) + count, then the **filter controls** (see *Filters*). Body is a scrolling list of **player cards**:
  4px left colour edge by availability, avatar (keeper gets an amber ring) with a status dot badge, name, role line
  (`roleLine`), availability reason if any, a **form sparkline** (last‑4 mini bars) + form word, a squad tag for
  non‑1st‑XI players, and an add affordance (→). Whole card is tap‑to‑add and (on desktop) drag‑to‑XI.
  Unavailable players are dimmed and non‑interactive.
- **Right — "Selected XI · batting order":** header with **Auto‑fill** and **Clear** mini‑buttons. Body is 11 numbered
  rows. Each filled row: big batting‑order number, a **grip handle** (drag to reorder / drag to pool to remove),
  avatar+dot, name (+ `C`/`WK` tags), role line, **form bars**, then per‑row **C / WK / ✕** buttons. Empty rows are
  dashed "Open slot" drop targets; the focused empty row reads "Tap a player in the pool".
- **Mobile (≤920px):** the two rails become a sticky **segmented switcher** — `Available pool` ⇄ `Your XI · n/11`
  (the count updates live). Only the active panel shows; tap‑to‑add still feeds the XI. Inner lists drop their
  `max-height` so the page scrolls naturally.

### View B — Team sheet ("finesse & assess")
- **Masthead** (accent→surface vertical gradient card, rounded top only): kicker `TEAM SHEET · <round>` (mono, accent),
  title `<Us> vs <Opponent>` (Geist 700, **sentence case** — *not* a condensed face), `<date · time · venue (H/A)>` sub.
  Right side: a large **`n / 11`** count (accent) and a compact `BAT/ALL/BWL/WK` tally (amber on the same low‑count rules).
- **The sheet** (surface card, joins the masthead with no gap): a `Batting order` header row with Auto‑fill/Clear, then
  11 ruled rows. Filled row: large order number (accent), grip handle, avatar+dot, name, role line + form chip, and
  `C / WK / ✕` controls. Even filled rows get a faint zebra tint. Empty rows: "Open slot" / "Tap a card below to draft
  here" (focused) / "Drop to draft" (drag‑hover, with an inset accent rail). Footer: captain + keeper status.
- **Draft pool** (separate surface card below): `Draft pool` header + the **same filter controls**, then a responsive
  **grid** of player cards (`repeat(auto-fill, minmax(232px,1fr))`, 1 column on mobile). Cards mirror the Dual‑rail
  card (colour edge, avatar+dot, name, squad tag, role line, form bars+word, a draft `+` affordance). Tap to draft into
  the next open slot; drag up onto a slot on desktop.

---

## Interactions & behaviour
- **Placement model (shared state):** an array of 11 slot ids; helpers `place(idx,id)`, `move(from,to)` (reorder),
  `removeAt(idx)`, `addPlayer(p)` (fills the focused empty slot else the next empty), `toggleCap(id)`, `toggleWk(id)`,
  `clearXI()`, `autofill()` (best available by tier then form, skipping unavailable). Adding a player already in the XI
  moves them rather than duplicating. Unavailable players cannot be placed.
- **Drag & drop:** a single **pointer‑based** engine (works for mouse *and* touch) with a floating ghost. Drop zones:
  each slot (`data-drop-kind="slot" data-drop-idx`) and the pool (`data-drop-kind="pool"`, drop here to remove).
  A 6px threshold distinguishes a drag from a tap. **On touch, only grip handles set `touch-action:none`** so lists
  still scroll; whole‑card drag is a desktop nicety and **tap‑to‑place is the primary mobile interaction.**
  *(In the real app, prefer the codebase's existing DnD approach if there is one; otherwise this pointer model is
  mobile‑safe and dependency‑free.)*
- **Captain / keeper:** per‑row `C` / `WK` toggles; exactly one of each (toggling reassigns). Keeper also surfaces the
  amber ring on the avatar + a `WK` tag.
- **Auto‑fill / Clear:** Auto‑fill fills only empty slots from eligible players sorted by `tier` then `score`. Clear
  empties all slots and resets captain/keeper.
- **Save / Share:** stubs in the prototype (toast). Wire **Save XI** to the real lineup‑save endpoint and **Share** to
  the existing share flow.
- **Persistence:** `localStorage['bs-view']` (current view), `localStorage['bs-theme']`. View/panel also accept
  `?view=B|C` and `?panel=pool|xi` query params (used for deep‑linking / previews — optional to keep).
- **Reduced motion / print:** no infinite decorative animation; entrance states should degrade to the visible end‑state.

## Filters (expanded — applies to both views)
One shared filter system in the pool header:
- **Search** by name.
- **Sort menu** (popover): `Squad order` (tier then form — default), `Form` (score desc), `Name (A–Z)`.
- **Quick chips** (always visible): role `Bat · Bowl · All · WK` toggles + a `Hide unavailable` toggle.
- **Filter panel** (behind a `Filters` button with an active‑count badge), grid of groups:
  - **Availability** — Available / Maybe / No response / Unavailable (use `availability.js`).
  - **Bowling** — Pace / Spin / Doesn't bowl (classify: `bowling_type` contains "spin"/"orthodox" → spin; else if a
    bowling style exists → pace; else none).
  - **Batting hand** — Right‑hand / Left‑hand (`batting_hand`).
  - **Form** — Hot / In form / Steady / Out of nick (buckets over the form score).
  - **Squad** — 1st XI / 2nd XI / 3rd XI / A (`squad`/`tier`).
- **Active‑filter pills** below the controls — each removable; a `Clear all` resets everything.
- Live **"X of Y shown"** count. Picked players are excluded from the pool automatically.

## State management
- `view: 'B'|'C'` (persisted) · `theme: 'light'|'dark'` (persisted, sets `data-theme` on the root).
- `slots: (id|null)[11]`, `capId`, `wkId`, `focus` (focused empty slot index).
- Derived: `count`, `usedIds`, `balance { BAT, ALL, BWL, WKT, bowlers, hasKeeper, lightBowling }`.
- Filter state: `q, roles[], avails[], bowling[], hands[], squads[], forms[], hideUnavail, sort` → feeds a memoised
  `pool` (exclude picked → search → each filter → sort).
- **Data fetching:** load the fixture + selection pool from the real selection endpoints (see *Data model*); persist
  the lineup, captain, keeper and batting order on Save.

## Data model (map prototype → real fields)
The pool is assembled by `backend/app/services/selection_pool.py`. Each prototype player maps to real fields:

| Prototype field | Real source | Notes |
|---|---|---|
| `name` | player name | "Surname, First" in the prototype |
| `skills[]` (BAT/BWL/ALL/WKT) | `skill_positions` / `player_role` | drives the role chips + balance counts |
| `player_role` | `player_role` | Batter / Bowler / All Rounder / Wicketkeeper(-Batter) |
| `batting_hand` (RIGHT/LEFT) | `batting_hand` | → `RHB`/`LHB` |
| `bowl` (e.g. "Off spin") | compose from `bowling_action` + `bowling_type` | "Right‑arm" + "Fast" → "Right‑arm fast" |
| `opener` | `is_opening_batsman` | promotes role noun to "Opening bat" |
| `availability` + `availability_reason` | availability join | render via `availability.js` |
| `squad` / `tier` | squad / tier | non‑1st‑XI players get a squad tag |
| `score` + `form` + `recent[]` | form score / recent innings | **form indicator source** — use the existing form score; derive the sparkline from the last ~4 innings. If no recent series is available, show the form word only. |

> The **single most important data change**: stop rendering positional `POS_HINTS`. Render `roleLine(player)` —
> role noun + `RHB/LHB` + bowling style — plus the form indicator, in both the XI rows and the pool cards.

## Design tokens
Use the **existing** `pb-*` tokens (do not redefine). The prototype's values mirror them for reference:
- **Accent (brand, fixed in BetterSelect):** `--pb-accent #16c784`. Semantic: positive `#16c784`, amber `#f5b542`, red/negative `#ef5b5b`.
- **Light:** bg `#f5f6f8`, surface `#ffffff`, surface2 `#eef0f3`, hairline `#e1e4ea`/`#d0d4dd`, text `#1b1e27`, dim `#5b6072`, faint `#8a90a2`, faintest `#b6bac6`.
- **Dark (`[data-theme="dark"]`):** bg `#0a0d14`, surface `#10141d`, surface2 `#161b27`, hairline `#1d2331`/`#262d3d`, text `#e6e8ef`, dim `#8a90a2`, faint `#5b6072`, faintest `#3a3f50`.
- **Type:** display/body **Geist** (used everywhere now — the previous condensed face was removed for consistency), mono **JetBrains Mono** for tags/labels/numerals‑in‑chips.
- **Radius:** cards 12–14px, rows/controls 9–11px, chips/pills 999px. **Shadow:** the `--pb-shadow` token.
- **Availability colours come from `availability.js`** — green / amber / hollow‑grey (no response) / red.

## Assets
None external. Avatars are initials placeholders — wire to real player photos where available (keep the keeper amber
ring + status‑dot badge treatment). Icons are inline geometric SVGs — substitute the codebase's existing icon set.

## Files (in this bundle)
- `BetterSelect Selection.html` — entry; theme tokens, chrome CSS, all component CSS, script load order.
- `selection/data.js` — mock pool + domain helpers (`roleLine`, `styleLine`, `formOf`, `spark`, availability map, squads). **Reference for the data shape**, not for shipping.
- `selection/shared.jsx` — atoms (Icon, Dot, Avatar, RoleChips, Tag, FormBars/FormChip, Btn, Segmented, Search), the **pointer DnD engine**, `useSelection` (shared state), `useFilters` + `usePool`, bowling/form classifiers.
- `selection/app.jsx` — app shell: sidebar, header, **view toggle**, theme toggle, shared drop semantics.
- `selection/dirB.jsx` — **Dual rail** view (+ the mobile Pool⇄XI switcher).
- `selection/dirC.jsx` — **Team sheet** view.
- `selection/dirA.jsx` — *(superseded "Team First" exploration; still defines the shared `FixtureBar`, `BalanceStrip`,
  and `FilterControls` used by both live views — keep for reference, or lift those three components out.)*
- `selection/mobile-preview.html` — a 3‑phone harness embedding the app at 390px to view the mobile states.

## Build notes
- Rebuild `AdminSelection.jsx` (and split into a couple of child components) to match this prototype; keep it wired to
  the existing selection API and the `BetterSelectLayout` chrome.
- Lift the prototype's atoms onto the real `ui.jsx` atoms; extend the real `filters.jsx` rather than forking it.
- Keep both light + dark working via the existing token system; verify no horizontal scroll at 390px on both views.
- The prototype runs on in‑browser Babel (dev only) — in‑app it's just normal JSX in the Vite build.
