# Guide: Career and season figures, rates, milestones, grade/match/competition scopes, StatLab, records, awards

**Read this before**:
- Touching any career, season, leaderboard, record-book, StatLab or profile figure.
- Editing `services/grade_scope.py`, `junior_hiding.py`, `rate_coverage.py`, `dismissal.py`, `game_status.py`, `milestone_totals.py`, `match_coverage.py`, `competition_*.py`, `routers/records.py`, `statlab.py`, `StatLab.jsx`.
- Adding a filter or query on `v_effective_player_season_stats` or `game_appearances`.
- Symptoms: a filter raising a total; matches disagreeing between header and grid; strike rate too high; junior season in senior career; Records 15s.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/stats-figures-records-and-filters.md`. Grep hints: `milestone_totals`, `RETIRED NOT OUT`, `A rate is only as good`, `Season × grade`, `A washout is not`, `StatLab: one player`, `Grade Type / Match Type`, `several values at once`, `A grade is several things`, `IMPORT RESIDUAL`, `Junior stats split`, `Awards`, `Stats by competition`, `two match counts`, `Which lens a panel`, `Hide a club's juniors`.

**Related guides**: sync and import guides (writers of `not_out`, `balls`, `match_format`, `status`, residual rows); CricketStatz/import pairing guide (paired twins, per-innings views).

## Standing rules

**Rates (migration 282, `services/rate_coverage.py` as `rc`)**
1. Runs and balls in a rate come from the same innings. Never `SUM(runs)/SUM(balls)` across a season or career. Only the ratio changes source; runs, innings, wickets keep theirs.
2. Covered = `balls IS NOT NULL AND (balls > 0 OR runs = 0)` (old sync stored a missing count as 0).
3. No scorecards (BetterImport totals): the aggregate stands, payload `basis: "aggregate"`. Do not withhold.
4. Minimums count covered innings/spells. Platform default 0 on purpose (`organisations.stats_min_rate_innings`/`_spells`, NULL = none, via `services/stats_display.py`). A viewer's explicit 0 is real: test None, not falsiness.
5. Strike-rate records are per season, never all time.
6. Rates come from the server only. Use `rc.with_coverage` (presence-aware) and `batting_rate_columns(extra=...)` when did-not-bat rows are selected. Every new rate query imports `rc`.
7. Overs are cricket notation (10.2): convert to balls before summing or dividing.
8. Per-innings SR is derived on read (`rc.innings_strike_rate_sql`), never stored or backfilled.
9. Coverage mark is a dagger, never an asterisk; notes only where the figure is short and shown.
10. StatLab family targets re-derive from covered halves and publish no coverage pair. Scout and `iq._their_key_players` stay on aggregates.

**Dismissals and matches played**
11. `services/dismissal.py` is the one rule, whole-phrase, never `LIKE 'retired%'`. CA ids: 0 DNB, 1 Not Out, 8 Retired Hurt, 13 Retired, 14 Retired Not Out, 15 Absent. 14 (Law 25.4.2) and 8 are not dismissals; 13 (25.4.3) is.
12. Fix the writer (`sync.py`, live scorecard merge), not readers. Every average is `innings - not_outs` (by-opposition, by-venue, by-position, by-grade too). A retirement leaves the dismissal donut; retired-out stays.
13. `games.status` (266) is CA's word verbatim (`result` NULL cannot tell washout from unplayed). `services/game_status.py` is the one vocabulary (`NOT_PLAYED_STATUSES`; NO RESULT excluded). A named player with no bat/bowl/field row in a not-played fixture is subtracted.
14. That correction lives in `v_effective_player_season_stats` AND every reader counting `game_appearances`, via `appearance_counts_as_match(alias)` (StatLab `appear`, by-grade, by-season-grade, by-venue, Formats). Ask which source a new screen reads. Recent-games lists keep washouts.

