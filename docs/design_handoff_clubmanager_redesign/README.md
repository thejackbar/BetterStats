# Handoff: BetterClubManager — People & Club redesign + Volunteer Rostering

## Overview

BetterClubManager's People (Committee, Volunteers, Roles, Activities, Families, Qualifications)
and Club (Events, Assets & Facilities, Bookings, Club Diary) modules currently sit as nine
separate sidebar pages with little connective tissue. Each entity is administered in isolation:
you add a volunteer on one page, give them a role from a catalogue on a second, record a
qualification on a third, log their hours against an activity on a fourth, and nothing links back.

This redesign collapses those nine pages into **eight connected surfaces** and adds the missing
entity the club actually runs on: a **weekly volunteer roster**, organised into configurable
operational areas, filled by drag-and-drop, with rules that block or warn.

It also reframes two entities the current build under-serves:

- **Club Diary** becomes a *template library* of recurring club obligations that **generates** a
  dated season plan — with role→person substitution, dependencies, blockages, critical path
  and budgets. It is not a calendar.
- **Assets & Facilities / Bookings** becomes a per-facility **availability grid** plus an
  **approval queue with conflict detection**, plus gear-loan tracking.

Concepts are borrowed from TidyHQ (one contact record driving everything; meetings with
agendas/minutes/motions; tasks with due dates and assignees; event ticketing with attendee
lists) — **not** TidyHQ's UI or navigation. Visual language stays entirely within the existing
BetterCricket / BetterStats theme.

---

## About the Design Files

**The files in this bundle are design references created in HTML.** They are prototypes that
demonstrate intended layout, styling, interaction and rule behaviour. They are **not production
code to copy into the app**.

The task is to **recreate these designs inside the existing BetterStats frontend** — React +
Vite + Tailwind, using the established patterns in `frontend/src/`:

- Page components under `frontend/src/pages/admin/`
- Shared module chrome: `components/admin/ModuleLayout.jsx`, `BetterClubManagerLayout.jsx`
- Module branding and accent from `lib/moduleBrand.js`
- Theme tokens from `styles/theme.css` and `tailwind.config.js`
- Icon glyph paths from `pages/admin/betterselect/ui.jsx` (`ICON_PATHS`)
- Member/player pickers from `components/admin/clubmanager/pickers.jsx`

Do **not** port the prototype's inline-style strings. Every colour in this document maps to an
existing Tailwind token in the repo (the `pb-*` palette); use those tokens, not raw hex, wherever
a token exists. The prototype uses inline literals purely because it is a standalone HTML file.

The prototype's data is fixture data written to make the rules and relationships visible. Real
implementation needs the schema and endpoints described under **Data model & API** below.

---

## Fidelity

**High-fidelity.** Colours, typography, spacing, radii, states and copy are final and taken from
the existing theme. Recreate the UI faithfully using the repo's Tailwind tokens and component
patterns. Where this document gives a pixel value, it is intentional — the roster and facility
grids in particular have geometry that matters (see the notes on row heights).

Two things are deliberately *not* final and should be treated as scaffolding:

1. Fixture data (names, dates, dollar amounts).
2. The three prototype toggles (`landingScreen`, `enforceQualifications`, `weeklyShiftCap`) —
   these exist to demo behaviour. `enforceQualifications` and `weeklyShiftCap` should become
   real club-level settings; `landingScreen` should not ship.

---

## Information architecture

### Current (9 sidebar items, two hub pages above them)

```
Overview
  People  →  Committee · Volunteers · Roles · Activities · Families · Qualifications
  Club    →  Events · Assets & Facilities · Club Diary
```

### Redesigned (8 items, no hub pages)

```
Today                        ← new: aggregated blockages across every module
PEOPLE
  Roster                     ← new entity
  Directory                  ← absorbs Volunteers + Families + Qualifications + hours
  Committee                  ← absorbs Committee positions + meetings + motions + actions
CLUB
  Club Diary                 ← rebuilt as template → generated season plan
  Facilities                 ← absorbs Assets & Facilities + Bookings
  Events                     ← ticketing / RSVP / attendees
SETUP
  Areas & Roles              ← absorbs Roles + Activities + Qualification types
                               and configures the Roster
```

**Rationale for each merge**

| Old page | Where it goes | Why |
| --- | --- | --- |
| Volunteers | Directory (person record) | A volunteer is not a separate species from a member. The roster needs one record with roles, quals, availability and load. |
| Families | Directory → Family section | A family is a relationship between person records, not a list to administer separately. |
| Qualifications | Directory (per person) + Areas & Roles (types) | Expiry only matters in context: whose, and what it gates. |
| Activities | Areas & Roles (catalogue) + Directory (hours by activity) | The catalogue is setup; the hours are a fact about a person. |
| Roles | Areas & Roles | Roles exist to gate rostering and to name committee positions. Both are configuration. |
| Committee | Committee (unchanged name, much larger scope) | Positions alone are a table; the value is meetings, motions and action items with due dates. |
| Assets & Facilities + Bookings | Facilities | Bookings are the only interesting thing about a facility; splitting them hid every conflict. |

**Cross-links that must exist** (these are the point of the redesign):

- Directory role chip → filters Directory by that role
- Directory family member → selects that person's record
- Directory diary task → opens the Club Diary task drawer
- Directory → "Open this week's roster"
- Committee agenda item → opens its linked Club Diary task
- Committee position holder / action assignee → that person's Directory record
- Events → "Roster this event" and "Open diary task"
- Today → every card and every attention row deep-links to the relevant screen **and tab**
- Areas & Roles → shows which areas each role and qualification gates

---

## Screens / Views

Eight screens. Shared chrome first, then each screen.

### Shared: shell

