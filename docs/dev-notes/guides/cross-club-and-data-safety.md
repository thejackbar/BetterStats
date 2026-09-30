# Guide: Cross-club data leaks, shared fixtures and never deleting a club's own work

**Read this before** (this guide holds the rules whose breach leaks another club's data or destroys a club's hand-entered work):
- Writing or editing any SQL that reads `batting_innings`, `bowling_spells`, `fielding_stats`, `game_appearances`, `partnerships`, `fall_of_wickets`, `bowler_wickets`, `player_season_stats` or `player_season_grade_stats` and attributes rows to "our" club.
- Deciding "is this game ours" or "what kind of grade is this" (`seasons.organisation_id`, `grades`, `resolve_scope`, `resolve_season_filter`, `club_game_sql`, `_club_game_clause`, `club_grade_rows`).
- Touching `sync.py` player/grade/season identity (`_resolve_org_player`, `_resolve_org_grade`, `grassroots_id`, `uuid5(org, guid)`), or merge code (`_merge_players_core`, `undo_merge`, `merge_carry.CARRIED`).
- Adding any `DELETE` or `sa_delete` near `manual_*` tables, a season or grade delete, a Full Rebuild, an import undo, or a club delete/archive.
- Reading a `players` row from a `fee_members` row (Directory, fees, comms) or enrolling people from `game_appearances` (`recompute_fee_match_days`).
- Symptoms: a career or season table drawn twice or three times, a Players-list count that differs from the profile, an opponent appearing as our member, a Juniors filter returning senior matches, another club's phone or email in a Directory, a club delete that "did nothing", a merge that lost half a career, a second club showing only its unique grades.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/cross-club-and-data-safety.md`. Grep hints: `NEVER DELETE OR OVERWRITE`, `A FIXTURE BELONGS TO BOTH CLUBS`, `seasons drawn two and three times`, `M IS MATCHES PLAYED`, `Grouping is a job`, `already in our own database`, `deadlocked writing`, `grade leaderboard and the profile under it`, `this game is ours`, `same year counted twice`, `Cross-club member leak`, `shared-game rule`, `Super Admin Club Delete`, `Cross-Club Player Over-Count`, `Cross-Club Grade Collision`.

**Related guides**: `stats-figures-records-and-filters` (GradeScope, the club default filter, competitions, match coverage; the same scoping rules apply to every board), `data-sources-and-sync` (sync architecture, Full Rebuild, per-club ids), `cricketstatz-import` (`merge_carry`, `hand_edited_games`, import undo), `imports-manual-entries-and-data-tidy` (manual entries, undo/snapshots, season and grade merges), `clubhouse-people-roster-fees` (fee members, Directory), `betteriq` (per-game reads in `iq_*`), `club-directory-onboarding-and-admin-shell` (self-serve registration, club archive).

## Standing rules

**A. Hand-entered work is never deleted (owner's standing rule, set after a merge deleted half a player's career)**

1. A manual game, its innings and a hand-typed correction are the club's own work. A function may ADD to them and MOVE them. It may remove or replace only what it wrote itself, never what a person wrote. Reason: there is no upstream to re-pull them from.
2. A merge MOVES a record, never deletes one. `_merge_players_core` once reached no `manual_*` table, and every one is `ON DELETE CASCADE` on `players.id`, so removing the merged-away player destroyed their whole manual and imported career. `services/merge_carry.CARRIED` is the list; a table that records what a player DID belongs on it. The same list serves the undo (`merge_logs.carried_row_ids`).
3. An import replaces only what that import wrote. `cricketstatz_import.import_match` refreshes a match it created (matched on `cricketstatz_match_id`). `hand_edited_games` reads `manual_edit_logs` (the import writes none): any un-undone row means a person edited it, so the import skips the match and says so. An edit later undone does not count.
4. A Full Rebuild deletes from `games`, never `manual_games`. It re-pulls from Cricket Australia and a manual game has nothing to re-pull.
5. Season and grade deletes refuse while a manual game or manual adjustment points at them (`_season_in_use`, `_grade_in_use` in `routers/manual_entries.py`; `_season_in_use` also covers `player_season_stats` and `imported_stats`). Both FKs cascade, so these checks are the only guard.
6. De-duplicating is not deleting. A merge may drop the removed record's row for an innings the keeper already holds (same innings under two identities). It must never drop an innings only one of them had. Collision match on unique keys uses `IS NOT DISTINCT FROM`, not `=`, because part of a key can be NULL (a season adjustment with no grade).
7. The rule is enforced by `verify_merge_carry.py`: it scans `app/` for every `DELETE FROM manual_*` and `sa_delete(Manual*)` and fails on any site missing from `ALLOWED_DELETES` (each needs a stated reason), and asserts every manual table with a `players.id` FK is on `CARRIED`. A new delete must be justified there.
8. When a club has already lost rows this way, say what recovers them: a CricketStatz import re-writes the same matches (deterministic `cricketstatz_match_id`, upsert), onto the one kept record. Hand-typed history has no such path.