**Grade scope (`services/grade_scope.py`; 228, 229, 259, 283)**
15. `GradeScope` is the one place a selection becomes SQL. Gate on `scope.active`, never `scope is None`. Empty exclusion set emits no clause.
16. Category is EXCLUSION: `col IS NULL OR NOT (col = ANY(excluded))`; a row we cannot categorise is not known junior, so kept. Never an include-list. Resolved per grade NAME in Python.
17. `grades.categories`/`match_formats` are TEXT[]; `grades.category` tracks the first entry. Every writer of `category=suggest_category(...)` also writes `categories=` (sync x2, manual_entries x2).
18. An explicit category pick matches ANY of a grade's categories; the club DEFAULT and `judge_primary=True` judge the primary only.
19. Format is per FIXTURE (`games.match_format`; `format_sql_case()` mirrors `format_from_match_type`, change both). An unlabelled game uses its grade's format only if the grade plays one; `format_from_match_type` returns None for unknown strings; unplaceable formats are left OUT of an explicit format filter.
20. `clause(col, kind)`: `game` (default), `aggregate` (`AND FALSE` under a format filter), `grade` (EXISTS, true grade listings only). A query joining `v_effective_games` is per fixture (`game_alias="g"`). `scope.active` includes `format_active`.
21. A picked grade beats the CATEGORY half only (`GradeScope.formats_only()`). Picked-grade SQL is separate: add `{scope_clause}` and its bind there too (records.py has five fragments).
22. `_RESIDUAL_SOURCES = (manual_aggregate, manual_career, import)` are added back under a category scope; never `api`/`manual_game` (double count).
23. Import residuals classify by `grade_label` (v9.89.2): `excluded_labels` in `resolve_scope`; `clause(..., label_column=...)` is a CASE (id, else label as `text[]`, else kept). Sites: `_career_residuals`, `_residual_totals_cte`, `_season_by_season_scoped`, StatLab residuals.
24. Competition axis (283) is an INCLUSION: subquery on `grades.competition_id` (`ix_grades_competition`), not a grade-id list. Junk or foreign ids drop; an all-junk pick is an ACTIVE filter matching nothing. Ungrouped grades, residuals and grade-less manual games drop out (`_fetch_manual_games_as_list` takes the scope).
25. A grade is in at most one competition. Competitions are the club's groups, seeded one per association (`grades.association_id`); `is_seeded` clears on a person's edit so sync never renames. `grades.competition_id` is ON DELETE SET NULL.
26. `resolve_scope_for_player` widens category only when the default leaves a junior-only player empty (`stats_auto_show_played_grades`, 229), never a format, profile only, gated on `scope.category_active`.
27. `organisations.stats_grade_categories`: empty or all-junk stores NULL. Age-group regexes end `\d+s?`. `grades-with-stats` computes classification in its own query (unnesting inflates runs). Filter rows hide when there is nothing to choose; `api.js` has one `scopeQuery()`.

4a. The Players page is a roster: it sends `min_rate_innings=0` and `min_rate_spells=0` because a board minimum drops the player, not just the rate. M is `max(batting.games, bowling.games)`. A new page that borrows a leaderboard for a list of people does the same. Check: `frontend/scripts/verify-players-page.mjs`.

**Career matches and lenses (say it, never renumber)**
28. Header matches = `SUM(player_season_stats.matches)` (CA, no grade). Any active scope (club default included) switches to games we hold, PLUS CA's season total for a player-year with no in-scope scorecard (`services/summary_only_seasons`, v9.106.3; one definition for profile, boards and milestones). A new residual reader must use it, and a caller of `_residual_totals_cte` must bind `club_player_ids` and `org_id`. The by-grade grid uses per season AND grade `max(held, CA per-grade)` plus unplaceable shortfall. Do NOT adopt `max` in the header (rewrites ~19k players).
29. `services/match_coverage.py` reads both figures itself. Grade-less games count as held. `extra_scorecards` and `without_scorecard` are separate, never negative. Note only where they differ, never for last-N/date windows, and under a scope it names both sources. Grid note is summed from its own rows and off while the grid is scoped. The profile header carries only an "i" beside MATCHES (`MatchCoverageInfo`, same panel as `MatchCoverageNote`); no sentence beside the figure. Do not render the headline note there.
30a. A synced game CA calls COMPLETED (or has no status for) with an EMPTY scorecard (no innings scored, no real batting line, no bowling spell) is not a match played: `game_status.looks_unplayed_sql`, folded into `not_played_game_sql`, which `appearance_counts_as_match` and the raw status checks (`_scoped_games_played`, the `played` CTE, `milestone_totals`, `sync` missing-totals backfill) use. A game that started and was stopped still counts (never judge the result against the play). Hand-typed games are never `games` rows, so never inferred. The unscoped header is CA's own aggregate and already excludes these: do not subtract there. Every verification harness needs `games.innings_totals` (lifespan DDL, not on the ORM model, so `create_all` omits it).
30. `get_player_team_breakdown`: one (season, grade) cell map, per season, folded seasons (`load_reverse_alias_map`), `unattributed` only when non-zero. It takes the scope (scorecards fully; CA per-grade by category/competition; a format is `aggregate`). The gap heuristic is gated PER SEASON (`mixed` seasons left to scorecards, `seasons_left_to_scorecards`); a senior-only player's grid must be byte-identical under the club default and no scope.
31. Reach notes (`components/FilterReach.jsx`: `enumeration`, `career`, `unfiltered`) fire on the RAW pick (`catParam`/`fmtParam`/`compParam`), never the club default; name only filters on; `FilterReachDot` on tabs. New panels must declare reach. Teammates and captain-stats take the scope (`_og_cte`). Honours never filtered.
32. Competition pill order is `display_order` (`POST /admin/competitions/reorder` sends the whole list).

