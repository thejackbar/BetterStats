# Guide: Career and season figures, rates, milestones, grade/match/competition scopes, StatLab, records, awards

**Read this before**:
- Touching any career, season, leaderboard, record-book, StatLab or profile figure (matches, average, strike rate, economy, milestones).
- Editing `services/grade_scope.py`, `rate_coverage.py`, `dismissal.py`, `game_status.py`, `milestone_totals.py`, `match_coverage.py`, `competition_stats.py`, `competition_grouping.py`, `stats_display.py`, `player_formats.py`, `routers/records.py`, `services/statlab.py`, `StatLab.jsx`.
- Adding a filter, scope param or query that reads `v_effective_player_season_stats` or `game_appearances`.
- Symptoms: a filter that raises a total; header, note and by-grade grid disagreeing on matches; strike rate far too high; a junior season inside a senior career; Records taking 15s; milestones "reached" that are not.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/stats-figures-records-and-filters.md`. Grep hints: `milestone_totals`, `RETIRED NOT OUT`, `A rate is only as good`, `Season × grade matches`, `A washout is not a match`, `StatLab: one player`, `Grade Type / Match Type filters`, `list filters take several values`, `A grade is several things`, `IMPORT RESIDUAL IS CLASSIFIED`, `Junior stats split`, `Awards`, `Stats by competition`, `two match counts`, `Which lens a panel`.

**Related guides**: sync and import guides (writers of `not_out`, `balls`, `match_format`, `status`, residual rows); CricketStatz/import pairing guide (paired twins, per-innings views); BetterSelect and Comms guides only where they reuse `resolve_scope`.

## Standing rules

**Rates (migration 282, `services/rate_coverage.py`, imported as `rc`)**
1. Runs and balls in a rate must come from the same innings. Never `SUM(runs)/SUM(balls)` across a season or career. Only the ratio changes source; runs, innings, wickets keep theirs.
2. Covered innings = `balls IS NOT NULL AND (balls > 0 OR runs = 0)`. Old sync wrote a missing ball count as 0. A genuine 0 off 0 is covered.
3. No scorecards (BetterImport totals): the aggregate stands and the payload says `basis: "aggregate"`. Do not withhold it.
4. Qualification minimums count covered innings/spells, never innings played. Platform default is 0 on purpose (`organisations.stats_min_rate_innings`/`_spells`, NULL = no preference, via `services/stats_display.py`). A viewer's explicit 0 is real: test None, not falsiness.
5. Strike-rate records are per season, never all time.
6. Rates come from the server only; the browser never divides summed balls. Use `rc.with_coverage` (presence-aware, from `sr_counted/sr_of`, `econ_counted/econ_of`) and `batting_rate_columns(extra=...)` when the select includes did-not-bat rows. Every new rate query imports `rc`.
7. Overs are cricket notation (10.2): convert to balls before summing or dividing, everywhere.
8. Per-innings SR is derived on read (`rc.innings_strike_rate_sql`, `NULLIF(balls,0)`), never stored or backfilled; a stored rate is only the fallback where balls were not recorded.
9. Coverage mark is a dagger, never an asterisk. Notes draw only where the figure is short and drawn (`RateFootnote` `when`).
10. StatLab family targets re-derive from covered halves and publish no coverage pair (uniform column contract). Scout and `iq._their_key_players` stay on aggregates.

**Dismissals and matches played**
11. `services/dismissal.py` is the one rule, whole-phrase match, never `LIKE 'retired%'`. CA ids: 0 Did Not Bat, 1 Not Out, 8 Retired Hurt, 13 Retired, 14 Retired Not Out, 15 Absent. 14 (Law 25.4.2) and 8 (from the Law, not measured) are not dismissals; 13 (25.4.3) is.
12. Fix the writer (`sync.py` and the live scorecard merge set `not_out`), not readers. Every average is `innings - not_outs`, kept on the alias in by-opposition, by-venue, by-position, by-grade. A retirement leaves the dismissal donut and unusual dismissals; retired-out stays. `wkts_lost`, `our_wkts_lost` and the fantasy `out` were left alone.
13. `games.status` (266) is CA's word verbatim; `result` NULL cannot tell washout from unplayed. `services/game_status.py` is the one vocabulary (`NOT_PLAYED_STATUSES`; NO RESULT is not in it). A named player with no bat/bowl/field row in a not-played fixture is subtracted.
14. The washout correction lives in `v_effective_player_season_stats` AND in every reader counting from `game_appearances` via `appearance_counts_as_match(alias)` (StatLab `appear` CTE, by-grade, by-season-grade, by-venue, Formats). Ask which source a new match-counting screen reads. Recent-games lists deliberately show washouts. CA's `matches` counts anyone on the team sheet; do not fix it in the caller.

**Grade scope (`services/grade_scope.py`; migrations 228, 229, 259, 283)**
15. `GradeScope` is the one place a category/format/competition selection becomes SQL. Gate on `scope.active`, never `scope is None`. An empty exclusion set emits no clause.
16. Category is EXCLUSION: `col IS NULL OR NOT (col = ANY(excluded))`. A row we cannot categorise (grade-less manual game, residual) is not known junior, so it is kept. Never an include-list. Categories resolve per grade NAME in Python, never in the WHERE.
17. `grades.categories`/`match_formats` are TEXT[]; `grades.category` stays in step with the first entry. Every writer of `category=suggest_category(...)` also writes `categories=` (sync x2, manual_entries x2).
18. Explicit category pick matches ANY of a grade's categories (inclusion). The club DEFAULT and `judge_primary=True` judge the primary category only, else a Girls U16 grade returns to senior careers.
19. Format is per FIXTURE (`games.match_format`, `format_sql_case()` mirrors `format_from_match_type`: change both). Category is per grade. Unlabelled game falls back to its grade's format only if the grade plays exactly one. `format_from_match_type` returns None for unknown strings. A grade whose format cannot be placed is left OUT of an explicit format filter.
20. `clause(col, kind)`: `game` (default), `aggregate` (`AND FALSE` under a format filter: aggregates have no game), `grade` (EXISTS, true grade listings only). A query joining `v_effective_games` is per fixture whatever column the category half uses (`game_alias="g"`). `scope.active` includes `format_active`.
21. A picked grade beats the CATEGORY half only: `GradeScope.formats_only()`. Picked-grade SQL is separate from default SQL: add `{scope_clause}` AND its bind to both (records.py has five fragments).
22. Aggregate-only residual sources `_RESIDUAL_SOURCES = (manual_aggregate, manual_career, import)` are added back under a category scope; never `api` or `manual_game` (double count). Recompute blended averages from summed counts.
23. Import residuals are classified by `grade_label` (v9.89.2): `resolve_scope` builds `excluded_labels`; `clause(..., label_column=...)` is a CASE (grade_id present: by id; label present: by label, `text[]` cast; both NULL: kept). Five residual sites read `pss`: `_career_residuals`, `_residual_totals_cte`, `_season_by_season_scoped`, StatLab family and career/season residuals. The club default is unaffected.
24. Competition axis (283) is an INCLUSION, a subquery on `grades.competition_id` (`ix_grades_competition`), not a grade-id list. Junk, non-uuid or foreign ids drop in `resolve_scope`; an all-junk pick is an ACTIVE filter matching nothing (fail closed). A grade in no competition, a residual and a grade-less manual game drop out (`_fetch_manual_games_as_list` takes the scope; `list_games` resolves scope above the manual fetch).
25. A grade belongs to at most one competition. Competitions are the club's own groups seeded one per association (`grades.association_id`, from `owningOrganisation` on the teams payload). `is_seeded` clears on a person's edit so sync never overwrites naming. `grades.competition_id` is ON DELETE SET NULL. Ungrouped grades show as "Other grades".
26. `resolve_scope_for_player` widens category only when the default leaves a junior-only player empty (`stats_auto_show_played_grades`, 229; `auto_shown`), never a format, default only, profile only. Gate on `scope.category_active`.
27. `organisations.stats_grade_categories` (228): empty or all-junk stores NULL. Age-group regexes end `\d+s?`. `grades-with-stats` computes classification in its own query (unnesting the arrays inflates runs).
28. The filter row is not drawn when a club has nothing to choose (fewer than two competitions, no junior grades) or no season. The additive "Include" row and Grade Type row are never shown together. `api.js` has one `scopeQuery()`.

**Career matches and lenses (say it, never renumber)**
29. Header matches = `SUM(player_season_stats.matches)` (CA, no grade). Any active scope (the club default included) switches to matches we hold a game row for. The by-grade grid uses per season AND grade `max(held, CA per-grade)` plus unplaceable shortfall, inner-joined to grades. Three rules, three questions. Do NOT adopt `max(held, claimed)` in the header (would rewrite ~19k players).
30. `services/match_coverage.py` reads both figures itself, never the caller's current one. Grade-less games count as held. `extra_scorecards` (surplus) and `without_scorecard` (shortfall) are separate, never a negative. The note draws only where they differ, never for last-N or date windows, makes no causal claim it cannot prove, and under a scope names both sources rather than claiming to be the headline.
31. Grid note is summed from its own rows (`held`, asterisks, `unattributed`); `GradeTotalNote` is suppressed while the grid is scoped (its grade-less line uses scope-independent `breakdown_matches`).
32. `get_player_team_breakdown` builds one (season, grade) cell map and derives rows from it, per season, folds seasons via `load_reverse_alias_map`, orders columns by folded grade name (`MIN(display_order)`), shows `unattributed` only when non-zero, does not special-case historical bundle seasons, and keeps the by-grade table sorted by matches.
33. It takes the scope: scorecard side takes all of it; CA per-grade and corrections take category/competition, a format is `aggregate`. The season-total gap heuristic is gated PER SEASON (scoped vs unscoped counts differ = `mixed`, left to scorecards, `seasons_left_to_scorecards`). A senior-only player's grid must be byte-identical under the club default and with no scope.
34. Reach notes (`components/FilterReach.jsx`: `enumeration`, `career`, `unfiltered`) fire on the RAW pick (`catParam`/`fmtParam`/`compParam`), never the club default; name only filters actually on; `FilterReachDot` on tab labels. New panels must declare reach. Teammates and captain-stats take the scope (`_og_cte(scope)`). Honours are career facts, never filtered.
35. Competition pill order is the club's (`display_order`; `POST /admin/competitions/reorder` sends the whole list). Screen is "Grades & Competitions" (display only; `/admin/grades#competitions`).

