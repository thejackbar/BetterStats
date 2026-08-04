# Handoff: BetterClubhouse — merging BetterFees, BetterComms, BetterMerch and BetterClubManager

## Overview

BetterAdmin currently groups four independently-built sub-modules — **BetterFees**, **BetterComms**, **BetterMerch** and **BetterClubManager** — under one umbrella. They share a codebase but not a design language, and they duplicate three person lists, two money ledgers, two Square integrations and three reports surfaces between them.

This handoff covers two things:

1. **Consolidation** — one module with one sidebar, one accent, one person spine and one account per member. Proposed name: **BetterClubhouse**.
2. **The visual system** — BetterClubManager's redesigned shell (`pages/admin/clubmanager/redesign/`) promoted into the shared `ModuleLayout`, so all four sub-modules inherit it, and the platform chrome that the ClubManager fork dropped (module switcher, bookmarks, user menu) given back.

Deliver in this order. Step 1 of the sequencing below is a change to one shared component and gives every screen the glow-up without rewriting any of them.

---

## About the design files

The files in this bundle are **design references created in HTML** — prototypes showing intended look and behaviour, not production code to copy.

The target codebase is **thejackbar/BetterStats**, a React 18 + Vite + Tailwind app. Recreate these designs there using its existing patterns:

- `frontend/src/styles/theme.css` — the `--pb-*` Press Box token set (light and dark)
- `frontend/tailwind.config.js` — the `pb-*` colour aliases, `font-display` / `font-body` / `font-mono` stacks, `tracking-wide2/3/4`
- `frontend/src/pages/admin/betterselect/ui.jsx` — the house `Icon` component and its `ICON_PATHS`
- `frontend/src/components/admin/ModuleLayout.jsx` — the shared module shell to be upgraded
- `frontend/src/pages/admin/clubmanager/redesign/ui.jsx` — the primitives to promote

Do **not** hand-write new SVG icons: every icon in the prototypes is copied verbatim from `ICON_PATHS` in `betterselect/ui.jsx` or `NAV_ICONS` in `clubmanager/redesign/ClubManagerApp.jsx`.

The prototypes use inline styles because of the tooling they were authored in. In the codebase, use Tailwind classes with the `pb-*` tokens, exactly as the existing screens do.

## Fidelity

**High fidelity.** Colours, type sizes, spacing, radii and copy are final and are all drawn from the repo's own token files. Recreate pixel-for-pixel. Every hex below is already a `--pb-*` variable — use the variable, not the literal.

The one exception is the **BetterClubhouse logo mark**, which is a striped placeholder in the prototype. A real mark needs drawing; the existing `betteradmin.svg` (amber tile, `rx="15"` on a 64 viewBox, `#fbb12e → #d97706` gradient, `#ffffff` @ 0.18 inner hairline, `#1b1205` checklist glyph) is the family it should join.

---

## Files in this bundle

| File | What it is |
| --- | --- |
| `BetterClubhouse.dc.html` | The interactive prototype. Working nav across 15 screens, five of them fully built (Today, Directory, Accounts, Audiences, Inventory) plus Settings; the rest are described interim pages. Open it in a browser. |
| `BetterAdmin Review.dc.html` | The review document: the cohesion audit, the overlap/duplication findings with recommendations, naming rationale, the IA proposal, faithful recreations of the four current screens, and the redesigned screens. Pan/zoom canvas. |
| `assets/*.svg` | The real module marks, copied from `frontend/src/assets/modules/`. Use these, not redrawn versions. |
| `github.md` | Source association and the screen → repo-file map the designs were built from. |

`BetterClubhouse.dc.html` is the specification for behaviour; `BetterAdmin Review.dc.html` is the specification for *why*, and contains the as-is recreations you can diff against.

---

## Design tokens

All of these already exist in `frontend/src/styles/theme.css`. Use the variables.

### Surfaces and text — dark (default)

| Token | Hex | Use |
| --- | --- | --- |
| `--pb-bg` | `#0a0d14` | Page background |
| `--pb-surface` | `#10141d` | Cards, sidebar, headers, tables |
| `--pb-surface2` | `#161b27` | Inputs, table heads, avatars, chips |
| `--pb-hairline` | `#1d2331` | Dividers, card borders, row separators |
| `--pb-hairline2` | `#262d3d` | Input borders, stronger edges, avatar rings |
| `--pb-text` | `#e6e8ef` | Primary text |
| `--pb-dim` | `#8a90a2` | Secondary text, body copy |
| `--pb-faint` | `#5b6072` | Tertiary, mono labels, inactive nav |
| `--pb-faintest` | `#3a3f50` | Captions, zero values, placeholder text |

### Surfaces and text — light

| Token | Hex |
| --- | --- |
| `--pb-bg` | `#f5f6f8` |
| `--pb-surface` | `#ffffff` |
| `--pb-surface2` | `#eef0f3` |
| `--pb-hairline` | `#e1e4ea` |
| `--pb-hairline2` | `#d0d4dd` |
| `--pb-text` | `#1b1e27` |
| `--pb-dim` | `#5b6072` |
| `--pb-faint` | `#8a90a2` |
| `--pb-faintest` | `#b6bac6` |