**Milestones (`services/milestone_totals.profile_totals`)**
33. `profile_totals` is the ONE definition (profile default scope, junior auto-widen, ids as an array); every milestone surface reads it. Entries carry `junior_split`, `counts`, `variant` (dedupe key carries the basis). "Without junior" is `judge_primary=True`.
34. `sync._compute_milestones(reconcile=True)` removes thresholds no longer reached, keeps dates, runs at the END of sync; `match_pull_failed` only adds. Reached = `max(profile figure, whole unscoped career)`. Catch-up adds are undated (`achieved_at` NULL) unless the player has a game within `notification_scan.LOOKBACK_DAYS` (21), else `_src_milestone_achieved` emails "just reached".

**StatLab**
35. `context.player_id` is NOT a `PLAYER_CONTEXT_FILTERS` entry (they set `needs_live`); `_with_player_filter` ANDs onto each target's final WHERE, not for family, team innings, derived. `TARGET_GUIDE` (`StatLab.jsx`) says which filters apply per target; keep it in step.
36. StatLab applies the club default. Scope rides in the context as `_scope` (browsers cannot send underscore keys). Aggregate-only queries carry their own clause (`query_family_career` in the JOIN, `query_family_season`, `derived_most_minutes_in_season`). Family targets cannot answer match type; say so.
37. Multi-select: `grade_names`, `season_ids`, `results`, `dismissals`; keep legacy `grade_name`. `_text_list` never comma-splits (repeated `?c_grade_names=`). Category/format stay one comma string. Share `_RESULT_CASE_SQL`, `_dismissal_match_sql(param)`. `dismissals` in the innings block; `results` in `_RESIDUAL_DISQUALIFYING_LIST_KEYS`, coerce first. Seasons via `_pss_season_filter`.