- **Sidebar**: 232px fixed, `bg #10141d`, right border `1px solid #1d2331`, `position: sticky; top: 0; height: 100vh`.
  - Header block, 16px padding, bottom border `1px solid #1d2331`:
    - Club avatar: 32×32, radius 4px, `bg rgba(99,102,241,0.15)`, text `#6366F1`, weight 700, 15px, centred initial.
    - Club name 14px/700; season line below in JetBrains Mono 10px, `#3a3f50`, letter-spacing 0.08em, uppercase.
    - Module lockup: 26×26 SVG (radius 8px) + "Better**ClubManager**" at 14px/700, the second word in `#6366F1`.
  - Section captions: JetBrains Mono 10px, letter-spacing 0.14em, `#5b6072`, padding `16px 16px 4px`. Captions are `PEOPLE`, `CLUB`, `SETUP`.
  - Nav items: full width, padding `8px 16px`, 13.5px, gap 11px, 17px stroke-1.6 icon.
    - Idle: `color #5b6072`, transparent background, `border-right: 2px solid transparent`.
    - Active: `color #6366F1`, `background rgba(99,102,241,0.1)`, `border-right: 2px solid #6366F1`.
  - Roster nav item carries a count pill when shifts are unfilled: JetBrains Mono 9.5px, `bg rgba(245,181,66,0.18)`, text `#f5b542`, radius 999px, padding `1px 6px`, pushed right with `margin-left: auto`.

- **Responsive**: below **1280px** the sidebar becomes off-canvas: `position: fixed; inset-block: 0; left: 0; z-index: 70`, with a dismissing backdrop at `z-index: 69`, `rgba(0,0,0,0.5)`. A ☰ button appears in each screen header (`border 1px solid #262d3d`, radius 7px, `color #8a90a2`, padding `7px 9px`).
  - **Two implementation traps, both found in review:**
    1. Every screen header must establish a stacking context above the drawer — `position: sticky; top: 0; z-index: 80`. A statically-positioned header lets the fixed drawer paint over its own ☰ button, trapping the user.
    2. Selecting a nav item must close the drawer in the same action. Any code path that changes the current screen (nav, and all cross-screen deep links) must also clear the open state.

- **Screen header** (every screen): `position: sticky; top: 0; z-index: 80`, `bg #10141d`, bottom border `1px solid #1d2331`, padding `14px 20px`, flex, gap 16px, wrapping.
  - `h1` 19px/700, letter-spacing −0.01em.
  - Sub-line: JetBrains Mono 10px, letter-spacing 0.14em, `#5b6072`, uppercase.
  - Segmented tab control where present: wrapper `bg #161b27`, `border 1px solid #1d2331`, radius 8px, padding 3px; buttons padding `5px 12px`, radius 6px, 12.5px/600; active `bg rgba(99,102,241,0.15)`, `color #6366F1`; idle transparent, `color #5b6072`.
  - Stat readouts right-aligned via `margin-left: auto`: value 19px/700 tabular-nums, label JetBrains Mono 9px letter-spacing 0.1em `#5b6072`.

- **Toast / feedback strip**: sits directly under the header, full width, padding `10px 20px`, 13px, bottom border `1px solid #1d2331`. Title 600 weight, body at 0.85 opacity, dismiss ✕ pushed right at 0.6 opacity.
  - `ok` — `bg rgba(22,199,132,0.12)`, text `#16c784`
  - `warn` — `bg rgba(245,181,66,0.12)`, text `#f5b542`
  - `block` — `bg rgba(239,91,91,0.12)`, text `#ef5b5b`
  - `info` — `bg rgba(99,102,241,0.12)`, text `#6366F1`

- **Right-hand drawer** (person record, diary task): overlay `position: fixed; inset: 0; z-index: 90`, `bg rgba(0,0,0,0.55)`, panel right-aligned, 440–460px wide (`max-width: 92vw`), `bg #10141d`, `border-left: 1px solid #262d3d`, entering with `riseIn` — `opacity 0 → 1`, `translateY(6px) → none`, 180ms ease. Clicking the scrim closes; clicks inside must stop propagation.

- **Scrollbars**: 9px, thumb `#262d3d` radius 8px, transparent track.

---

### 1. Today

**Purpose** — answer "what needs me right now" in one screen, and route to it. Replaces the two
hub-card pages, which carried no information.

**Layout** — single scrolling column, `max-width: 74rem`, padding `22px 24px`.

1. **Week strip**: 4-column grid, gap 8px. Each card `bg #10141d`, `border 1px solid #1d2331`, radius 10px, padding `14px 16px`, clickable.
   - Value 21px/700 `#6366F1` tabular-nums
   - Label JetBrains Mono 9px letter-spacing 0.1em `#5b6072`, margin-top 4px
   - Detail 12px `#8a90a2`, margin-top 7px, line-height 1.45
   - The four cards: roster coverage %, bookings this week, next meeting, events live.
2. **Attention caption**: JetBrains Mono 10px letter-spacing 0.14em `#3a3f50` — reads "N things need you".
3. **Attention rows**: vertical stack, gap 7px. Each row `bg #10141d`, radius 10px, padding `14px 16px`, clickable, `border 1px solid <tone>40` where tone is `#ef5b5b` (blocking) or `#f5b542` (warning).
   - Count: 26px/700 tabular-nums in the tone colour, fixed 40px width, `flex-shrink: 0`
   - Unit line 14.5px/600 `#e6e8ef`
   - Detail 12.5px `#8a90a2`, line-height 1.5, margin-top 4px
   - CTA: JetBrains Mono 9.5px letter-spacing 0.1em in the tone colour, margin-top 7px, suffixed " →"

**Rows are derived, not authored.** Ordered blocking-first, and each row is omitted entirely when
its count is zero:

| Row | Tone | Derived from | Deep link |
| --- | --- | --- | --- |
| Diary tasks overdue | block | dated diary tasks past due, not done, not blocked | Club Diary, plan tab, issues filter on |
| Tasks blocked by another | block | tasks with an incomplete dependency | Club Diary, plan tab, issues filter on |
| Qualifications expired | block | any person's qual past expiry | Directory, "quals to renew" filter on |
| Booking requests clash | block | pending requests overlapping a confirmed booking | Facilities, requests tab |
| Shifts unfilled this week | warn | roster slots with no assignee | Roster |
| Committee actions overdue | warn | meeting action items in overdue state | Committee, motions & actions tab |
| Items overdue back | warn | gear loans past due, not returned | Facilities, assets tab |
| Committee positions vacant | warn | positions with no holder | Committee, positions tab |
| Events with no volunteers | warn | events whose requirement is unmet | Events, that event selected |

