# Guide: CricketStatz history import, two-source pairing and the effective views

**Read this before**:
- Touching `services/cricketstatz_*.py` (client, parse, import, awards, ddl), `routers/cricketstatz.py`, `components/admin/CricketStatzImport.jsx` (a panel inside `AdminSync.jsx`).
- Touching `services/match_pairing.py`, `services/superseded_ddl.py`, `manual_games.superseded_by_game_id` / `pair_prefers_import`, or any of the eight `v_effective_*` views.
- Symptoms: a career, record board or hundreds count that is about double for seasons both Cricket Australia (CA) and CricketStatz cover; a leaderboard listing one person twice ("Quinsee, Brad" and "Brad Quinsee"); a merge that halves a career; a club with 3,000+ matches and no honours; "30 sixes in an innings of 8"; an import that looks hung.
- Editing `_merge_players_core`, `services/merge_carry.py`, or the lifespan mirror in `app/main.py` that replays migration DDL.
- Keywords: CricketStatz, `linkreport`, `cricketstatz_match_id`, `stats_source`, `superseded_ddl`, `reconcile_org`, `pair_imported_matches`, `boundary_counts`.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/cricketstatz-import.md`. Grep hints: `linkreport`, `resolve_player`, `earliest of the most recent 999`, `IT IS AN AND`, `NEVER RAN`, `pairing_applied`, `TWO THOUSAND LINES`, `log_statement`, `pg_get_viewdef`, `PER-INNINGS DECISION`, `uq_manual_games_superseded_by_game`, `fours * 4`, `Preston`, `CHANGES OVER AS ITS OWN`, `player_season_grade_stats`, `run_notes_pass`, `stats_source`, `merge_carry`, `classify_note`, `plan_seasons`, `STALL_AFTER_SECONDS`.

**Related guides**: the merge/duplicates guide (`_merge_players_core`, Merge Duplicates); the stats/effective-views guide (`v_effective_*`, record boards, timing, shared fixtures); the sync guide (Full Rebuild triggers pairing); the BetterImport/import-ingest guide (`match_players`); the awards guide (`player_achievements`, award definitions); the migrations/lifespan guide (numbering, mirrors).

## Standing rules

**The importer (fetch and parse)**
1. Every CricketStatz report is `/ss/linkreport?mode=<N>&club=<id>&web=1`, which returns `document.write("<table>...")`. Mode 12 is the match list, `mode=100&match=<id>` is the two-team scorecard, `mode=106` is ball by ball (unused). Unwrap with `cricketstatz_parse.unwrap`.
2. `limit` caps a report at 999 rows. Pull matches season by season. The club page's season dropdown lists every season back to 1860 for every club, so it is a candidate list to probe, never a truth.
3. Read column layouts from the header row (`_column_map`). A 1995 card is `R M 4s 6s` with no balls or strike rate; positional reading files boundaries as balls faced, silently.
4. Read a dismissal clause by clause from each `span.ss_block`'s own how-out marker. Split on the block's OPENING tag: a clause nests its own `ss_howout` span, so a non-greedy match to the first `</span>` loses every name (it once lost all 102 bowler credits).
5. Captain, keeper and duck come from `title=` attributes, never the emoji. Caught behind is derived structurally: the keeper is marked on the fielding side's own batting card.
6. Only our own players get `players` rows. A card carries both sides; minting the opposition is the cross-club leak `purge_foreign_members` exists for. The opposition half lives on `manual_games.extracted_payload`.
7. Identity is CricketStatz's own `playerid`, not the printed name. `manual_games.cricketstatz_match_id` (deterministic) makes a re-import an upsert, not a double.
8. A placeholder is not a person. A card whose batters all read `N/A` is left out (they all resolved to one player and hit `uq_manual_batting_game_inns_player`); the match still imports with result and full card.
9. Commit one match at a time, and clear ALL caches (season, grade, players roster) on rollback. A rollback discards a flushed season/grade while the cache still serves its id, so every later match in that season fails on a dangling FK (one bad card once cost 97 good ones).
10. The record book is captured generically into `cricketstatz_records` (title, headers, rows JSONB, one live copy per club per mode). Never merge it into our computed records; a blended board cannot be checked against either source.
11. An expired CricketStatz subscription answers `Error: Subscription expired`. `unwrap` raises a typed `CricketStatzError` so it is never read as "no matches". Their database is deleted 12 months after expiry.
12. Client behaviour: identifies itself, concurrency 3, delay between requests, 30-minute cache so preview and import share a pull, scorecards are NOT cached (fetched once). Their `robots.txt` disallows `/ss/`; proceeding was a data-portability call. Never enumerate club ids or sweep the site.
13. Grades are created classified: write `category=suggest_category(name)` AND `categories=list(suggest_categories(name))`, and `grassroots_id=None` on season and grade. Otherwise imported juniors sit inside senior careers (migration 228 exists to stop that).
14. Season planning: `plan_seasons` probes EVERY candidate season concurrently (about 1 minute for 167) and keeps the rows; the plan is the work list, ordered oldest first. Never bound the range from record-board dates (top-100 lists can miss a quiet early season) and never stop at a run of empty years.
15. Preview "earliest" is only a floor: the all-time list is capped at 999 matches, so use the minimum year across five record boards and say "back to at least".

**Player matching**
16. `resolve_player` goes through `import_ingest.match_players` (the shared BetterImport pipeline). Raw `ilike` fails because the club stores "Quinsee, Brad" and CricketStatz writes "Brad Quinsee". Only an `exact` result is taken (it already covers middle initials). Anything looser gets its own record and is REPORTED by name pointing at Merge Duplicates; an initial is not an identity.
17. A newly created player is appended to the roster cache, or a second spelling of the same new name mints a second row in one import.
18. A re-import does not repair a club already holding duplicates (`resolve_player` finds its own row by the CricketStatz id first). Use the repair script (below).

**Merge must move, never delete**
19. `_merge_players_core` must carry every table that records what a player did. `services/merge_carry.CARRIED` is the one list shared by merge and undo; `merge_logs.carried_row_ids` is one JSONB blob keyed `"<table>.<column>"`. Every `manual_*` table is `ON DELETE CASCADE` on `players.id`, so an uncarried table is destroyed by the merge. `player_achievements` has no FK, so its rows are orphaned instead.
20. The keeper's row wins a collision, joined with `IS NOT DISTINCT FROM` (a NULL grade is a real key part). Keep integer ids as integers in the JSONB (asyncpg cannot cast a string list to `int[]`). Skip a table that is absent (`to_regclass`), as `player_achievements` and `club_honour_entries` are lifespan-created. Move the import identity onto the keeper if it has none.
21. Recovery for a club a bad merge hit: re-run the import (deterministic ids, upsert). Undoing the merge cannot help for logs written before `carried_row_ids`.

**Two sources: the current design (per-MATCH pairing, migration 293, v9.70.0)**
22. The two sources COMPLEMENT each other: an AND, never an OR. The club's record is the union with duplicates removed per match. Choosing a source per season lost matches the other source alone held (CA 401 vs CricketStatz 473 across five seasons, each with gaps).
23. `manual_games.superseded_by_game_id` pairs an imported match to the synced game that IS that match. `pair_prefers_import` says which half counts. CA wins by default (live, current). The import wins only where the synced game has no scorecard of ours and the imported one does. Everything unpaired from both sides counts. Nothing is deleted; unpairing brings the copy straight back.
24. The scorecard is the identifier, not the date (a two-day match is dated by start in one source and finish in the other). Entry rules: three shared scores at any distance; one shared score plus same club within ten days; same day against same club; two shared scores close together; and a fifth (same club within ten days) only where one side has no card at all.
25. Our own club name is on both sides of every match, so `split_sides` removes our side first (stored opposition wins, club-name test is the fallback). One shared word is not a club: `teams_agree` needs containment or two identifying words, after stripping age groups. Which of OUR sides played (`side_marker`: "2nd-XI", "2nd XI", "1's", "U17") is the one hard no. A grade letter is never read as a team number.
26. A cluster nothing can tell apart is paired off, not refused (v9.70.2 reversed v9.70.0's refusal). Reason: refusing left counts near double; pairing keeps the COUNT right whichever way round. Accepted cost: a mis-attributed fixture, or a lost match where each source alone holds a different one of two identical fixtures.
27. Ties in `assign` are broken by ids so the assignment is stable across runs and process hash seeds. Without it a settled club rewrote 2 rows on every `--apply`.
28. The pass RE-DERIVES and never accumulates: it starts from the data as it stands, clears pairs it can no longer justify, and is idempotent. It runs per season during an import, at the end, after a full sync and a Full Rebuild, once at boot for every club holding an import, nightly (`jobs/scheduler.pair_all_imported_matches`, 02:50 Perth), and on `POST /pairing/rebuild`.
29. Write pairs by clearing every changing row first, then one `unnest` UPDATE. Row-by-row writes hit `uq_manual_games_superseded_by_game` when a game moves between holders and roll back the whole pass.
30. Matching is seconds of CPU: run `assign` via `asyncio.to_thread`, never inline on the event loop (it froze the API and the deploy health check). Hold the boot task in `main._BACKGROUND_TASKS` (a bare `create_task` is garbage collected). Bind card queries to the loaded game ids (`= ANY(CAST(:ids AS UUID[]))`); a players-only bind scanned the whole platform's `batting_innings`.
31. Aggregate level differs from per-innings level. The per-innings views are per match, so a paired synced game steps aside and the import can answer. `player_season_stats` is a season total with no row to drop, so a paired imported match is not counted from the import there (v9.70.6). See Flag 4 for the later refinement.
32. `player_season_grade_stats` (CA's per-grade aggregate) is a third table the effective views do not cover. CA names the grade "NMCA - Jika Shield" and CricketStatz "A-GRADE", so `max(held, claimed)` per (season, grade) sums them. Imported scorecards are paired away before they reach the grid's `held` side; CA's per-grade figure is counted in full.
33. `seasons.stats_source` is retired: left in place, read by nothing (except `superseded_years` for the screen's note). Do not reintroduce a per-season source marker.
34. Undo removes the imported rows and their pairs, so a synced game that stepped aside returns with nothing to re-derive. Undo also clears leftover `stats_source` for seasons it emptied (`seasons_handed_back`) and the confirm says so.

**Effective views: keep the database equal to the code**
35. `services/superseded_ddl.STATEMENTS` owns all eight views (`v_effective_games`, `_player_season_stats`, `_batting_innings`, `_bowling_spells`, `_fielding_stats`, `_fall_of_wickets`, `_partnerships`, `_bowler_wickets`). Any change to any of them is made HERE or lasts only until the next boot; it also owns `v_effective_batting_innings`' `caught_behind` from migration 291. Each definition must start from the newest migration that defined the view (`CREATE OR REPLACE VIEW` cannot drop columns, so an older definition aborts and once took the API down). Qualify every column, use LEFT JOIN so grade-less games survive, and join on primary keys only.
36. Never replay an older migration's view DDL from a lifespan mirror. The migration 266 mirror in `app/main.py` re-executed 266's pre-pairing definitions of two views every boot (same column list, so `CREATE OR REPLACE` accepted it silently). Ownership fix: the mirror applies 266's column and index only; `superseded_ddl` owns the views and guarantees `games.status`.
37. `superseded_ddl.verify(conn)` reads `pg_get_viewdef` and logs a SCHEMA MISMATCH per view; it reports, never raises. It must log the count on EVERY boot (a check that logs only on failure cannot tell "ran clean" from "never ran"). Needle is `superseded_by_game_id`: 3 mentions in the current aggregate view, 2 in a per-innings view, 0 pre-pairing. Do not probe for `pair_prefers_import` (absent from both fixed and old).
38. `jobs/scheduler.repair_effective_views` runs hourly, re-applies shipped STATEMENTS where `verify` fails, writes nothing when healthy. It is the net for an already-overwritten database; keep it.
39. A migration recorded as applied is not evidence its effect is in the database. Ask Postgres (`pg_get_viewdef`) before inferring a cause from outside.
40. A new view added to this set must join `VERIFIED_VIEWS`, or the boot check will not know about it. The downgrade must drop views first (a `CREATE OR REPLACE` back to the old shape is refused when a guard column exists, and dropping `stats_source` fails while views reference it).

**Data quality and honours**
41. `services/boundary_counts.clean`: `fours*4 + sixes*6 <= runs` holds for every innings, so a count that breaks it is not a count. Judge each column on its own first; null both only if the pair still cannot fit. Store NULL (not recorded), never 0. Never touch runs. Applied by the sync's per-innings write, the season aggregate and this import. CA's own feed carries these bad counts; no re-sync or parser fix reaches them.
42. Player notes become honours by `cricketstatz_awards.classify_note`. An unrecognised note is not an award (biography like "COLLINGWOOD FC (313 Games)" must not reach the honour board); unrecognised lines are reported. A two-year token is a season only when the second half is first plus one (`1982-83` yes, `2011-15` no; `_span_end` rolls the century). An `Nx` prefix means won N times, never a role, checked before role vocabulary; one honour with "Won N times", not N rows. Every honour goes into the club's award catalogue (`ensure_award_definition`) using `ROLE_TYPE_TO_SUBCATEGORY` names.
43. The notes pass runs last, on its own session, and a failure is noted not raised. `POST /notes` (`run_notes_pass`) reruns it alone against the most recent non-undone import, reusing that import's batch id so undo still removes the honours. A re-import re-stamps only rows a CricketStatz import wrote (`ci.organisation_id` checked), never a hand-typed honour. Award definitions survive an undo.

**Progress and status**
44. Every progress write is a heartbeat (`cricketstatz_imports.updated_at`, migration 286); `/status` returns seconds since. "Still going" under 90 s. The bar tracks seasons (monotonic), not `matches_done / matches_total` (the total grows as seasons are walked). Move `phase` column and blob together. Beat every 5 matches mid-season.
45. A run silent past `STALL_AFTER_SECONDS` (300) is closed out as errored so a dead process cannot lock the club out with a 409. There is a Stop button (`/imports/{id}/stop`).
46. The screen is a panel on Data Sync, not its own page.

## Traps and failure signatures

- **Doubled records after import** (270 listed twice, 14,966 runs vs 10,444): same cricket held from CA and CricketStatz. Fixed by per-match pairing (rules 22 to 31), not by skipping or marking seasons.
- **Pairing "did nothing", 171 games for a season (85 + 86)**: the pass never ran, or failed silently. Check the boot and nightly log for the per-club result lines; run `pair_imported_matches`. Also check the views (rule 37).
- **Pair count of 6 of 86**: matcher compared our own club name (rule 25).
- **Pass reports failure with `uq_manual_games_superseded_by_game`**: row-by-row write (rule 29).
- **Career header double, innings list right, shared seasons exactly 2.000x**: the aggregate view still counts the imported copy, or the view in the database is a pre-pairing definition. Split by the view's `source` column, then read `pg_get_viewdef`.
- **Two of eight views stale on a running system**: an older definition with the same column list replaced them silently. Cause was our own mirror (rule 36). A 169-era definition instead fails loudly with `cannot drop columns from view`. Search for what executes, not for the view name: `grep v_effective_games app/main.py` finds one comment because the SQL lives in the migration module.
- **Boundary counts like 30 sixes off 8 runs**: CA data, not import (rule 41).
- **Merged player loses half a career**: merge did not carry `manual_*` tables (rule 19).
- **Leaderboard lists a player twice, one uuid5 and one uuid4**: name spelling mismatch (rule 16).
- **Honours all zero after a full import**: notes phase never ran (rule 43).
- **Import reads as hung**: heartbeat missing (rule 44); or a dead process holding `status='running'` (rule 45).
- **Feature "works" under `py_compile` and `vite build` but fails**: columns added in raw DDL and not mapped on the ORM model (`ManualGame.cricketstatz_match_id`).
- **`resolve_season` returns a `Season`, not an id**: a raw `UPDATE ... WHERE id = :s` bound a repr, raised, was swallowed as a note, and wrote zero matches. Set it on the ORM row.
- **A guard column that makes an overwrite fail loudly took the site down** (v9.70.11): the writer was our own boot path. Know who trips a guard before turning silent failure into a hard one.
- **`games.raw_payload` is `JSON` on the ORM and `JSONB` in migrated databases**: a `create_all` harness gets the narrower type and the view's `NULL::jsonb` cannot union with it.
- **`/organisations/{id}/results` ignores `limit`**: concatenated "pages" are the same rows; do not read it as a fan-out.

## How to verify a change here

- `backend/verification/verify_cricketstatz_import.py` (the main suite: parsers over real captured reports, import, pairing, views, undo, notes). Control runs that must fail: matcher neutered, hooks unwired, per-innings views unfiltered, roster/rollback cache handling, honours classifier and re-stamp neutered, pass removed.
- `verify_merge_carry.py` (merge and undo through the shipped bodies; control: previous behaviour leaves the keeper with 2 of 7 innings).
- `verify_boundary_counts.py` (rule plus backfill; SQL mirror and Python rule agree on 300 random rows).
- Neighbours to re-run when views change: club records, match coverage, competitions, rate coverage, season fold, shared fixtures, retired not out, records timing.
- Harness gotchas: suites share one database and their stub tables collide (run a differing suite on its own database); lifespan-only tables (`player_achievements`, award tables) must be copied column for column from `main.py`; unwind migrations newest first; a control that does not really stop the run proves nothing (refuse a scorecard, the one place `CricketStatzError` propagates); a check needs a real duplicate in the fixture; assert the write, not the column name; leave fixtures as found; assign order-stability by running `assign` over the same rows in three orders (a same-process idempotency check cannot catch it); realistic opposition names in scale tests; a stub must remember which player got which notes.
- Browser check for the panel (`verify_cricketstatz_browser` style suites, Chromium): progress bar on seasons, "still going" and stalled notices, Stop control, shared-season count; the control fails on the old 95% bar. File name not verified in this pass.

## Operator commands and scripts

- `python -m app.scripts.pair_imported_matches [<org|all>] [--apply]`: re-derive pairs now. Dry run by default; a failing club is named, not fatal.
- `python -m app.scripts.merge_cricketstatz_duplicates <org|all> [--apply]`: merge the club's own record with the import's duplicate through `_merge_players_core` (undoable, keeps the club's record). Dry run by default.
- `python -m app.scripts.backfill_boundary_counts <org|all> --apply`: null impossible boundary counts, no network. Dry run by default.
- `python -m app.scripts.inspect_player_aggregate <player> [year]`: read-only. Splits a career by view branch, lists rows for a season, prints `pg_get_viewdef`. It lives in `app/scripts` because `ops/` is not in the backend image.
- `POST /club-admin/cricketstatz/pairing/rebuild` (button) and `POST /notes` (honours only).
- After deploy for a club that reported doubles: run `pair_imported_matches` for it. For duplicate players: `merge_cricketstatz_duplicates`. Database log: `log_statement = 'ddl'` (a reload) plus `%h`/`%a` in `log_line_prefix` names any process rewriting views; failing statements were already in the log.

## Open follow-ups

- Missed pairs (about 234 per 3,500 in the awkward case) are still counted twice with nothing on screen; a "these look like the same match" review list from declined near misses.
- Nothing flags rows whose boundary counts were nulled, and nothing detects seasons a club holds twice from before pairing.
- The process that once overwrote two views after the lifespan applied them was never named beyond our own 266 mirror.
- `iq_team`, `iq_trends` and `import_reconcile` still read `player_season_grade_stats` unfiltered.
- `v_effective_batting_innings.id` is not unique across both sources (both SERIAL); one `DISTINCT ON (id)` from a bug.
- The merge still does not carry `net_attendance`, `team_members`, `family_members`, availability, `fixture_lineups`, `fee_members`, `comms_contacts`, `merch_movements`, fantasy tables.
- `mode=106` ball-by-ball report, their league JSON API and the level-8 database extract are unused.
- Player page batting hand and bowling type could map to `players.batting_hand` / `bowling_type`.
- An import already running when a fix deploys keeps the old behaviour until it finishes.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-CSI-1] Per-season source marker: `seasons.stats_source`, `POST /superseded/clear`, "hand a season back", marking seasons per match or at run end, the 'playhq' state | Superseded by per-match pairing (v9.70.0). Code confirms: `stats_source` helpers removed, `/superseded/clear` no longer routed, `superseded_years` kept only for a note, `superseded_ddl` docstring says nothing reads the column | v9.68.4, v9.69.2 (marker timing), v9.69.3 (undo hands back), v9.69.4, v9.69.8 (L11412 to 11474 marked superseded in the archive) | retire; lessons kept as rules 33, 34, 28.
- [FLAG-CSI-2] Tie handling: v9.70.0 says "a tie is refused rather than guessed"; v9.70.2 says a cluster that cannot be told apart is paired off, reversing it | Later note wins by date; I did not re-read `assign` to confirm the current tie code | v9.70.0 (L10782) vs v9.70.2 (L11286) | verify in `match_pairing.assign`, keep rule 26.
- [FLAG-CSI-3] Guard column: v9.70.10 says both views carry `pairing_applied` so an older definition cannot replace them; v9.70.11 says that guard crash-looped the boot and was reverted | `grep pairing_applied` over `backend/app` finds nothing, so the guard is gone. The hourly repair and boot verify are the net | v9.70.10 (L10947), v9.70.11 (L10985) | retire the guard; keep rules 36 to 38.
- [FLAG-CSI-4] Aggregate rule: v9.70.6 says a paired imported match is never counted from the import at the aggregate level, `pair_prefers_import` or not | Current `superseded_ddl.py` `counts_here` counts a paired match when `pair_prefers_import` AND `seasons.import_authoritative` (a later "re-sourced season counts per match" change, migration 309, plus an `api_scorecard` branch) | v9.70.6 (L11145), v9.70.0 aggregate bullet (L10782) | verify against the migration 309 note in the stats guide before relying on rule 31.
- [FLAG-CSI-5] Import default: v9.68.3 says overlapping synced seasons are SKIPPED by default (`synced_years` 'skip', `synced_coverage`), with 'cricketstatz' as an opt-in that "marks seasons so CA steps aside" | Code still has `skip` as default and the 'cricketstatz' branch, but marking is gone, so 'cricketstatz' now only means "import them too" and pairing handles overlap. v9.70.0 says the design is an AND | v9.68.3 (L11751), v9.68.4 (L11686) | verify what the skip default should be now; the overlap note text ("steps aside") is possibly stale.
- [FLAG-CSI-6] Migration numbering: 285 (import), 286 (heartbeat), 287 (superseded), 290 (one source), 291/292 (per-innings source, renumbered from 291), 293 (pairing). Later 303 and 309 also re-run `superseded_ddl.STATEMENTS` | All present under `backend/alembic/versions`; every one re-runs the same idempotent list, so the numbers are history | throughout | keep; when adding a view change, edit `STATEMENTS`, do not add a new copy.
- [FLAG-CSI-7] Suite counts and "the suite is N checks" figures across sections (113 to 305) | one-off evidence, grow with each change | all "Verified" bullets | retire the counts.
- [FLAG-CSI-8] Whether real-club rosters and figures named in the archive (Keon Park, Cockburn, Brad Quinsee) still match production | one-off measurements, not verified | v9.67.x to v9.70.x | history only.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| A club brings its history across from CricketStatz (migration 285, v9.67.0, Sep 2026) plus all `###` follow-ups (L10637-12118) | rules extracted | see sub-rows |
| . intro and v9.67.0 bullets (L10637-10711) | rules extracted | Standing rules 1 to 12; Traps (ORM mapping); Flag 6 |
| . The club already held its players, spelled its own way (v9.67.4) (L10712-10759) | rules extracted | Rules 16 to 18; Operator commands (merge script) |
| . The preview's "earliest" was the earliest of the most recent 999 (v9.67.3) (L10760-10781) | rules extracted | Rule 15; harness check note |
| . THE TWO SOURCES COMPLETE EACH OTHER. IT IS AN AND (migration 293, v9.70.0) (L10782-10897) | rules extracted (current design) | Rules 22 to 24, 26, 28, 31 to 33; Flags 2, 4, 5; Follow-ups |
| . THE PAIRING WAS RIGHT AND NEVER RAN (v9.70.4) (L10898-10946) | rules extracted | Rules 28, 30; Operator commands; Traps |
| . AN OLDER DEFINITION CAN NO LONGER REPLACE THE VIEW (v9.70.10) (L10947-10984) | rules extracted; guard column superseded by v9.70.11 | Rules 38, 40; Flag 3 |
| . IT WAS OUR OWN BOOT PATH, TWO THOUSAND LINES LATER (v9.70.11) (L10985-11029) | rules extracted (current) | Rule 36; Traps; Flag 3 |
| . AND POSTGRES'S OWN LOG NAMED THE SHAPE OF IT (v9.70.8) (L11030-11083) | rules extracted | Rules 35, 38; Operator commands (log_statement) |
| . THE VIEW IN THE DATABASE WAS NOT THE VIEW IN THE CODE (v9.70.7) (L11084-11144) | rules extracted | Rules 37, 39; Traps; Operator commands (inspect script) |
| . PREFERRING THE IMPORTED COPY IS A PER-INNINGS DECISION (v9.70.6) (L11145-11195) | rules extracted, refined by later migration 309 | Rule 31; Flag 4 |
| . AND THEN IT REFUSED ITS OWN WORK (v9.70.5) (L11196-11241) | rules extracted | Rules 27, 29; How to verify (order check) |
| . A COUNT THAT CANNOT FIT THE RUNS IS NOT A COUNT (v9.70.3) (L11242-11285) | rules extracted | Rule 41; Operator commands (backfill) |
| . OUR OWN CLUB'S NAME IS ON BOTH SIDES OF EVERY MATCH (v9.70.2) (L11286-11355) | rules extracted (reverses v9.70.0 tie refusal) | Rules 25, 26; Flag 2 |
| . A SEASON CHANGES OVER AS ITS OWN MATCHES LAND (v9.69.2) (L11356-11411) | superseded by v9.70.0 (season marker gone); lesson kept | Rule 28, Flag 1, How to verify (control must really stop run) |
| . EVERY EFFECTIVE VIEW APPLIES THE SEASON'S SOURCE (migration 291, v9.69.8) (L11412-11474) | superseded by v9.70.0; eight-view structure still current | Rules 35, 40; Flag 1 |
| . THE PER-GRADE AGGREGATE IS A SECOND TABLE (v9.69.7) (L11475-11512) | rules extracted (rule persists, `season_source.py` gone) | Rule 32; Follow-ups |
| . THE HONOUR BOARD RUNS ON ITS OWN (v9.69.6) (L11513-11545) | rules extracted | Rule 43; Operator commands |
| . A MIGRATION RECORDED AS APPLIED IS NOT EVIDENCE (v9.69.5) (L11546-11582) | rules extracted | Rules 37, 39 |
| . ONE SOURCE PER SEASON, DECIDED BY THE DATA (migration 290, v9.69.4) (L11583-11658) | superseded by v9.70.0 | Flag 1; lessons in Traps (`resolve_season` returns a Season) and harness gotchas |
| . AND UNDOING ONE HAD TO HAND THOSE SEASONS BACK (v9.69.3) (L11659-11685) | superseded by v9.70.0 (pairs go with rows); residual clear kept | Rule 34; Flag 1 |
| . AND WHICH SOURCE IS THE RECORD IS THE CLUB'S CALL (migration 287, v9.68.4) (L11686-11750) | superseded by v9.70.0 | Flags 1, 5; Traps (`raw_payload` JSON/JSONB) |
| . THE SAME CRICKET FROM TWO SOURCES COUNTS IT TWICE (v9.68.3) (L11751-11821) | rules extracted; skip default partly current | Flag 5; Follow-ups (view `id`); Traps |
| . A MERGE MOVES A RECORD; IT MUST NEVER DELETE ONE (v9.68.1) (L11822-11896) | rules extracted | Rules 19 to 21; Follow-ups (uncarried tables); How to verify |
| . The honour board is written in the notes (v9.68.0) (L11897-11985) | rules extracted | Rules 42, 43; How to verify |
| . An imported grade is classified on the way in (v9.67.3) (L11986-12002) | rules extracted | Rule 13 |
| . Find out what there is before pulling it (v9.67.2) (L12003-12040) | rules extracted | Rule 14 |
| . A working import that read as a hung one (migration 286, v9.67.1), incl. trailing "lives on Data Sync" and client-politeness bullets (L12041-12118) | rules extracted | Rules 12, 44 to 46; Follow-ups (`mode=106`) |