In light mode the amber accent must darken for legibility on white — the prototype's light-mode Inventory screen uses `#b47407` for accent *text* and keeps `#f59e0b` for accent *fills*. Do the same. Likewise `#0f8f5f` replaces `#16c784` and `#c73f3f` replaces `#ef5b5b` for text on light.

### Accent and semantic

| Token | Hex | Note |
| --- | --- | --- |
| `--pb-accent` (module) | `#f59e0b` | The BetterAdmin amber, from `MODULE_BRAND.admin` in `lib/moduleBrand.js`. Confirmed as the merged module's accent. |
| — | `#0a0d14` | **Text colour on an amber fill.** One answer everywhere. This replaces the current four (`text-pb-bg`, `text-white`, `text-black`, `#fff`). |
| `--pb-positive` | `#16c784` | Current / OK / in credit |
| `--pb-amber` | `#f5b542` | Owing, low stock, expiring soon, warnings |
| `--pb-red` | `#ef5b5b` | Overdue, expired, out of stock, blocked |
| (indigo) | `#6366f1` | `MODULE_BRAND.clubmanager` — **retired** by this merge. |

Accent-tinted fills use `rgba(245,158,11,α)`: `0.04` table row wash, `0.07–0.08` panel wash, `0.1` active nav, `0.12` active pill, `0.14–0.15` chip / active switcher pill, `0.18` badge, `0.38–0.5` borders.

### Typography

Families from `tailwind.config.js`:

- **Display / body**: `Geist, Inter, system-ui, sans-serif` (`font-display`, `font-body`)
- **Mono**: `JetBrains Mono, Fira Code, monospace` (`font-mono`)

| Role | Size | Weight | Letter-spacing | Notes |
| --- | --- | --- | --- | --- |
| Screen title (`h1`) | 19px | 700 | `-0.01em` | In the sticky screen header, never in the body |
| Detail-pane name | 22px | 700 | `-0.01em` | `white-space: nowrap` + ellipsis |
| Stat readout value | 19px | 700 | — | `font-variant-numeric: tabular-nums` |
| Stat card value | 21px | 700 | — | Accent coloured, tabular |
| Attention-row count | 26px | 700 | — | Tone coloured, `width: 44px`, `line-height: 1` |
| Section heading | 15.5px | 600 | — | |
| Body copy | 13.5px | 400 | — | `line-height: 1.65`, `text-wrap: pretty` |
| Secondary copy | 12.5px | 400 | — | `line-height: 1.6`, `--pb-dim` |
| Nav item | 13.5px | 400 | — | |
| Button | 13px | 600 | — | Sentence case |
| Small button | 12.5px | 400/600 | — | |
| Input / select | 13.5px | 400 | — | 13px inside panels |
| Table cell | 13–13.5px | 400/600 | — | |
| **Mono screen caption** | 10px | 400 | `0.14em` | Uppercase, `--pb-faint` |
| **Mono section caption** | 10px | 400 | `0.14em` | Uppercase, `--pb-faintest` |
| **Mono stat label** | 9px | 400 | `0.1em` | Uppercase, `--pb-faint` |
| **Mono table head** | 9px | 400 | `0.12em` | Uppercase, `--pb-faint` |
| Mono figure | 11–12.5px | 400/600/700 | — | Money, counts, dates, refs |
| Mono badge | 9–9.5px | 400/700 | `0.08em` | |

**Mono is for labels and figures only** — never for buttons, headings or body copy. This is the single biggest visual change from BetterFees, whose primary actions are currently 10px mono all-caps (`+ MEMBER`, `IMPORT`, `SYNC MATCH DAYS`).

### Radius

| Value | Use |
| --- | --- |
| 4–5px | Mono badges, chips, family tags, logo tile in the club lockup |
| 7px | Small cards inside a section (qualification rows) |
| 8px | **Default.** Buttons, inputs, selects, list rows, stat cards, sub-panels |
| 8px | Module lockup mark (26–28px tile) |
| 10px | Cards, tables, attention rows, panels |
| 11–12px | Page-level containers, modals |
| 999px | Filter pills, switcher pills, count badges |
| 50% | Avatars |

The current `.pb-card` is `border-radius: 6px`. **Raise it to 10px** — that one change moves most of the app onto the new scale.

### Spacing

4px base. Common values: nav item `9px 16px`; nav group heading `15px 16px 4px`; screen header `14px 20px`; content `20–24px`; card `13–16px` small / `24–32px` large; table cell `10–11px 12px`, first cell `padding-left: 16–18px`, last `padding-right: 16–18px`; grid gaps 8px (stat cards), 7px (attention rows), 12px (cards), 24–28px (sections).

### Elevation

Only two shadows in the whole system:

- Drawer: `0 0 40px rgba(0,0,0,0.5)`
- Toast: `0 8px 40px rgba(0,0,0,0.6)`

No card shadows. Depth comes from surface steps and hairlines.

