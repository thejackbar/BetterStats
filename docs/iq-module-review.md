# BetterIQ module review (Aug 2026)

A full audit of BetterIQ, prompted by live club feedback (Matt, Toowoomba-area club):
"often get some strange stats come back", the grade filter not narrowing the
opposition scout ("it's not filtering only Woolnough Shield as Camblar Keys plays
in the Mackie 3rd or 4th XI"), a par card claiming "the lowest total we've
defended is 21", and an open question of spend vs return for a 20-25-player club.

Every claim below was verified against the code with file and line references.
Nothing in this document is a guess. Both reported symptoms are fully
root-caused, and both turn out to be instances of wider structural problems
rather than one-off bugs.

## Implementation status

P0 and P1 from the roadmap (section 10) are implemented and verified against
a real Postgres instance (24 checks: the opponent-first-synced shared game,
an incomplete-scorecard "win", junior/senior mixing, a third club's rows
leaking into a shared fixture, and the dossier grade filter narrowing a
synced opponent's pool without dropping a player who plays across grades).
Both reported bugs are fixed and covered by the harness. Commits:
`9771283` (backend) and `a5ecd7e` (frontend + a cross-club season-matching
fix the verification pass surfaced — `iq_filters.season_member_clause_cross_club`,
needed because a shared game the opponent synced first carries their own
per-club season row).

Most of P2 landed alongside P1 (migration-228 scope integration in
`player_trend`, selection clash-awareness, Ask IQ season args + name
disambiguation + prompt caching, the statistical-hygiene fixes).

P3 status, after a scoping discussion on the three items:

- **Persisting true innings totals at sync** — done (`677fe0e`, migration 230).
  `games.innings_totals` (JSONB, prospective-only, no forced backfill) stores
  the real per-innings total straight from Grassroots
  (`runsScored`/`numberOfWicketsFallen`/`totalExtras`); `_per_game` prefers it
  over the bat-only `SUM(batting_innings.runs)` approximation whenever every
  innings we batted in has a stored figure, all-or-nothing. Verified against
  a real Postgres instance (4 more checks on top of the earlier 24: exact
  total preferred, NULL fallback, a stored-but-null entry never flipping
  exact, the par payload's new `exact_total_games` count).
- **Nav consolidation** — written up as a design proposal, not implemented
  (`docs/iq-nav-consolidation-proposal.md`, `7f18220`). The closer read for
  the proposal found less real duplication than the original audit assumed —
  Match preview/Opposition club turned out to be a deliberate, already
  cross-linked summary→detail pair, and the two opposition-player search
  entry points already share their render component. The one genuine overlap
  (Player search vs Form & trends) is proposed as a fold-in, pending review of
  the doc's open questions — not implemented.
- **Mobile pass** — done (`7f18220`) on the three matchday pages (Cheat sheet,
  Match preview, Selection analysis). Fixed two confirmed overflow sources
  (Cheat sheet's three-column row had no wrap with `nowrap` text inside,
  guaranteed to overflow a 390px screen) plus several borderline
  action-button/filter rows. Not live-browser-verified at 390px — this
  environment has no fully seeded, authenticated club to screenshot against,
  so the fixes are grounded in reading the actual flex/width math rather than
  a visual check.

---

## 1. Reported bug 1: the grade filter does not reach the opposition scout

The filter bar promises "Filters apply across BetterIQ" (`Context.jsx:489-492`)
and shows "THEIR GRADE: Woolnough Shield", yet the synthesised game plan is
built around a 3rd/4th XI player. The chain has five independent breaks, any
one of which produces this symptom:

1. **The dossier endpoint has no grade or season parameter at all.**
   `GET /iq/opposition/dossier` accepts only `opponent`, `fixture_id`, `team`,
   `name` (`routers/iq.py:70-105`). The instant report endpoint takes `grade`
   and `season_ids`; the dossier, which produces the danger players and the
   whole "How to beat them" card, never sees either.

2. **`_target_season_grades` uses the fixture's grade only to pick a SEASON,
   then returns every grade in it** (`iq_opponent.py:777-836`). The universe of
   "their teams" is every grade our club fields a side in that season, so their
   3rd/4th XI is in scope whenever we also field a side in that competition.
   `iq_opponent.py` never imports `iq_filters` at all.

3. **Whole-club mode pools all their sides into one untagged pool.** Up to 8
   grades, 8 matches each, 44 matches total (`iq_opponent.py:61-70, 1221-1254`).
   `_accumulate` keys purely on `participantId` and stamps no grade on any row,
   so nothing downstream can tell a 1st XI run from a 4th XI run. The danger
   index (`avg*0.5 + runs*0.05`, `iq_opponent.py:595-602`) has no innings
   floor, so a lower-grade player with a fat small-sample average tops the
   "remove early" tile. That is the exact path by which Camblar Kays became
   "Get Camblar Kays early".

4. **The one narrowing lever (`team`) silently fails.** The frontend maps the
   filter's grade name onto the dossier's `teams[]` list by exact
   case-insensitive string equality (`OppositionScout.jsx:774-781`), without
   `gradeBase()` sponsor-stripping and without merge-alias resolution, so
   "Woolnough Shield" never matches "Woolnough Shield (Sponsor)". Worse,
   `teamsList` is only populated FROM a completed dossier response and is
   cleared on every opponent pick (`:869`), so the FIRST dossier request is
   always whole-club. A miss returns `null`, which the API layer drops
   entirely (`api.js:2915`), indistinguishable from "whole club, deliberately".

5. **The cache can serve a dossier built under a different scope.** The cache
   key is `opp_key` plus optional `team_grade_id` (`iq_opponent.py:629-632`);
   the `grade_hint`, and therefore the resolved season, is not in the key.
   TTL is 7 days. Pre-warm (`iq_prewarm.py:152-153`) and Ask IQ
   (`iq_ask.py:519-521`) always build/read the whole-club key. And for a
   SYNCED opponent, `team` is ignored outright: `_db_season_accumulators`
   takes only the org id and pulls all their grades in their latest year
   (`iq_opponent.py:394-592, 1201-1224`), so picking a team changes the cache
   key but returns a byte-identical whole-club payload.

Two aggravations worth calling out:

- **"averages 68.00 against us" can be built from one or two innings.** The
  `vs_us` block has no minimum-innings gate anywhere: `_enrich_batter:1045`,
  `:1066` and `_game_plan`'s `key_warning` (`:1163-1167`) all fire on the bare
  average. `vs_us.innings` is in the payload and the strings never use it. The
  vs-us record is also all-time and all-grade by design (`_our_games_vs`,
  `iq_opponent.py:700-716`, capped at 25 games, no season or grade predicate).
- **One card, two scopes.** The GamePlan card mixes the unfiltered dossier
  tiles with the correctly-filtered report lines ("Record vs them", "Our
  edge") with no visual distinction (`OppositionScout.jsx:254-288`).

Also mislabelled: "THEIR GRADE" is populated from OUR grade list
(`Context.jsx:181, 448-461` via `iqTeamGrades()`), and it means "our grade"
for the report but "their side" for the dossier. Two different things behind
one control.

### Fix plan (opposition)

- Add `grade` + `season_ids` params to `/iq/opposition/dossier` and
  `/refresh`; thread them into `get_or_start_dossier`; include them (and the
  resolved season) in `_cache_key`.
- Apply `grade_match_clause(grade_canonical_label(...))` inside
  `_target_season_grades` and in all four `_db_season_accumulators` queries
  (they already join grades/seasons, so `season_grade_clause` drops in).
- Return the canonical grade label from `_target_season_grades` (or better:
  send the grade NAME to the backend and resolve it there), killing the
  frontend string-match and the bootstrap race in one move.
- Stamp each accumulated innings/spell with its grade in `_accumulate` and
  emit a `by_grade` breakdown, enabling per-grade gating, UI badges, and
  post-hoc filtering without a rebuild.
- Gate every synthesised vs-us claim on `vs["innings"] >= 3` and print the
  sample in the string ("averages 68.00 against us (3 inns)"). Shrink the
  danger index toward a prior (`(runs + K*prior)/(outs + K)`, K≈3) so a
  two-innings cameo cannot top the plan.
- Surface `confidence` and `alert.caution` in the GamePlan card (already in
  the payload, currently discarded), and badge the card with the scope it was
  actually built from.

---

## 2. Reported bug 2: "the lowest total we've defended is 21"

The 21 is not one bug; it is five compounding ones with no sanity net.

**The immediate cause is a one-line frontend bug.** `MatchPreview.jsx:180`
calls `api.iqTeamOverview()` with NO arguments, so the par card is computed
over every game the club has ever synced: all 48 seasons, every grade
(juniors, women's, masters), every format, home and away. The copy "Median
winning first-innings score across our grounds" and "Par at this level" are
both false: the par block never consults `our_venue` and no grade is passed.
Meanwhile Team analysis calls the same endpoint WITH filters
(`TeamAnalysis.jsx:692`), so the same named metric shows different numbers on
two pages.

**The computation itself has zero guards.** `iq_team.py:1461-1468`:
`lowest_defended` is a raw `min()` over games passing three predicates
(`batted_first`, `result == 'WIN'`, `our_runs is not None`). No min-overs,
min-wickets, min-batting-rows, format, or completeness check. Floors exist
everywhere else in the file (venues ≥3, partnerships ≥3, captaincy ≥3); par
and score bands are the only cards with none. `samples` is computed and never
rendered anywhere.

**Live poisoning vectors feeding it:**

| Vector | Mechanism |
|---|---|
| Missing extras | `our_runs = SUM(bi.runs)` only (`iq_team.py:176`), understating every total by 10-25 runs |
| Partial scorecards | sync skips batters with `dismissalTypeId == 0` (`sync.py:2072-2074`); incomplete cards are not cached but ARE persisted (`grassroots_scores_client.py:215, 292-299`) |
| Forfeits/abandonments as wins | `classify_match_result` matches any `WON*` prefix incl. `WON_BY_FORFEIT` (`sync.py:44-73`); the scorecard sync path never checks CA's statusId |
| Shared-fixture result inversion | `games.result` is written once, from the first-syncing club's perspective (`sync.py:1988-1991`); `iq_team` reads it raw while `aggregations.py:3519-3540` re-derives an `effective_result`. A genuinely lost low-scoring game can read as a bat-first win |
| Manual chases read as bat-first | `ManualBattingIn.innings_number` defaults to 1 (`manual_entries.py:115`) and the UI defaults it too, so a hand-keyed chase win (truncated by definition: chasing 20, you make 21 and stop) is a textbook "defended 21" |
| Two-day innings summed | our innings 1 and 3 sum into one "first-innings total" (`iq_team.py:183`), inflating par upward |
| Junior/short formats mixed | default filter is All grades; `grades.category` is fetched but `_scope` never uses it; `_BANDS` are hardcoded T20-shaped (`iq_team.py:69`) |

### Fix plan (par / team stats)

- One-line fix first: pass the fixture's grade + current season from
  MatchPreview, or rewrite the copy to what the data actually is.
- Add a completeness gate before a game enters par/bands/chase stats
  (≥7 non-DNB batting rows OR ≥8 wickets lost OR ≥15 overs faced), and emit
  an `excluded_incomplete` count.
- Stop reporting a raw min as an analytic. Replace "lowest defended" with the
  lowest of N qualifying defences (or 5th percentile), labelled with N, and
  link the game so a club can verify it in one click. Report par as an
  interquartile range ("147, typical winning range 128-171").
- Re-derive `effective_result` the way `aggregations.py:3530-3540` does, and
  adopt its LEFT JOIN + four-way ownership clause so shared and grade-less
  games stop disappearing (see section 3).
- Split formats: `grades.fee_format` + `derive_fee_format` (`fees.py:89-107`)
  already classify two-day/one-day/T20 for BetterFees; wire them into `_scope`
  and derive band edges from the scope's own distribution.
- Longer term: persist the true innings total at sync (`innings[].runsScored`
  is in the payload and currently discarded), which eliminates the extras and
  partial-card vectors at the source and gives a cross-check.

---

## 3. Systemic: the cross-club scoping pass (v9.11.1) is incomplete

The v9.11.1 audit fixed 9 functions but its heuristic required a
`JOIN players` to flag a site. Five sites in `iq_team.py` have no such join
and were invisible to it:

| Site | Impact |
|---|---|
| `_per_game` bat/bowl CTEs (`iq_team.py:174-193`) | **The query the entire Team page is built from.** On a shared both-synced fixture, `our_runs` sums BOTH sides' batting, `opp_runs` both sides' bowling, `wkts_lost` up to 20, and `batted_first = BOOL_OR(innings_number=1)` is always true, misclassifying every chase. Drives record, par, score bands, bat-first/chase, venues |
| `_partnerships` (`:220`) | `is_club_innings IS TRUE` is not a club filter (both clubs stamp TRUE on a shared row) |
| `_collapses` (`:499`) | same, opposition collapses counted as ours |
| `_team_starts` (`:1050`) | same, opposition opening stands in our profile |
| `_wickets_quality` (`:886-894`) | unscoped `bowler_wickets`; sibling `_collapse_bowlers` (`:971`) scopes correctly |

Additional confirmed gaps elsewhere:

- `iq_review.py:183-192` collapse query: no org scoping AND `by_inn` keys on
  `innings_number` only, so our wicket 3 and theirs overwrite each other
  (last row wins, non-deterministic).
- `iq_opponent.py:564-578` partnerships query in `_db_season_accumulators`:
  no player-org predicate (the batting query 100 lines up documents exactly
  this hazard).
- `iq.py:763-812, 815-860` (`_their_danger_batters`, `search_opponent_players`):
  `bowler_wickets` read with no bowler-org predicate.
- `iq_selection.py:296-301` name fallback: unscoped `players` read.

**The opposite failure mode is just as damaging: games we own but cannot
see.** Every per-game IQ read scopes via `INNER JOIN grades → seasons →
organisation_id`. Migrations 167/169 document this as broken for (a) shared
fixtures first synced by the opponent (grade_id points at THEIR per-club
grade row) and (b) manual games with no grade at all. The canonical corrected
predicate exists in `aggregations._club_results` (`aggregations.py:3458-3495`:
`g.organisation_id / home_org_id / away_org_id / s.organisation_id /
appearance-EXISTS`, grades LEFT-joined). A grep for `home_org_id` across
`iq*.py` returns zero matches. Consequence: a manual scorecard uploaded with
Grade "— none —" is invisible to every per-game IQ surface while still
counting in the same player's career header. Numbers disagree with the Games
list and Leaderboard with no explanation. This is a large slice of "strange
stats".

**Career reads are not org-scoped at all.** `player_trend` calls
`get_season_by_season` / `get_career_*` with no scope (`iq_trends.py:354-360`),
so a shared-GUID player's trend page includes the other club's seasons, while
the deep-dive innings beneath it do not. Same for `_player_recent` (the
sparkline), `_similar_players`' pool, and the three all-time aggregation
helpers embedded in the deep dive (`get_player_by_venue`,
`get_bowling_dismissal_breakdown`, `get_bowling_by_batter_position`), which
produce a second, different wicket total on the same page as the org-scoped
`bowler_deep_dive`.

**Action:** re-run the v9.11.1 audit with the heuristic widened (drop the
"has a JOIN players" requirement; flag any per-game-table read with no
organisation_id anywhere in the block), fix the sites above, and adopt the
`_club_results` ownership predicate as the standard "our games" clause for
IQ.

---

## 4. Systemic: the filter contract is broken in both directions

"Filters apply across BetterIQ" is the bar's promise. The reality:

- **Range collapses to one season.** `effectiveSeasonId` returns only
  `season.to.id` (`Context.jsx:152-155`). Only Team analysis passes real
  `season_ids`. Trends and Review advertise "Comparing N seasons" in the
  header tag while requesting one.
- **Per-player cards take no filters at all.** `iqTrendsPlayer`,
  `iqPlayerDeepDive`, `iqBowlerDeepDive` accept no season/grade
  (`routers/iq.py:356-394`); the radar takes season but not grade. Result: on
  Form & trends, one screen shows four different scopes under a single
  "2024/25 · A Grade" header (movers = filtered; radar = season only; deep
  dive = career all grades; career header = career all grades all CLUBS).
- **One page rewrites the global filter for everyone.**
  `OppositionScout.jsx:765-770` flips the persisted session-wide season to
  all-time on first landing. This is very likely how the reporting club ended
  up staring at "48 seasons · all-time" they never chose.
- **Picking a grade silently changes the data source and can EMPTY boards.**
  `_movers_src` (`iq_trends.py:68-75`) and `player_impact`
  (`iq_team.py:1179`) swap to `player_season_grade_stats`, which is only
  populated when CA syncs it. Manual scorecards and BetterImport history have
  no psg rows; older seasons may predate psg population, and the prior-career
  JOIN then drops players entirely. Picking a grade therefore reads as "the
  filter doesn't work". `aggregations.py` has a per-game fallback for exactly
  this; iq_trends does not.
- **"Seniors only" is an include-list**, the exact shape
  `grade_scope.py:13-25` documents as wrong twice over: it drops grade-less
  manual games and import residuals. And BetterIQ was deliberately left out
  of the migration-228 junior/senior stats split, so with the platform
  default (juniors excluded from Leaderboards/profiles), a dozen IQ surfaces
  still carry junior runs unconditionally: career trend + milestones, deep
  dives, similar players, radar baselines, teammates, selection form,
  selection_value, the Ask roster. A player can be "12 runs from 1000" in IQ
  on a number the Leaderboard doesn't recognise.
- **Smaller instances:** `list_lineups` caps at 40 rows BEFORE the
  client-side grade filter (`iq_selection.py:131`), so a lower-grade picker
  can be empty mid-season; `milestones` inside trends-overview ignores both
  filters; Ask IQ has no season on any of its 11 tools.

**The honest fix has two halves.** Backend: thread season/grade into the
per-player endpoints and add a psg-empty fallback. Frontend: make the bar say
what each route actually honours, per-card scope badges wherever a card's
scope differs from the header, fix `effectiveSeasonId`, and stop
OppositionScout mutating the global filter.

---

## 5. Statistical soundness

Recurring theme: gates exist in some places and are absent from precisely the
surfaces making the boldest claims.

- **No minimum sample:** vs-us averages (section 1), par/lowest-defended
  (section 2), reliability percentiles (computed from 1 innings; a
  single-innings player is labelled "Steady", `iq_trends.py:645-685`), radar
  target (peers are gated at 3 innings, the SUBJECT is not,
  `iq_radar.py:109-114`; and `outs = max(inns - no, 1)` invents a dismissal so
  one 50* renders a 50.0 axis), emerging (`iq_trends.py:181-215`, no gate,
  and a per-grade season count that makes a ten-year veteran "emerging" in his
  second 3rd-Grade season), batting pairs at 2 stands when filtered
  (`iq_team.py:395`), all-rounders at 4 innings/4 wickets when filtered
  (`iq_team.py:301`), captaincy sorted by win% so 1-for-1 beats 35-of-50
  (`iq_team.py:604`).
- **selection_value is confounded:** "win% with vs without" compares against
  every decided game the whole club ever played, all grades all eras
  (`iq_trends.py:737-767`). A defensible version is within-grade
  within-season with ~6 games per arm, or drop it.
- **Similar players weights averages by innings, not outs**
  (`iq_trends.py:468-469`), systematically inflating not-out-heavy profiles;
  `shared < 2` lets a specialist bat and a specialist bowler be "similar" on
  two features; presented as a hard percentage.
- **Movers:** ratio thresholds (`latest >= baseline*1.35`) at 5 innings have
  a huge false-positive rate and results sort by raw delta, floating the
  small-sample swings to the top. Prior baseline is unbounded in time, so
  decline detection always fires on ageing players.
- **Internal inconsistencies:** two different definitions of "out" inside
  `player_deep_dive` (failure rate vs averages won't reconcile,
  `iq_trends.py:670` vs `:709/:725/:810`); three different wicket-equivalence
  constants in one module (18, 20, 25); `'TIE'` counted in nine places but
  never emitted by `classify_match_result`.
- **Milestone ETA** uses career rate, not recent rate (recent form is loaded
  three lines later and unused), on a cross-club junior-inclusive total, and
  outputs bare games with no date translation.

**Principle to adopt module-wide:** every synthesised or ranked claim carries
its sample size in the payload AND the rendered string, and is suppressed (or
explicitly hedged) below a floor. The `_confidence()` helper already exists;
it is applied to almost nothing and rendered almost nowhere.

---

## 6. Selection analysis

Eligibility genuinely mirrors BetterSelect's pool (`assemble_selection` is
shared). But the recommendations built on top diverge:

- **Promote and best-XI ignore clash blocks.** `selection_pool` computes
  same-day clash blocking; `iq_selection.promote` (`:411-426`) and
  `_best_available_xi` (`:59-91`) filter only on eligibility + availability.
  IQ will recommend promoting a player already named in the 1st XI that same
  day. BetterSelect's own board would block the pick, and the coverage note
  claims the two match "exactly".
- **12-month recency wall vs 24-month dormancy wall:** a player last seen 18
  months ago gets no flag from IQ yet is ineligible in BetterSelect.
  `recent_ok` is on the pool row and never read.
- **Two form definitions on one row:** the pool's form score reads raw tables
  (last 4, player-org-scoped), the rendered `recent_scores` strip reads the
  effective views (last 5, game-org-scoped). They can visibly contradict.
- **Best-XI ranking is availability-dominated:** `NO_RESPONSE` ranks below
  "available", so the "best XI" is really the most responsive XI; the ≥5
  bowlers repair counts anyone with a bowling_type ever set.
- `_season_load` reads one season row, all grades (not year-expanded, not the
  fixture's grade), so fairness numbers won't match the Team page.

What a selector actually wants (all reachable from held data): the same-round
conflict view ("picked at 4 in the 1sts") instead of a silent bad suggestion;
availability freshness ("9 of 14 answered, 3 answers older than 2 weeks");
a fairness ledger (games vs squad median, played-up/played-down counts);
batting-order sanity (two openers at 6 and 7, no keeper in the top 7);
attack SHAPE, not attack count (reuse `_attack_structure`: "your only stock
bowler is unavailable").

---

## 7. Ask IQ

- No tool accepts a season: team_overview answers all-time, form_movers
  latest-season, in the same reply, with no way for the model to say so.
- `player_detail` merges the cross-club career trend with the org-scoped deep
  dive into one payload; the model narrates two scopes as one story.
- Ambiguous names resolve first-match-wins (`iq_ask.py:216-218`); should
  return candidates and force disambiguation.
- The roster includes non-players (no `is_player` filter in `iq_players`).
- Bowler performers are trimmed WITHOUT sample sizes (batters keep theirs),
  and the system prompt never instructs the model to qualify small samples.
- A `max_tokens` stop is treated as a complete answer (mid-sentence replies);
  a refusal returns the generic apology.
- No prompt caching: ~900-word system prompt + 11 tool schemas re-sent every
  step of an up-to-8-step loop. One `cache_control` breakpoint on the last
  system block caches both (check the pinned SDK version first,
  `requirements.txt` pins anthropic==0.40.0).

---

## 8. Trust and presentation

- **The disclaimer hierarchy is inverted.** Synthesised claims render at 24px
  bold; every caveat in the module renders via `Note` at 11px in the faintest
  grey (`ui.jsx:260-266`). Sample sizes, where they exist at all, hide in
  `title=` tooltips (unreachable on touch, invisible in print).
- **The dossier's build date is conditionally hidden**: `built_at` is nested
  inside the coverage-notes guard (`OppositionScout.jsx:1080-1082`, same bug
  in `OppositionPlayer.jsx:402`). A week-old dossier renders with "this
  season" eyebrows and no date, directly under an "all-time" header.
- **KeyPlayersCard renders backend prose (`key_note`, `plan`, a red "risk"
  badge) with no provenance marker**; its tiny confidence chip is the only
  confidence indicator in the entire module.
- **The cheat sheet hardcodes "Applecross" as the club name**
  (`CheatSheet.jsx:148`). Every other club prints someone else's name on the
  sheet the captain takes to the toss. It also builds "save him for this
  match-up" advice by surname string-matching across two data sources
  (`:108-114`), never refetches (`[]` deps), isn't in the nav, and has four
  lines of print CSS with no page-break control.
- Unbounded dossier polling with a fake timer-driven progress bar on the
  flagship page (CheatSheet caps its polls; OppositionScout doesn't).

---

## 9. Product shape for a small club (the spend-vs-return question)

The reporting club has 20-25 senior players and is weighing cost against
value. Two observations follow:

**The value is concentrated in the cheap, high-frequency surfaces, and both
reported bugs live exactly there.** A club this size gets its value from: the
cheat sheet (one page, in the captain's pocket, zero learning curve), the
head-to-head/our-record-vs-them block (data only we hold; already correct),
and the team-talk copy button (a formatted paste into the group chat, which
is the real workflow, currently a ghost button). Against that, much of the
module assumes an analyst persona: z-scored MVP boards, radar charts
normalised over tiny peer groups, with/without splits. With ~14 games a
season those samples cannot support the charts, and the module renders them
without saying so.

**Trust compounds.** A club weighing renewal does not audit filter plumbing;
they see "defended 21", conclude the numbers are unreliable, and stop opening
the module. Correctness of the high-frequency surfaces matters more than
breadth. No new feature should land ahead of the P0/P1 list below.

**Navigation:** eleven nav routes plus an unlisted twelfth, with real
duplication (four ways to view one of our players; two ways to view an
opposition player; two match-preview surfaces; PlayerHub and PlayerTrends are
near-identical code with different filter behaviour). Consolidating to
roughly five destinations (Overview / Opposition / Our players / Our team /
Match day) would remove more confusion than any new feature adds, and makes
the filter contract explainable in one sentence.

**Mobile:** the filter bar wraps to 2-3 rows under a 64px header on a phone;
the "Filters apply across BetterIQ" explanation is `hidden md:flex`; the
squad table's real vs-us numbers are in hover tooltips touch can't reach.
Match-day usage is phone usage.

---

## 10. Prioritized roadmap

### P0 — days, stops the bleeding (all are small, high-visibility fixes)

1. `MatchPreview.jsx:180`: pass grade + season to `iqTeamOverview` (the "21"
   card). One line.
2. `CheatSheet.jsx:148`: replace hardcoded "Applecross" with the club name.
3. Render `built_at` unconditionally on dossier surfaces.
4. Fix `effectiveSeasonId` range collapse (or downgrade trends/review to
   single-season) so "Comparing N seasons" stops lying.
5. Sample-size gates + printed N on every vs-us claim and the danger index
   (section 1); surface `confidence` in GamePlan.
6. Render `par.samples`; swap "lowest defended" for lowest-of-N-qualifying
   with a link to the game.
7. Stop OppositionScout mutating the global season filter
   (`OppositionScout.jsx:765-770`).

### P1 — 1-2 weeks, the structural correctness pass

8. Dossier grade/season parameters end to end: router → `get_or_start_dossier`
   → `_cache_key` → `_target_season_grades` → `_db_season_accumulators`;
   canonical grade labels in `teams[]`; grade tags on accumulated rows.
9. Cross-club scoping completion: `_per_game` (above all), `_partnerships`,
   `_collapses`, `_team_starts`, `_wickets_quality`, the `iq_review` collapse
   query (+ its dict-key collision), the `iq_opponent` partnerships query,
   `_their_danger_batters` / `search_opponent_players`. Re-run the audit with
   the widened heuristic.
10. Adopt `aggregations._club_results`' ownership predicate + LEFT JOIN
    grades as the standard "our games" clause across IQ (fixes invisible
    manual/shared games).
11. Par/bands sanity: completeness gate, `effective_result` re-derivation,
    format split via `fee_format`, format-relative bands.
12. Org-scope the career reads on the trends page (`get_career_*`,
    `_player_recent`, `_similar_players`, embedded aggregation helpers).
13. psg-empty fallback for the grade filter in movers/MVP.

### P2 — the coherence pass

14. Migration-228 integration: pass `resolve_scope_for_player` scope into
    IQ's career reads; replace the "Seniors only" include-list with
    grade-scope exclusion semantics; surface `auto_shown`.
15. Filter contract UX: per-card scope badges, honest per-route bar labels,
    split "our grade (head-to-head)" from "their side (live squad)" on
    Opposition.
16. Selection: honour clash blocks in promote/best-XI; flag the 12-vs-24
    month gap via `recent_ok`; unify the two form computations; server-side
    grade filter on `list_lineups` before the cap.
17. Ask IQ: season args + resolved-scope echo on tools, sample sizes on
    bowler trims, disambiguation for names, `max_tokens`/refusal handling,
    prompt caching.
18. Statistical hygiene: one "out" definition, one wicket-equivalence
    constant, similar-players weighting by outs, gates on reliability/radar
    subject/emerging, captaincy sort by decided-games-weighted record.
19. Cheat sheet finish: nav entry, scope + build-date line, page-break CSS,
    id-based (not surname) matchup joins.

### P3 — the value pass

20. Persist true innings totals at sync (`runsScored` / statusId), making
    every team score exact and giving par a real completeness signal.
21. Nav consolidation to ~5 destinations; retire the duplicated player pages.
22. New scorecard-reachable analytics: margin-of-victory distribution, chase
    success by target band, FOW curve from stored `score_at_fall`/
    `overs_at_fall` (also the input to the completeness gate), club-level
    extras/discipline trend, availability freshness + fairness ledger in
    selection.
23. Mobile pass on the filter bar and squad tables.

---

## Appendix: full findings by file

The detailed audit (with every file:line) is preserved in the four analysis
reports this document summarises. Key entry points per file:

- `iq_opponent.py`: no filter params, all-grades pooling, cache keying,
  synced-path team bypass, unscoped partnerships, redaction filter missing.
- `iq_team.py`: `_per_game` unscoped, par unguarded, format blindness,
  `player_impact` ignores range + reads a different source, small-sample
  boards when filtered, `_safe` masks failures with no flag in the payload.
- `iq_trends.py`: unfiltered per-player endpoints, psg source-switch, movers
  gates, emerging, similar-players math, selection_value confound, two "out"
  definitions, unscoped career/sparkline/venue/dismissal reads.
- `iq_selection.py`: clash-blind promote/best-XI, dual form definitions,
  `_season_load`, 40-row cap, unscoped name fallback.
- `iq_review.py`: unscoped collapse query + innings-number dict collision.
- `iq_ask.py`: no season tools, mixed-scope player payload, name
  disambiguation, stop_reason handling, no prompt caching.
- `iq_radar.py`: ungated subject, invented dismissal, mean-normalisation.
- `Context.jsx` / `OppositionScout.jsx` / `MatchPreview.jsx` /
  `CheatSheet.jsx` / `KeyPlayersCard.jsx` / `ui.jsx`: the filter-contract and
  trust-presentation issues in sections 4 and 8.