---

### 2. Roster  ← the new entity

**Purpose** — build and publish the club's repeating weekly roster. Modelled on Deputy's
scheduling interaction, not its visual design.

**Header** — title + "WEEK OF MON 3 NOV 2026"; People/Areas segmented control; then right-aligned:
coverage readout (`filled` 18px/700 + `/ N FILLED` in mono 10px), a 120×6px progress bar (radius 3px,
track `#161b27`, fill `#6366F1`, or `#16c784` at 100%), a "Candidates" panel toggle, "Auto-fill open
shifts" (secondary: `border 1px solid #262d3d`, `color #8a90a2`, radius 8px, padding `8px 14px`, 13px/600),
and "Publish week" (primary: `bg #6366F1`, `color #fff`, same metrics).

**Grid** — horizontally scrollable, `min-width: 1266px` at full size.
Columns: `216px repeat(7, minmax(150px, 1fr))`; below 1280px, `176px repeat(7, minmax(0, 1fr))`.

- **Column header row**: `position: sticky; top: 0; z-index: 20`, `bg #0a0d14`, bottom border `1px solid #262d3d`. Each day cell padding `10px 12px`: day-of-week in mono 10px letter-spacing 0.14em `#5b6072`, date 13px/600 `#8a90a2`. Sat/Sun tinted `rgba(99,102,241,0.05)`.
- **Open shifts row** (People view only): background `rgba(245,181,66,0.04)`, bottom border `1px solid #262d3d`. Label cell: "Open shifts" 13px/700 `#f5b542` plus "N unfilled · drag onto a person" in mono 10px `#5b6072`. Cells hold unfilled shift chips.
  - Identical unfilled slots collapse into one chip with a `×N` multiplier (4 open umpire slots read "Umpires ×4"), and each cell shows at most 2 chips with a "+ N more" / "show less" expander (mono 9.5px, `border 1px dashed rgba(245,181,66,0.4)`, radius 6px, `color #f5b542`).
  - **This row must be hidden by returning `display: none` from its own style** — a `hidden` attribute cannot beat the element's inline `display: grid` (found in review).
- **Person rows** (People view): label cell padding `10px 14px`, clickable, opens the person drawer.
  - Avatar 28×28 circle, `bg #161b27`, `border 1.5px solid #262d3d`, mono 10px/600 `#8a90a2`, initials.
  - Name 13.5px/600, role line mono 9.5px `#5b6072`, both ellipsised.
  - Load bar underneath: 4px tall, radius 2px, track `#161b27`, fill `#6366F1` — `#ef5b5b` when over cap. Count label mono 9.5px, red when over.
  - Day cells: `min-height: 74px`, padding 6px, gap 5px, right border `1px solid #1d2331`. Days the person has not declared available are hatched: `repeating-linear-gradient(45deg, transparent 0 6px, rgba(58,63,80,0.10) 6px 12px)` and, when empty, carry the label `UNAVAILABLE` in mono 9px `#3a3f50`, centred.
- **Area rows** (Areas view): department band rows (`bg #10141d`, mono 10px letter-spacing 0.14em `#8a90a2`, spanning all columns) followed by one row per area. Label cell shows a 9×9 radius-3 colour swatch, area name 13.5px/600, fill count (mono 9.5px, `#16c784` when complete else `#f5b542`), and the requirement line in mono 9.5px `#5b6072`. Cells hold one chip per shift, showing the assignee's name or `OPEN`.

**Shift chip** — radius 7px, padding `6px 8px`, `cursor: grab`, `user-select: none`.
- Assigned: `background color-mix(in srgb, <area> 13%, transparent)`, `border 1px solid color-mix(in srgb, <area> 40%, transparent)`, text in the area colour.
- Open: `bg rgba(245,181,66,0.10)`, `border 1px solid rgba(245,181,66,0.45)`, text `#f5b542`.
- Warned: border `rgba(245,181,66,0.5)` and a `!` glyph pushed right in `#f5b542` 11px.
- Content: 7px colour dot + area name 12px/600 (ellipsised), then the time range in mono 10px at 0.75 opacity.
- Drop target highlight: `background rgba(99,102,241,0.14)` + `inset 0 0 0 1.5px #6366F1` on the cell; `box-shadow: 0 0 0 1.5px #6366F1` on a chip.
- Selected chip: `outline: 1.5px solid #6366F1; outline-offset: 1px`.

**Two drag directions — both required**

| View | Dragged | Dropped on | Result |
| --- | --- | --- | --- |
| People | a shift chip | a person's day cell, or the Open row | shift reassigned to that person, or returned to Open |
| Areas | a volunteer card from the side panel | a shift chip | that volunteer assigned to that shift |

Selecting any shift (click) ranks candidates in the side panel regardless of view.

**Side panel** — 296px, `border-left: 1px solid #1d2331`, `bg #10141d`, padding 16px. Below 1280px it becomes a fixed overlay at 320px, `z-index: 65`.
- When a shift is selected: a summary card (`bg #161b27`, `border 1px solid #262d3d`, radius 8px, padding 12px) with colour dot + area name 14px/600, the when-line in mono 11px `#8a90a2`, the requirement in mono 10px `#5b6072`, then "Fill best match" (primary, flex-1) and "Clear" (secondary).
- Caption flips between `RANKED CANDIDATES` and `VOLUNTEER POOL`; a hint line (11.5px `#5b6072`) explains the drag direction for the current view.
- Candidate cards: `bg #161b27`, radius 8px, padding `9px 10px`, `border 1px solid #1d2331` — `rgba(99,102,241,0.35)` for a clean match. 26px avatar, name 13px/600, sub-line mono 9.5px `#5b6072` carrying either the first warning or "Clear match · N shifts". Right-hand chip `FIT` (`bg rgba(99,102,241,0.15)`, `#6366F1`) or `WARN` (`bg rgba(245,181,66,0.15)`, `#f5b542`), mono 9px. Cards are `draggable`.
- **Rules applied** list at the bottom, above a `1px solid #1d2331` divider: 6px dot (red = blocks, amber = warns) + label at 11.5px `#8a90a2`.

