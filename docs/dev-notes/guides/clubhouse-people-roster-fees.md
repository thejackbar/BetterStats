# Guide: BetterAdmin (Clubhouse) shell, Directory, roster, areas and roles, fees, merch and assets

**Module naming (read first).** The merged back office was called BetterClubhouse from v9.3.0, then renamed back to **BetterAdmin** in v9.40.0 (display only). Entitlement key is `admin` (bundle of `fees`, `comms`, `merch`, `crm`) and never changed. Code names still say Clubhouse (`BetterClubhouseLayout.jsx`, `/admin/clubhouse/*`, `pages/admin/clubhouse/`): do not rename them. `auth/modules.py` `BILLABLE_MODULE_NAMES` and `module_display_name()` are the one backend place that names it.

**Read this before** (triggers):
- Editing `components/admin/ModuleLayout.jsx`, `BetterClubhouseLayout.jsx`, `components/admin/ui.jsx` (admin kit) or `pages/admin/clubmanager/redesign/ui.jsx` (redesign kit: `SegGroup`, `HeaderSearch`, `usePref`).
- Any Clubhouse screen: Directory, Roster, Accounts, Payments, Stock, Facilities, Events, Club Diary, Today, Audiences.
- `services/roster.py`, `roster_area_roles`, `volunteer_hours`, Areas & roles, `services/roles_activities.py`.
- Fees: `services/fees.py`, `fee_member_seasons`, rollover, Accounts save panels, membership tier.
- `services/directory.py`, Families, `services/merch.py`, `services/assets.py`, `club_assets`, Square sync.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/clubhouse-people-roster-fees.md`. Grep hints: `house control`, `ONE asset register`, `newest season`, `inside a <label>`, `PlayHQ registration`, `absent key is not a clear`, `rollover: undo`, `Families is a BetterStats`, `three type axes`, `Directory is the reference`, `role is a level`, `Confirming the roster`, `Roster shift CRUD`, `four sub-modules`, `open to club admins`, `Match-Fee`, `stock register`, `Square POS`.

**Related guides**: comms/segments (scope rule); committee (minutes); BetterSelect (`usePref` twin); billing/Stripe; verification conventions.

## Standing rules

**Shell and UI kit**
1. `ModuleLayout` is the shell for every module screen. A new screen passes `title` and `caption` and draws no `<h1>` of its own (header is 19px, sticky). Switcher, account and bookmarks live in the sidebar footer. One breakpoint: `lg` (1024px).
2. Use `components/admin/ui.jsx` (Button, Field, SearchInput, FilterPill, StatCard, Badge, Drawer, Toast...) not local copies. Mono is for labels and figures only, never buttons, headings or body. Text on accent fill is `ON_ACCENT` (`#0a0d14`). Tints use `TINT` (color-mix), never `rgba(var(--pb-accent-rgb), a)`. A surface that re-points `--pb-accent` must carry `.pb-ink`.
3. Tab and filter rows wrap, never scroll. Segmented chrome is `SegGroup` plus `SegItem`, exported separately in BOTH kits; `SegButtons`/`SegTabs` are built from them. Use them when a row is not one-of-N (independent filters, menus, a real `<select>`); `MenuButton` takes `seg`; `SegItem` takes `as` for navigating items.
4. Box colour is `border-pb-hairline`. `border pb-hairline` is not a class (a Tailwind colour), so the colour falls to preflight `#e5e7eb`. `SEG_GROUP_CLS` is the one definition; the typo appears about 917 times, deliberately not swept.
5. Header layout: the section button row is centred on the title line (`ModuleLayout` `tabs` prop, or `HEAD_SIDE`/`HEAD_CENTRE`/`HEAD_SIDE_END` in the redesign kit; sides are `flex: 1 1 0`). Keep the right-hand box even when empty. Centring wrappers must be shrinkable (never `flex-shrink: 0`).
6. One search box per section, below the buttons that narrow the same list, left aligned. It searches the section (Facilities keeps a facility whose booking matches; Events one whose attendee matches). `EntityManager`/`AreaEditor` `query` narrows what is drawn, never what is loaded, so reorders renumber against the whole list; the drag grip is withdrawn while a query runs.
7. The primary action ("+ Add person", "Publish week", "Add member"...) sits on the right of the search row, not the title line (`HeaderSearch` `trailing`; `ModuleLayout` `twoRow` with `items-end`; `twoRow` filters get `flex-1 min-w-0`, actions `shrink-0`). In a column container `HeaderSearch` needs `style={{ flex: '0 0 auto' }}`.
8. Set input widths INLINE (`INPUT_CLS` has `w-full`; class order is Tailwind emit order).
9. A composite widget (picker, chip multiselect, segmented control) never sits in a `<label>`: `Field` renders a label that forwards a click to whatever control it holds. Pass `composite` (renders `role="group"`). Picker rows and clear buttons in `clubmanager/pickers.jsx` also `preventDefault()` in `choose()` as a net.
10. Never declare a component inside a render (`const Header = () => ...`): new element type each render kills the caret. Use a plain function and call it (`{header()}`). A `const` the header reads must be declared above every `header(...)` call, including ones in early returns (temporal dead zone; Roster's `publish`).
11. `usePref(key, fallback)` is per user, per browser, read in the state initialiser (not an effect). Counts come from one fetch (`clubhouse/data.js` `useClubhouseData` plus `deriveCounts`); do not denormalise. Intros (`clubhouse/intro.jsx`): `always|once|never`, per person, default `once`; deep links pass `state: { skipIntro: true }`.
12. Indigo `#6366F1` is retired; `MODULE_BRAND.clubmanager` aliases `admin`. The old layouts (`BetterFeesLayout` etc.) wrap `BetterClubhouseLayout`; new screens use it directly.
13. Load lists with `rows(res, ...keys)` (always an array), never `r?.items || r || []`.

**Access and scope**
14. Each nav item carries the capability its router enforces (Roster `MANAGE_VOLUNTEERS`, Committee/Events `MANAGE_COMMITTEE`, Facilities `MANAGE_ASSETS`, Diary `MANAGE_CLUB_DIARY`, Families `MANAGE_FAMILIES`). No role gates (`requireRole="super_admin"`, `super: true`); the server never relied on them. `/admin/member-portal` stays super-admin only.
15. BetterComms scope rule (hard): never expose Super Admin (directory, telemetry) fields, context bar or copy in a club build, not disabled, not listed. `segmentFields.jsx`: `CLUB_FIELD_DEFS` imported only by `ClubhouseSegments.jsx`, `DIRECTORY_FIELD_DEFS` only by `InternalSegments.jsx`; `SegmentsRoute.jsx` chooses on `is_marketing_org`. `segmentEngine.jsx` imports neither, `defs` is required; no `isInternal` flag.

**Directory and people**
16. Three independent type axes from `services/directory.list_people`: `membership_types` (migration 175, club's own catalogue, the real type, may be empty), `fee_members.member_category`, and `players.status` as `player_status` (NULL for a non-player). No single membership-type column. Sponsors are not people (`org_sponsors` is the organisation; their person is a member typed "Sponsor Contact").
17. Membership-type CRUD lives in BetterFees (`MANAGE_FEES`), so `GET /club-admin/directory/people` returns the catalogue itself. Directory sets `membership_type_id` via `MemberUpsert` (`_resolved_type_id`: 422 for another club's id, `""` clears); the join is org-scoped both sides.
18. Families is BetterStats Core: `/admin/families` (`requireCore`, `BetterStatsLayout` must forward `caption`); `/admin/clubhouse/directory/families` redirects. A suggestion starts with nobody selected; confirm is dead until someone is picked; unselected players stay in the list.

**Fees**
19. Match-fee status is derived, never stored: `allocate_match_days` (`services/fees.py`) pays oldest first (`played_at` nullslast, then `id`), boundary game `partial`, $0 game `na`, leftover is credit. Buckets stay separate (match credit never offsets membership owing); no tier means no credit; overpayment not clamped. `paid_payment_id`, `mark-paid`/`unmark`/`payments/bulk` are legacy but live.
19a. Every sync ends with `_refresh_fee_match_days` inside `sync_organisation` (all kinds but `player_deep`); do not add a second call in a caller. Fee enrolment reads two sources: scorecard appearances (these also charge match days) and CA season totals (`_aggregate_player_ids`: club players with matches > 0, Exclude grades honoured). A player in the totals only is on the list with no match days. Never make enrolment depend on a scorecard existing.
20. `patch_member_season`: key presence is intent (`model_fields_set`). Absent `fee_schedule_id` leaves the tier; `null` or `""` clears it. Never assume a field is always present. 
21. Accounts detail: every save button saves every touched panel (baseline compared), one PATCH per endpoint (Membership and Tier both write `fee_member_seasons`, two would race). Touched panel shows UNSAVED; a button names other panels it writes; two or more reads `SAVE ALL CHANGES (n)`; nothing edited sends nothing.
22. `fee_member_seasons.playhq_registered` (+ `_at`, migration 235) is an admin-ticked fact (no API). Rollover never sets it. Accounts season is URL state (`?season=`, `replace`); unknown falls back to newest.
23. Rollover: `POST /club-admin/fees/rollover/undo` clears a season's rows but keeps members with a payment (`fee_payments` cascades). `DELETE .../members/{id}/season` 409s once a payment exists. `POST .../members/enroll` is idempotent (`ensure_for_player`). `RolloverModal` warns when the destination season has no fee schedule (tiers resolve by name against it).

**Roster, areas and roles**
24. Role is a level: Area, Role, Shift. An area holds a palette (`roster_area_roles`, migration 306) of roles each with its own gating `required_qualification_type_id`; each shift and pattern carries one `role_id`; `check_assignment` reads role and qualification off the shift. `roster_areas.required_role_id`/`required_qualification_type_id` are deprecated (backfill only; `list_areas` still emits the first palette entry). `role_id` on patterns and shifts is `ON DELETE SET NULL`; `roster_area_roles.role_id` is `NOT NULL ON DELETE CASCADE`.
25. Paid is derived from the shift's role type (`category == 'paid'`, `PAID_CATEGORY`), never a per-shift or per-person flag. `volunteer_hours.is_paid` (migration 221) is the one snapshot, stamped when posted. Never sum wage bill and volunteer effort. `role_shortages` buckets by `s.role_id` (NULL is `no_role_required`).
26. The roster subsystem is raw SQL outside ORM/alembic: mirror every DDL change idempotently in `main.py`'s lifespan, byte-identical to the migration. `volunteer_hours.roster_shift_id` has no FK on purpose.
27. A shift outlives an archived area (`delete_area` is soft; `list_areas` is active only). Never look a shift's area up in the active set: `_shift_rows` LEFT JOINs `roster_areas` and carries `area_name`; `areaLabel(shift)` never returns `undefined`. `assign`/`check_assignment` take no `area`; `assign` refuses only "Unknown volunteer".
28. Open-shift chips group by `(area_id, role_id, start, end)`, never name plus hours. Roster grid Areas view groups shifts by role (`areaRoleGroups`, null role is "General help" last, only roles with shifts draw); one group leaves the row byte-identical; `areaDayCol` is the one chip renderer; collapse is `usePref('roster_areas_collapsed', {})`, default expanded.
29. Confirm roster: `roster_shifts.worked_hours` NULL is not checked, `0` is did not turn up. Confirming reconciles via `uq_volunteer_hours_shift` (upsert, deletes posted row for a shift since unassigned or zeroed). Unconfirming leaves posted hours. `hours_summary` keeps rostered and worked apart.
30. Roster drags: a shift drops only in its own day column; a blocked person still accepts the drop and the server returns the sentence; open chips are drop targets in People view. Frozen first column is `position: sticky` on the grid item; keep its background opaque (no row tint).
31. Role titles are unique across all roles; the Roles list hides committee roles (`is_committee` or committee type). `_role_clash_message` (`services/roles_activities.py`) is the one definition for `create_role` and `update_role`: a hidden committee clash names the Committee screen and asks for a different name (never "reclassify", the flag alone hides it). Archived clash reactivates.
32. `organisations.diary_start_month` (1-12, default 7) drives the Club Diary season plan; edited in Settings (`DiaryYearPanel`).

**Merch and assets**
33. One asset register: `club_assets` is the base; `merch_assets` stays in place, read by nothing, routes deleted. `services/asset_register_ddl.py` is the one DDL copy (alembic 279 and lifespan). The carry fills, never clobbers (`COALESCE`), matches asset tag then case-folded name only, maps vocabularies (`new`->`excellent`, `retired`->`unserviceable`, `out_for_repair`->`in_repair`). `merch_asset_id` makes it idempotent; `source='merch'` marks inserted rows so the downgrade removes only those (never delete on the id).
34. Asset alerts are core: `assets.asset_alerts`, `GET /club-admin/assets/alerts` (service and `replace_due_date`), no module gate.
35. BetterMerch: stock is `merch_variants.quantity` (one 'Standard' variant if un-varied); `record_movement` bumps balance and writes the audit row, no commit; `merch_alerts` computed on read and feeds the bell when `org_has_module(club,'merch')`. Gated `require_module("merch")` plus `MANAGE_MERCH`; player link admin-only. Per-variant `unit_cost`/`unit_price` override product; `for_resale` false is club-use (no sell price or owing).
36. Square is a one-way mirror to BetterMerch, all in ONE transaction (helpers `flush`, avoids `MissingGreenlet`). Inventory count is truth: sales import as `sold` movements, then a `stocktake` movement sets the absolute count (no double decrement); dedupe on `external_ref` (`square:{order_id}:{line_uid}`). `ensure_fresh_token` refreshes within a week of the 30-day expiry (`session.refresh(conn)` after). OAuth `state` is a signed JWT (20 min); callback is public `routers/public_square.py`; `sync_all_square` runs daily 04:00.

## Traps and failure signatures
- "Could not load facilities.": wrong response key (rule 13). Picker empties after choosing, Edge/Safari only: rule 9. Caret leaves the search box after one character: rule 10 (`fill()` cannot catch it). Pale `#e5e7eb` border: rule 4. Tier reset or a panel's edits lost: rules 20, 21.
- Shift chip "undefined ×2" or "Unknown volunteer or area": archived area (rule 27); React renders a bare `undefined` child empty, only string concat prints it. Role add refused with none visible: rule 31. Roles merged into one chip: rule 28.
- Infinite `/fees/all-members` calls: an effect depends on `toast` and its `catch` raises a toast.
- Unrelated PATCH 500 in a stubbed-lifespan harness: `audit_logs` missing (aborted transaction poisons the commit); create lifespan-only tables (`player_achievements`, `org_award_definitions`, `audit_logs`) by hand.
- A browser-suite stub returning an object where the router returns a bare array breaks Accounts/Payments.

## How to verify a change here
- Backend, real Postgres (`backend/verification/`): `verify_roster_area_roles.py` (control fails per-role qualification and role-on-shift checks), `verify_role_create_committee_clash.py` (control neuters the committee branch of `_role_clash_message`), `verify_member_fees_form_save.py` (control fails the tier reset; expire the session after raw UPDATEs).
- Browser (`frontend/verification/`): `verify_clubhouse_buttons_browser.mjs`, `verify_member_fees_save_browser.mjs`, `verify_roster_area_roles_browser.mjs`, `verify_roster_role_grid_browser.mjs`, `verify_roster_open_shift_labels_browser.mjs` (target `div[draggable]`).
- Assert layout from real boxes and computed style; gate absence checks on the thing having been shown first; control runs must report, not crash.
- `text=UNSAVED` matches ancestors (use `data-testid`). HTML5 drag tests: dispatch `DragEvent`s, `dragstart` and `drop` in separate `evaluate` calls.
- Re-run a 390px `<h1>` and `scrollWidth` pass over Clubhouse screens when adding one (Accounts, Payments, Stock overflow pre-existing). Suites share one database.

## Operator commands and scripts
- None in the archive. Migrations 221, 222, 235, 279, 306 via alembic plus the lifespan mirror. Square deploy: server `.env` `SQUARE_APP_ID`, `SQUARE_APP_SECRET` (never commit), `SQUARE_ENVIRONMENT=production|sandbox`, optional `SQUARE_API_VERSION`; register redirect `https://betterat.cricket/api/public/square/callback`; box must reach `connect.squareup.com`.

## Open follow-ups
- Joining the data (handoff step 4): Fees members, Comms contacts and ClubManager directory are still three person lists.
- Logo mark not made (lockup reuses `betteradmin.svg`).
- No route-leave guard for an UNSAVED panel.
- Roster: no migration of a shift's people when its role changes; no per-role headcount target.
- `pb-hairline` typo unswept; Square tokens stored plain; no asset depreciation fields.

## Flags: conflicting, superseded or possibly obsolete guidance
- [FLAG-CLUB-1] Merge section calls the module BetterClubhouse. | Reversed in v9.40.0; `modules.py` has `"BetterAdmin"` (comment: "briefly BetterClubhouse"). | BetterAdmin to BetterClubhouse merge, L9341-9486 | keep structure, retire naming.
- [FLAG-CLUB-2] "Two things deliberately still say BetterAdmin" (marketing, `billing_pricing.py`). | Now everything says BetterAdmin; Stripe Product names keep their creation-time name. | same, L9341-9486 | retire; verify Stripe dashboard.
- [FLAG-CLUB-3] Merch: "toggle covers fees+comms+merch", Equipment as a Merch page. | Group is fees, comms, merch, crm; Equipment moved to `club_assets` (279). | L12891-12984 vs L5310-5391 | verify, retire Equipment detail.
- [FLAG-CLUB-4] Directory search "above the filter buttons (v9.51.0)" vs "below the buttons that narrow the list (v9.52.1)". | Conflicting wording; later text wins. | L8536-8589 vs L5134-5309 | verify on live Directory.
- [FLAG-CLUB-5] Paid via `roster.area_pay_kinds`. | Superseded by 306; function gone. Snapshot rule holds. | L9218-9282, superseded by L8699-8976 | retire resolver.
- [FLAG-CLUB-6] Nav `super` flag in the merge section. | Removed in v9.6.1; capability per item is the rule. | L9341-9486, L9647-9671 | retire.
- [FLAG-CLUB-7] Draft minutes (`claude-haiku-4-5`, 10/hour/club, 503 without key). | Route and model exist; limit and 503 not re-checked. | L9218-9282 | verify.

## Section coverage
| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| Committee's buttons are the house control (v9.52.0), L5134-5309 | rules extracted | Rules 2 to 10, 13 |
| - The pale edge was a class that does not exist (v9.52.1) | rules extracted | Rules 3, 4, 6 |
| - The primary action moved down beside the search (v9.53.1) | rules extracted | Rules 7, 10 |
| ONE asset register (migration 279, v9.53.0), L5310-5391 | rules extracted | Rules 33, 34 |
| Accounts kept resetting to the newest season (v9.25.2), L7272-7292 | rules extracted | Rule 22 |
| A picker inside a `<label>` (v9.23.1.1), L7403-7436 | rules extracted | Rule 9 |
| A PlayHQ registration checkbox on Accounts (migration 235), L7574-7596 | rules extracted | Rule 22 |
| An absent key is not a clear (v9.65.2), L7597-7667 | rules extracted | Rules 20, 21 |
| BetterFees season rollover (v9.19.13), L7668-7709 | rules extracted | Rule 23 |
| Families is a BetterStats tool again (v9.19.7), L7710-7748 | rules extracted | Rule 18 |
| The Directory's three type axes (v9.11.1), L8536-8589 | rules extracted | Rules 16, 17; FLAG-CLUB-4 |
| One look across BetterClubhouse (v9.10.1), L8665-8698 | rules extracted | Rules 1, 3, 12 |
| A role is a level between the area and the shift (migration 306), L8699-8976 | rules extracted | Rules 24 to 26 |
| - The roster grid opens an area into its roles (v9.82.1) | rules extracted | Rule 28 |
| - An open shift on an archived area read "undefined" (v9.82.4) | rules extracted | Rules 27, 28 |
| - A shift on that archived area could not be rostered (v9.82.5) | rules extracted | Rule 27 |
| - A duplicate role named a role the list will not show (v9.82.3) | rules extracted | Rule 31 |
| Confirming the roster, frozen column, drags (migration 222), L8977-9021 | rules extracted | Rules 11, 29, 30 |
| Roster shift CRUD, paid vs volunteer hours, diary year (migration 221), L9218-9282 | rules extracted (paid resolver superseded by 306 section) | Rules 25, 29, 32; FLAG-CLUB-5, 7 |
| BetterAdmin to BetterClubhouse merge (v9.3.0), L9341-9486 | rules extracted (naming superseded by v9.40.0) | Header; Rules 1, 2, 5, 7, 11, 12, 15; FLAG-CLUB-1, 2, 6 |
| BetterClubhouse is open to club admins (v9.6.1), L9647-9671 | rules extracted | Rule 14 |
| BetterFees Match-Fee Auto-Allocation (v7.32.0), L12882-12890 | rules extracted | Rule 19 |
| BetterMerch club stock register (v8.18), L12891-12984 | rules extracted (Equipment superseded by asset register) | Rules 35, 36; FLAG-CLUB-3 |
| - Square POS integration (migration 084, v8.18.1) | rules extracted | Rule 36; Operator commands |
