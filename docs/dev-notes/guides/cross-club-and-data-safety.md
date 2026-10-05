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
3. An import replaces only what it wrote (`cricketstatz_import.import_match`, matched on `cricketstatz_match_id`). `hand_edited_games` reads `manual_edit_logs` (the import writes none): an un-undone row means a person edited it, so the import skips the match and says so.
4. A Full Rebuild deletes from `games`, never `manual_games`.
5. Season and grade deletes refuse while a manual game or adjustment points at them (`_season_in_use`, `_grade_in_use`, `routers/manual_entries.py`). Both FKs cascade, so these are the only guard.
6. De-duplicating is not deleting: drop the removed record's row only for an innings the keeper already holds, never one only it had. Match unique keys with `IS NOT DISTINCT FROM`, not `=` (a season adjustment with no grade has a NULL key part).
7. Enforced by `verify_merge_carry.py`: every `DELETE FROM manual_*` / `sa_delete(Manual*)` must be on `ALLOWED_DELETES` with a reason, and every manual table with a `players.id` FK on `CARRIED`.
7a. A merge keeps the person too (v9.106.2): `merge_profile.carry_profile` fills the keeper's empty profile columns (photo trio as one unit) before the row is deleted, and the link tables (availability, squads, lineups, nets, family, aliases, fee/comms/CRM links) are on `CARRIED`. `fee_members`, `comms_contacts`, `crm_people` are `_NEVER_DELETE`. A new player-keyed table with a CASCADE or SET NULL FK goes on `CARRIED`; a new `players` column goes in `merge_profile.FIELDS`. Suite: `verify_merge_profile_carry.py` (own database).
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

## Traps and failure signatures

- Season "2025/26" twice, rows sum to the header: fixture filed under the first club's season (rule 30).
- Players M 106 vs profile 150; Juniors returns senior matches (rules 10 to 12, 15). Board 61 vs grid 60 (rules 31, 32).
- Opponents in Directory/fees with contact details (rules 23 to 25). Opposition's best stand in our review (rule 18).
- Career doubled (7 became 63; 86 = 56 + 30) or second club shows only unique grades: rules 26, 29. Cutover: Sync Now mints per-club rows and moves aggregate seasons; game-level rows re-attach only on a Full Rebuild.
- Club delete "did nothing": rule 42. Archived club "already registered": rule 43.
- Audit noise: match a per-game table only after `FROM`/`JOIN` (`st.batting_innings` is a COLUMN on `player_season_stats`).
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
- Harness: ORM-built tables, views from the migrations; smoke-execute every patched read scoped and unscoped (caught "missing FROM-clause entry for table g" in captain by-season CTEs, which need no clause).

## Operator commands and scripts

- `python -m app.scripts.purge_foreign_members [<org_id>|all] [--apply] [--delete]`: clears member rows pointing at other clubs' players. Dry run by default; archives unless `--delete`. Rows with a payment, role, qualification, committee term, hours, family link or roster shift are reported and left alone. Once clean: `ALTER TABLE fee_members VALIDATE CONSTRAINT fk_fee_members_player_same_org`.
- `python -m app.scripts.backfill_all_associations [--apply] [--no-api] [--org <id-or-slug>] [--concurrency N]`: groups every club's grades into competitions. Dry run by default.
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