---

## Component specifications

### Sidebar — 232px

`width: 232px; flex: 0 0 232px; border-right: 1px solid var(--pb-hairline); background: var(--pb-surface); position: sticky; top: 0; height: 100vh; overflow-y: auto; display: flex; flex-direction: column`

Note: 232px, not the current 240px (`w-60`) — matching the ClubManager redesign.

**Header** (`padding: 16px; border-bottom: 1px solid var(--pb-hairline)`):
1. Club identity row, `gap: 10px` — logo 32px `border-radius: 5px`, or initial fallback on `rgba(245,158,11,0.15)` in accent at 15px/700. Then club name 14px/700 `line-height: 1.2` with ellipsis, and beneath it `2026/27 SEASON` in mono 10px `0.08em` `--pb-faintest`.
2. Module lockup, `margin-top: 12px`, `gap: 8px` — 26px mark at `border-radius: 8px`, then `Better` + accent-coloured `Clubhouse` at 14px/700 `line-height: 1`.

Drop the `← Back to admin` link that the current layouts carry — the switcher in the footer replaces it.

**Nav** (`flex: 1; padding: 8px 0`):
- Group heading: `padding: 15px 16px 4px`, mono 10px `0.14em`, `--pb-faint`. Groups: `PEOPLE`, `MONEY`, `STOCK`, `COMMS`, `CLUB`, `SETUP`. `Today` sits above the first heading.
- Item: `display: flex; align-items: center; gap: 11px; width: 100%; padding: 9px 16px; font-size: 13.5px; text-align: left`. Icon 17px, `stroke-width: 1.6`, `flex-shrink: 0`.
  - Inactive: `color: var(--pb-faint)`, transparent background, `border-right: 2px solid transparent`
  - Active: `background: rgba(245,158,11,0.1)`, `color: var(--pb-accent)`, `border-right: 2px solid var(--pb-accent)`
- Count badge: `margin-left: auto`, mono 9px, `padding: 1px 5px`, `border-radius: 999px`. Amber `rgba(245,181,66,0.18)` / `#f5b542`, or red `rgba(239,91,91,0.18)` / `#ef5b5b`.

Keep the existing capability filter and the rule that drops a heading whose items were all filtered away — that is what stops one large sidebar feeling large. A treasurer sees Today, Money and People, which is fewer items than BetterFees shows them today.

**Footer** (`border-top: 1px solid var(--pb-hairline); padding: 11px 12px`) — this is the platform chrome the ClubManager fork lost:
1. `SWITCH MODULE` in mono 9px `0.12em` `--pb-faintest`
2. Wrapping switcher pills, `gap: 4px`: `padding: 4px 8px`, `border-radius: 999px`, 11.5px, 14px mark at `border-radius: 4px`. Inactive `--pb-faint`; active `rgba(245,158,11,0.14)` fill, `rgba(245,158,11,0.38)` border, accent text, 600.
3. User row, `border-top` above it: 24px initials avatar, name at 12.5px `--pb-dim`, bookmark icon 15px.

Moving the switcher, bookmarks and account here is the load-bearing decision: it keeps the screen header clean enough to carry the title, filters and stat readouts, and it means every screen inherits the chrome instead of each layout re-declaring it.

### Screen header — sticky

`position: sticky; top: 0; z-index: 40; border-bottom: 1px solid var(--pb-hairline); background: var(--pb-surface); padding: 14px 20px; display: flex; align-items: center; gap: 14–16px; flex-wrap: wrap`

Left to right: title block (`h1` 19px/700 `-0.01em` + mono 10px `0.14em` uppercase caption, `margin-top: 2px`) → optional help affordance → search input → filter pills → `margin-left: auto` → stat readouts → primary action.

The **help affordance** is an 18px circle, `border: 1px solid var(--pb-hairline2)`, mono 10px `--pb-faint`, containing `?`. It reopens the screen's introduction. `gap: 8px` from the title.

**Stat readouts**: value 19px/700 tabular (accent or `--pb-text`), label mono 9px `0.1em` `--pb-faint`, `white-space: nowrap`, `gap: 26px` between them.

The caption is not decoration — it carries the live count (`One record per person · 6 of 8 shown`), which is why the current screens' separate "Showing 5 of 118" footer line disappears.

### Buttons

All `border-radius: 8px`, sentence case, `font-family: inherit`, `cursor: pointer`.

| Variant | Spec |
| --- | --- |
| Primary | `padding: 8px 14px; font-size: 13px; font-weight: 600; background: var(--pb-accent); color: #0a0d14; border: none` |
| Primary (large, on an intro page) | `padding: 10px 18px; font-size: 13.5px; font-weight: 600; white-space: nowrap` |
| Secondary | `padding: 8px 14px; font-size: 13px; border: 1px solid var(--pb-hairline2); background: transparent; color: var(--pb-dim)` |
| Small secondary | `padding: 6px 12px; font-size: 12px` |
| Inline action | `padding: 7px 13px; font-size: 12.5px` |

