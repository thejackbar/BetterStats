# Guide: Imports, manual entries and data tidy-up

**Read this before**:
- `routers/manual_entries.py` (manual games, `/games/import/*`, `/games/check`, `/seasons/for-date`, `update_season`), `routers/games.py` (`_merge_manual_innings`, `_manual_side_names`), `MatchScorecard.jsx` side-splitting.
- The scorebook/CSV match import, `scorebook_innings.py`, `game_import_staging.py`, `manual_result.py`, `manual_game_check.py`, `game_sides.py`, `season_resolve.py`.
- Stats importers and reconcile (`import_ingest.py`, `import_reconcile.py`, `routers/imports.py`, `match_pairing.py`, `import_cleanup.py`).
- Merge Duplicates or Manage Grades suggestions (`services/grade_duplicates.py`), or the scorecard reader (`scorecard_ocr.py`, `AdminScorecardUpload.jsx`).
- Symptoms: see Traps below.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/imports-manual-entries-and-data-tidy.md`. Grep hints: `stray innings`, `short_form`, `innings_order_known`, `re-sourced`, `is_team_labelled`, `discriminator`, `name_variant`, `cleanup_seasons`, `import_batch_id`, `staging`, `for-date`, `grade-less`, `exclude_id`, `balls_per_over`, `card_error`.

**Related guides**: `cricketstatz-import` (pairing, effective views), `stats-figures-records-and-filters`, `cross-club-and-data-safety`, `data-sources-and-sync`.

## Standing rules

**Manual games and the scorebook CSV**
1. A hand-entered innings stores no total, wickets or overs when its side is "us": `_replace_game_children` nulls them, the form clears them in `setInningsSide` and omits them in `buildPayload`. Why: `_merge_manual_innings` lets a recorded `total_runs` replace the batters' sum, so a stray copy shows the opposition total twice. The CSV legitimately records OUR total (`innings_total`), so the merge still honours one: fix at the source.
2. A game that does not add up is warned about, never refused. `manual_game_check.check_game` is the one definition, behind `POST /manual-entries/games/check` (writes nothing); a failed check never blocks a save.
3. The CSV carries opposition and innings figures and fall of wickets (`opp_innings_number`, `batting_order_known`, `innings_*`, `opp_*`, `fow_wicket`, `fow_score`, `bowling_order`). Read innings meta off every row BEFORE the blank-player skip. Our bowlers are filed under the OPPOSITION's innings number. Opposition figures without `opp_innings_number`, or one innings given as both sides', are refused.
4. `innings_no` is not batting order (converter numbers by leg, ours 2n-1, theirs 2n, sends `batting_order_known=false`). `manual_games.innings_order_known` records it; NULL reads as known. When false the page shows "INNINGS" unnumbered, no margin, no HOME/AWAY, and says why.
5. `scorebook_innings.derive_partnerships` returns None (refuse) on a gap, a batter out who is not at the crease, a score going backwards or a wicket-count mismatch. A wrongly paired stand is worse than none.
6. `_EXTRA_GAME_CHILDREN` snapshots fall of wickets, partnerships and innings figures. `_restore_extra_children` replaces only a child table the snapshot holds. Why: an edit logged earlier has no keys, and "absent means none" would delete a scorebook import's fall of wickets.
7. Imported matches leave `home_team`/`away_team` blank. Every reader must use `game_sides.sides_sql` (Python twin in `_fetch_manual_games_as_list`), which names a blank pair from the club and opposition with `home_away_known=false`.
8. The CSV template is built from dicts keyed on column name, never positional (a drifted example misfiled bowlers). Fetch `origin/main` before building on an import format.
9. `manual_result.py` is the one winner rule (CSV import, hand-entry, `settle_manual_winners`). It changes the winner only when the result line opens Won/Lost, the recorded winner names the other side, it is one innings each and the scores agree. Scores are computed only where winner and result line already disagree.
10. Our innings is named for the match's team, not the club: `games._manual_side_names` (whichever of home/away is not the opposition, punctuation-insensitive; else the side sharing a non-generic word with the club; else the single named non-opposition side; else the club name). Frontend: `AGE_TOKEN` keeps "60s"/"U14" generic, `sidesSwapped` judges both sides against both teams, `splitSides` files by exact normalised name first.
11. Header stays home/away, team cards stay in batting order (owner instruction, v8.79.2). A club asked for cards under header columns: raised, not built.
12. Manual spells keep insertion order: every read orders by `id` (scorecard, edit form, snapshots), so `bowling_order` and undo survive.

**Seasons and grades on manual games**
13. `manual_games.season_id` is NOT NULL but optional on the wire: omitted, `_resolve_game_season` files the game under the season its date falls in and creates it (and the grade via `grade_name`, writing BOTH `category` and `categories`). An explicit season wins. The club year starts in JULY; the rule lives in `season_resolve.py` (`canonical_name`, `season_start_year`, imported by `cleanup_seasons`). Read a season's year off its NAME first, then `year` (can be NULL); prefer the canonical name, then a synced season.
14. `GET /manual-entries/seasons/for-date` is read-only on purpose (runs before anyone decides to import). A season/date mismatch is said aloud, never refused.
15. A manual game may lack `grade_id` but always has `season_id` and `organisation_id`. Read the view's own columns from `v_effective_games`, never join through `grade_id`, and never test ownership with a bare `g.source = 'manual'` (cross-club leak). `list_games`' `api_games` sub-query is `source='api'` only.
16. `PATCH /club-admin/seasons/{id}` edits name/year on ANY season (sync never overwrites a name). Delete is manual-only and empty-only; `_season_in_use` must cover `player_season_stats` and `imported_stats` (both cascade). The list returns `synced` (`grassroots_id IS NOT NULL`), not `synced_at`.
17. `cleanup_seasons` writes only manual seasons (`grassroots_id IS NULL`), MERGES duplicates via `season_aliases` (undoable, single-hop), renames a lone manual season to "Summer YYYY/YY" with `year`, and refuses to guess when several synced seasons exist and none is plain-named.

**Large sheets**
18. The sheet is parsed once and staged (`manual_game_import_staging`, `game_import_staging.py`, migration 302, 1 hour TTL). Resolve and commit send a token; `rows` stays accepted as the direct-caller fallback (`_rows_for` prefers the token). Why: the wizard re-posted every row on each resolve (145 MB).
19. Staging is a table, never the media volume: deleted at commit, never backed up. Scope club AND user in the WHERE clause so wrong, expired and unknown tokens look identical. Expiry is enforced on read (the sweep only tidies). The token is spent in the games' transaction.
20. `_MAX_GAME_UPLOAD_BYTES` and the nginx `client_max_body_size` on the preview location move together (nginx refuses first). Resolve and commit have their own locations for the TIMEOUT (writes take 68 to 124 s, past nginx's 60 s: 504 while the job finishes). Use exact `location =`; a trailing-slash prefix 301s `POST /games/import` and drops the body. Single-shot `POST /games/import` stays on ordinary limits. The preview's `rows` reply is capped at 8 MB; the token is always returned.

**Pairing and season totals (re-sourced seasons, migration 309)**
21. A season total has no per-match granularity. An overwrite import marks the season `import_authoritative`, and the `api_scorecard` branch of `v_effective_player_season_stats` counts every synced game with no preferred imported twin from scorecards (batting, bowling, fielding, appearances; org-scoped via `players`). The import's rollup counts the file's matches; the two are disjoint ("and, not or"). Aggregate each table on its own, THEN join (a LEFT JOIN of batting, bowling and fielding on one key multiplies rows). A fixture the other club synced first is keyed onto our season (guid, then year).
22. Matcher: `_existing_game_index` covers the club's season OR either side of the fixture; unmatched sheet matches get a second look via `match_pairing.assign` on a `(player_id, runs)` signature (never a second copy of the rules); `match_pairing.load_synced` is the one synced-side query. A re-import inherits the old row's pair or the synced copy returns. `repair_overwrite_pairs` holds back pairs with 0 shared scores.
23. A `WITH` CTE referenced more than once is MATERIALIZED and blocks `player_id = X` pushdown, so player-dependent CTEs are `NOT MATERIALIZED`. `auth_games` does not depend on the player and stays `AS MATERIALIZED` (inlining cost 45 s on `/stats`). StatLab's `appear` CTE unions the four match sources (imported matches have no `game_appearances`).
24. Sync and full rebuild never delete manual games (`cross-club-and-data-safety`).

**Team-labelled sheets and name matching**
25. `import_reconcile.is_team_labelled` (two or more grade labels) reconciles per player against the WHOLE GR record, season by season; labels stay stored (`season_rows_by_grade`), the residual carries no grade. Commit and preview (`routers/imports.py::_resolve`) must make the same call (preview reads earlier uploads too). `covered_by_year`: covered when GR holds that YEAR under any season row. Result is the ONLINE figure when online holds more. Accepted cost: separate 1st/2nd sheets read as one book. No re-import needed (`reconcile_imported_totals` runs every sync).
26. Short-form first names ("Steve"/"Steven") are a separate step, not a `match_players` change (many callers); only the two stats importers opt in (`short_form_suggestions`, `apply_short_form_suggestions`). `import_ingest.is_short_form` is the one rule (same surname, one first name a prefix of the other, at least 3 letters, middles compatible; Bob/Robert never claimed); `admin._first_name_link` calls it. Result is PRE-SELECTED, never silent (status `suggested`). Refuse where two club players fit or another name on the SAME sheet reaches that player. Careers over `MAX_CAREER_GAP_YEARS` (5) apart are offered, not chosen; undated or overlapping careers do not block. Run BEFORE overrides.
27. Merge Duplicates tiers: exact, fuzzy (`FUZZY_MERGE_THRESHOLD` 0.90), `name_variant` (`_name_variant_pairs`, blocked on surname plus first initial, `_name_parts`/`_middles_compatible` IMPORTED from `import_ingest`). Edit distance degrades multiplicatively (short form plus middle initial is 0.78): never lower the threshold, no nickname list, 2 characters is too short. File a player under BOTH `name` and `display_name` (`_name_keys`). Bulk Approve is an allowlist (`isExactPair`); a new tier is manual-confirm by default.

**Grade duplicate suggestions**
28. Never point `admin._fuzzy_name_pairs` at grade names: a discriminator (number, bare letter, colour, announced format) IS the meaning, and edit distance ranks different grades above real duplicates. `grade_duplicates.py` requires discriminating tokens IDENTICAL (`same_name`, `extra_words`, `word_typo` only after that). Format is read off the RAW name via `suggest_formats`. Synonyms EXPAND abbreviations, never contract.
29. Association (`grades.association_id`) is a VETO; category clash and coexisting in a season are CAUTIONS. Only `same_name` is bulk-safe (`BULK_SAFE_KINDS`). Direction is a suggestion. Pairs come from `list_grades_with_stats`. `grade_merge_pair_ignores` (294) keys on NAMES, sorted; `grade_ignore_ddl.py` is the one DDL copy. The CA grade GUID cannot link grades.

**Undo and scorecard reader**
30. `players.import_batch_id` (234) marks players the import minted (`ON DELETE SET NULL`); a re-import moves it forward only where non-NULL. `import_cleanup.deletable_players` is the one rule (undo endpoints and script): delete only with none of ~40 `BLOCKING_REFS`, no profile data, no `grassroots_id`/`playhq_id`. Check emptiness AFTER `db.flush()`.
31. Reader: it transcribes faithfully; the ONE allowed deviation is inferring a blank result (`result_inferred`, flagged). `reconcile()` returns `[{kind, text}]`: `card_error` (card's own figures disagree, fix-or-keep) versus `misread`. Unticked "This card tracks" columns import as NULL, not 0 (migration 184; defaults stay `Optional[int] = 0`, only explicit null means unrecorded). Pre-1980 8-ball overs: `match.balls_per_over` (DB overs stay as written). Read EVERY occurrence of a name (bowling analysis is authority for bowlers, batting order for batters; never merge players sharing only a surname). Roster matching: `import_ingest.match_players` (auto-fill exact or one candidate at 0.9+). Run `scorecard_eval` before and after any prompt, schema or model change (`docs/scorecard-reader-eval.md`); uploads never teach the model.
32. Jump-back edit replays `extracted_payload` through the upload review UI (photo uploads only); save is `PATCH /games/{id}`. `check_scorecard_duplicate` takes `exclude_id`. Delete and restore use the one audit trail (`/admin/manual-entries#audit`).

