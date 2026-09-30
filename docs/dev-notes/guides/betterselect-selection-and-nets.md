# Guide: BetterSelect selection board, squads, availability, rules, nets, player kit and date of birth

**Read this before**:
- `frontend/src/pages/admin/betterselect/*` (AdminSelection, NetSession, Squads board, `dragOrder.js`, `selectionMeta.js`, `ui.jsx`), `routers/net_manager.py`, `routers/public_net_checkin.py`, `routers/availability.py`, `routers/public_availability.py`.
- `services/selection_rules.py`, `selection_pool.py`, `player_age.py`, `player_kit.py`, `profile_import.py`.
- Squad membership (`squad_team_id`, `team_members`), marking a player inactive, `directory.set_squad`.
- Nets live session, batting order, padding up, priority, check-in QR/NFC link, guests, `net_attendance`.
- Self-service availability link (`/avail/:token`, `bs_avail`).
- Association rules (age, overseas, workload, finals), date of birth, `select_show_age`, shirt number / shirt size / pants size.
- Symptoms: two devices showing different nets sessions, a player missing at the nets door, Selection header toggle painted over, a 402 naming "admin".

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/betterselect-selection-and-nets.md`. Grep hints: `three pools`, `pointer events`, `padding up`, `turning up isn't batting`, `net_checkin_token`, `Ending the night`, `age_basis`, `selection_rule_players`, `visible_age`, `VALUE_FIELDS`, `min-w-0`, `full-replace`, `turn_seq`, `shirt_number`, `ADMIN_MODULE_KEYS`, `availability_link_token`.

**Related guides**: `betterselect-votes-and-medals` (same fixtures); `imports-manual-entries-and-data-tidy` (importers); `clubhouse-people-roster-fees` (Directory); `clubhouse-committee-and-plans` (letterhead); `betterfootball-afl`; `cross-club-and-data-safety`.

## Standing rules

**Squads board and inactive players**
1. Unassigned is a working list: active, still-around, unsquadded players. Everyone else is FILED, not hidden: `Potential fill-ins` (played before, not lately) and `Not yet played`. Cards in any pool must still drag into a squad.
2. "Still around" uses the club's `dormancy_months` from the availability-matrix payload, the same definition the matrix and `selection_pool` use. No second window.
3. The fill-in reach offers only windows wider than the dormancy boundary (24 months: 3/5/10/any; 12: 2/3/5/10/any); a control that can only answer "nobody" is worse than none.
4. Marking a player inactive clears their squad in the same write (`update_player_profile`, profile importer), only when the request sets the status. Reactivating does not re-file. `auto_assign_suggest` and Bulk add skip inactive players. Board shows "N inactive not shown" plus `Show inactive players`.
5. Every squad write must mirror into `team_members` (`directory.set_squad` once did not). Raw SQL there, by that module's posture.

**Nets live session (multi-device)**
6. Never reintroduce a full-replace attendance write. Every change is a small discrete write (check in, remove, batted, reorder, rotate, clock) that bumps `net_sessions.version`. Screens poll `GET /sessions/{id}/live?since=`; a match returns `{version, server_time, unchanged: true}`.
7. Bump the version in SQL (`_touch` assigns `version = version + 1`), never `s.version + 1` in Python, or simultaneous taps leave the version unmoved.
8. The clock is an absolute deadline (`live_state.ends_at`); devices count down against `server_time`. A passed deadline reads as stopped before anyone writes it (`_timer_payload`).
9. Rotate must not repeat: `RotateBody.turn_seq` is the turn the sender saw; older turns are ignored. Auto-roll is server side inside the idempotent `expire` action, which refuses a deadline not yet passed.
10. Duplicate check-in is a no-op at two levels (app read, `IntegrityError` on the partial unique). Capture `club_id` before the flush: `club.id` after `db.rollback()` is a lazy load (MissingGreenlet). After `check_in_person` returns None touch no lazy attribute.
11. `reorder_queue` appends ids the sender did not know, so a stale reorder drops no one. `_renumber` re-lays `position` 0..n-1 after every mutation (waiting first, then batted). Sending someone back goes to the END.
12. `ended` is read off the server payload. Ending stops the clock in the same write (`update_session`) and closes the QR link (`live_sessions` returns active only). Nothing is destroyed; Reopen restores.
13. `GET /nets/players/{id}/attendance` returns every session (cap 500); `attended` is that list's length. The tally modal reads whole history.
14. CSVs: session register includes guests; per-player report excludes them. `days=0` is all time. Use `CAST(:since AS date) IS NULL OR ...` (asyncpg cannot type a bare `:param IS NULL`). Downloads are plain `<a href>`.