Put `white-space: nowrap` on any button whose label can grow from data (`Email these 34`, `Continue to Directory →`) — a wrapped label breaks out of the fill.

### Filter pills

`padding: 5px 11px; border-radius: 999px; font-size: 12px; cursor: pointer`

- Inactive: `border: 1px solid var(--pb-hairline2)`, transparent, `--pb-dim`
- Active (accent): `border: 1px solid rgba(245,158,11,0.5)`, `background: rgba(245,158,11,0.12)`, accent text
- Active (amber, for warning-flavoured filters like "Owes money" / "Quals to renew"): `border: 1px solid rgba(245,181,66,0.45)`, `background: rgba(245,181,66,0.12)`, `#f5b542`

Pills replace the bare mono-labelled checkboxes currently used in BetterFees (`NEEDS TIER`, `OWES MONEY`).

### Inputs

`background: var(--pb-surface2); border: 1px solid var(--pb-hairline2); border-radius: 8px; padding: 8px 11–12px; font-size: 13–13.5px; color: var(--pb-text); outline: none`. Focus: `border-color: var(--pb-accent)`. Placeholder `--pb-faintest`.

Label above: mono 9.5px `0.1em` uppercase `--pb-faint`, `margin-bottom: 5px`.

### Cards

- Stat card: `background: var(--pb-surface); border: 1px solid var(--pb-hairline); border-radius: 10px; padding: 13–14px 15–16px`. Value 19–21px/700 accent tabular; label mono 9px `0.1em` `--pb-faint` `margin-top: 3–4px`; optional detail 12px `--pb-dim` `margin-top: 7px` `line-height: 1.45`. Accent variant: `border-color: rgba(245,158,11,0.4)`.
- Attention row: `display: flex; align-items: flex-start; gap: 14px; border-radius: 10px; padding: 15px 17px`, border tinted by tone — `rgba(239,91,91,0.28)` blocking, `rgba(245,181,66,0.28)` warning, `var(--pb-hairline)` calm. Count 26px/700 in the tone colour, `width: 44px`, `line-height: 1`. Then title 14.5px/600, an area tag (mono 9px `0.08em` on `--pb-surface2` with a `--pb-hairline2` border), detail 12.5px `--pb-dim`, and one or two buttons at `margin-top: 11px`.

### Tables

Wrap in `overflow-x: auto` and give the header, every row and the footer the **same** `grid-template-columns` and a `min-width` that clears the fixed tracks. First track `minmax(160–180px, 1fr)`; never `minmax(0, 1fr)`, which collapses to a few pixels once the fixed tracks exceed the container.

| Table | `grid-template-columns` | `min-width` |
| --- | --- | --- |
| Accounts | `minmax(180px,1fr) 120px 120px 90px 90px 100px 116px` | 860px |
| Audiences | `minmax(180px,1fr) 160px 110px 120px` | 700px |
| Inventory | `minmax(160px,1fr) 90px 80px 90px 90px 100px` | 620px |

- Head: `background: var(--pb-surface2)`, mono 9px `0.12em` `--pb-faint`, `padding: 9–10px 12px`
- Row: `border-top: 1px solid var(--pb-hairline)`, `align-items: center`, `cursor: pointer` where it opens a record. Attention wash `rgba(245,158,11,0.04)`; selection wash `rgba(245,158,11,0.07)`
- Numeric cells: `text-align: right`, mono 11px, tabular
- Footer totals row: `border-top: 1px solid var(--pb-hairline2)`, `background: var(--pb-surface2)`, total in mono 13px/700 accent

### Master–detail

`display: flex; flex-wrap: wrap; align-items: stretch; min-height: 0`

**Set `box-sizing: border-box` globally first.** Without it, `flex-basis` excludes padding and border, the panes' outer widths exceed the values you set, and the row wraps at a width where side-by-side is still fine.

- List pane: `flex: 0 1 260–270px; max-width: 340px; min-width: 240px; border-right: 1px solid var(--pb-hairline); background: var(--pb-surface); overflow-y: auto; padding: 10px`
- Detail pane: `flex: 1 1 390px; min-width: 380px; overflow-y: auto; padding: 22px 24px`

Wrapping is decided by **flex-basis**, not `min-width` — keep list basis + detail basis under the narrowest row you want side-by-side. Put the list's `max-width` and `flex` in a **class rule, not the inline style**, so the responsive override can win; an inline declaration beats a media query.

At `max-width: 900px` the list releases to `flex-basis: 100%`, swaps `border-right` for `border-bottom`, drops its `max-width`, and the pattern becomes list-then-record.

**List row**: `display: flex; align-items: center; gap: 10px; padding: 9px 11px; border-radius: 8px`. 30px initials avatar; name 13.5px/600 with ellipsis; sub-line mono 9.5px `--pb-faint` with ellipsis; optional 6px amber flag dot; optional mono 10px trailing figure. Selected: `border: 1px solid rgba(245,158,11,0.4)`, `background: rgba(245,158,11,0.08)`.