## Traps and failure signatures

- Same total on both innings: rule 1. "All" lower than "Men's": rules 21, 22. "— vs —" or `home_team: None`: rule 7. Scores under the wrong team: rule 10. Bowlers bowl at own batters: rules 3, 8.
- Player page 6 s or 45 s slow after a rollup change: CTE wall (rule 23), or `player_categories` running a correlated EXISTS per grade row. Find what every endpoint on the page calls.
- Import 504, 413 or a vanished POST body: rule 20.
- "Steve" beside "Steven": rule 26. Brad K Mant missed: rule 27. One Day Grade 2 into Grade 4: rule 28. 1974 card under 1999/00: rule 13. Card invisible under every season: rule 15.
- Harness: suites share one database and stub tables collide (`player_achievements.org_id`): use a fresh one. StatLab path needs lifespan-only `grade_merge_logs`; views need `_view_ddl.py`. Check `origin/main` before numbering a migration.

## How to verify a change here

Real Postgres, shipped route bodies, and a control run that REPORTS rather than crashes. A check on an empty fixture or a crashed control proves nothing.
- `backend/verification/`: `verify_manual_game_check.py` (control reports 142/7), `verify_scorebook_innings.py` (control "None v None"), `verify_csv_innings_import.py`, `verify_manual_side_names.py`, `verify_manual_winner.py`, `verify_manual_games_import.py`, `verify_import_team_labels.py`, `verify_junior_residual_scope.py`, `verify_short_form_match.py`, `verify_grade_duplicates.py`, `verify_season_resolve.py`. Browser twins: `frontend/verification/`.
- Diagnose live data first: `ops/diagnostics/csv_import_unpaired.sql`.

