# Guide: Career and season figures, rates, milestones, grade/match/competition scopes, StatLab, records, awards

**Read this before**:
- Touching any career, season, leaderboard, record-book, StatLab or profile figure (matches, average, strike rate, economy, milestones).
- Editing `services/grade_scope.py`, `rate_coverage.py`, `dismissal.py`, `game_status.py`, `milestone_totals.py`, `match_coverage.py`, `competition_stats.py`, `competition_grouping.py`, `stats_display.py`, `player_formats.py`, `routers/records.py`, `services/statlab.py`, `StatLab.jsx`.
- Adding a filter, pill, scope param or a new per-game/aggregate query that reads `v_effective_player_season_stats` or `game_appearances`.
- Symptoms: a filter that raises a total; header, note and by-grade grid disagreeing on matches; a strike rate that is far too high; an average that differs between profile and StatLab; a junior/women's season inside a senior career; the Records page taking 15s; milestones "reached" that are not.
- Keywords: retired not out, washout, `balls = 0`, competition filter, Grade Type, Match Type, `GradeScope`, `formats_only`, `pss_club_clause`, coverage dagger, award starter template.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/stats-figures-records-and-filters.md`. Grep hints: `milestone_totals`, `RETIRED NOT OUT`, `A rate is only as good`, `Season × grade matches`, `A washout is not a match`, `StatLab: one player`, `Grade Type / Match Type filters`, `list filters take several values`, `A grade is several things`, `IMPORT RESIDUAL IS CLASSIFIED`, `Junior stats split`, `Awards — default templates`, `Stats by competition`, `two match counts`, `Which lens a panel`.

**Related guides**: sync and import guides (writers of `not_out`, `balls`, `match_format`, `status`, residual rows); CricketStatz/import pairing guide (paired twins and the per-innings views); BetterSelect/Comms guides only where they reuse `resolve_scope`.

## Standing rules

**Rates and coverage (migration 282, `services/rate_coverage.py`)**
1. Runs and balls in a rate must come from the same innings. Never `SUM(runs)/SUM(balls)` over a whole season or career. Only the ratio changes source; runs, innings and wickets keep their normal source.
2. Covered innings = `balls IS NOT NULL AND (balls > 0 OR runs = 0)`. Older sync wrote a missing ball count as 0, so `IS NOT NULL` alone reads them as covered. A genuine 0 off 0 is covered.
3. Where there are no scorecards (BetterImport season totals) the aggregate stands and the payload says `basis: "aggregate"`. Do not withhold it.
4. Rate qualification minimums count covered innings/spells, never innings played. Platform default is 0 on purpose (`organisations.stats_min_rate_innings` / `stats_min_rate_spells`, NULL = no preference, read via `services/stats_display.py`). A viewer's explicit 0 is real: test for None, not falsiness.
5. Strike-rate records are season by season, never all time (scoring practice changed by era).
6. Rates are served by the backend only. The browser never divides summed balls. Use `rc.with_coverage` (presence-aware pair from `sr_counted/sr_of`, `econ_counted/econ_of`) and `batting_rate_columns(extra=...)` when the select is wider than the innings the rate is about (did-not-bat rows).
7. Overs are cricket notation (10.2 = 10 overs 2 balls): convert to balls before summing or dividing, everywhere (economy, balls per wicket, captain panel).
8. Per-innings SR is derived on read (`rc.innings_strike_rate_sql`, `NULLIF(balls,0)` is the coverage test), never stored or backfilled. A stored rate is only a fallback where balls were not recorded.
9. The coverage mark is a dagger, never an asterisk (asterisk means not out). `RateFootnote`'s `when` stops a footnote appearing for a figure not drawn.
10. Every new rate query must import `rc.`. Audit: grep the frontend for division by summed balls, and the backend for rates in modules with no `rc.` import. Competition breakdown (`player_competition_breakdown`) had to be fixed after shipping without it.
11. StatLab family targets re-derive rates from covered halves and publish no coverage pair (uniform column contract, `_serialise` feeds the CSV). Scout and `iq._their_key_players` stay on aggregates (basis "aggregate") because there are no scorecards.

**Dismissals and matches played**
12. `services/dismissal.py` is the one rule. Retired Not Out (CA id 14, Law 25.4.2) and Retired Hurt (8, from the Law, not measured) are not dismissals; plain Retired (13, Law 25.4.3) is. Whole-phrase match only. Never `LIKE 'retired%'`. CA ids: 1 Not Out, 8 Retired Hurt, 13 Retired, 14 Retired Not Out, 15 Absent, 0 Did Not Bat.
13. Fix the writer, not readers: `sync.py` and the live scorecard merge decide `not_out`. Every average is `innings - not_outs`; keep it on the alias (by-opposition, by-venue, by-position, by-grade). A retirement is not a way of getting out (leaves the dismissal donut, unusual dismissals); retired-out stays.
14. `wkts_lost`, `our_wkts_lost` and the fantasy engine's `out` are a different question and were left alone.
15. `games.status` (migration 266) is CA's word verbatim. `result` NULL cannot tell washout from unplayed. `services/game_status.py` is the one vocabulary (`NOT_PLAYED_STATUSES`; NO RESULT is not in it, that game started). A player named but with no batting, bowling or fielding row in a not-played fixture is subtracted.
16. The washout correction lives in `v_effective_player_season_stats` AND in every reader that counts from `game_appearances` via `appearance_counts_as_match(alias)` (StatLab `appear` CTE, by-grade, by-season-grade, by-venue, Formats). Ask which source a new match-counting screen reads. Recent-games lists deliberately still show a washout.
17. CA's `matches` counts anyone on the team sheet. Do not "fix" it in the caller.

**Grade scope (`services/grade_scope.py`, migrations 228, 229, 259, 283)**
18. `GradeScope` is the one place a category/format/competition selection becomes SQL. Every caller gates on `scope.active`, never `scope is None`. Empty exclusion set emits no clause, so clubs with nothing to exclude run the old SQL.
19. Category is EXCLUSION-based: `col IS NULL OR NOT (col = ANY(excluded))`. A grade-less manual game or residual is not known to be junior, so it is kept. Never turn it into an include-list.
20. Categories resolve per grade NAME in Python (may be an unconfirmed `suggest_category` guess), never in the WHERE.
21. `grades.categories` and `grades.match_formats` are TEXT[]; `grades.category` is kept in step with the first (canonical order) entry. Every writer of `category=suggest_category(...)` must also write `categories=` (sync x2, manual_entries x2), or a "Girls Under 16" loses its women's half.
22. An explicit category pick matches ANY of a grade's categories (inclusion). The club DEFAULT and `judge_primary=True` judge the primary category only, else a Girls U16 grade sneaks back into senior careers.
23. Format is per FIXTURE (`games.match_format` via `format_sql_case()`, mirror of `format_from_match_type`; change both together). Category is per grade. A game with no `match_format` falls back to the grade's format only if the grade plays exactly one. `format_from_match_type` returns None for unknown strings and must keep doing so.
24. `clause(col, kind)`: `game` (default, per-fixture), `aggregate` (emits `AND FALSE` under a format filter: season aggregates have no game), `grade` (EXISTS over that grade's games, only for a true grade listing). A query that joins `v_effective_games` is per-fixture whatever column the category half uses (`game_alias="g"`).
25. `scope.active` includes `format_active`, so any format filter moves readers off aggregates to per-innings rows.
26. Picked grade beats the CATEGORY half but not the format or competition half: `GradeScope.formats_only()`. Picked-grade branches are separate SQL from default branches: add `{scope_clause}` and its bind to both (records.py has five fragments).
27. Aggregate-only residual sources `_RESIDUAL_SOURCES = (manual_aggregate, manual_career, import)` must be added back under a category scope; never add `api` or `manual_game` (double count). Blended averages recompute from summed counts.
28. Import residuals are classified by `grade_label` (v9.89.2): `resolve_scope` builds `excluded_labels` like `excluded_ids`; `clause(..., label_column=...)` is a CASE: grade_id present judges by id, label present judges by label (`text[]` cast), both NULL kept. Five residual sites read `pss` (`_career_residuals`, `_residual_totals_cte`, `_season_by_season_scoped`, StatLab family and career/season residuals). The default is untouched (senior labels stay).
29. Competition axis (283) is an INCLUSION, expressed as a subquery on `grades.competition_id` (`ix_grades_competition`, binds 1 to 5 uuids), not a resolved grade-id list. Junk, non-uuid or another club's ids drop in `resolve_scope`; an all-junk pick is an ACTIVE filter matching nothing (fail closed). A grade in no competition, a career residual and a grade-less manual game drop out. `_fetch_manual_games_as_list` takes the scope, and `list_games` resolves scope above the manual fetch.
30. A grade belongs to at most one competition; a competition is the club's own named group, seeded one per association (`grades.association_id`, `owningOrganisation` on the teams payload). `is_seeded` clears on any person edit so sync never overwrites naming. `grades.competition_id` is ON DELETE SET NULL. Ungrouped grades show as "Other grades", never dropped.
31. `resolve_scope_for_player` widens category only when the default would leave a junior-only player empty (`stats_auto_show_played_grades`, migration 229, `auto_shown`); it never widens a FORMAT and only for the default, profile only. Gate on `scope.category_active`.
32. `organisations.stats_grade_categories` (228): empty or all-junk stores NULL. Senior is the baseline.
33. Age-group regexes end `\d+s?` ("Under 14s", "U14s", "Year 9s", "Over 40s"); `\d+\b` misclassified plurals as senior.
34. The filter row is not drawn for a club with fewer than two competitions (or nothing to filter). Additive "Include" row and Grade Type row are never shown together. Filter row also needs the club to have a season.
35. `grades-with-stats` computes classification in its own query: unnesting the array columns into the aggregate multiplies batting rows and inflates runs.

**Career matches and lenses (notes, never renumbering)**
36. Header matches = `SUM(player_season_stats.matches)` (CA, no grade). Any active scope switches to matches we hold a game row for. By-grade grid = per season AND grade `max(held, CA per-grade)` plus unplaceable shortfall, inner-joined to grades. Three rules, three questions. Do NOT adopt `max(held, claimed)` in the header (would rewrite 19,439 players). Say the difference instead.
37. `services/match_coverage.py` reads both figures itself, never the caller's current figure (with a filter on it has already switched source). Grade-less games count as held. Surplus is `extra_scorecards`, shortfall `without_scorecard`, never a negative. Note draws only where the two differ; nothing for a last-N or date window. Copy makes no causal claim it cannot prove. Under a scope (incl. the club default) the note names both sources rather than claiming to be the headline.
38. By-grade grid note is summed from its own rows (`held`, asterisks, `unattributed`). `GradeTotalNote` is suppressed while the grid is scoped (its grade-less line uses scope-independent `breakdown_matches`).
39. `get_player_team_breakdown` builds one per-(season, grade) cell map and derives rows from it (totals equal by construction), per season not per career, folds seasons via `load_reverse_alias_map`, orders columns by folded grade name with `MIN(display_order)`, shows a muted `unattributed` column only when non-zero, and is not special-casing historical bundle seasons.
40. It takes the scope. Scorecard side takes the whole scope; CA per-grade rows take category/competition but a format is `aggregate` (`AND FALSE`). The season-total gap heuristic is gated PER SEASON: a season where scoped and unscoped counts differ is `mixed` and left to scorecards (`seasons_left_to_scorecards`), a season where they agree still runs the heuristic. A senior-only player's grid must be byte-identical under the club default and with no scope.
41. Reach notes (`components/FilterReach.jsx`: `enumeration`, `career`, `unfiltered`) fire on what was PICKED (raw `catParam`/`fmtParam`/`compParam`), never on the club default; name only filters actually on; `FilterReachDot` on tab labels. New panels must declare their reach. Teammates and captain-stats now take the scope (`_og_cte(scope)`, one `club` string).
42. Honours are career facts, never filtered. Milestones: see rule 44.
43. Order of competition pills is the club's (`club_competitions.display_order`, `POST /admin/competitions/reorder` sends the whole list). Screen is "Grades & Competitions" (display only; `/admin/grades#competitions` scrolls to the panel).

