# Archive: stats-figures-records-and-filters

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: Career and season figures, rates, milestones, grade type / match type / competition scopes, StatLab, records, awards.
Read the distilled rules first: `docs/dev-notes/guides/stats-figures-records-and-filters.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L454-537 -->
## A milestone is measured on the profile's figure, and a junior split is SHOWN (v9.93.0, Sep 2026)

Reported off Shoalwater Bay's Milestones page: S Hetel 87 short of 6,000 with
5,924 on his profile, A Godfrey 3 short of 200 wickets on 478, P Ritchie 2
short of 200 catches on 201, and J Hind 18 from 3,000 "including junior games".

- **THE SCAN SUMMED THE BASE `player_season_stats`, THE PROFILE READS THE VIEW.**
  So every imported or hand-entered match was missing from the milestone and
  present on the profile. `services/milestone_totals.profile_totals` is now the
  ONE definition: the figures the profile opens on (club default grade
  categories, auto-widened for a junior-only player), batched per scope group
  with the ids bound as an array. The Milestones page, the dashboard, the admin
  report, the player's own card and the notification all read it. The suite
  asserts EQUALITY with `get_career_*` player by player under two club
  defaults, not a mirrored query.
- **NO SENIOR/JUNIOR SWITCH, BECAUSE THE EMAIL CANNOT PRESS ONE.** Asked for as
  a toggle, then settled as "predict it and show both". A player with junior
  AND open-age records carries `junior_split` (with / without their junior
  matches) on every entry, `counts` names which the headline is, and a
  milestone only the other figure is close to arrives as its own `variant`
  entry. The notification's dedupe key carries the variant's basis and its body
  gives both figures. **This reverses v9.64.0's "milestones are never
  filtered"**: they now follow the profile's default, which is what the club
  compares them against. A toggle can still be added later as a filter over
  these fields without changing what an email says.
- **"WITHOUT JUNIOR" IS JUDGED ON THE PRIMARY CATEGORY** (`resolve_scope(...,
  judge_primary=True)`). An explicit all-but-junior pick is an inclusion and
  keeps a Girls Under 16 grade on its women's half; that is junior cricket.
- **THE STORED MILESTONES RECONCILE.** `sync._compute_milestones(reconcile=True)`
  removes a threshold the current figure no longer reaches (the only writer of
  `milestones` is this function, so it is our output, never a club's typing) and
  a threshold still reached keeps its date. It runs at the END of the sync now,
  after the scorecards and the import reconcile, because a scoped career counts
  scorecards a Full Rebuild has just wiped; a run with `match_pull_failed` only
  adds. `python -m app.scripts.reconcile_milestones <org|all> [--apply]` repairs
  what September's double count minted. **Run it for Shoalwater after deploy.**
- **A STORED MILESTONE IS REACHED ON EITHER FIGURE, NOT THE PROFILE'S ALONE
  (v9.93.1).** The first cut reconciled against the profile's figure only, and
  its dry run on Shoalwater proposed removing **352** milestones against 67
  added. Two real cases were being deleted: a player who reached 50 matches
  WITH his junior games counted (the club default leaves them out), and a
  veteran whose scoped figure is counted from scorecards and sits below Cricket
  Australia's own career total (the control run reads Hetel's scoped runs as
  911 against a 5,913 career). The writer now takes `max(profile figure, whole
  career)`, the whole career being the unscoped effective view, correct since
  309. The phantoms still go, because nothing reaches a 500 wickets on 478.
  **A CATCH-UP ADD IS UNDATED.** A threshold the whole career had already
  passed before the club's latest season is written with `achieved_at` NULL
  ("reached, date unknown", a dash on every screen), because
  `_src_milestone_achieved` announces anything dated in the last 21 days and a
  club would otherwise be emailed that a veteran "just reached" 5,000 runs from
  an imported history. Control run: the dated writer announces Hetel's 500
  through 5,000 runs at once. `reconcile_milestones`' dry run now prints each
  removal's recorded date and current figures; Shoalwater's was 101 dated
  10 Sep (the double count), 4 dated 24 Sep, all wickets (the 037-shape
  bowling fan-out), and 9 dated 2 Sep, none reached by any figure now.
  **Never run a reconcile's `--apply` off a dry run whose REMOVE list is
  dominated by juniors-turned-seniors; that is the scope talking, not a bug
  being fixed.**
- **"BEFORE THIS SEASON" IS NOT ENOUGH IN AN OFF-SEASON (v9.93.2).** A club's
  newest season row is still last summer's until the new one syncs, so every
  threshold crossed during that summer read as new and would have been dated
  today and emailed as "just reached", months after the game. A threshold is
  now dated only when the player has a game inside the notification window
  (`notification_scan.LOOKBACK_DAYS`, 21 days); otherwise, and for a player with
  no game at all, it is undated. `_compute_milestones` reports `dated`, and
  `reconcile_milestones` marks those additions and prints line-buffered so a run
  redirected to a file can be `tail -f`'d. Control run: 3 of 81 fail.
  **That first cut made an all-clubs run take 3+ hours (v9.95.1)**: it joined
  `v_effective_games` for EVERY player at every club. It now asks only about the
  players with a candidate addition not already history by the season test, off
  the base `games`/`manual_games` tables (a paired twin carries the same date),
  the script sets `jit = off`, and an `all` run prints `[n/N] club: … (Ns)` per
  club so a slow run cannot read as a stuck one.
- **Verified against a real Postgres** (`verify_milestone_figures.py`, 72
  checks now; a control run with the profile-only writer fails the 3 new ones,
  removing Hetel's 1,000-5,000 runs; the original 66
  checks) **with a control run**: 45 fail against the previous build, reporting
  the club's own "87", "3 short of 200" and "2 short of 200". Chromium
  (`verify_milestone_split_browser.mjs`, 10; control fails 5). Neighbours
  re-run: upcoming milestones 24, match coverage 66, junior residual 24,
  notifications 146, manual games import 194, competitions 136, shared
  fixtures 38.

<!-- END original CLAUDE.md L454-537 -->
<!-- BEGIN original CLAUDE.md L3112-3202 -->
## A RETIRED NOT OUT IS NOT A DISMISSAL, and a plain RETIRED is (v9.66.0, Sep 2026)

Reported by a club with two screenshots of one player. Lily Thompson, Payneham
CC, SGCL Metro U18, 2025/26: her profile header read **15.40**, matching
PlayCricket, and StatLab with the grade picked read **12.83**. 77 runs and 8
innings on both.

- **`sync.py` DECIDED THIS WITH `not_out = dt_id == 1`**, so every retirement
  landed in the database flagged as a wicket. Any figure worked out from our own
  scorecards then put it in the average's denominator: 77 / (8 - 2) = 12.83
  against CA's 77 / (8 - 3) = 15.40. The unfiltered header was right only because
  it reads `player_season_stats.not_outs`, which is CA's own `battingNotOuts`
  copied verbatim — so the two paths disagreed by exactly one innings and the
  club could see both numbers on one screen.
- **THE TWO RETIREMENTS ARE DIFFERENT INNINGS, AND THAT IS THE WHOLE FIX.** MCC
  Law 25.4.2 ("Retired - not out", illness or injury, did not resume) is not a
  dismissal; **25.4.3 ("Retired - out", retired for any other reason without the
  opposing captain's consent) IS one**, credited to no bowler. CA sends both, as
  separate ids, and treats them exactly the way the Law does.
- **`services/dismissal.py` IS THE ONE RULE**, and it is deliberately a
  whole-phrase match. **NEVER write this as `LIKE 'retired%'`** — that sweeps
  CA's plain `Retired` in with the two not-out retirements and hands every
  retired-out batter an average they have not earned, which is this same bug
  pointed the other way. The suite pins both directions for exactly that reason.
- **CA'S VOCABULARY WAS ENUMERATED LIVE, NOT ASSUMED**: 260 real scorecards
  across 33 grades give `0 Did Not Bat, 1 Not Out, 2 Caught, 3 LBW, 4 Bowled,
  5 Stumped, 6 Run Out, 8 Retired Hurt, 13 Retired, 14 Retired Not Out,
  15 Absent`. **8, 13 and 14 are three different answers** and no amount of
  reading the code would have told us which.
- **RECONCILED AGAINST CA'S OWN AGGREGATE BOTH WAYS, which is what settled 13.**
  Lily's `battingNotOuts: 3` over two plain not outs plus one Retired Not Out
  proves 14 is a not out. N Raux (Murrumbidgee, 2025/26) retired for 0 and CA
  counted it among his `batting0s` with `battingNotOuts: 1` for his one genuine
  not out — a duck AND a wicket. **8 (Retired Hurt) rests on the Law and on
  CA's naming, not on a measurement**: the aggregate for the one live case found
  belongs to a club outside the sample, and the note says so rather than
  implying it was checked.
- **THE FIX IS THE WRITER, NOT THE READERS.** Every average in the app was
  already `runs / (innings - not_outs)`; they were all reading a flag that was
  wrong. So the change is one line in `sync.py`, the same line in the live
  scorecard merge, and a backfill — not thirty query edits.
- **`python -m app.scripts.backfill_retired_not_out <org|all> --apply`** repairs
  what is stored. No network at all: the dismissal name is already on the row,
  so it is a plain UPDATE, quick enough to run platform-wide and idempotent. Dry
  run by default.
- **PRESSING FIX MISSING TOTALS AGAIN REPAIRS NOTHING, so the backfill does it.**
  `_backfill_missing_season_stats` ends `ON CONFLICT (player_id, season_id) DO
  NOTHING`, so a second run writes nothing at all to a row that already exists —
  and its `source='backfill'` rows were rolled up FROM the old flag, for the
  (player, season) pairs CA omits. The script re-derives their `not_outs` and
  `ducks` from the corrected innings, AFTER fixing those innings, or it would
  re-derive from the very flag it is correcting. **CA's own `source='api'` rows
  are never touched** — they already had this right and are what we reconcile
  against. Found by reading the INSERT, not by assuming a re-run would do it;
  the suite pins the `ON CONFLICT` clause so the reasoning cannot go stale.
- **TWO AVERAGES ON ONE PROFILE, found by auditing rather than by the report.**
  By-opposition and by-venue divided by `NOT not_out AND dismissal_type IS NOT
  NULL`, so an uploaded card whose dismissal column was never read dropped out of
  the denominator there and stayed in it on the career header. Batting by
  position and by grade had the same shape. All four are `innings - not outs`
  now, and **the suite asserts it structurally on the ALIAS** so a new board
  cannot reintroduce it.
- **THE WICKET COUNTERS BESIDE THEM WERE DELIBERATELY LEFT** (`wkts_lost`,
  `our_wkts_lost`, the fantasy engine's `out`). How many wickets a side lost is a
  different question from how many times a batter was dismissed, and nobody asked
  for those to move. They still improve for free, since a retirement is no longer
  a wicket.
- **A RETIREMENT IS NOT A WAY OF GETTING OUT**, so it leaves the How I Get Out
  donut and the record book's unusual dismissals. A retired-OUT stays on both.
  Retiring for 0 is no longer a duck; retiring OUT for 0 still is.
- **Verified against a real Postgres**
  (`backend/verification/verify_retired_not_out.py`, 64 checks through the
  shipped aggregation, StatLab, backfill and writer code: the reported card
  replayed innings by innings, the average agreeing across the career header,
  by-opposition, by-venue, by-grade, the leaderboard and StatLab, a retired-out
  still counting as a dismissal and a duck, retired hurt not, the backfill's dry
  run / apply / no-op re-run / club scoping / never touching a retired-out, and
  the SQL and Python rules agreeing row by row) **with a control run**: 27 of the
  64 fail against the previous commit, reporting the customer's own **12.83** on
  both the profile and StatLab.
- **THE FIXTURE IS SEEDED THROUGH THE CODE UNDER TEST, and the first cut was not.**
  It repaired the rows with the backfill before reading them, so every check
  about the average passed against the broken code — the one thing a control run
  exists to catch. `writer_flag()` asks the shipped rule and falls back to the
  old `dismissalTypeId == 1` when the module is absent, so the control stores the
  fixture exactly as a club's real database holds it today.
- **NOTICED, NOT FIXED**: `player_season_stats.batting_average` still stores CA's
  own figure and a few BetterIQ features read it rather than recomputing. It
  agrees with ours now, so it is no longer a divergence, but it is a second
  stored copy of a derived number.

<!-- END original CLAUDE.md L3112-3202 -->
<!-- BEGIN original CLAUDE.md L3203-3427 -->
## A rate is only as good as the innings behind it (migration 282, v9.59.0, Sep 2026)

**Asked for as a RULE to set, not off a live report** — the 500 runs / 150 balls
/ 333.33 below is a worked example chosen to make the arithmetic obvious, and
nobody has measured how far a real club's figures move. What WAS established
before building is that the mechanism is real: a season scored partly on an iPad
and partly in a written book gives CA a runs total covering every innings and a
balls total covering only the ones somebody typed in, every rate in the app
summed those two halves separately, and `sync.py` wrote a missing ball count as
a zero. **How much any club's figures actually shift is still unmeasured** —
`SELECT` the innings where `balls = 0 AND runs > 0` against a real database to
find out.

- **RUNS AND BALLS MUST COME FROM THE SAME INNINGS, and that is the whole
  rule.** Every rate in the app was `SUM(runs) / SUM(balls)` across a season or
  career, which divides one population by another: the runs from the un-balled
  innings land in the numerator with nothing behind them in the denominator.
  `services/rate_coverage.py` is the one definition, mirroring `game_status` and
  `grade_scope`. **This is the rule `sync._derive_partnerships_grassroots`
  already applies to stands** — when the inputs do not reconcile, refuse to
  derive a figure from them rather than publishing a wrong one.
- **A ZERO BALL COUNT BEHIND REAL RUNS IS NOT A BALL COUNT, and that half is
  load-bearing rather than defensive.** `sync.py` wrote
  `balls=row.get("ballsFaced") or 0`, so a missing count from CA has ALWAYS
  landed in the database as a zero rather than a NULL. Testing `balls IS NOT
  NULL` alone would therefore read every one of those innings as covered and
  reproduce the reported bug one level down. Covered is `balls IS NOT NULL AND
  (balls > 0 OR runs = 0)`; the sync preserves NULL going forward, and the
  zero-with-runs test is what covers the history already stored. **Found by
  reading the writer, not the reader.**
- **A GENUINE 0 OFF 0 IS COVERED.** A batter run out backing up without facing
  is a real innings that contributes nothing to either half, and calling it
  uncovered would understate the coverage fraction on every scorecard that
  holds one.
- **THE RATE CHANGES SOURCE; NOTHING ELSE DOES.** Runs, innings, wickets and
  every average still come from wherever they came from before, so a career
  header still reads 500 runs. Only the ratio is re-derived, from the
  scorecards, where the two halves stay together. That is what lets the answer
  be "500 runs, strike rate 100, from 3 of 10 innings" rather than a smaller
  career.
- **WHERE THERE ARE NO SCORECARDS THE AGGREGATE STANDS AND SAYS SO.** A
  BetterImport season carries a runs total and a balls total and nothing that
  can separate them, so `basis: "aggregate"` is reported instead of a fraction.
  Withholding every historical club's strike rate would be a worse answer than
  naming where the figure came from. Withholding is reserved for what genuinely
  cannot be worked out.
- **`_with_rate_coverage` IS PRESENCE-AWARE**, so a query that never asked for
  coverage keeps its exact payload shape. That is what let one helper serve the
  career header, both season paths, all twelve leaderboard branches, the
  yearbook boards and the record book without any of them growing keys they do
  not use.
- **THE MINIMUM IS COUNTED ON COVERED INNINGS, NEVER ON INNINGS PLAYED.** Ten
  innings with three ball counts is a three-innings strike rate, and letting
  that clear a ten-innings bar is exactly what the bar exists to stop. The
  suite asserts both directions (clears 3, fails 4) on every board branch.
- **THE PLATFORM DEFAULT IS 0, DELIBERATELY.** Nothing has ever qualified these
  boards, so switching a number on for every club would drop players off their
  own leaderboard the day it deployed without anybody choosing it — and a
  number we invented would be quoted back at us. Migration 282 gives a club its
  own (`organisations.stats_min_rate_innings` / `.stats_min_rate_spells`, NULL
  = no preference), read through `services/stats_display.py`, with viewer pills
  above the board for a one-off look. **A viewer's explicit 0 is a real answer**
  — it switches the bar off — so the resolver tests for None, not falsiness.
- **A STRIKE RATE RECORD IS SEASON BY SEASON AND NEVER ALL TIME.** How much was
  written down changed from one era to the next, so a career figure blends
  decades of differently scored cricket into one number nobody can check. A
  season was scored one way. The record book already sets its own qualification
  floors (20 wickets for a bowling average, 50 overs for an economy) and these
  are their siblings; the screen points at StatLab, which already takes several
  seasons at once, for a range.
- **THE NOTE ONLY APPEARS WHERE THE FIGURE IS SHORT, AND ONLY WHERE THE FIGURE
  IS DRAWN.** A note on every rate in the app is noise that trains people to
  stop reading it. `RateFootnote`'s `when` is what stops a leaderboard sorted by
  runs carrying a footnote about a mark nobody can see — caught by the browser
  suite, not by reading the code. The mark is a **dagger, not an asterisk**: an
  asterisk already means "not out" on every scorecard in the world.
- **Fixed while here**: the per-spell economy boards divided by `SUM(overs)` in
  cricket notation, so 10.2 + 10.2 summed to 20.4 rather than 20 overs 4 balls.
  Every economy now converts to balls first, the conversion `player_formats`
  already documented.
- **Verified against a real Postgres** (`backend/verification/verify_rate_coverage.py`,
  105 checks through the shipped functions and route bodies: the reported case
  replayed on the career header, both season paths, all five leaderboard
  branches, the formats page, StatLab's fast and live paths, the yearbook and
  the record book; the flattened zero excluded and the genuine 0(0) kept; the
  scorecard-less season keeping its own figure; the minimum counted on covered
  innings both ways; and the SQL and Python covered tests agreeing row by row)
  **with a control run**: 42 fail against the previous commit, reporting 333.33
  on every surface. **Driven in Chromium** (`verify_rate_coverage_browser.mjs`,
  36: the new strike-rate board, the exact params on the wire for a pill and for
  the club default, the marked and unmarked rows read off the rows themselves,
  the explainer and Escape closing it, both season records and the StatLab link,
  no footnote where nothing is short, and no overflow at 390px) **with a control
  run**: 11 fail against the previous commit.
- **A CHECK THAT COUNTS MARKS ON A PAGE CANNOT FAIL PROPERLY.** The first cut of
  "the covered leader is not marked, the partial one is" counted daggers in the
  whole document, which passes with BOTH marked. It reads the two rows.
- **NOTICED, NOT FIXED — and SETTLED in v9.65.1 below**: StatLab's family
  targets (`family_career`, `family_season`) divided the season totals, and said
  so in a comment where the rate was built, on the reasoning that they already
  ignored every other match-context filter. They honour the aggregate scope now,
  and coverage is not a filter, so all three are re-derived from the members'
  own scorecards. A club's history that predates the sync also
  needs a Full Rebuild before its ball counts read as NULL rather than zero;
  until then the zero-with-runs test is what carries it, which is why that test
  exists rather than being tidied away.

### The one figure the browser still worked out itself (v9.65.1, Sep 2026)

Reported off Darren Hind's profile: the Player Profile radar read a **strike
rate of 320.19** beside an innings history where most rows record no balls
faced at all. 2,379 runs over the ~743 balls somebody had typed in.

- **282 SET THE RULE AND SEVERAL SURFACES WERE NEVER BROUGHT ACROSS.** The
  career header two inches above the radar already had the figure right; the
  radar computed its own in the browser as `SUM(runs) / SUM(balls)` over every
  innings it drew. `careerBatting.strike_rate` and its coverage pair were on
  the payload the component already received — it simply ignored them. **It was
  the last client-side rate in the frontend**, and the audit that found it is
  the one to repeat: grep the frontend for a division by summed balls, and the
  backend for a rate whose module carries no `rc.` import.
- **A RATE READS THE SERVER'S FIGURE OR IT IS A SECOND DEFINITION.** The fix is
  not to reimplement coverage in the browser — it is to stop computing rates
  there at all. Two places that work out a strike rate are two places that can
  disagree about it, which is exactly what a reader saw.
- **`rc.with_coverage` IS THE ONE SHAPE OF A COVERAGE PAIR**, moved out of
  `aggregations._with_rate_coverage` (which now delegates) so a ROUTER can use
  it too. A query emits `sr_counted`/`sr_of` or `econ_counted`/`econ_of` and the
  helper turns them into the pair. Presence-aware, so a query that never asked
  keeps its exact payload shape.
- **`batting_rate_columns(extra=…)` EXISTS FOR A SELECT WIDER THAN THE INNINGS
  THE RATE IS ABOUT.** A query keeping did-not-bat rows for their counts has to
  leave them out of the coverage, or a 0 off 0 nobody batted in reads as an
  innings that answered the question — and `covered_innings` then exceeds the
  innings it is counted against. The teammate split is that shape.
- **THE CAPTAIN PANEL'S ECONOMY WAS TWO BUGS IN ONE LINE**: `SUM(runs) /
  SUM(overs)` with no coverage AND overs summed in cricket notation, so 10.2 +
  10.2 came to 20.4 rather than 20 overs and 4 balls. It read **6.25 where the
  answer is 3.00**. StatLab's balls-per-wicket carried the same `overs * 6` on
  three targets.
- **AN OPPONENT'S CARD REACHES US THE SAME WAY OURS DOES.** `iq_opponent`'s
  live accumulator wrote `ballsFaced or 0`, the same flattening `sync.py` does,
  so a danger batter's strike rate was inflated the same way. `DOSSIER_VERSION`
  is bumped so every cached dossier rebuilds rather than waiting out the 7-day
  TTL.
- **THE FAMILY TARGETS ARE FIXED, AND THE OLD NOTE'S REASONING NO LONGER
  HOLDS.** v9.59.0 left them alone because they "ignore every other
  match-context filter", so half-fixing looked worse. They honour the aggregate
  scope now, and — the part that settles it — **coverage is not a filter**. It
  is about which innings can answer, so re-deriving the rate over the SAME
  population the counts cover is consistent rather than half-fixed.
- **A FAMILY'S RATE IS THE FAMILY'S COVERED HALVES, and the first cut of the
  check got this wrong.** It expected the family's WHOLE 700 runs over its 550
  counted balls (127.27) — the same two-population mixing on a family scale.
  The answer is 350 over 550. Found by running it, not by reading it.
- **STATLAB PUBLISHES NO COVERAGE PAIR ON ANY TARGET, so the family ones do not
  either.** The extra columns were written, then dropped: a target that reports
  a pair no sibling reports is a column contract that differs per target, and
  `_serialise` passes every column through to the CSV. Correct figures, uniform
  shape. Saying it on a StatLab report is its own change.
- **DELIBERATELY LEFT ON THE AGGREGATE, and each for the same reason — there
  are no scorecards to re-derive from**: the Scout product (`iq_scout`,
  `scout_discovery`, `scout_internal_link`, `frontend/src/scout/lib/seasonRollup.js`)
  reads CA's season totals for players at OTHER clubs, and `iq._their_key_players`
  reads a synced opponent's own aggregates. That is the documented
  `basis: "aggregate"` case. They are NOT marked as such today, which is the
  obvious follow-up and is a frontend change in three screens.
- **ALSO LEFT, and NOT because it is hard**: `iq_team._role_ratings` and
  `iq_trends._similar_players` derive an economy and a strike rate from
  `player_season_stats` as z-scored FEATURES and `pop()` them before returning —
  no figure is published, and switching their source would move the MVP rating
  and the similar-player list for every club with nobody having asked.
- **Verified against a real Postgres**
  (`backend/verification/verify_rate_coverage_everywhere.py`, 33 checks through
  the shipped route bodies and services: the captain economy and its coverage,
  two 10.2-over spells measured as 124 balls, the teammate split both sides with
  the fully-covered mate NOT marked, the deep dive's balls and balls-per-boundary
  from the covered innings, the attack board, the dossier's batter and bowler
  through the real accumulator, all three family targets, no coverage columns
  leaking into a StatLab row, and the SQL and Python agreeing row by row) **with
  a control run**: 17 of the 33 fail against the previous commit, reporting
  333.3, 300.0, 127.27 and the captain's 6.25.
- **Driven in Chromium** (`frontend/verification/verify_radar_rate_browser.mjs`,
  21: the radar reading the server's figure and not the one its own innings
  would give, the dagger, the note naming the innings, a fully covered player
  drawing neither, the aggregate basis still drawing a figure rather than a
  dash, the economy row counting SPELLS, and no overflow at 390px) **with a
  control run**: 11 of the 21 fail, the radar reading 500.00 where the server
  said 100.00 and a dash where the aggregate figure belongs.
- **The neighbouring suites were re-run rather than assumed**: rate coverage
  105, competitions 136, match coverage 66, shared fixtures 38, season fold 65,
  records timing 47, milestones 23, and the profile browser suite 49.
- **A CHECK THAT READS THE WHOLE CARD CANNOT TELL WHICH FIGURE IS MARKED.** The
  radar checks read each axis off its own row and strip the dagger before
  comparing, since the career strip above the card prints a strike rate too.
- **THE INNINGS HISTORY SR COLUMN WAS BLANK ON EVERY ROW, and it is the column
  a reader would have used to check the headline.** `batting_innings.strike_rate`
  has a writer for a hand-entered manual innings and none at all for a synced
  one — `sync.py` stamps CA's `battingStrikeRate` onto the season aggregate and
  nothing else — so the column was NULL for essentially every innings on the
  platform. Derived on read now (`rc.innings_strike_rate_sql`), never
  backfilled: a stored rate is wrong the moment somebody corrects the runs, and
  deriving it fixes every row already in the database with no migration and no
  re-sync. Same call `player_age.age_on` makes about an age.
- **AT ONE INNINGS THERE IS NO POPULATION TO MIX, so `NULLIF(balls, 0)` IS the
  coverage test.** The runs and the balls are the same innings by construction,
  and the three ways an innings cannot answer — a NULL count, a count flattened
  to zero with runs on it, and a genuine 0 off 0 — all fall out of that one
  expression as NULL. The suite asserts the SQL and the Python agree row by row
  rather than taking the equivalence on trust.
- **A STORED FIGURE IS THE FALLBACK, NOT THE ANSWER.** Where balls were
  recorded, a stored rate that contradicts the two columns printed beside it
  reads as a bug; where they were not, it is the only thing we hold, which is
  the case the manual scorecard form's own field exists for.
- **`get_batting_by_position` AVERAGED PER-INNINGS STRIKE RATES**, which weights
  a four-ball cameo the same as a hundred-ball innings — over a column nothing
  writes, so it read blank anyway and no screen draws it. Fixed rather than left
  standing: it would have been wrong the day somebody rendered it. **The control
  run is what showed the shape of it** — the old expression reads **88.0**, the
  one manual innings that happened to carry a stored figure, ignoring the three
  real ball-counted innings entirely.
- **NOT DONE: no SR column was added to Batting by Position.** The field is
  correct now and nothing renders it; adding a column to a table nobody asked
  about is a product decision, not part of fixing a wrong figure.

<!-- END original CLAUDE.md L3203-3427 -->
<!-- BEGIN original CLAUDE.md L6123-6190 -->
## Season × grade matches on a player profile, and the undercount it exposed (v9.37.3, Aug 2026)

Asked for on Analysis → Team: seasons down one axis, a column per grade the
player actually turned out in, a plain match count in each cell, columns in the
club's own reading order. No migration, no new endpoint.

- **The grid and the by-grade table above it come from ONE attribution pass.**
  `get_player_team_breakdown` now builds a per-(season, grade) cell map and
  derives `rows` from it, rather than the two being computed separately. That
  is what makes the grid's column totals equal the table's `matches` **by
  construction** — the same one-place discipline `_season_by_season_scoped`
  exists for, and the reason a screen can't end up disagreeing with the card
  sitting two inches above it.
- **Doing it per season fixed a live undercount.** Step 1 used to compare CA's
  exact per-grade aggregate against the scorecard count **across the whole
  career** (`extra = max(0, agg_total - scorecard_total)`), which is only right
  when every season is one or the other. A player with `player_season_grade_stats`
  for 2024/25 (CA: 10, held: 3) and scorecards only for 2025/26 (5) read **10**,
  not 15 — the scorecard season was swallowed by the aggregate one. Reproduced
  against a real Postgres by running the pre-change function, then the new one.
  It flows into the grade-matches milestones too (`players.py` ×2 read
  `rows[].matches`).
- **The two attribution rules are unchanged, just applied per season**: CA's
  per-grade row wins but never below the scorecards we hold; with no per-grade
  row, a season's shortfall goes to the one grade it can only have come from,
  else to `unattributed`. A season CA HAS broken down is taken at its word, so
  a shortfall against its own season total is left alone rather than guessed at
  — the deliberate `seasons_with_exact` skip the old code made, kept.
- **Seasons are folded onto their canonical row before anything is counted**
  (`load_reverse_alias_map`), or a Merge Seasons pair, or one CA season guid per
  competition, draws the one year as two lines.
- **`_org_grade_display_orders` is keyed on the FOLDED grade name**, not the raw
  CA guid `social_rounds._grade_display_orders` uses — these rows have already
  been through the merge alias and the club's rename, and two guids can land on
  one name. `MIN(display_order)`: the reorder endpoint stamps the position onto
  the canonical grade and every alias merged into it, so MIN ignores a NULL left
  on an alias nobody ordered. A grade the club has never placed reads NULL and
  the column sorts after every placed one, the same rule everywhere else.
- **The existing MATCHES BY GRADE table is deliberately still sorted by matches
  descending.** The club's order was asked for on the new grid; re-sorting a
  leaderboard-shaped summary was not, and quietly widening the change is how a
  screen someone relies on moves under them.
- **`unattributed` gets its own muted column, only when non-zero**, so the
  columns plus that column equal the TOTAL on every row and on the career line.
  The AFL grid's trade-off (season total ≠ sum of cells, documented in its own
  comment) is avoided rather than copied.
- **A historical bundle season is NOT special-cased.** `_HISTORICAL_BUNDLE_MATCH_CAP`
  hides those from `get_season_by_season`, but the by-grade table has always
  attributed their matches into grades, so excluding them here would make the
  grid disagree with the table above it — the worse of the two outcomes. A club
  with one will see a large early row.
- **Merge Grades is renamed Manage Grades** (nav label + the copy that names it;
  the URL `/admin/grades` and the in-page "Merge Grades" panel heading are
  unchanged, and the AFL silo's own screen is untouched).
- **Verified against a real Postgres** (41 checks through the shipped
  `get_player_team_breakdown`: the plain grid, the club's order with an unplaced
  grade last, a merged grade as one column under one position, a renamed grade,
  the mixed-history undercount, an unplaceable mixed-grade season, a
  single-grade gap, two merged seasons as one row, the season filter, a grade CA
  counts but we hold no scorecard for, a club that has never ordered anything,
  an empty player, and another club's order not reaching ours) and **driven in
  Chromium** (9: the column headings in club order, every rendered row and its
  dashes, the career line, the rendered rows and columns meeting at the same
  total, the grid agreeing with the table above it, no page errors, no overflow
  at 390px). The harness builds its tables from the ORM models and pulls the
  five `v_effective_*` views straight out of migrations 038 / 075 / 147 / 266.


<!-- END original CLAUDE.md L6123-6190 -->
<!-- BEGIN original CLAUDE.md L6569-6643 -->
## A washout is not a match played (migration 266, v9.32.1, Aug 2026)

Reported off Hamilton Veterans: Geoff Barker's 25/26 reads 13 matches, the club
counts 10, and three fixtures were washed out.

- **Nothing was miscounting. `player_season_stats.matches` is CA's own
  `statistics.matches`, copied verbatim** (`sync.py`'s season-stats upsert),
  and CA's answer really is 13. **CA counts a player as having played the
  moment they are on the team sheet**, ball bowled or not. Verified live rather
  than reasoned about: the club's 25/26 card is 14 fixtures, three
  `status: ABANDONED`, and a team-mate named in all of them reads 14.
- **The comment in `aggregations.py`'s opposition breakdown claiming CA already
  excludes abandoned games is wrong**, and was wrong before this. It is
  corrected in place. Do not build on it.
- **`games.status` (migration 266) exists because `result` cannot answer the
  question.** A NULL result covers a washout, a fixture still to be played, one
  in progress and one we could not classify, all four. The column takes CA's
  own word verbatim.
- **The correction lands in `v_effective_player_season_stats`, not in the
  callers** — the same one-place discipline migration 060 used for the
  cross-club leak, so career totals, the season table, the leaderboards and
  records all move together and a club with no washouts joins an empty set and
  is byte-for-byte unchanged.
- **The rule is "named and recorded nothing at all", not "abandoned".** A game
  called off at tea with a hundred on the board was played and the club counts
  it, so the subtraction only fires where the player has no batting, bowling or
  fielding row for that fixture. `NO RESULT` (statusId 5) is deliberately NOT
  in `NOT_PLAYED_STATUSES` for the same reason — that is a game that started.
- **`services/game_status.py` is the one vocabulary**, shared by the sync, the
  view, the read paths, the backfill script and (as a mirrored constant) the
  two screens. Two copies of "which statuses mean it never happened" is how
  they start disagreeing.
- **The view was NOT enough, and this is the lesson.** Correcting
  `v_effective_player_season_stats` fixes every reader that sums CA's season
  aggregate, and misses every reader that counts matches from
  `game_appearances` itself — which is what StatLab does. Reported live:
  StatLab still read 13 after the platform-wide figure was already 10.
  `appearance_counts_as_match(alias)` is the shared predicate, applied at
  **five** sites found by auditing every `game_appearances` read rather than
  assuming: StatLab's `appear` CTE (the only source of its `matches`), the
  by-grade and by-season-grade breakdowns, by-venue, and the FORMATS page.
  **When adding a screen that counts matches, ask which of the two sources it
  reads.** By-opposition needed nothing — it already drops a result-NULL game.
  The recent-games lists at `aggregations.py:511/553` are deliberately left
  alone: a fixture list should show a washout a player was picked for.
- **No Full Rebuild.** The grade match list already carries `status` per
  fixture and the discovery loop already fetches it, so a plain Sync Now fixes
  the current season through the same bulk pass `is_final` and `match_format`
  use. `python -m app.scripts.backfill_game_status <org-id-or-slug|all>` covers
  the seasons an incremental run no longer scans.
- **A club whose season rows came from "Fix Missing Totals" needs it re-run.**
  Those rows (`source = 'backfill'`) store a count computed from per-game rows
  rather than reading CA's, so the view's correction cannot reach them. The
  rollup's `appearances` CTE now excludes called-off fixtures; the script says
  when a club has such rows.
- **Scale, measured before building rather than assumed**: 316 of 4,165
  fixtures across all 102 clubs' latest season carry no result; ~88% of a
  sample are genuinely ABANDONED/CANCELLED and about half of those have a team
  sheet. So ~140 fixtures a season platform-wide, across ~45 clubs. Invisible
  at a club playing 380 fixtures, glaring at one playing 14 — which is why a
  veterans club found it and nobody else had.
- **Found while verifying: `CREATE OR REPLACE VIEW` cannot DROP a column.**
  The first cut of 266's downgrade replaced the status-carrying
  `v_effective_games` with the shorter prior definition and failed outright.
  It drops and recreates now. **Migration 169's own downgrade has the same
  latent defect** and would fail the same way; it has simply never been run.
- **Verified against a real Postgres** (24 checks through the shipped view and
  the real service functions: the reported 13 → 10 and a team-mate's 14 → 11, a
  control club-mate unchanged, CA's stored row never rewritten, a mid-play
  abandonment staying counted, a NULL status subtracting nothing, NO RESULT
  still counting, CANCELLED behaving like ABANDONED, the rollup, the scoped
  path, the season-by-season table and career games both reading 10, the
  Matches screen's list, migration 266 applied three times to a populated
  table, and the downgrade putting CA's figure back).

<!-- END original CLAUDE.md L6569-6643 -->
<!-- BEGIN original CLAUDE.md L6760-6786 -->
## StatLab: one player, and tabs that reshape the filters (v9.96.0, Sep 2026)

Asked for off the StatLab screen: a Player filter as the first thing in Build
custom query, and the table-type tabs (Player career, Player season...) to do
something, since they only swapped the target and left the filters identical.

- **`context.player_id` IS DELIBERATELY NOT A `PLAYER_CONTEXT_FILTERS` ENTRY.**
  Every entry there sets `needs_live`, which moves player_career onto the
  per-innings path and counts the career from scorecards, so a player's
  filtered row would read differently from the same row unfiltered.
  `_with_player_filter` ANDs a restriction onto each target's FINAL WHERE
  instead: the row the unfiltered table shows, alone. Match list reads "matches
  he played in" (the four-source union), Partnerships "either batter". Not
  applied to family targets, team innings or derived reports, and the UI hides
  the picker there.
- **`TARGET_GUIDE` (StatLab.jsx) is which filters mean anything per target**,
  read off what each backend query actually applies (`ic`/`pc` usage). A tab
  click runs the table, snaps the sort, and `pruneContext`/`pruneTree` DROP what
  the new target cannot use rather than hiding it, so no hidden filter keeps
  scoping results. Keep it in step when a target starts or stops honouring a
  context filter.
- **Verified**: `backend/verification/verify_statlab_player_filter.py` (17
  checks, real Postgres, the filtered row equal to the unfiltered one on both
  paths; control: 11 fail) and `frontend/verification/verify_statlab_player_browser.mjs`
  (23; control: 16 fail). `verify_rate_coverage.py` gained a `__main__` guard so
  it can be imported for its schema and seed.

<!-- END original CLAUDE.md L6760-6786 -->
<!-- BEGIN original CLAUDE.md L6787-6861 -->
## StatLab gets the platform's Grade Type / Match Type filters (v9.29.4, Aug 2026)

StatLab was the last stats surface with no `GradeScope` (migration 259). Two
consequences, and the second is the one that mattered: there was no way to ask
it for the T20s or the women's grades, AND it counted every grade whatever the
club had set, so a club that leaves juniors out saw StatLab disagree with its
own Leaderboard.

- **StatLab now applies the club default like every other screen, and that is a
  deliberate behaviour change.** `categories=None` means "the club's default"
  everywhere else, so it means that here too. A club with junior grades will see
  StatLab's unfiltered figures drop to match the Leaderboard's, including inside
  a saved report written before this. The Grade type control says what the
  default leaves out ("Club default (no Juniors)") rather than reading "All",
  and the results carry `scopeNote`'s own line, the same one Records shows.
- **The resolved scope rides in the context dict under `_scope`, and that key
  can never arrive from a browser.** `_ctx_from_request` only ever writes keys
  from its own whitelists and none of them start with an underscore, so a
  crafted URL cannot hand the query builder a scope of its choosing. Doing it
  this way meant two touch points instead of threading a new argument through
  all ~30 `_build_context_filters` call sites.
- **`_scope_fragment` exists because the two sides format differently.**
  `GradeScope.clause()` hands back a fragment with a leading ` AND ` for callers
  that paste it into a WHERE; StatLab keeps conditions in a list and joins them
  itself, so the AND comes off. Every condition inside is already bracketed, so
  what is left composes.
- **`kind` per read, exactly as the platform rule says.** `game_universe` gets
  `clause("g.grade_id")` (per-game: category off the grade, format off each
  fixture's own `match_format`, which is what stops a grade that plays both
  formats filing all its games under one). The residual CTEs and the three
  aggregate-only queries get `clause("pss.grade_id", "aggregate")`, which emits
  `AND FALSE` under a match-type filter rather than counting an imported season
  towards a T20 record it can say nothing about.
- **The three aggregate-only queries had to be found, not assumed**:
  `query_family_career`, `query_family_season` and `derived_most_minutes_in_season`
  sum `player_season_stats` directly and never touch `game_universe`, so the
  clause `_build_context_filters` adds would have missed them entirely and the
  filter would have read as working while doing nothing. Same class of gap as
  the `_pss_season_filter` one the release before. On family_career it goes in
  the JOIN condition, not the WHERE: a family whose every row is out of scope
  should still list at zero rather than disappear.
- **An active scope sets `any_match_used`,** so the aggregate-path targets
  (player_career, player_season) switch to live per-innings aggregation. A scope
  is only answerable from per-game rows, and this is the same trade
  `records.py`'s `use_game_level` makes with its own `scope_active`.
- **A match type genuinely cannot be answered by Family career / Family by
  season, and the screen says so** instead of showing an unexplained empty
  table. Those two have no per-game path at all.
- **The picker offers only what the club runs.** `GET /organisations/{id}/grade-categories`
  (public, cheap, already there) supplies `available` / `default` /
  `available_formats`; a club with no junior programme is never shown a Juniors
  tick box, which is also exactly when the filter would do nothing.
- **On the wire they are ONE comma-separated string each** (`?categories=senior,womens`),
  not a repeated param, because that is the shape every other stats endpoint
  takes and what `resolve_scope` reads. So they stay plain text context keys and
  the picker splits and joins around them — the opposite call to `grade_names`,
  which is repeated precisely because a grade name can contain a comma and these
  fixed keys cannot.
- **Verified against a real Postgres** (19 checks through the real `resolve_scope`
  and the shipped StatLab builders: the club default leaving juniors out, an
  explicit junior pick finding them, one mixed grade splitting 1 two-day / 1
  one-day / 1 unplaceable, an unlabelled game inheriting a single-format grade's
  format but NOT a mixed grade's, every-format reading as no filter, the two
  axes composing with each other and with a picked grade, residuals kept under a
  category scope and emptied under a format one, and a senior-only club emitting
  no clause and binding nothing) and **driven in Chromium** (35 checks, the 26
  from the multi-select release plus the two new pickers: the club-default
  label, only the offered types, the exact params on the wire, both chips,
  dismissing one, the left-out note, and a shared link opening with both ticked;
  no page errors, no overflow at 390px).
- **Noticed, NOT fixed**: Family career and Family by season ignore every OTHER
  context filter too (opposition, result, dismissal, a picked grade). They sum
  season aggregates and predate the live per-innings path the player targets
  use. That is a pre-existing gap, not one this release introduced.

<!-- END original CLAUDE.md L6787-6861 -->
<!-- BEGIN original CLAUDE.md L6862-6939 -->
## StatLab's list filters take several values at once (v9.29.2, Aug 2026)

Reported: StatLab could only ever be scoped to ONE grade, so "most runs across
1st and 3rd Grade" was unanswerable. A range picker was the obvious shape and is
the wrong one — the whole point is dropping a grade out of the middle of a run.

**The rule that decided the scope: a filter whose values come from a KNOWN LIST
gets the tick-box picker; everything else keeps the control it had.** So Grade,
Season, Result and Dismissal are multi-select (`grade_names`, `season_ids`,
`results`, `dismissals`); opposition, player role and the award fields stay free
text (there is no list to tick), the year and position fields stay ranges, and
Gender / Overseas stay single because ticking every option there IS "no filter".

- **`grade_names` (a list) is the new filter; `grade_name` (single) stays.** The
  UI writes `grade_names` and clears `grade_name` in the same update, so the two
  can never disagree; the single key is kept because a saved report and a shared
  link written before this shipped both carry it. If both arrive anyway they
  AND, which is what a link the user then added to should do.
- **It is NOT a new spec-dict entry.** `MATCH_CONTEXT_FILTERS` values are one
  fixed SQL string with one bound param, and this clause grows with the
  selection, so it lives in `_build_match_list_filters` beside the `season_ids` /
  `grade_ids` id filters that already worked that way. Same expression the
  single-value filter compares (`COALESCE(am.canonical_name, gr.name)`), so a
  merged grade still resolves through its canonical name.
- **`_text_list` deliberately does NOT comma-split, and the router gives text
  lists their own reader.** The id lists accept `?grade_ids=a,b` because a UUID
  can't contain a comma; a grade name can ("A Grade (Smith, Jones)" is real
  enough — a sponsor suffix does this), and splitting it would quietly turn one
  grade into two that match nothing. `_CTX_KEYS_LIST_TEXT` reads the repeated
  param only. The URL is `?c_grade_names=…&c_grade_names=…` for the same reason.
- **Residuals answer it, and their halves are ORed.** `_residual_grade_match`
  took a `suffix` so each ticked grade binds its own param; the clauses are ORed
  inside one bracket, since ANDing them asks for a row that is two grades at
  once. `grade_names` is not in `_RESIDUAL_DISQUALIFYING_MATCH_KEYS` for the
  same reason `grade_name` isn't — an imported or manual row carries its grade.
- **A selected grade that is no longer in the club's list still draws a row** in
  the picker (renamed, merged away, arriving from a saved report), so it can be
  seen and un-ticked instead of silently scoping the query from nowhere.
- **`results` and `dismissals` reuse ONE definition of their SQL, extracted.**
  `_RESULT_CASE_SQL` and `_dismissal_match_sql(param)` are now shared by the
  single-value spec entry and the multi-select builder, because two copies of a
  CASE that size drift the first time one is edited. The dismissal CASE takes
  its bind param BY NAME so each ticked value gets its own.
- **`dismissals` lands in the INNINGS block, and that is what keeps residuals
  honest.** `_residual_disqualified` treats any innings clause as unanswerable,
  so putting the clause in `ic` costs nothing extra. `results` needed its own
  entry (`_RESIDUAL_DISQUALIFYING_LIST_KEYS`) since it has no spec entry to read
  a `value_kind` from — and it **coerces before disqualifying**, or a selection
  that is entirely junk would filter nothing while still knocking residuals out.
- **Season multi-select was supported server-side all along and one query had
  never been told.** Three queries aggregate straight off `player_season_stats`
  rather than through `game_universe` (player_season's aggregate path,
  family_season, batting minutes), so they each carry their own season clause —
  and `query_family_season` only ever honoured the single `season_id`. Shipping
  the picker would have meant a multi-season pick working on four screens and
  silently doing nothing on Family by season. All three go through
  `_pss_season_filter(context, params, prefix)` now.
- **The Season chip is labelled the way the picker labels it** (`formatSeason`,
  so "2025/26"), not the season's stored `name` ("Summer 2025/26") as it was.
  A chip should read back what was ticked.
- **Verified against a real Postgres** (33 checks through the shipped builders'
  own SQL: two grades returning exactly those two, one grade matching the old
  single-value result byte for byte, a merged grade pulling in its alias' games
  and its alias-tagged residual rows, the comma-carrying name, an unknown grade
  returning nothing rather than everything, the residual halves ORing rather
  than ANDing, both results and both seasons, caught counting the keeper's catch
  as well, a junk value filtering nothing AND not disqualifying residuals, and
  the shared pss season clause honouring a multi-season pick) and **driven in
  Chromium** (26: the exact params on the wire for all four pickers, each chip's
  wording, dismissing one clearing both keys, un-ticking one of three, the
  search box, an old single-value link on each filter still opening pre-ticked
  and handing over cleanly once a second value is added, no page errors, no
  overflow at 390px).
- **Noticed, deliberately NOT fixed**: the Result filter offers "Tied" and can
  never match it. `games` carries a winning team or it doesn't, so the CASE only
  ever emits won/lost/drawn and a tie is indistinguishable from a draw. Fixing
  it is a data-model question, not a filter one.

<!-- END original CLAUDE.md L6862-6939 -->
<!-- BEGIN original CLAUDE.md L7001-7212 -->
## A grade is several things at once, and the dashboard filters on that (migration 259, v9.26.0, Aug 2026)

Reported off the club dashboard: the GENDER filter should be a **Grade Type**
filter (Men's / Juniors / Women's / Masters), T20 needs to exist, a grade should
be able to hold several classifications at once, there should be a second
**Match Type** filter (Two Day / One Day / T20), and the CAPTAIN filter should
go.

- **The Gender filter was reading a player attribute to answer a question about
  the grade.** `p.gender` is free text, every writer stores it lowercase, and
  the leaderboard SQL compared `p.gender = :gender` against the `'Male'` /
  `'Female'` the pill sent — so it returned an empty board wherever it was
  actually wired, and on the dashboard it was a **dead control** (no state, a
  no-op setter). Same for CAPTAIN there, and on Players, Games and Ladders.
  Those pills are off on all four screens now. **Gender is left in place on
  Leaderboard and Records**, where it is wired; the casing bug is theirs and was
  not chased here.
- **`grades.categories` and `grades.match_formats` (TEXT[], migration 259)**,
  and **`grades.category` stays and is kept in step with the first entry of
  `categories`** in canonical order. That is what makes this additive: the
  public grade grouping, `grade_labels.org_grade_categories`, the AFL silo's own
  single-label readers and everything else that reads one value are untouched.
  Send `category` alone to `PATCH /admin/grades/classify` and it still works.
- **The two axes resolve into ONE `GradeScope` and one exclusion list**, so
  adding a whole second filter changed no query — `resolve_scope` gained a
  `formats=` argument and every one of the ~25 `scope.clause(...)` call sites is
  as it was. A grade has to pass both tests to stay in.
- **The axes fail differently on an unclassified grade, deliberately.** Every
  grade has a category (the name suggestion bottoms out at men's senior), so
  that test always has something to judge. A grade's FORMAT is often genuinely
  unknowable, so a grade we cannot place is left OUT of an explicit format
  filter rather than swept in — asking for T20 and being shown everything the
  club has ever run is worse than being shown what we can vouch for.
- **Format is derived, not asked for.** `org_grade_format_sets` falls: what the
  club ticked → **the formats actually recorded on that grade's games
  (`games.match_format`)** → the grade name. The middle step is the one that
  matters: it is accurate for a single-format grade and needs no admin action,
  which is why most clubs will find their grades already right. `fee_format` is
  read too, but `'exclude'`/`'women'` are billing answers and map to nothing.
- **`format_from_match_type` returns None for an unrecognised string, and must
  keep doing so.** `fees.derive_fee_format` has to pick something ("everything
  else is a single day") because a match day must be billed; a filter that
  cannot tell has to say so instead.
- **An explicit pick matches ANY of a grade's categories; the club DEFAULT
  matches only the primary one.** Load-bearing, and the browser found it: with
  ANY-matching everywhere, a "Girls Under 16" grade sneaks back into a default
  that leaves junior out, on its women's half — junior seasons back inside
  senior careers, which is the exact bug migration 228 exists to prevent. An
  explicit "show me the women's grades" is an INCLUSION and should find it;
  the default is an EXCLUSION and should not. `primary_category()` is the same
  junior-first precedence `suggest_category` already used, so the default path
  is byte-for-byte what it was.
- **A picked grade beats the CATEGORY half of the scope and NOT the format half
  (`GradeScope.formats_only()`).** Reported from the Leaderboard with 4th Grade
  selected: the Match Type pills did nothing. The rule above was written as
  `if grade_id or grade_name: scope = None`, which threw the format away with
  the category — and picking a grade AND a format is the single most useful
  thing this filter does, because a grade routinely plays both in one season.
  Six sites: the three extended leaderboards, `records.py`, `games.py`,
  `get_org_results`, `_club_results` and `get_club_summary`'s grade branch.
- **The grade branches never interpolated `scope_clause` at all**, which is the
  other half of the same report. A picked grade takes its OWN query path in
  every one of those functions (`WHERE g.grade_id = :grade_id`, or
  `WHERE {_GRADE_MATCH}` for a grade picked by name), and those templates simply
  had no `{scope_clause}` in them — so even once `formats_only()` kept the scope
  alive it had nowhere to land. **When adding a filter to a leaderboard, check
  the picked-grade branch as well as the default one**; they are separate SQL and
  the default branch passing is not evidence about the other. `records.py` is
  the worst of it — `game_grade_clause`, `pairs_grade_clause`, `_bat_where`,
  `_bowl_where` and `_match_grade_filter` are five separate fragments, and the
  first two used to REPLACE the scope clause with the grade condition rather
  than append to it.
- **FORMAT IS PER FIXTURE, CATEGORY IS PER GRADE, and the two are not
  symmetrical.** The first cut filtered format at grade level and was wrong:
  Applecross 1st Grade plays 32 one-day and 26 two-day games inside ONE season,
  so a grade-level answer files most of a season under the wrong heading.
  `GradeScope.format_clause()` is a condition on each game's own
  `match_format`; `clause()` gained a `kind` argument so the ~22 per-game call
  sites needed no edit at all (`kind='game'` is the default) and only the five
  that are not per-game did:
  - **`kind='aggregate'`** (3 sites, `pss.grade_id`) emits `AND FALSE` under a
    format filter. A `player_season_stats` residual has no game and therefore no
    format — counting it towards "his T20 record" would be inventing a figure
    rather than filtering one. A CATEGORY-only scope still keeps residuals, per
    the `_RESIDUAL_SOURCES` rule below.
  - **`kind='grade'`** is an EXISTS over that grade's games, for a genuine grade
    LISTING with no game in the query. **The two `gr.id` sites are NOT that** —
    `get_batting_by_grade`/`get_bowling_by_grade` join games and express only the
    CATEGORY exclusion against `gr.id`, so they pass `game_alias="g"` and read
    format per fixture. Classifying them as `'grade'` was the first cut and the
    verification caught it: a two-day filter returned every innings in a grade
    that *sometimes* plays two-day, i.e. the exact bug this design exists to
    prevent. If a query joins `v_effective_games`, its format is per fixture,
    whatever column the category half happens to use.
  - **`scope.active` now includes `format_active`**, so a format filter switches
    every reader to the per-game path even when no grade is excluded. That is
    what makes it work at all: the aggregates cannot answer it.
- **A game with no recorded `match_format` falls back to its GRADE's format,
  but only when the grade plays exactly one.** A mixed grade says nothing useful
  about one unlabelled fixture, and guessing would put one-day runs in the
  two-day column. So the Grades screen's Match Type ticks are a FALLBACK for
  pre-`match_format` history, not the filter itself — the copy says so.
- **`format_sql_case()` is the SQL mirror of `format_from_match_type`**, and the
  verification asserts they agree on a table of 18 real strings ("Two Day+",
  "TWENTY20", "40-over", "BYE", "2-day", …). Change one and change the other, or
  the dashboard's filter and the profile's split file the same game differently.
- **Confirmed against live CA data for the reported grade.**
  `/scores/grades/94159f73-…/matches` (Applecross 1st Grade 25/26) returns
  **39 One Day and 32 Two Day in the ONE grade**, and the fixture the club
  linked (`/scores/matches/4dbd37f7-…`) reads `matchType: 'Two Day'`,
  `matchTypeId: 1`. That is the field PlayHQ shows as **Match Info → Format**,
  it is on the match record AND on every row of the grade match list, and it is
  what `games.match_format` stores.
- **A bare curl of that endpoint returns PascalCase, and it will send you
  chasing a bug that isn't there.** `grassroots_scores_client._get` always
  sends `jsconfig=eccn:true` (a ServiceStack formatting flag), which is what
  camelCases the payload — WITH it the envelope is `{"matches": [...]}` and rows
  carry `matchType`; WITHOUT it they are `{"Matches": [...]}` and `MatchType`,
  so `data.get("matches")` and `m.get("matchType")` both read empty. Reproduce
  through the client, or pass `jsconfig=eccn:true` by hand.
- **Fixed while here, and it was a real one**: `_JUNIOR`/`_MASTERS` ended their
  age patterns `\d+\b`, and a word boundary cannot match before a letter — so
  **"Under 14s", "U14s", "Year 9s" and "Over 40s" all classified as SENIOR**.
  The singular spellings always worked, which is why nobody noticed, and the
  plural is how clubs actually write them. Junior seasons have been sitting
  inside senior career averages for every club that spells it that way. Now
  `\d+s?`.
- **The filter is on every stats surface, from one control.** Leaderboard,
  Records, Players, Games and the player profile all draw the same two pill rows
  (`components/GradeFilterPills.jsx`, shared with `SeasonSelector`) and send the
  same two params. The additive "Include" row is gone from all of them — it and
  Grade Type answer the same question, and `SeasonSelector` refuses to draw both.
- **The profile threads the scope into every Analysis panel, not just the
  header.** `_resolve_player_scope` gained `formats`, so dismissals, by-grade,
  by-position, by-venue, by-opposition, partnerships, bowling breakdowns and the
  season-by-season table all move together — a header that says T20 above a
  by-venue panel counting two-day games is worse than no filter.
- **`resolve_scope_for_player` never widens a FORMAT.** The junior auto-widen
  exists so a junior-only player doesn't open on zeroes; a player with no T20
  matches asking for T20 SHOULD see an empty page, because that is the answer.
  Gated on `scope.category_active`, not `scope.active`.
- **`api.js` has one `scopeQuery()` helper** for the ten player sub-endpoints,
  which previously each hand-built `?categories=`. Ten copies of a URL builder
  is how one of them ends up not sending the new param.
- **`GET /players/{id}/formats` (`services/player_formats.py`) is the
  per-format profile page** — two-day vs one-day vs T20 batting, bowling and
  fielding, rendered as a FORMATS sub-tab under the profile's Analysis tab
  (self-fetching and lazy, so a visitor reading the batting tab never pays for
  the query). Reads per-innings rows only, groups on the same
  `format_sql_case`, recomputes every average from its own column's counts
  (never an average of averages), and converts cricket-notation overs to balls
  before any economy. **A match we cannot place gets its own `not_recorded`
  bucket and a coverage line** rather than being folded into one of the three —
  a club whose history predates the `match_format` writer sees most of its games
  there until `backfill_match_format` has run, and the page says so.
  Deliberately takes no `categories` scope: slicing a career two ways at once
  buys nothing.
- **`get_club_summary` switches source under a scope**, the same trade the
  leaderboards and career totals already make: CA's season aggregates carry no
  grade (`v_effective_player_season_stats`'s `api` branch hardcodes NULL), so a
  filtered figure is only answerable from the per-innings scorecards.
- **The additive "Include" row and the pick-one "Grade Type" row are never
  shown together** (`showCategoryFilter && !showGradeTypeFilter`). They answer
  the same question two ways, and the dashboard briefly drew both. "All" on the
  Grade Type row means the club's own default, and the note under the bar says
  what that leaves out rather than dropping a club's juniors quietly.
- **Auto-suggestion is untouched and now covers both axes.** An unclassified
  grade still resolves on the fly, `POST /grades/apply-suggestions` still fills
  the blanks (category from the name, format from the grade's own games, and it
  refuses to guess a format it cannot tell), and the sync still persists a guess
  for a brand-new grade. **Every site that writes `category=suggest_category(...)`
  must ALSO write `categories=`** — sync ×2 and manual_entries ×2 — or a synced
  "Girls Under 16" lands as junior alone and loses its women's half, which is
  NARROWER than leaving both blank. Asserted structurally so a new write site
  can't skip it. `match_formats` is deliberately left NULL on creation: a new
  grade has no games yet, and leaving it unset keeps the derive-from-games step
  live so it self-corrects as they arrive.
- **`grades-with-stats` computes classification in its OWN query.** Unnesting
  the two array columns into the existing aggregate multiplies every batting row
  by the number of tags and silently inflates the RUNS column — written that way
  first, caught before it shipped, and asserted against.
- **Verified against a real Postgres** (191 checks: migration 259 applied three
  times to a populated pre-259 table and matching the lifespan mirror, the
  plural age-group spellings, both org resolvers' three-step fallbacks, every
  branch of the two axes composing, a senior-only club coming out inactive and
  emitting no clause, the scoped summary, and the route bodies incl. the
  runs-inflation guard, the `category` column staying in step, an empty list
  clearing back to the suggestion and apply-suggestions refusing to guess a
  format, plus the every-write-site-pairs-both-columns guard; and the
  per-fixture suite: the reported mixed grade splitting 180/60 rather than
  double-counting, an unlabelled game in a mixed grade landing in NO column, the
  Python/SQL format mappings agreeing on 18 real strings, an import residual
  contributing nothing to a format column while still counting under a category
  filter, every figure on the new profile page, and the picked-grade suite: a
  grade plus Two Day, a grade plus One Day, the two splitting back to the
  grade's own total, and the same across club records, the club summary and its
  game count, the games list and the results list — with a control asserting an
  explicitly picked junior grade still beats the CATEGORY filter) and
  **driven in Chromium** (50: the pills that render and the ones
  that no longer do, the exact params on the wire for all four dashboard
  fetches, the two filters composing, clearing one without the other, the
  Grades screen's chips and its PATCH, plus the profile's FORMATS tab — lazy
  fetch, all three columns, the strongest-format callout picking the LOWEST
  bowling average, the coverage line, and the same two rows on Leaderboard,
  Records, Players, Games and the profile with the exact params on the wire —
  no page errors, no overflow at 390px on any of them).
- **The harness builds its tables from the ORM models, not by hand, and that is
  load-bearing.** A hand-written test schema spelled `bowling_spells.runs` as
  `runs_conceded`, the new format-split service made the same mistake, and 51
  checks passed against the shared error. The real column is `runs` (runs
  conceded).

<!-- END original CLAUDE.md L7001-7212 -->
<!-- BEGIN original CLAUDE.md L8165-8225 -->
## AN IMPORT RESIDUAL IS CLASSIFIED BY ITS LABEL, NOT KEPT BLIND (v9.89.2, Sep 2026)

Reported off The Basin: Nathan Freeling, a senior player whose only record for
2006/07-2008/09 is a BetterImport residual under senior grade labels ("Division
3/4/5"), read **18 matches / 376 runs under the JUNIORS filter — and the same
under Women's and Masters**, on a player with no junior grades at all.

- **THE CATEGORY FILTER IS EXCLUSION-BASED AND AN IMPORT RESIDUAL HAS NO
  grade_id, SO IT SURVIVED EVERY PICK.** `GradeScope.clause`'s category branch is
  `column IS NULL OR NOT (column = ANY(excluded_ids))` — correct for the DEFAULT
  ("no juniors": a row we can't classify is probably senior, keep it) and wrong
  for an EXPLICIT pick. An import residual carries `grade_id = NULL`, so
  `grade_id IS NULL` is TRUE and it was kept under Juniors, Women's and Masters
  alike. Nathan's three seasons exist ONLY as residuals (CA's per-grade data
  starts 2009/10), so they were swept into every category. **This hit every
  BetterImport club with pre-CA seasons**, not just him.
- **THE RESIDUAL CARRIES A CLASSIFIABLE grade_label NOW, so it is no longer
  genuinely unclassifiable.** Migration 252 put `grade_label` on the import
  branch of `v_effective_player_season_stats`, and the team-labelled reconcile
  (v9.89.1) writes a real per-grade label. So the row IS classifiable — the
  filter was just looking at the NULL grade_id instead of the label.
- **`resolve_scope` BUILDS `excluded_labels` THE SAME WAY IT BUILDS
  `excluded_ids`.** One extra `SELECT DISTINCT grade_label FROM
  import_effective_deltas`, only when a category filter is active, each label
  classified with `categories_for_name` (its stored categories, else
  `suggest_categories`) and `judged = cats if explicit else {primary}` — the
  identical rule the grade walk applies. No per-row cost; empty for a club with
  no imports, so those queries are byte-for-byte what they were.
- **`clause(..., label_column=...)` IS A CASE, NOT A BLANKET KEEP.** grade_id
  present -> judged by grade_id (unchanged, a season adjustment still filters by
  its real grade); grade_label present -> judged by the label
  (`NOT (label = ANY(excluded_labels))`, cast to `text[]` so an empty list is
  safe); grade_label NULL -> KEPT, because a career-level lump with neither is
  genuinely unclassifiable, the one case the old reasoning still holds for.
- **THE FIVE RESIDUAL FILTER SITES ALL READ `pss` (the view with grade_label),
  so all move together**: `_career_residuals` (the profile cards + MATCHES
  stat), `_residual_totals_cte` (leaderboards), `_season_by_season_scoped` (the
  season table) and StatLab's family + career/season residuals. The by-grade
  grid is NOT one of them — it matches an import residual to a real grade row by
  NAME (`_IMPORT_GRADE_MATCH`) and filters on that grade's `gr.id`, so it already
  classified correctly.
- **THE DEFAULT IS UNTOUCHED, WHICH IS THE HALF THAT COULD HAVE BROKEN.** Under a
  club default that excludes junior, a senior label ("Division 3") is NOT in
  `excluded_labels` (its category is what's wanted), so the senior residual is
  still KEPT — a club's pre-CA senior seasons still show on the ordinary page.
  Only an explicit non-matching pick drops them.
- **No re-import, no migration** — it's a read-path scope change, so every
  affected club corrects on the next page load.
- **Verified against a real Postgres**
  (`backend/verification/verify_junior_residual_scope.py`, 24 checks through the
  shipped `resolve_scope` / `_career_residuals` / `_season_by_season_scoped` /
  `_residual_totals_cte` over the real view: the reported senior residual reading
  0 under Juniors/Women's/Masters and its full 18/376 under Men's and the
  junior-excluding club default, a genuine junior residual showing under Juniors
  only, a label-less career lump kept under every category, a real-grade_id
  residual still excluded by its id, the season table and leaderboard agreeing,
  and another club's identical residual untouched) **with a control run**: 10 of
  the 24 fail against the previous commit, reporting the customer's own **18/376**
  under Juniors and the same under Women's and Masters. The control reports rather
  than crashing — `excluded_labels` is read through `getattr`.

<!-- END original CLAUDE.md L8165-8225 -->
<!-- BEGIN original CLAUDE.md L8226-8315 -->
## Junior stats split off career stats (migration 228, v9.18.0, Aug 2026)

An Under-14 season was landing inside a senior career average. `grades.category`
(migration 123, Senior/Junior/Women's/Masters/Mixed) had existed since v8.x and
**nothing in the stats layer had ever read it** — it drove grouping and public
visibility only.

- **`services/grade_scope.py` is the one place a category selection becomes SQL**,
  and **it works by EXCLUSION, which is load-bearing**. The obvious shape is an
  include-list of senior grade ids; it is wrong twice. A manual game may have no
  `grade_id` at all (Grade is optional on Upload Scorecard) and a career-scope
  import residual has none either — an include-list drops both, an exclude-list
  keeps them, because **a row we cannot categorise is not a row we know to be
  junior**. And an empty exclusion set emits **no clause at all**, so a club with
  no junior grades runs byte-for-byte the queries it ran before. That is what
  makes a default that excludes junior safe to ship platform-wide. Every caller
  gates on `scope.active`, never on `scope is None`.
- **`clause()` is `col IS NULL OR NOT (col = ANY(...))`, not a bare `NOT`** —
  with a NULL `grade_id` the ANY comparison is NULL and `NOT NULL` is NULL, so a
  grade-less manual game would be silently dropped by a filter that has no
  opinion about it.
- **Categories resolve per grade NAME, in Python, never in the WHERE clause.** A
  category may be an unconfirmed `suggest_category` guess rather than a stored
  column (the 25/26 "Under 14s" row typically has `category` NULL), so it cannot
  go into SQL. Same approach the public lineups endpoint already takes.
- **CA's season aggregates carry no grade — `v_effective_player_season_stats`'s
  `api` branch hardcodes `grade_id NULL`.** So a scoped career total is only
  answerable from per-innings scorecards, and an active scope switches source.
  Same trade the leaderboards already make for a grade/finals/captain filter
  (`use_game_level` in records.py now includes `scope_active` for this reason).
- **The three aggregate-only residual branches must be added back, or a
  BetterImport club loses its history the moment the default filter applies.**
  `_RESIDUAL_SOURCES = (manual_aggregate, manual_career, import)` — the branches
  with no per-innings rows behind them. `api` and `manual_game` are excluded from
  that list because the per-game views already cover the same games; counting
  either alongside them doubles every figure. `_career_residuals` does this for
  one player, `_residual_totals_cte` for the leaderboards (the same shape as the
  existing `import_totals` CTE beside it). **Every blended average is recomputed
  from summed counts**, never averaged from two averages.
- **An explicitly picked grade beats the category default** (`if grade_id or
  grade_name: scope = None`). Someone choosing "Under 14s" from a dropdown means
  it; returning an empty board would read as broken.
- **Two things a scoped view genuinely cannot answer, and says so rather than
  guessing**: `fielding_stats` holds one run-out count and never splits assisted
  from unassisted (only CA's season aggregate does) → returned as **NULL, not 0**,
  because 0 reads as "never assisted a run-out"; and best bowling *figures* come
  from the per-spell rows only, since a residual branch knows the wicket count but
  its figures string belongs to a spell we hold no scorecard for.
- **`get_season_by_season` needed its own per-game variant** (`_season_by_season_scoped`),
  or the table would sum to a different number than the scoped header above it.
  It drops the "Prior Seasons & Adjustments" row — that lump is the NULL-season
  residual and belongs to no season, though it is still counted in the header.
- **`organisations.stats_grade_categories`** (migration 228, JSONB list, NULL =
  platform default) is the club's own default. An empty or all-junk selection
  **stores NULL rather than saving**, or a club would be looking at empty stats
  with no obvious way back. Edited from Club Settings → "Stats by grade"; Senior
  is shown but disabled, since it is the baseline the rest are added to.
- **Bug the verification caught**: the leaderboards' finals and captain branches
  built `scope_clause` but nothing bound its parameter, so those two combinations
  failed at execute time. Bound once right after each `params` dict is created.
  A clause built from a helper and interpolated into several branches needs its
  bind at the point every branch shares, not beside the interpolation.
- **Verified against a real Postgres** — 47 service-level + 18 route-level checks
  against the real 5-branch view stack (pulled straight out of migrations 038 /
  070 / 075 / 092 / 147 / 169 rather than retyped): the unconfirmed-junior guess,
  a senior-only club coming out inactive and byte-identical, import history
  surviving the filter, the season table reconciling with the header, an
  explicitly picked junior grade still returning its runs, finals composing with
  the filter, and migration 228 applied twice to a populated table.
- **A junior-only player must not open on a page of zeroes** (migration 229,
  `organisations.stats_auto_show_played_grades`, default TRUE).
  `resolve_scope_for_player` widens the scope to the categories a player has
  actually turned out in **when the default would leave them with nothing at
  all**, and returns `auto_shown` so the profile can say why its figures differ
  from the Leaderboard's. Three rules: it only ever applies to the DEFAULT (an
  explicit `categories=` is honoured even when it comes back empty, or the
  toggle would appear not to work); it is **profile-only**, never a club-wide
  board; and a career-level residual carries no grade, so it counts towards
  neither side of "has this player played in a counted category".
- **Bug found in the wild**: `get_settings` had no `db` dependency, so the two
  grade-category fields added to its response raised at request time and the
  Settings page sat on "Loading…" forever (`AdminSettings.jsx` swallows the
  error with `.catch(() => {})`). The route suite had exercised every OTHER new
  endpoint but never `get_settings` itself. **A handler missing a `Depends`
  compiles, imports and passes `py_compile` — only actually awaiting it fails.**
  It is called for real in the suite now.
- **Deliberately not touched**: BetterIQ (its own `iq_filters` grade vocabulary
  and a client-side "Seniors only" preset already), StatLab, Yearbooks, and the
  AFL silo (`services/afl/grade_labels.py` has its own category set —
  senior/colts/womens/masters/integrated — and would need its own pass).
<!-- END original CLAUDE.md L8226-8315 -->
<!-- BEGIN original CLAUDE.md L12666-12695 -->
## Awards — default templates (v8.28.0, Jun 2026)

Award catalogue lives in two tables (created in `main.py` lifespan, not Alembic):
`org_award_definitions` (the per-club catalogue that drives the dropdowns; clubs
rename via `display_name`, hide via `active`) and `player_achievements` (the
records). Templates are built in `backend/app/routers/award_definitions.py`:

- **`STARTER_TEMPLATE`** (`_build_starter_template`) — the **default for new
  clubs**, ~55 rows, club-agnostic: whole-club Season awards, a 1st/2nd/3rd XI
  block, generic `Premiership › Team`, the universal Milestone ladders, a
  `Committee` role list, Hall of Fame + Life Membership. No WASTCA/WABCC/PSWL,
  no OD/ICL/Colts ladder.
- **`GLOBAL_TEMPLATE`** (`_build_global_template`) — the old ~450-row
  comprehensive WA list. Kept as the opt-in **'comprehensive'** preset only.
- **`APPLECROSS_TEMPLATE`** — ACC's exact trophy names, matching their existing
  `player_achievements` values. Seeded for slug `applecross` on startup; not in
  the picker.
- `/award-definitions/seed?template=` reads the `TEMPLATES` map
  (`starter`|`comprehensive`|`global`(alias)|`applecross`); unknown → starter.
  Frontend auto-seeds **`starter`** on first visit to the definitions page when a
  club has zero defs, and the "Reset to Template" control offers Starter vs
  Comprehensive.

Seeding only fills an **empty** org (`seed_org_definitions` is a no-op if any def
exists), so Applecross and any already-seeded club are never touched. The
hardcoded `ACHIEVEMENT_TREE` in `frontend/src/lib/achievementOptions.js` (+ its
Python mirror in `routers/achievements.py`, used by the CSV import template) is
still the ACC-flavoured deep fallback shown only when an org has no defs at all —
a leaner import template is a possible follow-up, not done here.

<!-- END original CLAUDE.md L12666-12695 -->
<!-- BEGIN original CLAUDE.md L15772-16384 -->
## Stats by competition, and the association that runs a grade (migration 283, v9.60.0, Sep 2026)

Asked for off two PlayHQ screenshots: Applecross plays Summer 2025/26 across
THREE associations at once, and Hamilton Veterans field one side in several
competitions of the SAME association in one season. Neither could be
separated — the stats layer scoped to a season, a grade, a grade CATEGORY and
a match FORMAT, and to nothing about who ran the competition.

- **THE COMPETITION IS NOT IN THE GRASSROOTS FEED, AND ESTABLISHING THAT IS
  WHAT DECIDED THE WHOLE DESIGN.** Checked live before a line was written, not
  inferred: it is absent from `/fixturesladders/organisations/{org}/seasons`,
  from `/teams`, from `/fixturesladders/grades/{id}`, from
  `/scores/grades/{id}/matches` and from the full `/scores/matches/{id}`
  record; six plausible competition endpoints on the proxy all answer 403
  ("The API key you provided does not have access"), and PlayHQ's own
  `api.playhq.com/graphql`, where "Border Cup" lives, is CloudFront-403 from
  this environment — the thing this file already says never to hang a
  club-facing button on. **A CA season GUID is also GLOBAL, not per
  competition**: `Summer 2024/25` is `fc1465b6…` for Hamilton AND for Veterans
  Cricket Victoria, so the season list cannot carry it either.
- **THE ASSOCIATION IS EXACT, FREE, AND WAS ALREADY ON THE WIRE.**
  `grade.owningOrganisation` rides on the teams payload `sync` ALREADY fetches
  to seed its grades, and it was reading only `id` and `name` from it.
  Verified back to **Summer 1975/76**, so a club's whole history is reachable
  for ONE call per season. Applecross's 2025/26 resolves to WASTCA, the Perth
  Scorchers Women's League and the WA Integrated Cricket League with no
  guessing at all.
- **SO A COMPETITION IS THE CLUB'S OWN NAMED GROUP OF GRADES, SEEDED ONE PER
  ASSOCIATION.** The seed alone answers Applecross. It cannot answer Hamilton —
  Veterans Cricket Victoria runs the Border Cup, an Over 60s competition and
  the Echuca divisions, so the association is one bucket for three — which is
  exactly why a club-owned split has to exist and why association-only was
  rejected. `is_seeded` is cleared the moment a person edits a competition,
  which is what stops the next sync putting our naming back over theirs.
- **A GRADE BELONGS TO AT MOST ONE COMPETITION, and that is what makes this
  expressible at all.** A team plays several (Hamilton's Over 60 Men are in
  two in one season; Applecross's 7th XI plays One Day Grade 2 AND Grade 3),
  but each is a DIFFERENT grade row — so grouping by grade separates them with
  no per-game decision to make.
- **THE FILTER IS AN INCLUSION, WHERE THE CATEGORY AXIS IS AN EXCLUSION, and
  the asymmetry is deliberate.** A category filter has a club-wide DEFAULT, so
  it must be "leave these out" or a club with nothing to exclude would still
  get a clause. A competition filter is only ever asked for, so "show me only
  these" is what it means — which also settles the two cases an exclusion
  could not: a grade in NO competition drops out, and a career residual with
  no grade drops out, the same call the format axis makes. Counting an import
  residual towards a competition would invent a figure rather than filter one.
- **It rides on `GradeScope`, so adding it changed NO query** — all ~35 call
  sites already route through `clause()`/`bind()`, exactly as the format axis
  did in v9.26.0. It survives `formats_only()` for the same reason format
  does: it is never a default, so it can only be there because somebody asked.
- **EXPRESSED AS A SUBQUERY ON `grades.competition_id`, not a resolved list of
  grade ids.** An established club has hundreds of grade rows against a handful
  of competitions, so this binds 1-5 uuids and reads `ix_grades_competition`.
  **Measured at platform scale** (848 grade rows, 25,440 games, 76,320
  innings): a competition-filtered leaderboard is **53ms against the existing
  match-type filter's 292ms** on the same data — the subquery narrows the games
  by index before the per-innings unions are scanned, where the format CASE has
  to be evaluated per row.
- **IT FAILS CLOSED.** An id that is junk, not a uuid, or another club's is
  dropped in `resolve_scope` before it reaches SQL — and an all-junk selection
  is then an ACTIVE filter matching NOTHING, never an inactive one matching
  everything. Failing open on an id a browser got wrong would hand a club
  figures it never asked for, which is the worse direction (the same lesson
  v9.58.2's case-folding fix records).
- **THE COMPETITION HALF REACHES A GRADE-LESS MANUAL GAME AND THE OTHER TWO
  DELIBERATELY DO NOT.** `_fetch_manual_games_as_list` takes the scope now: a
  manual game with no grade is rightly KEPT by a category or format filter ("a
  row we cannot classify is not a row we know to be junior") and must DROP
  under a competition one, or a club filtering to the Border Cup finds an
  uploaded scorecard from another competition in the list. Resolving the scope
  had to move ABOVE the manual fetch in `list_games` for that.
- **A FILTER AND A BREAKDOWN ARE BOTH WANTED, AND THEY ARE DIFFERENT
  QUESTIONS.** `services/competition_stats.py` enumerates: the club's record
  per competition, every grade under its own competition (the TEAM half), and
  a player's batting/bowling/fielding/appearances per competition. Every
  average is recomputed from that competition's own counts, never an average
  of averages, and overs are converted to balls before anything is divided.
- **`unattributed` is on every player payload, and the screen says it out
  loud.** A competition figure comes from the scorecards, so a BetterImport
  career carries rows with no grade that belong to no competition — reported,
  never folded into one, and the panel explains why the rows do not add up to
  the career total.
- **The un-grouped bucket is SHOWN, never dropped** ("Other grades"), the same
  rule the `unattributed` column on the by-grade grid follows.
- **`services/competition_ddl.py` is the ONE copy alembic and the lifespan
  mirror both run**, per the `vote_medal_ddl` rule. **Numbered 283, not
  282**: the rate-qualification work landed on `main` as 282 while this was
  in flight, and two migrations sharing a revision id break Alembic
  outright — check `origin/main` before numbering one.
  `grades.competition_id` is **ON DELETE SET NULL**: deleting a competition
  un-groups its grades and never deletes a grade or a game, and the confirm
  says so rather than warning about a loss that cannot happen.
- **The filter row is NOT drawn for a club with fewer than two competitions** —
  a control that can only ever answer "everything" is worse than none, the same
  call `ageFilterOptions` and the Fees/Training notes make. Most of the
  platform therefore never sees it.
- **`python -m app.scripts.backfill_grade_associations <org|all> [--apply]`**
  fills in the history an incremental sync no longer scans — ONE call per
  season, not per grade. Dry-run by default. **Run against the live CA feed for
  both reported clubs**: Applecross 19 grades across its three associations,
  Hamilton 6 across its one, and an idempotent re-run writes nothing.
- **Verified against a real Postgres**
  (`backend/verification/verify_stats_by_competition.py`, 89 checks through the
  shipped services and route bodies: migration 282 applied three times to a
  populated pre-283 schema, the FK's referential action read out of
  `pg_constraint`, the association written by the shipped `_resolve_org_grade`
  on a new AND an existing grade and never erased by a blank, the seeding's
  skip-don't-replace at both levels, the reported Hamilton split, every figure
  of the club and player breakdowns, the filter on the leaderboard / games list
  / player profile, two competitions at once, an import residual counted
  unfiltered and in no competition, all four fail-closed cases, cross-club
  refusal from both sides, and every admin route body) **with a control run**
  reporting the feature absent, and **driven in Chromium**
  (`frontend/verification/verify_competitions_browser.mjs`, 41: the row on all
  five screens with the exact params on the wire, a single-competition club
  offered no row at all, the profile's lazy COMPETITIONS panel and its
  unattributed note, the Manage Grades panel's assign/rename/create/delete
  payloads, a dismissed delete sending nothing, no page errors, no overflow at
  390px) **with a control run**: 19 of the 41 fail against the previous commit.
- **A HARNESS TABLE THAT MERELY LOOKS RIGHT IS WORSE THAN NONE.** The suite's
  first `audit_logs` used `organisation_id` where the lifespan uses `org_id`;
  `audit_log` swallows its own failure, so the caller's transaction was left
  ABORTED and the competition it had just created silently vanished — three
  unrelated checks failed with no hint why. Copy the lifespan's DDL column for
  column.
- **Also caught by running it**: `games` has no `organisation_id` of its own
  (the effective view derives it), `manual_batting_innings` keys on
  `manual_game_id`, and a manual game cannot have a `game_appearances` row.
- **Two checks were measuring the harness rather than the code and had to be
  fixed**: the control club was used as the OPPOSITION on every fixture, which
  by the app's own `home_org_id`/`away_org_id` rule made all 15 genuinely its
  own; and a `document.querySelectorAll('div')` row locator matched an ancestor
  and drove the first `<select>` on the screen instead of the intended grade's.
- **NOTICED, NOT FIXED**: `get_player_team_breakdown` (the season x grade grid)
  is not grouped by competition — it is its own attribution pass with the
  `max(held, claimed)` reconciliation against CA's per-grade rows, and threading
  a third dimension through it is a bigger change than this. The grid's grades
  are already separated per competition by the FILTER, and the new
  Analysis -> Competitions panel answers the enumeration.
- **Not built**: nothing reads PlayHQ's own competition name, and nothing
  should until that API is reachable without a WAF in the way. The AFL silo is
  untouched — `services/afl/grade_labels.py` has its own vocabulary and would
  need its own pass.

### The club groups its own older seasons, and reads them back (v9.61.0)

Asked for straight after the filter shipped: a club admin should be able to run
`backfill_grade_associations` themselves when the app notices a competition has
been renamed or added, watch it happen, and come back later if they would
rather. Plus the club-level breakdown, which existed as an endpoint nothing
called.

- **THE GAP IS REAL AND NOTHING SAID SO.** A competition can only hold a grade
  Cricket Australia has told us the association for, and an incremental sync
  only scans the seasons that could still have been in play — so an established
  club's older seasons sit outside every competition it has just finished
  naming, showing under "Other grades" with no explanation. Nothing was wrong
  with those matches; they simply could not be found.
- **`services/competition_grouping.run_grouping` IS THE ONE IMPLEMENTATION, and
  the script now calls it rather than owning it.** Two copies of "fill in the
  associations and re-seed" is how the button and the command line start
  disagreeing about what grouping means. The script keeps its own reasons to
  exist: it takes `all`, it has a dry run, and it needs nobody logged in.
- **IT REUSES `sync_runs` UNDER A NEW KIND, `competition_grouping`, WHICH IS
  DELIBERATELY NOT ONE OF THE TWO THE PLATFORM RESUMES.** `_FULL_SYNC_KINDS`
  (`org_full`, `org_hard_refresh`) is an allowlist the Setup Wizard, All Clubs
  and `wizard_analytics` all read as "this club's history has been pulled", so
  a new kind can never be mistaken for it; and `main.py`'s restart self-heal
  only resumes those two, so a run cut off by a deploy is finalised as errored
  and started again rather than resumed behind an admin's back. That is right
  here precisely because the job is cheap and idempotent. **No migration** —
  progress rides in the run's own `stats` JSONB, which `update_sync_run`
  merges rather than replaces.
- **SAFE TO RUN TWICE, AND THAT IS WHAT LETS THE BUTTON CARRY NO WARNING.** Only
  a grade with NO association is written, an association CA omits never erases
  one we hold, and the seeder is skip-don't-replace — so a competition the club
  has renamed or split keeps its own naming and a second run over a finished
  club writes nothing at all.
- **ONE RUN PER CLUB.** Two would fetch the same seasons twice and race each
  other's writes for nothing, so `POST /admin/competitions/grouping` hands back
  the IN-FLIGHT run rather than starting a second — which is also what lets a
  screen reloading mid-job rejoin the same bar instead of launching another.
- **ONE SEASON'S UPSTREAM HICCUP IS NOT THE JOB.** That season is counted as
  failed and the rest of the club is still grouped, which beats an
  all-or-nothing pass a flaky upstream can stop halfway. The result says how
  many could not be read, so running it again later is an obvious next step
  rather than a mystery.
- **`needs_grouping` IS THE ONLY FIELD A SCREEN READS, and it is seasons the
  job can ACT on, never grades left un-grouped.** An admin may have deliberately
  left a grade out; a button that would write nothing is worse than no button.
  `grades_ungrouped` is reported beside it for context and is never the trigger.
- **DISMISSED, NEVER GONE.** "Not now" is a per-user, per-club localStorage flag
  read in the state initialiser (never an effect, or the prompt renders for one
  frame before snapping shut), and what it leaves behind is one quiet line
  still offering the job. `useDismissed` is a local four-line twin of the
  Clubhouse kit's `usePref` rather than an import, per the nets rule — that
  module is a different bundle and a remembered dismissal should not pull it
  into this page's first paint.
- **CLUB ADMIN AND SUPER ADMIN ARE ONE PATH, not two.** The endpoints carry
  `MANAGE_MERGES` — the capability Manage Grades already runs on, since
  grouping a grade is the same kind of act as merging one — and a super admin
  implies every capability, so acting as a club gives them the same button on
  the same screen with no super-admin-only surface to keep in step. The command
  line stays the operator's way in for the platform-wide sweep (`all`) and for
  a club nobody is logged in to. There is deliberately NO Better HQ screen for
  it: the club that has just named its competitions is the one who knows
  whether the older seasons matter, and a sweep run for them from outside would
  arrive with no explanation attached.
- **`--no-group` WAS A SILENT NO-OP** in the first cut of the refactor (a
  ternary whose branches were identical), so the flag is a real `group=False`
  parameter on `run_grouping` now: fill the associations in and stop, for an
  operator who does not want to touch a club's own naming. The button never
  passes it.
- **THE CLUB PAGE OPENS ON THE WHOLE HISTORY, not the newest season.** The
  question it answers is which competitions the club plays in, and a club that
  has moved between them has most of that answer outside the current year. It
  draws a season picker and NO grade picker — the page IS the grade breakdown,
  so a grade filter above it would be filtering the answer out.
- **`/{slug}/competitions` is a club section, so four lists had to learn it**:
  the Navbar's own `CLUB_SECTIONS` and `statsActive`, `SponsorFooter`'s copy and
  `FaviconManager`'s. None is a reserved ROOT segment question — the route is
  two segments deep — but a club page whose crest and sponsor footer go missing
  is the same class of bug the `/videos` note records.
- **Verified against a real Postgres** (the suite is 117 checks now: both team
  payload shapes and a grade with no owning organisation skipped, the gap and
  its `needs_grouping` trigger, the association and its short name stored,
  `group=False` leaving the competitions alone, grouping then placing the
  newly-filled grade, a second run writing nothing, a blank association not
  erasing one held, a failed season counted rather than raised, a dry run
  writing nothing, the two route bodies, one background task queued, a second
  press handed the same run, a screen rejoining it, and another club's run never
  picked up as this club's) **with a control run**: the grouping half reports
  itself missing against the previous commit while all 89 earlier checks still
  pass.
- **A `check` FOR `triggered_by_user_id` NEEDS A REAL `users` ROW.** `sync_runs`
  has a foreign key on it, so the stand-in object with an invented id every
  other route check in this suite uses cannot start a run.
- **Driven in Chromium** (the suite is 70 checks now: the prompt and the number
  it names, "Not now" and the quiet line it leaves, the dismissal surviving a
  reload and clearing bringing it back, the POST on the wire, the bar carrying
  a real percentage and MOVING between two reads, the season it is on, the
  result naming what it did, no prompt at all for a club with nothing to fetch,
  and the public page's competitions, records and grades at 1440 and 390 with a
  grade measured as sitting inside its own competition's card) **with a control
  run**: 23 of the 70 fail against the previous commit.
- **THE FINISHED JOB'S OWN RESULT WENT MISSING, AND ONLY THE BROWSER FOUND
  IT.** `CompetitionManager.load()` put the whole section back into its loading
  state on every refresh, so the panel's `onDone` unmounted the very component
  that was about to report. The spinner belongs to the FIRST load; a refresh
  after an edit swaps the data in place, which also stops every assign, rename
  and delete blanking the section on its way through.
- **A CONTROL RUN MUST REPORT, NOT CRASH.** The first cut clicked "Not now"
  unguarded, so the control run died on a missing button after two failures and
  said nothing about the other twenty-one. Every interaction in that block is
  behind a presence check now, and "the bar moved" treats a locator that finds
  nothing from the start as a failure rather than as an unchanged bar.

### Which of the forty queries the record book is waiting on (Sep 2026)

Reported off Hamilton Veterans' Records page with Competition set to All, and
asked as "do the new grade-to-competition linkages need more indexes".

- **THEY DO NOT, AND THE MEASUREMENT SAYS THE OPPOSITE.** With Competition set
  to All the frontend omits the param, `competition_active` is false and
  `competition_clause` returns an empty string, so the SQL is byte-for-byte
  what it was before migration 283 — which is also all that commit did to
  `records.py`, thread one parameter into `resolve_scope`. Timed against the
  live site: **unfiltered 15.0/15.1/15.7s, the same request narrowed to one
  competition 2.4/2.2s**, a season 2.7s, a match type 3.4s. A filter makes it
  six times FASTER, because the clause narrows the games through
  `ix_grades_competition` before the per-innings unions are scanned.
- **AND IT IS NOT THIS CLUB.** Applecross unfiltered is **16.6/16.8s** on the
  same measurement, so it is not Hamilton's imported history either. All-time
  records is slow for everybody.
- **ONE REQUEST RUNS ~40 AGGREGATIONS, EACH AWAITED IN TURN**, and the round
  trips are not the cost: a season filter cuts every one of them down and the
  whole thing drops under two seconds. The scans are the cost.
- **SO `q` TIMES EVERY QUERY AND NAMES IT AFTER THE BOARD IT BUILDS.**
  `_query_label` reads the caller's frame and scans BACK to the nearest
  `name = await q(` — a multi-line call reports its line differently across
  Python versions (the statement's first line before 3.11, the exact position
  after), so scanning back is what makes the label right either way. Zero edits
  at 40 call sites, and the label is what the board is called on the payload
  anyway. It costs **10.3us per query, 0.4ms for a whole request**, against the
  15,000ms being diagnosed.
- **`_timed` WRAPS THE READS THAT ARE NOT BOARDS**, or the report would not add
  up to the request: `resolve_scope` (which does its own reads for the club
  default categories, its grade formats and now its competitions),
  `resolve_season_filter`, the manual partnership records, the hidden-players
  check and the two `org_available_*` calls in the payload builder.
- **IT IS DECLARED WITH `timings`, ABOVE ITS FIRST USE.** The first cut put it
  where `q` is defined, three hundred lines below the `resolve_scope` call that
  uses it — the temporal-dead-zone trap the Roster note already documents. A
  closure defined further down the body does not exist yet when an earlier line
  runs.
- **THE BREAKDOWN IS SERVED ONLY TO A VIEWER WHO MAY ALREADY SEE THE CLUB'S
  PRIVATE DATA.** `?debug_timing=1` returns `_query_timings` (total, query
  time, the remainder that is Python, and every query slowest first) for the
  club's own admins and Better staff, reusing the `user_can_view_org_private`
  call the endpoint already makes for hidden players. Everyone else gets the
  ordinary payload with no extra key.
- **A SLOW REQUEST LOGS ITS WORST OFFENDERS; AN ORDINARY ONE LOGS NOTHING.**
  `SLOW_RECORDS_LOG_MS` (2000) is the gate — this is a public page, and a line
  per visit is how a log stops being read. That is also why the log exists
  alongside the payload: a signed-out visitor's slow load is the one nobody can
  ask for a breakdown of.
- **A SIGNED-OUT VISITOR PAYS FOR ONE QUERY AN ADMIN DOES NOT** — working out
  which players the club has hidden, which an admin may see anyway. Found by a
  check that compared the logged count against the payload's and disagreed by
  one; it asserts the asymmetry now rather than being loosened.
- **Verified against a real Postgres**
  (`backend/verification/verify_records_timing.py`, 35 checks through the
  SHIPPED route body: the ordinary payload unchanged and carrying no extra key,
  the breakdown withheld from a signed-out visitor and from a user with no
  membership here, every query named rather than reported as a line number, the
  six boards and three non-board reads named individually, slowest first, the
  parts summing to the total, the log firing once when slow and not at all when
  not, and a season-filtered request timed the same way) **with a control run**:
  it reports the instrumentation absent rather than 35 identical errors.
- **NOT DONE, and this only measures**: nothing is cached and nothing runs
  concurrently yet. The two obvious fixes once the log names the culprits are
  caching an unfiltered board on the club's last successful sync, and running
  the independent queries on their own sessions — an `AsyncSession` is not
  concurrency-safe, so `asyncio.gather` over the existing one is not the move.


### And what the timing said: a compiler and a platform-wide scan (Sep 2026)

The log came back flat — 28 queries, 13,287ms of query time, the eight slowest
between 900 and 1,027ms with nothing dominant. `EXPLAIN (ANALYZE, BUFFERS)` on
production (`ops/diagnostics/records_slow_board.sql`) named both halves, and
the hypothesis that led there was WRONG.

- **THE `unplayed` SUBQUERY IS 15ms, NOT THE PROBLEM.** It reads as the
  suspect — an uncorrelated derived table aggregating every abandoned fixture
  platform-wide, recomputed per reference — and it is genuinely cheap:
  `ix_games_status_not_played` narrows it to 488 games and the three anti-joins
  are index-only scans. **Measured before it was believed.**
- **HALF OF EVERY BOARD IS THE JIT COMPILER.** A board reading
  `v_effective_player_season_stats` plans at **cost 5,340,376**, past
  `jit_above_cost` (100k) and both `jit_optimize_above_cost` and
  `jit_inline_above_cost` (500k) — so Postgres compiles **177 functions in
  505ms** (238ms optimising, 210ms emitting) to run a query that then takes
  ~580ms. Fourteen references to that view is **~7s of the 13.3s spent
  compiling**. `get_records` now runs `SET LOCAL jit = off` FIRST: transaction
  -scoped, so no pooled connection carries it away, and there is nothing here
  JIT can win back — these are sub-second queries over a wide UNION view, not
  the minute-long scans it exists for.
- **THE OTHER HALF IS MIGRATION 060'S ORG SCOPING, RUN ONCE PER ROW OF THE
  PLATFORM.** Its `WHERE EXISTS (players JOIN seasons ...)` is planned as a
  correlated SubPlan, so the `api` branch is a **Seq Scan over all 315,288
  `player_season_stats` rows with the subplan executed 315,288 times** — 2.2
  MILLION buffer hits, 483ms — and the club filter is applied only afterwards,
  by a hash join to the 101 players who were wanted all along. The same board
  reading the base table instead of the view is **2.1ms**.
- **A VIEW IS WHERE A RULE BELONGS AND ALSO WHERE A PREDICATE GOES TO DIE.**
  Both halves are the price of one-place correctness: the 060 scoping and the
  266 washout correction both live in the view so every reader moves together,
  and both are therefore paid per reference, uncapped by the club being asked
  about. Keep the rule there; the fix is to give the planner something
  selective on the view's own `player_id` up front, not to scatter the rule.
- **`ops/diagnostics/records_pushdown_test.sql` tests exactly that** — the
  board as it is, against the same board with the club's players bound as an
  array, plus an EXCEPT both ways proving the two return identical rows, and
  the JIT cost measured by switching it back on. Not yet run.
- **`_query_timings` entries carry `n`**, where in the request each query ran,
  which is what makes "the JIT setting is issued FIRST" assertable rather than
  a check that cannot fail.


### Name the club's players, and the record book stops reading the platform (Sep 2026)

`EXPLAIN (ANALYZE)` on production, through
`ops/diagnostics/records_pushdown_test.sql`, on one board of the record book:

| | Execution |
|---|---|
| A. today: join `players`, filter the club, JIT off | **514ms** |
| B. `pss.player_id = ANY (SELECT id FROM players WHERE org = ...)` | **49,815ms** |
| C. `pss.player_id = ANY (ARRAY(SELECT ...))` | **0.877ms** |
| D. do A and C agree | 54 rows each, **0 differences either way** |
| E. A again with JIT back on | 769ms |

- **A BOUND ARRAY AND A SUBQUERY ARE NOT THE SAME THING, AND THE GAP IS
  57,000x.** `= ANY (SELECT ...)` is planned as a semi-join against the
  un-narrowed view — 49.8 SECONDS, ninety-seven times WORSE than doing nothing
  at all. `= ANY (array)` is a plain restriction on the view's own column,
  pushed into each UNION ALL branch, reading `idx_pss_player`. **Never "tidy"
  the array back into a subquery**; the comment above `pss_club_clause` says so
  where somebody would be tempted.
- **THE NEW CLAUSE IS LOGICALLY REDUNDANT, WHICH IS WHY IT IS SAFE.** Every
  board already joins `players p ON pss.player_id = p.id` and filters
  `p.organisation_id`, so `pss.player_id = ANY(the club's players)` cannot
  change a row — it only tells the planner something it could not work out for
  itself. D proves it empirically rather than by reading the SQL, and the suite
  seeds a rival club's bigger scorer and asserts he appears on no board of
  ours.
- **ONE CHEAP LOOKUP FEEDS ALL FOURTEEN.** `club_player_ids` is resolved once
  per request (an index-only scan of `uq_players_org_id`, 101 rows) and bound
  into every board.
- **CAST, BECAUSE A CLUB WITH NO PLAYERS BINDS AN EMPTY LIST** and asyncpg
  cannot infer an array's type from one — the same trap the vote-medals note
  records for a bare `:param IS NULL`. An empty array correctly matches
  nothing.
- **THE CLAUSE RIDES WITH `pss_gender_clause`, which appears at exactly the
  fourteen sites that read the view and nowhere else**, so threading it was one
  substitution rather than fourteen hand edits. The suite asserts it
  STRUCTURALLY — every `+ pss_gender_clause + ` must be preceded by
  `pss_club_clause` — so a board added later cannot quietly put the
  platform-wide scan back. Checked by breaking one on purpose: it reports
  "13 of 14".
- **Verified against a real Postgres** (the suite is 47 checks now: the club's
  players resolved once, its own top scorer leading its board, both its
  scorers still on it, a rival club's bigger scorer on no board, and a club
  with no players answering with empty boards rather than raising) **with a
  control run** reporting the instrumentation absent.
- **THE BOUND FORM SURVIVES PLAN CACHING, WHICH IS THE ONE THING THAT COULD
  HAVE UNDONE THIS.** asyncpg prepares its statements, and Postgres builds a
  custom plan for the first five executions before weighing a generic one — a
  generic plan that discarded the array's selectivity would put the seq scan
  straight back for every warmed-up connection, which is exactly the state a
  live pool is in. Section F of the diagnostic prepares the board with a bound
  `uuid[]` and runs it six times: **0.957, 0.602, 0.513, 0.654, 0.589, 1.070ms**.
  The sixth is the one that matters and it holds. No `plan_cache_mode` needed.
  An empty array (section G) is 0.017ms.


### A career has two match counts, and a filter switches between them (Sep 2026)

Reported off Rob Wilton's profile: **333 matches with Competition set to All,
337 with one competition picked**. A filter that INCREASES a total is
incoherent however it is explained.

- **NEITHER FIGURE IS WRONG. THEY ARE DIFFERENT SOURCES.** With no filter the
  header reads `SUM(player_season_stats.matches)`, Cricket Australia's own
  season totals. CA's aggregates carry no grade (the `api` branch of
  `v_effective_player_season_stats` hardcodes `grade_id` NULL), so they can say
  nothing about a competition, a grade type or a format — the moment any scope
  is active every figure is recomputed from the per-innings scorecards instead.
  `?categories=senior` gives the identical 337, so this predates competitions
  entirely and has been there since the grade-category filter (migration 228).
- **THE FOUR EXTRA GAMES ARE ALL REAL, and naming them is what stopped this
  being fixed the obvious way.** Every one is `source=api`, `status=COMPLETED`,
  with a real grade, date and opponent: a one-off appearance in a second grade
  that season (10th Grade, 9th Grade, One Day 4), an intra-club Applecross Red
  v Applecross Black fixture, and games with no result recorded. No manual
  upload, no duplicate, no other club's game. **1993/94 runs the other way** —
  CA counts 14 where we hold 13 — which is a genuinely missing scorecard.
- **SO THE OBVIOUS FIX WAS `max(held, claimed)`, THE RULE THE BY-GRADE GRID
  ALREADY USES, AND THE PLATFORM MEASUREMENT KILLED IT.**
  `ops/diagnostics/career_matches_sources.sql` over all 95,151 players:

  | | players | |
  |---|---|---|
  | the two sources agree | 38,795 | 41% |
  | we hold MORE than CA counts | 19,439 | 20%, worst **+221** |
  | CA claims MORE than we hold | 36,917 | 39%, worst **-484** |

  Adopting the higher figure would rewrite the headline career match count for
  **19,439 players**, one of them by 221 — a mass rewrite, not a correction.
  And it would do nothing for the 36,917 whose filtered view already DROPS,
  which is the LARGER half of the same problem: a club whose old seasons
  arrived as totals has few scorecards to filter, so any filter reads far
  lower. **The grid can apply `max(held, claimed)` because it compares per
  season AND grade against CA's own per-grade rows (`player_season_grade_stats`)
  and carries an `attributed_unknown` column for what it cannot place. The
  career header has neither.**
- **THE DUPLICATE HYPOTHESIS IS RULED OUT**: no manual upload duplicates a
  synced game on the same club, date and grade, anywhere on the platform (0
  rows). The extra held games are genuinely held.
- **SO THE NUMBERS MUST NOT MOVE. The page has to say which source it used**,
  the way `RateFootnote` marks a strike rate drawn from fewer innings than the
  figure beside it. Same rule as that one: only where the figure is short, and
  never on every number in the app.
- **Worth a look separately, NOT part of this**: Nairne's Sam Morgan reads CA
  127 against 348 held, and Sunrise's Jackey Patel CA **0** against 98 held. A
  player with a hundred games and no season aggregate at all is its own
  question.


### Say the two figures differ before anybody adds them up (v9.63.1)

Asked for directly after the diagnosis above: "the concept of ALL being one
number, then the sum of all matches display for each competition filter
tallying to a different number is confusing... tell the user about it
pre-emptively and explain why the numbers dont add up — don't allow the user to
discover that the numbers don't add up. That looks like a mistake."

- **NOTHING IS RENUMBERED, AND THE PLATFORM MEASUREMENT IS WHY.** The obvious
  fix is `max(held, claimed)`, the rule the by-grade grid already applies. It
  was measured before it was believed
  (`ops/diagnostics/career_matches_sources.sql`, all 95,151 players): the two
  sources agree for 41%, we hold MORE than CA counts for 20% (worst **+221**)
  and CA counts more for 39% (worst **-484**). Adopting the higher figure
  rewrites the headline career match count for **19,439 players** and does
  nothing for the 36,917 whose filtered view already reads LOWER, which is the
  larger half of the same problem. **The grid can do it because it compares per
  season AND grade against CA's own `player_season_grade_stats` and carries an
  `attributed_unknown` column for what it cannot place. The career header has
  neither.** So the figures stay and the page explains itself.
- **`services/match_coverage.py` READS BOTH FIGURES ITSELF, never the caller's
  current one, and that is the whole design.** With a filter on, the caller's
  figure has ALREADY switched to the scorecards — so a note derived from it
  compares them against themselves and draws nothing at exactly the moment
  somebody is looking at a moved number. The difference is a fact about the
  career, not about the view, so the note reads identically either way.
  Asserted, not assumed: the suite drives a genuinely active scope and compares
  the two payloads.
- **A GRADE-LESS GAME COUNTS AS HELD.** An uploaded scorecard with no grade
  belongs to no competition, but we DO have the match — filing it under "we
  hold no scorecard for this" blames the wrong thing and sends an admin looking
  for a game that is right there. The first cut inner-joined `grades` and got
  this wrong; season now comes from `v_effective_games.season_id`, the house
  rule migration 169 already set. That is what makes the panel's own arithmetic
  close: **rows + unattributed == breakdown_matches**, leaving only the career
  total to explain.
- **THE SURPLUS IS ITS OWN FIGURE, never a negative "missing" one.** `337 of
  333` is the shape of a bug, not an explanation, so `without_scorecard` and
  `extra_scorecards` are separate and every line of copy branches on which
  applies. Both directions are ordinary — 20% of players against 39% — so
  neither is the "normal" one.
- **THE NOTE DRAWS ONLY WHERE THE TWO GENUINELY DIFFER**, the rule
  `rate_coverage` already keeps: a note on every player is noise that teaches
  people to stop reading notes. The payload is presence-aware, so a career with
  nothing to explain keeps its exact shape.
- **A LAST-N-GAMES OR DATE WINDOW DRAWS NOTHING.** That headline is a slice of a
  career rather than the career, so comparing it against a career total would
  mean nothing.
- **THE COPY MAKES NO CAUSAL CLAIM IT CANNOT PROVE.** The first cut said a
  missing scorecard is "usually an older season the club's records never
  reached" — plausible, unverified, and quoted back at us the first time it is
  wrong. It says what the query actually establishes: we hold no game row for
  it at all, so there is nothing waiting to be filed.
- **THIS IS NOT THE COMPETITION FEATURE'S DOING.** `?categories=senior`
  reproduces it exactly, and that axis shipped with migration 228. Also ruled
  out empirically: Applecross (22 grades), Payneham (112) and Hamilton Veterans
  (4) each have ZERO grades outside a competition and their per-competition
  figures sum exactly, and no manual game duplicates a synced one anywhere on
  the platform (0 rows).
- **A NEW CLUB IS GROUPED THE MOMENT ITS FIRST SYNC LANDS**, not at 02:30.
  `_sync_safe` calls `maybe_group_club` on the SUCCESS path only — after
  `finish_sync_run` and above the pause/cancel and crash handlers, so a sync
  that did not complete never triggers it — and both onboarding paths (self-
  serve registration and a super admin's New Club) reach it through
  `_onboard_club_core`. A Full Rebuild does the same on its own true-success
  branch, since a rebuild rewrites every grade and that is when the
  associations are freshest. `maybe_group_club` owns the decision and settles,
  so calling it after every full sync costs nothing once a club is done. **The
  nightly job stays** — a club that played nothing in a period never reaches a
  sync at all, which is the entire reason that pass exists.
- **Verified against a real Postgres**
  (`backend/verification/verify_match_coverage.py`, 33 checks through the
  shipped service and route bodies: both directions, the grade-less boundary,
  the silence where the two agree, a season-total-only career, cross-club both
  ways, the season scope, the career figure the note quotes being the headline
  the page draws, the note surviving an active filter, and a last-N window
  drawing none; plus the competitions suite is 136 now, with the onboarding and
  rebuild hooks pinned structurally) **with control runs**: with the service
  absent the suite reports it rather than crashing; with the route left unwired
  5 of the 33 fail; with the two hooks neutered 4 of the 136 fail.
- **A CHECK THAT MATCHES THE WORD RATHER THAN THE CALL CANNOT FAIL.** Every
  hook site carries a comment naming `maybe_group_club`, so the first cut
  passed with the call itself renamed away. It matches
  `competition_grouping.maybe_group_club(` now, and the ordering checks return
  False for an absent part rather than raising, so a control run REPORTS them.
- **Driven in Chromium** (`verify_match_coverage_browser.mjs`, 22: the note on
  the UNFILTERED view, the headline read out of its own element, both
  directions' wording, the explainer opening and closing, nothing drawn where
  the two agree, and no overflow at 390px) **with a control run**: 10 of the 22
  fail against the previous commit.
- **`MATCHES212` HAS NO WORD BOUNDARY**, so `/\b212\b/` fails on a correct
  page; and the headline COUNTS UP, so reading it straight away catches
  `MATCHES187` mid-animation. The suite waits for the figure to stop moving and
  reads it out of its own `.pb-num`, never out of the tile's whole text — the
  note beside it quotes numbers too.
- **AND THE BY-GRADE GRID IS A THIRD NUMBER (v9.63.2).** Reported straight
  after: Applecross's Tristram Fletcher reads **309** on the career header,
  **313** in the note beside it, and **314** on Analysis -> Team. Three rules,
  three questions, none of them wrong:
  - **309** is `SUM(player_season_stats.matches)`, Cricket Australia's count of
    matches played, with no grade on it at all.
  - **313** is the matches we hold a game row for, which is what any filter
    counts from — grade-less uploads included.
  - **314** is `get_player_team_breakdown`'s own reconciliation: per season AND
    grade it takes `max(scorecards held, CA's per-grade figure)`, adds a
    season's unplaceable shortfall, and INNER JOINS `grades`, so it drops a
    grade-less game and adds a match CA credits to a grade we hold no scorecard
    for. The `5 *` on One Day Grade 1 is exactly that second half.
  **The grid's rule is the right one for a grade breakdown** — `max` is what
  keeps it self-healing when a shared fixture the other club synced first drops
  off the scorecard side — so the fix is again to SAY SO, not to renumber.
- **THE GRID'S NOTE IS SUMMED FROM ITS OWN ROWS, never asserted.** `held` is the
  rows' `scorecard_matches`, `added` is the sum of the asterisks, and the two
  plus `unattributed` equal the printed total, so a reader can check every part
  of it against the table above. A sentence merely claiming the total is "worked
  out differently" tells nobody anything. The grade-less line is
  `breakdown_matches - held`, which is the one figure that needs the header's
  own coverage block — both are season-scoped the same way
  (`resolve_season_filter(..., include_shared=True)`) and neither is
  grade-scoped, so they are comparable.
- **A GRID THAT ALREADY ADDS UP SAYS NOTHING**, the same rule as the header.
- **THE ASTERISK FOOTNOTE WAS WRONG AND IS CORRECTED IN PLACE.** It claimed the
  figure is "attributed to a grade only when the player played in a single grade
  that season" — true of the gap heuristic, and NOT of the `exact` branch, which
  sets `attributed_unknown` from `claimed > held` with no such condition. It now
  states what the mark means and confines the single-grade rule to the branch
  that actually applies it.
- **NOTICED, NOT FIXED**: the grid carries no grade-type, format or competition
  scope at all, so the Men's/Women's pills above it move the header and leave
  the grid alone. Right for "every grade this player has appeared in", wrong the
  moment somebody reads the two as the same question; it needs its own look.

<!-- END original CLAUDE.md L15772-16384 -->
<!-- BEGIN original CLAUDE.md L16385-16615 -->
## Which lens a panel is under, said on the panel (v9.64.0, Sep 2026)

Asked for after the three-number diagnosis above: "what should I do next so
that the user is always accurately and clearly informed about the different
lenses they are looking through at the data."

- **THE FILTER BAR IS PAGE-LEVEL AND ONLY REACHED ELEVEN OF EIGHTEEN PANELS.**
  It sits above the TAB bar, so every tab renders under it. Audited before
  building anything: `/stats`, dismissals, by-position, by-grade,
  bowling-by-grade, bowling-dismissals, bowling-by-batter-position, by-venue,
  by-opposition, seasons and partnerships take the scope; competitions,
  formats, team-breakdown, teammates, captain-stats, milestones and rankings do
  not. A club filtering to Men's on Batting found the women's grades back on
  Milestones one click later with nothing saying why.
- **THREE REASONS, NOT ONE, WHICH IS WHY A SINGLE DISCLAIMER WOULD BE WRONG.**
  `components/FilterReach.jsx` carries the vocabulary: `enumeration` (the panel
  IS the list of every value — filtering Competitions to one competition leaves
  a one-row table), `career` (a fact about a whole career), `unfiltered` (a gap,
  said out loud until it is closed). One list, so a panel added later has to
  declare itself rather than quietly inheriting a promise the bar cannot keep.
- **THE NOTE NAMES ONLY THE FILTERS ACTUALLY ON.** Mentioning Match type when
  nobody has touched it reads as a fault in a control they never used, so
  `activeFilterNames` reads `category_active` / `format_active` /
  `competition_active` off the scope the payload already returns. Nothing at
  all is drawn with every filter on All, which is most visits — the rule
  `rate_coverage` and the coverage note already keep.
- **MILESTONES ARE DELIBERATELY NEVER FILTERED.** "247 runs to 5,000" is a
  career fact and is what the notification bell reports; recomputing it under a
  Men's-only filter would give a number nobody can act on and would change what
  a club is told is coming up. Same for an honour — a Life Membership is not a
  men's honour or a T20 honour. Both now SAY it rather than being silently
  exempt.

### The grid answers to the bar now, and a match type is the exception

- **`get_player_team_breakdown` takes the scope, and the three halves of it
  reach different parts of the function.** The scorecard side is per-game and
  takes the whole scope (`clause("gr.id", game_alias="g")` — the category is
  expressed against the joined grade while the format is still read off each
  game's own `match_format`). CA's per-grade aggregate and the club's own
  per-grade corrections carry a GRADE, so a category or competition filter is
  answerable against them and a FORMAT is not: `kind='aggregate'` emits
  `AND FALSE`, the same call `GradeScope` already makes everywhere else.
- **THE SEASON-TOTAL GAP HEURISTIC IS SKIPPED ENTIRELY UNDER AN ACTIVE SCOPE**,
  and that half is load-bearing. `v_effective_player_season_stats` has no grade
  at all, so under a filter it counts matches the filter has just excluded —
  and the heuristic would hand that difference to an in-scope grade, inventing
  matches in it. Nothing to compare against is the honest answer.
- **The payload reports `scope: {active, aggregate_excluded}`**, so the screen
  can say the asterisked matches have gone and why, rather than leaving a
  shorter grid to read as data going missing. Presence-aware: an unfiltered
  request keeps the payload's exact shape.
- **The card's subtitle moves with it.** "Every grade this player has appeared
  in" stops being true the moment the bar narrows the table.

### A CLUB DEFAULT IS ALREADY A FILTER, and it broke the note one level down

- **Found by adding a junior grade to the verification fixture, not by reading
  the code.** `resolve_scope_for_player` applies the club's own default, so a
  club with a junior programme has `scope.active` TRUE with nobody having
  touched a control — and the headline is then neither career figure.
  v9.63.1's filtered copy read "Counted from the 313 matches we hold a
  scorecard for" beside a headline showing something else entirely, which is
  the exact class of mistake that note exists to prevent.
- **So the note never claims to be the headline.** Filtered, it names both
  sources instead: "Filtered figures are counted from the N matches we hold a
  scorecard for, not the M in Cricket Australia's season totals." True whatever
  the figure above it happens to read.
- **`GradeTotalNote` is scope-aware for the same reason.** Its grade-less line
  is `breakdown_matches - held`, and `breakdown_matches` is deliberately
  scope-INDEPENDENT — so subtracting a FILTERED `held` from it would report
  every match the filter just excluded as one with no grade, the opposite of
  true. Suppressed while the grid is scoped.
- **Verified against a real Postgres**
  (`backend/verification/verify_match_coverage.py` is 46 checks now: the junior
  grade in and out of the grid, the club default excluding it, an explicitly
  all-category request reading as no scope at all, the aggregate dropped under
  a match type and kept under a category one, the grid under a format filter
  holding nothing it does not have a scorecard for, and the club default moving
  the headline off both career figures) **with a control run**: with
  `scope_active` forced false, 6 of the 46 fail.
- **Driven in Chromium** (`verify_match_coverage_browser.mjs`, 44: each reach
  note in its own words, the note naming only the active filters, nothing drawn
  with every filter on All, the Milestones line, and the club-default case
  where the headline is neither career number) **with a control run**: with
  `FilterReachNote` stubbed to null, 5 fail.
- **NOTICED, NOT FIXED**: `teammates` and `captain-stats` still do not take the
  scope — they now SAY so rather than being silently unfiltered, which was the
  point, but closing them is its own change. Club rankings are unfiltered too
  and are arguably a career fact like a milestone; that needs a decision rather
  than a pass.

### The review, and what it changed (v9.64.1)

Asked to review 1, 2 and 3 above honestly. Two of the design calls were wrong,
and one had been pushed to `main` without being measured.

- **THE BLANKET SKIP DROPPED REAL MATCHES ON THE DEFAULT VIEW, and the control
  run reproduces it exactly.** v9.64.0 skipped the season-total gap heuristic
  under ANY active scope. A club with a junior programme has the club default
  active on every visit, so every senior player there whose older seasons
  predate CA's per-grade data had their grid total drop with nobody touching a
  control — in the suite, a senior-only player read `matches: 5,
  attributed_unknown: 0` where the unfiltered read gives `9` and `4`. **Gated
  per season now, not switched off**: an unscoped per-season count is compared
  against the scoped one, a season where they differ is `mixed` and its gap is
  not this filter's to place, and a season where they agree is one the total
  describes exactly, so the heuristic runs as ever. The payload reports
  `seasons_left_to_scorecards` and the grid says it. The suite asserts a
  senior-only player's grid is BYTE-IDENTICAL under the club default and with
  no scope at all, which is the property the first cut broke.
- **THE REACH NOTES FIRE ON WHAT WAS PICKED, NEVER ON THE CLUB DEFAULT.** Six
  tabs carrying "the filter above does not apply here" on every visit to a
  junior-programme club, about a filter nobody turned on, is the "a note on
  everything teaches people to stop reading notes" rule broken behind a
  condition that is true by default for a large share of clubs. `FilterReach`
  takes the RAW selection (`catParam`/`fmtParam`/`compParam`, null where
  untouched), not the resolved scope — the frontend already knew the
  difference. The default is announced once, by the header, and once is enough.
- **A MARK ON THE TAB LABEL SAYS IT BEFORE THE TAB IS OPENED.**
  `FilterReachDot` on Competitions, Formats, Milestones and Honours, drawn only
  while something is picked. `presskit.TabBar` already accepts a node as a
  label, so the main bar needed no change.
- **TEAMMATES AND CAPTAIN ARE CLOSED, NOT DECLARED.** Both are per-game reads.
  `iq_teammates` has one "our games" universe CTE and every read is built on
  it, so `_og_cte(scope)` narrows the list and the with/without split
  together; every captain query joins `v_effective_games g` and interpolates
  one `club` string, so the scope rides on that string rather than being
  pasted into six places.
- **Found while closing it**: the season table was sent the category and
  format halves and never the competition — same class of gap as the grid.
- **Verified against a real Postgres** (`verify_match_coverage.py` is 59
  checks now: the senior-only player byte-identical under the club default, a
  mixed player's senior-only season still placing its gap while his mixed
  season is left to the scorecards, the count reported, the two totals
  differing by exactly the junior scorecards plus the unplaceable gap, and the
  teammate and captaincy counts each dropping the shared junior game under
  Men's) **with two control runs**: the blanket skip this replaces fails 7, and
  the two new scopes neutered fail 2. **Driven in Chromium** (49: nothing
  marked or noted under the club default, the pick made by pressing the real
  Juniors pill, the dots on both bars before the tabs are opened, each note
  naming Grade type and NOT Match type, Teammates carrying no note and the pick
  on the wire to it, and the grid's per-season line) **with a control run**:
  the notes and dots stubbed to null fail 5 and leave the silence checks green.
- **THE FILTER ROW IS GATED ON THE CLUB HAVING A SEASON**, so a stub that
  answers `[]` for `/organisations/{id}/seasons` renders no pill to press and
  every pick-driven check fails with the pick never made. Found by probing the
  rendered buttons, not by reading the harness.
- **NOTICED, NOT FIXED**: club rankings are still unfiltered and carry no
  note. They are arguably a career fact like a milestone, and that is a
  decision rather than a pass.

### Hamilton's second ask was unmet in the panel built for the first (v9.64.2)

Asked to review whether the competition layer satisfied Hamilton Veterans'
request — "batting strike rates and bowling economy rates will be handy ...
however balls faced counting did not commence until specific competitions from
2013 onwards" — and it did not, at the one place he would look.

- **`competition_stats.player_competition_breakdown` DIVIDED `SUM(runs)` BY
  `SUM(balls)` ACROSS EVERY INNINGS IN THE COMPETITION.** That is the exact
  shape migration 282 removed from every other rate in the app (`rate_coverage`,
  v9.59.0), and this query shipped as 283 — one migration later — without it.
  For a competition with pre-2013 innings every run lands in the numerator and
  only the typed-in balls in the denominator: the suite's four-innings case
  reads 125.00 where 75.00 is right, and the control run reproduces the 125.
  Economy had the milder version of the same thing through a spell with no
  overs recorded.
- **Fixed with the module that already existed**: `rc.batting_rate_columns`
  and `rc.bowling_rate_columns` ride alongside the plain sums, the rate is
  `rc.strike_rate(covered_runs, covered_balls)`, and `strike_rate_coverage` /
  `economy_coverage` ride on the payload. Runs, innings and wickets are still
  the whole competition's — only the ratio changes source, per the 282 rule.
- **`FormatCompareTable` already took a `coverage` accessor per row** and drew
  the dagger and footnote itself, so the panel needed two row definitions
  changed and nothing else. The Formats page had been doing this since 282;
  the Competitions page beside it had not.
- **A CHECK FOR A RATE NEEDS AN INNINGS THE RATE CANNOT USE.** The competition
  suite's fixture wrote `balls = runs + 10` for every innings, so every rate in
  it was fully covered and the bug could never have shown. The new case carries
  an un-balled innings with runs (the sync's stored zero), a genuine 0 off 0
  (covered — it contributes nothing to either half) and a spell with no overs.
- **Verified against a real Postgres** (`verify_match_coverage.py` is 66
  checks: 75.00 from 3 of 4, the 0(0) counted as covered, economy 4.00 from 2
  of 3, runs and wickets still whole) **with a control run** that reads 125.0
  and 5.0; the competitions suite unchanged at 136. **Driven in Chromium**
  (`verify_competitions_browser.mjs`): the partially-covered rate carries the
  dagger, the complete one beside it does not, and the footnote under the
  table says why.

### The order of the competition pills is the club's to set (v9.65.0)

Reported: the pills on a club's public stats pages come out in whatever order
the sync first met the competitions, and a club fielding sides in several
should be able to lead with the one that matters.

- **NOTHING NEW ON THE BACKEND, and checking that first is what kept this
  small.** `club_competitions.display_order` has existed since migration 283,
  `competitions.reorder_competitions` stamps it by position,
  `POST /admin/competitions/reorder` is routed and `api.adminReorderCompetitions`
  was already written. `list_competitions` sorts on it and
  `org_available_competitions` is that list filtered, so every pill row and both
  breakdown surfaces already read the order — nobody could set it.
- **A SWAP SENDS THE WHOLE LIST, not the moved pair.** The server stamps
  positions over every id it is given, so a partial list would renumber two
  rows against stale neighbours; sending all of them is also what makes a
  foreign or stale id skippable without leaving a gap, the rule
  `reorder_plan_tree` and `reorder_agenda_items` already follow.
- **Arrows, not drag.** Two to five cards in a vertical list, on a screen an
  admin visits once. `dragOrder.js` exists for the nets batting order because
  that is run from an iPad mid-session; this is not that.
- **`MANAGE GRADES` IS NOW `GRADES & COMPETITIONS`**, in the sidebar and as the
  page's own heading. The screen has owned competitions since 9.60 and the name
  said nothing about it; a club admin looking for where to manage them had no
  reason to open it. Display only — the route, the capability and every stored
  row are untouched, the same call the BetterAdmin rename made.
- **`/admin/grades#competitions` scrolls to the panel**, so a guide or a link
  can land on it rather than the top of a long page. Gated on the data having
  loaded, or there is nothing to scroll to yet.
- **Driven in Chromium** (the suite is 78 now: the control on every card, the
  whole list on the wire in its new order, the cards actually moving, the first
  and last ends disabled, the sentence saying the order drives the public
  filter, and the page named for competitions) **with a control run**: with the
  arrows removed, 4 fail.
- **A CHECK THAT COMPARES THE PAYLOAD AGAINST THE STUB'S OWN STATE CANNOT
  FAIL.** The first cut asserted the sent ids differed from `comps`, which the
  stub had already reordered — so it compared the payload with itself. It
  captures the order BEFORE the click now and asserts the two swapped ends.
  The stub also has to APPLY the reorder, or "the list actually moves" is
  measuring a redraw.

<!-- END original CLAUDE.md L16385-16615 -->

## Records counted matches batted; the scorecard never drew its catches (v9.100.3, Sep 2026)

Reported by Shoalwater Bay off two screens: no catches on a 1992-93 B Grade scorecard, and R Spinks on Records at 7,045 runs, 435 matches, 438 innings against 465 matches on his profile.

- **Neither Records figure was wrong; they were different questions.** With a grade-type default active (any club with a junior grade) the Records career boards take their game-level branch, whose `matches` was `COUNT(DISTINCT bi.game_id)` over the board's own batting rows: matches he batted in. The profile, the Leaderboard (v9.62.2) and Most Matches count matches played. The unfiltered branch reads `SUM(pss.matches)`, also matches played, so the column changed meaning with the filter.
- **`records._appearances_sql` is now the one definition** of "in the game" (batting row incl. did-not-bat, spell, fielding row, roster appearance), used by Most Matches and by a single per-club `matches_played_rows` query applied to seven boards after they run. One extra query, not one per board, and a board's own count is kept as a floor so it can only raise a low figure. Captain-only is excluded on purpose: "matches as captain" is what that view means. Innings is untouched, so matches can sit either side of it (two-day matches give two innings).
- **A note was considered and rejected.** Detecting "played differs from batted" needs the same per-player union as showing the right figure, and would fire on nearly every row (anyone who ever bowled without batting).
- **Verified against a real Postgres** (`backend/verification/verify_records_matches_played.py`, 27 checks through the shipped `get_records` and `get_scorecard`: Spinks in miniature with games batted, bowled-only, fielded-only, named-only and DNB-row on the synced and manual tables, every board agreeing, the control who always bats unmoved, a named grade, captain-only left alone, an all-category request reading the view untouched) **with a control run**: 11 fail on the previous commit, reporting 6 matches where 11 were played. Neighbours: records timing 47, rate coverage 105, shared fixtures 38, season fold 65, scorebook innings 47.
- **`ops/diagnostics/player_matches_split.sql`** splits one player's matches played into batted / bowled only / fielded only / named only on the live database. NOT run against Shoalwater's data (the session that built this had no database access): the 30-match gap is the explanation the code gives and the fixture reproduces, not a measurement. Run it for Spinks to confirm.
- **Noticed, not fixed:** the CSFW converter stores keeper catches in `catches_wk` with `catches` blank (582 of 584 keeper rows in Shoalwater's 1992-2008 file) where the app treats `catches` as the total including keeper catches (`catches_non_wk = GREATEST(catches - catches_wk, 0)`). A keeper's headline catch total is understated and his outfield figure floors at 0. The converter should send `catches + wk_catches` and the archive be re-imported; that is a decision for the club.
