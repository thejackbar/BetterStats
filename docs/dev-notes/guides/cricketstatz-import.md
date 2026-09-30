# Guide: CricketStatz history import, two-source pairing and the effective views

**Read this before**:
- Touching `services/cricketstatz_*.py`, `routers/cricketstatz.py`, `components/admin/CricketStatzImport.jsx` (a panel inside `AdminSync.jsx`).
- Touching `services/match_pairing.py`, `services/superseded_ddl.py`, `manual_games.superseded_by_game_id` / `pair_prefers_import`, or any of the eight `v_effective_*` views.
- Symptoms: a career, record board or hundreds count about double for seasons CA and CricketStatz both cover; one person listed twice ("Quinsee, Brad" and "Brad Quinsee"); a merge that halves a career; 3,000 matches and no honours; "30 sixes in an innings of 8"; an import that looks hung.
- Editing `_merge_players_core`, `merge_carry.py`, or the lifespan mirror in `app/main.py` that replays migration DDL.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/cricketstatz-import.md`. Grep hints: `linkreport`, `resolve_player`, `most recent 999`, `IT IS AN AND`, `NEVER RAN`, `pairing_applied`, `TWO THOUSAND LINES`, `log_statement`, `pg_get_viewdef`, `PER-INNINGS DECISION`, `fours * 4`, `Preston`, `player_season_grade_stats`, `run_notes_pass`, `stats_source`, `merge_carry`, `classify_note`, `STALL_AFTER_SECONDS`.

**Related guides**: merge/duplicates (`_merge_players_core`); stats and effective views (record boards, shared fixtures); sync (Full Rebuild triggers pairing); BetterImport (`match_players`); awards (`player_achievements`); migrations and lifespan mirrors (numbering).

## Standing rules

**Fetch and parse**
1. Reports are `/ss/linkreport?mode=<N>&club=<id>&web=1`, answering `document.write("<table>...")` (`cricketstatz_parse.unwrap`). Mode 12 is the match list, `mode=100&match=<id>` the scorecard, `mode=106` ball by ball (unused).
2. `limit` caps a report at 999 rows: pull season by season. The club page's season dropdown lists every season back to 1860 for every club, so it is a candidate list only. `plan_seasons` probes EVERY candidate concurrently (about 1 minute for 167), keeps the rows, orders oldest first. Never bound the range from record-board dates (top-100 lists can miss a quiet early season) or stop at a run of empty years.
3. Preview "earliest" is only a floor (the all-time list is capped at 999): use the minimum year across five record boards and say "back to at least".
4. Read columns from the header row (`_column_map`); a 1995 card is `R M 4s 6s`, and positional reading files boundaries as balls faced.
5. Read a dismissal per `span.ss_block` how-out marker, splitting on the block's OPENING tag (a clause nests its own `ss_howout` span; a non-greedy match lost all 102 bowler credits). Captain, keeper, duck come from `title=` attributes, never the emoji. Caught behind is derived from the keeper marked on the fielding side's card.
6. Only our own players get `players` rows (minting opposition is the leak `purge_foreign_members` cleans). The opposition half lives on `manual_games.extracted_payload`. Identity is CricketStatz's `playerid`; `manual_games.cricketstatz_match_id` makes re-import an upsert.
7. A placeholder (`N/A` batters) is not a person: leave the row out, still import the match (else `uq_manual_batting_game_inns_player`).
8. Commit one match at a time and clear ALL caches (season, grade, roster) on rollback, or a dangling cached id fails every later match in the season (one bad card cost 97 good ones).
9. The record book goes to `cricketstatz_records` generically (one live copy per club per mode). Never blend it into our computed records.
10. An expired subscription answers `Error: Subscription expired`; `unwrap` raises a typed `CricketStatzError` so it is not read as "no matches". Their database is deleted 12 months after expiry.
11. The client identifies itself, concurrency 3, delays, 30-minute cache, scorecards uncached. Their `robots.txt` disallows `/ss/`; proceeding was a data-portability call, so never enumerate club ids or sweep the site.
12. Create grades classified: write `category` AND `categories` (`suggest_category`/`suggest_categories`) and `grassroots_id=None` on season and grade, or imported juniors sit in senior careers.

**Player matching and merging**
13. `resolve_player` uses `import_ingest.match_players`, not raw `ilike` (club stores "Quinsee, Brad", CricketStatz "Brad Quinsee"). Take only `exact` (covers middle initials). Looser matches get their own record and are REPORTED pointing at Merge Duplicates. Append a new player to the roster cache. A re-import cannot repair existing duplicates (it finds its own row by CricketStatz id first): use the repair script.
14. `_merge_players_core` must carry every table recording what a player did. `services/merge_carry.CARRIED` is the one list for merge and undo; `merge_logs.carried_row_ids` is a JSONB blob keyed `"<table>.<column>"`. `manual_*` tables cascade on `players.id`, so an uncarried one is destroyed; `player_achievements` has no FK and is orphaned.
15. Keeper's row wins a collision, joined with `IS NOT DISTINCT FROM` (NULL grade is a real key part). Keep integer ids as integers in JSONB (asyncpg cannot cast strings to `int[]`). Skip absent lifespan-created tables (`to_regclass`). Move the import identity to the keeper if it has none. Recovery for a hit club: re-run the import; undoing the merge cannot help for old logs.

**Two sources: current design is per-MATCH pairing (migration 293, v9.70.0)**
16. The sources complement each other: an AND, never an OR. Per-season choice lost matches the other source alone held (CA 401 vs CricketStatz 473 over five seasons).
17. `superseded_by_game_id` pairs an imported match to the synced game that IS that match; `pair_prefers_import` says which half counts. CA wins by default; the import wins only where the synced game has no scorecard of ours and the import does. Unpaired matches from either side count. Nothing is deleted.
18. The scorecard is the identifier, not the date (two-day matches are dated differently). Ways in: three shared scores; one shared score plus same club within ten days; same day and club; two shared scores close together; and same club within ten days only where one side has no card.
19. Our club name is on both sides: `split_sides` removes our side first (stored opposition wins). One shared word is not a club: `teams_agree` needs containment or two identifying words, age groups stripped. Which of OUR sides played (`side_marker`) is the one hard no. A grade letter is never read as a team number.
20. A cluster nothing can tell apart is paired off, not refused (v9.70.2 reversed v9.70.0): keeps the COUNT right. Ties break by id so assignment is stable across processes (else a settled club rewrote rows every run).
21. The pass RE-DERIVES, never accumulates, and is idempotent. It runs per season during import, at import end, after a full sync and Full Rebuild, at boot for every club with an import, nightly (`jobs/scheduler.pair_all_imported_matches`, 02:50 Perth) and on `POST /pairing/rebuild`.
22. Write pairs by clearing all changing rows first, then one `unnest` UPDATE. Row-by-row hits `uq_manual_games_superseded_by_game` and rolls back the whole pass.
23. Matching is seconds of CPU: `asyncio.to_thread` (`assign`), never inline. Hold the boot task in `main._BACKGROUND_TASKS`. Bind card queries to loaded game ids (`= ANY(CAST(:ids AS UUID[]))`); a players-only bind scanned the platform.
24. Aggregate level differs from per-innings: `player_season_stats` is a season total with no row to drop, so a paired imported match is not counted from the import there (v9.70.6). See Flag 4.
25. `player_season_grade_stats` (CA per-grade) is a third table the views do not cover. CA's "NMCA - Jika Shield" and CricketStatz's "A-GRADE" never share a cell, so `max(held, claimed)` sums them. Count CA in full and pair imported scorecards away before the grid's `held` side.
26. `seasons.stats_source` is retired: kept, read by nothing (only `superseded_years`, for a note). Undo removes imported rows and their pairs (synced games return); it also clears leftover markers on seasons it emptied (`seasons_handed_back`).

**Effective views: database must equal code**
27. `services/superseded_ddl.STATEMENTS` owns all eight views. Change them HERE or the change lasts to the next boot (it also owns migration 291's `caught_behind` on batting). Start from the newest definition (`CREATE OR REPLACE VIEW` cannot drop columns; an older one once took the API down), qualify columns, LEFT JOIN, primary-key joins only, downgrade drops views first.
28. Never replay an older migration's view DDL from a lifespan mirror. The 266 mirror in `app/main.py` re-ran pre-pairing definitions of two views every boot (same columns, so accepted silently). The mirror now applies 266's column and index only.
29. `superseded_ddl.verify(conn)` reads `pg_get_viewdef`, logs SCHEMA MISMATCH per view, never raises, and must log a count EVERY boot. The needle is `superseded_by_game_id` (3 in the aggregate view, 2 per-innings, 0 pre-pairing); do not probe `pair_prefers_import`. A new view joins `VERIFIED_VIEWS`.
30. `jobs/scheduler.repair_effective_views` runs hourly and re-applies STATEMENTS where verify fails. Keep it. A migration recorded as applied is not evidence its effect exists: ask Postgres first.

**Data quality, honours, progress**
31. `services/boundary_counts.clean`: `fours*4 + sixes*6 <= runs` always. Judge each column alone first; null both only if the pair still cannot fit; NULL, never 0; never touch runs. Applied by sync, season aggregate and this import. CA's feed carries the bad counts; no re-sync fixes them.
32. `cricketstatz_awards.classify_note`: an unrecognised note is not an award (biography like "COLLINGWOOD FC (313 Games)" stays off the board; unrecognised lines are reported). A two-year token is a season only if second = first + 1 (`_span_end` rolls the century). `Nx` prefix means won N times, never a role, checked first; one honour saying "Won N times". Every honour enters the award catalogue (`ensure_award_definition`, `ROLE_TYPE_TO_SUBCATEGORY`).
33. The notes pass runs last on its own session and a failure is noted, not raised. `POST /notes` (`run_notes_pass`) reruns it alone on the latest non-undone import, reusing its batch id so undo removes the honours. Re-import re-stamps only rows a CricketStatz import wrote (`ci.organisation_id`), never a hand-typed honour. Award definitions survive undo.
34. Every progress write is a heartbeat (`cricketstatz_imports.updated_at`, migration 286); `/status` returns seconds since; "still going" under 90 s. The bar tracks seasons, not matches (total grows). Move `phase` column and blob together. A run silent past `STALL_AFTER_SECONDS` (300) is closed as errored so a dead process cannot 409 the club. Stop button at `/imports/{id}/stop`.

## Traps and failure signatures

- **Doubled records (270 listed twice)**: same cricket from both sources. Fix is per-match pairing, not season skipping or marking.
- **171 games in a season (85 + 86)**: pairing never ran or failed silently. Read the per-club boot and nightly log lines; run `pair_imported_matches`.
- **6 of 86 paired**: matcher compared our own club name (rule 19).
- **Career header double, list right, shared seasons exactly 2.000x**: aggregate view counts the import, or the database view is a pre-pairing definition. Split by the view's `source` column, then `pg_get_viewdef`.
- **Two of eight views stale on a live system**: an older same-column definition replaced them silently (our own 266 mirror). A 169-era one fails loudly (`cannot drop columns from view`). `grep v_effective_games app/main.py` finds one comment because the SQL is in the migration module: search for what executes.
- **A guard column making overwrites fail loudly crash-looped boot** (v9.70.11): the writer was our own. Know who trips a guard first.
- **`resolve_season` returns a `Season`, not an id**: a raw `UPDATE ... WHERE id = :s` bound a repr, was swallowed as a note, wrote zero matches.
- **Passes `py_compile` and `vite build` but fails**: raw-DDL columns not mapped on the ORM model.
- **`games.raw_payload` is `JSON` on the ORM, `JSONB` in migrated databases**: a `create_all` harness cannot union it with the view's `NULL::jsonb`.

## How to verify a change here

- `backend/verification/verify_cricketstatz_import.py` (parsers over captured reports, import, pairing, views, undo, notes). Controls that must fail: matcher neutered, hooks unwired, per-innings views unfiltered, cache handling, honours classifier and re-stamp.
- `verify_merge_carry.py` (control: keeper keeps only its own innings), `verify_boundary_counts.py` (SQL mirror equals Python rule), `frontend/verification/verify_cricketstatz_browser.mjs` (panel progress, stall, Stop; control fails the old 95% bar).
- Re-run neighbour stats suites when views change (club records, match coverage, competitions, rate coverage, season fold, shared fixtures, retired not out, records timing).
- Harness gotchas: suites share one database (stub tables collide); copy lifespan-only tables (`player_achievements`, award tables) column for column; unwind migrations newest first; a control must really stop the run (refuse a scorecard, the one place `CricketStatzError` propagates); a check needs a real duplicate in the fixture; assert the write, not the column name; test tie stability by running `assign` over the same rows in three orders; use realistic opposition names in scale tests.

## Operator commands and scripts

- `python -m app.scripts.pair_imported_matches [<org|all>] [--apply]`: re-derive pairs. Dry run by default; failing clubs are named.
- `python -m app.scripts.merge_cricketstatz_duplicates <org|all> [--apply]`: merge club record with import duplicate via `_merge_players_core`, keeping the club's record. Dry run by default.
- `python -m app.scripts.backfill_boundary_counts <org|all> --apply`: null impossible counts, no network. Dry run by default.
- `python -m app.scripts.inspect_player_aggregate <player> [year]`: read-only per-branch split and `pg_get_viewdef`. Lives in `app/scripts` because `ops/` is not in the backend image.
- Endpoints: `POST /pairing/rebuild`, `POST /notes`. DB log: `log_statement = 'ddl'` (reload) plus `%h`/`%a` in `log_line_prefix` names a rewriting process.

## Open follow-ups

- Missed pairs (about 234 per 3,500 in the awkward case) still count twice, unshown; a "same match?" review list is unbuilt.
- Unused: `mode=106` ball by ball, their league JSON API, level-8 extract.
- Nothing flags boundary counts nulled; nothing detects seasons held twice from before pairing.
- The outside process that once overwrote two views was never named beyond our 266 mirror.
- `iq_team`, `iq_trends`, `import_reconcile` still read `player_season_grade_stats` unfiltered.
- `v_effective_batting_innings.id` is not unique across sources.
- Merge still does not carry `net_attendance`, `team_members`, `family_members`, availability, `fixture_lineups`, `fee_members`, `comms_contacts`, `merch_movements`, fantasy tables.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-CSI-1] Per-season source marker (`seasons.stats_source`, hand-back, marking timing, 'playhq' state) | Superseded by per-match pairing; code confirms helpers removed, `/superseded/clear` unrouted, column read only by `superseded_years` | v9.68.4, v9.69.2, v9.69.3, v9.69.4, v9.69.8 (L11356-11474, L11583-11750) | retire; lessons kept.
- [FLAG-CSI-2] v9.70.0 says a tie is refused; v9.70.2 says it is paired off | later note wins; `assign` not re-read | v9.70.0 (L10782), v9.70.2 (L11286) | verify in `match_pairing.assign`.
- [FLAG-CSI-3] v9.70.10 says both views carry a `pairing_applied` guard column; v9.70.11 says it crash-looped boot and was reverted | `grep pairing_applied backend/app` finds nothing | L10947, L10985 | retire the guard; keep verify and hourly repair.
- [FLAG-CSI-4] v9.70.6: a paired imported match is never counted from the import at aggregate level | `superseded_ddl.py` `counts_here` now also counts it when `pair_prefers_import` AND `seasons.import_authoritative` (later migration 309 "re-sourced season counts per match") | L11145, L10782 | verify against the stats guide before relying on rule 24.
- [FLAG-CSI-5] v9.68.3/9.68.4: overlapping synced seasons are skipped by default (`synced_years` 'skip'), 'cricketstatz' marks seasons so CA steps aside | code keeps the skip default and the option, but marking is gone; the "steps aside" note text is likely stale | L11686-11821 | verify intended default under the AND design.
- [FLAG-CSI-6] Migrations 285, 286, 287, 290, 291/292, 293 | 303 and 309 also re-run `superseded_ddl.STATEMENTS`; numbers are history | throughout | keep; edit `STATEMENTS`, not a new copy.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| A club brings its history across from CricketStatz (migration 285, v9.67.0), with all `###` follow-ups (L10637-12118) | rules extracted | sub-rows |
| . intro and v9.67.0 bullets (L10637-10711) | rules extracted | Rules 1, 4 to 11; Traps (ORM mapping); Flag 6 |
| . The club already held its players (v9.67.4) (L10712-10759) | rules extracted | Rule 13; Operators |
| . The preview's "earliest" (v9.67.3) (L10760-10781) | rules extracted | Rule 3 |
| . THE TWO SOURCES COMPLETE EACH OTHER, AN AND (migration 293, v9.70.0) (L10782-10897) | rules extracted (current design) | Rules 16 to 18, 21, 24 to 26; Flags 2, 4, 5 |
| . THE PAIRING WAS RIGHT AND NEVER RAN (v9.70.4) (L10898-10946) | rules extracted | Rules 21, 23; Traps |
| . AN OLDER DEFINITION CAN NO LONGER REPLACE THE VIEW (v9.70.10) (L10947-10984) | rules extracted; guard column superseded by v9.70.11 | Rules 27, 30; Flag 3 |
| . IT WAS OUR OWN BOOT PATH (v9.70.11) (L10985-11029) | rules extracted | Rule 28; Traps; Flag 3 |
| . POSTGRES'S OWN LOG NAMED THE SHAPE OF IT (v9.70.8) (L11030-11083) | rules extracted | Rules 27, 30; Operators |
| . THE VIEW IN THE DATABASE WAS NOT THE VIEW IN THE CODE (v9.70.7) (L11084-11144) | rules extracted | Rules 29, 30; Traps; Operators |
| . PREFERRING THE IMPORTED COPY IS A PER-INNINGS DECISION (v9.70.6) (L11145-11195) | rules extracted, refined by migration 309 | Rule 24; Flag 4 |
| . AND THEN IT REFUSED ITS OWN WORK (v9.70.5) (L11196-11241) | rules extracted | Rules 20, 22; How to verify |
| . A COUNT THAT CANNOT FIT THE RUNS (v9.70.3) (L11242-11285) | rules extracted | Rule 31; Operators |
| . OUR OWN CLUB'S NAME IS ON BOTH SIDES (v9.70.2) (L11286-11355) | rules extracted (reverses tie refusal) | Rules 19, 20; Flag 2 |
| . A SEASON CHANGES OVER AS ITS OWN MATCHES LAND (v9.69.2) (L11356-11411) | superseded by v9.70.0 | Flag 1; How to verify (control must stop run) |
| . EVERY EFFECTIVE VIEW APPLIES THE SEASON'S SOURCE (migration 291, v9.69.8) (L11412-11474) | superseded by v9.70.0; eight-view structure current | Rule 27; Flag 1 |
| . THE PER-GRADE AGGREGATE IS A SECOND TABLE (v9.69.7) (L11475-11512) | rules extracted | Rule 25; Follow-ups |
| . THE HONOUR BOARD RUNS ON ITS OWN (v9.69.6) (L11513-11545) | rules extracted | Rule 33; Operators |
| . A MIGRATION RECORDED AS APPLIED IS NOT EVIDENCE (v9.69.5) (L11546-11582) | rules extracted | Rules 29, 30 |
| . ONE SOURCE PER SEASON (migration 290, v9.69.4) (L11583-11658) | superseded by v9.70.0 | Flag 1; Traps (`resolve_season`) |
| . AND UNDOING ONE HAD TO HAND THOSE SEASONS BACK (v9.69.3) (L11659-11685) | superseded by v9.70.0; residual clear kept | Rule 26; Flag 1 |
| . WHICH SOURCE IS THE RECORD IS THE CLUB'S CALL (migration 287, v9.68.4) (L11686-11750) | superseded by v9.70.0 | Flags 1, 5; Traps (`raw_payload`) |
| . THE SAME CRICKET FROM TWO SOURCES COUNTS IT TWICE (v9.68.3) (L11751-11821) | rules extracted; skip default partly current | Flag 5; Follow-ups; Traps |
| . A MERGE MOVES A RECORD; IT MUST NEVER DELETE ONE (v9.68.1) (L11822-11896) | rules extracted | Rules 14, 15; Follow-ups |
| . The honour board is written in the notes (v9.68.0) (L11897-11985) | rules extracted | Rules 32, 33 |
| . An imported grade is classified on the way in (v9.67.3) (L11986-12002) | rules extracted | Rule 12 |
| . Find out what there is before pulling it (v9.67.2) (L12003-12040) | rules extracted | Rule 2 |
| . A working import that read as a hung one (migration 286, v9.67.1), incl. trailing bullets (L12041-12118) | rules extracted | Rules 11, 34; Follow-ups |