**Milestones (`services/milestone_totals.profile_totals`)**
44. `profile_totals` is the ONE definition (profile default scope, junior-only auto-widen, batched per scope group, ids bound as an array); Milestones page, dashboard, admin report, player card and notification all read it. Milestones follow the profile default and carry `junior_split`, `counts`, and a `variant` entry; the notification dedupe key carries the variant basis. This reverses "never filtered" from v9.64.0.
45. "Without junior" is judged on the primary category (`judge_primary=True`).
46. `sync._compute_milestones(reconcile=True)` removes thresholds no longer reached (we are the only writer) and keeps dates; it runs at the END of sync (a scoped career counts scorecards a Full Rebuild just wiped); `match_pull_failed` runs only add.
47. A stored milestone is reached on `max(profile figure, whole unscoped career)`. Catch-up adds are undated (`achieved_at` NULL) unless the player has a game inside `notification_scan.LOOKBACK_DAYS` (21), else `_src_milestone_achieved` would email "just reached". Candidate-only, base-table date check keeps an all-clubs run fast; the script sets `jit = off`.

**StatLab**
48. `context.player_id` is NOT a `PLAYER_CONTEXT_FILTERS` entry (those set `needs_live` and move player_career to per-innings). `_with_player_filter` ANDs onto each target's final WHERE; not applied to family, team innings or derived reports.
49. `TARGET_GUIDE` in `StatLab.jsx` is which filters mean anything per target; `pruneContext`/`pruneTree` drop what a new target cannot use. Keep in step when a target starts or stops honouring a filter.
50. StatLab applies the club default like every other screen. Resolved scope rides in the context dict under `_scope`; `_ctx_from_request` never writes underscore keys, so a browser cannot supply it. `_scope_fragment` strips the leading ` AND `. Three aggregate-only queries need their own clause (`query_family_career`, `query_family_season`, `derived_most_minutes_in_season`); on family_career put it in the JOIN. Match type cannot be answered by the two family targets, and the screen says so.
51. List filters: known-list values get tick boxes (`grade_names`, `season_ids`, `results`, `dismissals`). Keep legacy `grade_name`. Not a spec-dict entry (variable clause). `_text_list` never comma-splits (grade names contain commas): repeated params `?c_grade_names=..&c_grade_names=..`. Category/format keys are one comma string (`?categories=senior,womens`). Residual grade halves are ORed. Reuse `_RESULT_CASE_SQL` and `_dismissal_match_sql(param)`. `dismissals` goes in the innings block; `results` needs `_RESIDUAL_DISQUALIFYING_LIST_KEYS` and coerces before disqualifying. Season multi-select goes through `_pss_season_filter`.

