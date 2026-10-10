# Guide: BetterIQ (opposition, selection, trends, team analysis, scouting cards)

**Read this before**:
- Touching `backend/app/services/iq*.py` (`iq`, `iq_opponent`, `iq_scout`, `iq_team`, `iq_trends`, `iq_selection`, `iq_review`, `iq_filters`, `iq_ask`, `iq_prewarm`), `services/scouting_intel.py` or the `/iq/*` routers.
- Touching the frontend under `/admin/betteriq` (`IQLayout`, `OppositionScout`, `OppPlayerProfile`, `KeyPlayersCard`, `TeamAnalysis`, `PlayerTrends`, `PlayerDeepDive`, `MatchPreview`, `MatchReview`, `CheatSheet`, `SelectionAnalysis`, `ScoutingCard`, `scoutDna.js`, `PlayerLink`, `viz`).
- Adding any per-game read that attributes rows to "our side", or any grade/season filter in IQ.
- Changing the dossier or deep-scan payload shape.
- Symptoms: an opposition player on our list, "Couldn't load team analysis", `?player=undefined` links, dormant players shown as risers, header season over all-time numbers, a merged grade listed twice, dossier stuck on `building`.
- Wanting ball-by-ball, phase, toss or win-probability features (out of reach, rule 3).

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/betteriq.md`. Grep hints: `Opposition, Selection & Player Trends`, `Zeplin`, `grade_match_clause`, `grade_canonical_label`, `Review Fixes`, `Review Round 2`, `_current_season_year`, `Bowler deep-dive, captaincy`, `_discipline`, `Match review, par`, `opponent_ladder`, `batting_intel`, `Dossier cache`, `_BUILD_TASKS`.

**Related guides** (check `docs/dev-notes/guides/` for which exist):
- Stats/sync guide: shared-game player-scope rule, per-club player and grade ids.
- BetterSelect guide: `selection_pool.assemble_selection` is reused here.
- Grades guide: `grade_merge_logs`, `suggest_category`.
- Migrations: 059 `opposition_dossiers`, 063 `opponent_aliases`, 064 `opponent_player_tags`, 094 scouting intel.

## Standing rules

**Shape and ceiling**
1. Gated by `require_module("iq")` plus `MANAGE_IQ`. Own `IQLayout` (violet `--pb-accent`), routes under `/admin/betteriq`, tile appears when `MODULE_INFO`/`MODULE_META` have `built: true`.
2. Everything is a read-only, org-scoped read over the `v_effective_*` views (grades to seasons). Own tables only: `opposition_dossiers`, `opponent_aliases`, `opponent_player_tags`, `player_scouting_cards`.
3. We hold scorecards, not ball-by-ball. Phase, ball matchup, pressure, win probability, dot%, SR-by-ball-range and biggest-over swings are out of reach. The surviving matchup proxy is `iq._our_bowler_dominance` (from `bowler_wickets`). The UI says so in `coverage.notes`. Roadmap: `docs/community-cricket-analytics-brief.md`.
4. Scouting synthesis is rule-based, scorecard-derived, no LLM. Toss analysis needs a stored toss (none stored, see Flags).

**Player scope (cross-club leak)**
5. A match between two both-synced clubs is ONE `games.id` with BOTH clubs' per-innings rows. A per-game read that scopes the game but not the player mixes the opposition into "our" lists. Always add `p.organisation_id = :org_id` when attributing to our side. Fixed at `iq._our_performers_vs`, `_our_bowler_dominance`, `_last_meeting`, `iq_review.game_review`. Re-check every new per-game read.
6. `_our_performers_vs` drops redacted names (`^\*+$`) and returns each player's BetterSelect `squad`.

**Selection**
7. `iq_selection` must reuse `selection_pool.assemble_selection` (routers/selection.py delegates to it): 12-month recency wall, gender wall, squad tier, per-date availability with period fallback. Re-deriving it let ghosts through (women's player or dormant names as promote picks for a men's 2nd XI).
8. It adds: XI balance (pace/spin, keeper, openers, all-rounders, LH/RH), last-5 form, warnings (no keeper, attack under 5, ineligible flags, bat form under 15), promote (`autofill_eligible`, available, in form, unselected), rest, tier up/down, match-up column, and `_best_available_xi` (greedy, keeper and 5+ bowlers enforced, diff as `suggest_in`/`suggest_out`).
9. `list_lineups` LEFT JOINs `fixture_lineups` and keeps upcoming fixtures with 0 picked (`HAVING COUNT(fl)>0 OR f.played_on >= CURRENT_DATE`); UI shows "needs selecting".

**Opponent identity and dossier**
10. `opp_key = COALESCE(opp_org_id, opp_club_name)`. `_resolve_opp_key` prefers an explicit `opponent` over `fixture_id` (that is how "Match club" links an unlinked fixture).
11. `opponent_aliases` (unique org, lowercased alias_name) stores matches: `iq.save_opponent_alias`, `POST /iq/opposition/match`; `_load_aliases` is defensive (`{}` if not migrated) and checked first in the fixture branch.
12. Two layers: `iq.py` instant report from held data; `iq_opponent.py` live dossier. Sync discards the opposition half of a card, so the dossier re-fetches the fixture grade's matches from Grassroots `/scores/*`, keeps the opponent (`teams[].owningOrganisation.id` not ours, or club-name match), aggregates current-season batting/bowling/fielding per `participantId`, plus a capped head-to-head re-fetch. A never-played opponent is still scoutable.
13. Opponent stats are NOT normalised: the JSON in `opposition_dossiers` is the only place they land (small data-rights surface).
14. Dossier builds in a detached `asyncio` task with its own `async_session_maker` session; hold it in `_BUILD_TASKS` (GC). `status` building/ready/error, frontend polls `GET /iq/opposition/dossier`. TTL 7 days, `POST .../dossier/refresh` forces.
15. Bump `iq_opponent.DOSSIER_VERSION` on any dossier shape or synthesis change so all cache keys rebuild (same for `iq_scout.DEEP_VERSION`).
16. Bounds: `MAX_OPP_SEASON_MATCHES=18`, `MAX_HEAD_TO_HEAD_GAMES=25`, shared scorecard cache, semaphore(6). `_overs_to_balls(10.2)=62`.
17. Synthesis: `_enrich_batter`/`_enrich_bowler` add `key_note`, `plan`, `risk`, `confidence` (sample-gated) and `alert` (danger: hot form or big average vs us; caution "paper tiger": not-out-inflated average, one big score, low sample, slow SR). `_how_they_win_lose`, `_game_plan`, FOW partnership map (`season_fow`) and `dismissal_breakdown` ride on the dossier.
18. `opponent_ladder` (`GET /iq/opposition/ladder`) reads the LIVE ladder for the fixture grade, current standings only (no snapshots). Opponent row matched by club-name tokens, stop-words stripped.

**Filters**
19. Filters must mean what they say. `OppositionScout` defaults season to All on first visit (`ctx.touched` false).
20. `ctx.team.id` may be grade base-names joined with `'||'`. Use `iq_filters.grade_match_clause` (`= ANY(string_to_array(:grade,'||'))`) for every grade match; one `:grade` bind serves one or many. Frontend compares with `teamNames()` (`Context.jsx`). "Seniors only" preset comes from `team_grades().category`.
21. Grade filters must honour merges: `iq_filters.grade_canonical_label(alias, org_param)` (single hop, like `aggregations._GRADE_MATCH`) before stripping the sponsor suffix. Used by `season_grade_clause`, `iq_team._scope`, `player_impact`, `iq_trends._movers_src`, `iq._opp_scope`, `team_grades`. `org_param` defaults `"org"`; `iq.py` binds `"org_id"`.
22. `team_overview(season_id, grade_id)`: `_scope` prefers `gr.id`, else `gr.season_id`, else all-time. `GET /iq/team/grades` feeds the bar. `_team_fielding` reads `v_effective_fielding_stats` (outfield = `catches - catches_wk`).

22a. The opposition dossier honours Grade Type / Match Type and the fixture's grade. The router puts the scope in a ContextVar; `iq_opponent` rebuilds it against THEIR grades (`_opponent_scope`, category on primary category, `formats_only()` once a grade or team is picked) and applies it in `_db_season_accumulators`, `_our_games_vs` and `_target_season_grades`. A scout started from a fixture (`grade_id` set) with no grade or team defaults the grade filter to the fixture's canonical grade (`grade_from_fixture`), and a grade taken from the fixture is never relaxed to the whole club: an empty answer sets `scoped_empty` and never falls through to the live whole-club scout. The scope is in the cache key (`_scope_sig`) and prewarm builds under the club's default scope. Not covered: the live Grassroots path (non-synced opponents) has no per-game format, only grade-level scope on our side.

22b. The opposition's NAMED XI (`services/iq_lineup.py`, `GET /iq/opposition/lineup`, `OppLineup.jsx`) is read live from the fixture's match record, never stored: `Fixture.playhq_id` is the Grassroots match GUID (a hand-added fixture has none, status `no_match`), `gr.get_match_detail` carries `teams[].players[]` (empty means not named yet, status `not_named`). Their side is found by their org id or club name; "the team that isn't ours" is only used when OURS is positively in the record. Players match to the dossier by participant GUID, then full name, then surname plus first initial; a name that fits two scouted players matches neither, and a redacted junior matches by GUID only (CA can issue a different GUID on this route). Two pools: the page's own dossier (`pool: grade`), then their whole club with NO Grade Type / Match Type filter (`pool: other_sides`) so a 1st XI T20 player named in the 3rds is flagged, labelled as form from another side and never blended in. The whole-club pool is always read: it is also where every named player's grade history comes from (`grades` on dossier rows, grade name to distinct matches, both scouting paths; `attach_grades`: usual grade is the busiest, a tie goes to the fixture's grade). "Higher/lower side" is only claimed between spelled-out ordinals (1st, 3rd); `Div 1` and `T20` are competitions, not rungs. `analysis.lines` is the rule-based quick read (threats with a small-sample note, visitors, danger players not named, never scouted, names that fit two players); Ask IQ's `opponent_lineup` tool returns it with the players. The route takes the same `team`/`grade` as the dossier route.

**Team analysis and trends**
23. Team scores are reconstructed: ours `SUM(batting_innings.runs)`, theirs `SUM(bowling_spells.runs)` (extras excluded, so close not exact). One `_per_game` pull, aggregated in Python.
24. Wrap every optional `team_overview` add-on in `iq_team._safe(session, factory, default)` (logs, `session.rollback()`, returns default) so one heavy all-time query cannot blank the page. Avoid short SQL aliases like `no` (use `nout`).
25. Bowling overs are cricket notation: convert to balls in SQL (`FLOOR(overs)*6 + ROUND(frac*10)`) before summing.
26. `player_impact` (`GET /iq/team/mvp`) aggregates the whole current YEAR (`s.year = :year`), not one season id (a year spans several season rows), falling back to one id only if year is NULL. Whole-season measure by design, not form. Blend `1.0*bat + (0.9*wkt + 0.45*inv-econ) + 0.35*field`, z-scored, economy needs 30+ balls, scaled 0 to 100. Emits `player_id`, not `id`.
27. Trends gate on `iq_trends._current_season_year(org)` (MAX year with stats): `_batting_movers`, `_bowling_movers`, `_emerging` require `latest.year = :cur`. Min samples: bat 5 recent/10 prior innings, bowl 6/15 wickets. `list_players` returns current-season players with recomputed averages and BetterSelect squad.
28. `player_deep_dive` (`/iq/trends/player/{id}/deep`) makes ONE innings pull and derives all cards in Python (starts/conversion, dismissals, position, opposition min 2 innings, scouting note, `batting_style`, `context`, `selection_value`, `reliability`, `similar_players`). Add cards to that pull. Reliability: `_percentile` 25/50/90, failure = dismissed under 10.
29. `bowler_deep_dive` (`/bowling-deep`, all-time) reads `bowler_wickets`: wicket quality by `batter_runs` (set 30+, started 10 to 29, new under 10), fielder combos (c&b excluded), discipline; gated on `bdeep.wickets > 0`.
30. `_discipline` returns `None` when no extras are recorded anywhere (old cards omit them); no false "spotless" card. Min 10 overs season/50 all-time.
31. Floors: all-rounders 4 inns and 4 wkts season (10/10 all-time); bowling roles 60 balls season/300 all-time; captaincy min 3 games (`game_appearances.is_captain`); collapse = worst 3 consecutive wickets summing to 15 or fewer (from `partnerships` by `(game_id, innings_number)`, `is_club_innings`); pairs by `LEAST/GREATEST(batter1_id, batter2_id)`; similar-player needs 2+ shared features, similarity `100/(1+d)`.
32. Par (`innings.par`) = median first-innings total in bat-first wins plus lowest defended. `iq_review` (`/iq/review/*`) reuses the collapse reconstruction per game.
33. `MatchPreview` (instant report, deliberately not the live dossier), `CheatSheet` (print, light theme, `@media print` A4) and `MatchupMatrix` are frontend-only compositions of existing payloads.

**Scouting cards and tags**
34. Manual cards hold what CA never records (shot direction, length/line, bowler type faced), per player not per dismissal, for opposition and our own. Storage: JSONB `batting_intel`/`bowling_intel` columns on `opponent_player_tags` (key `(organisation_id, participant_id)`, participant = CA GUID = dossier `player_id`; migration 094 plus lifespan mirror) and table `player_scouting_cards` (unique `(org, player)`). Tags stay decoupled from the 7-day cache and merge on the frontend. Tag vocab (batting_hand, bowling_action, bowling_type, player_role, is_wicket_keeper, is_danger, notes) mirrors `players.*`; unknown becomes NULL.
35. `services/scouting_intel.py` (`clean_batting_intel`, `clean_bowling_intel`, `BOWLING_KINDS`, `BAT_SHOTS`, `BOWL_VARIATIONS`, `BOWL_DANGER`, `ZONE_LENGTHS`/`ZONE_LINES`) is the one validator for both upserts. Empty blob becomes NULL. `scoutDna.js` labels mirror the backend vocab: change both.
36. Saves are present-aware: `upsert_opponent_tag` writes a field only when its key is present (`CASE WHEN :x_present`) and returns the full stored row, so the four editors (tags, zones, batting, bowling) do not clobber each other. Same in `player_scouting_cards`. Editors send only their own keys.
37. Batting intel lists: `vuln_bowling`/`fav_bowling` (`BOWLING_KINDS`), `risky_shots`/`fav_shots` (`BAT_SHOTS`), `zones[20]` (4x5, 0 to 3), `strengths`, `weaknesses`, `plan`. Bowling: `stock`, `variations`, `zones`, `danger`, and the text fields. The pre-split `shots[]` key is a read-side fallback only (as `risky_shots`); never write it.
38. Routes: own players `GET/PUT /iq/trends/player/{id}/scouting` (gated by `players WHERE id AND organisation_id`); opponents `GET /iq/opposition/player-tags`, `PUT .../player-tags/{player_id}` (body may carry the intel blobs).
39. Be fair to bowlers: Bat/Bowl radar toggle (default stronger side), wagon wheel hidden for pure bowlers, deep scan (`iq_scout._scan_player_deep`) derives wickets and quality from opposition cards, reusing sync's `_parse_bowler_and_fielder`/`_BOWLER_CREDIT_DT`.

**Frontend and Ask**
40. `PlayerLink.jsx` is the one link: ours `/admin/betteriq/trends?player=`, opposition `/admin/betteriq/opposition-player?opponent=&player=` (or `&playerName=` for name-only rows, resolved once the dossier builds). Payload id is `player_id`.
41. `viz.Radar` has hover/focus tooltips and `legend`; pass `details` from `buildRadar`. Averages 2dp (`fmt2`). Catches use `total_catches_non_wk`/`total_catches_wk`. Add a `<Note>` "how this is worked out" to any opaque blended rating.
42. `iq_ask.py` tools: `upcoming_fixtures`, `opposition_report`, `opponent_danger_players` (via `get_or_start_dossier`, reports `building` when cold). Prompt: resolve the fixture first, keep picks team-relevant via `squad` (lower-grade record vs opponent is a "possible promotion"), point unlinked opponents at "Match club". `MAX_STEPS = 8`.
42a. Ask IQ can ask back. `ask_user` (options 2 to 5, cleaned by `_clarify_from`) ends the turn with `{answer, clarify:{question, options[{label, value}]}}`; the page shows buttons and sends the pick's `value` as the next message. History turns carry `clarified`; the turn after one is not offered `ask_user`, so a thread asks at most once. The prompt limits it to choices that change the answer (grade, season, format, which club), using real options from the tools. Each pick is a normal ask against the 20 an hour limit.

## Traps and failure signatures

- Opposition player on our list, or their best batter credited as ours: missing `players.organisation_id` scope (rule 5).
- Header says 2025/26, numbers all-time: rule 19.
- Merged grade shown as two options, each matching only its own games: filter skipped `grade_merge_logs` (rule 21).
- "Couldn't load team analysis": heavy add-on blanked the page; use `_safe` (rule 24).
- `?player=undefined`: payload used `id` (rule 26).
- Key in-form player missing from MVP: one season id instead of the year (rule 26).
- Dormant players as risers: no current-year gate (rule 27).
- Ghost promote picks: eligibility re-derived (rule 7).
- Zones editor wiped role/danger flags: whole-row overwrite (rule 36).
- Saved scouting intel vanished after the favoured/risky split: dropped `shots[]` read fallback (rule 37).
- Upcoming fixtures with no XI vanish from Selection: inner join (rule 9).
- Stale synthesis after a code change: `DOSSIER_VERSION` not bumped (rule 15).
- Dossier never finishes: task not held in `_BUILD_TASKS`, or reused the request session (rule 14).
- A "3rd XI" scout full of 1st XI or T20 numbers, header "whole club": the dossier ignored the fixture grade or the Grade Type / Match Type scope (rule 22a).
- Economy or workload wildly off: cricket-notation overs summed directly (rule 25).

## How to verify a change here

The archive records no dedicated suites for BetterIQ. Check by hand against a real Postgres with `v_effective_*` views built from the migrations:
- A shared fixture with both clubs' rows on one `games.id`: the opposition must never appear on our lists.
- The grade filter with one name, several (`'||'`) and a merged alias.
- Force an add-on to raise: `team_overview` must still return the core.
- Bump check: `DOSSIER_VERSION`/`DEEP_VERSION` after shape changes.
- `backend/verification/verify_iq_dossier_scope.py` (own database): the 3rds fixture under Men's and Two day must exclude the 1st XI's T20, a T20 game inside the same grade, and the juniors; a 4th grade fixture they have no side in must say `scoped_empty`, never the whole club. Run it against the previous commit for the control.
- `backend/verification/verify_iq_ask_clarify.py` (no database, scripted model) and `frontend/scripts/verify-ask-iq-clarify.mjs` (real page, stubbed `/iq/ask`) for the clarify buttons.
- `backend/verification/verify_iq_opponent_lineup.py` (real Postgres, stubbed match record; `SHOW=1` prints the generated text, read it) and `frontend/scripts/verify-opp-lineup.mjs` for the named XI.
- Frontend: first visit defaults season to All; deep links; `CheatSheet` print layout.

## Operator commands and scripts

None in this archive. Dossier refresh is `POST /iq/opposition/dossier/refresh`. Pre-warm (`services/iq_prewarm.py`, `/iq/opposition/prewarm*`) is documented in the setup wizard notes.

## Open follow-ups

- Toss and toss-decision analysis: needs a stored toss (`games` column plus sync capture).
- Historical "vs top 4" splits: needs ladder snapshots we do not keep.
- Ball-by-ball features (phase, dot%, biggest over, win probability): out of reach with scorecard data.
- Milestone watch removed from IQ home and trends overview (still in payload and the bell).

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-IQ-1] `DOSSIER_VERSION` "bumped to 3", `DEEP_VERSION`→2 | code has `DOSSIER_VERSION = 12`, `DEEP_VERSION = 3`; numbers are history | "Danger/false-threat alerts", "Manual scouting cards" (L13501-13527, L13641-13718) | keep the rule, ignore numbers.
- [FLAG-IQ-2] "NL Q&A is the one remaining phase", "no LLM" | `services/iq_ask.py` exists (`MAX_STEPS = 8`) and v8.74 documents its tools | "Opposition, Selection & Player Trends" vs "Filters honest" (L13501-13527, L13528-13596) | retire "parked"; keep "synthesis is rule-based".
- [FLAG-IQ-3] `_safe(session, factory, default)` | code signature is `_safe(session, factory, default, key=None, degraded=None)`, failed cards go in a `degraded` list | "Review Fixes v2.12.1" (L13597-13606) | verify, update rule 24.
- [FLAG-IQ-4] "We don't store the toss" | a scorecard note elsewhere in project docs says `matchSummary.teams` carries `wonToss`/`battedFirst`, contradicting the sync-path claim | "Bowler deep-dive, captaincy & bowling discipline" (L13616-13623) | verify against a live payload and `games` schema.
- [FLAG-IQ-5] Files not covered by the archive: `iq_phases.py`, `iq_phrases.py`, `iq_players.py`, `iq_radar.py` | their rules are unrecorded | all sections | verify when touching.
- [FLAG-IQ-6] Branch name `claude/gifted-babbage-7QE8g` | dated, likely merged | "Review Fixes v2.12.1" (L13597-13606) | retire.
- [FLAG-IQ-7] v2.12.2 scopes team analysis by single `grade_id`; v8.74 filters by grade names with `'||'` | not a conflict, but a new card must pick the right path | "Review Round 2" vs "Filters honest" (L13607-13615, L13528-13596) | verify.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| BetterIQ — Opposition, Selection & Player Trends (v2.1.0), L13501-13527 | rules extracted | Rules 1 to 4, 7 to 10, 12 to 18, 23 to 33 |
| - v2.1.0 Selection and Player trends; v2.3.0 deeper analytics | rules extracted | Rules 7, 8, 10, 27, 28 |
| - v2.4.0 dossier depth; v2.5.0 synthesis; v2.9.0 alerts | rules extracted | Rules 3, 4, 15, 17 |
| - v2.6.0 team self-analysis; v2.10.0 fielding/memory/selection value | rules extracted | Rules 23, 24, 28 |
| - v2.7.0 player deep-dive; v2.11.3 reliability | rules extracted | Rules 15, 28 |
| - v2.8.0 cheat sheet; v2.11.1 matchup matrix | rules extracted | Rules 3, 33 |
| - v2.10.1 all-rounders; v2.10.2 pairs; v2.10.3 similar; v2.11.2 collapse; v2.11.5 attack | rules extracted | Rules 25, 31 |
| - v2.11.0 Club MVPs | rules extracted | Rule 26 |
| - v2.11.4 milestone watch on home | superseded by "Review Fixes v2.12.1" (removed) | Open follow-ups |
| - v2.12.0 consolidation and polish | rules extracted | Rule 41 |
| BetterIQ — Filters honest, cross-club leak fix, multi-grade filter, clickable players, fixture-aware Ask (v8.74), L13528-13596 | rules extracted | Rules 5, 6, 19 to 21, 40 to 42 |
| BetterIQ — Review Fixes (v2.12.1), L13597-13606 | rules extracted | Rules 9, 11, 24, 26, 27; Flags 3, 6 |
| BetterIQ — Review Round 2 (v2.12.2), L13607-13615 | rules extracted | Rules 22, 26, 27, 41; Flag 7 |
| BetterIQ — Bowler deep-dive, captaincy & bowling discipline (v2.14.0), L13616-13623 | rules extracted | Rules 4, 29 to 31; Flag 4 |
| BetterIQ — Match review, par, role-adjusted batting & batting depth (v2.15.0), L13624-13634 | rules extracted | Rules 28, 32 |
| BetterIQ — Match preview, opponent ladder & opposition scouting tags (v2.16.0), L13635-13640 | rules extracted | Rules 18, 33, 34 |
| BetterIQ — Manual scouting cards: batting & bowling intel (v8.26.0), L13641-13718 | rules extracted | Rules 12 to 16, 34 to 39; Flag 1 |
| - Batting intel favoured vs risky split; Two data layers; Dossier cache; Ceiling; Bounds | rules extracted | Rules 3, 12 to 16, 37 |
