# Guide: Cross-club data leaks, shared fixtures and never deleting a club's own work

**Read this before**:
- Writing SQL over the per-game tables (`batting_innings`, `bowling_spells`, `fielding_stats`, `game_appearances`, `partnerships`, `fall_of_wickets`, `bowler_wickets`) or `player_season_stats`/`player_season_grade_stats` that attributes rows to "our" club.
- Deciding "is this game ours" or "what kind of grade is this" (`seasons.organisation_id`, `resolve_scope`, `resolve_season_filter`, `club_game_sql`, `_club_game_clause`, `club_grade_rows`).
- Touching `sync.py` player/grade/season identity (`_resolve_org_player`, `_resolve_org_grade`, `grassroots_id`, `uuid5(org, guid)`) or merge code (`_merge_players_core`, `undo_merge`, `merge_carry.CARRIED`).
- Adding any `DELETE`/`sa_delete` near `manual_*`, a season or grade delete, a Full Rebuild, an import undo, or a club delete/archive.
- Reading a `players` row from a `fee_members` row, or enrolling people from `game_appearances`.
- Symptoms: a season drawn twice, Players-list count differing from the profile, an opponent listed as our member, another club's contact details in a Directory, a club delete that "did nothing", a merge that lost half a career.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/cross-club-and-data-safety.md`. Grep hints: `NEVER DELETE OR OVERWRITE`, `FIXTURE BELONGS TO BOTH`, `two and three times over`, `M IS MATCHES PLAYED`, `Grouping is a job`, `already in our own database`, `deadlocked`, `grade leaderboard and the profile`, `this game is ours`, `same year counted twice`, `member leak`, `shared-game rule`, `Club Delete`, `Player Over-Count`, `Grade Collision`.

**Related guides**: `stats-figures-records-and-filters` (GradeScope, competitions), `data-sources-and-sync` (sync, Full Rebuild), `cricketstatz-import` (`merge_carry`, `hand_edited_games`), `imports-manual-entries-and-data-tidy` (undo, season/grade merges), `clubhouse-people-roster-fees` (fee members, Directory), `betteriq` (per-game reads), `club-directory-onboarding-and-admin-shell` (self-serve, archive).

## Standing rules

