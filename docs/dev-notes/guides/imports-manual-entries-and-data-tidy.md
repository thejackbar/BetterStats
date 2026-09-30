# Guide: Imports, manual entries and data tidy-up

**Read this before**:
- Touching `routers/manual_entries.py` (manual games, `_replace_game_children`, `_restore_extra_children`, the `/games/import/*` preview, resolve and commit routes, `/games/check`, `/seasons/for-date`, `update_season`).
- Touching the scorebook or CSV match import (`GAME_CSV_COLUMNS`, the CSFW converter, the downloadable template) or `services/scorebook_innings.py`, `game_import_staging.py`, `manual_result.py`, `manual_game_check.py`, `game_sides.py`, `season_resolve.py`.
- Touching the stats importers and reconcile (`import_ingest.py`, `import_reconcile.py`, `routers/imports.py`, `match_pairing.py`, `import_cleanup.py`) or the name matchers behind them.
- Touching Merge Duplicates or Manage Grades suggestions (`admin._name_variant_pairs`, `_fuzzy_name_pairs`, `services/grade_duplicates.py`).
- Touching the scorecard photo/PDF reader (`services/scorecard_ocr.py`, `AdminScorecardUpload.jsx`).
- Touching `MatchScorecard.jsx` header or side-splitting, `games._manual_side_names`, `games._merge_manual_innings`.
- Symptoms: "All" reads lower than "Men's"; a game shows the same score for both sides; "— vs —" on imported matches; imported player minted as "Steve" beside "Steven"; a 1970s card filed under a 1999 season; a 24 MB CSV that will not upload; undo leaves imported players behind; an uploaded card missing from the public Games page.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/imports-manual-entries-and-data-tidy.md`. Grep hints: `stray innings`, `short_form`, `innings_order_known`, `re-sourced`, `is_team_labelled`, `discriminator`, `name_variant`, `cleanup_seasons`, `import_batch_id`, `staging`, `for-date`, `grade-less`, `exclude_id`, `balls_per_over`, `card_error`.

**Related guides**: `cricketstatz-import` (the per-match pairing and `superseded_ddl.py` own the effective views these imports feed), `stats-figures-records-and-filters` (scope, competitions, rate coverage), `cross-club-and-data-safety` (shared-fixture and never-delete-manual-work rules), `data-sources-and-sync` (sync and the `sync_runs` reconcile at the end).

## Standing rules

**Manual games and the scorebook CSV**
1. A hand-entered innings stores no total, wickets or overs when its side is "us". `_replace_game_children` nulls them, the form clears them on `setInningsSide` and never sends them in `buildPayload`. Why: `_merge_manual_innings` lets a recorded `total_runs` replace the batters' sum, so a stray copy on our innings shows the opposition total twice. The CSV import still records OUR total (`innings_total`) legitimately, so the merge keeps honouring one. Fix at the source, never in the merge.
2. A game that does not add up is warned about, never refused. `services/manual_game_check.check_game` is the one definition, read by `POST /manual-entries/games/check` (writes nothing). A failed check draws nothing and must not stop a save. Clubs entering scorebooks often lack a figure.
3. The CSV carries the opposition, our and their innings figures and the fall of wickets (`opp_innings_number`, `batting_order_known`, `innings_*`, `opp_*`, `fow_wicket`, `fow_score`, `innings_extras`, `opp_extras`, `bowling_order`). Innings meta is read off every row BEFORE the blank-player skip, because a match with nobody of ours named still carries the opposition's innings.
4. Our bowlers are filed under the OPPOSITION's innings number. A sheet giving opposition figures with no `opp_innings_number`, or one innings given as both sides', is refused.
5. `innings_no` is not batting order (the converter numbers by leg, ours 2n-1, theirs 2n, and sends `batting_order_known=false`). `manual_games.innings_order_known` records it. NULL (every older game) reads as known. When false the match page draws "INNINGS" unnumbered, no winning margin, no HOME/AWAY for blank teams, and says why.
6. Partnerships are derived by `scorebook_innings.derive_partnerships` and REFUSED (None) on a gap, a batter out who is not at the crease, a score going backwards or a wicket-count mismatch. A stand credited to the wrong pair on a record board is worse than none.
7. `_EXTRA_GAME_CHILDREN` puts fall of wickets, partnerships and innings figures in the edit/delete snapshot. `_restore_extra_children` is the one restore loop and only replaces a child table the snapshot actually holds. Why: an edit logged before these were snapshotted has no keys, and reading "absent" as "none" would delete a scorebook import's fall of wickets the edit never touched.
8. Imported matches leave `home_team`/`away_team` blank, so `services/game_sides.sides_sql` (Python twin in `_fetch_manual_games_as_list`) names a blank pair from the club and its opposition, with `home_away_known=false`. Any new reader of those two columns must go through it or it shows "— vs —".
9. The CSV template is built from dicts keyed on column name (never positional), uses the downloading club's name, and models `opp_innings_number` for bowling. A positional example drifted one column out and filed bowlers against their own batters.
10. Fetch `origin/main` before building on an import format. A second CSV scheme was written and thrown away because the first had already shipped.
11. `services/manual_result.py` is the one winner rule (CSV import, hand-entry create and update, `settle_manual_winners`). It changes `winning_team` only when the result line opens Won/Lost, the recorded winner names the other side, it is one innings each and the scores agree with the result line. A tie, a missing total or a rain-rule result is left as entered. Scores are only worked out (via `get_scorecard`) for games whose winner and result line already disagree.
12. Our innings is named for the team the match says, not the club: `games._manual_side_names` (ours is whichever of home/away is not the opposition, punctuation-insensitive, else the side sharing a non-generic word with the club name, else the single named side that is not the opposition, else the club name). Frontend `AGE_TOKEN` (`/^[uo]?\d+s?$/`) keeps "60s" and "U14" generic, `sidesSwapped` judges both sides against both teams, and `splitSides` files by exact normalised name first (with one side seen it needs every distinctive word shared).
13. The header stays home/away and the team cards stay in batting order (the Wisden and Cricinfo convention, and an earlier owner instruction). The club asked for cards under their header columns: raised, not built.
14. Manual spells keep insertion order: every read of manual spells orders by `id` (scorecard, edit form, snapshots) so `bowling_order` and later undo survive. No migration needed.

**Seasons and grades on manual games**
15. `manual_games.season_id` is NOT NULL but optional on the wire. Omit it and `_resolve_game_season` files the game under the season its own date falls in, creating it (and the grade, via `grade_name`, writing BOTH `category` and `categories`) if the club has none. An explicit season still wins. The club year starts in JULY everywhere; the rule is server-side in `services/season_resolve.py` (`canonical_name`, `season_start_year`, imported back by `cleanup_seasons`).
16. A season's year is read off its NAME first, then the `year` column (manual seasons can have NULL year). A year with several seasons picks the canonically named one, then a synced one. `GET /manual-entries/seasons/for-date` is read-only on purpose: it runs when a card is read, before anyone decides to import. A season/date mismatch is said aloud, never refused.
17. A manual game may have no `grade_id` but always has `season_id` and `organisation_id`. Read the view's own `season_id`/`organisation_id` from `v_effective_games`, never derive them through `grade_id`, and never test ownership with a bare `g.source = 'manual'` (cross-club leak). `list_games`' `api_games` sub-query scopes to `source='api'` only.
18. `PATCH /club-admin/seasons/{id}` edits name/year for ANY season (the sync never overwrites a season's name, only backfills a NULL year). Delete is manual-only and empty-only, and `_season_in_use` must include `player_season_stats` and `imported_stats` (both cascade). `GET /club-admin/seasons` returns `synced` (`grassroots_id IS NOT NULL`), not `synced_at`, to decide if Delete is offered.
19. `cleanup_seasons` writes only manual seasons (`grassroots_id IS NULL`), MERGES duplicates through `season_aliases` (undoable, chain re-pointed to keep resolution single-hop), renames a manual season with no synced sibling to "Summer YYYY/YY" with its `year`, and refuses to guess when several synced seasons exist and none is named plain "Summer YYYY/YY", or a name has no "YYYY/YY" token.

**Large sheets**
20. The sheet is parsed once and staged (`manual_game_import_staging`, `services/game_import_staging.py`, migration 302, 1 hour TTL). Resolve and commit name it by token; `rows` stays accepted on the request as the direct-caller fallback (`_rows_for` prefers the token). Why: the wizard re-posted every row as JSON on each resolve (145 MB for a 33 MB sheet), and resolve fires again on every override change.
21. Staged rows are a TABLE, never the media volume: they are deleted at commit and must not be backed up. Scope by club AND user in the WHERE clause (not fetch then check) so wrong, expired and unknown tokens are indistinguishable. Expiry is enforced on read, the sweep (on preview) only tidies. The token is spent in the same transaction as the games (rolled back means retryable, landed means not importable twice).
22. `_MAX_GAME_UPLOAD_BYTES` (`manual_entries.py`) and the nginx `client_max_body_size` on the preview location MUST move together (nginx refuses the body before FastAPI). Resolve and commit have their own locations for the TIMEOUT (a big write is 68 to 124 s, past nginx's 60 s default, which gives the browser a 504 while the job finishes). Use exact `location =`: a trailing-slash prefix makes nginx 301 `POST /games/import` and drop the body. The strict single-shot `POST /games/import` stays on the ordinary `/api/` limits (no app-level size cap).
23. The commit needs no chunking: `_write_games` gives each game its own savepoint and flushes as it goes. The preview's own `rows` reply is capped at the old 8 MB limit, but the token key is always returned.

**Import pairing and season totals (re-sourced seasons)**
24. A season total has no per-match granularity, so an overwrite import (marks a season `import_authoritative`) counts the WHOLE season from scorecards: the `api_scorecard` branch of `v_effective_player_season_stats` rolls up every synced game in a re-sourced season with no preferred imported twin (from `batting_innings`, `bowling_spells`, `fielding_stats`, `game_appearances`, org-scoped through `players`). The import's own rollup counts the matches the file held. The two are disjoint by construction ("and, not or").
25. In those rollups aggregate each table on its own, THEN join. Never LEFT JOIN batting, bowling and fielding on one (player, game) key (a player who batted twice and bowled once reads 2 spells, 4 wickets, 2 catches).
26. A fixture the other club synced first is keyed onto our own season for the same real season (CA season guid first, year second, `LATERAL ... LIMIT 1` so a year with two rows counts once), filed on THEIR grade id.
27. The matcher: `_existing_game_index` covers the club's season OR either side of the fixture; a sheet match the date rule leaves unmatched gets a second look through `match_pairing.assign` (the CricketStatz matcher's rules, never a second copy) on a `(player_id, runs)` signature; `match_pairing.load_synced` is the one query all three readers of the synced side share. A re-import must inherit the old row's pair, or the synced copy comes back beside it.
28. `repair_overwrite_pairs` (after the fact) holds back any proposed pair with 0 shared scores ("held back, check by hand"): every imported match carries the sheet's card, so a zero-score pair is a cardless synced game, usually a junior fixture the archive never tracked. The live matcher is unchanged.
29. CTE materialisation: a `WITH` CTE referenced more than once is MATERIALIZED and the outer `player_id = X` cannot enter it. Player-dependent CTEs are `NOT MATERIALIZED`. `auth_games` does not depend on the player, so it stays `AS MATERIALIZED` (inlining it cost 45 s on `/stats`). Inline a CTE only when there is a predicate to push into it. Its shared-fixture arm is driven FROM the re-sourced seasons through indexed `home_org_id`/`away_org_id` with `DISTINCT ON (g.id)`.
30. StatLab's `appear` CTE unions the four match sources `_scoped_games_played` unions (an imported match never has a `game_appearances` row), with the called-off rule on the roster arm only.
31. Imported and manual games are never deleted by a sync or a full rebuild (see the never-delete rule in `cross-club-and-data-safety`).

**Team-labelled sheets and name matching**
32. `import_reconcile.is_team_labelled` (two or more grade labels in the org's imported rows) switches reconcile to per-player against the WHOLE GR record, season by season (ungraded path). Labels are still stored, pre-GR season deltas keep their team (`season_rows_by_grade`), the career residual carries no grade. Commit and preview (`routers/imports.py::_resolve`) must make the same call, and the preview reads earlier uploads too. Accepted cost: separate 1st/2nd sheets are read as the whole book, so a grade CA has that the sheets omit is not topped up per grade. `covered_by_year` treats a season as covered when GR holds that YEAR under any season row. The expected result is the ONLINE figure whenever online holds more. Recovery needs no re-import: `reconcile_imported_totals` rebuilds from `imported_stats` and runs at the end of every sync.
33. Short-form first names ("Steve" for "Steven") are a separate step, not a change to `match_players` (12 callers). Only the two stats importers opt in through `import_ingest.short_form_suggestions` / `apply_short_form_suggestions`. `is_short_form` is the one rule (same surname, one first name a prefix of the other, at least 3 letters, middles compatible; Bob/Robert never claimed) and `admin._first_name_link` calls it, so the importer and Merge Duplicates cannot disagree.
34. A short-form suggestion is PRE-SELECTED, never silent (status `suggested`, note names both careers). Refuse it where two club players fit, or where another name on the SAME sheet reaches that player. Careers more than `MAX_CAREER_GAP_YEARS` (5) apart are offered, not chosen (son under his father's name); an undated career does not block; overlap deliberately does not block. Run it BEFORE the overrides so a person's own answer wins.
35. Merge Duplicates has three tiers: exact, fuzzy (`FUZZY_MERGE_THRESHOLD` 0.90) and `name_variant` (`_name_variant_pairs`, blocked on surname plus first initial, using `_name_parts`/`_middles_compatible` IMPORTED from `import_ingest`). Edit distance degrades multiplicatively (short form plus a middle initial is 0.78), so never fix a miss by lowering the threshold. Never claim a nickname that is not a prefix; 2 characters is too short. Detection files a player under BOTH `name` and `display_name` (`_name_keys`), keeps the best ratio per pair and an `emitted` set stops duplicates.
36. Bulk Approve is an allowlist (`isExactPair`), not `kind !== 'fuzzy'`. A new suggestion tier is manual-confirm until someone decides otherwise. The same allowlist idea is `BULK_SAFE_KINDS` for grade suggestions.

**Grade duplicate suggestions**
37. `admin._fuzzy_name_pairs` must never be pointed at grade names. Grades differ by a discriminator (number, bare letter, colour, announced match format) that IS the meaning, and edit distance ranks different grades above real duplicates (One Day Grade 2/4 0.93, A Grade / A Grade (Gatorade) 0.56). `services/grade_duplicates.py` requires discriminating tokens IDENTICAL; tiers `same_name`, `extra_words`, `word_typo` (only after discriminators match). Format is read off the RAW name via `suggest_formats` (catches "(One Day)"). Synonyms EXPAND abbreviations (division to div is wrong); `_PREFIX_SYNONYMS` fire only on letters stuck to a number.
38. The association is a VETO (`grades.association_id`, migration 283), category clash and coexistence in one season are only CAUTIONS. Only `same_name` is bulk-safe, and not if the two coexisted. Direction is a suggestion (fuller record kept, card can flip it). Pairs are built from `list_grades_with_stats` so an already-merged group is never suggested against itself. `grade_merge_pair_ignores` (294) keys on NAMES, stored sorted; `services/grade_ignore_ddl.py` is the one DDL copy for alembic and the lifespan. The CA grade GUID cannot link grades: it is minted fresh every season.

**Undo and cleanup of stats imports**
39. `players.import_batch_id` (migration 234) marks a player the import commit itself minted (NULL for synced or hand-added, `ON DELETE SET NULL`). A re-import moves the marker forward, only where already non-NULL. `services/import_cleanup.deletable_players` is the one rule for both undo endpoints and the script: delete only when none of ~40 `BLOCKING_REFS`, no profile data, no `grassroots_id`/`playhq_id`. Derivative rows do not block. The emptiness check runs AFTER `db.flush()`. Kept players are reported with reasons and the audit row names both.

**Scorecard reader**
40. Uploads never teach the model; the eval set is the training loop. Run `scorecard_eval` before and after any prompt, schema or model change (`docs/scorecard-reader-eval.md`).
41. The reader transcribes faithfully. The ONE allowed deviation is result inference when the result box is blank and the innings decide it, flagged `result_inferred` for review. `reconcile()` returns `[{kind, text}]`: `card_error` (the card's own figures disagree, fix-or-keep) versus `misread` (likely reader error). Nothing auto-corrects. The frontend tolerates old plain-string warnings via `asWarn`.
42. Unticked "This card tracks" columns import as NULL, not 0 (`manual_batting_innings.fours/sixes`, `manual_bowling_spells.maidens/wides/no_balls`, migration 184). Pydantic defaults stay `Optional[int] = 0`, so only an EXPLICIT null means "not recorded" (CSV and hand-entry omit the fields).
43. Pre-1980 Australian cards use 8-ball overs (`match.balls_per_over`, honoured by `overs_to_balls` and the overs reconcile). DB storage is unchanged (overs as written). `innings[].fielding` merges with dismissal-derived fielding by max per stat; re-edit seeds it from saved `fielding_stats`.
44. Name cross-referencing: read EVERY occurrence of a name, the bowling analysis is authority for bowler names and the batting order for batters, but never merge two players that only share a surname. `_name_close` (0.6) advises when a dismissing bowler is not among the analysed bowlers. Roster matching goes through `import_ingest.match_players`: auto-fill exact hits and a single candidate at 0.9 or more, everything else ships as `match_info` candidates. `_suggest_player` stays for import-time FOW/partnership names, deliberately.
45. Jump-back edit reuses the upload review UI from `extracted_payload` (photo uploads only; `is_photo_upload`, `created_by_name` on the list; the list pops the blob). Save calls `PATCH /games/{id}`, a fresh read clears `editingId`. `check_scorecard_duplicate` takes `exclude_id`. Delete and restore go through the one audit trail (`/admin/manual-entries#audit`). PDFs go to the API as native `document` blocks (mind the ~32 MB request cap).