**Milestones (`services/milestone_totals.profile_totals`)**
36. `profile_totals` is the ONE definition (profile default scope, junior-only auto-widen, batched, ids bound as an array); Milestones page, dashboard, admin report, player card and notification read it. Entries carry `junior_split`, `counts`, and a `variant` entry; the notification dedupe key carries the variant basis. "Without junior" uses `judge_primary=True`.
37. `sync._compute_milestones(reconcile=True)` removes thresholds no longer reached (we are the only writer), keeps dates, runs at the END of sync; a `match_pull_failed` run only adds. A stored milestone is reached on `max(profile figure, whole unscoped career)`. Catch-up adds are undated (`achieved_at` NULL) unless the player has a game inside `notification_scan.LOOKBACK_DAYS` (21), else `_src_milestone_achieved` emails "just reached". Check candidates off base `games`/`manual_games`; the script sets `jit = off`.

**StatLab**
38. `context.player_id` is NOT a `PLAYER_CONTEXT_FILTERS` entry (those set `needs_live`). `_with_player_filter` ANDs onto each target's final WHERE; not for family, team innings, derived reports.
39. `TARGET_GUIDE` (`StatLab.jsx`) says which filters mean anything per target; `pruneContext`/`pruneTree` drop the rest. Keep in step.
40. StatLab applies the club default. Resolved scope rides in the context under `_scope` (browser cannot send underscore keys). `_scope_fragment` strips the leading ` AND `. Three aggregate-only queries carry their own clause (`query_family_career` in the JOIN, `query_family_season`, `derived_most_minutes_in_season`). Match type cannot be answered by the family targets; the screen says so.
41. List filters: known-list values are multi-select (`grade_names`, `season_ids`, `results`, `dismissals`); keep legacy `grade_name`. Not a spec-dict entry. `_text_list` never comma-splits (grade names have commas): repeated `?c_grade_names=`. Category/format are one comma string. Residual grade halves are ORed. Share `_RESULT_CASE_SQL`, `_dismissal_match_sql(param)`. `dismissals` goes in the innings block; `results` needs `_RESIDUAL_DISQUALIFYING_LIST_KEYS` and coerces first. Season multi-select goes through `_pss_season_filter`.