**Records and performance (`routers/records.py`)**
52. `get_records` runs `SET LOCAL jit = off` first (transaction-scoped): boards over the wide UNION view plan past JIT cost and burn ~half their time compiling.
53. Every board that reads `v_effective_player_season_stats` carries `pss_club_clause` (`AND pss.player_id = ANY(CAST(:club_player_ids AS uuid[]))`, `club_player_ids` resolved once). A bound ARRAY is a pushable restriction; `= ANY (SELECT ...)` is a semi-join against the whole view (49.8s vs 0.9ms). Never tidy it into a subquery. It is logically redundant (boards already join players), so it changes no rows. It rides with `pss_gender_clause`; cast the array (empty list needs the type).
54. A rule belongs in the view, but a predicate on it is paid per reference. Give the planner a selective `player_id` up front rather than scattering the rule.
55. `q` times every query and labels it by the board (`_query_label` scans back to the nearest `name = await q(`); `_timed` wraps non-board reads; `timings` is declared above first use. `?debug_timing=1` returns `_query_timings` only to viewers who may see org private data; requests over `SLOW_RECORDS_LOG_MS` (2000) log their worst queries. `_query_timings` entries carry `n` (order).
56. Competition filter makes records faster (narrows by index); the unfiltered all-time page was the slow one for every club.