**Detail header**: `display: flex; flex-wrap: wrap; gap: 14px; row-gap: 12px`. 52px avatar; name block at `flex: 1 1 240px; min-width: 200px` with the name `nowrap` + ellipsis; buttons `flex-shrink: 0` so they move to their own line rather than breaking the name.

**Inner grids must reflow, not crush**: stat row `repeat(auto-fit, minmax(130px, 1fr))`, section grid `repeat(auto-fit, minmax(240px, 1fr))`.

### Drawer

`position: fixed; inset: 0; z-index: 90; display: flex; justify-content: flex-end; background: rgba(0,0,0,0.55)`. Panel `width: 440px; max-width: 92vw; background: var(--pb-surface); border-left: 1px solid var(--pb-hairline2); overflow-y: auto; box-shadow: 0 0 40px rgba(0,0,0,0.5)`.

Enter animation, ported from the ClubManager redesign's `bcmRiseIn`:
```css
@keyframes chRise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
/* animation: chRise 180ms ease both */
```
Scrim click closes; clicks inside `stopPropagation`.

### Toast

`position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); z-index: 120; background: var(--pb-surface); border: 1px solid rgba(245,158,11,0.5); border-radius: 10px; padding: 13px 18px; box-shadow: 0 8px 40px rgba(0,0,0,0.6)`. Title 13.5px/600 accent, body 13px `--pb-dim`, dismiss `✕`. Enters with `chRise 160ms`.

### Side panel (Inventory movement)

`flex: 1 1 346px; min-width: 300px; background: var(--pb-surface); overflow-y: auto; padding: 20px`, with `max-width: 420px` and `border-left` **in a class rule**. At `max-width: 1200px` it drops the left border for a top border and releases its `max-width`, so when it stacks below the table it fills the row instead of leaving a dead column.

---

## Screens

### Today — the front door

Replaces four separate module home pages. Aggregates across money, people, stock, comms and the club.

**Header**: title `Today`, caption `Sat 16 Jan · round 9 at home`, then three stat readouts — total owed (amber), people count, things-need-you count.

**Body** (`padding: 22px 24px; max-width: 74rem`):
1. `BLOCKING FIRST` section caption
2. Attention rows, `gap: 7px`, blocking-first then warning then calm, each with an area tag and two actions. Real rows: members owing money (Money), unfilled canteen shifts (People), overdue renewals and reorders (Club · Stock), a draft email waiting (Comms).
3. `THE WEEK AHEAD` caption
4. Four stat cards: next meeting, events taking RSVPs, taken this week, diary due this week.

**Rows must be omitted when their count is zero**, and the section caption pluralises. Counts are derived, never authored — the prototype computes every one from the same data the other screens read, which is the point.

Merch's existing three-up `AlertCard` row and ClubManager's `Today` attention rows are together about 80% of this; keep Merch's card pattern for the week-ahead row.

### Directory — the person spine

Replaces the three person lists. This is the substrate; build it first.

**Header**: title, caption `One record per person · N of M shown`, help `?`, search input (`max-width: 280px`), filter pills (`Everyone`, `Players`, `Volunteers`, `Committees`, `Parents`, `Quals to renew` — the last in the amber tone), and `Email these N` as the primary action.

That last button is the consolidation made concrete: filtering and sending become one motion instead of two screens apart.

**List** (300px): rows as specified above, sub-line showing club roles or the first segment, uppercased.

**Detail**: avatar + name + contact + segment chips + `Email` / `Open account`. Then a reflowing stat row — hours this season, account balance, club roles, quals to renew. Then a two-up section grid:

- `CLUB ROLES` — accent chips, `background: rgba(245,158,11,0.15)`, `border-radius: 5px`, `padding: 3px 9px`, 12.5px
- `ACCOUNT` — a four-line ledger (subs, match fees, kit, balance) in a bordered card; balance row bold, amber if owing and green if in credit
- `QUALIFICATIONS` — name + expiry line + status badge. `CURRENT` `#16c784`, `EXPIRES SOON` `#f5b542` (≤60 days), `EXPIRED` `#ef5b5b`. Badge is mono 9px `0.08em` with a `{colour}66` border
- `KIT ISSUED` — date (mono 9.5px, 46px wide), item, amount in amber

Label the three role vocabularies honestly and separately: **club role**, **committee position**, **playing role**. They do not merge; this record is where they reconcile.

### Accounts — one balance per person

Replaces BetterFees Members. The important change is that stock charges land here, so a member has one balance rather than two.

**Header**: title, caption `One balance per person · N of M shown`, help `?`, pills (`Everyone`, `Owes money` in amber, `Needs tier`), then `Import bank CSV` and `Email these N`.

**Notice strip** below the header: `background: rgba(245,181,66,0.07); padding: 10px 20px; font-size: 13px; color: #f5b542` — `$X of this is issued kit. Stock charges land on the member's account, so the balance below is everything they owe the club.`

**Five KPI cards**: people, owe money, subs & match fees, issued kit, total outstanding (accent variant).

**Table** columns: person (avatar + name + role line), tier (or `⚠ needs tier` in mono amber), family (accent tag or `—`), subs, match, kit, balance. Balance amber when owing, green `+$40` when in credit, `--pb-faintest` at zero. Footer totals every money column.