**Rostering rules** — the substance of the screen.

*Blocking* (drop refused, red toast naming every reason):
1. Missing the qualification the area requires — e.g. RSA for Bar, accreditation for Umpires. Configurable off (`enforceQualifications`), in which case it degrades to a warning.
2. Volunteer has not declared that day available.
3. Overlaps another shift they already hold that day.

*Warning* (drop allowed, amber toast, chip flagged, warning persists on the chip):
4. Not in the role the area calls for.
5. Over their weekly shift cap.
6. Heavy week — 4+ shifts.
7. Clashes with a match they are selected in (BetterSelect integration).
8. Another member of the same family is already on that exact slot.

**Auto-fill** — iterates unfilled slots; for each, ranks all volunteers, discards anyone with a
blocking violation, prefers zero-warning candidates, and breaks ties on current load (fairness).
Reports how many it placed and how many remain unfillable.

**Publish** — with gaps, publishes anyway and states that volunteers can self-nominate for the
remainder subject to confirmation. With none, states that rostered volunteers receive their shift
plus a check-in tap that logs their hours.

**Not yet designed (agreed as follow-up):** the volunteer-facing self-nomination queue.

---

### 3. Directory

**Purpose** — one record per person. Replaces Volunteers, Families, Qualifications and the hours
half of Activities.

**Header** — title, "ONE RECORD PER PERSON · N of M SHOWN", a search input (`bg #161b27`,
`border 1px solid #262d3d`, radius 8px, padding `8px 12px`, 13.5px, `flex: 1`, `max-width: 340px`)
matching name, role and position; then filter pills.

**Filter pills** — radius 999px, padding `5px 11px`, 12px. Active `border 1px solid rgba(99,102,241,0.45)`,
`bg rgba(99,102,241,0.12)`, `color #6366F1`; idle `border 1px solid #262d3d`, transparent, `#8a90a2`.
Segments: Everyone / Committees / Volunteers / Parents / Players. Plus a "Quals to renew" pill in the
amber treatment, and a dismissible "Role: X ✕" pill when a role filter is active.

**Body** — 300px list column (`border-right: 1px solid #1d2331`, `bg #10141d`, padding 10px) beside a
scrolling detail pane (padding `22px 24px`). No page navigation between people.

- **List rows**: padding `9px 11px`, radius 8px, gap 10px. Selected `border 1px solid rgba(99,102,241,0.4)`, `bg rgba(99,102,241,0.08)`. 30px avatar, name 13.5px/600, sub-line mono 9.5px `#5b6072` (committee position, else roles, else "Member"), a 6px amber dot when any qualification needs renewing, and total hours in mono 10px `#3a3f50`.
- **Detail header**: 52px avatar, name 22px/700 letter-spacing −0.01em, contact line 12.5px `#5b6072` (email · phone · member since), then segment chips (mono 9px letter-spacing 0.08em, `bg #161b27`, `border 1px solid #262d3d`, `#8a90a2`, radius 4px).
- **Stat strip**: 4-column grid, gap 8px — hours this season, shifts this week, diary tasks, quals to renew. Card `bg #10141d`, `border 1px solid #1d2331`, radius 8px, padding `11px 13px`; value 19px/700 `#6366F1`, label mono 9px letter-spacing 0.1em.
- **Two-column section grid**, gap `22px 28px`, each section captioned in mono 10px letter-spacing 0.14em `#3a3f50`:
  - **Committee position** — title 14px/600 + term in mono 10px, or "Not on the committee."
  - **Roles** — chips `bg rgba(99,102,241,0.15)`, `#6366F1`, radius 5px, padding `3px 9px`, 12.5px; clicking one filters the whole Directory by that role. Interested-in roles below as dashed chips (`border 1px dashed #3a3f50`, `#8a90a2`) suffixed "· interested".
  - **Qualifications** — row per qual, `bg #10141d`, radius 7px, padding `8px 11px`: name 13px, expiry in mono 9.5px, status chip right. `CURRENT` `#16c784` / `EXPIRES SOON` `#f5b542` (within 60 days) / `EXPIRED` `#ef5b5b`, each mono 9px with a 40%-alpha border of its own colour.
  - **Hours by activity** — labelled bars, 4px tall, fill `#6366F1`, scaled against the person's own maximum.
  - **Diary tasks** — the tasks this person owns, each with live status chip; clicking opens the Club Diary task drawer.
  - **Family** — "<Surname> family" caption; linked members as clickable rows with 26px avatar and a → affordance, or "No linked family members."
- **Footer action**: "Open this week's roster →" (secondary button).

---

### 4. Committee

**Purpose** — positions, and the meeting record that actually governs the club.

Three tabs: **Meetings** (default), **Positions**, **Motions & actions**.
Header stats: positions filled (amber when any vacancy), open actions (red when any overdue), motions this season.

**Meetings tab** — 290px meeting list beside a detail pane.
- List cards: `bg #10141d`, `border 1px solid #1d2331`, radius 8px, padding `11px 12px`; selected in the indigo treatment. Title 13.5px/600, meta line mono 9.5px (kind · date), status chip: `TODAY` `#6366F1` / `SCHEDULED` `#8a90a2` / `MINUTES APPROVED` `#16c784`.
- Detail: title 21px/700 + status chip; mono 11px line "kind · date · N min agenda".
  - **Agenda** — numbered rows (`bg #10141d`, radius 8px, padding `10px 13px`): index in mono 10px `#3a3f50` (12px wide), item 13.5px, owner + duration in mono 9.5px. Items tied to diary work carry a `DIARY TASK →` chip (mono 9px, `border 1px solid rgba(99,102,241,0.4)`, `#6366F1`) that opens the task drawer.
  - **Present / Apologies** — 13px `#8a90a2`, line-height 1.55.
  - **Motions** — card per motion: text 13px line-height 1.45, outcome chip right (`CARRIED` / `CARRIED UNANIMOUSLY` green, `LOST` red), then "Moved X, seconded Y · tally" in mono 9.5px.
  - **Action items** — row per action, clickable through to the assignee's Directory record: text 13.5px, "who · due date" in mono 9.5px, state chip `DONE` `#16c784` / `OPEN` `#6366F1` / `OVERDUE` `#ef5b5b`.