## Operator commands and scripts

All dry run by default; `--apply` acts.
- `python -m app.scripts.fix_stray_innings_totals <org|all> [--apply]`: NULLs total/wickets/overs on our innings identical to the opposition's (batters listed, batters plus extras not already equal). Audit entry with before and after, undoable.
- `python -m app.scripts.settle_manual_winners <org|all> [--apply]`: fix contradicted winners. Run for Hamilton.
- `python -m app.scripts.repair_overwrite_pairs <org|all> [--apply]`: pair matches an overwrite import left unpaired (import-created, re-sourced seasons only). Read the held-back list first; run `all` after v9.90.3.
- `python -m app.scripts.reconcile_imports <org>`; `python -m app.scripts.reconcile_milestones <org|all> [--apply]`. Shoalwater recovery: undo the CSFW batch, re-import `manual_games_scorecards.csv`, then both repair scripts.
- `python -m app.scripts.remove_cross_attached_imports <org> <keeper-player-id> <other-player-id> [--apply]`: removes the keeper's `imported_stats` rows that are figure-for-figure copies of the other player's (two same-name players given one sheet line), audits each, rebuilds the import deltas and reads the season-less line back. Never touches hand-typed adjustments (reports them).
- `python -m app.scripts.purge_import_only_players <org-id-or-slug>`: cleanup for batches undone before 234, one club at a time.
- `python -m app.scripts.cleanup_seasons <org-id-or-slug>`; `python -m app.scripts.refile_manual_game_seasons <org|all>` (grade carried BY NAME); `python -m app.scripts.scorecard_eval <cases_dir>`.

