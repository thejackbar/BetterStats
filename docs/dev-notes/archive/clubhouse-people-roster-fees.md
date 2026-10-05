# Archive: clubhouse-people-roster-fees

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: BetterAdmin / Clubhouse shell and UI kit, Directory, roster and areas and roles, fees, merch and assets.
Read the distilled rules first: `docs/dev-notes/guides/clubhouse-people-roster-fees.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L5134-5309 -->
## Committee's buttons are the house control, everywhere in BetterAdmin (v9.52.0, Aug 2026)

Asked for directly: make every module screen's button row look like the
Committee screen's, centre several of them on the title line, and add a search
where a section had none. Plus a reported failure: Facilities read "Could not
load facilities." whatever the club held.

- **"COULD NOT LOAD FACILITIES" WAS A MIS-READ KEY, NOT A BACKEND FAULT.**
  `GET /club-admin/assets/items` answers `{assets: [...]}` and `Facilities.jsx`
  read `r?.items || r || []` — so the fallback handed the RESPONSE OBJECT to
  `.filter`, which threw inside the `.then` and was caught by the outer
  `.catch` as the load failing. **One wrong key took the entire screen down**,
  including the availability grid and the requests queue, neither of which
  reads that endpoint. `rows(res, ...keys)` replaces the `a || b || []` chain
  and ALWAYS hands back an array, so the next shape change costs one list
  rather than the page. Reproduced against the real payload shape before
  fixing it (`AdminAssets.jsx` was reading `d.assets` correctly all along,
  which is what confirmed which side was wrong).
- **THE BOX IS EXPORTED SEPARATELY FROM THE TABS, and that is the whole
  design.** `SegButtons` / `SegTabs` are one row, one value, pick exactly one.
  Half the rows asked for are not that: Accounts' four filters can each be on
  at once, the Directory's and Payments' Membership / Role / More are MENUS,
  and Stock's category narrowing is a real `<select>`. So `SegGroup` (the
  container) and `SegItem` (the button) are their own exports in BOTH kits, and
  `SegButtons`/`SegTabs` are now built from them — one definition of the
  chrome, filled by whatever control the row actually needs. A `seg` prop on
  `MenuButton` wears the same button styling, which is what lets a dropdown sit
  in the row without reading as a different kind of thing.
- **CENTRING TAKES THREE PARTS, NOT ONE.** The title block and the right-hand
  group each claim an equal share of what is left (`flex: 1 1 0`), so the row
  between them lands in the middle of the header rather than wherever the title
  happens to end. `HEAD_SIDE` / `HEAD_CENTRE` / `HEAD_SIDE_END` are that rule
  named, mirroring what `ModuleLayout`'s own `tabs` prop already did, so a
  screen on either shell centres the same way. **The right-hand box stays even
  when it is empty** (the Roster's grid actions on the Hours tab): it has a
  zero basis so it costs nothing, and dropping it lets the title take the whole
  row and slides the buttons off centre.
- **A CENTRING WRAPPER MUST BE ALLOWED TO SHRINK, and getting this wrong is
  what the 390px check caught.** The first cut gave both `HEAD_CENTRE` and
  `ModuleLayout`'s `tabs` slot `flex-shrink: 0`, which pushed Areas & Roles
  68px sideways and made Accounts' existing overflow worse — the same trap the
  Selection-header note documents, since `flex-wrap` on the row cannot save a
  child told not to shrink. Both are shrinkable now. It costs nothing at width,
  because the two sides carry a ZERO basis and therefore give way first: the
  centre only narrows once there is genuinely nothing left, which is exactly
  when its own buttons should be wrapping.
- **`Header` DECLARED INSIDE THE RENDER had to go before a search box could be
  added to it.** Facilities, Events and Club Diary each wrote
  `const Header = () => …` in the render body, so React saw a different element
  TYPE every render and tore the subtree down — which throws the caret out of
  an input after one character, the bug the Committee screen already documents.
  All three are plain functions CALLED (`{header()}`) now. The suite types
  character by character and re-reads `document.activeElement` after each,
  since `fill()` sets the value in one shot and cannot catch this.
- **A SEARCH BOX SEARCHES ITS SECTION, NOT THE LIST ON SCREEN.** Facilities
  keeps a facility whose BOOKING matches ("where is the Doyle engagement" is
  what a booking grid is asked), and Events keeps an event whose ATTENDEE
  matches. `EntityManager` and `AreaEditor` gained a `query` prop that narrows
  what is DRAWN and never what is loaded, so a reorder still renumbers against
  the whole list — and the drag grip is WITHDRAWN while a query runs, rather
  than letting a filtered list be dragged into an order nobody can see.
- **The Directory's own search moved to its own line and the four menus took
  the title line.** Nothing about what they filter changed; the chips
  underneath still carry the state, which is what makes hiding options in a
  menu defensible.
- **Payments gained the chips it never had.** Its menus moved off the filter
  row, so the state needed a visible home; Accounts already worked this way.
  `usePeopleFilters({ seg: true })` is per-call, so Accounts' own copy of those
  menus is untouched.
- **Stock's category control is still a real `<select>`.** A club's category
  tree is as long as the club makes it, which is what a native picker is for —
  it just wears the same box as the buttons above it now.
- **Verified in Chromium** (`frontend/verification/verify_clubhouse_buttons_browser.mjs`,
  63 checks against the real screens with the API stubbed at the network
  layer): every button row's box read off the COMPUTED style rather than a
  class name, so a hand-built lookalike fails; each centred row measured as
  "its midpoint sits within 24px of the header's"; each new search box measured
  as below the caption and starting at the header's own left edge; the caret
  held per character in all four; the reported Facilities failure gone and the
  club's own facilities and gear drawn; and no page errors. **With the change
  stashed, 41 of the 63 fail**, including the reported one.
- **Three screens overflow at 390px and that is PRE-EXISTING**, confirmed by
  re-running the same probe with the change stashed: Accounts 33px, Payments
  111px ("Import bank CSV") and Stock 12px ("New product"), each an action
  cluster carrying `shrink-0`, none of them a button row this touched. The
  suite's budget is those measured numbers, so this can never make one worse or
  introduce a new one — Accounts in fact comes out at 27px now.

### The pale edge was a class that does not exist (v9.52.1)

- **`border pb-hairline` IS NOT A CLASS, and that is the reported "white
  border".** `pb-hairline` is a tailwind COLOUR (`colors.pb.hairline`), so the
  utility is `border-pb-hairline`; the bare form only applies the WIDTH and lets
  the colour fall through to Tailwind's preflight default of `#e5e7eb`. Measured
  off the computed style rather than guessed: Committee's own box reads
  `rgb(29,35,49)` and the Tailwind kit's read `rgb(229,231,235)`. Only
  `.pb-hairline-t/-b/-r` exist as real classes, which is why the sibling
  `border-b pb-hairline-b` on the module header was always right.
- **The same typo appears ~917 times across the app and is DELIBERATELY NOT
  SWEPT.** One shared definition (`SEG_GROUP_CLS`) is what every reported row
  reads, so fixing it there fixed all of them; a 900-line sweep of screens
  nobody mentioned is a different change with a different risk, and belongs to
  whoever asks for it. The suite asserts the COLOUR now, not "has a border", so
  a box that regresses to the default fails.
- **A SEARCH BOX BELONGS BELOW THE BUTTONS THAT NARROW THE SAME LIST.**
  Committee, Club Diary, Accounts, Payments and Stock all read top to bottom:
  pick the group, then search what is left. `isAbove` measures it off the real
  boxes, so "below" is a fact rather than a reading of the source order.
- **`HeaderSearch` gained a `style` escape hatch, and it is load-bearing.** Its
  `flex: 1 1 100%` is what forces the line break inside the wrapping header;
  inside a COLUMN container that basis is read against the HEIGHT instead, so a
  caller there passes `{ flex: '0 0 auto' }`.
- **Moving the Club Diary's box down beside its cadence buttons would have left
  the template library with no search at all** — those buttons only exist on the
  Season plan tab. The templates tab keeps its own box at the top of the list it
  narrows.
- **`SegItem` gained `as`**, mirroring `Button`'s own escape hatch, for a row
  whose item NAVIGATES rather than toggles. `aria-pressed` is only emitted on a
  real button, since a link has no pressed state.
- **Events' and Facilities' Manage links moved INTO their section's box**, in
  the middle of the row. They were floating on the right on their own, which
  read as a different kind of control from the buttons beside them. The suite
  asserts the box's children IN ORDER, so "in between" is measured.
- **Facilities is `Facilities & Assets`** in the sidebar, on the screen and on
  its manage screen. The rename is display only: `/admin/assets`,
  `MANAGE_ASSETS` and every stored row are untouched.
- **Verified in Chromium**: the suite is 84 checks now, and **31 of them fail
  against the previous commit** — including the pale border, read back as the
  measured `rgb(229,231,235)`.

### The primary action moved down beside the search (v9.53.1)

- **NARROWING A LIST AND ADDING TO IT ARE ONE LINE.** `+ Add person`,
  `Publish week`, `+ New meeting`, `Add member`, `Import bank CSV` and
  `New product` each sat on the title line while the box that searches the very
  list they add to sat below. They are on the right of the search row now, on
  all six screens.
- **`HeaderSearch` grew a `trailing` slot** rather than each screen hand-rolling
  the row, so the two kits stay one definition apart: `ModuleLayout`'s `twoRow`
  block does the same job for the screens on that shell.
- **`items-start` → `items-end` is the whole `ModuleLayout` change, and it is
  the right one.** Accounts, Payments and Stock stack their filters (a control
  row, then the search under it), so top-aligning the action cluster put it
  beside the CONTROLS. Bottom-aligning lands it beside the search. A screen
  whose filters are a single row (every Comms screen) is unaffected — both
  boxes are one line tall either way — which is why this needed no per-screen
  opt-in.
- **On Committee the action had to LEAVE the header for the readouts to
  arrive.** `POSITIONS FILLED` / `OPEN ACTIONS` / `MOTIONS THIS SEASON` are
  passed in as `header(children)` and carry `marginLeft: 'auto'`; so did the
  action cluster, and two auto-margin siblings share the space rather than one
  taking the right edge. Removing the action div is what puts the readouts on
  the title line — nothing about the readouts themselves changed.
- **`alignSelf: 'stretch'` on Committee's search row is load-bearing.** The
  column above it sets `alignItems: 'flex-start'`, so the row is only as wide as
  its own contents and an auto left margin has nothing to push the button
  against. Without it the action sits immediately after CLEAR rather than on the
  right.