## Traps and failure signatures

- Both innings show the same total, e.g. 142/7/40 twice: a total typed while the innings was Opposition, then flipped to Ours (rule 1). Repair with `fix_stray_innings_totals`.
- "All" reads LOWER than "Men's", or a filter raises a total: an overwrite import stepped a whole season's CA summary aside and dropped the matches the file did not hold (rules 24 to 28).
- Imported match lists as "— vs —" or `home_team: None` on Games, Team pages or a player's innings tables: a reader bypassed `game_sides.sides_sql` (rule 8).
- Header shows each score under the other side's name, or "Portland Over 60s" scores partial-match "Mt Gambier Over 60s": club name used for our side or "60s" read as a club word (rule 12).
- Bowlers appear to bowl at their own batters: filed under our innings number, or the template example drifted (rules 4, 9).
- Undoing an EDIT wipes a scorebook import's fall of wickets: restore loop treated absent snapshot keys as "none" (rule 7).
- Player page 6 s or 45 s slow after a change to the rollup views: materialised CTE wall (rule 29), or `player_categories` correlated EXISTS over `v_effective_games` per grade row. Look for the thing every endpoint on the page calls, not the thing that changed.
- Import bounces with a 504 while the job finishes, or 413 before FastAPI: nginx timeout or body cap out of step (rule 22). A POST body vanishing: prefix `location` 301 (rule 22).
- Imported "Salter, Steve" beside the club's "Steven": short-form step off or "Create all" swept unmatched rows (rules 33, 34).
- Merge Duplicates misses Brad K Mant / Bradley Mant: whole-string edit distance (rule 35). Grade suggestions offering One Day Grade 2 into Grade 4: edit distance on grade names (rule 37).
- A 1974 card filed under "Summer 1999/00": season required from a list that cannot hold the right one (rules 15, 16).
- Uploaded card invisible on the public Games page under every season: grade-less game joined through `grade_id` (rule 17).
- A season with imported history deleted straight through: `_season_in_use` missed `player_season_stats`/`imported_stats` (rule 18).
- Undo leaves surname-only players: no `import_batch_id` marker (rule 39); older batches need `purge_import_only_players`.
- Verification harness traps: suites share one database and their stub tables collide (`player_achievements.org_id`); run a suite whose stubs differ on its own database. `verify_manual_games_import.py` StatLab path needs lifespan-only `grade_merge_logs`. The views need `_view_ddl.py`.
- Migration numbering: two migrations with one revision id break Alembic outright. Check `origin/main` at merge time (294 was renumbered this way).