Rows open the person drawer.

### Audiences — one audience concept

Replaces Contacts + Lists + Segments.

**List** (270px): each audience with a name, a `N conditions · live` sub-line, and a live count — accent when selected, `--pb-faintest` otherwise. Below the list, two explanatory notes: what this replaced, and — required — a `CLUB SCOPE ONLY` note (see the scope rule below).

**Detail**: name 22px/700, blurb, `Duplicate` and `Email these N`. Then `MATCH PEOPLE WHERE ALL OF THESE ARE TRUE` and the rule rows — field select, operator select, value, remove `✕`. Then a live resolution line: `N people match · N reachable by email · N need another route`. Then a preview table: person, in-the-directory-as, balance, reachable (`EMAIL` green / `VIA GUARDIAN` amber / `NO ADDRESS` red).

A hand-picked list is an audience whose rule is "these people" — do not build a second mechanism for it. An audience resolves at send time and is never frozen.

### Inventory — issuing posts a charge

Replaces Merch Stock + Activity.

**Header**: title, caption, help `?`, category pills (`Apparel`, `Equipment`, `Food & drink`, `Needs reorder` in amber), then two stat readouts (stock at cost, units on hand) and `Record movement`.

**Table**: product (name + mono meta line), on hand (amber below reorder, red at zero, 600 weight when low), reorder point, cost, retail, status badge (`OK` green / `LOW` amber / `REORDER` red). Clicking a line loads it into the panel.

**Movement panel** (346px): `RECORD A MOVEMENT`, then kind pills — `Received`, `Sold`, `Issued`, `Used`, `Write-off`, `Stocktake` (from `MOVEMENT_KINDS` in `bettermerch/ui.jsx`). Then product, qty, price each, and an `ISSUE TO` person select showing each person's tier and current balance.

Then the panel's most important element — a **consequence preview** on `rgba(245,158,11,0.08)` with a `rgba(245,158,11,0.35)` border, headed `WHAT THIS DOES`:

> Takes 1 × Club polo out of stock and posts $38.00 to Chloe's account. Balance goes $135 → $173, and because they are a junior the reminder routes to a guardian.

Then `Issue & charge` (primary) and `Issue free` (secondary), then a `RECENT` movement list. Committing must mutate stock **and** post the charge **and** append the movement **and** raise a toast — the four together are what make the join believable.

### Settings — the interim-page flag

A club officer asked for this directly: the introduction pages help a new committee and irritate a practised one.

Card headed `SCREEN INTRODUCTIONS`, titled `Show an introduction when a screen opens`, with three pills: **Every time** / **First visit only** (default) / **Never**. Each mode shows an explanatory note beneath. In "first visit only" mode, add a line reporting how many screens have introduced themselves and a `Show them all again` reset.

Rules:
- **Per person, not per club.** A treasurer joining in March gets the introductions even if the rest of the committee turned them off in October.
- **Today never gets one** — it is the front door.
- **Deep links always skip it.** Pressing `Open accounts` on Today goes to the work; the officer already said what they wanted. Only sidebar navigation can trigger an introduction.
- The `?` beside every screen title reopens it on demand, in every mode.

### Interim introduction page

Per screen: `WHAT THIS SCREEN IS FOR` caption, a one-line lede at 19px/600 (`max-width: 46ch`), two to four bullet points with 5px accent dots, an optional accent-tinted note giving the consolidation history ("This replaced three separate people lists…"), then `Continue to {Screen} →` (primary, nowrap) and `Don't show introductions again` (secondary). A footer line explains why it appeared and links to Settings. The header carries a `Skip` button.

### Remaining screens

Roster, Committee, Payments, Rate card, Equipment, Emails, Diary, Events, Integrations are described but not built in the prototype. Each has an introduction page in `BetterClubhouse.dc.html` stating its purpose, its three or four capabilities, and where it sits — use those as the functional brief. Two notes:

- **Rate card** merges Fee Schedule and Membership Types.
- **Integrations** replaces the Fees Square page, the Merch Square page, the Xero page and the Comms provider settings with one screen listing three connections and a live status each.

---

## Interactions and behaviour

| Interaction | Behaviour |
| --- | --- |
| Sidebar nav | Sets the screen; shows the introduction if the flag and seen-state say so; closes any open drawer |
| Deep link (Today action, `Open accounts`, `Email these N`) | Sets the screen **and** its filter/selection, skips the introduction, marks the screen seen |
| Row click (Accounts, Audiences) | Opens the person drawer, tagged with where it was opened from |
| Drawer `Open full record` | Navigates to Directory with that person selected, filters cleared, drawer closed |
| Filter pill | Sets the filter; the header caption and all derived counts update |
| Search | Filters on name and club-role title; selection falls back to the first remaining row |
| Inventory line click | Loads it into the movement panel |
| `Issue & charge` | Decrements stock, posts the charge to the account, appends the movement, raises a toast |
| `Email these N` | Loads the matching audience and raises a toast naming the count |
| `?` beside a title | Reopens that screen's introduction |
| Toast | Dismissed manually via `✕` |