**Awards templates (`routers/award_definitions.py`)**
57. `STARTER_TEMPLATE` (~55 rows, club-agnostic) is the default for new clubs; `GLOBAL_TEMPLATE` is the opt-in 'comprehensive' preset; `APPLECROSS_TEMPLATE` is seeded for slug `applecross`, not in the picker. `/award-definitions/seed?template=` uses `TEMPLATES` (unknown = starter). Seeding only fills an EMPTY org. `ACHIEVEMENT_TREE` (`frontend/src/lib/achievementOptions.js`, mirrored in `routers/achievements.py`) is only the fallback when a club has no defs. Tables are lifespan-created, not Alembic.

**Club grouping job (`services/competition_grouping.py`)**
58. `run_grouping` is the one implementation (script and button both call it). Uses `sync_runs` kind `competition_grouping`, deliberately not in `_FULL_SYNC_KINDS` and not resumed on restart. Safe to run twice (only NULL associations written; blank never erases; seeder skip-don't-replace). One run per club (POST returns the in-flight run). One season failing is counted, not fatal. `needs_grouping` (seasons the job can act on) is the only trigger, never `grades_ungrouped`. Endpoints carry `MANAGE_MERGES`. Frontend dismissal is a per-user, per-club localStorage flag read in the state initialiser. `maybe_group_club` fires on the success path of `_sync_safe` and the Full Rebuild true-success branch; the nightly 02:30 job stays for clubs that never sync. `--no-group` maps to `group=False`.
59. `/{slug}/competitions` is a club section: Navbar `CLUB_SECTIONS` and `statsActive`, `SponsorFooter`, `FaviconManager` all know it.

## Traps and failure signatures

- Strike rate 320 or 333.33 next to an innings list full of blank balls: SUM/SUM mixing, or a browser-side rate (radar). Use server rate and coverage.
- Two `10.2` overs summing to 20.4: cricket-notation overs summed raw (economy 6.25 vs 3.00).
- Average differs between profile header and StatLab or by-venue: header reads CA `not_outs`, scorecard paths read a `not_out` flag that treated Retired Not Out as a wicket. Fix the flag, not the readers.
- Player shows 13 matches, club counts 10: washout named on the sheet. Correct the view AND `game_appearances` readers.
- A filter INCREASES a total (333 to 337): source switch (CA aggregate to scorecards), not a bug. `?categories=senior` reproduces it.
- Junior or senior residual appears under Juniors/Women's/Masters: import residual has `grade_id` NULL and survived exclusion. Classify by `grade_label`.
- Match Type pills do nothing with a grade picked: scope dropped whole instead of `formats_only()`, or the picked-grade SQL lacks `{scope_clause}`.
- Filtered leaderboard fails at execute time on finals/captain: clause built but its bind not set where all branches share it.
- A two-day filter returns every innings of a grade that sometimes plays two-day: format classified at grade level (`kind='grade'`) instead of per fixture.
- "Under 14s" counted as senior: `\d+\b` regex.
- Settings page stuck on "Loading…": handler missing `Depends(get_db)` compiles and imports; only awaiting fails. Call route bodies in suites.
- Grid total drops on the default view for senior players of a junior-programme club: blanket skip of the gap heuristic. Gate per season.
- Six tabs say "the filter does not apply here" nobody touched: note fired on club default. Use the raw pick.
- Records page 15s: JIT plus per-row correlated subplan in view 060 (seq scan of 315k rows). See rules 52 and 53.
- A stub `[]` for `/organisations/{id}/seasons` renders no filter pills, so pick-driven browser checks fail with nothing pressed.
- `MATCHES212` has no word boundary and the headline counts up: wait for it to stop and read `.pb-num`.
- Competitions panel result vanishes after job: `CompetitionManager.load()` reset to loading on refresh and unmounted `onDone`. Spinner only on first load.
- Curl of `/scores/grades/{id}/matches` returns PascalCase and empty `matches`: missing `jsconfig=eccn:true`; go through the client.
- `CREATE OR REPLACE VIEW` cannot drop a column (266 downgrade drops and recreates; 169's downgrade has the same latent defect).
- Harness tables written by hand: `bowling_spells.runs` misspelt `runs_conceded` passed 51 checks. Build from ORM models; copy lifespan DDL column for column (`audit_logs` uses `org_id`, failure aborts the transaction silently). `games` has no `organisation_id`; `manual_batting_innings` keys on `manual_game_id`.
- Milestone reconcile `--apply` off a dry run whose REMOVE list is mostly juniors-turned-seniors: that is scope, not a fix. Do not apply.

## How to verify a change here

Suites (real Postgres, shipped route bodies; each has a control run that must report or fail on the named behaviour, never crash):
- `verify_rate_coverage.py`, `verify_rate_coverage_everywhere.py` (control reads 333.3, 300.0, 127.27, captain 6.25); browser `verify_rate_coverage_browser.mjs`, `verify_radar_rate_browser.mjs`.
- `verify_retired_not_out.py` (control reads 12.83 on profile and StatLab).
- `verify_milestone_figures.py` (control: profile-only writer removes Hetel's 1,000 to 5,000 runs); `verify_milestone_split_browser.mjs`.
- `verify_match_coverage.py` (control: `scope_active` forced false, or blanket skip reproduces `matches: 5`; competition rate control reads 125.0), `verify_match_coverage_browser.mjs`.
- `verify_stats_by_competition.py`, `verify_competitions_browser.mjs` (competitions suite is the one to re-run for any `GradeScope` change).
- `verify_junior_residual_scope.py` (control: 18/376 under Juniors), `verify_statlab_player_filter.py` (filtered row equals unfiltered on both paths), `verify_records_timing.py` (asserts every `pss_gender_clause` is preceded by `pss_club_clause`).
- Grade Type/Match Type suites; the every-write-site-pairs-both-columns guard is structural.

Rules for suites: a control run must not crash (read new keys with `.get`/`getattr`, guard clicks); seed through the code under test; a fixture needs an innings the rate cannot use (else all rates are covered); compare payload to state captured BEFORE the action; check per row not whole document; the CSS `uppercase` trap returns transformed text from `innerText`.
Diagnostics: `ops/diagnostics/records_slow_board.sql`, `records_pushdown_test.sql` (A/B/C/D/E plus prepared-statement section F and empty-array section G), `career_matches_sources.sql`.
Re-run neighbours after a scope change: competitions 136, match coverage, shared fixtures 38, season fold 65, records timing, junior residual 24.

## Operator commands and scripts

- `python -m app.scripts.reconcile_milestones <org|all> [--apply]` (dry run default; prints removals with recorded date; `all` prints `[n/N] club (Ns)` per club).
- `python -m app.scripts.backfill_retired_not_out <org|all> --apply` (no network; re-derives `source='backfill'` season rows AFTER fixing innings; CA `source='api'` rows never touched).
- `python -m app.scripts.backfill_game_status <org-id-or-slug|all>` (seasons an incremental sync no longer scans; Sync Now fixes the current season).
- `python -m app.scripts.backfill_match_format <org>` (see sync guide).
- `python -m app.scripts.backfill_grade_associations <org|all> [--apply] [--no-group]` (one CA call per season; dry run default).
- After deploy (from the archive, may be done): reconcile_milestones for Shoalwater; backfill_grade_associations for Applecross and Hamilton.
- Clubs whose season rows came from "Fix Missing Totals" need `backfill_game_status` re-run.
- Pressing Fix Missing Totals again repairs nothing (`ON CONFLICT DO NOTHING`).

## Open follow-ups

- Records: nothing cached, nothing concurrent. Ideas: cache unfiltered board on last successful sync; independent sessions (not `asyncio.gather` on one `AsyncSession`).
- Scout screens (`iq_scout`, `scout_discovery`, `scout_internal_link`, `seasonRollup.js`) and `iq._their_key_players` are not marked as aggregate-basis.
- `iq_team._role_ratings`, `iq_trends._similar_players` derive rates from aggregates as z-scored features (left on purpose).
- No SR column in Batting by Position (field correct, nothing renders it).
- `player_season_stats.batting_average` is a second stored copy of a derived number.
- Result filter offers "Tied" but can never match (tie looks like draw in `games`).
- Family career/season ignore other context filters (opposition, result, dismissal, picked grade).
- Gender filter casing bug (`p.gender` lowercase vs `'Male'`) left on Leaderboard and Records.
- Players with ~100 games and no season aggregate (CA 0 vs 98 held) is its own question.
- Club rankings are unfiltered and unnoted (career fact or not: needs a decision).
- Nothing reads PlayHQ's own competition name (WAF); AFL silo untouched (`services/afl/grade_labels.py` own vocabulary).
- Leaner award import template instead of the ACC-flavoured `ACHIEVEMENT_TREE`.
- Manual-rollup 037-shape fan-out beside `player_season_stats` and StatLab family per-context gaps: see archive if touched.
- BetterIQ, StatLab (partly), Yearbooks not on `GradeScope`-style defaults (BetterIQ has its own `iq_filters` vocabulary).
- Some clubs' history needs Full Rebuild before ball counts read NULL not 0 (zero-with-runs test carries it).

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-STATS-1] "MILESTONES ARE DELIBERATELY NEVER FILTERED" (v9.64.0) | reversed by v9.93.0: milestones follow the profile default via `profile_totals`; the Milestones tab reach note text may still say never filtered | Which lens a panel (L16385-16615) vs A milestone is measured (L454-537) | verify frontend copy in `FilterReach.jsx`/Milestones panel, then align
- [FLAG-STATS-2] Grid heuristic "skipped entirely under an active scope" (v9.64.0) | replaced by per-season gating in v9.64.1 (`seasons_left_to_scorecards` exists in `aggregations.py`) | Which lens a panel (L16385-16615) | retire the blanket-skip wording; keep per-season rule
- [FLAG-STATS-3] StatLab family targets "left alone" (v9.59.0 note) | settled in v9.65.1 (they now honour scope and coverage) | A rate is only as good (L3203-3427) | retire
- [FLAG-STATS-4] `if grade_id or grade_name: scope = None` (228) | narrowed by 259 to `formats_only()` (category dropped, format and competition kept) | Junior stats split (L8226-8315) vs A grade is several things (L7001-7212) | keep rule 26, retire the 228 wording
- [FLAG-STATS-5] Migration numbering: 259 text says "migration 259" applied; competitions section says "migration 282 applied... pre-283" | typo-level inconsistency, 282 is the rate-qualification migration, 283 competitions | Stats by competition (L15772-16384) | keep 283 for competitions
- [FLAG-STATS-6] "Not yet run" for `records_pushdown_test.sql` and "nothing is cached, only measures" | the next sub-section reports its run (0.877ms vs 49.8s) and the shipped `pss_club_clause`; code confirms `pss_club_clause` and `SET LOCAL jit = off` in `routers/records.py` | Stats by competition sub-sections (L15772-16384) | retire "not yet run"; caching remains open
- [FLAG-STATS-7] Noticed-not-fixed "grid carries no scope" (v9.63.2) | closed in v9.64.0 (grid takes the scope) | Stats by competition (L15772-16384) | retire
- [FLAG-STATS-8] Noticed-not-fixed "`teammates`, `captain-stats` do not take scope" (v9.64.0) | closed in v9.64.1 | Which lens a panel (L16385-16615) | retire
- [FLAG-STATS-9] Line refs `aggregations.py:511/553` for recent-games lists, and "five sites" for `appearance_counts_as_match` | line numbers stale; count may have changed | A washout is not a match played (L6569-6643) | verify with grep before relying
- [FLAG-STATS-10] Records timings (15s, 13,287ms, 315,288 rows) and "Not part of this" player counts | one-off measurements, production data as of Sep 2026 | Stats by competition (L15772-16384) | history only, do not quote
- [FLAG-STATS-11] Milestone dry-run figures for Shoalwater (352 removals, 101 dated 10 Sep) | one-off evidence, club-specific | A milestone is measured (L454-537) | history only
- [FLAG-STATS-12] Gender filter left on Leaderboard and Records with a known casing bug | not re-checked in code | A grade is several things (L7001-7212) | verify, then fix or retire

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| A milestone is measured on the profile's figure, and a junior split is SHOWN (v9.93.0) (L454-537) | rules extracted | Standing rules 44 to 47, Traps (reconcile apply), Operator commands, Flags 1 and 11 |
| A RETIRED NOT OUT IS NOT A DISMISSAL (v9.66.0) (L3112-3202) | rules extracted | Rules 12 to 14, Traps (average mismatch), Operator commands, Follow-ups |
| A rate is only as good as the innings behind it (migration 282) (L3203-3427) | rules extracted | Rules 1 to 11, Traps (strike rate, overs), Flag 3 |
| &nbsp;&nbsp;The one figure the browser still worked out itself (v9.65.1) | rules extracted | Rules 6, 8, 10, 11, Follow-ups (Scout, role ratings, position SR) |
| Season × grade matches on a player profile (v9.37.3) (L6123-6190) | rules extracted | Rule 39, Rule 43 (rename) |
| A washout is not a match played (migration 266) (L6569-6643) | rules extracted | Rules 15 to 17, Traps (washout, view drop), Operator commands, Flag 9 |
| StatLab: one player, and tabs that reshape the filters (v9.96.0) (L6760-6786) | rules extracted | Rules 48, 49 |
| StatLab gets the platform's Grade Type / Match Type filters (v9.29.4) (L6787-6861) | rules extracted | Rule 50, Follow-ups (family filters) |
| StatLab's list filters take several values at once (v9.29.2) (L6862-6939) | rules extracted | Rule 51, Follow-ups (Tied) |
| A grade is several things at once (migration 259, v9.26.0) (L7001-7212) | rules extracted | Rules 18 to 26, 33 to 35, Traps (format, picked grade, plural), Flags 4 and 12 |
| AN IMPORT RESIDUAL IS CLASSIFIED BY ITS LABEL (v9.89.2) (L8165-8225) | rules extracted | Rule 28, Traps (residual) |
| Junior stats split off career stats (migration 228, v9.18.0) (L8226-8315) | rules extracted | Rules 18 to 20, 27, 31, 32, Traps (Depends), Flag 4 |
| Awards — default templates (v8.28.0) (L12666-12695) | rules extracted | Rule 57, Follow-ups |
| Stats by competition, and the association that runs a grade (migration 283, v9.60.0) (L15772-16384) | rules extracted | Rules 29, 30, 36 to 40, 52 to 56, 58, 59; Traps; Operator commands; Flags 5, 6, 7, 10 |
| &nbsp;&nbsp;The club groups its own older seasons, and reads them back (v9.61.0) | rules extracted | Rule 58, 59, Traps (job result vanishes) |
| &nbsp;&nbsp;Which of the forty queries the record book is waiting on (Sep 2026) | rules extracted | Rules 55, 56 |
| &nbsp;&nbsp;And what the timing said: a compiler and a platform-wide scan (Sep 2026) | rules extracted | Rules 52, 54, Flag 6 |
| &nbsp;&nbsp;Name the club's players, and the record book stops reading the platform (Sep 2026) | rules extracted | Rule 53 |
| &nbsp;&nbsp;A career has two match counts, and a filter switches between them (Sep 2026) | rules extracted | Rule 36, Follow-ups (Sam Morgan), Flag 10 |
| &nbsp;&nbsp;Say the two figures differ before anybody adds them up (v9.63.1, v9.63.2) | rules extracted | Rules 37, 38, 58 (grouping hook), Traps (MATCHES212) |
| Which lens a panel is under, said on the panel (v9.64.0) (L16385-16615) | rules extracted | Rules 40 to 42 |
| &nbsp;&nbsp;The grid answers to the bar now, and a match type is the exception | superseded by v9.64.1 sub-section (per-season gate) | Rule 40, Flag 2 |
| &nbsp;&nbsp;A CLUB DEFAULT IS ALREADY A FILTER (v9.64.0) | rules extracted | Rule 37 (note names both sources), Rule 38 |
| &nbsp;&nbsp;The review, and what it changed (v9.64.1) | rules extracted | Rules 40, 41, Traps (grid drop, stray notes), Flag 8 |
| &nbsp;&nbsp;Hamilton's second ask was unmet in the panel built for the first (v9.64.2) | rules extracted | Rule 10, Verify (fixture needs an unusable innings) |
| &nbsp;&nbsp;The order of the competition pills is the club's to set (v9.65.0) | rules extracted | Rule 43, Verify (stub state check) |