**Batting order, padding up, priority**
15. Drag uses pointer events, never the HTML5 drag API (iOS Safari fires none). `touch-action: none` on the GRIP, not the row. Snapshot thresholds at pick-up in PAGE coordinates. Rows reorder under the finger (no ghost). A drag holds the poll off on the write's in-flight counter; the preview is held until the write returns. Arrow keys move a focused grip.
16. One "Batting order" list; first `nets` rows badged `NET n`.
17. Padding up is an explicit flag, not the next N. It is spent by a rotation at both ends and cleared when marked batted or leaving the rotation; someone further down keeps theirs.
18. Priority records a fact and moves nobody; ticking always asks. The reason goes into the existing `note` (pre-filled, never overwritten). It survives a turn and a spell out.
19. "Bat next" is front of the line for the NEXT turn, not the list: while a turn runs the top `nets` names are in, and inserting above them swaps a batter mid-knock and marks a non-batter as batted. `netsBusy` covers turn-over-not-rotated. Dragging is exempt.
20. Every state is a word as well as a tint (`NET n`, `PADDING UP`, `PRIORITY`); pills always drawn, only the LEFT EDGE takes precedence (net, padding up, priority). Text and grip at `--pb-dim`, never `--pb-faintest`. Row actions wrap at 390px.
21. Glyphs: pad = PAIR of pads, filled, strap as an EVEN-ODD hole; bat = two diagonal strokes. Judge at 16/22/40/72px.

**Nets roster, `bats`, check-in link, guests**
22. `GET /nets/roster` returns every `is_player` player tagged `dormant`/`inactive`; the screen groups, never filters. Keep `active_self_service_players` unchanged (built from `dormant_player_ids` + `club_player_roster`; the public link reads it).
23. `net_attendance.bats` separates turning up from batting. `_waiting()` is the one queue definition (`_rotate` reads it). Returning goes to the BACK. `check_in_person` (single writer, admin and public) takes `bats`/`note`; a repeat check-in must not rewrite state.
24. QR and NFC are one link, one token (`organisations.net_checkin_token`). Scanning joins EVERY live session (`net_manager.live_sessions`: active, dated within a day either side of today, no club timezone).
25. A newcomer is a GUEST (`player_id` NULL + `guest_name`), never a player. Typed details go to `net_checkin_registrations` (`pending`). Approving is the one place a player is created and it CONVERTS the guest row (keep the real row and drop the guest if both exist). Dismissing leaves attendance alone. No `previous_club` column.
26. Two switches: `net_checkin_require_pin` (default true) and `net_checkin_allow_registration`.
27. `net_attendance.source` ('admin'|'self') drives the arrival alert (pre-272 rows read 'admin'). Only `self` pops up, chimes and vibrates; a screen opening mid-session seeds its seen set silently. iOS ignores `navigator.vibrate`. `touch_session` (= `_touch`) must run on a self check-in or the poll sees nothing.
28. Landing payload never says who is checked in; refusals are 404. No Web Push (deliberate).
29. Guests to players: `GET /nets/guests` groups by `_guest_key` (case and outer whitespace only, not fuzzy) and leaves out anyone with a PENDING registration; `POST /nets/guests/promote` moves the WHOLE history, collapses clashes, settles the registration, resolves the key server side. Gate: `require_any_cap` of `MANAGE_SELECTIONS` or `MANAGE_PLAYERS`. `UnrosteredGuests` renders nothing when empty and never calls the endpoint for a club without BetterSelect (402).