Every count in the UI is derived from the same source data. The sidebar badge, the Today row, the Accounts KPI and the audience count for "owes money" are one number computed once — if issuing a shirt changes a balance, all four move together. Do not denormalise these.

## State

| State | Purpose |
| --- | --- |
| `screen` | Current screen key |
| `intro` | Whether the interim page is showing |
| `introMode` | `'always' \| 'once' \| 'never'` — per user |
| `seen` | Map of screen → introduced already |
| `query`, `dirSeg`, `dirSel` | Directory search, segment filter, selection |
| `acctFilter` | Accounts filter |
| `audSel` | Selected audience |
| `invCat`, `invSel` | Inventory category filter, selected line |
| `moveKind`, `moveQty`, `issueTo` | Movement form |
| `products`, `charges`, `movements` | Mutable stock, posted charges, movement log |
| `drawer`, `drawerFrom` | Open person, and where from |
| `toast` | Current toast or null |

In the real app, `products` / `charges` / `movements` come from the API; the rest is view state. `introMode` and `seen` persist per user.

## Responsive

The current code has **two** breakpoints doing the same job — the shared layout hides the sidebar under a hamburger below 768px (`md:`), while the ClubManager redesign switches at 1280px and drops its detail pane. Collapse to one.

- **≥1200px** — full layout, side panels beside their tables
- **900–1200px** — side panels stack below their tables and fill the row; master–detail stays side by side
- **≤900px** — master–detail becomes list-then-record; the list fills the row
- **≤1024px** — sidebar becomes a drawer behind `☰` (single breakpoint for the whole module)
- Tables scroll horizontally inside their wrapper rather than collapsing

Minimum hit target 44px. The current 8px-padded nav items and `py-2.5` table rows are below that — raise them on touch.

---

## ⚠ BetterComms: Super Admin vs club scope

**This is a hard rule, not a preference.**

BetterComms serves two audiences from one engine and they must stay strictly separated:

- **Club scope** — a club officer emailing their own people. Fields come from the club's Directory, accounts, roster, events and email activity, and nothing else.
- **Super Admin scope** — BetterCricket's own marketing against the Clubs Directory: `is_trialing`, `requested_trial`, `had_demo`, `customer_status`, `directory_status`, `engagement_score`, `visited_page`, `exported`, plus the marketing-org context switch and the act-as-club mechanism.

**Never expose Super Admin features, fields, context bars or copy to a club build** — not behind a dropdown, not greyed out, not in a segment field list. A club must never see BetterCricket's sales telemetry or the Clubs Directory context.

Today this leaks: `CommsSegments.jsx` ships `DIRECTORY_FIELD_DEFS` alongside `CLUB_FIELD_DEFS` and switches on a context flag, and `CommsContextBar` renders the marketing-org switch inside the club surface. Move the prospect field set behind BetterCRM or a super-admin-only mount, and drop the context bar from the club build entirely. Same engine, two mounts.

Apply the same rule to any future module that gains a platform-side mode.

---

## Naming

Proposed: **BetterClubhouse** — the clubhouse is the one building where all four things happen (subs at the bar, the noticeboard, the storeroom, the committee upstairs). Warm, spoken, three syllables, sport-neutral, and it survives a seventh tool being added.

Runners-up with rationale are in `BetterAdmin Review.dc.html` (option `1c`): **BetterPavilion** (cricket-native, less portable), **BetterBackroom** (flatters the volunteers, sounds hidden), **BetterKeeper** (best pun, reads as one job title).

`BetterClubManager` is deliberately not carried forward: it is three words, it names a person's job rather than the club, and it is already one of the four sub-module names, so the umbrella and a section would share a name.

The old names become sidebar section headings and stop being brands: **People**, **Money**, **Stock**, **Comms**, **Club**, **Setup**. One lockup, one accent, one switcher entry — four fewer products for a club to be sold, learn and pay for.

---

## Suggested sequencing

1. **Shell.** Promote the ClubManager screen header, grouped nav and card scale into `ModuleLayout`, and move the switcher, bookmarks and account into the sidebar footer. All four sub-modules get the glow-up in one change with no screen rewritten. Also: `box-sizing: border-box` globally, and `.pb-card` radius 6px → 10px.
2. **Language.** One button, one input, one pill, one stat card, one table head — deleting the four local copies in `bettermerch/ui.jsx`, `betterselect/ui.jsx`, `clubmanager/redesign/ui.jsx` and the inline ones in the Fees and Comms pages. Mono caps stop being buttons and go back to being labels. Most of the visual incoherence dies here.
3. **Merge the nav.** One sidebar, six groups, capability-gated. Rename, one lockup, one amber accent, one switcher entry. Collapse Contacts/Lists/Segments into Audiences, and the two Square pages into Integrations.
4. **Join the data.** The Directory becomes the only person list; Fees and Merch balances become one account per person. This is the real work and the real payoff — every cross-module moment becomes possible, and Today can finally speak for the whole club.