- **A `const` READ BY THE HEADER MUST BE DECLARED ABOVE IT.** Roster's
  `publish` sat below `header`, which is fine while the header does not read it
  — but two of the three `header(...)` calls are inside EARLY RETURNS that run
  before that point in the render body, so putting the button in the header
  threw on a temporal-dead-zone reference the moment the "no operational areas
  yet" screen drew. `publish` moved up. A `data &&` guard is not a fix here:
  that branch runs with `data` truthy.
- **Verified in Chromium**: `onSearchLine` measures the two real boxes — they
  must overlap VERTICALLY (genuinely one line, not a wrap) and the action must
  start after the box ends. A check that only asked "are both in the header"
  would have passed with the action still up on the title line. The Committee
  readouts are measured against the `<h1>` for the same reason. The suite is 97
  checks now, and **all seven of the new ones fail against the previous
  commit** — each reporting the gap it was measuring (`aTop` 76 against `iTop`
  133 on the Directory, 173/224 on the Roster, 76/244 on Committee, 127/171 on
  Accounts and Payments, 119/161 on Stock), and the Committee readouts reading
  `sameLine: false`.

<!-- END original CLAUDE.md L5134-5309 -->
<!-- BEGIN original CLAUDE.md L5310-5391 -->
## ONE asset register: equipment is not inventory (migration 279, v9.53.0, Aug 2026)

Asked for after a question about the accounting shape: treat inventory as one
thing, and property / facilities / fixed assets / equipment as another.

- **THE SPLIT WAS JUSTIFIED AGAINST THE WRONG TABLE, and that is the whole
  origin of the duplication.** Migration 177's own docstring says why it did not
  reuse what existed: general club property "is a different concern from
  BetterMerch's retail/kit stock tracking (merch_assets, a paid-module table)".
  `merch_assets` is not retail or kit stock — retail stock is `merch_products` /
  `merch_variants`, which carry quantity, cost, price and movements. The
  MerchAsset model's own docstring reads "an individual high-value piece of
  equipment (bowling machine, covers, sight screen) … quantity is implicitly 1;
  not stock-counted", which is a fixed-asset register. 177 compared club
  property against a table it believed was stock and built a second register of
  the same thing. A mis-description, not a decision, which is why undoing it is
  safe.
- **`club_assets` IS THE BASE, and not arbitrarily: `merch_assets` is a strict
  column SUBSET of it.** All thirteen of its columns have same-named,
  same-typed, same-defaulted twins among `club_assets`' sixteen; only `category`
  and `facility_id` are unique to the club side. Nothing is given up, and the
  club register additionally has maintenance history and lives in core.
- **`services/asset_register_ddl.py` is the ONE copy alembic and the lifespan
  mirror both run**, per the `vote_medal_ddl` rule, and it runs AFTER both
  tables are created in that same lifespan.
- **`merch_asset_id` MAKES THE CARRY IDEMPOTENT, `source` MAKES IT REVERSIBLE,
  and conflating the two would have destroyed club data.** A gap-filled row and
  an inserted row both carry the id, because both have dealt with that merch
  row and neither must be processed twice. Only an INSERTED row is the
  migration's to remove, so it is marked `source='merch'`; the first cut's
  downgrade deleted on the id and took the club's own pre-existing assets with
  it. **Found by the verification, not by reading the code.**
- **The carry FILLS, NEVER CLOBBERS.** Every field is `COALESCE(what is here,
  what is coming)`, so a figure somebody typed always wins. `condition` and
  `status` are NOT NULL on the club side, so they always have a value and are
  never touched. Notes are the one field where keeping what is here would lose
  something, so a merch note not already contained in the club note is
  appended.
- **`DISTINCT ON` picks one merch row per club row.** Two merch rows matching
  one club asset must not silently merge into a single object — the second
  stays uncarried and step 2 gives it its own row.
- **Matching is asset tag first, then case-folded name, and NOTHING fuzzier.** A
  serial number is a real identity. A club really can own a "Line marker" and a
  "Line marking machine", and folding those would put one object's service
  history on another.
- **The two vocabularies are MAPPED, not unioned** (`new`→`excellent`,
  `retired`→`unserviceable`, `out_for_repair`→`in_repair`), so the register ends
  up with one vocabulary rather than the sum of two.
- **`merch_assets` IS LEFT IN PLACE AND READ BY NOTHING**, the call 267 made for
  `vote_settings`. Its ROUTES are deleted rather than merely unused: a second
  register still answering writes could only drift from the live one.
- **THE ALERTS MOVED TO CORE, and that was half the point.** Service and
  replacement due fired only from the merch copy, so `club_assets.
  service_due_date` reached no bell, no Today row and no badge — a club without
  the paid module had a field that warned nobody. `assets.asset_alerts` +
  `GET /club-admin/assets/alerts` are core, with no module gate.
- **`replace_due_date` had existed since 177 through the model, DDL, API and
  serialiser with NO screen reading or writing it.** It is what the merch
  register raised its replacement alerts from, so it had to become reachable.
- **Deliberately NOT built: depreciation, useful life, written-down value,
  disposal proceeds, insurance valuation, or a total asset value.** None of them
  exists on either register today (`purchase_cost` is stored, filtered, and
  never summed anywhere), so this is a maintenance and cashflow register, not
  yet an accounting one. Making it one is a bigger, separate piece of work.
- **Verified against a real Postgres** (44 checks through the shipped statements
  and `asset_alerts` itself: the list applied three times to a populated pre-279
  schema without duplicating, the gap-fill filling and never clobbering, a note
  appended rather than dropped and an identical note not appended twice, a
  serial matching where the names differ, the enum mapping, two merch rows on
  one asset staying two, cross-club isolation, no merch row left behind, the
  alerts reading the carried dates and ignoring a retired asset, and the
  downgrade removing only what the carry created) and **driven in Chromium**
  (the suite is 90 now: the old Stock URL redirecting, Equipment gone from the
  Stock sidebar, and the service alert still reaching Today through the core
  endpoint).
- **A STUB THAT RETURNS THE WRONG SHAPE MEASURES A BROKEN PAGE.** The browser
  suite had `{seasons: […]}` and `{payments: […]}` where those routers answer
  bare ARRAYS, so Accounts and Payments threw on `.filter` and drew no table —
  and the 390px overflow "baseline" recorded from that was 33px / 111px rather
  than the real 245px / 168px. Check what a router actually returns before
  recording a measurement against it.

<!-- END original CLAUDE.md L5310-5391 -->
<!-- BEGIN original CLAUDE.md L7272-7292 -->
## Accounts kept resetting to the newest season (v9.25.2, Aug 2026)

Same report: work through 2025/26, open a member, come back, and you are in
2026/27.

- **`AdminFeeMemberDetail` already linked back with `?season=`; the Accounts
  screen just ignored it** — `useState('')` then "set `sorted[0]`" on every
  mount, unconditionally. Half the round trip had been built.
- **The season is URL state now**, seeded from `?season=` and mirrored back on
  change (`replace`, so the back button leaves the screen instead of walking the
  season history). It survives a refresh and is shareable, which is what the
  reported URL was.
- **A season named in the URL that the club no longer holds falls back to the
  newest** rather than leaving an empty screen with no way out.
- **Driven in Chromium** against the real screens with the API stubbed (11
  checks: the round trip holding 25/26, the back link, the no-param default, the
  stale-id fallback, the dropdown writing the URL, no page errors). The one
  failing check, horizontal overflow at 390px, was confirmed **pre-existing** by
  re-running it with the change stashed — the members table is wide, and that is
  not this fix's to solve.

<!-- END original CLAUDE.md L7272-7292 -->
<!-- BEGIN original CLAUDE.md L7403-7436 -->
## A picker inside a `<label>` cancels its own selection (v9.23.1.1, Aug 2026)

Reported from Accounts → Add member → Find in club: picking a player from the
search results left "Player or member" empty for one super admin and worked for
another, on the same club, the same person and the same two search results. The
difference was the browser. Chrome held the pick; Edge and Safari dropped it.

- **`Field` renders a `<label>`, and a label forwards a click on ANY descendant
  to whichever labelable control the field holds at that moment.** Choosing
  someone re-renders `PersonSearch` from "an input plus a list of option
  buttons" into "the chosen name plus a CLEAR button", so the forwarded click
  lands on Clear and wipes the choice before it can be seen. Nothing to do with
  the data, the club, capabilities or `active_club_id`, which is why two super
  admins on identical rows disagreed.
- **It survives only if the re-render has NOT committed by the time the browser
  forwards.** Verified in Chromium against the real components: commit the swap
  synchronously or in a microtask and the pick is wiped, defer it a task and it
  holds. That race is the whole "works for me, not for them", and no amount of
  reading the search endpoint would have found it.
- **`Field` gained `composite`**, which renders a `role="group"` div instead of
  a label. Use it for anything holding its own buttons. An ordinary input keeps
  the `<label>`, which is what gives it an accessible name and its
  click-the-caption-to-focus behaviour, so this is not a blanket change.
- **The pickers also defend themselves**: every option row and clear button in
  `clubmanager/pickers.jsx` goes through `choose()`, which calls
  `preventDefault()`. That suppresses the forwarding, so a picker mounted in a
  stray label still holds its choice. It cannot save a click on the label's own
  caption text, which is why the wrapper is the real fix and the guard is the
  net. The Club Diary's assigned-member and volunteer pickers had the same
  wrapper and are fixed too.
- **The trap generalises.** Any composite widget (a combobox, a chip
  multi-select, a segmented control) inside a `<label>` is a click-forwarding
  bug waiting to be reported by whoever is not on Chrome.

<!-- END original CLAUDE.md L7403-7436 -->
<!-- BEGIN original CLAUDE.md L7574-7596 -->
## A PlayHQ registration checkbox on Accounts (migration 235, v9.19.14, Aug 2026)

Playing a season requires the person to be registered with PlayHQ, and there
is no API this app can read that fact back from — Grassroots' `/scores/*`
and the Partner API are both match-data feeds, neither exposes registration
status. So it is a plain admin-ticked fact, the same shape as the existing
`is_new_registration` checkbox already living on the same row.

- **`fee_member_seasons.playhq_registered`** (bool, default false) +
  **`.playhq_registered_at`** (nullable timestamp, set/cleared with the
  checkbox — "when did we last check"). `PATCH /club-admin/fees/members/
  {id}/season` gained the field, alongside the two it already had.
- **Deliberately NOT carried forward by rollover** — `rollover_members`
  never sets it, so a rolled-over row always starts unticked. Registration is
  a per-season requirement; carrying last season's tick forward would assert
  something nobody has confirmed for the new season.