**Self-service availability**
30. Unauthenticated router, NOT under `require_module`: resolves the club from `availability_link_token`, checks `org_has_module(club,"select")` and the enabled flag itself (else 404). PIN = last-4 of `Player.phone`; cookie `bs_avail` (~30 days); lockout 5 wrong / 15 min per (token, player, IP) via `rate_limit.FailureTracker`; unknown player counts as a failure.
31. Self answers are `player_availability` rows with `source='self'`, `recorded_by` NULL; an admin override re-stamps `'admin'`. Admin endpoints `GET/POST /availability/self-service`, `POST .../regenerate` (`MANAGE_SELECTIONS`).

**Association rules**
32. One table `selection_rules` (`kind`, `scope`, `config`); `services/selection_rules.py` is the only reader/writer. Kinds: `age`, `overseas`, `bowling_workload`, `finals_qualification`, `grade_cap`, `fees`, `training`, `registration`, `rest`, `custom`. No table per kind.
33. Age is measured on a setting: `age_basis` (month, day, which END of the season gives the year) or `fixed_date` (does not move with the season). Cutoff resolves against the SEASON. `season_start_month` (default 7) is the fallback. Operators per end: `min_op` gte/gt, `max_op` lt/lte (none reads gte/lt). `_min_phrase`/`_max_phrase` are the one wording. Ladder runs to 23.
34. Rules name grades, never ids. Names match sponsor-stripped and case-folded, and the fixture grade is folded through `grade_alias_map`. Empty scope means EVERY fixture. The scope picker (`club_grades`) mirrors Manage Grades (aliases folded, `display_order`, `recent` flag).
35. Severity is the club's: `warn` or `block`; `bowling_workload` is forced `info`. A block removes the player from auto-fill (`autofill_eligible`) and the board opens eligible-only (once per fixture); warnings stay visible. `selection_rule_players` is the per-RULE permit.
36. Silence where data cannot answer (no DOB, fees module or override, registration row, nets session, squad seniority): never a breach.
37. Overseas cap depends on who else is picked: the browser counts it live from a payload definition, the SAVE re-counts. Never let the browser's count decide.
38. `assemble_selection` resolves fees and training FIRST and passes the maps to the engine (`_flag_maps`); `rule_context`/`club_rule_context` give the save path the same answer.
39. Qualifying games count scorecards AND named XIs, deduped on the DATE. `_FIXTURE_ONLY_KINDS` (`finals_qualification`, `grade_cap`, `rest`, `overseas`) are not answered on the matrix or roster.
40. An age rule moves the card's age to the competition's date (`visible_age(dob, club, as_of=age_at)`); the display gate still applies.
41. Screens draw nothing when the club has no rules (`flags.rules`/`rules.active`). Fees and training notes can be switched off (`show_fees`/`show_training` in `selection_rules_config`): value WITHHELD, not hidden; a fees or training RULE still flags.
42. Starter is only the CA Junior Cricket Policy bowling ladder, skip-don't-replace; no invented numbers. Settings live on the rules screen (`MANAGE_SELECTIONS`, not `MANAGE_SETTINGS`).

**Date of birth and age**
43. Age is never stored: `player_age.age_on` derives it (None for no date, future, over 120 years; leap-day safe). Club rule applied server side in one place, `visible_age`: `organisations.select_show_age` (default off), `select_show_age_under` (NULL = every player). Never send and hide.
44. The profile returns DOB, ungated `age` and `age_visible`. `select_show_age_under` is a real tri-state: `patch_settings` reads `model_fields_set`; `clean_age_limit` turns 0/junk/out-of-range into NULL.
45. Never public (no `public_show_age`); `clone_demo_club` does not copy DOB; nothing syncs a birthday.
46. `ageFilterOptions` (`selectionMeta.js`, reads `flags.age`) offers only what the rule can answer: no "18 and over" under an under-16 rule, no "no date of birth" under a limit.
47. Profile importer: a new profile column goes in `VALUE_FIELDS` and `PLAYER_FIELDS`, plus `FIELD_LABELS`, `SYNONYMS`, `row_profile`, the router's `_current_profile` (or a re-stated value reads as a change), both templates and the wizard `FIELDS`/`SIMPLE`. The suite checks every `PlayerProfileUpdate` field is importable or on a named exclusion list. Draw the wizard `FIELDS` 4th element (hint).
48. Import dates: ISO, `4 Mar 2012`, `04/03/2012` (DAY FIRST), Excel serial (cells arrive stringified; serial floor above any 4-digit year). Refuses what `player_age.dob_error` refuses. Country alone marks overseas unless "No". BetterSelect overrides can be SET from a sheet, never cleared.