## Overlap and duplication to resolve

Full findings with evidence are in `BetterAdmin Review.dc.html` (option `1b`). Summary, most expensive first:

1. **Three person lists, and the same CSV importer written twice.** `AdminFeesMembers.jsx` and `clubmanager/redesign/screens/Directory.jsx` ship importers whose columns are character-for-character identical (`name, email, mobile, category, roles`), and `CommsContacts` keeps a third list whose `source` field (`player` / `member` / `import` / `manual`) admits the problem. → One Directory. Fees owns a *fee account* hanging off a directory person. Contacts is deleted as a concept.
2. **A member can owe money in two ledgers that never meet.** Fees stamps `FINANCIAL` / `OWES`; Merch separately has an `issued` movement kind carrying money and an "Owed by members" KPI. → One account per person, with families rolling up.
3. **Square is connected twice; reports and settings scattered four ways.** → One Integrations screen, one Reports screen with a source selector.
4. **"Event" means four things** — a club activity (ClubManager), email telemetry (Comms segments), pipeline activity (CRM), a social post (`EventPostEditor`). → Reserve **Event** for the thing a member attends; rename Comms telemetry to **Activity**. Then "registered for presentation night" becomes a legal audience rule, which is the integration worth having.
5. **Contacts, Lists and Segments are three answers to one question.** → One **Audience**.
6. **Expiry-and-renewal implemented twice with identical semantics** (qualifications; stock expiry and equipment service). → One `renewal` primitive — thing, date, lead time, owner — feeding Today.
7. **Your own sales telemetry inside a club-facing module.** → See the scope rule above.
8. **Two role vocabularies, only one visible.** → Keep them separate, label them honestly; the Directory record is the reconciliation.

## Cross-module moments to make possible

These are the joins that make it feel like one product, and each one only works after the consolidations above:

- `34 owe subs` on Today → account list already filtered → `Email these 34` → compose with the audience attached and a reminder template chosen
- Issue a playing shirt in Inventory → pick the person from the Directory → the charge lands on their account and the balance moves in the same second
- Open registration on an event → payments through the one Square connection, confirmation through the one email provider
- Two canteen shifts unfilled → email everyone holding the Canteen role who isn't already rostered, from the gap itself
- One person record carrying balance, roles, quals, hours, committee terms, family and kit — the same drawer from anywhere
- Today aggregating money, stock, renewals, roster gaps and the diary

## Assets

`assets/` holds the real module marks, copied from `frontend/src/assets/modules/`: `betteradmin.svg`, `betterclubmanager.svg`, `betterstats.svg`, `betterselect.svg`, `betteriq.svg`, `bettersocials.svg`. Use them at 26–28px `border-radius: 8px` in a lockup and 14–16px `border-radius: 4–5px` in a switcher pill, per `ModuleLockup.jsx` and `ModuleSwitcher.jsx`.

Icons are not assets — they are inline SVG paths already in the codebase. Take them from `ICON_PATHS` in `pages/admin/betterselect/ui.jsx` and `NAV_ICONS` in `pages/admin/clubmanager/redesign/ClubManagerApp.jsx`. Nav mapping used: Today `overview`, Directory `teams`, Roster `fixtures`, Committee `sheet`, Accounts `money`, Payments `list`, Rate card `sheet`, Inventory `list`, Equipment `settings`, Emails `list`, Audiences `filter`, Diary `ladders`, Events `timer`, Integrations `share`, Settings `settings`.

The **BetterClubhouse mark does not exist yet** and is a striped placeholder in the prototype. It needs drawing before launch.

## Source files the designs were built from

See `github.md` for the full screen → repo-file map. The load-bearing ones:

- `frontend/src/components/admin/ModuleLayout.jsx` — the shell to upgrade
- `frontend/src/components/admin/{BetterFees,BetterComms,BetterMerch,BetterClubManager}Layout.jsx` — the four nav definitions to merge
- `frontend/src/components/admin/{ModuleSwitcher,BookmarkButton,CommsContextBar}.jsx` — chrome to relocate; the context bar to remove from club builds
- `frontend/src/components/ModuleLockup.jsx` — the one way a module is shown
- `frontend/src/pages/admin/clubmanager/redesign/{ui.jsx,ClubManagerApp.jsx,screens/*}` — the primitives and screens to promote
- `frontend/src/pages/admin/{AdminFeesMembers,AdminFeePayments}.jsx` — the Fees screens to rebuild as Accounts
- `frontend/src/pages/admin/bettercomms/{CommsCampaigns,CommsSegments,CommsContacts,CommsLists}.jsx` — to collapse into Emails + Audiences
- `frontend/src/pages/admin/bettermerch/{BetterMerchHome,MerchStock,ui.jsx}` — the KPI + alert pattern to keep, and the stock screens to rebuild
- `frontend/src/pages/admin/betterselect/ui.jsx` — the `Icon` set
- `frontend/src/styles/theme.css`, `frontend/tailwind.config.js`, `frontend/src/lib/moduleBrand.js` — tokens and brand registry