**Records, awards, grouping**
38. `get_records` runs `SET LOCAL jit = off` first. Every board on `v_effective_player_season_stats` carries `pss_club_clause` (`pss.player_id = ANY(CAST(:club_player_ids AS uuid[]))`, resolved once, beside `pss_gender_clause`). A bound array pushes down; `= ANY (SELECT ...)` is a semi-join on the whole view (49.8s vs 0.9ms). Never tidy it into a subquery; cast it. A predicate on a view is paid per reference.
38a. JIT is off for the whole app (`connect_args={"server_settings": {"jit": "off"}}` in `models/db.py`), not only in Records: the `v_effective_*` views plan at millions and every read compiled first (7s against 0.66s). Never a per-route `SET LOCAL jit`; a new engine must carry the same parameter. `verify_club_pss_and_jit.py` asserts `SHOW jit`.
38b. `get_records` copies the club's `v_effective_player_season_stats` rows into temp table `_club_pss` once (lazily, in `q`) and the season-total boards read the copy. A new board that needs the season totals reads `_club_pss pss`, never the view.
38c. The per-innings boards read the club's own copies too (`_club_bi`, `_club_bs`, `_club_fs`, `_club_ga`, `_club_games`, built together, lazily, `ANALYZE`d), never `v_effective_batting_innings bi` / `_bowling_spells bs` / `_fielding_stats fs` / `v_effective_games g` directly: a direct read scans the whole platform (0.5 to 1.5s a board) and a bound array on the view alone was measured 25x WORSE (the views' `LEFT JOIN ... IS NULL` anti-join is costed at 0.5%). A statement that names a copy runs under `SET LOCAL enable_nestloop = off` (set and reset in `q`, not request-wide). The partnership, team and milestone reads stay on the views. `verify_club_pss_and_jit.py` asserts no board uses a view alias directly.
39. `q` times and labels every query (`_query_label`); `_timed` wraps non-board reads; declare `timings` above first use. `?debug_timing=1` returns `_query_timings` only to viewers who may see org private data; requests over `SLOW_RECORDS_LOG_MS` (2000) log worst queries.
40. Awards (`routers/award_definitions.py`): `STARTER_TEMPLATE` default, `GLOBAL_TEMPLATE` 'comprehensive', `APPLECROSS_TEMPLATE` for slug `applecross`; seed via `TEMPLATES` (unknown = starter), only into an EMPTY org. `ACHIEVEMENT_TREE` is the no-defs fallback. Tables are lifespan-created.
41. `run_grouping` (`services/competition_grouping.py`) is the one implementation. `sync_runs` kind `competition_grouping` is deliberately not in `_FULL_SYNC_KINDS` and not resumed. Idempotent (only NULL associations written). One run per club. `needs_grouping` is the only trigger, never `grades_ungrouped`. `MANAGE_MERGES`. `maybe_group_club` fires on `_sync_safe` success and Full Rebuild success; the 02:30 job stays. `/{slug}/competitions` must be known to Navbar `CLUB_SECTIONS`/`statsActive`, `SponsorFooter`, `FaviconManager`.
42. Records `matches` on the game-level career boards (`top_career_runs`, `top_batting_avg`, `most_fifties`, `most_hundreds`, `top_career_wickets`, `top_bowling_avg`, `top_allrounders`) is matches PLAYED, not matches batted or bowled in. `_appearances_sql` is the one "in the game" union (Most Matches uses it too); one `matches_played_rows` query is applied to the boards after they run, keeping a board's own count as a floor. Captain-only is left alone. Never count `COUNT(DISTINCT bi.game_id)` as a games figure; the unfiltered branch (`SUM(pss.matches)`) already means played.