- **Surfaced in two places**: a PLAYHQ column on every Accounts row (checkbox,
  optimistic toggle via `PATCH .../season`) plus a "Not on PlayHQ" filter
  pill (`summary.playhq_missing`), and the same checkbox on the member detail
  page beside "New registration this season".
- **No new endpoint** — reuses the existing per-season PATCH, same as
  `is_new_registration`.

<!-- END original CLAUDE.md L7574-7596 -->
<!-- BEGIN original CLAUDE.md L7597-7667 -->
## An absent key is not a clear: the member's tier, and one save per page (v9.65.2, Sep 2026)

Reported off Sam Alborn's Accounts page (Applecross, 2025/26): changing the
Membership Type and saving RESET the Membership Tier to "Needs tier", and with
two panels edited only one panel's changes survived whichever button was
pressed.

- **ONE LINE CAUSED THE FIRST HALF, AND ITS OWN COMMENT SAID WHY IT WAS
  SAFE.** `patch_member_season` read `# fee_schedule_id is always present in
  the body; treat "" / null as clear.` It was not always present: **two**
  callers wrote that row without it — the membership panel saving a status, and
  the Accounts LIST ticking "Registered with PlayHQ" — so each of those writes
  silently wiped the member's tier and left the club reading "No tier assigned
  — fees won't calculate." **A comment asserting an invariant is not the
  invariant**; grep the callers.
- **THE KEY'S PRESENCE IS THE INTENT** (`model_fields_set`, the rule
  `select_show_age_under` already keeps): absent means this caller is not
  editing the tier, null or `""` means clear it. A genuine tri-state, and the
  three states are what let one save carry several panels.
- **THE ACCOUNTS LIST NEEDED NO FRONTEND CHANGE.** `togglePlayhq` was already
  sending only what it meant to change; the server was reading a field it had
  never been given. Fixing the reader fixes both screens at once, which is why
  the fix is server-side rather than "make every caller send the tier back" —
  that would put a stale tier from a browser on the wire and make the list
  screen able to overwrite a tier it never displayed.
- **THREE PANELS, TWO ENDPOINTS, ONE ACT OF SAVING.** Membership, Membership
  Tier and Contact & Notes each had their own button that saved only itself, so
  an admin who edited two and pressed one silently lost the other. Every button
  now saves every panel that has been TOUCHED — compared against a baseline
  captured on load, so an untouched panel writes nothing rather than re-sending
  fields nobody edited.
- **EACH ENDPOINT IS WRITTEN ONCE, with everything bound for it.** Membership
  and Tier both write `fee_member_seasons`; two PATCHes would race and one
  would overwrite the other's view of the row. The suite asserts one call per
  endpoint, not merely that both changes landed.
- **A PANEL SAYS IT IS UNSAVED, AND A BUTTON SAYS WHAT ELSE IT WILL WRITE.**
  Silently widening what a button does is its own surprise, so a touched panel
  carries an UNSAVED mark and a button about to write another panel's changes
  names them above it. With two or more touched the label itself becomes
  `SAVE ALL CHANGES (n)`.
- **PRESSING SAVE WITH NOTHING EDITED SENDS NOTHING** and says so, rather than
  reporting a save that never happened.
- **Verified against a real Postgres**
  (`backend/verification/verify_member_fees_form_save.py`, 41 checks through
  the shipped route bodies: the reported case replayed, the same write from the
  Accounts list, an explicit null AND an explicit `""` still clearing, a clear
  not rewriting the carry-forward default, the combined save landing every
  field of all three panels, every refusal leaving the stored tier exactly as
  it was, cross-club both ways, and a status-only save opening a season row
  without inventing a tier for it) **with a control run**: 5 fail against the
  previous commit, on exactly the reported behaviour.
- **Driven in Chromium** (`frontend/verification/verify_member_fees_save_browser.mjs`,
  39: the exact payload on the wire for each button, a membership save saying
  NOTHING about the tier, one write per endpoint, an untouched panel sending
  nothing, an intended clear carrying the key with null, the marks and the
  notes, and no overflow at 390px) **with a control run**: 15 fail.
- **A CHECK THAT MEASURES THE HARNESS IS NOT A CHECK, twice here.** The
  backend suite's `reset_tier` used a raw UPDATE and left the ORM's in-memory
  copy stale, so the next write looked like a no-op and a passing behaviour
  read as failing — it expires the session now. The browser suite counted
  `text=UNSAVED`, which matches every ANCESTOR of the pill too (5 for 2 marks),
  and counted page-view telemetry as a save; both are addressed by their own
  `data-testid` and a `/usage/` filter.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN.** The browser suite's
  first cut clicked `SAVE ALL CHANGES` directly, so against a build without the
  feature it died on an absent locator after three checks and said nothing
  about the other thirty-six. `pressSave` falls back to the panel's own label.
- **NOTICED, NOT FIXED**: nothing warns on navigating away from the page with a
  panel still marked UNSAVED. The marks make it visible, and a route-leave
  guard is its own change.

<!-- END original CLAUDE.md L7597-7667 -->
<!-- BEGIN original CLAUDE.md L7668-7709 -->
## BetterFees season rollover: undo, find-and-add, and remove (v9.19.13, Aug 2026)

Reported from Applecross getting 26/27 ready: rolling players over before the
new season's fee schedule is set up leaves everyone mismatched (rollover
resolves each member's tier by name against the DESTINATION season's rate
card, so an empty rate card means everyone lands "needs tier" with no way
back short of SQL), there was no way to add a player who sat out last season
or one new to the club without minting a duplicate manual entry, and no way
to drop a player who isn't returning.

- **`POST /club-admin/fees/rollover/undo`** clears every `FeeMemberSeason`
  row for a season in one go — "Remove all" on the Accounts page, for
  exactly the mismatched-rollover case above. A member with a payment
  already recorded this season is kept, never deleted (`fee_member_seasons`
  → `fee_payments` is `ON DELETE CASCADE`, so removing the row would take
  real money with it). Deliberately a season-wide reset, not "undo only what
  the last rollover added" — by the time someone reaches for this, sorting
  rollover-added rows from anyone else added since isn't a distinction worth
  making.
- **`RolloverModal` warns up front** when the destination season has no fee
  schedule yet, with a link straight to Fee Schedule, rather than letting the
  admin discover the mismatch after the fact.
- **`POST /club-admin/fees/members/enroll`** is the search-driven
  counterpart to the existing `create_member` (which only ever makes a
  brand-new non-playing person): finds an existing `fee_members` row OR a
  Stats player with none yet (`needs_member: true` off the existing
  `GET /people/search` / `PersonSearch` picker, the same one Committee's
  "start term" already uses), enrols them into the season via
  `members_svc.ensure_for_player` when needed, and is idempotent — enrolling
  someone already in the season just returns their row. "Add member" on the
  Accounts page is now two tabs, **Find in club** (this) and **New person**
  (the old manual-create form).
- **`DELETE /club-admin/fees/members/{member_id}/season`** removes one
  member's line from one season — a Remove action on every row and on the
  existing bulk-select bar, for "I know they're not coming back this
  season". Only clears that season's row; the person record and every other
  season are untouched. Refused (409) once a payment is recorded against
  them this season, for the same cascade-delete-real-money reason the undo
  above guards against.
- **No schema change** — all three read/write the existing `fee_members` /
  `fee_member_seasons` / `fee_payments` tables.

<!-- END original CLAUDE.md L7668-7709 -->
<!-- BEGIN original CLAUDE.md L7710-7748 -->
## Families is a BetterStats tool again, and a suggestion is opted INTO (v9.19.7, Aug 2026)

Families moved into BetterClubhouse with the v9.3.0 merge, which put it behind a
module a club may not hold — but a family grouping is Core data (it is a StatLab
player filter, `PLAYER_CONTEXT_FILTERS` in `services/statlab.py`), so it belongs
with Players and Seasons.

- **`/admin/families` is the screen again**, under BetterStats → Club Data.
  `AdminFamilies.jsx` renders in `BetterStatsLayout` and the route is
  `requireCore`, matching every other Core tool. That URL previously mounted the
  Clubhouse Directory; **`/admin/clubhouse/directory/families` now redirects to
  it**, so the Directory's own Families button and any bookmark still land.
  `BetterStatsLayout` had to start forwarding `caption` to `ModuleLayout` — it
  accepted only `title`, so the screen's mono subtitle was being dropped.
- **The nav item carries `MANAGE_FAMILIES`, the same capability
  `routers/families.py` enforces** — the rule the Clubhouse note below sets, and
  it holds across modules.
- **The Directory keeps its per-person family panel.** Only the setup screen
  moved; `dirCreateFamily`/`dirAddToFamily` are untouched, and a person's family
  is still read and edited where that person is.