**Positions tab** — `max-width: 56rem`. A vacancy callout when any position is unfilled
(`bg rgba(245,181,66,0.07)`, `border 1px solid rgba(245,181,66,0.25)`, `#f5b542`, radius 8px, 12.5px)
naming them and noting that their diary tasks have nobody to substitute in. Then a row per position:
title 13px `#8a90a2`, holder 13.5px/600 (`#f5b542` reading "Vacant" when empty), an `EXEC` chip for
executive positions, term right-aligned in mono 9.5px, and a → when the row is navigable. Vacant rows
take an amber border.

**Motions & actions tab** — two columns: the full season motion register, and every open action across
all meetings with its source meeting named.

---

### 5. Club Diary  ← rebuilt concept

**Purpose** — hold the club's recurring institutional knowledge as a **template**, generate a dated
plan for each season from it with roles substituted for the people currently holding them, then track
that plan by due date, budget, blockage and critical path.

Two tabs: **Season plan** (default) and **Template library**.
Header: "2026/27 SEASON · GENERATED FROM TEMPLATE, EDITED SINCE"; stats: dated tasks done, overdue, blocked, spent / budgeted.

**Season plan**

1. **Two-column analysis strip** (padding `14px 20px`, bottom border):
   - **Critical path** — caption "CRITICAL PATH — N days of chained work"; the chain rendered as
     `Task → Task → Task` at 13px inside `bg rgba(239,91,91,0.07)`, `border 1px solid rgba(239,91,91,0.25)`, radius 8px.
   - **Blockages** — one clickable row per overdue task: `bg rgba(239,91,91,0.07)`, 7px red dot, title 13px/600, and a detail line naming the owner, the date it was due, and **what it is holding up**.
2. **Filter row**: cadence pills (All / Annual / One-Time / Quarterly / Monthly / Weekly / Conditional) in the indigo pill treatment, plus an "Overdue & blocked only" pill in red.
3. **Timeline**: `min-width: 1000px`, columns `330px 1fr`, 12 month columns Jul→Jun.
   - Month header cells are **day-proportional**: `flex: <days-in-month> 0 0`.
   - **Gridlines in the track must be derived from the same cumulative day offsets** as those headers — a `repeating-linear-gradient` of 12 equal columns drifts from the real month boundaries by up to ~2 days (found in review). Build an explicit `linear-gradient` with a stop at each month's cumulative percentage.
   - Grouped by cadence with collapsible headers (`bg #10141d`, caret + cadence in mono 10px letter-spacing 0.14em + task count).
   - Task rows: label column shows an 8px status dot (2px-radius square for milestones), title 13.5px/600 — struck through in `#8a90a2` when done — and a meta line "Role → Person · due date", or the recurrence rule for repeating tasks. Right-aligned chips: `⛔ N` when blocked (red, dashed-free 1px border), `CP` when on the critical path (`bg rgba(239,91,91,0.15)`, `#ef5b5b`).
   - Bars: absolutely positioned by day fraction over 365, height 20px, radius 5px, `background color-mix(in srgb, <tone> 22%, transparent)`, border in the tone (solid full-strength when on the critical path). Blocked bars add `repeating-linear-gradient(45deg, transparent 0 4px, rgba(239,91,91,0.28) 4px 8px)`. Recurring and conditional tasks render as a dashed band with a striped fill across their active span instead of a discrete bar. Bar label is the budget when there is one, else the status. Over-budget tasks show "$N over" in red just past the bar's right edge.
   - A 1px `rgba(99,102,241,0.45)` today line runs through every row at the current date's fraction.
   - Status tones: `DONE` `#16c784` · `IN PROGRESS` `#6366F1` · `OVERDUE` `#ef5b5b` · `BLOCKED` `#ef5b5b` · `NOT STARTED` `#5b6072` · `MILESTONE` `#a855f7` · `RECURS` `#06b6d4` · `ON TRIGGER` `#f5b542`.

**Task drawer** — title 17px/700, status chip + `ON CRITICAL PATH` chip; a 2×2 fact grid (cadence,
role, assigned, window or recurrence rule) in `bg #161b27` cards; budget with a 5px progress bar
(green, red when overspent); **Depends on** and **Holds up** lists where every entry is clickable and
carries the other task's live status; and a footer line stating which template generated it and which
role was substituted for whom.