**Hiding a club's juniors (`services/junior_hiding.py`; 315)**
42. `organisations.hide_juniors` + `club_competitions.is_junior` (NULL = the name's guess, TRUE/FALSE = a person's, never overwritten by sync). A junior grade is one in a junior competition, via `club_grade_rows` (a foreign row resolves to OUR competition). A junior-only player has junior evidence and nothing else; grade-less games, residual imports and seasons with totals but no grade evidence count as NOT junior (fail open). Derived on read, cached 120s, `forget()` on any tag/assign/delete/seed. The DDL is in `cricket_schema_mirror.SHARED_DDL_MODULES` (shared ORM models map both columns, so football's DB needs them).
43. It rides on `resolve_scope(..., hidden_grade_ids=)`: folded into `excluded_ids` AND kept in `hidden_grade_ids` so `formats_only()` restores it (a picked grade or `categories=all` never gets past it). Only for a public viewer: `routers/auth.public_junior_hiding` (inactive for `user_can_view_org_private` and switch-off clubs; `with_players=False` when only games matter).
44. Every `/players/{player_id}/...` route is gated by ONE router dependency (`_gate_junior_hidden_player`: 404 + the `_PUBLIC_HIDING` ContextVar the scope resolvers read). A new player route needs nothing; a NEW public route that names games or players must call `public_junior_hiding` itself.
45. A scope-less endpoint is only given a scope WHEN something is hidden (`_hidden_only_scope`), so every other club's answer stays byte-identical. Not covered: yearbooks, honours, achievements, awards, club rankings, stored milestone rows (see archive).
46. A player can ask to be removed (`players.privacy_hidden_at/_by/_reason`, migration 316, `services/player_privacy.py`, `python -m app.scripts.hide_player_at_request <id> [--report|--apply|--restore]`). It sets `is_public` false (the one hiding mechanism) and records WHY; the club cannot undo it (profile PATCH `is_public: true` and a photo upload return 409, a bulk profile import skips it), photos are deleted including `scouted_players` copies (restore never brings them back). It hides EVERY club's row for the same CA participant id (`player_privacy.siblings`) and records `player_privacy_suppressions(grassroots_id)`; `protect_new_player` (called from `sync._resolve_org_player` and the fill-in claim in `routers/players.py`) makes a row minted later born hidden. A NEW player-minting path that knows the participant id must call it. The row is never deleted: sync resolves to it, and the match records hang off it. `is_public = false` is enforced by the router gate on EVERY `/players/{id}/...` route (not just the profile), the sitemap and the share card. For a person who asked (`privacy_hidden_at` set) the gate has NO admin escape: every route 404s for everyone except the capability-gated management routes in `_PRIVACY_MANAGEMENT_ROUTES` (profile, aliases, request-sync, claim, rename); a NEW management route a hidden person's admin screen needs must be added there. The club's own `is_public` switch keeps its admin escape. The WHOLE public site is covered by `services/privacy_scrub.PrivacyScrubMiddleware` (added in `main.py`): every text GET response is scrubbed of a removed person's ids and every written form of their name, each scrubbed site-wide ONLY when it can only mean them (`_unambiguous`: full name unless another player has the same first name, initial form unless one shares the initial, bare surname unless anyone shares the surname); on `/games/{id}/scorecard` the ambiguous forms are resolved from who is in the card (`Scrubber.scrub_card`: the removed person's id must be present and no other card name may share the surname/initial), otherwise left alone so a relative is never masked; a request with a VALID SESSION COOKIE (`bs_session`, JWT checked, NOT an Authorization header: sign-in is by cookie) to `MANAGEMENT_PREFIXES` or the admin profile routes is NOT scrubbed, a session alone never unscrubs a public route, `/iq` and `/scout` are NOT exempt (they show other clubs' players); PUBLISHING output is scrubbed for everyone: `/admin/social/*` always, and any request carrying `X-Publishing: 1` (`lib/api.js` `setPublishingContext`, set by `AdminSocialPost`; a NEW screen that builds published or printed output must set it). In publishing mode a record carrying the person's id is DROPPED from lists (a ranking, a shortlist, a roster), except `/admin/social/scorecard/*`, where the row stays masked so totals add up; records are matched by id first (`Scrubber.structural`), because social payloads hold the name as separate `first`/`last`/`short` fields that text matching cannot see when a relative shares the surname. A NEW management prefix a club works from while signed in must be added there or its screen shows "********". Re-run `verification/audit_hidden_player_exposure.py` (calls every GET route signed out; its before-pass is the control) after adding public routes. Not caught: a nickname nobody recorded, text inside an image or PDF, anything already in a search engine or archive. Evidence for the person: `python -m app.scripts.hide_player_at_request <id> --evidence [--format html] [--no-verify] > file` writes a PDF (fpdf2) or page of clickable links to every match they are in plus their profile, with a live check of each (`services/privacy_evidence.py`); it must never mention anything financial, and its profile check requires the words "Player not found" (a mistyped URL is also a 404).
47. M on a Leaderboard is matches PLAYED under every pick, a grade included (`_matches_played_cte`, narrowed by `_grade_matches_played` for a picked grade); never `COUNT(DISTINCT game_id)` over a board's own rows (finals-only and captain-only keep their own meaning). A picked-grade board always joins its import CTE, or the `_NO_IMPORT_*` stand-in. StatLab's Grade picker sends the DISPLAY name, so a grade-name match must accept the canonical name (saved reports) and the club's rename (`_GRADE_NAME_MATCH_SQL`, `_residual_grade_match`).

## Traps and failure signatures

- Strike rate 320 or 333.33 beside blank balls: rules 1, 6. Overs summing to 20.4: rule 7. Header average differs from StatLab: rule 12. 13 matches where the club counts 10: rules 13, 14.
- A filter INCREASES a total (333 to 337), or header, note and grid read 309/313/314: source switch, not a bug (rules 28 to 30).
- Residual under Juniors/Women's/Masters: rule 23. Match Type pills dead with a grade picked: rule 21. Mixed grade's every innings under a two-day filter: rule 20. "Under 14s" counted senior: rule 27.
- Settings stuck on "Loading…": handler missing `Depends(get_db)` passes `py_compile`; only awaiting fails. Call route bodies in suites.
- Grid drops on the default view for a junior-programme club: rule 30. Stray notes: rule 31. Records 15s: rule 38.
- `CREATE OR REPLACE VIEW` cannot drop a column (266 downgrade drops and recreates; 169's has the same latent defect).
- Harness tables: build from ORM models, copy lifespan DDL exactly (`bowling_spells.runs`, `audit_logs.org_id`; a swallowed failure aborts the transaction).
- Milestone `--apply` when the dry run REMOVE list is mostly juniors-turned-seniors: that is scope, not a fix.

## How to verify a change here

- Real-Postgres suites (shipped route bodies), each with a control run that must fail without crashing: `verify_rate_coverage.py` and `_everywhere.py` (control reads 333.3, 127.27), `verify_retired_not_out.py` (12.83), `verify_milestone_figures.py`, `verify_match_coverage.py`, `verify_stats_by_competition.py` (re-run for any `GradeScope` change), `verify_hide_juniors.py` (control reads juniors on the public site; also run its browser twin), `verify_junior_residual_scope.py` (18/376), `verify_statlab_player_filter.py`, `verify_records_timing.py` (asserts `pss_club_clause` precedes every `pss_gender_clause`). Browser twins: `frontend/verification/verify_*_browser.mjs`.
- Gotchas: read new keys with `.get`/`getattr` and guard clicks so a control reports; seed through the code under test; a rate fixture needs an innings the rate cannot use; capture stub state BEFORE the action; a seasons stub of `[]` hides the filter pills; the headline counts up, so wait then read `.pb-num`.
- Diagnostics: `ops/diagnostics/records_slow_board.sql`, `records_pushdown_test.sql`, `career_matches_sources.sql`.

## Operator commands and scripts

- `python -m app.scripts.reconcile_milestones <org|all> [--apply]` (dry run default).
- `python -m app.scripts.backfill_retired_not_out <org|all> --apply` (no network; re-derives `source='backfill'` rows after fixing innings; `source='api'` untouched). Fix Missing Totals again repairs nothing.
- `python -m app.scripts.backfill_game_status <org-id-or-slug|all>`; `python -m app.scripts.backfill_grade_associations <org|all> [--apply] [--no-group]` (one CA call per season; dry run default).
- Archive lists as due after deploy (status unknown): reconcile_milestones (Shoalwater); backfill_grade_associations (Applecross, Hamilton).

## Open follow-ups

- Records: `/records/{org}/milestones` still reads the per-innings views directly; the views' anti-join estimate is still wrong for every reader that is not `get_records`; `_club_pss` (0.6 to 1s) is the largest cost left; nothing cached or concurrent (cache on last sync; separate sessions, never `asyncio.gather` on one `AsyncSession`)
- Scout screens and `iq._their_key_players` not marked aggregate-basis; `iq_team._role_ratings`, `iq_trends._similar_players` use aggregates on purpose.
- `player_season_stats.batting_average` is a second stored copy.
- Result filter offers "Tied" but never matches. Family targets ignore other context filters. Gender filter casing bug. Club rankings unfiltered and unnoted (decision needed). Players with ~100 games and CA 0 unexplained.
- No PlayHQ competition name (WAF). AFL silo, BetterIQ, Yearbooks not on GradeScope defaults.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-STATS-1] "Milestones are deliberately never filtered" (v9.64.0) | reversed by v9.93.0 (`profile_totals` follows the profile default); Milestones reach-note copy may still say never filtered | Which lens a panel (L16385-16615), A milestone is measured (L454-537) | verify frontend copy, align
- [FLAG-STATS-2] Gap heuristic "skipped entirely under an active scope" (v9.64.0) | replaced by per-season gating in v9.64.1 (`seasons_left_to_scorecards` in `aggregations.py`) | Which lens a panel (L16385-16615) | retire blanket wording
- [FLAG-STATS-3] Family targets "left alone" (v9.59.0) | settled v9.65.1 | A rate is only as good (L3203-3427) | retire
- [FLAG-STATS-4] `if grade_id or grade_name: scope = None` (228) | narrowed by 259 to `formats_only()` (exists in `grade_scope.py`) | Junior stats split (L8226-8315) | keep rule 21
- [FLAG-STATS-5] "migration 282 applied... pre-283 schema" | 282 is rate qualification, 283 competitions; typo | Stats by competition (L15772-16384) | keep 283
- [FLAG-STATS-6] "Not yet run" for `records_pushdown_test.sql`, "only measures, nothing cached" | later sub-section reports the run and the shipped clause (`pss_club_clause`, `SET LOCAL jit = off` confirmed in `routers/records.py`); caching still open | Stats by competition (L15772-16384) | retire "not yet run"
- [FLAG-STATS-7] "Grid carries no scope", "teammates/captain unscoped" | closed in v9.64.0 and v9.64.1 | Stats by competition; Which lens a panel | retire
- [FLAG-STATS-8] `aggregations.py:511/553` line refs, "five sites" | stale | A washout is not a match played (L6569-6643) | verify with grep
- [FLAG-STATS-9] Timings, milestone dry-run counts, player-count splits | one-off production evidence, Sep 2026 | several | history only
- [FLAG-STATS-10] Gender filter kept on Leaderboard/Records with a casing bug | unchecked | A grade is several things (L7001-7212) | verify, fix or retire

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| A milestone is measured on the profile's figure, and a junior split is SHOWN (v9.93.0) (L454-537) | rules extracted | Rules 33, 34; Flags 1, 9 |
| A RETIRED NOT OUT IS NOT A DISMISSAL (v9.66.0) (L3112-3202) | rules extracted | Rules 11, 12; Operator |
| A rate is only as good as the innings behind it (migration 282) (L3203-3427) | rules extracted | Rules 1 to 10; Flag 3 |
| &nbsp;&nbsp;The one figure the browser still worked out (v9.65.1) | rules extracted | Rules 6, 8, 10 |
| Season × grade matches on a player profile (v9.37.3) (L6123-6190) | rules extracted | Rules 30, 32 |
| A washout is not a match played (migration 266) (L6569-6643) | rules extracted | Rules 13, 14; Flag 8 |
| StatLab: one player, and tabs that reshape the filters (v9.96.0) (L6760-6786) | rules extracted | Rule 35 |
| StatLab gets the platform's Grade Type / Match Type filters (v9.29.4) (L6787-6861) | rules extracted | Rule 36 |
| StatLab's list filters take several values at once (v9.29.2) (L6862-6939) | rules extracted | Rule 37; Follow-ups |
| A grade is several things at once (migration 259, v9.26.0) (L7001-7212) | rules extracted | Rules 15 to 21, 27; Flag 10 |
| AN IMPORT RESIDUAL IS CLASSIFIED BY ITS LABEL (v9.89.2) (L8165-8225) | rules extracted | Rule 23 |
| Junior stats split off career stats (migration 228, v9.18.0) (L8226-8315) | rules extracted | Rules 15, 16, 22, 26, 27; Flag 4 |
| Awards — default templates (v8.28.0) (L12666-12695) | rules extracted | Rule 40 |
| Stats by competition, and the association that runs a grade (migration 283, v9.60.0) (L15772-16384) | rules extracted | Rules 24, 25, 28, 38, 39, 41; Flags 5 to 7, 9 |
| &nbsp;&nbsp;The club groups its own older seasons (v9.61.0) | rules extracted | Rule 41; Traps |
| &nbsp;&nbsp;Which of the forty queries (record book timing) | rules extracted | Rule 39 |
| &nbsp;&nbsp;What the timing said: JIT and a platform-wide scan | rules extracted | Rule 38; Flag 6 |
| &nbsp;&nbsp;Name the club's players (record book) | rules extracted | Rule 38 |
| &nbsp;&nbsp;A career has two match counts | rules extracted | Rule 28; Flag 9 |
| &nbsp;&nbsp;Say the two figures differ (v9.63.1, v9.63.2) | rules extracted | Rules 29, 41 (grouping hook); Traps |
| Which lens a panel is under, said on the panel (v9.64.0) (L16385-16615) | rules extracted | Rules 30, 31 |
| &nbsp;&nbsp;The grid answers to the bar now | superseded by "The review, and what it changed (v9.64.1)" | Rule 30; Flag 2 |
| &nbsp;&nbsp;A club default is already a filter | rules extracted | Rule 29 |
| &nbsp;&nbsp;The review, and what it changed (v9.64.1) | rules extracted | Rules 30, 31; Flag 7 |
| &nbsp;&nbsp;Hamilton's second ask was unmet (v9.64.2) | rules extracted | Rule 6; Verify |
| &nbsp;&nbsp;The order of the competition pills (v9.65.0) | rules extracted | Rule 32; Verify |