**B. A fixture belongs to both clubs**

9. A CA match between two clubs that both sync is ONE `games` row. Its `grade_id`, and so `season_id`, points at whichever club synced it first. That club does not own the fixture. Both clubs' scorecards hang off it and both clubs' statistics must count and classify it. (Reported four times: second club's Games list, player's own club as opposition, season table drawn repeatedly, career counting another club's matches, then Shoalwater Bay.)
10. Never decide "is this game ours" with `seasons.organisation_id`. Ownership is `services/club_grades.club_game_sql`: `v_effective_games.organisation_id` is us OR we are `home_org_id`/`away_org_id` (migration 167, both indexed). `aggregations._OURS_GAMES` and `records._OURS_GAMES` are that one string. `aggregations._club_game_clause` is the player-scoped sibling (same predicate, mirrors `iq_trends._ours_clause`). Do not write the test as an OR of season org and the two sides in a hand-rolled way (it measured slower); use the shared string.
11. Never decide "what kind of grade is this" from a `grades` row your own club owns. `club_grade_rows` enumerates the club's own grades PLUS every grade row its own games sit in, and resolves each to the club's own answer by NAME, folded through `grade_merge_logs`.
12. A category (grade type) filter is an exclusion, so it is only as good as its enumeration. Widen the enumeration, never relax the exclusion. A grade the filter cannot name is kept (a grade-less manual game or import residual is not known to be junior).
13. A merged-away grade spelling must read as the grade that was kept: `grade_labels._apply_alias_fold` registers the canonical's confirmed answer under the alias key in all three name maps (shared fixtures are exactly where CA's older name turns up).
14. Grade competition/association for a foreign grade resolves to OUR answer: `club_grade_competitions` (never the foreign grade's own `competition_id`). The association fallback applies only to a name we have never held; a grade we hold under that name gets the answer we gave it, ungrouped included.
15. A season filter needs `resolve_season_filter(..., include_shared=True)` to reach the other club's row for the same real season (CA season GUID first, then year, then name). It is opt-in: pass it only where the read is ALSO guarded by the club's own players or by the ownership predicate, otherwise a season-list-only guard reaches another club's rows.
16. The brief for a board with a picked filter: bring the boards up to the profile, never the profile down to the boards (150 matches was right, 106 was the leak).

**C. Scope the PLAYER, not just the game**

17. `games -> grades -> seasons -> organisation_id` says the game is in our competition. It says nothing about whose player a row belongs to. Any read of `batting_innings`, `bowling_spells`, `fielding_stats`, `game_appearances`, `partnerships`, `fall_of_wickets` or `bowler_wickets` that attributes a row to our side must ALSO scope `players.organisation_id`.
18. `is_club_innings` is set per club, so a shared game's one row carries BOTH clubs' partnerships as TRUE. `WHERE game_id = X AND is_club_innings IS TRUE` is not a club filter.
19. Partnerships: scope ONE batter (both are in the same innings so the same club). Scoping both would drop a stand involving a teammate whose `players` row sits under another club. Exception: `_combinations` scopes both (pairs come from appearances on one game, where ours can pair with theirs). `bowler_wickets`: scope the bowler, leave the fielder.
20. Check CTEs, not only `JOIN players`. `_captaincy`'s `scores` CTE summed the OPPOSITION's runs into "average team score under this captain" with no join at all.
21. Deliberately left unscoped (verified safe, do not "fix"): `aggregations.get_player_partnerships` and `iq_trends.bowler_deep_dive` (anchored on `:pid`), `yearbooks._generate_narrative_core`, StatLab `derived_best_partnership_pair`, `_partnership_aggregates_pair`, `_century_partnerships_pair`, `_bowler_fielder_combo` (one side scoped), and `iq_team._team_fielding`'s combo query and `_batting_pairs` (partner alias).
22. Season-aggregate reads of `player_season_stats` are a different shape: read `v_effective_player_season_stats` (migration 060 only emits a row when `player.organisation_id IS NULL OR player.org = season.org`), or join `seasons s` and filter `s.organisation_id`. Never sum `player_season_stats` filtered only by `players.organisation_id`.
23. Any read-through from a member to its player joins on `p.organisation_id = fm.organisation_id` and reads the org-scoped result (`directory.list_people` uses `our_player_id`, never `fm.player_id`). A link that does not resolve in the club must not tag the person a Player nor carry a `player_id` to the frontend.
24. Fee/member enrolment loads the appearing players org-scoped FIRST, then filters `game_appearances` to them (`fees.recompute_fee_match_days`). Never enrol "every appearance on our games". The comment "only our club's players have rows" was false.
25. Migration 223 makes the leak unrepresentable: composite FK `fee_members (organisation_id, player_id)` to `players (organisation_id, id)`, added NOT VALID (enforced on new writes). Still filter on read.

**D. Per-club identity (seasons, players, grades)**

26. CA participant, grade and season GUIDs are shared across clubs. Never create or look up by a global `session.get(Player|Grade, raw_guid)` in sync. Use `sync._resolve_org_player` and `_resolve_org_grade`: look up by `(org, grassroots_id)`, mint `id = uuid5(org, guid)` only when the raw GUID is already a row in another club, else keep the raw GUID (so single-club orgs are byte-for-byte unchanged). `players.id` and `grades.id` no longer equal the CA GUID for per-club rows; the raw GUID lives in `grassroots_id`.
27. The raw GUID is what every Grassroots API call must use (per-grade stats `gradeId`, `get_grade_matches`, `iq_opponent` grade lookups, `ladders.py`, `iq.opponent_ladder`): `COALESCE(grassroots_id, id)`. Scorecard `grade.id` maps to the per-club id via `grade_id_by_guid`; scorecard `participantId` maps via `_team_pid`/`pid_by_guid`.
28. `undo_merge` must set `grassroots_id` (= `id::text`) on the re-created player, or the next sync mints another per-club duplicate.
29. Do NOT merge a legacy-GUID duplicate into a per-club record when their seasons overlap. MyCricket and PlayHQ give different season GUIDs to one real season, and `merge_players` dedupes by raw `season_id`, so it moves the older seasons and the career reads 86 = 56 + 30. Recovery is undo-merge. A merge is only safe for genuinely disjoint registrations.
30. A season's fold, not a drop: `_SEASON_FOLD_CTE` folds every season onto the viewing club's own row for that year, then through any active merge. Org-filtering the games instead removes matches and leaves the table summing to less than the header. A year the club has no row for folds to itself. A historical bundle (`_HISTORICAL_BUNDLE_MATCH_CAP`) is deliberately left unfolded (folding a real season into it sends it into the lump). Key season rows by `season_id`, not `season_name`.
31. `get_player_team_breakdown` is its own attribution pass: `_canonical_season` folds alias, then the club's own row for that year, then back through any merge. BOTH the scorecard side and CA's `player_season_grade_stats` side must be scoped by the season's organisation; scoping one side breaks `max(held, claimed)` self-healing. A per-grade manual correction is applied to the cell last (clamped at zero) and excluded from `season_aggregate`, or the gap heuristic counts it twice.
32. The grade leaderboard (`use_psgs_path`) sums `player_season_grade_stats` scoped through `seasons.organisation_id`, keeps `max(held, claimed)` (`grade_games` floor; `grade_scoped_games` narrows games first), so it reads exactly what the profile grid reads.

**E. One definition of matches played**

33. M means matches PLAYED, INN means innings. `_matches_played_cte` is the one definition (unions batting, bowling, fielding and bare `game_appearances`, same four sources as `_scoped_games_played`), narrowing games FIRST. It supplies the figure, never the qualification (LEFT JOIN for the number only, or a batting board fills with non-batters). `records.most_matches` `use_game_level` has the fourth (`game_appearances`) arm too.

**F. Association backfill and competition grouping (data derived from our own tables)**

34. Grouping is a platform job, not a button a club must find. It is NOT hooked to `sync_organisation` (a club that played nothing never reaches it via `_record_idle_run`): `competition_grouping.maybe_group_club` runs from the nightly `jobs/scheduler.group_all_organisations` (02:30 Perth) over `auto_sync.eligible_clubs`, own try/except and own session. `GROUP_CLUBS_PER_RUN = 40` (the batch script owns the backlog).
35. It is a job that finishes: `run_grouping` reports `seasons_unresolved`, and the trigger fires only when the current gap is GREATER than the last completed run's residual. A run in flight is never doubled (`running_run_id`). The button stays as the escape hatch.
36. `games.raw_payload` is a dead column (nothing writes it), so the association cannot be recovered from stored payloads.
37. Own-data phases (`services/association_backfill.py`): (a) a CA grade GUID is competition-wide, so an association any club holds against a guid applies to every row carrying it; (b) a club's own grade NAME is its own competition (folded through `grade_merge_logs` and the sponsor-suffix strip, the same two rules as `club_grade_rows`); (c) `propagate_from_directory`: a club the Directory shows in EXACTLY one association has its whole gap filled, matched by NAME never by the Directory's id (id spaces disagree). Target id is reused if anything already calls it that, else minted as `uuid5` in a namespace of its own; a name that already means two ids is left alone.
38. Every phase refuses to guess: `HAVING COUNT(DISTINCT association_id) = 1`. A wrong association files a club's matches under a competition it never played in, worse than a missing one. Every statement is `WHERE association_id IS NULL`, so nothing is overwritten and a second run writes nothing. `grades.association_id` is TEXT, so cast arrays to `text[]`, not `uuid[]`.
39. `propagate_all` loops until nothing writes (bounded at five passes). The API phase collapses as it goes: each answer is applied across EVERY club holding that guid, and each season is re-checked right before its call.
40. `apply_associations` is ONE `UPDATE` via `unnest` (a per-guid loop deadlocked under concurrency, `DeadlockDetectedError`), and the write sits INSIDE the same semaphore as the fetch. A bounded retry in a FRESH session is the backstop.
41. A dry run must measure before it rolls back: `propagate_all(commit=False)` reuses the real loop so the reported gap is accurate. `plan_api_phase` gives the real CA call count from held data (a lower bound; it assumes CA answers every season), computed after the SQL phases.

**G. Club delete and archive**

42. Club "delete" in the UI is a soft archive: `organisations.archived_at` (migration 143), `POST /club-admin/super/clubs/{id}/archive` and `.../restore`. Archiving does NOT touch `is_active`. `GET /club-admin/super/clubs` hides archived clubs unless `?include_archived=true`. Hard `DELETE /club-admin/super/clubs/{id}` (`delete_club`) refuses with 409 unless the club is already archived.
43. The DB schema can drift from the ORM: `partnerships.game_id` was not `ON DELETE CASCADE` live though `models/db.py` declared it, so the club delete rolled back silently. Migration 142 reconciles the FK on `batting_innings`, `bowling_spells`, `fielding_stats`, `bowler_wickets`, `game_appearances`, `fall_of_wickets`, `partnerships`, `milestones`, `fee_match_days`: build `NOT VALID`, then `VALIDATE CONSTRAINT` separately, check `pg_constraint.confdeltype` first (no-op on re-run via the `main.py` mirror). Do not trust ORM `ondelete` for pre-Alembic tables.
44. `sync.find_matching_organisation(..., include_archived=True)` defaults to including archived rows (so `upsert_organisation` reuses an archived row rather than minting a second). Self-serve `search`, `/prepare` and `/submit` pass `include_archived=False` so an archived club reads as available, and `/submit` clears `archived_at` on reuse.

## Traps and failure signatures

- Season table shows "2025/26" twice or "2022/23" three times, rows sum exactly to the career header: not double counting, a shared fixture filed under the first club's season row. Fix is the fold (rule 30), never dropping games.
- Players-list M 106 vs profile M 150, Juniors filter returns senior matches: boards scoped by `s.organisation_id` and `resolve_scope` enumerating only the club's own grades (rules 10 to 12, 15). 127 minus 21 innings equalled 106 exactly.
- Board reads 61 vs grid 60 (or 9 vs true 6): `player_season_grade_stats` unscoped, or a manual correction not reaching the board (rules 31, 32).
- Opponent players appear in Directory / fee members with real email, phone and photo: `recompute_fee_match_days` enrolled all appearances, plus an unscoped `players` join (rules 23 to 25).
- Career reads double (7 became 63; 86 = 56 + 30): a global `session.get(Player, guid)` or a merge across overlapping seasons (rules 26, 29).
- Second club shows only its unique grades: global grade PK, first club owns the shared grade row (rule 26).
- Opposition's best stand in our match review: `is_club_innings` is per club (rule 18).
- Club delete "did nothing" and the transaction rolled back: FK cascade drift (rule 43).
- Archived club rejected as "already registered": missing `include_archived=False` at the self-serve call sites (rule 44).
- Exclusion filter passes another club's grade at all categories: the grade was never in the exclusion list (rule 12).
- Second-club cutover: after deploying per-club ids, Sync Now mints per-club rows and moves aggregate seasons; game-level rows only re-attach on a Full Rebuild (the game-level sync skips already-synced games), then merge the duplicate if seasons are disjoint.
- Audit false positives: match a per-game table only after `FROM`/`JOIN` or `st.batting_innings` (a COLUMN on `player_season_stats`) floods the audit.
- A check reading zero is not a passing check: fixtures need a `result` (by-venue drops NULL), a `game_appearances` row (`player_game_ids` reads appearances) and a `match_format` (else `not_recorded`).
- A check that reads one row of a split season can pass on the bug (dict collision); sum across every row with the label (`grade_total()`).
- A junior-suggesting name is needed to prove a merged-away grade reads as ours; a senior-suggesting name passes on an unclassified fall-through.

## How to verify a change here

Repeatable audits (re-run when adding a per-game read):
- Player scoping audit: extract every triple-quoted SQL block, keep those with a per-game table after `FROM`/`JOIN` AND a `JOIN players <alias>`, flag any alias with no `<alias>.organisation_id` in the block. Also read CTEs (rule 20).
- Function-level audit for "is this game ours": read whole function bodies for `:pid` plus a per-game table and no org reference of any kind (grepping SQL text alone flags already-correct code whose filter arrives through an interpolated `extra`). It found 13 reads in `aggregations.py`, plus `player_formats` and `get_player_captain_stats`. `player_formats`'s docstring wrongly argued no filter was needed (true of the PLAYER, not the GAME); corrected in place.
- Season-org audit: extract every triple-quoted SQL block with a per-game table after `FROM`/`JOIN`, flag any that tests a seasons alias' `organisation_id` without naming `home_org_id`. It reported 89 blocks; the club-facing stats reads are covered.
- Manual-delete audit: `verify_merge_carry.py` (rule 7). CARRIED audit: walk every `ForeignKey("players.id")` in `models/db.py`, resolve to table and ORM class, flag any the merge body names neither of (reported 41).

Suites (all `backend/verification/`, real Postgres, shipped route bodies; each has a control run that must fail on the named behaviour):
- `verify_merge_carry.py`: control (old merge) leaves the keeper with 2 of 7 innings; breaking an `ALLOWED_DELETES` entry or dropping a table off `CARRIED` must fail. Also asserts total row count falls by exactly the genuine duplicates.
- `verify_shared_fixture_stats.py`: control fails on Juniors returning senior runs and boards reading 3 where the profile reads 7. Includes the format axis on a grade we do not own and the merged spelling read as ours.
- `verify_player_season_fold.py`: control fails on 2 rows for 2025/26 and 3 for 2022/23; bundle checks must still pass.
- `verify_association_backfill.py`: neutered propagation phases fail 11, `commit` flag ignored fails 3, removing the ambiguity guard must show the phase picking a side. Deadlock cannot be reproduced single-threaded, so the suite pins the structural fix (one call with several guids writes all).
- `verify_match_coverage.py` and the competitions suite for the grouping trigger (the SYNC is what calls it, structurally).
- Cross-club member leak: reproduce with two clubs, one shared fixture, both sets of appearances on it.
- Harness gotchas: build tables from ORM models, not by hand; pull views straight out of the migrations that define them; scope-changing edits need a smoke pass that executes every patched read scoped and unscoped (it caught "missing FROM-clause entry for table g" in captain by-season CTEs, which need no clause since they are narrowed to `captain_games`).
- Platform-scale timing was measured for these scopes (a few ms per read); do not swap the ownership predicate for an OR of season org and sides.

## Operator commands and scripts

- `python -m app.scripts.purge_foreign_members [<org_id>|all] [--apply] [--delete]`: clears member rows pointing at other clubs' players. Dry run by default. Archives (reversible) unless `--delete`. Rows with anything attached (payment, role, qualification, committee term, logged hours, family link, roster shift) are reported and left alone. After a clean database: `ALTER TABLE fee_members VALIDATE CONSTRAINT fk_fee_members_player_same_org`.
- `python -m app.scripts.backfill_all_associations [--apply] [--no-api] [--org <id-or-slug>] [--concurrency N]`: groups every club's grades into competitions. Dry run by default; `--no-api` is SQL only.
- `python -m app.scripts.inspect_association_sources`: read-only, no writes, no upstream call. Reports whether `grades.association_id` and Directory association ids share a namespace (found 0 of 3 ids shared, all 3 names shared) and how many Directory clubs play in exactly one association. (The archive says `scripts/inspect_association_sources.py`; it now lives in `app/scripts/`.)
- After deploying per-club ids to an affected second club: Sync Now, then Full Rebuild for game-level consistency.
- Recovery for a merge that lost a CricketStatz career: re-run the CricketStatz import (rule 8). Undo-merge for the overlapping-seasons merge (rule 29).
- No migration or re-sync is needed for the read-side scoping fixes; figures correct on the next page load.

## Open follow-ups

- `seasons.organisation_id` shape still in the yearbook generator, the fantasy engine and several admin tools (none a club-facing stats figure).
- `records.py` partnership leaderboards and similar can still surface a stand by two players of ours who never batted together for us (only noted in the wider archive, verify).
- Grade-scoped, finals-only and captain-only branches of the boards still count their own per-innings rows instead of `_matches_played_cte` (each needs its own reading: finals played, matches captained).
- Career header vs per-scoped-path career size for a player at more than one synced club is a product decision (which reading a club wants).
- Squad-level counts: Players screen (`players`), Accounts (`fee_members` per season), Directory (all `fee_members` plus org players) and Comms Lists (`comms_contacts`) legitimately differ until the Clubhouse "join the data" step is done.
- Season-alias / migration-season dedup (needed to merge legacy and per-club players with overlapping seasons) is unbuilt.
- A match between two both-synced clubs gives the second club no row of its own (shared `games.id`): known limitation, by design of rule 9.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-XCLUB-1] v7.32.1 says queries filtering `WHERE s.organisation_id = :org` were "already correct" (yearbooks, iq_trends trajectory, iq_selection) | v9.62.0 says never decide "ours" with `seasons.organisation_id` for a per-game read, and lists the yearbook, fantasy and admin tools as still having that shape | the two differ by read shape (season-aggregate vs per-game), so apply the season-org test only to `player_season_stats` aggregates | "June 2026 Cross-Club Player Over-Count Fix" and "A FIXTURE BELONGS TO BOTH CLUBS" | keep both, read by shape.
- [FLAG-XCLUB-2] v9.53.10 and v9.53.11 list "career header and season table still count every game whatever club's fixture" as noticed, not fixed | v9.53.12 then applied `_club_game_clause` to every player read and asserts header, season table and grid agree | superseded | "A player's seasons drawn two and three times over" (sub-rows v9.53.10, v9.53.11, v9.53.12) | retire the two noticed-not-fixed items.
- [FLAG-XCLUB-3] v9.53.11 says the grid's total needs attribution scoping "so max(held, claimed) is self-healing", v9.53.13 says the leaderboard needs the same `max` | both hold; not a conflict, but the `max` rule is a separate design from the career-total rule in the stats guide | same section | keep.
- [FLAG-XCLUB-4] Rule 43 says 142 was "mirrored in `main.py`" and lists nine tables | verify the current table list in `alembic/versions/142_fix_game_stat_fk_cascades.py` before adding a tenth table | "Super Admin Club Delete" | verify.
- [FLAG-XCLUB-5] Grouping sections cite thresholds and counts (`GROUP_CLUBS_PER_RUN` 10 to 40, five-pass bound, 02:30 Perth) | `GROUP_CLUBS_PER_RUN = 40` confirmed in `app/jobs/scheduler.py`; the 02:30 and five-pass values not re-checked | "Grouping is a job" and "association is already in our own database" | verify before relying on the numbers.
- [FLAG-XCLUB-6] The archive says `games.raw_payload` is written by nothing | `superseded_ddl.py` still selects it (NULL for manual) and `clone_demo_club.py` copies it | still consistent | keep, but re-grep before designing anything on it.
- [FLAG-XCLUB-7] Migration numbers 060, 062, 067, 142, 143, 167, 169, 223 | all confirmed present under `backend/alembic/versions/` | none | keep.
- [FLAG-XCLUB-8] `services/org_merge.py` exists in code and mentions `_resolve_org_grade`/`_resolve_org_player` | not covered by this archive | may carry further per-club id rules | verify if merging organisations.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| NEVER DELETE OR OVERWRITE WHAT A CLUB TYPED IN BY HAND (v9.68.2), L1771-1826 | rules extracted | Standing rules 1 to 8, How to verify (manual-delete audit), Traps |
| A FIXTURE BELONGS TO BOTH CLUBS (v9.62.0), L2996-3111 | rules extracted | Standing rules 9 to 16, Traps, How to verify (season-org audit, shared-fixture suite), Open follow-ups |
|   sub: What Shoalwater Bay reported, and why it read as two unrelated bugs | rules extracted | Rules 12 to 16, Traps bullets 2, 10, 13 |
| A player's seasons drawn two and three times over (v9.53.10), L3428-3893 | rules extracted | Rules 30, 33, Traps bullet 1, Flags 2 |
|   sub: M IS MATCHES PLAYED. INN IS INNINGS (v9.62.2) | rules extracted | Rule 33, Open follow-ups |
|   sub: Grouping is a job the platform does (v9.62.1) | rules extracted | Rules 34, 35 |
|   sub: The association is already in our own database (v9.62.3) | rules extracted | Rules 36 to 39, Operator commands, Flag 5 |
|   sub: A live dry run needs the real cost (v9.62.4) | rules extracted | Rule 41 |
|   sub: The Club Directory closes what the sync alone cannot (v9.62.5) | rules extracted | Rules 37, 38, Operator commands |
|   sub: A live run at concurrency deadlocked (v9.62.6) | rules extracted | Rule 40, How to verify |
|   sub: The grade leaderboard and the profile under it (v9.53.13) | rules extracted | Rule 32, Traps bullet 3 |
|   sub: One rule for "this game is ours", on every player read (v9.53.12) | rules extracted | Rules 10, 17, How to verify (function-level audit, smoke pass) |
|   sub: The same year counted twice, and another club's matches with it (v9.53.11) | rules extracted | Rule 31, Traps |
| Cross-club member leak: the opposition were enrolled as our members (Aug 2026), L9022-9079 | rules extracted | Rules 23 to 25, Traps bullet 4, Operator commands, Open follow-ups |
| The shared-game rule: scope the PLAYER, not just the game (v9.11.1), L9080-9136 | rules extracted | Rules 17 to 22, How to verify (player scoping audit) |
| Super Admin Club Delete, soft-delete + FK cascade fix (Jul 2026), L12800-12811 | rules extracted | Rules 42 to 44, Traps bullets 6, 7 |
| June 2026 Cross-Club Player Over-Count Fix (v7.32.1), L12839-12865 | rules extracted | Rules 22, 26 to 29, Traps bullets 5, 9, Flag 1 |
| June 2026 Cross-Club Grade Collision Fix (v2.16.1), L12866-12881 | rules extracted | Rules 26, 27, Traps bullet 6, Open follow-ups |