**Template library** — the knowledge base. Row per template: title 14.5px/600 + cadence chip, then
"Role · timing rule" in mono 10px (timing expressed relative to the season anchor, e.g. "Due 6 weeks
before Round 1", "28th of Oct, Jan, Apr, Jul", "Trigger: >10mm rain in the 24h before a match"), with
budget guide and dependency count right-aligned.
Beside it, a 340px **Generate a season** panel: explanatory copy, the full role → next-season-holder
substitution table, and a primary "Generate 2027/28 plan" button. Generating states how many tasks were
created, that dates were anchored to Round 1, that roles were substituted, and that nothing is locked.

**Derived, not stored**: blocked state (any incomplete dependency), overdue state (due date passed),
and the critical path (longest dependency chain through remaining work).

---

### 6. Facilities

**Purpose** — see availability at a glance, approve or decline requests with conflicts already
detected, and track gear that has left the building.

Three tabs: **Availability** (default), **Requests** (count badge), **Assets & loans**.
Header sub-line states "EACH COLUMN RUNS 8AM → MIDNIGHT". A source legend sits right-aligned:
`MATCH` `#6366F1` · `TRAINING` `#a855f7` · `EVENT` `#f5b542` · `HIRE` `#06b6d4` · `DIARY` `#16c784` · `MAINT` `#ef5b5b`.

**Availability** — `min-width: 1100px`, columns `200px repeat(7, minmax(0, 1fr))`, one row per facility.
Label cell: name 13.5px/600, kind in mono 9.5px `#5b6072`, hours-booked in mono 9.5px `#3a3f50`.
Day cells are `position: relative`, `height: 190px`, spanning 8:00–24:00 — roughly 11.9px per hour.

- **Booking blocks**: `position: absolute`, `left: 3px; right: 3px`, top and height computed in **pixels** from the hour offset, radius 5px, padding `2px 6px`, `overflow: hidden`. Fill `color-mix(in srgb, <source> 18%, transparent)`, border 45% alpha of the source colour. Conflicting blocks take a `#ef5b5b` border, red 45° hatching and red text. Pending (unapproved) blocks are dashed at 0.85 opacity.
- **Geometry matters.** An earlier 92px row height made 11 of 13 blocks clip their own text. Two rules: keep the row tall enough that a 2-hour booking clears two text lines, give blocks a **pixel** minimum height (~20px), and below ~26px put title and time on **one line** (`display: flex; align-items: baseline; gap: 6px`) rather than stacking them. A percentage `min-height` cannot guarantee a text box.

**Requests** — `max-width: 62rem`. Explanatory line, then a card per request: title 14.5px/600 + source
chip, "Facility · day date · time range" in mono 11px, "requester · note" in 12.5px `#5b6072`, and
Approve / Decline buttons.
- Every request is checked against every confirmed booking on that space **before display**.
- Clashing requests take a red border and a callout row (`bg rgba(239,91,91,0.08)`, radius 7px, 12px
  `#ef5b5b`) naming the conflicting booking and its hours; the primary button degrades to a muted
  "Approve anyway" (`bg #161b27`, `#5b6072`) and pressing it refuses with a blocking toast that names
  the clash and suggests moving, shortening or declining.
- Approving a clean request moves it onto the calendar and confirms that it now shows in Events and the
  Club Diary. Declining confirms the requester is notified with the reason.

**Assets & loans** — two columns.
- **Out on loan**: row per item, `bg #10141d`, radius 8px, padding `10px 13px` — item 13.5px/600,
  "who · out date · due date" in mono 9.5px, status chip `ON LOAN` green / `OVERDUE` red (overdue rows
  take a red border), and a "Returned" button that clears it.
- **Inventory**: row per asset type with an availability bar (green, red when everything is out),
  "N of M available" in mono 10px, and a condition note in mono 9.5px `#3a3f50`.

---

### 7. Events

**Purpose** — ticketing, RSVPs, who is actually coming, and whether anyone is rostered to run it.

**Layout** — 290px event list beside a detail pane.
- List cards mirror the Committee pattern; status chips `OPEN` `#16c784` / `ON SALE` `#6366F1` / `DRAFT` `#8a90a2`; meta line "date · venue · N sold".
- Detail: title 21px/700 + status chip, then "when · venue · kind" in mono 11px.
  - 3-column stat strip: tickets sold or confirmed (`sold/capacity`), revenue, diary budget.
  - Capacity bar 5px, `#6366F1`, turning `#f5b542` above 90%; "N% of capacity" in mono 9.5px.
  - **Ticket types** — labelled bars: "Name · $price" with "sold / quantity" right-aligned.
  - **Volunteers needed** — callout stating the requirement and how many are rostered. Amber when
    partially staffed, red when nobody is (`bg rgba(239,91,91,0.07)`). Below it, "Roster this event →"
    and, where the event has one, "Open diary task →".
  - **Attendees** — `max-width: 46rem`, row per attendee: name 13px, "ticket type · note" in mono 9.5px,
    and a status chip — `PAID` green / `UNPAID` amber / `RSVP YES` green / `RSVP NO` red / `FREE` green.
    Roll-up rows ("+ 63 more ticket holders", "12 families yet to reply") render dashed at `#5b6072`.
  - Draft events show a dashed empty state: "Not on sale yet — no attendees. Publish the event to start
    taking registrations."

---

### 8. Areas & Roles

**Purpose** — the configuration every other screen reads from. Sub-line says exactly that.

Four tabs: **Operational areas** (default), **Roles**, **Activities**, **Qualifications**.

**Operational areas** — `max-width: 68rem`. Grouped by department (Food & Beverage,
Cricket Operations — both configurable). Card per area: 9×9 colour swatch + name 14.5px/600 +
"N shifts / week" right-aligned; requirement line "Role · must hold Qualification" in mono 10px; then
the **weekly shift pattern** as chips — "Sat 12pm–12am ×2" — each in the area's own colour at 12%
fill / 35% border. Copy states plainly that changing a pattern here changes what next week's roster
generates.

**Roles** — two columns. General roles: title 13.5px/600, holder count, and which roster areas the
role gates (`#6366F1` when it gates something, `#3a3f50` when it does not). Committee positions:
title + holder, amber when vacant.

**Activities** — `max-width: 44rem`. Labelled hour bars, ranked. Copy explains that a completed roster
shift books its hours against one of these once the volunteer taps to confirm.

**Qualifications** — `max-width: 48rem`. Per type: name, "N hold · N to renew" (amber when any need
renewing), and what it gates — `#ef5b5b` "Gates rostering for Bar, Kitchen" or `#3a3f50`
"Recorded only — gates nothing". Copy makes the causal link explicit: an expired RSA is why a bar shift
refuses a drop.

---

## Interactions & Behavior

**Navigation**
- Sidebar selects a screen; below 1280px it also closes the drawer.
- Deep links set the screen **and** the destination tab **and** any relevant filter or selection in one
  action (e.g. Today's expired-qualifications row lands on Directory with the renew filter already on).
- Tabs, filter pills and list selections are local screen state.

**Drag and drop** (HTML5 DnD in the prototype; use whatever the codebase already uses)
- `dragstart` records what is moving — a shift id in People view, a person id from the panel in Areas view.
- `dragover` must `preventDefault()` and set `dropEffect = 'move'`, and marks the hovered target for
  highlight. In Areas view, ignore dragover entirely unless a person is being dragged.
- `drop` resolves the assignment through the rules engine. `dragend`/`dragleave` clear the highlight.
- Every assignment produces a toast: green on success, amber naming each warning, red naming each
  blocking reason and refusing the change.

**Transitions** — drawers enter with `riseIn` (opacity + 6px rise, 180ms ease). Nothing else animates;
this is a data tool.

**Empty states** — written as sentences that say what to do, never "No data". Examples in use:
"Nothing waiting on you. New requests land here with their conflicts already checked.", "Nobody matches
those filters.", "Everything is back in the shed.", "Nothing — this one can start any time."

**Responsive** — desktop-only by decision. Below 1280px: off-canvas sidebar with backdrop, overlay
candidates panel, narrower grid columns. Grids scroll horizontally rather than reflowing.

---

## State Management

Screen-level state in the prototype; map to the app's own patterns (server state for entities, local
state for view state).

**View state** — current screen; per-screen tab; roster view (people/areas); selected shift; selected
person; selected meeting; selected event; diary cadence filter; diary issues-only flag; collapsed diary
groups; directory query / segment / role filter / expiring-only flag; drag payload; hovered drop target;
active toast; sidebar open; candidates panel open; viewport width.

**Entity state that mutates in the prototype** — roster slot assignments and their warnings; confirmed
bookings; pending requests; returned loans.

**Derived every render — never stored**
- Roster: coverage, per-person load, per-area fill, candidate ranking, every rule violation.
- Club Diary: blocked state, overdue state, critical path, dependents map, budget totals.
- Directory: qualification status from expiry, hour totals, family membership.
- Facilities: booking conflicts, request clashes.
- Today: every attention row and count.

**Settings that should become real** — `enforceQualifications` (hard block vs warn) and
`weeklyShiftCap` (club-wide override of per-person caps).

---

## Data model & API

Entities the redesign needs, beyond what exists today.

**OperationalArea** — id, name, department, colour, requiredRoleId, requiredQualificationTypeId (nullable), active.

**ShiftPattern** — id, areaId, dayOfWeek, startTime, endTime, headcount. The repeating weekly template.

**RosterWeek** — id, seasonId, weekStartDate, status (draft/published).

**Shift** — id, rosterWeekId, areaId, dayOfWeek, start, end, assigneeId (nullable), warnings[], checkInAt (nullable), loggedActivityId (nullable).

**VolunteerProfile** (extends the person record) — availableDays[], maxShiftsPerWeek, rolesInterested[], livesNearby.

**ShiftNomination** — id, shiftId, personId, status (nominated/confirmed/declined). *Design pending.*

**DiaryTemplate** — id, title, cadence (Annual/One-Time/Quarterly/Monthly/Weekly/Conditional), roleId, timingRule (anchor + offset, or recurrence, or trigger text), budgetGuide, dependsOnTemplateIds[].

**DiaryTask** — id, seasonId, templateId (nullable for ad-hoc), title, cadence, roleId, assigneeId, startDate, dueDate, budget, spent, state (open/done), dependsOnTaskIds[].

**Meeting** — id, kind (Committee/AGM/Special), title, date, status.
**AgendaItem** — id, meetingId, order, text, ownerId, minutes, linkedDiaryTaskId (nullable).
**Attendance** — meetingId, personId, status (present/apology).
**Motion** — id, meetingId, text, moverId, seconderId, outcome, tally.
**ActionItem** — id, meetingId, text, assigneeId, dueDate, state.

**Facility** — id, name, kind, capacity, bookable.
**Booking** — id, facilityId, start, end, title, source (match/training/event/hire/diary/maintenance), sourceId, status (confirmed/pending/declined), requesterId, note.
**Asset** — id, name, total, condition.
**Loan** — id, assetId, quantity, personId, outDate, dueDate, returnedAt.

**Event** — id, title, start, end, venueId, kind (Ticketed/RSVP/Free registration), capacity, status, linkedDiaryTaskId, volunteerRequirement.
**TicketType** — id, eventId, name, price, quantity, sold.
**Attendee** — id, eventId, personId (nullable for guests), ticketTypeId, paidStatus, guests, note.

**Server-side rule endpoints worth having** rather than reimplementing per client:
`POST /roster/:weekId/check` (candidate + shift → blocks[] and warns[]),
`POST /roster/:weekId/autofill`,
`POST /bookings/check-conflict`,
`GET  /diary/:seasonId/critical-path`,
`POST /diary/generate` (templateSet + season → tasks with roles substituted).

---

## Design Tokens

All of these already exist in `styles/theme.css` / `tailwind.config.js` as the `pb-*` palette — use the
tokens, not these literals. Values given so the mapping is unambiguous.

**Surfaces**
| Value | Use |
| --- | --- |
| `#0a0d14` | app background, grid header background |
| `#10141d` | panels, cards, sidebar, headers |
| `#161b27` | inputs, inset cards, bar tracks, segmented-control wells |
| `#1d2331` | primary borders and dividers |
| `#262d3d` | stronger borders, input borders, scrollbar thumb |

**Text**
| Value | Use |
| --- | --- |
| `#e6e8ef` | primary text |
| `#8a90a2` | secondary text |
| `#5b6072` | tertiary / meta text |
| `#3a3f50` | captions, faintest labels |

**Accent & status**
| Value | Use |
| --- | --- |
| `#6366F1` | BetterClubManager accent — active nav, primary buttons, stat values, match bookings |
| `#16c784` | success, current qualifications, complete, diary bookings |
| `#f5b542` | warning, open shifts, expiring, vacancies, event bookings |
| `#ef5b5b` | blocking, overdue, conflicts, critical path |
| `#a855f7` | milestones, training bookings |
| `#06b6d4` | recurring tasks, external hire |
| `#f97316` | Kitchen area |
| `#3b82f6` | Umpires area |

**Alpha conventions** — accent fill `rgba(99,102,241,0.15)`, accent hairline `rgba(99,102,241,0.3–0.45)`,
active nav wash `rgba(99,102,241,0.1)`, weekend column tint `rgba(99,102,241,0.03–0.05)`, status callout
fill `<status> 7%` with a `25%` border, chip border `<status>66`.
Area-derived chips use `color-mix(in srgb, <area> 13%, transparent)` fill with a `40%` border.

**Typography**
- Display / UI: **Geist** — 400, 500, 600, 700.
- Mono: **JetBrains Mono** — labels, dates, times, counts, all-caps captions.
- Scale: 22px/700 record titles · 21px/700 detail titles · 19px/700 screen titles and stat values ·
  14.5px/600 card titles · 13.5px/600 row titles · 13px body · 12.5px secondary · 12px chips ·
  11.5px rule text · 10–11px mono meta · 9–9.5px mono captions.
- Caption convention: JetBrains Mono, 10px, letter-spacing 0.14em, uppercase, `#3a3f50`.
- Sub-header convention: JetBrains Mono, 10px, letter-spacing 0.14em, uppercase, `#5b6072`.
- `font-variant-numeric: tabular-nums` on every count, stat and money value.

**Spacing** — 2 · 3 · 4 · 5 · 6 · 7 · 8 · 9 · 10 · 11 · 12 · 13 · 14 · 16 · 18 · 20 · 22 · 24 · 26 · 28px.
Screen padding `22px 24px`; header padding `14px 20px`; card padding `11px 13px` to `14px 16px`;
grid cell padding 6px; section gaps `22px 28px`.

**Radii** — 2px (bar fills) · 4px (chips, small controls) · 5px (role chips, blocks) · 6px (segmented
buttons, inner rows) · 7px (shift chips, buttons) · 8px (cards, inputs, panels) · 9–10px (feature cards)
· 999px (filter pills) · 50% (avatars).

**Bars** — 4px (inline metrics) · 5px (budget, capacity) · 6px (header coverage). Track `#161b27`,
radius half the height.

**Grid geometry** (load-bearing)
- Roster columns `216px repeat(7, minmax(150px, 1fr))`, `min-width: 1266px`; narrow `176px repeat(7, minmax(0, 1fr))`.
- Roster cell `min-height: 74px`.
- Club Diary columns `330px 1fr`, `min-width: 1000px`, track height 42px, 12 day-proportional month columns.
- Facilities columns `200px repeat(7, minmax(0, 1fr))`, `min-width: 1100px`, cell height **190px** for an 8am–midnight span.

**Shadows** — overlay panels only: `0 0 40px rgba(0,0,0,0.5)`. Scrims `rgba(0,0,0,0.5)` (nav) and
`rgba(0,0,0,0.55)` (drawers). No card shadows.

---

## Assets

- `assets/betterclubmanager.svg` — module lockup mark, copied from
  `frontend/src/assets/modules/betterclubmanager.svg`. Already in the repo; reference it there.
- **Icons** are inline SVG paths at 17–18px, `stroke-width: 1.6`, `stroke-linecap`/`linejoin: round`,
  `fill: none`, `currentColor`. They are the same glyphs as `ICON_PATHS` in
  `frontend/src/pages/admin/betterselect/ui.jsx` — use that map rather than the prototype's copies.
- **Fonts**: Geist and JetBrains Mono, already loaded by the app.
- No raster images, no illustrations, no emoji. Two text glyphs are used as icons — `⚠` in callouts and
  `⛔` in the diary blocker chip.

---

## Files

| File | What it is |
| --- | --- |
| `BetterClubManager Redesign.dc.html` | **The redesign.** All eight screens, working drag-and-drop rostering, live rules engine, diary critical-path computation, booking conflict detection. The reference implementation. |
| `BetterClubManager Today.dc.html` | Recreation of the **current** UI (shell, Volunteers, Roles, Activities, Qualifications in full; Committee / Events / Assets / Diary headers and tab sets). Use it to diff old against new and to confirm which existing screens are being replaced. |
| `support.js` | Runtime the two HTML prototypes need in order to open in a browser. Not part of the design and not to be ported. |
| `github.md` | Source-repo record: repo, branch, and the screen → source-file map showing which existing pages each new screen replaces. |
| `assets/betterclubmanager.svg` | Module mark, as above. |

Open either HTML file directly in a browser. The redesign opens on **Today**; every screen is reachable
from the sidebar, and the roster's drag-and-drop, auto-fill, rule warnings, request approvals and diary
drawers are all live.

---

## Suggested implementation order

1. **Areas & Roles** — nothing else can be generated without operational areas, shift patterns and the
   role/qualification links. Ship this first even though it is the least visible.
2. **Directory** — the person record everything else points at; fold in the four pages it replaces.
3. **Roster** — the rules engine, then People view, then Areas view. Biggest single piece of work.
4. **Club Diary** — template model, generation, then dependency and critical-path derivation.
5. **Facilities** — availability grid, then the request queue with conflict checks, then loans.
6. **Committee** and **Events** — largely conventional CRUD against the schema above.
7. **Today** — trivial once the other seven expose their counts; do it last, not first.

## Known gaps

- **Volunteer self-nomination** for open shifts is referenced by the publish flow but not designed.
  Needs a volunteer-facing surface and a confirmation queue for the admin.
- **Permissions** — three audiences were identified (club secretary/admin, paid club manager, area
  coordinators who should only see their own patch). The designs assume full admin; scoping an area
  coordinator to their own areas still needs design.
- **Mobile** — out of scope by decision, other than volunteers viewing and accepting shifts.
- **Roster rules** are all-on in the prototype. If clubs need them individually configurable, that is a
  settings surface not yet designed.