**A. Hand-entered work is never deleted (owner's standing rule)**

1. A manual game, its innings and a hand-typed correction are the club's own work. A function may ADD to and MOVE them. It may remove or replace only what it wrote itself, never what a person wrote. There is no upstream to re-pull them from.
2. A merge MOVES a record, never deletes one. `_merge_players_core` once reached no `manual_*` table, each `ON DELETE CASCADE` on `players.id`, so it destroyed the removed player's manual and imported career. `services/merge_carry.CARRIED` is the list (shared with the undo via `merge_logs.carried_row_ids`); a table recording what a player DID belongs on it.
   A pair of same-name records with a game each on the same date, in different games, is probably two people: `services/merge_safety.same_day_clash_dates`. `merge-players` answers 409 `same_day_clash` unless `confirm_same_day_clash` is sent, and Bulk Approve skips flagged pairs. The fantasy merge, `hand_added_merge` and the org merge call the core directly and are not gated.
3. An import replaces only what it wrote (`cricketstatz_import.import_match`, matched on `cricketstatz_match_id`). `hand_edited_games` reads `manual_edit_logs` (the import writes none): an un-undone row means a person edited it, so the import skips the match and says so.
4. A Full Rebuild deletes from `games`, never `manual_games`.
5. Season and grade deletes refuse while a manual game or adjustment points at them (`_season_in_use`, `_grade_in_use`, `routers/manual_entries.py`). Both FKs cascade, so these are the only guard.
6. De-duplicating is not deleting: drop the removed record's row only for an innings the keeper already holds, never one only it had. Match unique keys with `IS NOT DISTINCT FROM`, not `=` (a season adjustment with no grade has a NULL key part).
7. Enforced by `verify_merge_carry.py`: every `DELETE FROM manual_*` / `sa_delete(Manual*)` must be on `ALLOWED_DELETES` with a reason, and every manual table with a `players.id` FK on `CARRIED`.
7a. A merge keeps the person too (v9.106.2): `merge_profile.carry_profile` fills the keeper's empty profile columns (photo trio as one unit) before the row is deleted, and the link tables (availability, squads, lineups, nets, family, aliases, fee/comms/CRM links) are on `CARRIED`. `fee_members`, `comms_contacts`, `crm_people` are `_NEVER_DELETE`. A new player-keyed table with a CASCADE or SET NULL FK goes on `CARRIED`; a new `players` column goes in `merge_profile.FIELDS`. Suite: `verify_merge_profile_carry.py` (own database).
7b. A photo address names the player it was uploaded to (`/api/images/players/<id>/photo`). Never copy `photo_url` or `hero_photo_url` between players: carry the bytes and rebuild the address with `merge_profile.player_image_url(new_id, col)`, or the picture 404s the moment the old row goes. A check that compares the stored string proves nothing; follow it through `routers/images`. Repair: `app.scripts.repair_player_photo_urls`.
8. Recovery for a lost CricketStatz career: re-run the import (deterministic ids, upsert) onto the kept record. Hand-typed history has no recovery path.

**B. A fixture belongs to both clubs**

9. A CA match between two clubs that both sync is ONE `games` row. Its `grade_id`, so `season_id`, points at whichever club synced first. That club does not own it. Both clubs' scorecards hang off it and both clubs' stats must count and classify it.
10. Never decide "is this game ours" with `seasons.organisation_id`. Use `services/club_grades.club_game_sql`: `v_effective_games.organisation_id` is us OR we are `home_org_id`/`away_org_id` (migration 167, indexed). `aggregations._OURS_GAMES` and `records._OURS_GAMES` are that string; `aggregations._club_game_clause` is the player-scoped sibling (mirrors `iq_trends._ours_clause`). Use the shared string, not a hand-rolled OR (measured slower).
11. Never classify a grade from a `grades` row your own club owns. `club_grade_rows` enumerates the club's grades PLUS every grade its games sit in, resolved to the club's answer by NAME through `grade_merge_logs`.
12. A category filter is an exclusion, only as good as its enumeration: widen the enumeration, never relax the exclusion.
13. A merged-away spelling must read as the grade kept: `grade_labels._apply_alias_fold` registers the canonical's answer under the alias in all three name maps.
14. A foreign grade's competition resolves to OUR answer (`club_grade_competitions`), never its own `competition_id`. The association fallback is only for a name we have never held.
15. `resolve_season_filter(..., include_shared=True)` reaches the other club's row for the same season (CA season GUID, then year, then name). Opt-in: only where the read is ALSO guarded by the club's own players or the ownership predicate.
16. When a board and a profile disagree because of this, bring the boards up to the profile, never the reverse.

**C. Scope the PLAYER, not just the game**

17. `games -> grades -> seasons -> organisation_id` says the game is in our competition, nothing about whose player a row is. Any read of the seven per-game tables that attributes rows to our side must ALSO scope `players.organisation_id`.
18. `is_club_innings` is set per club, so a shared game carries BOTH clubs' partnerships as TRUE: not a club filter.
19. Partnerships: scope ONE batter (same innings, same club); scoping both drops a stand with a teammate whose `players` row is under another club (exception: `_combinations` scopes both). `bowler_wickets`: scope the bowler, not the fielder.
20. Check CTEs too: `_captaincy`'s `scores` CTE summed the opposition's runs with no join.
21. Left unscoped on purpose (verified safe): `aggregations.get_player_partnerships`, `iq_trends.bowler_deep_dive` (anchored on `:pid`), `yearbooks._generate_narrative_core`, StatLab partnership/`_bowler_fielder_combo` helpers (one side scoped), `iq_team._team_fielding` combo query and `_batting_pairs`.
22. Season-aggregate reads are a different shape: read `v_effective_player_season_stats` (migration 060 emits a row only when `player.organisation_id IS NULL OR player.org = season.org`) or join `seasons s` and filter `s.organisation_id`. Never sum `player_season_stats` filtered only by `players.organisation_id`.
23. Member-to-player read-throughs join `p.organisation_id = fm.organisation_id` and use the scoped result (`directory.list_people` reads `our_player_id`, never `fm.player_id`). An unresolved link must not tag a Player nor carry a `player_id`.
24. Enrolment loads the appearing players org-scoped FIRST, then filters appearances (`fees.recompute_fee_match_days`); "only our club's players have rows" is false.
25. Migration 223: composite FK `fee_members (organisation_id, player_id)` to `players (organisation_id, id)`, NOT VALID (enforced on new writes). Still filter on read.

**D. Per-club identity (players, grades, seasons)**

26. CA participant, grade and season GUIDs are shared across clubs. Never `session.get(Player|Grade, raw_guid)` as a global create/skip in sync. Use `sync._resolve_org_player` / `_resolve_org_grade`: look up by `(org, grassroots_id)`, mint `id = uuid5(org, guid)` only when the raw GUID is already a row in another club, else keep the raw GUID (single-club orgs unchanged). `players.id`/`grades.id` no longer equal the CA GUID; the raw one is in `grassroots_id`.
27. Every Grassroots API call uses the raw GUID (`COALESCE(grassroots_id, id)`): per-grade stats `gradeId`, `get_grade_matches`, `iq_opponent` grade lookups, `ladders.py`, `iq.opponent_ladder`. Scorecard `grade.id` maps via `grade_id_by_guid`, `participantId` via `_team_pid`/`pid_by_guid`.
28. `undo_merge` must set `grassroots_id` (= `id::text`) on the re-created player, or the next sync mints a duplicate.
29. Do NOT merge a legacy-GUID duplicate into a per-club record when their seasons overlap: MyCricket and PlayHQ give different season GUIDs to one real season, `merge_players` dedupes by raw `season_id`, and the career reads 86 = 56 + 30. Recovery is undo-merge. Safe only for disjoint registrations.
30. Fold, never drop. `_SEASON_FOLD_CTE` folds seasons onto the viewing club's row for that year, then through active merges (org-filtering games leaves the table below the header). The historical bundle (`_HISTORICAL_BUNDLE_MATCH_CAP`) stays unfolded. Key season rows by `season_id`, not name.
31. `get_player_team_breakdown` is its own pass: `_canonical_season` folds alias, then own-club year row, then merges. Scope BOTH the scorecard side and CA's `player_season_grade_stats` side by season org (one side breaks the `max(held, claimed)` self-heal). A per-grade manual correction is applied last, clamped at zero, and excluded from `season_aggregate` (else counted twice).
32. The grade leaderboard `use_psgs_path` sums `player_season_grade_stats` scoped by `seasons.organisation_id`, with `max(held, claimed)` (`grade_games` floor, `grade_scoped_games` narrowing first), so it equals the profile grid.

**E. One definition of matches played**

33. M is matches PLAYED, INN is innings. `_matches_played_cte` is the one definition (batting, bowling, fielding and bare `game_appearances`, as `_scoped_games_played`), narrowing games FIRST, LEFT JOINed for the number only (never the qualification, or a batting board fills with non-batters). `records.most_matches` has the fourth arm too.

**F. Association backfill and competition grouping**

34. Grouping is a platform job, not a button. It is NOT hooked to `sync_organisation` (an idle club never reaches it via `_record_idle_run`): `competition_grouping.maybe_group_club` runs from nightly `jobs/scheduler.group_all_organisations` (02:30 Perth) over `auto_sync.eligible_clubs`, own try/except and session. `GROUP_CLUBS_PER_RUN = 40`.
35. It must finish: `run_grouping` reports `seasons_unresolved`; it re-fires only when the gap exceeds the last run's residual. One run per club (`running_run_id`).
36. Own-data phases in `services/association_backfill.py`: (a) a CA grade GUID is competition-wide, so any club's association applies to every row with it; (b) a club's own grade NAME is its own competition (same `grade_merge_logs` and sponsor-strip rules as `club_grade_rows`); (c) `propagate_from_directory`: a club the Directory shows in EXACTLY one association is filled whole, matched by NAME never by the Directory's id (id spaces disagree), reusing an existing id or minting a `uuid5` in its own namespace.
37. Every phase refuses to guess (`HAVING COUNT(DISTINCT association_id) = 1`): a wrong association files matches under a competition never played. Statements are `WHERE association_id IS NULL`, so reruns write nothing. `grades.association_id` is TEXT: cast to `text[]`, not `uuid[]`.
38. `propagate_all` loops until nothing writes (max five passes). The API phase applies each answer to EVERY club holding that guid.
39. `apply_associations` is ONE `UPDATE` via `unnest` inside the same semaphore as the fetch (a per-guid loop deadlocked, `DeadlockDetectedError`). Backstop: bounded retry in a FRESH session.
40. Dry runs use `propagate_all(commit=False)` (real loop, measure then roll back). `plan_api_phase` gives the CA call count (a lower bound), after the SQL phases.

**G. Club delete and archive**

41. Club "delete" is a soft archive: `organisations.archived_at` (migration 143), `POST /club-admin/super/clubs/{id}/archive` and `.../restore`. Archiving does NOT touch `is_active`. The club list hides archived unless `?include_archived=true`. Hard `DELETE` (`delete_club`) returns 409 unless already archived.
42. The live schema can drift from the ORM: `partnerships.game_id` was not `ON DELETE CASCADE` live, so the club delete rolled back silently. Migration 142 fixes nine per-game and per-player stat tables (incl. `partnerships`, `milestones`, `fee_match_days`): `NOT VALID` then `VALIDATE CONSTRAINT`, checking `pg_constraint.confdeltype` first. Do not trust ORM `ondelete` on pre-Alembic tables.
43. `sync.find_matching_organisation(..., include_archived=True)` by default (so `upsert_organisation` reuses an archived row). Self-serve `search`, `/prepare`, `/submit` pass `include_archived=False`, and `/submit` clears `archived_at` on reuse.

**H. Routes that take a player id (access)**

44. Every route that takes a player id and is NOT public must check `player.organisation_id == club.id` with `get_current_club`, and answer 404 (not 403, which confirms the player exists). A capability check (`require_cap(MANAGE_PLAYERS)`) says the caller is an admin of SOME club, nothing about THIS player. `GET` and `PATCH /players/{id}/profile` lacked it, so any club's admin could read and overwrite another club's player's contact fields. `verify_player_route_access.py` is the check, and its control run fails on the old code.
45. There is no `PATCH /players/{id}` (it renamed any player with no login at all and nothing used it). Rename is `PATCH /club-admin/players/{id}`. A route with neither a login dependency nor a club check is a hole: grep a new `@router.patch/post/delete` for `get_current_user` or `require_cap` before it ships.
46. Known, left on purpose: `POST /players/{id}/request-sync` is public (the profile page's "request a sync" button, de-duplicated). `POST /players/{id}/claim` lets any signed-in user claim an unclaimed profile and no screen calls it; it is closed for a person who asked to be removed and otherwise unchanged.

**I. Linked clubs (migration 322, v9.106.33)**
48. A Super Admin links clubs (`club_links`: one row per club, a shared `group_id`, two or more members, a club in at most one group). `services/club_links.py` is the only place that knows the rules. A user still has exactly ONE membership (migration 017); a linked Club Admin works in another club through `users.active_club_id`, the Super Admin's column. `auth.effective_club_id` (async) is the one answer to "which club is this request for": a `club_admin` is honoured only while `can_switch_to` says the target is linked, active and not archived, checked on EVERY request, so unlinking ends a switch at once and a stale column never widens reach. Only `club_admin` switches, never `club_member`.
49. Anything that resolves "the club" must go through `get_current_club` or `effective_club_id`, never `membership.club_id`. `require_module` read the home club and would have gated a switched admin by the wrong plan; it now uses `effective_club_id`. A lookup by `ClubMembership.club_id == club.id` finds nothing for a switched admin: use `club_links.covers_club` (`committee.is_club_admin`, StatLab's report gate). `User` has no `role`; read the membership.
50. Each club keeps its own trials, subscription status and Core state. A linked admin is bound by the club they are working in and gets nothing from the home plan. Money and plan authority stay with the club's OWN admins: the `m.club_id == club.id` gates in `billing.py` and `club_admin.py` (start trial, module requests, payment methods, billing method, primary transfer) are deliberately left home-only. Do not relax them for linked clubs.
51. `/auth/me` carries `linked_clubs` (home first, only active clubs), `can_switch_linked_clubs` and `acting_as_linked_club`. `acting_as_club` stays Super Admin only (`trialStatus.js` reads it). The football silo shares the router, so the DDL is in `cricket_schema_mirror.SHARED_DDL_MODULES`. Load a club WITH its `module_subscriptions` before reading entitlements: a second `db.get(..., options=)` for an object already in the session returns the cached copy and skips read-time trial expiry (`_build_me` did this for a club at home).
52. Known limit: the acted-as club is stored per user, not per tab. Two tabs of one admin share it, so a tab left open on club A acts on club B after a switch elsewhere. The banner is the mitigation. A per-request `X-Club-Id` check would close it.

**J. Who can open what: module locks and per menu item access (migration 344, v9.121.0 and v9.122.0)**
53. Everyone starts with full access. A `club_admin` with no `user_access` row has every capability. A Primary Admin (or a Super Admin) can limit a colleague in two ways: lock them to ONE module (`stats`, `select`, `socials`, `iq`, `fantasy`, `admin`; mode `module`), or give them a choice of menu items each at View or Manage (mode `items`, grants stored as `{item id: level}`). `services/access.py` is the only place that knows what a lock means, and `user_access(user_id, club_id, mode, module_key)` is the source of truth. A limited person's membership is role `club_member`; its `capabilities` list and `view_only_caps` list are a CACHE derived from `MODULE_ACCESS` and the item catalogue `ITEMS`: rewritten on every change and by `resync_module_caps` on every boot, so a catalogue change reaches existing users on deploy (an item the catalogue no longer has is dropped, never an error). Never edit those lists by hand and never write a second map from items to capabilities.
54. Only the Primary Admin or a Super Admin changes access (`_users_actor(needs_primary=True)`). The Primary Admin and Super Admins are never locked. The first admin to sign up is the Primary Admin (every signup path calls `ensure_primary_admin`). Never give a club user the `super_admin` role, which reaches every club.
55. A locked person stays in their own club: only `club_admin` switches (`effective_club_id`). A switched-in admin cannot list, invite, edit or remove the linked club's users (`_users_actor` refuses when the membership club is not the request's club). Another admin cannot edit, reset the password of, or remove the Primary Admin.
56. Every signed-in route declares what it needs: `require_cap`, `require_any_cap`, `require_full_admin` (club-wide screens that belong to no module: Plan & Billing, the setup wizard) or staff-only. A route with no declaration goes on `OPEN_TO_ANY_CLUB_USER` in `verification/audit_route_access.py` with a reason (a person's own inbox and settings, data the public site already shows, or a check inside the handler). The audit fails on an undeclared route and on a stale entry. A new gate never changes what a full admin can do, so tighten rather than loosen. The gates carry `required_caps` (and `full_admin_only`) so the audit can read them.
57. A new capability goes in exactly one module in `MODULE_ACCESS` AND is some item's own capability in `ITEMS`, or is in `NEVER_LOCKED` (`manage_settings`, `manage_users`, `run_hard_refresh`) or `UMBRELLA_CAPS` (`manage_selections`). The suite checks these cover `ALL_CAPABILITIES`, that no item grants a never-locked capability even with every item on, and that every prerequisite names a real item. A new menu item carries the capability its router enforces.
58. The Users PATCH reads `access` through `model_fields_set`: absent leaves a lock alone, `{"mode": "full"}` clears it. A name edit must not clear a lock.
59. The frontend hides what a locked person cannot open (`fullAdmin: true` nav items, dashboard tiles by `user.access`) and does not fetch what they cannot read (plan, setup flow, sync log). The server is the gate; the screen only presents.
60. Per menu item access: an item is a switch with the capabilities Manage grants (`caps`), an optional `view_caps` (votes: seeing results is a capability of its own), and `needs`. At View the item's capabilities are held and listed in `view_only_caps`. Where several menu screens share one capability (the three fee screens, the four email screens, Import Stats with Manual Entries) they are ONE switch that names every screen it opens, until the capability is split.
61. View is enforced by method, in one place. `require_cap` and `require_any_cap` take `request`: a read (GET, HEAD, OPTIONS) passes with the capability held at either level, anything else needs it at Manage, and a call with no request counts as a write. So a read must be a GET. `membership_can_write` is the same rule for an inline check (StatLab approvals use it). Known limit: a POST that only reads (the import and email previews, Ask BetterIQ) is refused at View.
62. BetterSelect has a capability per item: `select_squads` (squads and ladders), `select_availability`, `select_selection` (selection and whiteboard), `select_nets`, `select_fines`, `select_rules` (settings and selection rules), `select_audit`; fixtures (`manage_fixtures`) and votes keep theirs. `manage_selections` stays as the umbrella that satisfies any of them (full admins, a whole-module lock and the legacy allowlists hold it). A BetterSelect route gates on `require_any_cap(SELECT_<ITEM>, MANAGE_SELECTIONS)`, never on `MANAGE_SELECTIONS` alone, and a read several screens share (squad lists, the availability config, rules, who is already picked) gates on `require_any_cap(*SELECT_ANY)` on a GET only (the suite checks it sits on GET routes only). In the browser a menu item takes `anyCaps: selectCaps(CAP.SELECT_<ITEM>)` and a screen's `canEdit` is `canEditCap(CAP.SELECT_<ITEM>, CAP.MANAGE_SELECTIONS)`, which is what draws it read only at View.
63. Prerequisites are items (`needs`), added by `resolve_grants` on save and mirrored by `withNeeds` on the screen, which says what it switched on. An item another chosen item needs cannot be switched off. Today only Selection needs Availability (at View); shared reads need no prerequisite.
64. Only BetterSelect screens draw read only at View. In the other modules the screen still shows its buttons and the server refuses the write with a plain "view-only" message. Moving a screen over is the same two edits as rule 62.
65. Not built, agreed in principle: role templates such as Captain (live linked, detaching when someone's switches change), per-club roles at a linked club (a link making someone eligible rather than granting access), a certification gate on junior data, and splitting the other shared capabilities (fees, emails, imports, BetterIQ) into per-screen ones.

## Traps and failure signatures

- Season "2025/26" twice, rows sum to the header: fixture filed under the first club's season (rule 30).
- Players M 106 vs profile 150; Juniors returns senior matches (rules 10 to 12, 15). Board 61 vs grid 60 (rules 31, 32).
- Opponents in Directory/fees with contact details (rules 23 to 25). Opposition's best stand in our review (rule 18).
- Career doubled (7 became 63; 86 = 56 + 30) or second club shows only unique grades: rules 26, 29. Cutover: Sync Now mints per-club rows and moves aggregate seasons; game-level rows re-attach only on a Full Rebuild.
- Club delete "did nothing": rule 42. Archived club "already registered": rule 43.
- Audit noise: match a per-game table only after `FROM`/`JOIN` (`st.batting_innings` is a COLUMN on `player_season_stats`).
- A limited person sees a tile or link they cannot use, or a screen 403s for them: rules 56, 59. A new route fails `audit_route_access`: declare its capability or list it with a reason (rule 56). A locked user lost a capability after a deploy: the module map changed and the boot resync rewrote the list (rule 53).
- A check reading zero is not a pass: fixtures need a `result`, a `game_appearances` row and a `match_format`. Reading one row of a split season can pass on the bug (use `grade_total()`).

## How to verify a change here

Repeatable audits (re-run when adding a per-game read):
- Player scoping: extract every triple-quoted SQL block with a per-game table after `FROM`/`JOIN` AND a `JOIN players <alias>`; flag any alias with no `<alias>.organisation_id` in the block. Read CTEs too.
- "Ours" function audit: read whole function bodies for `:pid` plus a per-game table and no org reference (grepping SQL text flags correct code whose filter arrives via an interpolated `extra`). Found 13 in `aggregations.py` plus `player_formats`, `get_player_captain_stats`.
- Season-org audit: flag per-game SQL blocks testing a seasons alias' `organisation_id` without `home_org_id`.
- CARRIED audit: walk every `ForeignKey("players.id")` in `models/db.py` against the merge body (reported 41 unmerged).

Suites (`backend/verification/`, real Postgres, shipped route bodies, control run must fail):
- `verify_merge_carry.py`: old merge leaves the keeper 2 of 7 innings; breaking an `ALLOWED_DELETES` entry or dropping a table off `CARRIED` must fail; row count must fall by exactly the genuine duplicates.
- `verify_shared_fixture_stats.py`: control fails on Juniors returning senior runs.
- `verify_player_season_fold.py`: control fails on 2 rows for 2025/26.
- `verify_association_backfill.py`: neutered phases fail, `commit` ignored fails, ambiguity guard removed shows a side picked. Deadlock is not reproducible single-threaded; the suite pins the fix structurally.
- `verify_match_coverage.py` and the competitions suite for the grouping trigger. Member leak: two clubs, one shared fixture.
- `verify_user_access.py` (124 checks): full access by default, only the Primary Admin or a Super Admin locks, each of the six modules grants exactly its own capabilities, a locked person cannot act in a linked club, a switched-in admin cannot manage the linked club's users, the Primary Admin cannot be removed or edited by another admin, the boot resync, and the real route table. also View versus Manage on the real gates, prerequisites, the item catalogue and the BetterSelect route table (an item reaches only its own routes plus the shared reads). Control against the commit before each release: 21 pass and 39 fail for module locks; for per menu item access it reports the missing mode and column as failures without crashing. `audit_route_access.py` fails on an undeclared signed-in route. Browser: `frontend/verification/verify_user_access_browser.mjs` (76 checks; control 10 pass, 10 fail for items), which also logs console and page errors because a render error is caught by the app's error boundary and is not an uncaught page error. Harness traps: the club passed to a route body must not be an ORM object (a rollback after a refusal expires it); give `users.failed_login_count` its database default, which `create_all` omits.
- Harness: ORM-built tables, views from the migrations; smoke-execute every patched read scoped and unscoped (caught "missing FROM-clause entry for table g" in captain by-season CTEs, which need no clause).

## Operator commands and scripts

- `python -m app.scripts.purge_foreign_members [<org_id>|all] [--apply] [--delete]`: clears member rows pointing at other clubs' players. Dry run by default; archives unless `--delete`. Rows with a payment, role, qualification, committee term, hours, family link or roster shift are reported and left alone. Once clean: `ALTER TABLE fee_members VALIDATE CONSTRAINT fk_fee_members_player_same_org`.
- `python -m app.scripts.backfill_all_associations [--apply] [--no-api] [--org <id-or-slug>] [--concurrency N]`: groups every club's grades into competitions. Dry run by default.
- `python -m app.scripts.undo_player_merge <org-id-or-slug> <merge-log-id>... [--apply] [--by name]`: the Admin Undo button with a dry run. Runs the shipped `undo_merge`, so it moves back only what the merge logged; games synced after the merge stay on the kept player. Refuses a log that is already undone, another club's, or one with a newer live merge on the same players. Check: `verification/verify_undo_player_merge_script.py`.
- `python -m app.scripts.diagnose_player_merge <org-id-or-slug> "<name>"` (read only): for a player gone from the club with nothing on Merge History. Shows the club's players of that name, merge_logs naming them under ANY org (the screen only reads the club's own `org_id`), audit entries (`auto_merge_hand_added` is the post-sync merge nobody clicked) and name aliases.
- `python -m app.scripts.audit_player_games <org|auto> <player-id>` (read only) and `repair_misattributed_games` (dry run by default, `--apply --expect N --by`, undo with `--restore AUDIT_ID`): for a record holding games CA does not credit to them. See data-sources-and-sync.
- `python -m app.scripts.merge_player_pair <org-id-or-slug> <keep-id> <remove-id> [--apply] [--by name] [--allow-shared-games]`: one named pair through the shipped `_merge_players_core`, with a report first. For a person held under several CA profiles, including a redacted `********` row the Manual Merge screen cannot find by name. Refuses a pair that appears in the same game (two people) unless told. Undo with `undo_player_merge`. Check: `verification/verify_merge_player_pair_script.py`.
- `python -m app.scripts.inspect_association_sources`: read-only; do the association id spaces agree, and how many Directory clubs play in one association.

## Open follow-ups

- `seasons.organisation_id` shape remains in the yearbook generator, fantasy engine and some admin tools.
- Grade-scoped, finals-only and captain-only board branches still count their own rows, not `_matches_played_cte`.
- Career size for a player at two synced clubs (scoped vs unscoped path) is a product decision.
- Players, Accounts, Directory and Comms Lists show different counts until the Clubhouse "join the data" step.
- Season-alias dedup (to merge overlapping legacy and per-club players) is unbuilt.
- A both-synced match gives the second club no row of its own (shared `games.id`): known limitation.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-XCLUB-1] v7.32.1 calls `WHERE s.organisation_id = :org` "already correct" (yearbooks, iq_trends, iq_selection) | v9.62.0 says never use it for a per-game "ours" test and lists yearbook/fantasy as still having it | they differ by read shape (season-aggregate vs per-game) | "Cross-Club Player Over-Count Fix"; "A FIXTURE BELONGS TO BOTH CLUBS" | keep both, read by shape.
- [FLAG-XCLUB-2] v9.53.10 and v9.53.11 list the career header and season table counting every game as "noticed, not fixed" | v9.53.12 applied `_club_game_clause` to every player read and asserts they agree | superseded | "seasons drawn two and three times over" (v9.53.10, v9.53.11, v9.53.12 sub-rows) | retire.
- [FLAG-XCLUB-3] The nine tables in 142, the 02:30 Perth time and the five-pass bound come from the archive | `GROUP_CLUBS_PER_RUN = 40` and migrations 060, 062, 067, 142, 143, 167, 169, 223 exist; the rest not re-checked | "Super Admin Club Delete"; "Grouping is a job" | verify.
- [FLAG-XCLUB-4] `services/org_merge.py` mentions `_resolve_org_grade`/`_resolve_org_player` | not in this archive | may carry more per-club id rules | verify if merging organisations.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| Module-locked club users (v9.121.0) and per menu item access (v9.122.0), migration 344, archive only | rules extracted | Rules 53 to 65 |
| NEVER DELETE OR OVERWRITE WHAT A CLUB TYPED IN BY HAND (v9.68.2), L1771-1826 | rules extracted | Rules 1 to 8 |
| A FIXTURE BELONGS TO BOTH CLUBS (v9.62.0), L2996-3111 | rules extracted | Rules 9 to 16 |
|   sub: What Shoalwater Bay reported | rules extracted | Rules 12 to 16 |
| A player's seasons drawn two and three times over (v9.53.10), L3428-3893 | rules extracted | Rule 30, Flag 2 |
|   sub: M IS MATCHES PLAYED. INN IS INNINGS (v9.62.2) | rules extracted | Rule 33 |
|   sub: Grouping is a job the platform does (v9.62.1) | rules extracted | Rules 34, 35 |
|   sub: The association is already in our own database (v9.62.3) | rules extracted | Rules 35 to 38 |
|   sub: A live dry run needs the real cost (v9.62.4) | rules extracted | Rule 40 |
|   sub: The Club Directory closes what the sync alone cannot (v9.62.5) | rules extracted | Rules 36, 37 |
|   sub: A live run at concurrency deadlocked (v9.62.6) | rules extracted | Rule 39 |
|   sub: The grade leaderboard and the profile under it (v9.53.13) | rules extracted | Rule 32 |
|   sub: One rule for "this game is ours", on every player read (v9.53.12) | rules extracted | Rules 10, 17 |
|   sub: The same year counted twice, and another club's matches with it (v9.53.11) | rules extracted | Rule 31 |
| Cross-club member leak (Aug 2026), L9022-9079 | rules extracted | Rules 23 to 25 |
| The shared-game rule: scope the PLAYER, not just the game (v9.11.1), L9080-9136 | rules extracted | Rules 17 to 22 |
| Super Admin Club Delete, soft-delete + FK cascade fix (Jul 2026), L12800-12811 | rules extracted | Rules 41 to 43 |
| June 2026 Cross-Club Player Over-Count Fix (v7.32.1), L12839-12865 | rules extracted | Rules 22, 26 to 29, Flag 1 |
| June 2026 Cross-Club Grade Collision Fix (v2.16.1), L12866-12881 | rules extracted | Rules 26, 27 |
47. A hand-added player merges into their synced record on their own (`services/hand_added_merge.py`, after every sync) only when ALL hold: no CA/PlayHQ/CricketStatz id or import and no login on the hand-added record, no cricket of its own anywhere, a twin with a CA id that has played only in the club's latest season, one shared full name that no other club player has, and the pair not in `merge_pair_ignores`. It goes through `admin._merge_players_core` (undoable, `CARRIED`), never a second merge path, and `_merge_players_core` needs a `uuid.UUID` org id, not the string sync holds. Anything less clear stays on the merge screen.
- Undoing a merge re-creates the removed player with a raw INSERT that skips `protect_new_player`; `protect_restored_player` re-hides it (by participant id, or because the kept row is hidden). Any new code that creates a `players` row with a participant id must call `protect_new_player`. `verification/verify_privacy_survives_sync.py` covers sync, rebuild, re-pull and undo-merge.
- A person's removal request is enforced IN THE DATABASE: BEFORE INSERT and BEFORE UPDATE triggers on `players` (`player_privacy_enforce`, in `services/player_privacy_ddl.py`) look the row's participant id up in `player_privacy_suppressions` and force `is_public` false and the marker set, so no creator or edit can leave a suppressed person visible. They force, never raise. `restore_public` must delete the suppression BEFORE it switches rows back on. A row with no participant id (hand-typed, imported) is matched on NAME: the suppression keeps `names` (keys from `privacy_name_key`: lower-case words, sorted; two words or more, each two letters or more, so a surname or an initial never matches), and a matching row is held with `privacy_hidden_by = 'name-match'` until a club admin releases it (`POST /players/{id}/privacy-release`, which sets `privacy_name_cleared_at`). Only a name hold can be released by a club; a person's own request never can. A hold the trigger placed is lifted by the trigger when the row no longer matches. Downgrade drops the triggers before the columns.
- A person's data access request is answered with `services/player_data_report.py` (PDF) through Super Admin only routes in `routers/privacy_requests.py` (`/club-admin/super/privacy/...`, screen `SuperPrivacyRequests.jsx`). It prints the person's own details, never another person's (family links are counted, not named), never free-text notes, and counts fee records without amounts. A new table that points at a player is picked up from the catalogue and listed by a readable name; give it a label in `_RECORD_LABELS`. Hiding a person is still the `hide_player_at_request` script, not a button.