## Open follow-ups

- Shoalwater holds seven short-form pairs (Boddy, Fletcher, Hankey, Johnson, Marwood, Spinks, Trigg): Merge Duplicates; check Fletcher first.
- Team cards under header columns not built. No nightly sweep of staged sheets. `POST /games/import` has no size cap.
- Grade duplicates: opponent-overlap confirmation not built; AFL `routers/afl/merge.py` untouched. `_enrich_player` on Merge Duplicates cards ignores `imported_stats`.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-IMP-1] Archive says the upload cap was 8 MB | code has 64 MB (`_MAX_GAME_UPLOAD_BYTES`, nginx `64m`) | THE SHEET IS PARSED ONCE (L10460-10557) | keep rule 20, ignore the number
- [FLAG-IMP-2] 309's `import_authoritative` whole-season model versus later per-match pairing | `import_authoritative` still in `superseded_ddl.py`, so both are live in the views | A RE-SOURCED SEASON COUNTS PER MATCH (L641-788) | verify with `cricketstatz-import` before changing either
- [FLAG-IMP-3] Section says the 037 fan-out was "NOT fixed", then "FIXED" | later wins | same section | keep rule 21
- [FLAG-IMP-4] Fix credits migration 169 for `v_effective_games` columns | `superseded_ddl.py` re-issues that view every boot, so edits in 169 alone are lost | Uploaded scorecard missing (L15560-15609) | keep rule, edit the view in `superseded_ddl.py`
- [FLAG-IMP-5] Reader notes cite `anthropic 0.40.0` | still pinned in `requirements.txt`; claims age | Scorecard reader (L15646-15737) | verify on any bump

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| A game that does not add up is warned about, never refused (v9.99.2) (L32-75) | rules extracted | Rules 1, 2 |
| An importer pre-selects "Steve" for the club's "Steven" (v9.97.2) (L190-238) | rules extracted | Rule 26 |
| A scorebook import carries the opposition, the score and the stands (migration 311, v9.97.0) (L239-398) | rules extracted | Rules 3 to 7, 12 |
| (sub) v9.97.1 opposition named on other readers | rules extracted | Rule 7 |
| (sub) Template, single sundries figure, edit undo (v9.98.2) | rules extracted | Rules 6, 8 |
| (sub) Our innings named for the match's team (v9.98.6) | rules extracted | Rules 10, 11, 12 |
| (sub) Recorded winner contradicted (v9.98.7) | rules extracted | Rule 9 |
| A RE-SOURCED SEASON COUNTS PER MATCH (migration 309, v9.90.3) (L641-788) | rules extracted | Rules 21, 22, 24; Flags 2, 3 |
| (sub) v9.90.4 follow-ups (score guard, CTE wall, fan-out, StatLab) | rules extracted | Rules 21 to 23 |
| A SHEET SPLIT BY TEAM IS NOT A SHEET SPLIT BY GRADE (v9.89.1) (L1531-1576) | rules extracted | Rule 25 |
| Suggested duplicate grades: the discriminator rule (migration 294, v9.70.1) (L2887-2995) | rules extracted | Rules 28, 29; Follow-ups 4 |
| A duplicate whose first name is shortened is invisible to edit distance (v9.26.1) (L6940-7000) | rules extracted | Rule 27; Follow-ups 5 |
| Season list tidy-up script (v9.19.4.2) (L7749-7780) | rules extracted | Rule 17 |
| Seasons are editable and deletable from the Seasons page (v9.19.5) (L7781-7812) | rules extracted | Rule 16 |
| Undoing a stats import deletes the players it minted (migration 234, v9.19.4.1) (L7813-7853) | rules extracted | Rule 30 |
| THE SHEET IS PARSED ONCE, NOT CARRIED BY THE BROWSER (migration 302, v9.77.0) (L10460-10557) | rules extracted | Rules 18 to 20; Follow-ups 3; Flag 1 |
| A game brings its own season with it (v9.54.2) (L10558-10636) | rules extracted | Rules 13, 14 |
| Uploaded scorecard missing from the public Games page (migration 169, v8.76.1) (L15560-15609) | rules extracted | Rule 15; Flag 4 |
| Uploaded scorecards log, edit/undo from the upload page (v8.76.2) (L15610-15645) | rules extracted | Rule 32 |
| Scorecard reader, multi-format, PDFs, fielding column, eval set (v8.80.0) (L15646-15737) | rules extracted | Rule 31; Flag 5 |
| (sub) v8.80.1 tracked-fields toggles, roster matching | rules extracted | Rule 31 |
| (sub) v8.80.2 name cross-referencing | rules extracted | Rule 31 |
| (sub) v8.80.3 card-error versus misread | rules extracted | Rule 31 |