**Records (`routers/records.py`)**
42. `get_records` runs `SET LOCAL jit = off` first (transaction-scoped).
43. Every board reading `v_effective_player_season_stats` carries `pss_club_clause` (`pss.player_id = ANY(CAST(:club_player_ids AS uuid[]))`, resolved once), placed with `pss_gender_clause`. A bound array is pushable; `= ANY (SELECT ...)` is a semi-join against the whole view (49.8s vs 0.9ms). Never tidy it into a subquery. Cast it (empty list needs the type). It is logically redundant, so it changes no rows.
44. A rule belongs in the view, but a predicate on a view is paid per reference: give the planner a selective `player_id` up front.
45. `q` times and labels each query (`_query_label` scans back to `name = await q(`); `_timed` wraps non-board reads; declare `timings` above first use. `?debug_timing=1` returns `_query_timings` only to viewers who may see org private data; over `SLOW_RECORDS_LOG_MS` (2000) logs the worst queries. Entries carry `n`.

**Awards and grouping**
46. Award templates (`routers/award_definitions.py`): `STARTER_TEMPLATE` (~55 rows) is the default; `GLOBAL_TEMPLATE` is the 'comprehensive' preset; `APPLECROSS_TEMPLATE` seeded for slug `applecross`. `/award-definitions/seed?template=` uses `TEMPLATES` (unknown = starter). Seeding fills only an EMPTY org. `ACHIEVEMENT_TREE` (`achievementOptions.js`, mirrored in `routers/achievements.py`) is only the no-defs fallback. Tables are lifespan-created.
47. `run_grouping` (`services/competition_grouping.py`) is the one implementation (script and button). Uses `sync_runs` kind `competition_grouping`, deliberately not in `_FULL_SYNC_KINDS` and not resumed on restart. Safe to run twice (only NULL associations written; blank never erases; seeder skip-don't-replace). One run per club (POST returns the in-flight run). One failed season is counted, not fatal. `needs_grouping` (seasons it can act on) is the only trigger, never `grades_ungrouped`. Endpoints carry `MANAGE_MERGES`. Dismissal is a per-user, per-club localStorage flag read in the state initialiser. `maybe_group_club` fires on `_sync_safe` success and Full Rebuild true-success; the 02:30 job stays for clubs that never sync. `--no-group` = `group=False`.
48. `/{slug}/competitions` is a club section: Navbar `CLUB_SECTIONS` and `statsActive`, `SponsorFooter`, `FaviconManager` all know it.

## Traps and failure signatures

- Strike rate 320 or 333.33 beside blank balls: SUM/SUM or a browser-side rate (rules 1, 6). Two 10.2 overs summing to 20.4: rule 7.
- Header average differs from StatLab or by-venue: `not_out` flag wrote Retired Not Out as a wicket (rule 12).
- 13 matches where the club counts 10: washout (rules 13, 14).
- A filter INCREASES a total (333 to 337): source switch, not a bug (rule 29). Header, note and grid read 309/313/314: three rules (rules 29 to 31).
- Junior or senior residual under Juniors/Women's/Masters: residual `grade_id` NULL survived exclusion (rule 23).
- Match Type pills do nothing with a grade picked: `formats_only()` or a missing `{scope_clause}` (rule 21). Two-day filter returns all innings of a mixed grade: format done at grade level (rule 20). "Under 14s" counted senior: regex (rule 27).
- Filtered leaderboard fails at execute on finals/captain: clause built but bind not set where all branches share it.
- Settings page stuck on "Loading…": handler missing `Depends(get_db)` compiles, imports and passes `py_compile`; only awaiting fails. Call route bodies in suites.
- Grid drops on the default view for senior players of a junior-programme club: blanket skip of the gap heuristic (rule 33). Stray "filter does not apply" notes nobody triggered: rule 34.
- Records 15s: JIT plus per-row correlated subplan in view 060 (seq scan of ~315k rows). Rules 42 to 44.
- Filter pills missing in a browser suite: a stub `[]` for `/organisations/{id}/seasons` (row is gated on a season). `MATCHES212` has no word boundary and the headline counts up: wait, read `.pb-num`.
- Job result never shows: `CompetitionManager.load()` reset to loading on refresh and unmounted `onDone`. Spinner on first load only.
- Bare curl of `/scores/grades/{id}/matches` returns PascalCase: needs `jsconfig=eccn:true`; go through the client.
- `CREATE OR REPLACE VIEW` cannot drop a column (266 downgrade drops and recreates; 169's has the same latent defect).
- Harness tables: build from ORM models and copy lifespan DDL column for column (`bowling_spells.runs` is not `runs_conceded`; `audit_logs` uses `org_id` and its swallowed failure aborts the transaction). `games` has no `organisation_id`; `manual_batting_innings` keys on `manual_game_id`.
- Milestone `--apply` off a dry run whose REMOVE list is mostly juniors-turned-seniors: that is scope, not a fix. Do not apply.

## How to verify a change here

Real-Postgres suites through shipped route bodies, each with a control run that must fail on the named behaviour and report, never crash:
- `verify_rate_coverage.py`, `verify_rate_coverage_everywhere.py` (control reads 333.3, 300.0, 127.27, captain 6.25); `verify_rate_coverage_browser.mjs`, `verify_radar_rate_browser.mjs`.
- `verify_retired_not_out.py` (control reads 12.83). `verify_milestone_figures.py` (profile-only writer removes Hetel's 1,000 to 5,000 runs), `verify_milestone_split_browser.mjs`.
- `verify_match_coverage.py` (`scope_active` forced false fails 6; competition rate control reads 125.0), `verify_match_coverage_browser.mjs`.
- `verify_stats_by_competition.py` and `verify_competitions_browser.mjs` (re-run for any `GradeScope` change), `verify_junior_residual_scope.py` (control 18/376 under Juniors), `verify_statlab_player_filter.py`, `verify_records_timing.py` (asserts every `pss_gender_clause` is preceded by `pss_club_clause`).

Suite gotchas: read new keys with `.get`/`getattr` and guard clicks so a control run reports; seed through the code under test; a rate fixture needs an innings the rate cannot use; capture stub state BEFORE the action; read per row, not the whole document; CSS `uppercase` returns transformed `innerText`.
Diagnostics: `ops/diagnostics/records_slow_board.sql`, `records_pushdown_test.sql`, `career_matches_sources.sql`.
Re-run neighbours after a scope change: competitions, match coverage, shared fixtures, season fold, records timing, junior residual.

## Operator commands and scripts

- `python -m app.scripts.reconcile_milestones <org|all> [--apply]` (dry run default; prints removals with dates; `all` prints `[n/N] club (Ns)`).
- `python -m app.scripts.backfill_retired_not_out <org|all> --apply` (no network; re-derives `source='backfill'` season rows after fixing innings; CA `source='api'` rows untouched). Fix Missing Totals again repairs nothing (`ON CONFLICT DO NOTHING`).
- `python -m app.scripts.backfill_game_status <org-id-or-slug|all>` (seasons an incremental sync no longer scans; rerun for clubs with `source='backfill'` season rows).
- `python -m app.scripts.backfill_grade_associations <org|all> [--apply] [--no-group]` (one CA call per season; dry run default).
- Archive records these as due after deploy (status unknown): reconcile_milestones for Shoalwater; backfill_grade_associations for Applecross and Hamilton.

## Open follow-ups

- Records: nothing cached or concurrent (ideas: cache unfiltered board on last sync; separate sessions, not `asyncio.gather` on one `AsyncSession`).
- Scout screens and `iq._their_key_players` not marked aggregate-basis. `iq_team._role_ratings`, `iq_trends._similar_players` use aggregates as z-scored features (left on purpose).
- No SR column in Batting by Position. `player_season_stats.batting_average` is a second stored copy of a derived number.
- Result filter offers "Tied" but never matches. Family targets ignore other context filters. Gender filter casing bug on Leaderboard and Records.
- Players with ~100 games and CA 0 (Sunrise's Jackey Patel) unexplained. Club rankings unfiltered and unnoted (decision needed).
- Nothing reads PlayHQ's competition name (WAF). AFL silo untouched (`services/afl/grade_labels.py`). BetterIQ, Yearbooks not on GradeScope defaults.
- Leaner award import template instead of the ACC-flavoured `ACHIEVEMENT_TREE`.
- History before a Full Rebuild reads ball counts as 0 not NULL; the zero-with-runs test carries it.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-STATS-1] "Milestones are deliberately never filtered" (v9.64.0) | reversed by v9.93.0 (`profile_totals` follows the profile default); Milestones reach-note copy may still say never filtered | Which lens a panel (L16385-16615) vs A milestone is measured (L454-537) | verify frontend copy, then align
- [FLAG-STATS-2] Gap heuristic "skipped entirely under an active scope" (v9.64.0) | replaced by per-season gating in v9.64.1 (`seasons_left_to_scorecards` in `aggregations.py`) | Which lens a panel (L16385-16615) | retire the blanket wording
- [FLAG-STATS-3] StatLab family targets "left alone" (v9.59.0) | settled in v9.65.1 | A rate is only as good (L3203-3427) | retire
- [FLAG-STATS-4] `if grade_id or grade_name: scope = None` (228) | narrowed by 259 to `formats_only()` (`GradeScope.formats_only` exists) | Junior stats split (L8226-8315) vs A grade is several things (L7001-7212) | keep rule 21
- [FLAG-STATS-5] Competitions section says "migration 282 applied... pre-283 schema" | 282 is rate qualification, 283 competitions; typo-level | Stats by competition (L15772-16384) | keep 283
- [FLAG-STATS-6] "Not yet run" for `records_pushdown_test.sql` and "only measures, nothing cached" | later sub-section reports the run and the shipped clause (`pss_club_clause`, `SET LOCAL jit = off` confirmed in `routers/records.py`); caching still open | Stats by competition (L15772-16384) | retire "not yet run"
- [FLAG-STATS-7] "Noticed: grid carries no scope" (v9.63.2) and "teammates/captain do not take scope" (v9.64.0) | closed in v9.64.0 and v9.64.1 | Stats by competition; Which lens a panel | retire
- [FLAG-STATS-8] Line refs `aggregations.py:511/553` and "five sites" for `appearance_counts_as_match` | line numbers stale, count may have moved | A washout is not a match played (L6569-6643) | verify with grep
- [FLAG-STATS-9] Records timings, milestone dry-run counts (352 removals), player-count splits | one-off production evidence, Sep 2026 | several | history only, do not quote
- [FLAG-STATS-10] Gender filter left on Leaderboard and Records with a casing bug | not re-checked in code | A grade is several things (L7001-7212) | verify, then fix or retire

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| A milestone is measured on the profile's figure, and a junior split is SHOWN (v9.93.0) (L454-537) | rules extracted | Rules 36, 37; Traps (milestone apply); Operator commands; Flags 1, 9 |
| A RETIRED NOT OUT IS NOT A DISMISSAL (v9.66.0) (L3112-3202) | rules extracted | Rules 11, 12; Traps (average); Operator commands |
| A rate is only as good as the innings behind it (migration 282) (L3203-3427) | rules extracted | Rules 1 to 10; Traps (strike rate, overs); Flag 3 |
| &nbsp;&nbsp;The one figure the browser still worked out itself (v9.65.1) | rules extracted | Rules 6, 8, 10; Follow-ups |
| Season × grade matches on a player profile (v9.37.3) (L6123-6190) | rules extracted | Rule 32, 35 |
| A washout is not a match played (migration 266) (L6569-6643) | rules extracted | Rules 13, 14; Traps (washout, view drop); Operator commands; Flag 8 |
| StatLab: one player, and tabs that reshape the filters (v9.96.0) (L6760-6786) | rules extracted | Rules 38, 39 |
| StatLab gets the platform's Grade Type / Match Type filters (v9.29.4) (L6787-6861) | rules extracted | Rule 40; Follow-ups |
| StatLab's list filters take several values at once (v9.29.2) (L6862-6939) | rules extracted | Rule 41; Follow-ups (Tied) |
| A grade is several things at once (migration 259, v9.26.0) (L7001-7212) | rules extracted | Rules 15 to 21, 27, 28; Traps; Flags 4, 10 |
| AN IMPORT RESIDUAL IS CLASSIFIED BY ITS LABEL (v9.89.2) (L8165-8225) | rules extracted | Rule 23; Traps |
| Junior stats split off career stats (migration 228, v9.18.0) (L8226-8315) | rules extracted | Rules 15, 16, 22, 26, 27; Traps (Depends); Flag 4 |
| Awards — default templates (v8.28.0) (L12666-12695) | rules extracted | Rule 46; Follow-ups |
| Stats by competition, and the association that runs a grade (migration 283, v9.60.0) (L15772-16384) | rules extracted | Rules 24, 25, 29 to 31, 42 to 45, 47, 48; Traps; Operator commands; Flags 5, 6, 7, 9 |
| &nbsp;&nbsp;The club groups its own older seasons, and reads them back (v9.61.0) | rules extracted | Rules 47, 48; Traps (job result) |
| &nbsp;&nbsp;Which of the forty queries the record book is waiting on | rules extracted | Rule 45 |
| &nbsp;&nbsp;And what the timing said: a compiler and a platform-wide scan | rules extracted | Rules 42, 44; Flag 6 |
| &nbsp;&nbsp;Name the club's players, and the record book stops reading the platform | rules extracted | Rule 43 |
| &nbsp;&nbsp;A career has two match counts, and a filter switches between them | rules extracted | Rule 29; Follow-ups; Flag 9 |
| &nbsp;&nbsp;Say the two figures differ before anybody adds them up (v9.63.1, v9.63.2) | rules extracted | Rules 30, 31, 47 (grouping hook); Traps |
| Which lens a panel is under, said on the panel (v9.64.0) (L16385-16615) | rules extracted | Rules 33, 34 |
| &nbsp;&nbsp;The grid answers to the bar now, and a match type is the exception | superseded by "The review, and what it changed (v9.64.1)" (per-season gate) | Rule 33; Flag 2 |
| &nbsp;&nbsp;A CLUB DEFAULT IS ALREADY A FILTER | rules extracted | Rules 30, 31 |
| &nbsp;&nbsp;The review, and what it changed (v9.64.1) | rules extracted | Rules 33, 34; Traps; Flag 7 |
| &nbsp;&nbsp;Hamilton's second ask was unmet in the panel built for the first (v9.64.2) | rules extracted | Rules 1, 6 (competition breakdown uses `rc`); Verify (fixture gotcha) |
| &nbsp;&nbsp;The order of the competition pills is the club's to set (v9.65.0) | rules extracted | Rule 35; Verify (stub state) |