**Player kit**
49. `players.shirt_number` is Core (playing attribute). `fee_members.shirt_size`/`.pants_size` are BetterAdmin (a coach or canteen volunteer has no player row). Per direct instruction.
50. `admin` is NOT an entitlement key: `org_has_module(club,"admin")` is False for every club. Gate on `fees`/`comms`/`merch`/`crm`; frontend copy is `ADMIN_MODULE_KEYS`. Sizes are WITHHELD from a club without the module (`kit_sizes` on the payload), and a write gets the 402 upsell shape. The number rides regardless.
51. Sizes are free text; `services/player_kit.py` is the one rule for profile, Directory and importer (trim, collapse whitespace, cap). A number is TEXT ("07", "00"). The Directory writes the number via the PLAYER route. Present-and-blank clears, ABSENT leaves alone. Over-long numbers are REPORTED, not clipped.
52. Member CSV (Directory and BetterFees Members share it): sizes to `fee_members`, number to `players.shirt_number` or nowhere. Resolve via the member's link, else exact name; a name held by two players resolves to NEITHER (reported in preview). New person rows link to the unambiguous same-name player without a member row; an existing member row is never re-pointed. Gate on the sheet's columns (`columns_used`) at PREVIEW. A bare `shirt` column is claimed by neither.
53. `modules.module_display_name(key)` is the one place the backend names a module (`MODULE_META`, then `BILLABLE_MODULE_NAMES`).

**Layout and process**
54. `min-w-0` goes on the element that may shrink (`<h1>` `truncate min-w-0`, toggle `shrink-0`), not the group. Selection header uses `flex-wrap xl:flex-nowrap` and moves user name + Logout from `sm` to `xl`; only Selection passes `headerLeft`. `flex-wrap` cannot save a `shrink-0` child. A native date input clips its year if it shares a row (age on the caption line).
55. Re-check `origin/main` at merge before numbering a migration (duplicate revision ids break Alembic).
56. Minutes letterhead (committee guide): colours from `theme_config`; band is two stacked shaded paragraphs, never a table; crest converted to JPEG in-browser on a white canvas, `clubLogoJpeg` returns null not throws; `header` is its own `docBlocks` argument; PDF image objects numbered LAST.

## Traps and failure signatures
- Check-in vanishes or devices differ: full-replace write (6). Arrival never shows: `touch_session` missing (27). Player missing at door: dormancy roster (22).
- Drag snaps back, never starts or oscillates (15). Batter swapped mid-knock (19). Squad filter disagrees with board (5).
- Rule stops at rollover (34); flags everyone (36). Adult's age on a card (43). Kit sizes missing or 402 naming "admin" (50, 53). Shirt "07" reads 7 (51). Importer misses a column (47).
- Header toggle painted over or 390px overflow (54). Minutes PDF page blank (56).

## How to verify a change here
- Backend (real Postgres, shipped route bodies): `backend/verification/verify_net_batting_order.py`, `verify_net_checkin.py`, `verify_player_kit.py` (control with number resolution and size writes neutered fails the importer checks), `verify_multi_squad.py`.
- Browser (`frontend/verification/`): `verify_net_batting_order_browser.mjs` (pointer and synthetic touch, `touch-action` read from computed style), `verify_net_admin_browser.mjs`, `verify_net_alert_browser.mjs`, `verify_net_checkin_browser.mjs`, `verify_guest_promotion_browser.mjs`, `verify_squads_pools_browser.mjs`, `verify_minutes_letterhead_browser.mjs`, `verify_minutes_download_browser.mjs` (must pass unchanged).
- Race two real DB sessions for the version bump and duplicate check-in.
- A control run that crashes is not a control run: read new keys via `.get`, guard imports, report what is absent. Pair set with clear, entitled with non-entitled.
- Gotchas: Playwright `**` glob does not cross a `?` (route the live poll by regex or the catch-all hands `{}` and crashes the page); routes match most-recently-registered first; `NAMES.map(att)` passes `(value, index)`; `unzip` glob-matches `[Content_Types].xml`; lifespan raw-SQL tables need their CREATE plus every later ALTER; suites share one database; stubs must match real response shapes.