## How to verify a change here

Run against a real Postgres, through shipped route bodies, with a control run that REPORTS rather than crashes (read new keys with `.get`, wrap commit calls, gate blocks on the feature existing).
- `backend/verification/verify_manual_game_check.py` (control with writer change neutered fails and reports 142/7) and `frontend/verification/verify_manual_game_check_browser.mjs`.
- `verify_scorebook_innings.py` (control reports "None v None", no opposition innings) and `verify_scorebook_import_browser.mjs`; `verify_csv_innings_import.py` (three controls: previous commit, edit snapshot alone, key guard alone); `verify_manual_side_names.py` and `verify_manual_scorecard_sides_browser.mjs`; `verify_manual_winner.py`.
- `verify_manual_games_import.py` (largest suite: staging, pairing, aggregate agrees with per-innings views to the run, plan has no CTE Scan and the player id on every scan, StatLab match count).
- `verify_import_team_labels.py`, `verify_junior_residual_scope.py`, `verify_short_form_match.py` (+ `_browser.mjs`), `verify_grade_duplicates.py` (+ `_browser.mjs`; control swaps in SequenceMatcher 0.90), `verify_season_resolve.py` (+ `verify_scorecard_season_browser.mjs`), `verify_manual_innings.py`, `verify_manual_scorecard.py`.
- Neighbours to re-run for any rollup or view change: manual games import, cricketstatz import, match coverage, club records, competitions, rate coverage.
- Checks that cannot fail are not checks: a check against an empty sheet, an empty fixture or a control that crashes on the first missing key proves nothing. Assert the fixture holds what the rule reads (e.g. the player's `sheet` figures summed from the rows).
- Diagnose live data before changing code: `ops/diagnostics/csv_import_unpaired.sql`.
- Playwright: probe waits on the form's own field, not `text=Season` (matches the sidebar "2026/27 SEASON").

## Operator commands and scripts

All dry run by default; `--apply` acts.
- `python -m app.scripts.fix_stray_innings_totals <org|all> [--apply]`: NULLs total/wickets/overs on our innings that carry the SAME runs, wickets and overs as the opposition's, batters listed, batters plus extras not already equal. Writes an audit entry with before and after (undoable in the Audit tab).
- `python -m app.scripts.settle_manual_winners <org|all> [--apply]`: correct a recorded winner the result line and scores both contradict. Run for Hamilton Veterans after deploying v9.98.7.
- `python -m app.scripts.repair_overwrite_pairs <org|all> [--apply]`: pair imported matches an earlier overwrite import left unpaired. Only import-created matches, only re-sourced seasons. Read the held-back list before `--apply`. Run for every club with a re-sourced season after v9.90.3 (only Shoalwater Bay had it run).
- `python -m app.scripts.reconcile_imports <org>`: rebuild import deltas from `imported_stats` now (also runs at the end of every sync).
- `python -m app.scripts.reconcile_milestones <org|all> [--apply]`: re-run for a club after a re-import (Shoalwater recovery: undo the earlier CSFW batch, re-import the regenerated `manual_games_scorecards.csv`, then `repair_overwrite_pairs` and `reconcile_milestones`).
- `python -m app.scripts.purge_import_only_players <org-id-or-slug>`: retroactive cleanup for import batches undone before migration 234. One club at a time on purpose; a person reads the list.
- `python -m app.scripts.cleanup_seasons <org-id-or-slug>`: uniform season list (manual seasons only).
- `python -m app.scripts.refile_manual_game_seasons <org|all>`: refile manual games under the season their date falls in, grade carried BY NAME.
- `python -m app.scripts.scorecard_eval <cases_dir>`: score the reader against local golden cases (never committed).

## Open follow-ups

- `settle_manual_game` reads the same totals a stray copy would have corrupted; it reads correctly once the copy is gone (kept as a note).
- Shoalwater still holds seven short-form pairs (Boddy, Fletcher, Hankey, Johnson, Marwood, Spinks, Trigg): Merge Duplicates; check Fletcher Greg/Gregory first.
- Club feedback to seat team cards under their home/away header columns: raised, not built.
- Staged sheets expire only on the next preview; a nightly sweep was judged not worth a job. Strict single-shot `POST /games/import` has no app-level size cap.
- Grade duplicates: opponent-overlap confirmation not built (needs `club_match_keys` name matching). AFL Merge Grades (`routers/afl/merge.py`) untouched.
- `_enrich_player` (Merge Duplicates cards) counts `player_season_stats` and `batting_innings` only, so a BetterImport-only player reads 0/0/0/0.
- Season tidy: no automatic run; a synced season with a NULL year only gets a year from the sync.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-IMP-1] Archive says `_MAX_GAME_UPLOAD_BYTES` "refused anything over 8 MB" and the preview cap is "the old 8 MB limit" | code now has `_MAX_GAME_UPLOAD_BYTES = 64 * 1024 * 1024` and nginx `client_max_body_size 64m` on the preview location, so the 8 MB figure is history | THE SHEET IS PARSED ONCE (L10460-10557) | keep (rule 22 states the pairing, not the number)
- [FLAG-IMP-2] The 309 design ("re-sourced season", `import_authoritative`, whole season counted from scorecards) sits beside the later per-match pairing design (`superseded_by_game_id`, `pair_prefers_import`, "an AND, not an OR") | `import_authoritative` is still in `superseded_ddl.py` (lines 73 to 75, 231, 410), so both are live in the views; the CricketStatz archive says `seasons.stats_source` is read by nothing | A RE-SOURCED SEASON COUNTS PER MATCH (L641-788) | verify against `cricketstatz-import` guide before changing either view
- [FLAG-IMP-3] Same section says the `manual_game` rollup 037 fan-out was "Noticed, NOT fixed there" and, later in the same section (v9.90.4), "THE 037-SHAPE FAN-OUT IS FIXED" | internal contradiction, the later bullet wins | A RE-SOURCED SEASON COUNTS PER MATCH (L641-788) | keep rule 25
- [FLAG-IMP-4] Uploaded-card fix credits migration 169 for `v_effective_games` carrying `season_id`/`organisation_id` | `superseded_ddl.py` now owns and re-issues `v_effective_games` on every boot; a change to the view made only in migration 169 is lost at restart | Uploaded scorecard missing from the public Games page (L15560-15609) | keep the rule, make view edits in `superseded_ddl.py`
- [FLAG-IMP-5] Archive says "Twelve callers use `match_players`" and quotes suite check counts (194, 305, 47...) | counts drift with every change | An importer pre-selects "Steve" (L190-238) | verify with grep before relying
- [FLAG-IMP-6] Scorecard reader notes cite "anthropic 0.40.0 passes the dict through" and a Toowoomba archive | `backend/requirements.txt` still pins `anthropic==0.40.0`; model/SDK claims may age | Scorecard reader (L15646-15737) | verify on any SDK or model bump
- [FLAG-IMP-7] Archive notes the header-column card layout was "raised, not built" while another entry says a deliberate v8.79.2 instruction fixed batting order | not conflicting, but the owner decision is unresolved | Our innings is named for the team (v9.98.6) | keep, ask before changing

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| A game that does not add up is warned about, never refused (v9.99.2) (L32-75) | rules extracted | Standing rules 1, 2; Operator commands (`fix_stray_innings_totals`); Open follow-ups 1 |
| An importer pre-selects "Steve" for the club's "Steven" (v9.97.2) (L190-238) | rules extracted | Standing rules 33, 34; Traps bullet 8; Open follow-ups 2; Flag 5 |
| A scorebook import carries the opposition, the score and the stands (migration 311, v9.97.0) (L239-398) | rules extracted | Standing rules 3 to 8, 14; Operator commands (Shoalwater recovery) |
| &nbsp;&nbsp;v9.97.1 names the opposition on other readers | rules extracted | Standing rule 8 |
| &nbsp;&nbsp;The template a club downloads, a single sundries figure, edit undo (v9.98.2) | rules extracted | Standing rules 7, 9, 10 |
| &nbsp;&nbsp;Our innings is named for the team the match says, not the club (v9.98.6) | rules extracted | Standing rules 12, 13, 14; Traps bullet 4; Flag 7 |
| &nbsp;&nbsp;A recorded winner the result and the scores both contradict (v9.98.7) | rules extracted | Standing rule 11; Operator commands (`settle_manual_winners`) |
| A RE-SOURCED SEASON COUNTS PER MATCH, NOT PER SEASON (migration 309, v9.90.3) (L641-788) | rules extracted (partly overlaps the pairing design in the cricketstatz archive) | Standing rules 24 to 31; Traps bullets 2, 6; Flags 2, 3 |
| &nbsp;&nbsp;v9.90.4 shared-score pair guard, materialised CTE, `auth_games`, `player_categories` | rules extracted | Standing rules 28, 29; Traps bullet 6 |
| &nbsp;&nbsp;v9.90.4 037 fan-out fix and StatLab `appear` CTE | rules extracted | Standing rules 25, 30 |
| A SHEET SPLIT BY TEAM IS NOT A SHEET SPLIT BY GRADE (v9.89.1) (L1531-1576) | rules extracted | Standing rule 32; Operator commands (`reconcile_imports`) |
| Suggested duplicate grades: the discriminator rule (migration 294, v9.70.1) (L2887-2995) | rules extracted | Standing rules 37, 38; Traps bullet 9; Open follow-ups 5 |
| A duplicate whose first name is shortened is invisible to edit distance (v9.26.1) (L6940-7000) | rules extracted | Standing rules 35, 36; Open follow-ups 6 |
| Season list tidy-up script (v9.19.4.2) (L7749-7780) | rules extracted | Standing rule 19; Operator commands (`cleanup_seasons`) |
| Seasons are editable and deletable from the Seasons page (v9.19.5) (L7781-7812) | rules extracted | Standing rule 18; Traps bullet 12 |
| Undoing a stats import deletes the players it minted (migration 234, v9.19.4.1) (L7813-7853) | rules extracted | Standing rule 39; Operator commands (`purge_import_only_players`) |
| THE SHEET IS PARSED ONCE, NOT CARRIED BY THE BROWSER (migration 302, v9.77.0) (L10460-10557) | rules extracted | Standing rules 20 to 23; Traps bullet 5; How to verify; Open follow-ups 4; Flag 1 |
| A game brings its own season with it (v9.54.2) (L10558-10636) | rules extracted | Standing rules 15, 16; Operator commands (`refile_manual_game_seasons`); Traps bullet 10 |
| Uploaded scorecard missing from the public Games page (migration 169, v8.76.1) (L15560-15609) | rules extracted | Standing rule 17; Traps bullet 11; Flag 4 |
| Uploaded scorecards log, edit/undo from the upload page (v8.76.2) (L15610-15645) | rules extracted | Standing rule 45 |
| Scorecard reader, multi-format, PDFs, fielding column, eval set (v8.80.0) (L15646-15737) | rules extracted | Standing rules 40 to 44; Operator commands (`scorecard_eval`); Flag 6 |
| &nbsp;&nbsp;v8.80.1 tracked-fields toggles, roster matching | rules extracted | Standing rules 42, 44 |
| &nbsp;&nbsp;v8.80.2 name cross-referencing | rules extracted | Standing rule 44 |
| &nbsp;&nbsp;v8.80.3 card-error versus misread flags | rules extracted | Standing rule 41 |
