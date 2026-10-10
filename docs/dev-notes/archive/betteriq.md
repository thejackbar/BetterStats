# Archive: betteriq

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: BetterIQ opposition, selection, trends, team analysis, scouting cards.
Read the distilled rules first: `docs/dev-notes/guides/betteriq.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L13501-13527 -->
## BetterIQ — Opposition, Selection & Player Trends (v2.1.0, June 2026)

Best-tier analytics module (master-plan Phase 4). Gated by `require_module("iq")` + the `MANAGE_IQ` cap. Module surface mirrors BetterSelect — own `IQLayout` (violet `--pb-accent` override), dashboard tile + sidebar entry flip on automatically once `MODULE_INFO`/`MODULE_META` have `built: true`. Routes under `/admin/betteriq` (Overview + Opposition + Selection + Player trends). **NL Q&A is the one remaining phase** (still needs an LLM-provider decision — open in the spec).

**Selection & Player trends (v2.1.0)** — two more read-only surfaces, both pure reads over held data (org-scoped via grades→seasons over the `v_effective_*` views):
- `iq_selection.py` (`/iq/selection/*`) analyses a fixture's saved BetterSelect lineup (`fixture_lineups`). **It reuses BetterSelect's own pool** — `services/selection_pool.assemble_selection` (extracted v2.2.0 from `routers/selection.py`, which now delegates to it) — so eligibility (12-month recency wall, women's/men's gender wall, squad tier, per-date availability incl. period fallback) is **identical** to the selection board. Re-deriving it earlier let ghosts through (a women's player / years-dormant names appearing as promote picks for a men's 2nd XI). On top it computes XI **balance** (pace/spin, keeper, openers, all-rounders, LH/RH from `skill_positions`+`bowling_type`), last-5 **form**, **warnings** (no keeper, thin attack `<5`, plus ineligible-pick flags: wrong-grade/inactive/dormant/unavailable, out-of-form bat `<15`), **promote** (`autofill_eligible` + available + in form, never selected), **rest** (ineligible/out-of-form picks), playing up/down via the pool `tier`, and a **match-up** column (each player's record vs the fixture's opponent via `resolve_opponent` + `opp_key`). `_resolve_opp_key` prefers explicit opponent so this stays correct.
- `iq_trends.py` (`/iq/trends/*`) reuses `aggregations.get_season_by_season` / `get_career_*` / `get_upcoming_milestones_for_org` + `milestone_rules`: per-player season-by-season **trajectory**, **breakout/decline** (latest season vs prior-career baseline, min-sample gated: bat ≥5 recent / ≥10 prior inns, bowl ≥6/≥15 wkts), and **milestone forecasting**. No new tables.
- **Opponent match-to-club**: `_resolve_opp_key` now prefers an explicit `opponent` over `fixture_id` (identity from the chosen club; the fixture only supplies the grade), so the Opposition UI's "Match club" search can link an unlinked upcoming fixture to a known `opp_key`.
- **Deeper analytics (v2.3.0)** — all read-only: **Trends** add recent-form sparklines (`_player_recent`), milestone **ETA** (career per-game rate, `_eta_games`), peak season + **consistency** (σ of season avg), **role-evolution** (bat/bowl share, first vs last third), and an **"emerging"** shelf (`_emerging`). **Selection** adds `_best_available_xi` — a greedy best XI from the `autofill_eligible` pool (keeper + ≥5 bowlers enforced) diffed against the picked XI (`suggest_in`/`suggest_out`). **Opposition** adds `_venues_vs` (W/L by venue) and `_our_bowler_dominance` (our-bowler × their-batter repeat-dismissal grid from `bowler_wickets`; merged with main's parallel whole-club opposition rework).
- **Live dossier depth (v2.4.0)** — `iq_opponent.py` (main's whole-club scout) now also parses opponent **fall-of-wickets** into a partnership-by-wicket / collapse map (`season_fow` → `partnerships` + `_partnership_insight`) and a team-wide **dismissal breakdown** (`dismissal_breakdown`, summed from the per-batter `dism` counters). Frontend `KeyPlayersCard.jsx` — a Uiverse crypto-card-inspired, IQ-themed showcase — flicks through the danger batters/bowlers with a headline stat, vs-us record and a drawn recent-form sparkline.
- **Scouting synthesis (v2.5.0)** — rule-based, scorecard-derived, **no LLM** (NL Q&A stays parked). In `iq_opponent._assemble`: `_enrich_batter`/`_enrich_bowler` add a `key_note` + recommended `plan` + `risk` + `confidence` (sample-gated per the brief's §19.5) onto each danger player; `_how_they_win_lose` + `_game_plan` produce team tendencies (top-order reliance, strongest/fragile partnership, thin attack) and a "How to beat them" one-pager (`remove_early` / `see_off` / `target_bowler` / `key_warning` / `one_liner`). Surfaced via `GamePlan` + `WinLose` in `OppositionScout`, enriched on the frontend with head-to-head + best venue + our-performers from the instant report. **North-star vision doc: `docs/community-cricket-analytics-brief.md`** — the full "digital cricket analyst" roadmap. Reality filter: our data is **scorecard-level, not ball-by-ball**, so phase/ball-matchup/pressure/win-probability features (brief §1.2–1.3, §2.2–2.4, §10.1, §15.1) are out of reach; the matchup proxy that survives is `_our_bowler_dominance` (our-bowler dismissals of their batters).
- **Team self-analysis (v2.6.0)** — brief §7/§8, the opposition lens pointed at us. `iq_team.py` (`/iq/team/*`, page `TeamAnalysis.jsx` at `/admin/betteriq/team`) reconstructs **our** team score from `SUM(batting_innings.runs)` and the **opponent's** from `SUM(bowling_spells.runs)` (runs our bowlers conceded), so bat-first vs chase, "what score wins" bands and defending/chasing all come from stored per-innings data (no live fetch) — close-but-not-exact (extras we don't store are excluded). One per-game pull (`_per_game`, org-scoped via grades→seasons over `v_effective_*`), aggregated in Python into record/home-away, batting profile (top/mid/lower split via `batting_position`, boundary%), bowling, bat-first/chase win%, score-band win rates, venue records, partnership-by-wicket (`partnerships.is_club_innings`), and a `_how_we_win_lose` synthesis.
- **Player deep-dive (v2.7.0)** — brief §1.4/1.5/1.9/1.10. `iq_trends.player_deep_dive` (`GET /iq/trends/player/{id}/deep`) does ONE innings pull (runs, not_out, dismissal_type, batting_position, opp_key) and derives in Python: **starts & conversion** (reach-25 %, 25→50, 50→100, score bands), **dismissal breakdown**, **batting by position** (Opening/First-drop/Middle/Lower/Tail buckets + best position), **by-opposition** (best/worst by avg, min 2 inns) and a rule-based **scouting note** (CricViz card §16.9). Surfaced as extra cards in the `PlayerTrends` detail view (lazy-loaded alongside the trend). Dossier `DOSSIER_VERSION` bumped so the v2.5 opposition synthesis (game plan / win-lose / scouting notes) rebuilds for **every** cache key — whole-club and each team — instead of waiting on the 7-day TTL.
- **Captain's Cheat Sheet (v2.8.0)** — brief §16.6. `CheatSheet.jsx` at `/admin/betteriq/opposition/cheatsheet?opponent=…&fixture=…&team=…` — a **print-ready, light-themed one-pager** composed entirely from the existing report + dossier payloads (no new backend): game plan, danger batters/bowlers (with their plan), our bowler match-ups (`bowler_dominance` → "save X for Y"), how-they-win/lose, our edge (`our_performers`) and head-to-head + best venue. `window.print()` + a `@media print` block (hides chrome, fits A4). "Cheat sheet" button in `OppositionScout` passes the current opponent/fixture/team through the URL.
- **Danger/false-threat alerts (v2.9.0)** — brief §16.2/16.3. `_enrich_batter` now adds an `alert` (`danger` reasons: in hot form / averages big vs us; `caution`/"paper tiger" reasons: not-out-inflated average, leans on one big score, low-confidence sample, slow SR); `_enrich_bowler` flags the main threat. `DOSSIER_VERSION` → 3 so caches rebuild. Surfaced as a Danger / "Paper tiger?" badge + reason line on `KeyPlayersCard`.
- **More scorecard analytics (v2.10.0)** — **Fielding/keeping** (brief §3/§9): `iq_team._team_fielding` → top fielders, keepers, run-out specialists + fielder→bowler catching combos (from `bowler_wickets.fielder_id`), in `team_overview.fielding`. **Opposition memory** (§16.10): `iq._last_meeting` → most-recent meeting result, our/their score (`SUM(batting_innings.runs)` / `SUM(bowling_spells.runs)`), our top bat & bowler that game, in the instant report. **Selection value** (§6.2): `iq_trends.player_deep_dive` adds `selection_value` — team win% with vs without the player (`game_appearances` vs all org games) + swing.
- **All-rounder analysis (v2.10.1)** — brief §5. `iq_team._all_rounders`: players who clear both a batting-innings and a wickets floor (4/4 per season, 10/10 all-time) over the per-game `v_effective_*` tables; bat avg recomputed exactly from `batting_innings.not_out`, bowl avg from `runs_conceded/wickets`; ranked by the classic bat_avg−bowl_avg diff and role-classified (genuine / batting / bowling all-rounder). In `team_overview.all_rounders`, board on the Team page.
- **Batting partnership pairs (v2.10.2)** — brief §11.1. `iq_team._batting_pairs`: groups `partnerships` (is_club_innings) by the unordered `LEAST/GREATEST(batter1_id, batter2_id)` pair, org-scoped via games→grades→seasons; per pair → stands, total runs, avg-per-stand, best, 50+ stands, and an `opening` flag (≥half their stands at the 1st wicket). `team_overview.batting_pairs`, board on the Team page.
- **Similar player search (v2.10.3)** — brief §15.8. `iq_trends._similar_players`: club-internal nearest neighbour over a career profile (bat avg [innings-weighted from `batting_average`], bat SR, bowl avg, economy — all from `player_season_stats`), z-scored across the squad and compared only on features both players have (≥2 shared), distance→similarity `100/(1+d)`. In `player_deep_dive.similar_players`, card in the Player trends detail.
- **Club MVPs / player impact (v2.11.0)** — brief §15.3 (the scorecard-reachable subset; ball-level inputs like phase/pressure/dot-balls are out of reach). `iq_team.player_impact` (route `GET /iq/team/mvp`, optional `season_id`, defaults to latest season via `team_seasons`): per-player per-match rates over `player_season_stats` (runs, wickets, fielding dismissals) + economy (≥30 balls), z-scored across the squad (`statistics.pstdev`), blended `1.0·bat + (0.9·wkt + 0.45·inv-econ) + 0.35·field`, min-max scaled 0–100, role-tagged (Batting/Bowling/All-round/Fielding). Headline board on `BetterIQHome`, rows deep-link to `trends?player=`.
- **Matchup advantage matrix (v2.11.1)** — brief §16.5. Frontend-only reshape of the instant report's `matchups.bowler_dominance` (already a flat bowler→batter pairing list) into a heatmap grid in `OppositionScout` (`buildMatrix`/`MatchupMatrix`): top 6 our-bowlers × top 8 their-batters, cells shaded by dismissal count, Matrix/List toggle (matrix when ≥2 bowlers and ≥2 batters). No backend change.
- **Collapse analysis (v2.11.2)** — brief §7.5. `iq_team._collapses`: reconstructs fall-of-wickets per club innings from stored `partnerships` runs (keyed by `(game_id, innings_number)`, is_club_innings), finds the worst 3-consecutive-wicket span (sum of three contiguous partnership runs), flags a collapse when ≤15, and reports collapse %, worst collapse, and a start-wicket histogram ("where the wheels come off"). `team_overview.collapses`, card on the Team page.
- **Batting reliability (v2.11.3)** — brief §6.1 (scorecard-reachable subset). `iq_trends.player_deep_dive` adds `reliability` computed from the SAME innings pull (no extra query): floor/median/ceiling via `_percentile` (25th/50th/90th of the runs distribution), failure rate (dismissed <10), 20+ contribution rate, and a boom-or-bust/steady/balanced `profile` from the coefficient of variation. Card in the Player trends detail.
- **Milestone watch on home (v2.11.4)** — frontend-only. `BetterIQHome` calls `iqTrendsOverview()` and renders the top upcoming milestones (`{needed} to {target} {type}`) in a panel beside the Club MVPs; rows deep-link to `trends?player=`. No backend change.
- **Bowling attack structure (v2.11.5)** — brief §8.3. `iq_team._attack_structure`: per-bowler workload over `v_effective_bowling_spells` — **overs are cricket notation** (10.2 = 10 overs 2 balls), so converted to balls in SQL (`FLOOR(overs)*6 + ROUND(frac*10)`) before summing; pace/spin split from `players.bowling_type` (`_PACE_TYPES`/`_SPIN_TYPES`), per-bowler econ/avg/SR + a Strike/Containment/Stock role tag (min 60 balls season / 300 all-time). `team_overview.attack`, card on the Team page.
- **Consolidation & polish (v2.12.0)** — frontend-only. `TeamAnalysis` reorganised from a ~13-card scroll into **Overview / Batting / Bowling / Players** tabs (a `tab` state + tab bar; cards regrouped, the stray "conceding on avg" line promoted to a proper Bowling summary card). Added a reusable `<Note>` footnote component and "how this is worked out" notes to the opaque blended ratings (Club MVPs on home, all-rounders, collapse, bowling roles, reliability, similar-player). Player deep-dive detail gets a "Deep dive" section divider between the season-trajectory cards and the per-innings cards. No backend/API change.

<!-- END original CLAUDE.md L13501-13527 -->
<!-- BEGIN original CLAUDE.md L13528-13596 -->
## BetterIQ — Filters honest, cross-club leak fix, multi-grade filter, clickable players, fixture-aware Ask (v8.74, Jul 2026)

Five related fixes/features from live feedback on the Opposition page:

- **Cross-club player leak (the "Zeplin in our bowl-well list" bug)**: a match
  between two both-synced clubs shares ONE `games.id` carrying BOTH clubs'
  per-innings rows (each club's sync attaches only its own players — by design,
  see the shared-game note in sync.py). Any per-game read that org-scopes the
  GAME (grades→seasons) but not the PLAYER join therefore mixes the opponent's
  players into "our" lists. Fixed by adding `p.organisation_id = :org_id` at:
  `iq._our_performers_vs` (both queries; also now excludes redacted `^\*+$`
  names and returns each player's BetterSelect `squad`), `iq._our_bowler_dominance`,
  `iq._last_meeting` (scoreline sums + top bat/bowl, which used to credit the
  opponent's best batter as ours), and `iq_review.game_review` (totals + top-5s).
  **Anti-pattern**: never read per-game tables "for a game in our org's grades"
  without also scoping `players.organisation_id` when attributing to OUR side.
- **Filters mean what they say**: `OppositionScout` no longer treats the
  default newest season as "no filter" while the header shows 2025/26 over
  all-time numbers. On first visit (filter bar untouched this session — new
  `ctx.touched` flag set by ContextBar interactions) the page defaults the
  global season to **All seasons**; any picked season/grade then genuinely
  scopes every instant-report card (backend already supported it).
- **Multi-select grade filter, IQ-wide**: `ctx.team.id` may now be several
  grade base-names joined with `'||'` — `iq_filters.grade_match_clause`
  (`= ANY(string_to_array(:grade, '||'))`) replaced every `= :grade` site
  (iq_filters/iq/_opp_scope/iq_team×2/iq_trends), so the SAME single `:grade`
  bind serves one name or many; all existing callers unchanged. The filter-bar
  TeamPicker is a checkbox multi-select with a **Seniors only** preset driven
  by `team_grades`'s new `category` field (stored `grades.category` else
  `grade_labels.suggest_category` — the merge-grades classifier). Client-side
  grade comparisons (MatchPreview/SelectionAnalysis fixture narrowing) use
  `teamNames()` from Context.jsx.
- **Clickable player names** (`PlayerLink.jsx`): our players →
  `/admin/betteriq/trends?player=`, opposition → `/admin/betteriq/
  opposition-player?opponent=&player=` (or `&playerName=` for name-only rows —
  the instant report's danger batters have no participant id; OppositionPlayer
  resolves it via its pending-name matcher once the dossier builds). Applied
  across OppositionScout (our-record, match-ups, last meeting, squad tables,
  radars, historical threats), KeyPlayersCard, TeamAnalysis boards, MatchReview,
  MatchPreview, SelectionAnalysis XI.
- **Radar context**: `viz.Radar` has hover/focus tooltips per vertex (score,
  and with `buildRadar`'s new `details` the actual value + peer mean) and a
  `legend` prop; opposition + deep-dive callers pass both.
- **Multi-grade also honours the merge-grades admin feature**: a club can
  merge two literally-different raw grade names (e.g. "PSWL South" / "PSWL:
  South") into one competition via `grade_merge_logs` (org-scoped active
  `alias_name -> canonical_name` rows, `aggregations._GRADE_MATCH` already
  reads it for leaderboards) — the first cut of this filter only stripped the
  sponsor parenthetical (`grade_base`), so a merged club still saw both raw
  names as separate filter options that each only matched their own literal
  games. `iq_filters.grade_canonical_label(alias, org_param)` resolves an
  active alias to its canonical raw name (single-hop, matching
  `_GRADE_MATCH` — merges are re-targeted onto the final root at merge time,
  not chased through a chain here) before stripping the sponsor
  parenthetical; `season_grade_clause`/`iq_team._scope`/`iq_team.player_impact`
  /`iq_trends._movers_src`/`iq._opp_scope`/`iq_team.team_grades` (the
  filter-bar listing query) all route through it. `org_param` defaults to
  `"org"` (every caller except `iq.py`, which binds `"org_id"`).
- **Ask BetterIQ fixture/opposition tools** (`iq_ask.py`): `upcoming_fixtures`,
  `opposition_report` (trimmed instant report; performers carry `squad` for
  team-relevance), `opponent_danger_players` (reads the dossier cache via
  `get_or_start_dossier` — a cold dossier starts building in the background and
  the tool reports `building`, so the model answers from held data now and says
  the deeper scout will be ready shortly). System prompt: resolve the fixture
  first; keep suggestions team-relevant via `squad` (a lower-grade record vs
  the opponent is a "possible promotion" mention, not an automatic pick);
  unlinked opponents → point at "Match club" on the Opposition page.
  `MAX_STEPS` 6 → 8 for the longer tool chains.

<!-- END original CLAUDE.md L13528-13596 -->
<!-- BEGIN original CLAUDE.md L13597-13606 -->
## BetterIQ — Review Fixes (Jun 2026, v2.12.1)

Post-v2.12.0 review pass (live-site feedback). All on branch `claude/gifted-babbage-7QE8g`.
- **Team analysis resilience**: `team_overview` wraps every optional add-on (fielding, all-rounders, batting pairs, collapse, attack, partnerships) in `iq_team._safe(session, factory, default)` — logs + `session.rollback()` on failure so one heavy/failing query (e.g. an all-time statement timeout) can't blank the page. Root cause of "Couldn't load team analysis" was the cumulative weight of the new all-time scans; the wrapper makes the core always render. Also renamed a risky `no` SQL alias → `nout`.
- **Club MVP links**: `player_impact` now emits `player_id` (was `id`) to match the IQ-wide convention; home-page deep-links were going to `?player=undefined`.
- **Current-season gating (trends)**: `iq_trends._current_season_year(org)` = MAX(season year with stats). `_batting_movers`/`_bowling_movers`/`_emerging` take `current_year` and gate `latest.year = :cur`, so years-dormant "active" players no longer surface as risers/decliners. `list_players` now returns **current-season** players with this-season stats (runs/avg, wkts/avg, recomputed from not_outs) **+ their BetterSelect squad** (`players.squad_team_id` → `teams.name`) for the new All-squads filter. Averages 2dp everywhere (frontend `fmt2`). Milestone watch removed from home + trends overview (still computed in payload / shown in the bell). Full player grid → `PlayerSearch` combobox.
- **Selection shows unselected fixtures**: `iq_selection.list_lineups` LEFT JOINs `fixture_lineups` and keeps upcoming fixtures even with 0 picked (`HAVING COUNT(fl)>0 OR f.played_on >= CURRENT_DATE`). Frontend shows "needs selecting" + a "no XI saved yet" prompt (empty `data.players`).
- **Opposition match persists** (migration **063** `opponent_aliases`: org_id, alias_name [lowercased], opp_key, display_name, unique(org, alias_name)): `iq.save_opponent_alias` upserts; `iq._load_aliases` (defensive — returns {} if the table isn't migrated) is merged into `opposition_opponents`'s `by_name` and checked first in `_resolve_opp_key`'s fixture branch. New `POST /iq/opposition/match`; frontend `applyMatch` saves then refreshes the picker. Once "Bassendean" → "Bassendean Cricket Club" is matched, all fixtures with that name link.
- **MVP is a whole-season value measure, not current form** — by design it's season-aggregate per-match rates (a late-season slump averages in). The home note says so; "Form movers" / recent-form sparklines are the form lens.

<!-- END original CLAUDE.md L13597-13606 -->
<!-- BEGIN original CLAUDE.md L13607-13615 -->
## BetterIQ — Review Round 2 (Jun 2026, v2.12.2)

- **MVP year-based**: `iq_team.player_impact` aggregates over ALL season records of the current YEAR (org-scoped `s.year = :year`), not a single `team_seasons[0]` season_id. A club year often spans several season rows (comps / per-club grassroots ids); keying on one id silently dropped in-form players recorded under a sibling row (Monument/Seen symptom). Year resolved from `resolved.year`; falls back to single season_id only when year is NULL.
- **Team analysis by season AND team (grade)**: `team_overview(season_id, grade_id)`; a `_scope(season, grade)` clause (prefers `gr.id`, else `gr.season_id`, else all-time) threaded through every per-game add-on. `_team_fielding` rewritten onto per-game `v_effective_fielding_stats` (grade-filterable + outfield catches = `catches − catches_wk`). New `team_grades()` + `GET /iq/team/grades`. Frontend defaults to the latest season with prominent Season + Team dropdowns.
- **Trends picker = current-season players**: `list_players` returns this-season players (org-scoped seasons join, merged with main's cross-club guard) + BetterSelect squad; `PlayerSearch` combobox opens on focus & reports empty states.
- **Player deep-dive depth**: reuses `get_player_by_venue` (at-venues) + `get_bowling_dismissal_breakdown` (how they take wickets); career strip splits Caught / Ct (wk) / Stumpings via `total_catches_non_wk`/`total_catches_wk`.
- **Opposition player scout** (frontend-only): the dossier already returns full `batting`/`bowling` per-player lists (form, dismissals, vs_us); `OppPlayerScout`/`OppPlayerDetail` in `OppositionScout` add a search → full per-player profile.
- **Caught vs caught (wk)**: PlayerProfile, Leaderboard, TeamDetail, Yearbook already split; fixed `PlayerComparison` (was `total_catches`) → `total_catches_non_wk` / `total_catches_wk`. StatLab keeps a total + keeper-only-preset model.

<!-- END original CLAUDE.md L13607-13615 -->
<!-- BEGIN original CLAUDE.md L13616-13623 -->
## BetterIQ — Bowler deep-dive, captaincy & bowling discipline (v2.14.0, Jun 2026)

Three scorecard-reachable additions from the brief (no schema change, no new tables, no LLM):
- **Bowler deep-dive** (brief §2.5/§2.9) — `iq_trends.bowler_deep_dive` (`GET /iq/trends/player/{id}/bowling-deep`), the bowling mirror of `player_deep_dive`. Reads `bowler_wickets` (org-scoped via games→grades→seasons) — the table was previously only consumed for opposition matchups (`iq._our_bowler_dominance`). Derives **wicket quality** from the dismissed batter's stored `batter_runs`: set (30+) vs started (10–29) vs new (<10), avg scalp value, ducks inflicted; **fielder combos** (`fielder_id` on caught/stumped/run-out, c&b excluded); per-bowler **discipline** (wides+no-balls/over from `v_effective_bowling_spells`); + a rule-based bowling scouting note. Surfaced in `PlayerTrends.jsx` under a new "Bowling deep dive" header — the existing career `bowling_profile` card (added v2.13.0, sourced from the `/deep` batting payload) was **relocated** there so all bowling reads together; the new section is gated on `bdeep.wickets > 0` independent of `innings_count`, so a pure bowler still gets it. `player_deep_dive` itself was left untouched.
- **Captaincy** (brief §4) — `iq_team._captaincy`, added to `team_overview` via `_safe`. First analytics use of `game_appearances.is_captain`: per-skipper W/L/D, win%, team avg score under them (reconstructed like `_per_game`), finals record. Min 3 games. Board on the Team page **Players** tab. **Toss-decision analysis is out** — we don't store the toss (the Partner API has `coinToss` but the GR `/scores/*` sync path doesn't capture it; would need a `games` column).
- **Bowling discipline** (brief §2.9/§8.5) — `iq_team._discipline`, added to `team_overview`. Team wides/no-balls per over, extras as % of runs conceded, most-disciplined-first per-bowler ranking (min 10 overs season / 50 all-time). **Guarded**: returns `None` when no extras are recorded across the dataset (older scorecards omit them) so we never show a misleading "spotless" card. Card on the Team page **Bowling** tab.
- All three respect the `season_id`/`grade_id` `_scope` filter on the Team page; the bowler deep-dive is all-time (matches the player-trend view).

<!-- END original CLAUDE.md L13616-13623 -->
<!-- BEGIN original CLAUDE.md L13624-13634 -->
## BetterIQ — Match review, par, role-adjusted batting & batting depth (v2.15.0, Jun 2026)

More scorecard-reachable brief items, no schema change:
- **Post-match review** (brief §16.8) — new service `iq_review.py` (`GET /iq/review/games`, `GET /iq/review/game/{id}`) + new page `MatchReview.jsx` at `/admin/betteriq/review` (sidebar entry "Match review"). Per game: scoreline (our `SUM(batting_innings.runs)` / their `SUM(bowling_spells.runs)`), top batting/bowling contributions, best partnership, extras conceded, a single-game collapse check (worst 3-consecutive-wicket span from `partnerships`, same reconstruction as `iq_team._collapses`), and a rule-based "what changed the game" synthesis. Biggest-over / win-probability swings are out (ball-by-ball).
- **Player batting depth** (brief §1.1/§1.2) — `player_deep_dive` now also returns `batting_style` (strike rate, boundary % = share of runs in 4s/6s, balls-per-boundary, accumulator/boundary-hitter profile — needs `balls`/`fours`/`sixes`, now added to its one innings pull) and `context` (batting average in wins vs losses, batting first vs chasing via `g.result` + `innings_number`). Dot% / SR-by-ball-range stay out (ball-by-ball). Cards in `PlayerTrends.jsx`.
- **Team depth** — all added to `team_overview` via `_safe`, all honour `_scope`:
  - `_wickets_quality` (brief §8.4) — club-wide `bowler_wickets` roll-up: top-order/middle/tail split + set/new batters dismissed + dismissal-type mix. Bowling tab.
  - `_team_starts` (brief §7.4) — opening-stand (`partnerships` wicket 1, club innings) profile + win rate after a good (≥30) vs poor start. Batting tab.
  - `_role_ratings` (brief §15.4) — buckets innings by batting position, pools a club average per slot, rates each batter by their primary-slot average minus that slot's average (so an opener and a No. 8 aren't judged alike). Players tab.
  - **Par score** (brief §15.9) — `innings.par` = median first-innings total in bat-first wins + lowest defended. Surfaced on the Overview "What score wins" card.

<!-- END original CLAUDE.md L13624-13634 -->
<!-- BEGIN original CLAUDE.md L13635-13640 -->
## BetterIQ — Match preview, opponent ladder & opposition scouting tags (v2.16.0, Jun 2026)

- **Opposition player scouting tags** (brief §13 "Useful Optional Metadata" — opponent edition) — `opponent_player_tags` table (**migration 064**): org-scoped manual attributes (batting_hand, bowling_action, bowling_type, player_role, is_wicket_keeper, is_danger, notes), keyed by `(organisation_id, participant_id)` where `participant_id` is the CA participant GUID = the dossier's `player_id`. Opposition players aren't in our tables (only the dossier JSON), so tags live **decoupled** from the 7-day dossier cache and are merged on the frontend. `iq.get_opponent_tags` / `iq.upsert_opponent_tag` (raw SQL, mirrors `opponent_aliases`; controlled-vocab fields validated, unknown→NULL); routes `GET /iq/opposition/player-tags` + `PUT /iq/opposition/player-tags/{player_id}`. Editor + coloured badges in `OppPlayerProfile.jsx` (`ScoutingTags` + `TagBadges`), wired through `OppositionPlayer.jsx`. Vocab mirrors `players.*` so the choices match our own players.
- **Opponent ladder standing** — `iq.opponent_ladder` (`GET /iq/opposition/ladder`): fetches the live grade ladder (`grassroots_scores_client.get_grade_ladder` + an inline `_ladder_rows` parser of the documented fixturesladders shape) for the **fixture's grade** (via `resolve_opponent`), flags our row with `club_match_keys`, and matches the opponent row by club-name tokens (stop-words stripped). Returns `our_row` + `opponent_row` (rank/P/W/L/pts). **Current** standings only — historical "vs top-4" splits would need ladder snapshots we don't keep.
- **Match preview** (brief §17.4) — new page `MatchPreview.jsx` at `/admin/betteriq/preview` (sidebar "Match preview"). Frontend composition (no new aggregator endpoint): picks an upcoming fixture from `list_opponents`'s `upcoming`, then fetches `opposition_report` (instant — no dossier build) + `opponent_ladder` + `team_overview` (par/record) in parallel and renders a lean (synthesised client-side), ladder, head-to-head, last meeting, their danger players, our edge, and links to the full scout + cheat sheet. Uses the instant report (fast), not the live dossier.

<!-- END original CLAUDE.md L13635-13640 -->
<!-- BEGIN original CLAUDE.md L13641-13718 -->
## BetterIQ — Manual scouting cards: batting & bowling intel (v8.26.0, Jun 2026)

The ball-level read CA does **not** record (no shot direction, no delivery
length/line, no bowler-type-faced) entered by the scout, the same posture as the
existing scout-entered scoring-zones wagon wheel. A **per-player** card (not a
per-dismissal log — deliberately lighter than the competitor app that prompted
it), for **both opposition players and our own**, blended on read with the
dismissal mix we *do* hold into a short "DNA" read.

- **Storage** (**migration 094** + idempotent `main.py` lifespan mirror): two JSONB
  blobs `batting_intel` / `bowling_intel`. For opponents they're new columns on
  the existing `opponent_player_tags` (keyed by CA participant GUID, merged onto
  the dossier on the frontend like the other tags). For our own players, a new
  `player_scouting_cards` table (`organisation_id`, `player_id`, the two blobs,
  `updated_by`; unique `(org, player)`). Blob shape — batting: `vuln_bowling[]`,
  `fav_bowling[]`, `zones[20]` (4 lengths × 5 lines, intensity 0–3), `fav_shots[]`,
  `risky_shots[]`, `strengths`, `weaknesses`, `plan`; bowling: `stock`,
  `variations[]`, `zones[20]`, `danger[]`, `strengths`, `weaknesses`, `plan`.
- **Validation** — `services/scouting_intel.py` (`clean_batting_intel` /
  `clean_bowling_intel` + the controlled vocab: `BOWLING_KINDS`, `BAT_SHOTS`,
  `BOWL_VARIATIONS`, `BOWL_DANGER`, `ZONE_LENGTHS`/`ZONE_LINES`). Shared by the
  opponent upsert (`iq.upsert_opponent_tag`) and the own-player upsert
  (`iq_trends.upsert_player_scouting`). An empty blob normalises to NULL.
- **Present-aware partial save** — `upsert_opponent_tag` now only overwrites a
  field when its **key is present** in the body (per-field `CASE WHEN :x_present`),
  so the four distinct editors (basic tags / scoring zones / batting card / bowling
  card) don't clobber each other. This also **fixed a latent bug**: saving the
  scoring-zones editor used to NULL the role/danger flags it doesn't send. The
  upsert re-selects and returns the full stored row (not an echo of the partial
  body). Same present-aware pattern in `player_scouting_cards`.
- **Routes** — own players: `GET`/`PUT /iq/trends/player/{id}/scouting`
  (`iq_trends.get_player_scouting` / `upsert_player_scouting`, org-scoped via the
  same `players WHERE id AND organisation_id` gate as `player_deep_dive`).
  Opponents reuse `PUT /iq/opposition/player-tags/{id}` (the body just carries
  `batting_intel`/`bowling_intel` too). api.js: `iqPlayerScouting` /
  `iqSavePlayerScouting`.
- **Frontend** — shared `ScoutingCard.jsx` (Batting + Bowling cards, each a
  display + inline editor) + `scoutDna.js` (vocab labels mirroring the backend +
  `buildBattingDna`/`buildBowlingDna`, which blend manual intel with the held
  dismissal breakdown into bullet insights and a headline "plan"). New
  `viz.ZoneGrid` (editable length×line heatmap, click cycles 0→3). Wired into
  `OppPlayerProfile.jsx` (opponent tag save) and the shared `PlayerDeepDive.jsx`
  `DeepDiveTab` (optional `scouting`/`onSaveScouting` props) used by both
  `PlayerTrends.jsx` and `PlayerHub.jsx`.
- **Bowler-fairness fixes** (the original ask — the opponent profile was
  batting-first): the radar is now a Bat/Bowl toggle (`OppRadarCard`, defaults to
  the player's stronger side; a bowler no longer gets forced into a batting radar);
  the Bowling stat card adds strike rate + a recent-wickets sparkline; the
  scoring-zones wagon wheel (a *batting* feature) is hidden for a pure bowler; and
  the opponent **deep scan** (`iq_scout._scan_player_deep`, `DEEP_VERSION`→2) now
  derives **"how he takes wickets"** + wicket quality (set/started/new from the
  dismissed batter's runs) by parsing the opposition cards in the innings he
  bowled — reusing sync's `_parse_bowler_and_fielder` / `_BOWLER_CREDIT_DT`.
- **Batting intel split into favoured vs risky (Jul 2026)**: the original single
  "Favoured / risky shots" chip group and single "Vulnerable to (bowler type)"
  group didn't distinguish a batter's comfort zone from his danger zone. Batting
  intel now carries four vocab lists instead of two: `vuln_bowling[]`/
  `fav_bowling[]` (both `BOWLING_KINDS`) and `risky_shots[]`/`fav_shots[]` (both
  `BAT_SHOTS`) — `ScoutingCard.jsx`'s batting editor shows them as two side-by-side
  pairs. `scoutDna.buildBattingDna` emits a bullet per populated list ("Vulnerable
  to…" / "Comfortable against…" / "Goes after the…, set the trap" / "Favours
  the…"). A pre-split blob's old combined `shots[]` key is a **read-side
  fallback only** (never written again): `buildBattingDna` and the editor's
  `seed()` both treat it as `risky_shots` when the new split fields are still
  empty, so already-saved intel isn't silently dropped when the deploy lands or
  the editor is reopened; bowling intel (`stock`/`variations`/`danger`) is
  unchanged.

**Two data layers** (`backend/app/services/`):
- `iq.py` — *instant* report from data we already hold: head-to-head vs an opponent (W/L/D, home/away split, recent meetings) + our players' record vs them (selection intel). Opponent identity = `COALESCE(opp_org_id, opp_club_name)` (`opp_key`), org-scoped via grades→seasons over the `v_effective_*` views — same pattern as `aggregations.get_player_by_opposition`.
- `iq_opponent.py` — *live* opponent dossier. Opponents aren't synced, but they play in grades we already track and the Grassroots `/scores/*` scorecards carry BOTH teams (sync discards the opponent half: `if pid not in our_team_pids: continue`). So we fetch the fixture's grade matches, keep the opponent (the `teams[]` entry whose `owningOrganisation.id` ≠ ours, or matched by club name), and aggregate their current-season batting/bowling/fielding per `participantId` — the mirror of sync's `our_team_pids` gate. Plus deep head-to-head: re-fetch our stored games vs them (capped) and parse the opponent cards → each opponent player annotated with their record vs us. A never-played-but-fixtured opponent is still scoutable (key the dossier on the name + fixture grade).

**Dossier cache** (`opposition_dossiers`, migration 059): built on demand in a detached `asyncio` task (its own `async_session_maker` session; tasks held in `_BUILD_TASKS` to dodge GC). `status` building→ready/error drives a frontend poll — `GET /iq/opposition/dossier` returns `{status:'building'}` until ready, then the payload. TTL 7 days + a Refresh button (`force=True`, `POST .../dossier/refresh`). Opponent player stats are NOT normalised into tables — this JSON cache is the only place live opponent data lands (keeps the data-rights surface small, no opponent-stats schema).

**Ceiling**: we hold scorecards, not ball-by-ball — so form / averages / SR / conversion / dismissal-patterns / vs-us / venue, but NO phase or ball-level matchup data. The UI says so (`coverage.notes`).

**Bounds** (CA-proxy politeness + latency): `MAX_OPP_SEASON_MATCHES=18`, `MAX_HEAD_TO_HEAD_GAMES=25`; reuses `grassroots_scores_client`'s in-process scorecard cache + semaphore(6). First build ~10–40s, then cached. Overs maths: `_overs_to_balls(10.2)=62` (10 overs + 2 balls).

<!-- END original CLAUDE.md L13641-13718 -->

## BetterIQ: opposition scout scoped to the fixture's grade and the Grade Type / Match Type filters (v9.109.8, Oct 2026)

Reported by a club selector: pressing Scout on a Swanbourne 3rd XI fixture, with Grade Type Men's and Match Type Two day, returned a plan headed "WHOLE CLUB, 3 SIDES" whose danger batter was a 1st XI T20 Div 1 innings (79 at a strike rate of 219).

Causes, both in `iq_opponent`:
- `apply_grade_scope` resolved the Grade Type / Match Type scope for every `/iq` route, but the dossier's own queries (`_db_season_accumulators`, `_our_games_vs`, `_target_season_grades`) never read it, and the dossier cache key did not carry it.
- The fixture's grade (`grade_hint`) only chose the season. With "All grades" in the filter bar nothing narrowed to the side the fixture was against, so the dossier was the whole club.

Fix:
- `_opponent_scope` rebuilds the request scope against the opponent's own grades with `grade_scope.resolve_scope(opp_org, req.categories, formats=req.formats, judge_primary=True)`; `formats_only()` when a grade or team is picked. Format is per fixture off `match_format`, so a T20 friendly inside the 3rds is out of a Two day scout.
- `get_or_start_dossier` turns the fixture's grade into the grade filter when no grade or team was sent (`_fixture_grade_label`, payload `grade_from_fixture`). A fixture grade is never relaxed to the whole club: `_discover_opponent_teams(relax_grade=False)` and no whole-club retry in the synced branch. If the opponent holds games this season but none in scope, the payload carries `scoped_empty` and a note, and the build does not fall through to the live whole-club scout.
- `_scope_sig` joins the cache key (`::sc::`), `DOSSIER_VERSION` 10 to 11, prewarm builds under the club's default scope and polls the real key. The payload gains `scope_labels`, `scoped_empty`, `grade_from_fixture`; `GamePlan` shows the labels and an empty-scope message.
- Known gap: for a non-synced opponent (live Grassroots path) only our side's grade list is scoped, since a Grassroots match carries no per-game format we can filter on.
- Verified with `backend/verification/verify_iq_dossier_scope.py` on a real Postgres through the shipped `apply_grade_scope` and `opposition_dossier` bodies: 28 pass on the fix; the previous commit fails 19 of them, on exactly the whole-club squad.

## BetterIQ: Ask IQ asks a clarifying question as buttons (v9.109.9, Oct 2026)

Request: give Ask IQ the Claude habit of putting a short qualifying question, with buttons, before answering when the answer depends on the choice. Chosen scope: the Ask IQ chat only, and only when it matters. The Opposition scout is not changed.

- `iq_ask.TOOLS` gains `ask_user` (question plus 2 to 5 options, each `label` and optional `value`). The system prompt limits it to choices that change the figures (which grade or side, all-time or this season, one-day or two-day or T20, which of two clubs), with options taken from the other tools, and never when the question is already clear.
- `answer()` returns `{answer: <question>, clarify: {...}}` the moment the model calls it; anything else called in that step is not run. `_clarify_from` strips em dashes, de-duplicates, caps at five and rejects fewer than two options; an unusable call goes back to the model as an error result so it answers on its best reading.
- One ask per thread: the client marks the clarifying turn `clarified` in the history it sends, and the next call is not offered `ask_user`.
- `AskIQ.jsx`: `ClarifyChoices` buttons under the question. The bubble shows the label while the server gets the button's `value` (`sent`). Only the newest set is live; typing a reply answers it too. Each pick is one more question against the 20 an hour limit.
- Verified: `verify_iq_ask_clarify.py` (17 pass; the previous commit fails the 10 clarify checks) and `frontend/scripts/verify-ask-iq-clarify.mjs` in Chromium at 390px with the API stubbed (12 pass; the previous page renders no buttons).
- Not verified: how often the live model chooses to ask. That needs real traffic; the prompt is the only lever, so tune its wording first if it asks too much or too little.