## Operator commands and scripts
none. Migrations 268, 269, 271, 272, 273, 284, 289 are mirrored idempotently in the lifespan.

## Open follow-ups
- Squads header action cluster overflows 319px at 390px (shared `ModuleLayout`).
- Nets `adopt` takes any payload; a malformed one mid-deploy takes the screen down.
- Session CSV lacks padding up and priority. Nothing writes fixture availability from the nets.
- No Web Push, no bowling-overs count against actual junior spells.
- Sponsor prominence and venue naming rights: `docs/sponsor-prominence-and-venue-naming-rights.md`, not built.

## Flags: conflicting, superseded or possibly obsolete guidance
- [FLAG-BSN-1] Archive cites Postgres suites for rules, age maths, live session, roster, guests, squads pools | Checked across the whole repo during the split. Present: `backend/verification/verify_net_batting_order.py`, `verify_net_checkin.py`, `verify_player_kit.py`, `verify_multi_squad.py`; `backend/scripts/verify_squads_feedback.py`; browser suites in `frontend/verification/` (`verify_net_checkin_browser.mjs`, `verify_net_batting_order_browser.mjs`, `verify_net_admin_browser.mjs`, `verify_net_alert_browser.mjs`, `verify_guest_promotion_browser.mjs`, `verify_squads_pools_browser.mjs`). Not found anywhere: the Postgres suites the archive describes for selection rules, age maths, the live net session, guests and the squad pools | several sections | verify before citing the missing ones as existing; the check counts in the archive were not re-run.
- [FLAG-BSN-2] Kit section notes `require_module("admin")` names the module "admin", then says `module_display_name` fixed it | `auth/modules.py:431` defines it | L12119-12320 | keep later (fixed).
- [FLAG-BSN-3] Squads section says AFL has no BetterSelect squad board | football later got its own select module (`betterfootball-afl` archive) | L4592-4665 | verify.

## Section coverage
| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| Squads board's unassigned side is three pools (v9.46.0), L4592-4665 | rules extracted | Rules 1 to 5, follow-ups, FLAG-BSN-3 |
| Batting order is dragged, two flags (migration 284), L4752-4881 | rules extracted | Rules 15 to 21, Traps, How to verify |
| Nets check-in list was hiding players (migration 273), L4882-4951 | rules extracted | Rules 22, 23, 55 |
| A player checks themselves in at the nets (migration 272), L4952-5133 | rules extracted | Rules 24 to 28 |
|   sub: Turning a nets guest into a player (v9.42.1) | rules extracted | Rule 29 |
|   sub: Ending the night (v9.42.3) | rules extracted | Rule 12 |
| Association's rules written down once (migration 271), L5961-6122 | rules extracted | Rules 32 to 42 |
|   sub: What the first round of use changed (v9.41.2) | rules extracted | Rules 33 to 35, 41 |
| A player's date of birth (migration 269), L6191-6345 | rules extracted | Rules 43 to 46, 54 |
|   sub: Profile importer (v9.37.1) | rules extracted | Rules 47, 48 |
|   sub: `min-w-0` flex group overlaps siblings | rules extracted | Rule 54, Traps |
| A net session is run from several devices (migration 268), L6346-6449 | rules extracted | Rules 6 to 14 |
|   sub: Live session moved onto the server | rules extracted | Rules 6 to 11 |
|   sub: The lists a club can take away | rules extracted | Rule 14 |
|   sub: The tally opens into the dates | rules extracted | Rule 13 |
|   sub: Verification | history only (check counts) | How to verify |
| Three kit fields (migration 289), L12119-12320 | rules extracted | Rules 49 to 53, 55, FLAG-BSN-2 |
|   sub: Minutes letterhead (v9.69.0) | rules extracted | Rule 56 |
|   sub: Sponsors: written up, not built | rules extracted (pointer) | Open follow-ups |
| Self-service player availability (v8.1), L12985-13037 | rules extracted | Rules 30, 31 |