- **A suggestion now starts with NOBODY selected.** It used to select every
  player sharing the surname and ask the admin to deselect the strangers, which
  makes the destructive reading ("these people are a family") the default and
  the correct one an act of removal. Two unrelated Matthews households are
  ordinary, so **opting a player IN is the deliberate act** and the confirm
  button is dead until someone is picked ("Select players above" → "Confirm —
  create with N"). An unselected player is drawn plain, not struck through — it
  means "not chosen yet", not "excluded".
- **Anyone left unselected stays in the suggestion list** and comes back on the
  next refresh, which is what lets one surname be split into two families across
  two passes. That behaviour is unchanged; the card now says so in place of the
  old "N will be re-suggested".
- **No backend change** — same endpoints, same payloads, same capability.
- **Driven in Chromium** (18 checks: the BetterStats shell and sidebar item, the
  old URL redirecting, the confirm button disabled with nothing selected and its
  label at each count, select-all/clear, the not-selected hint's singular and
  plural, both create and add-to-existing paths, no page errors, no overflow at
  390px).

<!-- END original CLAUDE.md L7710-7748 -->
<!-- BEGIN original CLAUDE.md L8536-8589 -->
## What kind of member is this? The Directory's three type axes (v9.11.1, Aug 2026)

Reported: BetterStats → Players marks a player Inactive, but the Clubhouse
Directory read every person the same — a social member, a life member, a
sponsor's contact and this season's opening bat all just "Player" or nothing.

- **There is no single "membership type" column, and there should not be. Three
  independent axes already exist and all three are now returned by
  `services/directory.list_people`:**
  1. **`membership_types`** (migration 175) — the club's own cross-season
     catalogue: Senior/Junior Player, Parent, Social Member, Life Member, Coach,
     Selector, Volunteer, Umpire, Scorer, **Sponsor Contact**, Committee Member,
     Honorary Member (`services/membership_types.STARTER_TYPES`, carrying
     `is_playing` + voting/insurance/WWCC/PlayHQ flags). **This is the real
     membership type**, and nothing seeds it — a club adopts the starter set or
     builds its own, so it is legitimately empty for plenty of clubs.
  2. **`fee_members.member_category`** — volunteer | parent | committee |
     life_member | third_party | official | other. What the Directory's own
     "Add person" TYPE dropdown writes; drives the computed `segs`.
  3. **`players.status`** ('active' | 'inactive') — the flag the Stats Players
     screen shows. Returned as `player_status`, and **NULL for a non-player**,
     so "not playing" and "not a player" stay distinguishable. Plus the
     `is_life_member` / `is_honorary` (+ expiry) flags on `fee_members`.
- **Sponsors are not people.** `org_sponsors` is the sponsoring ORGANISATION
  (name, logo, website, one carried-over contact name/email from the KlubPro
  import). A sponsor's person belongs in the Directory as an ordinary member
  with the "Sponsor Contact" membership type. Don't union the two lists.
- **The membership-type catalogue's CRUD lives in BetterFees** (`/club-admin/fees/
  membership-types`, `MANAGE_FEES` + the fees module), which a volunteer or
  committee manager does not hold — so `GET /club-admin/directory/people`
  returns the catalogue itself alongside the people rather than sending the
  screen to an endpoint that would 403 for half its readers.
- **The Directory can now SET `membership_type_id`** (`MemberUpsert`, resolved
  through `_resolved_type_id` → 422 for another club's id, "" clears it). Without
  this the filter would be dead for every club that doesn't run BetterFees,
  since nothing else writes the column.
- **The `membership_types` join is org-scoped on BOTH sides**
  (`mt.organisation_id = fm.organisation_id`), same rule as the `players` join
  above it — see the cross-club member leak note further down.
- **The search sits on its own line above the filter buttons** (v9.51.0), left
  aligned with them, the same place Committee's own search box sits. It used to
  be squeezed against the right of the title line.
- **Frontend** (`redesign/screens/Directory.jsx`): `typeLabel(p)` falls
  membership type → category → player/former player → "Member", shown on every
  list row and as an accented chip on the detail pane. New filters: Playing /
  Former players (both exclude non-players rather than lumping them in with the
  inactive), a membership-type select with a **"No type set"** option, and the
  Life member / Official / Honorary segments — `list_people` had always computed
  those and they simply had no pill.
- **Verified against a real Postgres** (27 checks): the new join and every
  returned field, a member pointed at another club's type reading as no type,
  read-through players carrying their status, archived behaviour, and the
  router's own guard rejecting a foreign/unknown/non-uuid type id.

<!-- END original CLAUDE.md L8536-8589 -->
<!-- BEGIN original CLAUDE.md L8665-8698 -->
## One look across BetterClubhouse: the Directory is the reference (v9.10.1, Aug 2026)

Reported from a phone: the Directory reads well, and the older full editors
(Committee Administration and friends) clearly did not match it.

- **The difference was never the typeface.** The obvious guess is `font-display`
  vs the body font, but a club that has not chosen its own typography resolves
  both to the same face, and measuring the live pages confirmed every heading
  was already Geist. **Measure the rendered page before theorising about a
  design inconsistency** — the real causes were heading SIZE (24px in the page
  body vs 19px in a sticky header), tab rows that could not wrap, mono used as
  body copy, and mono uppercase buttons.
- **`ModuleLayout` already renders the Directory header** — 19px title, mono
  caption, sticky, on `--pb-surface`. The ten editors simply never passed
  `title`/`caption`, so the bar showed only the module lockup while the page
  drew its own 24px `<h1>` underneath. Passing the two props and deleting the
  in-body heading block is the whole fix. **A new Clubhouse screen should pass
  `title` and `caption` and draw no heading of its own.**
- **`FilterPill` (components/admin/ui.jsx) is byte-for-byte the Directory's own
  chip**, so the editors' hand-rolled mono tab buttons became `FilterPill` and
  matched for free. Prefer it over a local tab button.
- **Tab rows wrap, they do not scroll sideways.** Two screens overflowed at
  390px purely because a `flex` row of tabs could not wrap; the Directory's
  filter chips already wrap onto four lines on a phone, so wrapping is the
  house answer. `SegTabs` wraps too now.
- **The repo rule was already right and simply unenforced**: mono is for labels
  and figures, never buttons, headings or body. Long mono paragraphs moved to
  the body font and ~56 mono uppercase action buttons became body-font sentence
  case across the ten editors.
- **Verified by screenshotting all 17 Clubhouse screens at 390px** and asserting
  on each one's `<h1>` computed font, size and weight plus
  `documentElement.scrollWidth > clientWidth`. That check is worth repeating
  whenever a Clubhouse screen is added.

<!-- END original CLAUDE.md L8665-8698 -->
<!-- BEGIN original CLAUDE.md L8699-8976 -->
## A role is a level between the area and the shift (migration 306, v9.82.0, Sep 2026)

Reported off Setup → Areas & roles: an operational area paired ONE role with
ONE gating qualification ("ROLE THAT COVERS IT"), and the reporter wanted a
Match Day area to involve several — Umpires, Scorers, Team Managers, the roles a
junior fixture needs — stating the hierarchy in their own words: Department →
Operational Area → **Role** → Shift → Volunteer, each area holding many roles and
each role many shifts.

- **THE ROLE WAS A PROPERTY OF THE AREA, AND "EACH ROLE HAS MANY SHIFTS" CANNOT
  BE SAID THAT WAY.** `roster_areas.required_role_id` is one column and a shift
  knew nothing about roles — it only pointed at its area. So role becomes a
  first-class level: an area holds a PALETTE of roles (`roster_area_roles`, each
  role paired with the qualification that gates that one role), and every
  shift/pattern carries one `role_id` drawn from that palette.
- **THE QUALIFICATION IS PER ROLE, WHICH IS THE WHOLE POINT.** A Match Day
  Umpire needs an accreditation while the Scorer beside it needs nothing, so the
  gate lives on the palette ENTRY (`roster_area_roles.required_qualification_type_id`),
  not on the area. `check_assignment` reads the block and the role warning off
  the SHIFT (`shift.required_qualification_type_id`, `shift.role_id`), so a
  person cleared for one role on a fixture is not blocked for another on the same
  one.
- **PAID VS VOLUNTEER MOVED FROM THE AREA TO THE SHIFT'S ROLE, so one area can
  mix both.** `area_pay_kinds` is gone; `confirm_review` and `hours_summary`
  derive `is_paid` per shift by joining `club_roles` → `club_role_types` on
  `s.role_id` (`category == 'paid'`, `PAID_CATEGORY`). Worked-hours paid still
  reads the already-stamped `volunteer_hours.is_paid` (the snapshot rule).
  `role_shortages` buckets open shifts by `s.role_id` directly rather than
  resolving through the area — simpler and more accurate, and a NULL `role_id`
  is the `no_role_required` bucket.
- **THE BACKFILL MAKES AN EXISTING CLUB BYTE-IDENTICAL.** Migration 306's three
  idempotent statements carry every single-role area into a one-entry palette
  and stamp its patterns' and shifts' `role_id` from `required_role_id`, so a
  club that never touches this behaves exactly as before. `roster_areas`'
  `required_role_id`/`required_qualification_type_id` are KEPT but deprecated —
  read only by the backfill; a new area leaves them NULL and the palette is the
  source of truth. `list_areas` still emits `required_role_id`/`_name` = the
  first palette entry, so an un-refreshed client shows something.
- **THE WHOLE ROSTER SUBSYSTEM IS RAW SQL, OUT OF THE ORM/ALEMBIC GRAPH**
  (`services/roster.py` docstring), so `roster_area_roles` and the two `role_id`
  columns are mirrored idempotently in `main.py`'s lifespan, byte-identical to
  306's `STATEMENTS`, right after the migration-222 block. `role_id` on both
  patterns and shifts is `ON DELETE SET NULL` (a shift outlives a deleted role
  as general help); a palette entry with no role is meaningless, so
  `roster_area_roles.role_id` is `NOT NULL ON DELETE CASCADE`.
- **`seed_starter_areas` seeds each starter's role into the palette** and adds a
  multi-role **Match Day** starter (Umpire+accreditation, Scorer, Team Manager) —
  the reporter's own example, and the demonstration that the capability is
  reachable from the Starter Pack. A starter role that does not resolve to a
  `club_roles` row is skipped rather than seeding a dangling palette entry.
- **NUMBERED 306, down_revision 305** (the local branch head; `origin/main` tops
  at 304 — re-check `origin/main` at merge, per the house rule this file records
  repeatedly).
- **Verified against a real Postgres**
  (`backend/verification/verify_roster_area_roles.py`, 45 checks through the
  shipped service: migration/lifespan applied idempotently, the backfill carrying
  a legacy single-role area into a palette with its patterns and shifts
  inheriting the role, `_generate_shifts` copying `role_id`, a multi-role Match
  Day area gating each shift by its OWN role's qualification — the Umpire shift
  blocked without accreditation while the SAME person is NOT blocked for the
  Scorer shift — paid derived from the shift's role in confirm and hours,
  `role_shortages` bucketed by shift role, a role removed from the palette, and
  cross-club scoping) **with a control run**: with the feature reverted, 12 of
  the checks fail on exactly the per-role qualification and role-on-shift
  behaviour.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN, hit in the harness itself.**
  `caught(label, svc.create_area(...))` evaluated the call — with its new `roles`
  keyword — BEFORE wrapping it, so the control died with a `TypeError` instead of
  reporting. `caught` takes a no-arg factory now (`lambda:`), so an absent
  parameter is a reported failure rather than the end of the run.
- **Driven in Chromium**
  (`frontend/verification/verify_roster_area_roles_browser.mjs`, 16 checks: the
  palette editor growing to two role rows with row 2 refusing the role already
  chosen in row 1, the EXACT `roles: [...]` payload on the wire — Umpire carrying
  its accreditation, Scorer a null qualification — the area sub-line listing both
  roles with their quals, the per-pattern role picker scoped to the palette and
  its `role_id` on the wire, an open shift's chip showing its role on the weekly
  grid, and the AddShift picker scoped to the chosen area) **with a control run**:
  12 of the 16 fail against the previous commit, the old pattern and shift POSTs
  carrying no `role_id` at all. Every new element is read through `seen`/`press`/
  `pick`/`opts`, which report absence rather than throwing, so the control fails
  each new check cleanly instead of dying on the first missing locator.
- **NOTICED, NOT BUILT**: nothing migrates a shift's people when its role is
  changed, and there is no per-role headcount target on an area (a shift's
  headcount is still per pattern). Both are follow-ups, not part of making role a
  first-class level.

### The roster grid opens an area into its roles (v9.82.1, Sep 2026)

Reported straight after v9.82.0 landed: Match Day now holds Umpire, Scorer, Turf
Curator and Groundskeeper, but the ROSTER GRID's Areas view still drew Match Day
as one row with every role's shifts mixed into the day cells. A shift is created
and filled for a role, so the grid should read that way.

- **FRONTEND ONLY, because the shift already carries its role.** `_shift_rows`
  has returned `role_id`/`role_name` per shift and `list_areas` the `roles`
  palette since v9.82.0, so the grid had everything it needed — the Areas view
  just wasn't grouping by it. No migration, no service, no router change.
- **THE GRID GROUPS THE SHIFTS THAT EXIST, NOT THE PALETTE.** A palette role with
  no shift this week has nothing to display or assign, so it draws no row — the
  grid shows shifts, and a per-role row is only meaningful where shifts sit.
  `areaRoleGroups(a, areaShifts)` in `Roster.jsx` buckets the area's shifts by
  `role_id` (null → a "General help" group, kept last), ordered by the palette's
  `sort_order` first, then any role present but off-palette. A shift with no role
  is the one bucket that isn't a palette role.
- **ONE ROLE GROUP → THE ROW IS UNCHANGED.** A single-role area (or one with
  shifts for one role this week) renders exactly the row it did before — no
  header, no toggle, its role and qualification on the meta line. This is what
  keeps a single-role club byte-identical, the same posture v9.82.0's backfill
  took. Only two-or-more role groups draw the expanding header.
- **A MULTI-ROLE AREA IS A HEADER THAT FOLDS ITS ROLES AWAY.** The header carries
  the area total (filled/total, "N roles") and a toggle; each role is a sub-row
  beneath it with only that role's shifts in its day cells and its own
  filled/total and gating qualification. Collapsing leaves just the header.
- **`areaDayCol(a, cellShifts, d)` IS THE ONE PLACE A SHIFT CHIP IS DRAWN ON THE
  AREAS VIEW**, shared by the single-role row and every per-role sub-row, so they
  select, drop and warn identically — a volunteer dragged onto a role's shift is
  the same code path whichever row it lands in.
- **COLLAPSE IS A PER-PERSON PREFERENCE**, `usePref('roster_areas_collapsed', {})`
  keyed by area id, so a club with one area folded keeps the rest open and the
  fold survives the browser closing. Default (empty map) is expanded — the
  reported complaint was that the roles were hidden, so showing them is the
  default and folding is the opt-in.
- **Driven in Chromium** (`frontend/verification/verify_roster_role_grid_browser.mjs`,
  16 checks: the multi-role header and its toggle, both role sub-rows shown by
  default, the open Umpire shift landing in the Umpire sub-row and the assigned
  Scorer shift in the Scorer sub-row, a single-role area staying a plain row with
  no toggle, the toggle folding the sub-rows away and back, the fold surviving a
  reload, no page errors and no overflow at 390px) **with a control run**: 12 of
  the 16 fail against the previous commit, the 4 that pass in both being the
  single-role-unchanged, no-errors and no-overflow guards.
- **THE COLLAPSE CHECKS ARE CONTRASTS, NOT BARE ABSENCE.** "collapsing folds away
  the sub-row" and "survives a reload" are gated on the sub-row having genuinely
  been shown first (`wasExpanded`), or a build that never draws a sub-row would
  pass them vacuously — the "a check that can't fail is not a check" trap, caught
  by the control run passing them before they were tightened.

### An open shift on an archived area read "undefined" (v9.82.4, Sep 2026)

Reported off a live People-view roster: open-shift chips showed "undefined ×2" /
"undefined ×8" as their description.

- **THE CHIP NAMED A SHIFT BY LOOKING ITS AREA UP IN THE ACTIVE-AREAS SET, WHICH
  MISSES AN ARCHIVED AREA.** `list_areas` returns `is_active = TRUE` areas only,
  but `_generate_shifts` and `_shift_rows` don't filter active (the row still
  exists — `delete_area` is a soft delete), so a week generated before an area
  was archived keeps that area's shifts. The People-view chip's headline was
  `areaById[shift.area_id].name`, and `areaById` is built from `list_areas` — so
  an archived-area shift resolved to `{}` and rendered its name as `undefined`.
  **React renders a bare `undefined` child as EMPTY; only the `count > 1` path
  (`a.name + ' ×' + count` → string concat) produces the literal "undefined ×N"**
  the screenshot showed — which is why the reproduction fixture needs a PAIR, not
  a single, on the archived area.
- **THE SHIFT CARRIES ITS OWN `area_name` NOW, off an UNFILTERED LEFT JOIN.**
  `_shift_rows` LEFT JOINs `roster_areas` (not `list_areas`' active-only set), so
  an archived area's name still travels on the shift. The frontend already
  REFERENCED `x.area_name` in the section-search (`shiftHit`) — a field that was
  intended but never populated, the tell that this was the gap. `areaLabel(shift)`
  is the one robust namer: `shift.area_name || areaById[...]?.name || role_name ||
  'Shift'`, never `undefined`.
- **AND THE OPEN-SHIFTS ROW GROUPED BY AREA NAME + TIME, so two roles merged.**
  A shift is FOR one role now, but the grouping keyed on the area name and hours
  alone — so an Umpire slot and a Scorer slot at the same time in one Match Day
  area collapsed into one "Match Day ×3" chip whose subtitle showed only the
  representative role (the Scorer vanished). Keyed on `(area_id, role_id, start,
  end)` now, so each role is its own chip and a same-role pair reads "×2".
  Keying on the ids the shift already carries also stops every archived-area
  shift lumping together under the old `undefined === undefined` name key.
- **Verified against a real Postgres** (`verify_roster_area_roles.py` is 51 checks
  now: every shift row carrying an `area_name`, a Match Day and a legacy shift
  naming their areas, and — done last so it doesn't disturb the earlier sections
  — an area archived after generation still naming its shift while `list_areas`
  drops it) **with a control run**: with `area_name` reverted, 4 of the checks
  fail. **Driven in Chromium** (`verify_roster_open_shift_labels_browser.mjs`, 11:
  no chip reads "undefined", the archived area's real name shows, distinct roles
  render as separate chips, and the same-role pair reads "Match Day ×2" not "×3")
  **with a control run**: 5 of the 11 fail against the previous commit, the
  captured text reading the reported "undefined ×2" beside a merged "Match Day
  ×3".
- **A HEADLINE CHECK THAT SUBSTRING-MATCHES THE ROLE CANNOT FAIL.** The first cut
  asserted the archived chip showed "Grounds" while the role was "Groundskeeper"
  — which `includes('Grounds')` passes on regardless, since React renders the
  broken headline as empty rather than the string "undefined" at count 1. Fixed
  by naming the archived area "Turf" (not a substring of its role) and using a
  count-2 pair so the real "undefined ×2" bug reproduces.

### And then a shift on that archived area could not be rostered (v9.82.5, Sep 2026)

Reported one step on from the "undefined" labels: allocating the volunteer
"Abbas, Aamir" (Role: Bar Staff) to a Bar Staff shift returned **"Can't roster
Abbas, Aamir here. Unknown volunteer or area"**.

- **THE ASSIGNMENT NEVER NEEDED THE AREA, AND THE GUARD THAT SAID IT DID IS WHAT
  BROKE.** `assign` resolved the shift's area through `list_areas` (active-only)
  and refused on `if not cand or not area`. But since migration 306 the role and
  the qualification that gates it live on the SHIFT, and `check_assignment` reads
  everything off the shift — the `area` argument was carried only to be ignored.
  An archived area is not in `list_areas`, so the guard refused a fill that
  needed nothing from the area. It is the same orphan the shift outlives that the
  v9.82.4 note documents, hit on the write path this time.
- **THE DEAD `area` PARAMETER IS REMOVED, NOT WORKED AROUND**, from
  `check_assignment` / `_rank` / `assign` / `autofill` and the frontend's
  `checkClient` / `dropVerdict` — a stale guard on a value nothing reads is worse
  than none, and leaving it invites the same trap on the next reader. `assign`
  now refuses only "Unknown volunteer" (a real state), and only when the
  candidate itself does not resolve.
- **THE "BEST FIT FOR THIS SHIFT" PANEL WAS GATED ON THE AREA BEING ACTIVE**
  (`sel && selArea`), so an archived-area shift showed no fill controls at all —
  the drag path was fixed by the backend change but the panel still hid. It is
  gated on the shift alone now, named off the shift's own `area_name`, with the
  edit-the-area link dropped since an archived area is not in the list to edit.
- **Verified against a real Postgres** (`verify_roster_area_roles.py` is 54
  checks now: with Match Day archived, an accredited umpire is rostered onto one
  of its still-live Umpire shifts rather than refused, and the refusal is NOT the
  stale "Unknown volunteer or area") **with a control run**: with the fix
  reverted, 2 fail on exactly that. The `check_assignment` call in the harness
  tolerates both the old and new arity so the control reaches the assign checks
  (which use the unchanged `assign` signature) rather than crashing on the direct
  call — a control run that crashes is not a control run.
- **Driven in Chromium** (`verify_roster_open_shift_labels_browser.mjs` is 14:
  selecting the archived-area open shift surfaces the Best fit panel, named off
  its own `area_name`) **with a control run**: 2 fail against the previous commit,
  the panel `null` where the area was insisted upon. The chip that carries the
  `onClick` is the draggable root; the day-column div wrapping it starts with the
  same text but has no handler, so the check targets `div[draggable]`.

### A duplicate role named a role the list will not show (v9.82.3, Sep 2026)

Reported off Areas & roles → Roles: adding "Bar Manager" was refused as already
existing, with no Bar Manager anywhere in the list.

- **THE ROLE WAS THERE, HIDDEN, AND THE SILENCE WAS THE BUG** — the same call this
  file already records for a disabled Rediscover button and a figure that is
  correctly zero. The committee starter pack (`STARTER_COMMITTEE_ROLES`) seeds
  "Bar Manager" as a COMMITTEE role (`is_committee=True`), and the Roles list
  filters those out (`!x.is_committee && x.role_type_category !== 'committee'`)
  because they are managed as positions on the Committee screen. So a real,
  active role existed and the tab that raised the error was the one place it
  could never appear.
- **THE UNIQUENESS CHECK SPANS EVERY ROLE, WHICH IS RIGHT — the reactivation-by-
  `lower(title)` path and the many title lookups all assume one role per name.**
  So the fix is not to scope the check to what the list shows (that would allow
  two same-titled roles and break those assumptions); it is to make the refusal
  SAY where the clashing role lives. `_role_clash_message(existing, existing_type,
  *, caller_is_committee)` is the ONE definition, joining `club_role_types`: when
  the existing active role is committee-hidden (its `is_committee` flag OR a
  committee-category type — the same combined test the list applies) and the
  caller's own role is not, it points at the Committee screen and asks for a
  different name.
- **THE RENAME PATH SHARES THE SAME HELPER, so the two cannot disagree.**
  `update_role`'s rename-collision check (added on `main` the same week, whose own
  comment already noted the committee-hidden case but kept the bare message) now
  joins the type and calls `_role_clash_message` too — so renaming a visible role
  ONTO a hidden committee role reads the same explanation, from the other
  direction. `caller_is_committee` there is the role's effective `is_committee`
  after the update (`fields.get("is_committee", r.is_committee)`).
- **THE ADVICE IS ALWAYS-TRUE, NOT "RECLASSIFY IT".** The list hides a role when
  `is_committee` OR the type category is committee, and the seeded committee role
  has the FLAG set — so clearing only the type category would not surface it. A
  distinct name always works, so that is what the message says; suggesting a
  reclassification that would not actually list it is worse than saying nothing.
- **A GENUINE VISIBLE DUPLICATE KEEPS THE PLAIN MESSAGE**, and a committee CALLER
  clashing with a committee role keeps it too — it is not hidden from that
  caller's own list. An archived clash still reactivates rather than erroring,
  unchanged.
- **Verified against a real Postgres**
  (`backend/verification/verify_role_create_committee_clash.py`, 10 checks through
  the shipped `create_role` AND `update_role` over the ClubRole/ClubRoleType
  tables: the reported case naming the Committee screen, the same when hidden by
  the type category alone, the clash case-folded, a visible duplicate keeping the
  bare message and never mentioning the Committee screen, an archived clash
  reactivated, a committee create keeping the bare message, and the rename path
  naming the Committee screen while a rename onto a visible duplicate keeps the
  bare message) **with a control run**: with the committee-aware branch of
  `_role_clash_message` neutered, 5 of the 10 fail — every create and rename check
  that should name the Committee screen reports the customer's own bare
  `A role called "Bar Manager" already exists`.

<!-- END original CLAUDE.md L8699-8976 -->
<!-- BEGIN original CLAUDE.md L8977-9021 -->
## Confirming the roster, a frozen first column, and the drags that never worked (migration 222, v9.10.0, Aug 2026)

- **"Confirm roster" is the name, in the code as well as the UI.** The action was
  briefly called "closing off a week"; it was renamed everywhere the same day
  (service functions, routes, the `roster_weeks.status` value, the migration
  filename) rather than leaving the two languages to drift.
- **`roster_shifts.worked_hours` is the roster's record of what was worked;
  `volunteer_hours` is the club's ledger.** The flow is one-way — confirming
  POSTS to the ledger, nothing reads back. NULL `worked_hours` means "not
  checked yet" and a checked **0** means "rostered but did not turn up"; both
  have to be expressible, which is why it is nullable rather than defaulted.
- **Confirming RECONCILES, it never appends.** `uq_volunteer_hours_shift` (a
  partial unique on `roster_shift_id`) makes the insert an upsert, and a shift
  that has since been unassigned or checked down to zero has its posted row
  DELETED. Without that, correcting a mistake would leave the original behind
  and the ledger could only ever grow. `is_paid` is stamped from the role type
  at the moment of confirming and never revisited (migration 221's snapshot rule).
- **Unconfirming deliberately leaves the posted hours alone.** They were worked;
  deleting them because someone wants to fix a typo would take the club's ledger
  down with the correction. Confirming again reconciles.
- **The frozen first column is `position: sticky` on the GRID ITEM.** A grid
  item's containing block is its grid area, which suggests this cannot work —
  it does, verified in an isolated page and then in the app (9 cells holding at
  x=232 through a 694px scroll). **The trap is the background**: the rail's
  opaque `background` must not be overridden by a row tint, or the columns
  scrolling underneath show straight through it. The open-shifts row layers its
  amber over the top via `backgroundImage` instead.
- **`usePref(key, fallback)`** in `redesign/ui.jsx` is the per-user, per-browser
  screen preference (keyed on user id, like the screen introductions). Reads in
  the state initialiser, not an effect, or the panel renders open for one frame
  before snapping shut. Used for the minimised rail and the volunteer pool.
- **The People view's drags were half-wired.** `cellDrop` only ever read
  `st.dragId` (a shift) and `slotDrop` (a person) was attached in the AREAS view
  only, so dragging a volunteer from the pool onto an open shift in People did
  nothing and said nothing. Open chips are drop targets now.
- **A shift can only be dropped in its own day column.** It carries its own day,
  so accepting it anywhere else silently left it where it was — which reads as
  the roster ignoring you. Other days don't `preventDefault`, so the cursor says
  no before the mouse is released; a person who would be blocked still accepts
  the drop, so the refusal comes back from the server as a sentence.
- **Testing HTML5 drag-and-drop**: Playwright's real mouse cannot steer
  Chromium's native drag loop — it hangs. Dispatch `DragEvent`s instead, and put
  the `dragstart` and the `drop` in SEPARATE `evaluate` calls, or React has not
  re-rendered with the drag in flight and every drop reads as refused.

<!-- END original CLAUDE.md L8977-9021 -->
<!-- BEGIN original CLAUDE.md L9218-9282 -->
## Roster shift CRUD, paid vs volunteer hours, diary year, draft minutes (migration 221, v9.8.0, Aug 2026)

Six items from the second live feedback batch, plus the paid/volunteer split that
underpins one of them.

- **Paid work is derived from the role type, never stored as a second flag.**
  `club_role_types.category` has accepted `'paid'` since the roles catalogue was
  built but nothing ever read it, so a club could not tell the bar manager it
  employs from the parent running the canteen for nothing.
  `roster.area_pay_kinds` resolves an area → its `required_role_id` → that
  role's type category, and `PAID_CATEGORY = "paid"` is the only test. **Don't
  add a per-shift or per-person paid flag** — it would immediately disagree with
  the role type. `volunteer_hours.is_paid` (migration 221) is the ONE exception
  and is deliberately a snapshot: it records what the derivation decided AT THE
  TIME the hours were logged, so retyping a role later cannot silently rewrite
  last season's wage bill.
- **`roster.hours_summary(start, end)`** returns four numbers per person plus
  totals: `rostered_{volunteer,paid}` (the length of every shift they are
  assigned to in the window, from `roster_shifts`) and `worked_{volunteer,paid}`
  (what was logged afterwards, from `volunteer_hours`). **Rostered and worked
  are deliberately separate** — the gap between them is the thing a club wants
  to see, and a club's wage bill and its volunteer effort must never be summed
  (one goes to the treasurer, the other to the grant application). Surfaced as a
  third **Hours** tab beside People/Areas on the Roster (`HoursView` in
  `screens/Roster.jsx`, week/month/season spans; season is Jul-Jun).
  `volunteer_hours.roster_shift_id` exists for hours logged against a specific
  shift and **has no FK on purpose** — `roster_shifts` is one of the raw-SQL
  lifespan tables, so an ORM-side constraint would make `create_all()`
  order-dependent on a fresh database.
- **Shift CRUD** (`roster.create_shift/update_shift/delete_shift`, routed and
  org-scoped). Weekly patterns still materialise the week; this is for the shift
  a pattern should not carry (a final, a night game, an extra hand behind the
  bar) — editing the pattern would change every other week too. The Roster
  sidebar carries `+ Add a shift` and, with a shift selected, `Delete this shift`.
- **`PersonPanel`** on the Roster: click anyone in the volunteer pool to read and
  edit their availability (`roster.member_detail` / `set_member_availability`)
  and read their qualifications, rather than being sent to Directory → Volunteers.
  **Availability is stored as Monday=0 indexes but read tolerantly** — the
  volunteers router types `available_days: List[str]`, so `roster.day_index()`
  accepts `'Monday'`/`'mon'`/`'0'`/`0` and `set_member_availability` normalises
  writes back to indexes. That mismatch was the original Roster HTTP 500.
- **`organisations.diary_start_month`** (1-12, default 7, so no club changes by
  upgrading) drives the Club Diary's season plan; `ClubDiary.jsx`'s
  `monthDefs(startIdx, startYear)` uses real calendar day counts rather than the
  old hardcoded table. Edited from Clubhouse → Settings (`DiaryYearPanel`).
- **Draft minutes** (`POST /committee/meetings/{id}/draft-minutes`) composes the
  attendance, agenda, motions/votes and actions the meeting already holds into a
  prompt (`claude-haiku-4-5`, `strip_em_dashes`, rate-limited to 10/hour/club).
  **It returns the text and never saves it** — minutes are the club's legal
  record, so a machine writes the first pass and the secretary decides whether
  any of it is true. No API key configured gives a clean 503, not a 500.
- **Action board + timeline share one filter** (search, category, objective,
  assignee, overdue) in `AdminCommittee.jsx` — one `shown` list feeds both, so
  they can't disagree about what is in scope.
- **Fixed an infinite request loop** in `AdminCommittee`: the members effect
  depended on `toast`, and its own error handler raised a toast, which changed
  the context value, which re-ran the effect. A club without the fees module hit
  `/fees/all-members` 60+ times per page load. **Watch for this shape anywhere**
  a `catch` calls `toast.*` in an effect that lists `toast` as a dependency.
- **Local harness gotcha**: `player_achievements`, `org_award_definitions` and
  `audit_logs` are lifespan-created raw-SQL tables, so a stubbed-lifespan boot
  has to create them by hand. A missing `audit_logs` is especially misleading —
  `audit_log` catches its own failure and logs a warning, but the aborted
  transaction then poisons the caller's commit, so an unrelated PATCH 500s.

<!-- END original CLAUDE.md L9218-9282 -->
<!-- BEGIN original CLAUDE.md L9341-9486 -->
## BetterAdmin → BetterClubhouse: four sub-modules merged into one (v9.3.0, Aug 2026)

BetterFees, BetterComms, BetterMerch and BetterClubManager shared a codebase but
not a design language, and duplicated three person lists, two money ledgers, two
Square connections and three reports surfaces. They are now **one module,
BetterClubhouse**, on the old BetterAdmin amber. Handoff:
**`docs/design_handoff_betterclubhouse/`** (`README.md` is the spec,
`BetterClubhouse.dc.html` the prototype, `BetterAdmin Review.dc.html` the why,
`PROJECT_RULES.md` the scope rule below).

- **The `admin` key is unchanged.** Only display names moved —
  `MODULE_GROUPS.admin.name`, `moduleBrand('admin').name` and the backend
  `BILLABLE_MODULE_NAMES[admin]` read "BetterClubhouse". Entitlement, billing,
  `org_module_subscriptions` and every stored row still key on `admin` /
  `fees|comms|merch|crm`. **Two things deliberately still say BetterAdmin**: the
  public marketing site (incl. the `/modules/betteradmin` URL, its SEO/OG
  metadata and the dated blog articles) and `billing_pricing.py` / `pricing.js`,
  which are a hand-synced pair feeding Stripe Product creation — an existing
  Stripe Product keeps its old name until it's renamed in the dashboard. Both
  are commercial calls, not design ones.
- **`components/admin/ModuleLayout.jsx` is the shell for every module surface**
  and now carries the whole design: 232px sidebar (not 240), club identity +
  season line, module lockup (the `← Back to admin` link is gone), grouped nav
  with count badges, and — the load-bearing decision — the **module switcher,
  account and bookmarks in the sidebar FOOTER**, which frees the sticky screen
  header for title + mono caption + `?` + filters + stat readouts + one primary
  action. New optional props: `caption`, `onHelp`, `filters`, `stats`, `bare`
  (screen owns its padding), `hideHeader` (screen draws its own — the
  transitional escape hatch the promoted ClubManager screens use). **One
  breakpoint for the module: `lg` (1024px)**, sidebar becomes a drawer below it.
- **ONE SEARCH BOX, ONE PLACE (v9.51.2).** Below the heading, left aligned, with
  Bookmarks and the primary action beside it. `ModuleLayout` grew two opt-in
  props for it: **`twoRow`** moves `filters`, the bookmark and `actions` onto a
  full-width second line, and **`tabs`** puts a section's own button row CENTRED
  on the title line (the title block and the right-hand group each take
  `flex-1 basis-0`, so the buttons land in the middle rather than wherever the
  title happens to end). Both default off, so a screen that has not asked is
  byte-for-byte what it was. Carried by Accounts, Payments, Stock, Equipment,
  Emails, Lists, Segments and Templates; Roster and the Directory do the same
  thing by hand inside `ScreenHeader`, since they do not use `ModuleLayout`.
- **THE SECOND ROW'S FILTERS WRAP INSIDE THEIR OWN BOX.** `flex-1 min-w-0` on
  the filters and `shrink-0` on the action cluster, so the search and the
  buttons always share the top of that row — letting the whole row wrap put the
  buttons on a line of their own the moment a screen carried a few filters.
- **A WIDTH UTILITY DOES NOT BEAT `w-full` RELIABLY.** `INPUT_CLS` carries
  `w-full`, and which of two width classes wins is the order Tailwind EMITS
  them, not the order in the class string. `SearchInput`'s `wide` and the Stock
  category select therefore set their width INLINE; with a class they
  intermittently took the whole line and pushed everything beside them onto the
  next row. Measured, not guessed — the box read 380px while its sibling select
  read 522px in the same row.
- **`SegButtons`** is the house segmented control in the admin kit, the same
  markup Committee's `SegTabs` draws, so a Merch or Comms screen asking for "the
  same buttons as Committee" gets them rather than a lookalike.
- **`RecordListPane` takes a `query`** and filters on what a row actually says
  (its name and its second line), so one box serves every screen built on
  `crudShell` instead of four different filters. `SegmentListPane` forwards it.
- **`components/admin/ui.jsx` is the one admin UI language** — Button,
  TextInput/Select/Field/SearchInput, FilterPill, StatCard, StatReadout,
  Caption/FieldLabel/StatLabel, AttentionRow, TableWrap/TableHead/TableRow/
  TableFootRow/Cell, Badge, Chip, Initials, ListRow, Drawer, Toast, Note,
  HelpDot. **Use these instead of writing a local copy** (that's what produced
  the four divergent sets). Two rules: mono is for labels and figures only,
  never buttons/headings/body; and text on an accent fill is `ON_ACCENT`
  (`#0a0d14`), one answer everywhere. Accent tints come from `TINT` (color-mix,
  NOT `rgba(var(--pb-accent-rgb), α)` — that var is space-separated and the
  comma-form rgba can't parse it).
- **`--pb-accent-ink`** (theme.css) is the accent as *text*, darkened on light
  so amber stays legible on white. It's derived from whatever `--pb-accent`
  resolves to **on the element it's computed on**, so any surface that
  re-points `--pb-accent` must also carry **`.pb-ink`** (ModuleLayout's root
  does). `--pb-positive-ink` / `--pb-red-ink` are the same idea, static.
  `.pb-card` radius went 6px → 10px, which moves most of the app onto the new
  scale in one change.
- **`BetterClubhouseLayout`** owns the merged nav: six capability-gated groups
  (People / Money / Stock / Comms / Club / Setup) with `Today` above the first
  heading. Items carry `cap` (a capability, or an array meaning any-of),
  `module` (one of the umbrella's paid keys — the whole group disappears for a
  club that doesn't hold it) and `super` (the promoted ClubManager screens —
  real data, and open to the club's own admins since v9.6.1 — see the access
  note below). **The four old layouts
  are thin wrappers over it now**, which is how every existing screen inherited
  the shell without being rewritten. `BetterMerchLayout` still owns the
  storefront flag and passes `storefront` down.
- **Counts are computed once**: `pages/admin/clubhouse/data.js`'s
  `useClubhouseData` (module-level cache, 60s TTL) + `deriveCounts` feed the
  sidebar badge, the Today row, the Accounts KPI and the Reports figures from
  the same fetch. **Don't denormalise these** — if issuing a shirt changes a
  balance, all of them have to move together.
- **New screens** (`pages/admin/clubhouse/`): `ClubhouseToday` (the front door —
  aggregates money/stock/comms, omits a row whose count is zero),
  `ClubhouseAudiences` (replaces Contacts + Lists + Segments; both
  `/admin/comms/segments` and `/admin/comms/lists` now redirect here),
  `ClubhouseIntegrations` (Square + Xero + email sending, each linking to the
  screen that owns the setup), `ClubhouseReports` (source selector),
  `ClubhouseSettings` (the screen-introduction flag).
- **Screen introductions** (`clubhouse/intro.jsx`): `'always' | 'once' | 'never'`,
  **per person** (localStorage per user id), default `once`. Today never gets
  one; a deep link (`navigate(to, { state: { skipIntro: true } })` — every Today
  action uses it) always skips AND marks seen; the `?` reopens on demand in every
  mode. `useScreenIntro` decides **once at mount** in a state initialiser —
  deriving it live flashes the page for one frame, because marking the screen
  seen re-renders it away.
- **The indigo is retired.** Every `#6366F1` / `rgba(99,102,241,α)` in
  `pages/admin/clubmanager/` became `var(--pb-accent)` / `color-mix`, and
  `MODULE_BRAND.clubmanager` is gone (aliased to `admin`). `ClubManagerApp`
  dropped its own 232px sidebar and renders inside `BetterClubhouseLayout`
  (`bare hideHeader`); its screen comes from the route via `initialScreen`,
  synced by an effect because React can reuse the component across two routes.
- **⚠ BetterComms scope rule — hard, not a preference.** Club scope reads the
  club's own people; Super Admin scope is BetterCricket's sales telemetry
  against the Clubs Directory. **Never expose the Super Admin fields, context
  bar or copy in a club build** — not behind a dropdown, not greyed out, not
  listed and disabled. Enforced structurally: `segmentFields.jsx` exports
  `CLUB_FIELD_DEFS` (imported ONLY by `clubhouse/ClubhouseSegments.jsx`) and
  `DIRECTORY_FIELD_DEFS` (imported ONLY by `clubhouse/InternalSegments.jsx`),
  with no runtime context switch to get it wrong; `CommsContextBar` no longer
  renders in the club layout. Apply the same rule to any future module that
  gains a platform-side mode.
- **Both segment builders are Clubhouse screens on one URL** (`/admin/comms/
  segments`), and `clubhouse/SegmentsRoute.jsx` is the single place the two are
  chosen between — on `is_marketing_org`, once, lazily, so a club session never
  fetches the directory chunk. The internal one used to be a separate page
  outside the module (`SuperDirectoryAudiences`, on the plain `AdminLayout`
  chrome), so picking Segments in internal mode threw you out of BetterClubhouse
  mid-task; that page is gone and its URL redirects. **No backend change was
  needed** — `/segments/*` already resolves against whichever org you are acting
  as (`get_current_club`), and `/segments/options` already returns
  `context: "directory"` for the outreach org.
- **`clubhouse/segmentEngine.jsx` is the shared builder**: `useSegments` (load,
  live sizes, draft, resolve-as-you-type, save/duplicate/delete, "Email these N
  now") plus `RuleBuilder` / `SegmentListPane` / `SegmentTitleRow` / `CountBar`.
  It imports NEITHER field set — `defs` is a required argument, and each screen
  passes the one constant it imports. **`defs` is required because `newRule`
  reads the first field's first operator**, so an empty vocabulary is a
  TypeError, which is what a saved segment carrying zero rules would hit.
  Adding an `isInternal` flag in here is the wrong move; a third mount is a
  third screen.
- **Not done, and it's the real work**: step 4 of the handoff's sequencing —
  joining the data. The Directory is still not the one person list (Fees
  members, Comms contacts and the ClubManager directory remain three), and a
  member still has a fee balance and a merch balance rather than one account.
  Accounts, Directory and Inventory therefore keep their existing data layers;
  only their shell, language and naming changed. The BetterClubhouse **logo mark
  also does not exist yet** — the lockup currently reuses `betteradmin.svg`.

<!-- END original CLAUDE.md L9341-9486 -->
<!-- BEGIN original CLAUDE.md L9647-9671 -->
## BetterClubhouse is open to club admins (v9.6.1, Aug 2026)

Most of the module was invisible to the people paying for it. Directory,
Roster, Committee, Diary, Events, Facilities and the whole Setup catalogue
carried `requireRole="super_admin"` in `App.jsx` **and** a `super: true` flag in
`BetterClubhouseLayout`'s nav, so a club admin's sidebar showed only Today,
Audiences, Integrations, Reports and Settings. That gate came from
BetterClubManager being unlaunched and long outlived its reason.

- **Both halves are gone.** The routes are plain `<ProtectedRoute>`, and each
  nav item now carries the **capability its own router already enforces**
  (Roster → `MANAGE_VOLUNTEERS`, Committee/Events → `MANAGE_COMMITTEE`,
  Facilities → `MANAGE_ASSETS`, Diary → `MANAGE_CLUB_DIARY`, Directory and
  Areas & roles → the same any-of sets their routers use).
- **Safe because the server never relied on the route gate.** Every router
  behind these screens has `require_cap` / `require_any_cap` (verified across
  all eleven before removing anything). `club_admin` and `super_admin` imply
  every capability; a `club_member` gets their explicit allowlist, so the
  sidebar and the API now agree instead of the UI being the only check.
- **`/admin/member-portal` stays super-admin-only** — a genuinely unlaunched
  feature behind its own flag, not part of the merged module's nav.
- **When adding a Clubhouse screen**, give the nav item the same capability its
  router enforces. Do not reach for a role gate: role is not how this app
  expresses permission anywhere else in the module.

<!-- END original CLAUDE.md L9647-9671 -->
<!-- BEGIN original CLAUDE.md L12882-12890 -->
## BetterFees — Match-Fee Auto-Allocation (v7.32.0, Jun 2026)

A recorded match-fee payment settles a member's games automatically, **oldest game first**. Per-game Paid / Part-paid / Unpaid is **derived on read, not stored** — there is no per-row paid flag any more.

- **Single source of truth**: the sum of a member-season's `match_day` `fee_payments`. `allocate_match_days(charges, match_paid)` in `services/fees.py` walks the games oldest-first (`played_at` nullslast, then `id`), paying each in full while money lasts; the boundary game is `partial`, the rest `unpaid`, and a $0 game (rate $0 / no tier) is `na`. Money left once every game is covered = **credit** ("in the Green").
- `routers/fees.py::get_member` computes this on read and returns per-row `status` + `amount_covered` + `charge`. `_financials` now surfaces `membership_credit` / `match_fee_credit` / `credit` / `in_credit` (overpayment is **no longer clamped to 0**). Buckets are **kept separate** — match-fee credit never offsets membership owing. No tier ⇒ no credit claimed.
- Because status is derived, adding/removing a payment or editing `days_played` re-allocates automatically — **no migration, no stored flag to keep in sync**.
- **Legacy, still live**: the `paid_payment_id` column and the `mark-paid` / `unmark` / `payments/bulk` endpoints still exist and still create `match_day` payments (which feed allocation), but no longer drive the per-row display. The old per-row MARK PAID / UNMARK buttons were removed from the member page in favour of a single "Record match-fee payment" box (`RecordMatchFeeForm`). The bulk-payment page still works (it reads the derived `is_paid` and creates payments).

<!-- END original CLAUDE.md L12882-12890 -->
<!-- BEGIN original CLAUDE.md L12891-12984 -->
## BetterMerch — club stock register (v8.18, Jun 2026)

Third module under the **BetterAdmin** umbrella (`MODULE_GROUPS.admin` already
anticipated it; no separate price, the BetterAdmin toggle now covers
`fees`+`comms`+`merch`). Tracks club stock across three category templates on one
engine: **apparel** (sized/coloured variants), **equipment** (quantity OR
individual assets), **food_drink** (canteen/bar, with expiry). Gated by
`require_module("merch")` + the `MANAGE_MERCH` cap. Surface at `/admin/merch`
(`BetterMerchLayout`, BetterAdmin amber via `moduleBrand('merch')`); pages
Overview / Stock / Equipment / Activity / Reports / Square.

- **Migration 083** (mirrored idempotently in `main.py` lifespan): `merch_products`
  (the catalogue line), `merch_variants` (**stock lives here** as a running
  `quantity`; one 'Standard' variant for un-varied products so apparel and canteen
  read through the same code), `merch_movements` (signed in/out audit log:
  received/sold/issued/used/adjustment/stocktake/write_off), `merch_assets`
  (individual high-value equipment: condition + service/replace dates).
- **`services/merch.py`**: `record_movement` (bumps the variant balance + writes the
  audit row, no commit), `merch_alerts` (low-stock / expiring / service-due,
  computed on read, no table), `stock_summary`. `routers/merch.py`
  (`/club-admin/merch`) is products+variants, movements, assets, a player merch
  view, alerts, reports + CSV.
- **Player link** (admin-only): a sold/issued movement carries `player_id` + a
  `paid` flag; outstanding merch money = sum of unpaid movement amounts. Surfaced on
  the admin player profile modal via the `footer` prop added to
  `PlayerProfilePanel.Profile` (`PlayerMerchPanel`), gated on
  `hasModule('merch') && hasCapability(MANAGE_MERCH)`. Never on the public profile.
- **Alerts feed the notification bell**: `notifications.py` count+summary add merch
  alerts when `org_has_module(club,'merch')`. Like the pending-request counts, this
  is current state, not "since last seen".
- **Per-variant pricing + tracking mode (migration 085)**: each variant carries its
  own `unit_cost`/`unit_price` (override of the product default via `_eff_cost`/
  `_eff_price`), so one product holds several priced kinds (e.g. a 4-piece match ball
  and a 2-piece trainer). `merch_products.for_resale` splits stock into bought-to-sell
  (cost + price, sold/issued to members) vs **club-use** consumable (a straight cost,
  no sell price, no owing — e.g. balls); the New Product form defaults equipment to
  club-use. Club-use products drop sold/issued from the movement picker. Report margin
  counts only priced items (a `CASE` in `stock_summary`) so club-use cost doesn't drag
  it down. Money displays two decimals.
- **Category tree (migration 086)**: `merch_categories` is a self-referencing tree
  (≤3 levels) per club, partitioned by the fixed top type (`top_category`); products
  get an optional `category_id`. Created **inline** as items are added (POST
  `/categories` dedupes a same-named sibling). Endpoints `GET/POST/PATCH/DELETE
  /merch/categories` (delete reparents children, nulls products via FK SET NULL). The
  Stock list filters by node+descendants (`_descendant_ids`); reports add `by_item`
  and a rolled-up `by_category_node` (each node carries its whole subtree's totals).
  Frontend `CategoryPicker` is one dropdown (paths like "Balls › Match") + an inline
  "+ New category" with an optional parent. A `CategoryManagerModal` (the "Categories"
  button on Stock) renames/deletes nodes; `POST /categories/seed-defaults`
  (`MERCH_DEFAULT_CATEGORIES`, "Add starter set") seeds a generic one-level set
  (Match attire / Balls / Canteen…), idempotent. The three fixed types stay as the
  template drivers (sizes / expiry / club-use default), separate from the tree.
  Products and individual variants are both editable after creation (product Edit
  modal via the card gear; per-line `VariantEditModal` via the line gear — label/
  size/colour, cost/price, threshold, expiry; quantity stays movement-driven).

### Square POS integration (migration 084, v8.18.1)

One-way mirror, **Square → BetterMerch** (Square's till owns the canteen count).
OAuth code-flow, per club.

- **Migration 084**: `merch_square_connections` (one per club: tokens,
  `location_id`, `sync_enabled`/`sync_sales`, `sales_cursor`, last-sync status),
  plus mapping columns `merch_products.source/.square_object_id`,
  `merch_variants.square_object_id`, `merch_movements.source/.external_ref` (+ a
  partial unique index on `(org, external_ref)` to dedupe imported rows).
- **`services/square_client.py`** (httpx) — OAuth obtain/refresh/revoke, locations,
  `ListCatalog` (ITEMs carry their ITEM_VARIATIONs nested), `BatchRetrieveInventoryCounts`,
  `SearchOrders` (COMPLETED). Host from `settings.square_environment`
  (sandbox vs production). `services/square_sync.py` — catalog upsert → sales import →
  inventory reconcile, **all in ONE transaction** (helpers `flush`, sync commits
  once) so ORM objects don't expire mid-sync (async `MissingGreenlet` trap);
  `ensure_fresh_token` refreshes the 30-day access token within a week of expiry
  (`session.refresh(conn)` after, since that commit expires conn).
- **Double-count design**: inventory count is the source of truth for `quantity`.
  Sales are imported as `sold` movements (real negative delta + revenue), THEN we
  reconcile each variant to Square's current count via a `stocktake` movement. The
  stocktake is a set-to-absolute, not a second decrement, so sales never double down
  the stock; receipts/waste show up as the reconcile delta. Re-runs dedupe sales on
  `external_ref` (`square:{order_id}:{line_uid}`).
- **OAuth**: gated `GET /square/connect-url` mints a signed JWT `state`
  (`sign_square_state`, typ `square_oauth`, 20 min) and returns the authorize URL;
  the **public** `routers/public_square.py` `GET /public/square/callback`
  (unauthenticated, protected by the signed state) exchanges the code, stores the
  connection, auto-picks the location if there's one, then 302s back to
  `/admin/merch/square`. Scheduler runs `sync_all_square` daily at 04:00.
- **Deploy** (server `.env`): set `SQUARE_APP_ID` + `SQUARE_APP_SECRET` (never
  commit), `SQUARE_ENVIRONMENT=production` (or `sandbox`), optional
  `SQUARE_API_VERSION`. In the Square Developer dashboard register the app's OAuth
  **redirect URL = `https://betterat.cricket/api/public/square/callback`** (matches
  `settings.square_oauth_redirect`; nginx strips `/api`). The box must reach
  `connect.squareup.com`. Tokens are stored per club as plain columns (same
  precedent as `playcricket_api_token`); encryption-at-rest is a hardening follow-up.

<!-- END original CLAUDE.md L12891-12984 -->

## v9.106.23: Fees enrols players who only exist in the season totals

Report: new players (example `Cowcher, Baxter`, one match in CA's totals, `match_coverage.without_scorecard = 1`, no `games` row) were missing from Admin > Fees. Cause: `recompute_fee_match_days` enrolled from `game_appearances` (plus football lines) only, and returned early when a season had no scored games. A player first seen through the aggregate sync has a `players` row and a `player_season_stats` / `player_season_grade_stats` row but no appearance until a scorecard syncs, and a match CA counts can stay without one for good, so Rebuild could not add them either.
Fix: `_aggregate_player_ids` adds club players (`players.organisation_id`) with matches > 0 this season. Per-grade rows decide when present (an Exclude grade stays out); the season total decides only for a player with no per-grade row. They get a `fee_members` and `fee_member_seasons` row and no match days. The early exit for a season with no scored games is gone (stale auto rows are still cleaned up at the end).
Proof: `backend/verification/verify_fees_aggregate_players.py` on a real Postgres; the control against the previous `services/fees.py` fails exactly the three "enrolled" checks.
Not changed: recompute still only runs after the scheduled sync, so a manual sync or an import is not followed by one until someone presses Rebuild match days.
