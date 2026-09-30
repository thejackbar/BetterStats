# Archive: cross-club-and-data-safety

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: Shared fixtures, shared participant GUIDs, cross-club leaks, never deleting manual data, club delete.
Read the distilled rules first: `docs/dev-notes/guides/cross-club-and-data-safety.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L1771-1826 -->
## NEVER DELETE OR OVERWRITE WHAT A CLUB TYPED IN BY HAND (v9.68.2, Sep 2026)

**Set as a standing rule, after a merge deleted half a player's career.** A
club entering a season of scorecards spends hours on it, and unlike a synced
game there is **no upstream to re-pull it from** — a deleted manual row is
gone. So:

> **A manual game, its innings, and a hand-typed correction are the club's own
> work. A function may ADD to them and it may MOVE them; it may only remove or
> replace what it wrote ITSELF, and never what a person wrote.**

Where this has already gone wrong, and what each case teaches:

- **A MERGE MOVES A RECORD; IT NEVER DELETES ONE.** `_merge_players_core` was
  written for the SYNCED per-game tables and reached no `manual_*` table at
  all — and every one of them is `ON DELETE CASCADE` on `players.id`, so
  removing the merged-away player destroyed their whole hand-entered and
  imported career. `services/merge_carry.CARRIED` is the list it now carries;
  **a table that records what a player DID belongs on it.** See the v9.68.1
  note.
- **AN IMPORT REPLACES WHAT THAT IMPORT WROTE, AND STOPS AT ANYTHING A PERSON
  HAS TOUCHED.** `cricketstatz_import.import_match` refreshes a match it
  created, matched on `cricketstatz_match_id`, so it can never reach a game
  somebody typed in. On top of that, `hand_edited_games` reads
  `manual_edit_logs` — which the import writes none of, so any un-undone row
  means a person edited that match through Manual Entries — and the import
  **skips it and says so** rather than reverting their correction silently. An
  edit that was later undone does not count: the club took it back.
- **A FULL REBUILD DELETES FROM `games`, NEVER `manual_games`**, and it must
  stay that way. It exists to re-pull from Cricket Australia; a manual game has
  nothing to re-pull.
- **SEASON AND GRADE DELETES ALREADY REFUSE** while a manual game or a manual
  adjustment points at them (`_season_in_use` / `_grade_in_use`). Both FKs
  cascade, so those two checks are the only thing between a tidy-up and a lost
  season.
- **DE-DUPLICATING IS NOT DELETING, and the line is that the two rows describe
  ONE thing.** A merge drops the removed record's row for an innings the keeper
  already holds, because they are the same innings read under two identities.
  It must never drop an innings only one of them had — the suite asserts the
  total row count falls by exactly the number of genuine duplicates.

**THE RULE IS ENFORCED, NOT JUST WRITTEN DOWN.**
`backend/verification/verify_merge_carry.py` scans `app/` for every `DELETE
FROM manual_*` and `sa_delete(Manual*)` and fails on any site not on its
`ALLOWED_DELETES` list with a stated reason — so a new one cannot be added
without somebody justifying it — and separately asserts every manual table
carrying a `players.id` foreign key is on the merge's carry list. Both were
checked by breaking them on purpose: an unjustified delete elsewhere in `app/`
fails the first, and dropping one table off `CARRIED` fails the second.

**When a club HAS lost rows this way, say what recovers them.** A CricketStatz
import re-writes the same matches (deterministic `cricketstatz_match_id`, and
`import_match` upserts), so re-running it is the recovery — onto the one record
that was kept. A club's hand-typed history has no such path, which is the whole
reason for the rule.

<!-- END original CLAUDE.md L1771-1826 -->
<!-- BEGIN original CLAUDE.md L2996-3111 -->
## A FIXTURE BELONGS TO BOTH CLUBS. Read it that way, every time (v9.62.0, Sep 2026)

**THIS HAS NOW BEEN REPORTED FOUR TIMES** — the second club's Games list
(migration 167), a player's own club as their opposition (167), a season table
drawn two and three times over (v9.53.10), a career counting another club's
matches (v9.53.12), and now Shoalwater Bay. Every one is the same sentence
written a different way, so it is written here once, at the top, as a rule:

> **A CA match between two clubs that both sync BetterCricket is a SINGLE
> `games` row. Its `grade_id` — and so its `season_id` — points at whichever
> club synced it FIRST. That club does not own the fixture. Both sides played
> it, both sides' scorecards hang off it, and both sides' statistics have to
> count it and classify it.**

**NEVER decide "is this game ours" with `seasons.organisation_id`, and never
decide "what kind of grade is this" from a `grades` row your own club owns.**
Both are the same mistake at two ends of the query.

- **Ownership is `services/club_grades.club_game_sql`** — the game's own club is
  us (`v_effective_games.organisation_id`, migration 169) **or we are one of the
  two sides** (`home_org_id`/`away_org_id`, migration 167, both indexed).
  `aggregations._OURS_GAMES` and `records._OURS_GAMES` are that one string;
  `_club_game_clause` is the player-scoped sibling. A per-game read guarded by
  `players.organisation_id` and this predicate is correct; one guarded by the
  season's org is not.
- **Classification is `services/club_grades.club_grade_rows`**, which enumerates
  the club's own grades PLUS every grade row its own games sit in, and resolves
  each to the club's own answer by NAME (folded through `grade_merge_logs`).
- **A season filter needs `resolve_season_filter(..., include_shared=True)`**,
  which reaches the other club's row for the same real season: the CA season
  GUID both rows carry first (a CA season id is global, not per club — the key
  `iq_filters.season_ids_cross_club` already matched on), then the year, then
  the name for a row that has neither. **Opt-in, and that matters**: a query
  whose only club guard is the season list (a grade listing, a season dropdown)
  would otherwise reach another club's rows. Pass it only where the read is
  ALSO guarded by the club's own players or by the ownership predicate above.

### What Shoalwater Bay reported, and why it read as two unrelated bugs

Darren Hind's Players-list row said **106 matches**, his own profile said
**150**, and asking that profile for **Juniors** returned **28 senior Peel
Cricket Association matches** — the same matches the Men's filter returned.

- **THE CATEGORY FILTER IS AN EXCLUSION, SO A GRADE IT CANNOT NAME IS KEPT.**
  That is deliberate and still right (a manual game with no grade, or an import
  residual, is not a row we know to be junior). But `resolve_scope` built its
  exclusion list from `grades JOIN seasons WHERE s.organisation_id = us`, so
  the other club's grade row was never in the list and could not be excluded by
  anything. The fixture therefore passed Men's AND Juniors AND every other
  category at once. **An exclusion-based filter is only as good as its
  enumeration** — widen the enumeration, never relax the exclusion.
- **THE SAME FIXTURE WAS BEING DROPPED ELSEWHERE, WHICH IS WHY THE TWO SCREENS
  DISAGREED.** The leaderboards, the SIRS boards and the record boards all
  scoped `s.organisation_id = :org_id`, so the 21 innings the profile counted
  never reached the Players list. 127 − 21 = 106, exactly.
- **AND THE SEASON FILTER DROPPED THEM A THIRD TIME.** `resolve_season_filter`
  expanded a year to sibling rows **of the same club only**, so picking 2025/26
  lost the very matches the all-time figure counted.
- **150 IS THE RIGHT ANSWER OF THE TWO.** Shoalwater played those matches. The
  fix brings the boards up to the profile, never the profile down to the boards.
- **THE COMPETITION PANEL READ THE FOREIGN GRADE'S OWN `competition_id`**, which
  is NULL until the other club groups its grades and is THEIR competition after
  that. So 122 sat under Peel and 28 under "Other grades", and a club that had
  grouped its own grades would have had another club's competition name
  labelling its figures. `club_grade_competitions` resolves it to ours instead.
- **THE ASSOCIATION FALLBACK IS ONLY FOR A NAME WE HAVE NEVER HELD.** The first
  cut matched any ungrouped foreign grade to our competition running the same
  association, and the verification caught it: our own ungrouped "Under 14s" sat
  in "Other grades" while THEIR identically-named row was swept into Peel. A
  grade we hold under that name gets the answer we gave it, ungrouped included.
- **A MERGED-AWAY SPELLING MUST READ AS THE GRADE THAT WAS KEPT.** A shared
  fixture is exactly where CA's older name turns up, and the club has usually
  merged that name away. `_apply_alias_fold` registers the canonical's confirmed
  answer under the alias key in all three of `grade_labels`' name maps, so
  "F Grade Colts Cup" reads as the senior "F Grade" it was merged into rather
  than as the juniors its own name suggests.
- **StatLab's `game_universe` was one line** (`WHERE s.organisation_id`), and
  every per-player read below it is separately guarded by `p.organisation_id`,
  so widening the game universe there cannot reach another club's players.
  BetterIQ's team analysis was ALREADY cross-club aware (`_ours_clause`,
  `season_ids_cross_club`) and needed nothing.
- **Verified against a real Postgres**
  (`backend/verification/verify_shared_fixture_stats.py`, 31 checks through the
  shipped services and route bodies: the reported case replayed, the Juniors
  filter returning only real junior matches, the Players list and the profile
  agreeing, batting/bowling/fielding boards all counting the shared fixtures,
  the club that DID sync the fixture unchanged and its own player never leaking
  onto our board, a match we were not in still not ours, the season filter
  reaching the other club's row on the CA season GUID and on the year, their
  junior grade still excluded while their senior one is not, the merged
  spelling read as ours, the format axis on a grade we do not own, the
  competition panel filing every shared fixture under our own competition while
  an ungrouped grade stays ungrouped, and the filtered senior and junior runs
  adding back up to CA's own season total) **with a control run**: 22 of the 31
  fail against the previous commit, the Juniors filter returning 126 runs of
  senior cricket and the boards reading 3 where the profile reads 7.
- **Measured at platform scale** (25,000 games, 1,260 grades, 75,000 innings):
  `resolve_scope` 3.5 → 7.5ms, the scoped batting leaderboard 132 → 160ms. The
  leaderboard's extra 28ms is **the 11% more innings it now correctly counts**,
  not the predicate: the same query with only the WHERE swapped is 36.2 → 38.1ms
  and returns 75,000 rows against 67,500. Writing the ownership test as
  `s.organisation_id OR the two sides` measured SLOWER (42.1ms), so the plain
  form stands.
- **A CHECK THAT PASSES AGAINST THE BROKEN CODE IS NOT A CHECK.** The first cut
  of "their older spelling reads as our merged grade's category" used a name
  that suggests senior anyway, so an unclassified grade falling through passed
  it. It is a junior-suggesting name now, and its sibling asserts the Juniors
  filter does not claim it either — that pair fails both ways.
- **NOTICED, NOT FIXED**: the same `seasons.organisation_id` shape still appears
  in the yearbook generator, the fantasy engine and several admin tools. None is
  a club-facing stats figure, and each needs its own look. The repeatable audit:
  extract every triple-quoted SQL block, keep those with a per-game table after
  `FROM`/`JOIN`, and flag any that tests a seasons alias' `organisation_id`
  without also naming `home_org_id`. It reported 89 blocks; this change covers
  the club-facing stats reads.

<!-- END original CLAUDE.md L2996-3111 -->
<!-- BEGIN original CLAUDE.md L3428-3893 -->
## A player's seasons drawn two and three times over (v9.53.10, Aug 2026)

Reported off a live profile: Cameron Sawatzky's season table read "2025/26"
twice, "2022/23" three times and "2020/21" three times, each row holding a
slice of the real season.

- **NOTHING WAS DOUBLE-COUNTED, and establishing that first is what stopped
  this being fixed the wrong way.** The 26 rows summed EXACTLY to the career
  header above them (125 matches, 117 innings, 1,367 runs), and no two sibling
  rows carried the same figures. The data was right; it was filed under several
  headings.
- **A FIXTURE BETWEEN TWO SYNCED CLUBS IS ONE `games` ROW, AND ITS SEASON
  BELONGS TO WHICHEVER CLUB SYNCED IT FIRST.** A game's season is read through
  its grade, a grade belongs to one season, and each club mints its own per-club
  grade and season rows — so a Gosnells fixture that Willetton happened to sync
  first carries WILLETTON's "Summer 2025/26". `_season_by_season_scoped` grouped
  on that raw season id **with no club scoping anywhere in it**, so those
  matches drew a second, identically-named row beside the club's own.
- **PROVED AGAINST CRICKET AUSTRALIA, NOT INFERRED.** Season ids are
  `uuid5(org, ca_season_guid)`, so each row can be attributed by recomputing it:
  every season in the club's own dropdown derives from one of its 32 CA seasons,
  and none of the extras do. Walking a grade's match list back to its owning
  organisation named the club — Willetton Premier Cricket Club — and 9 of the 17
  extra rows are its season rows exactly. Reading the code alone would have got
  as far as "duplicate seasons" and no further.
- **THE FOLD IS THE RULE `resolve_season_filter` ALREADY APPLIES EVERYWHERE
  ELSE.** Picking "2025/26" from any dropdown has always returned every season
  row sharing that year, aliases included — the season TABLE was the one surface
  that disagreed with the filter above it. `_SEASON_FOLD_CTE` folds every season
  onto the viewing club's own row for that year, then through any active merge,
  and both paths read it. This is the table catching up, not a second definition
  of a season.
- **FOLD, NEVER DROP.** Org-filtering the games instead would have been the
  other obvious fix and is the wrong one: it removes matches from a career and
  leaves the table summing to less than the header right above it, which is the
  exact failure `_season_by_season_scoped`'s own docstring exists to prevent. A
  year the club has no row of its own for folds to itself and still draws.
- **A HISTORICAL BUNDLE IS DELIBERATELY LEFT UNFOLDED.** It carries a whole
  pre-migration career on one season row (`_HISTORICAL_BUNDLE_MATCH_CAP`) and is
  lifted out into "Prior Seasons & Adjustments" by matching its own season id —
  folding a real season into it would send that real season into the lump too,
  which is the one way this change could have lost a row.
- **`key={s.season_name}` on the season rows was a duplicate React key** for as
  long as two rows could share a label. Keyed on `season_id` now.
- **Verified against a real Postgres** (`backend/verification/verify_player_season_fold.py`,
  17 checks through the shipped `get_season_by_season` over the views pulled
  straight out of the migrations that define them: the reported case replayed
  across two and three clubs' season rows, the folded row filed under the club's
  own season, a year only another club holds a row for still drawn, the innings
  and runs still adding up to the career, our own year split across two of our
  rows folded on the unscoped path, and the 256-match bundle still lifted out
  whole) **with a control run**: with the fix stashed, 4 fail on exactly the
  reported behaviour — 2 rows for 2025/26 and 3 for 2022/23 — while the bundle
  checks still pass, so the fold is not what makes them pass.
- **Measured at platform scale** (4,437 season rows): 9.7 → 13.7ms on the scoped
  path, 13.5 → 9.3ms on the unscoped one.
- **NOTICED, NOT FIXED**: `_season_by_season_scoped` still counts every game a
  player appears in whatever club's fixture it was, while the unscoped path is
  org-guarded by the effective view (migration 060) — so the two paths can
  disagree about the size of a career for someone who has played for more than
  one synced club. Which of the two readings a club wants is a product decision,
  not a bug this fix should settle on its own.

### M IS MATCHES PLAYED. INN IS INNINGS. They are different numbers (v9.62.2)

Reported straight after the fix above: the Players list read **M 127** where
the same player's profile read **MATCHES 150**. Both were "right" and they
measured different things.

- **A BOARD'S GAMES FIGURE WAS COUNTED FROM ITS OWN PER-INNINGS ROWS**, so the
  batting board's M was matches he BATTED in, the bowling board's was matches
  he bowled in, and the fielding board's was matches a ball came to him. Beside
  an INN column that already means innings, M can only mean matches — and
  `aggregations._scoped_games_played` (the profile's own figure) already said
  so in its docstring. The 23 in the gap were matches he was picked for and
  never got a bat in.
- **WORSE, THE DEFINITION MOVED WITH THE FILTER.** With no grade-type filter
  the same column reads `SUM(player_season_stats.matches)` — Cricket
  Australia's own matches PLAYED — so one column meant two things depending on
  whether a pill was on. That is what made 106 / 142 / 150 three plausible
  answers to one question.
- **`_matches_played_cte` is the one definition**, unioning the same four
  sources `_scoped_games_played` unions (a batting innings, a bowling spell, a
  fielding row, a bare `game_appearances` row). It **narrows the games FIRST**
  so the three per-innings tables are not scanned platform-wide, the shape
  `records.py`'s `grade_scoped_games` already uses.
- **IT SUPPLIES THE FIGURE, NEVER THE QUALIFICATION.** A player is still listed
  on the batting board because he has a batting innings or a residual; the
  matches CTE is LEFT JOINed for its number alone. Joining on it would fill a
  batting leaderboard with players who never batted.
- **`records.most_matches` had the same hole** and it is the board literally
  called most matches: its `use_game_level` branch unioned the three
  per-innings tables and not `game_appearances`, so a player named in a side
  and dismissed for nothing measurable was short a match against his own
  profile. The fourth arm is added.
- **Measured** (25,000 games, 1,260 grades, 75,000 innings): the scoped batting
  leaderboard 160 → 188ms. The union is the cost, and it buys the column
  meaning one thing on every screen.
- **NOTICED, NOT FIXED**: the grade-scoped, finals-only and captain-only
  branches of the same boards still count their own per-innings rows. Each is a
  narrowed subset where "matches" wants its own reading (finals played, matches
  captained), and each needs its own look rather than the same CTE pasted in.

### Grouping is a job the platform does, not a button a club must find (v9.62.1)

Reported off Applecross: Manage Grades showed **0 competitions** and every
grade it has ever played under "not in a competition", with a button offering
to fix it. A club should not have to know that button exists.

- **THE SYNC ALREADY FILLS THE ASSOCIATION IN — FOR THE SEASONS IT SCANS.**
  `_resolve_org_grade` writes it on an existing grade as well as a new one, so
  a fresh club that syncs its whole history (Shoalwater Bay) comes out fully
  grouped. An ESTABLISHED club syncs incrementally, so only the current season
  is reached and the other fifty are not. That is the entire gap.
- **IT IS NOT HOOKED TO THE SYNC, and the first cut's mistake is worth
  keeping.** Hanging it off `sync_organisation` reads as the obvious place and
  is wrong: a club that played nothing in the period never reaches that
  function at all (`_record_idle_run` short-circuits it), so every off-season
  and every quiet club would sit un-grouped indefinitely — exactly the clubs
  most likely to be carrying a whole history of it. `competition_grouping
  .maybe_group_club` is called from a standalone nightly job instead
  (`jobs/scheduler.group_all_organisations`, 02:30 Perth), over
  `auto_sync.eligible_clubs`. Its own try/except and its own session.
- **IT IS A JOB THAT FINISHES, and that is the whole design problem.** Running
  it every sync would re-fetch, for the life of the club, the seasons CA simply
  has no association for. So `run_grouping` now reports **`seasons_unresolved`**
  — what is still missing once it has done all it can — and the trigger fires
  only when the current gap is GREATER than the last completed run's residual.
  True the first time, true again when a new season turns up without one, false
  for ever after on a club whose remaining gap is CA's own.
- **A run in flight is never doubled up** (`running_run_id`), so a sync landing
  while an admin has pressed the button joins nothing and starts nothing.
- **The button stays as the escape hatch**, for a club that wants it now rather
  than after the next sync, and the copy says which is which.

### The association is already in our own database — ask it, don't re-fetch (v9.62.3)

Asked for directly, after the nightly job above was costed out: a fortnight to
work through the platform's backlog is not acceptable, and the fix should come
from the data BetterCricket already holds rather than from Cricket Australia.

- **`games.raw_payload` IS A DEAD COLUMN — nothing writes it**, so the
  association cannot be recovered from stored match payloads. Checked before
  designing anything; the only reference left is `clone_demo_club.py`. That
  ruled out the obvious route and forced the two below, which are better.
- **A CA GRADE GUID IS COMPETITION-WIDE, so one club's answer is every club's.**
  The whole competition shares the guid (migration 067's own note: ten clubs
  share High Wycombe's "1st Grade"), so an association ANY club holds against a
  guid is the association for every club's row carrying it. That is what makes
  a single recently-synced club resolve the same grade for everybody who plays
  in it, with no call at all.
- **A CLUB'S OWN GRADE NAME IS ITS OWN COMPETITION, so one recent season
  resolves twenty-five old ones.** Folded through `grade_merge_logs` and the
  sponsor-suffix strip, so CA's older spelling and "A Grade (Solo Energy)"
  land on the same key — the same two rules `club_grade_rows` already applies,
  because a name resolved one way for the filter and another way for the
  backfill is how the two start disagreeing.
- **BOTH PHASES REFUSE TO GUESS, and that half is load-bearing.** Each is
  guarded by `HAVING COUNT(DISTINCT association_id) = 1`, so a club that MOVED
  association under one grade name has its unknown years left unknown rather
  than being filed under whichever era won. A wrong association is worse than a
  missing one: it puts a club's matches under a competition it never played in,
  which is the reported bug wearing a different hat.
- **THEY FEED EACH OTHER, so `propagate_all` loops until neither writes.** A
  guid filled from another club unlocks that club's other seasons of the same
  name, which carry a guid a third club is waiting on. Bounded at five passes
  so a pathological cycle cannot spin.
- **NOTHING IS EVER OVERWRITTEN.** Every statement is `WHERE association_id IS
  NULL`, so a run is idempotent and a second one writes nothing.
- **THE API PHASE COLLAPSES AS IT GOES.** What our own data cannot answer is
  fetched once per season, and each answer is applied across EVERY club holding
  that guid immediately — so the first club processed in an association drops
  the others' seasons off the list before they are ever called. Each season is
  re-checked right before its call for exactly that reason.
- **Measured at platform scale** (110 clubs, 23,381 grades, 2,750 seasons, with
  a sixth of the clubs having moved association and a third carrying a defunct
  competition that appears in no recent season): **96.4% of the gap closed from
  our own data in 6.5 seconds**, and the remainder needing a CA call falls from
  2,750 seasons to 407. `--apply --no-api` including the grouping of all 110
  clubs runs in 1.7s.
- **`python -m app.scripts.backfill_all_associations`** is the one-shot batch,
  dry-run by default per the house rule.
- **A DRY RUN MUST MEASURE BEFORE IT ROLLS BACK.** The first cut ran each phase
  once and measured the residual gap AFTER the rollback, so it reported the gap
  it started with — telling an operator nothing would be resolved by a run that
  in fact resolves 96% of it. `propagate_all(commit=False)` is the fix, and it
  exists so the dry run reuses the REAL loop rather than keeping a second copy
  that could drift. Found by running the script, not by reading it.
- **THE NIGHTLY JOB IS NO LONGER DRAINING A BACKLOG**, which is what its cap
  was for, so `GROUP_CLUBS_PER_RUN` went 10 → 40 and its comment says the batch
  owns the backlog. A settled club is skipped before any call is made, so the
  steady state costs nothing.
- **Verified against a real Postgres**
  (`backend/verification/verify_association_backfill.py`, 24 checks through the
  shipped functions: a club inheriting a shared grade's association across
  every season, a club's own earlier seasons inheriting from a later one
  including CA's merged-away spelling and a sponsor-suffixed one, both
  refusals — the club that moved and the club sharing nothing — the gap closing
  from 11 to the 4 nobody can answer, a second run writing nothing and never
  overwriting, `outstanding_seasons` naming only the two clubs left, one
  fetched answer resolving every club holding that guid, the grouping it
  unlocks, and the dry run reporting the real figures while leaving the
  database untouched) **with control runs**: with the service absent the suite
  reports it rather than crashing; with the two propagation phases neutered 11
  of the 24 fail; with the `commit` flag ignored, 3.
- **Verified**: the competitions suite is 126 checks now — the club grouped
  with nothing pressed, the residual recorded, a second sync skipping, a later
  season bringing it back, the club settling once CA answers, the in-flight
  guard, and a structural check that the SYNC is what calls it — **with a
  control run**: all 9 fail against the previous commit, reported rather than
  crashed.

### A live dry run needs the real cost, not the residual row count (v9.62.4)

Asked for directly: a dry run against a real database reported "22,862 rows
still missing" and read as the wall this feature was meant to remove — that
figure is grade ROWS, not Cricket Australia CALLS, and the gap between the two
is the whole reason the propagation phases exist.

- **`plan_api_phase` works out the real call count from data already held,
  with no request made.** It unions grades into the same components the two
  propagation phases spread along — a shared CA grade guid, one club's own
  grade name — and walks the outstanding seasons in the order the API phase
  would, counting a call only when it touches a component nothing has resolved
  yet. One fetched season can settle several components at once, which is
  exactly what collapses 2,750 outstanding seasons into ~33 real calls on the
  live data.
- **It is a lower bound, and says so.** It assumes CA answers every season it
  is asked, so a season CA genuinely has no association for is still counted
  as a call that resolves something. The real run reports the exact figures;
  this is what an operator reads before deciding to run it at all.
- **The dry run prints it after the SQL phases, not before** — it has to run
  against the state those phases leave behind (rolled back at the very end,
  not before), or it counts calls for seasons our own data has already
  answered and inflates the very number it exists to shrink.

### The Club Directory closes what the sync alone cannot (v9.62.5)

Asked directly, on seeing a live dry run: "the club directory displays all of
the associations linked to every club — why can't this information be used?"
Good instinct, and it works — but only after checking, not assuming, the two
things that decide whether it can.

- **`scripts/inspect_association_sources.py` is the check, and it is
  read-only.** No write, no upstream call. It answers the two questions that
  decide whether the Directory can be trusted here: do the two id spaces
  agree, and how many clubs does the Directory show playing in exactly one
  association (the only case where its answer is exact rather than a guess).
  Run against the live database it found **0 of 3** association ids shared
  between `grades.association_id` and `marketing_clubs.associations`, and all
  3 **names** shared — confirming this repo's own history of PlayHQ-main-graph
  ids disagreeing with Grassroots-proxy ids, and that the fix has to match on
  name, never on the Directory's own id.
- **`propagate_from_directory` is the third phase, and it never writes the
  Directory's id.** For a club the Directory shows playing in EXACTLY one
  association, every grade with no association becomes answerable in one
  step — not by propagating from a known row, but because the WHOLE club is
  known to mean one thing. A club in several associations says nothing about
  which one ran a given grade, so it is left untouched, same as the API phase
  would have to ask it directly.
- **The target id is resolved by NAME, reused if anything already calls it
  that, minted only if nothing does.** `HAVING COUNT(DISTINCT association_id)`
  the same refuse-to-guess guard the other two phases use: a name that already
  means two different real ids somewhere (two associations sharing a common
  word) is left alone rather than picking a side. Where nothing anywhere has
  ever called it that, a deterministic id is minted from the normalised name
  (`uuid5` in a namespace of its own, never a real CA guid), so two
  Directory-only clubs naming the same association land on one value even
  though neither has a synced grade to agree through.
- **It runs inside the same `propagate_all` loop as the other two, feeding
  and fed by them** — a whole club filled from the Directory can be the first
  known row for a guid or a name that unlocks a DIFFERENT club sharing it,
  exactly the way a synced club's answer already does.
- **Verified against a real Postgres** (the suite is 30 checks now: a
  Directory name that already means something reusing that id rather than
  minting a second one, a name nobody has ever synced being minted once and
  never colliding with a real id, the ambiguous-name refusal, the
  more-than-one-association club left for the API, and the gap closing from
  23 to the 10 nobody can answer with the three new clubs folded into the
  fixture) **with control runs**: with the phase neutered, 7 of the 30 fail;
  with the ambiguity guard removed, the refusal check catches it picking a
  side rather than declining.
- **Found by running it, not by reading it**: the first cut cast the minted
  and reused association ids to `uuid[]` in the batch UPDATE, matching the
  shape of every other id in this feature. `grades.association_id` is `TEXT`,
  because a real CA/PlayHQ association id is an arbitrary routing code, not
  guaranteed to be a UUID — the cast crashed on the very first Directory-linked
  club it touched. Fixed by casting to `text[]`, which is what the column
  actually is.

### A live run at concurrency deadlocked writing the answers back (v9.62.6)

Found running `--apply` for real, against the live database, not offline: the
SQL phases committed (15,838 rows, safe — `propagate_all` commits before the
API phase ever starts), then several concurrent workers into the API phase the
run crashed on `DeadlockDetectedError`.

- **`apply_associations` WROTE ONE GUID AT A TIME, IN A LOOP, IN WHATEVER
  ORDER A DICT ITERATED.** Two concurrent workers each writing several guids
  from their own team payload could lock the same two rows in opposite
  orders — the textbook two-transaction deadlock, and something no offline
  suite running single-threaded could ever exercise. It is now ONE UPDATE via
  `unnest`, the same shape `propagate_from_directory` already uses: a single
  statement takes every lock it needs in one scan and cannot deadlock against
  itself, which is what removes the ordering freedom that let two callers'
  writes cross.
- **THE SEMAPHORE ONLY CAPPED THE FETCH, NOT THE WRITE.** Once past the
  concurrency gate on `get_teams`, every worker's write could still land at
  once with no bound at all on how many concurrent transactions were touching
  `grades`. The write now happens INSIDE the same semaphore as the fetch, so
  total concurrency — fetch and write together — is bounded to the configured
  number rather than only the network half of it.
- **A DEADLOCK IS STILL A BACKSTOP AWAY FROM A CRASH.** Postgres's own remedy
  for a deadlock is "retry one of the two transactions" — it is not a data
  problem, so a bounded retry in a FRESH session (the failed one is unusable
  once the driver has raised) is the right response rather than losing a run
  that has already spent its Cricket Australia calls and fetched its answers.
- **THIS COULD NOT BE FOUND OFFLINE.** The verification suite runs one
  statement at a time against a real Postgres; a deadlock needs two
  transactions racing for the same rows in opposite orders, which is a timing
  condition no single-threaded check reproduces. What the suite CAN and does
  pin is the structural fix: one call to `apply_associations` with several
  guids writes every one of them, not just the first, and never re-races
  against itself.
- **Verified against a real Postgres** (the suite is 33 checks now: a single
  call filling several guids at once, each landing its own association rather
  than the call stopping after the first, and an already-known row still never
  overwritten) **with a control run**: a version that only ever applies the
  first guid in the dict fails both new checks, at 1 filled instead of 3.

### The grade leaderboard and the profile under it (v9.53.13)

Reported off Records with a grade picked: the board read 61 where the
player's own by-grade grid read 60.

- **NEITHER FIGURE WAS THE OLD BUG. The 1 was the club's own correction
  landing on one surface and not the other.** CA's per-grade figure for this
  player is 61; the club had entered a -1 against 2022/23 1st Grade, which
  v9.53.11 made reach the profile grid (60) and nothing had made reach the
  board. Establishing that first is what stopped this being "chase another
  missing match".
- **`use_psgs_path` SUMMED `player_season_grade_stats` WITH NO CLUB SCOPING**,
  the same leak the grid had: `JOIN grades gr ON gr.id = psgs.grade_id` and
  nothing about whose season that grade belongs to, so a second club's rows
  for the same participant GUID were added on top. Scoped through
  `seasons.organisation_id` now. In the suite the unscoped board reads 9
  against a true 6.
- **THE BOARD ALSO HAD TO KEEP THE PROFILE'S OTHER HALF.** `max(held,
  claimed)` — CA's per-grade row, never below the scorecards the club holds —
  is what the grid uses; the board took CA's figure alone, so it sat BELOW the
  player's own page wherever CA is short of what we hold (a shared fixture the
  other club synced first is exactly that case). `grade_games` supplies the
  floor, and `grade_scoped_games` narrows the games FIRST so the three
  per-innings unions are not scanned platform-wide — the shape the
  `use_game_level` branch beside it already uses.
- **Measured**: 1,567ms against a 1,528ms baseline for the whole records
  endpoint at platform scale, on a larger dataset than the baseline run. The
  added CTEs are not what that endpoint costs.
- **Verified against a real Postgres** (the suite is 65 checks now: the player
  on the board, the board reading exactly what the profile's grid reads, and
  that figure being CA's less the club's correction) **with a control run**:
  2 fail against the previous commit, the board reading 9 for a true 6.

### One rule for "this game is ours", on every player read (v9.53.12)

Asked for directly after the grid fix: it should be in effect across all
functions. Until now only the by-grade grid counted the club's own games; the
career header, the season table and every analysis panel still counted every
game the player appeared in.

- **`_club_game_clause` IS THE ONE PREDICATE, and it is the one the codebase
  already had.** `iq_trends._ours_clause` (mirroring `_club_results`) was
  already right: a game is ours when its own club is us OR **when we are one of
  the two sides** (`home_org_id`/`away_org_id`, migration 167). The first cut
  used `organisation_id` alone and the suite caught it — that drops a genuine
  shared fixture the other club synced first, which is the one thing this must
  not do. Fold, or keep; never lose a match the club actually played.
- **A FUNCTION-LEVEL AUDIT, NOT A GREP FOR SQL TEXT.** Searching the SQL
  strings alone flags `_player_recent`, which is already correct — its filter
  arrives through an interpolated `extra`. The audit that works reads the whole
  function body for `:pid` plus a per-game table and no org reference of any
  kind. It found 13 reads in `aggregations.py`, plus `player_formats` and
  `get_player_captain_stats`.
- **`player_formats`'s docstring argued it needed no filter** because a
  `player_id` is already per-club under the uuid5 scheme. That is true of the
  PLAYER and says nothing about the GAME, which is the whole bug. Corrected
  there rather than left to mislead the next reader.
- **THE CLUB FILTER RIDES ON `scope_clause`**, so each function's existing
  interpolation points pick it up and no query template needed editing. The two
  clause-list callers append it as their own entry. `_build_recent_games_cte`
  and `_build_date_filtered_games_cte` take it as an argument: without it a
  "last 10 games" window is drawn from another club's matches and then filtered
  down to fewer than 10.
- **THE SMOKE PASS IS WHAT MADE THIS SAFE.** Every patched read is executed,
  scoped and unscoped — 12 functions plus the formats page and captain stats.
  It caught two real breaks the type checker and `py_compile` cannot see: the
  captain by-season CTEs reference no games view, so a blanket clause raised
  "missing FROM-clause entry for table g" (they are already narrowed to
  `captain_games`, which carries the predicate, so they need none), and it
  proved the shared-fixture case end to end.
- **A FIXTURE HAS TO CARRY WHAT THE QUERIES FILTER ON.** Three checks read zero
  against working code until the games had a `result` (by-venue drops a NULL
  result by design), a `game_appearances` row (`player_game_ids` reads
  appearances, not innings) and a `match_format` (everything else lands in
  `not_recorded`). A check reading zero is not a passing check.
- **Verified against a real Postgres** (62 checks) **with a control run**: 15
  fail against the previous commit. Measured at platform scale (4,438 season
  rows): the grid 17.4 -> 28.4ms, the extra being the year map it now loads for
  every season rather than the club's own, so a foreign season can fold onto
  our row for that year.
- **The career header and the season table now agree with each other and with
  the grid**, which is the check that keeps this honest: the suite asserts
  career innings and runs equal the season table's own sums.

### The same year counted twice, and another club's matches with it (v9.53.11)

Reported straight after the fold above: the season x grade grid still drew the
year several times, "1st Grade" read 66 where the club counts 60, and a Manual
Entries correction changed nothing.

- **`get_player_team_breakdown` IS ITS OWN ATTRIBUTION PASS and the fold never
  reached it.** Its `_canonical_season` resolved the ALIAS map only — the
  comment above it already described folding a year split across several season
  rows, which is not what it did. It now folds alias -> the club's own row for
  that year -> back through any merge, the same rule as `_SEASON_FOLD_CTE`.
- **CRICKET AUSTRALIA SETTLED THE COUNT, AND IT AGREED WITH NEITHER FIGURE.**
  Querying `/participants/organisations/{org}/batting-statistics` per season
  with `gradeId` gives CA's own per-grade match count: 1st Grade is **61**, not
  our 66 and not the reported 60. Every one of the club's OWN season rows
  matches CA exactly across all 12 seasons and every grade; all **24** excess
  matches across the grid sit on other clubs' season rows. That is what makes
  this a scoping bug rather than a counting one.
- **BOTH SIDES OF THE ATTRIBUTION WERE UNSCOPED.** The scorecard counts joined
  `games -> grades` and CA's exact `player_season_grade_stats` joined `grades`,
  neither filtering the season's organisation — so a second club's rows for the
  same shared CA participant GUID were added on top of this club's. Both are
  scoped now, which is what lands the grid on CA's own numbers.
- **SCOPING BOTH SIDES IS WHAT KEEPS `max(held, claimed)` SELF-HEALING.** A
  shared fixture the other club synced first drops off the scorecard side —
  and CA's per-grade row still claims it, so `max` puts it back as
  `attributed_unknown`. Scoping only one side would have lost it.
- **A MANUAL CORRECTION NOW REACHES THE CELL, and it could not before.** The
  grid reads CA's per-grade rows and the scorecards; `manual_season_adjustments`
  is in neither, so a `-1` against a season and a grade did nothing wherever CA
  had per-grade data, and `max(held, claimed)` could not go below the
  scorecards held anyway. Per-grade corrections are read separately, applied to
  the cell last, clamped at zero — and **excluded from `season_aggregate`**, or
  the gap heuristic in the no-CA-data branch would count the same correction a
  second time. A grade-less adjustment still feeds the season as a whole, since
  it has no cell to go to.
- **Verified against a real Postgres** (the suite is 29 checks now: the grid
  drawn once per year, each cell reading CA's own figure rather than the sum of
  two clubs', the grade total and the scorecard count both the club's own, the
  cells still adding up to the grade rows, and the correction landing once,
  following through to the career total and leaving other seasons alone) **with
  a control run**: 9 fail against the previous commit.
- **A CHECK THAT READS ONE ROW OF A SPLIT SEASON CAN PASS ON THE BUG.** The
  first cut read `{r["season_name"]: r["grades"]}` — with the year unfolded the
  last row wins, and the correction check passed against the broken code on a
  dict collision. `grade_total()` sums across every row carrying the label.
- **NOTICED, NOT FIXED**: the career header and the season table still count
  every game the player appears in whatever club's fixture it was, so they
  remain higher than this grid for someone who has played for more than one
  synced club. Bringing them in line means dropping matches from a career
  total, which is a product decision rather than a bug fix.

<!-- END original CLAUDE.md L3428-3893 -->
<!-- BEGIN original CLAUDE.md L9022-9079 -->
## Cross-club member leak: the opposition were enrolled as our members (Aug 2026)

Reported live: a High Wycombe player (and HW club admin) appeared in
**Applecross's** Clubhouse Directory, under Everyone and Players, carrying his
real email, phone and photo. Not a display bug — Applecross genuinely held a
`fee_members` row for him.

- **Cause: `services/fees.py::recompute_fee_match_days`.** It selected the
  season's games (correctly org-scoped through grades → seasons), then read
  **every** `game_appearances` row on those games and enrolled the player behind
  each one as a member, with a comment asserting "only our club's players have
  rows". **That assertion is false and this file already documents why**: a
  fixture between two clubs that BOTH sync is a single `games` row, and each
  club's sync writes its own players' appearances against it. So every opponent
  from every both-synced club became one of our members. The `select(Player)`
  that followed had no org filter either, so nothing downstream could catch it.
- **This is the exact anti-pattern the v8.79.3 note names**: never read a
  per-game table "for a game in our org's grades" without ALSO scoping
  `players.organisation_id` when attributing to our side. The fix loads the
  appearing players org-scoped FIRST, then filters the appearances to them, so
  member creation and match-day charges both inherit the scope.
- **`services/directory.py::list_people` amplified it.** Its
  `LEFT JOIN players p ON p.id = fm.player_id` had no org condition, so a member
  row pointing at another club's player served that club's **photo, email and
  phone** into our Directory. Now joined on `AND p.organisation_id =
  fm.organisation_id`: a stray link degrades to a plain name rather than leaking
  contact details. **Any read-through from a member to its player needs this.**
- **`python -m app.scripts.purge_foreign_members [org|all] [--apply] [--delete]`**
  clears what was already written. Dry run by default; archives (reversible,
  and enough to clear the Directory) unless `--delete`. A row with anything
  attached — a payment, role, qualification, committee term, logged hours, a
  family link, a roster shift — is **reported and left alone**, because the link
  is wrong but the attached work may not be.
- **The state is now unrepresentable, not just filtered out (migration 223).**
  A composite foreign key on `fee_members (organisation_id, player_id)` →
  `players (organisation_id, id)` means Postgres refuses a member row that
  points outside its own club, whatever code is writing. Added **NOT VALID**:
  enforced on every new INSERT/UPDATE immediately, while rows the earlier bug
  wrote are tolerated until `purge_foreign_members` clears them. Run
  `ALTER TABLE fee_members VALIDATE CONSTRAINT fk_fee_members_player_same_org`
  once a database is clean to turn on the retrospective check too.
- **`list_people` reads `our_player_id` (the org-scoped join result), never
  `fm.player_id`.** A link that does not resolve within the club must not tag
  the person "Player" and must not carry a `player_id` through to the frontend —
  otherwise a stray row still reads as one of our players and still links to
  someone else's profile. Scoping the join alone was not enough.
- **Verified by reproducing it**: two clubs, one shared fixture, both sets of
  appearances on it. With the fix reverted the suite fails on exactly the
  reported symptom (the opponent enrolled and listed); with it in place, 14
  checks pass including that a pre-existing bad link leaks no contact details
  and a re-sync does not recreate the row.
- **The three different people counts are NOT all the same bug.** Core's
  Players screen reads `players` (unfiltered, so it is the true player count),
  Accounts reads `fee_members` for one season, the Directory reads all
  `fee_members` ∪ org players, and BetterComms Lists reads `comms_contacts` —
  a **fourth, separately-populated table** that nothing syncs from the other
  three. A club will legitimately see four different totals until step 4 of the
  Clubhouse handoff (joining the data) is done.
<!-- END original CLAUDE.md L9022-9079 -->
<!-- BEGIN original CLAUDE.md L9080-9136 -->
## The shared-game rule: scope the PLAYER, not just the game (v9.11.1, Aug 2026)

The member leak above was one instance of a much wider bug. An audit of every
SQL block that reads a per-game table and joins `players` found **15 more
sites** doing the same thing, and a production count confirmed **326,816
cross-club rows across 38 clubs** were being read as the viewing club's own.

- **The rule, and it is not optional**: a fixture between two clubs that BOTH
  sync is a SINGLE `games` row, and each club's sync writes its own players'
  rows against it. So `games → grades → seasons → organisation_id` tells you the
  game is in our competition; it tells you **nothing** about whose player a row
  belongs to. **Any read of `batting_innings`, `bowling_spells`,
  `fielding_stats`, `game_appearances`, `partnerships`, `fall_of_wickets` or
  `bowler_wickets` that attributes a row to our side must ALSO scope
  `players.organisation_id`.** Season-aggregate reads (`player_season_stats`)
  are a different shape and are already handled by the v7.32.1 view fix.
- **Fixed here**: `aggregations.get_fielding_leaderboard` (the finals and
  captain branches, the only public-facing one), all ten of `iq_team.py`
  (`_team_fielding`, `_batting_pairs`, `_attack_structure`, `_captaincy`,
  `_combinations`, `_discipline`, `_collapse_bowlers`, `_role_ratings`,
  `_batting_extra`), `iq_review.game_review`'s best-partnership query,
  `iq_teammates.teammates`, and `iq_opponent._db_season_accumulators` (×3).
  `iq.py` had already been done in v8.74; `iq_team.py` never got the same pass.
- **`_captaincy` also summed the OPPOSITION's runs** into "average team score
  under this captain" — its `scores` CTE read `batting_innings` for our games
  with no player scope at all. Not a join bug, so an audit that only looks at
  `JOIN players` misses it. Check the CTEs too.
- **`is_club_innings` is set PER CLUB** (`sync.py`: TRUE for whichever side is
  its own), so a shared fixture's one `games` row carries BOTH clubs'
  partnerships marked TRUE. `WHERE game_id = X AND is_club_innings IS TRUE` is
  therefore NOT a club filter. That is what put the opposition's best stand in
  our own match review.
- **Scope ONE side of a partnership, not both.** Both batters in a stand are
  from the same innings and so the same club, so scoping either one excludes an
  opposition pair. Scoping both would also drop a legitimate stand involving a
  teammate whose `players` row sits under another club (the shared-participant-
  GUID case). `_combinations` is the exception and scopes BOTH, because its
  pairs come from appearances on the same game, where one of ours can genuinely
  pair with one of theirs. Same reasoning for `bowler_wickets`: scope the
  BOWLER, leave the fielder, they are on the same fielding side.
- **Deliberately left unscoped** (verified safe, do not "fix" them):
  `aggregations.get_player_partnerships` and `iq_trends.bowler_deep_dive`
  (anchored on a specific `:pid`), `yearbooks._generate_narrative_core`,
  `statlab.derived_best_partnership_pair` / `_partnership_aggregates_pair` /
  `_century_partnerships_pair` / `_bowler_fielder_combo` (one side already
  scoped), and `iq_team._team_fielding`'s combo query / `_batting_pairs`
  (partner alias, per the rule above).
- **The audit is repeatable and worth re-running when adding a per-game read.**
  Extract every triple-quoted SQL block, keep those with a per-game table after
  `FROM`/`JOIN` **and** a `JOIN players <alias>`, and flag any alias with no
  `<alias>.organisation_id` anywhere in the block. Match the table only after
  `FROM`/`JOIN` or `st.batting_innings` (a COLUMN on `player_season_stats`)
  produces a pile of false positives.
- **Read-side only.** No migration, no data change, no re-sync: the rows are
  correct and belong exactly where they are. Every affected figure corrects
  itself on the next page load.

<!-- END original CLAUDE.md L9080-9136 -->
<!-- BEGIN original CLAUDE.md L12800-12811 -->
## Super Admin Club Delete — soft-delete + FK cascade fix (Jul 2026)

**Symptom**: clicking "DELETE PERMANENTLY" on a club (Super Admin → All Clubs) looked like it succeeded (no error surfaced), but the club was still there afterwards.

**Root cause**: `DELETE /club-admin/super/clubs/{id}` deletes `organisations`, relying on `ON DELETE CASCADE` FKs to remove everything downstream (seasons → grades → games → per-game stat rows). Live logs showed the real error: `ForeignKeyViolationError: ... "partnerships_game_id_fkey" ... Key (game_id)=(...) is not present in table "games"` — `partnerships.game_id` was **not actually `ON DELETE CASCADE` in the live database**, even though `app/models/db.py`'s ORM column has always declared `ondelete="CASCADE"`. The model's intent was never applied to the schema — these are pre-Alembic tables (no migration has ever touched these constraints by name), so the drift went unnoticed until a club with real synced data (partnerships rows) was actually deleted. The whole `DELETE` transaction rolled back, which is why it looked like nothing happened.

**Fix (migration 142)**: reconciled the FK on every sibling legacy per-game/per-player stat table sharing the same origin (`batting_innings`, `bowling_spells`, `fielding_stats`, `bowler_wickets`, `game_appearances`, `fall_of_wickets`, `partnerships`, `milestones`, `fee_match_days`) — not just the one that happened to be hit first. Safe on a live, populated table: builds each corrected constraint `NOT VALID` (near-instant) then `VALIDATE CONSTRAINT` separately (a background scan, doesn't block reads/writes), and checks `pg_constraint.confdeltype` first so an already-correct constraint is left alone (cheap no-op on every app-restart re-run via `main.py`'s idempotent mirror).

**Also shipped (migration 143), per direct request**: club "delete" is now a **soft-delete (archive)**, reversible. `organisations.archived_at` (nullable timestamp) — `POST /club-admin/super/clubs/{id}/archive` sets it (no row anywhere is touched), `POST .../restore` clears it. The old hard-delete (`DELETE /club-admin/super/clubs/{id}`) still exists for a genuine permanent purge later, but now requires the club to already be archived first (a speed bump), and is no longer what the UI's "Delete"/now "Archive" button calls. `GET /club-admin/super/clubs` hides archived clubs by default (`?include_archived=true` to show them); `SuperClubs.jsx` has a "Show archived" toggle and a "Restore" action per archived row. Archiving deliberately does **not** touch `is_active` — restoring shouldn't silently flip a state the admin didn't touch themselves.

**Follow-up bug (same day)**: archiving a club then trying to self-serve-register it again under the same CA org id was rejected as "already registered" — `find_matching_organisation` (the shared duplicate-check `sync.py` helper) had no awareness of `archived_at` at all. Fixed with an `include_archived` param (default `True`, preserving `upsert_organisation`'s own dedup guard — it must still find and reuse an archived row rather than creating a second one for the same CA org): `self_serve_trial.py`'s three duplicate-check call sites (`search`, `/prepare`, `/submit`) now pass `include_archived=False`, so an archived club reads as available to register again. `/submit`'s finishing block (alongside the existing `is_active=True`/slug backfill) now also clears `archived_at` — registering a previously-archived club un-archives it, which is what "available to register again" has to mean once submit reaches that point and reuses the row.

<!-- END original CLAUDE.md L12800-12811 -->
<!-- BEGIN original CLAUDE.md L12839-12865 -->
## June 2026 Cross-Club Player Over-Count Fix (v7.32.1)

**Symptom**: a player who turned out for two synced clubs (e.g. Applecross **Cricket Club** *and* Applecross **Junior Cricket Club**) showed his *combined* career on each club's page — 7 ACC matches displayed as 63 (7 + 56 junior).

**Root cause — players have the SAME shared-GUID collision that Seasons already solved.** `players.id` is the raw Cricket Australia participant GUID used as a **global** primary key, but CA reuses one participant GUID for a person across every club they play for. Both clubs' org-scoped aggregate feeds (`/participants/organisations/{org}/...-statistics`) therefore return that one GUID. Whichever club syncs first **creates** the single `players` row (and sets its `organisation_id`); the other club's sync then finds it by PK — `session.get(Player, pid)` is a **global** lookup, not org-scoped (sync.py ~538/558) — and attaches *its* seasons' `player_season_stats` to the same row. Every career query then did `SUM(player_season_stats.matches) … WHERE player_id = :pid` with **no organisation filter**, so the total double-counted across both clubs. (Seasons dodge this via a per-club derived id `uuid5(org, grassroots_id)`; players were never given that treatment.)

**Fix — enforce the invariant "a player's effective season stats are only the rows whose season belongs to the player's own org", once at the view + at every base-table reader that summed by org-*membership* instead of by *season's* org:**
- **Migration 060** redefines `v_effective_player_season_stats` so the base-table branch only emits a row when `EXISTS (player.organisation_id IS NULL OR player.org = season.org)`. This is the single point that fixes **every** view consumer — `get_career_*` / `get_season_by_season` (player profile), `records.py` (club records), `get_player_team_breakdown`'s aggregate count. Non-destructive (filters on read; base rows untouched), so it self-corrects and survives a re-sync — **no data cleanup or re-sync needed**.
- Base-table readers that bypass the view were scoped to the org's seasons individually: `players.py` upcoming-milestones, `sync.py::_compute_milestones` (stops minting inflated milestone rows), `iq.py::_their_key_players`, `statlab.py` (career + per-season + family + minutes), `iq_trends.py` active-players overview, `selection_pool.py` latest-season form snapshot, `club_admin.py` milestone projection.
- **Anti-pattern to avoid in new queries**: summing `player_season_stats` for a player filtered only by `players.organisation_id = :org` (player *membership*) without also constraining the **season** to that org. Read the view, or join `seasons s` and filter `s.organisation_id`. Queries that filter `WHERE s.organisation_id = :org` or `WHERE pss.season_id = <specific org season>` were already correct (yearbooks, iq_trends trajectory/breakout, iq_selection, the sync backfill).

**Deeper fix — per-club player ids (in progress, phased)**: the display scoping above stops a shared CA participant GUID from *displaying* co-mingled, but the second club of a shared GUID still can't see a player's stats at all (they sit on the first club's record — e.g. a junior club showing 30 when the player's junior career is 56, because the 56 live on the senior club's row). Giving players a per-club derived id like Seasons fixes it at the source. Rolled out incrementally so the 50+ single-club orgs are never touched:

- **Phase 1 (migration 062)** — add `players.grassroots_id` (raw CA participant GUID), backfilled from `id` (which IS the raw GUID for every legacy row), + `UNIQUE (organisation_id, grassroots_id)`. Non-breaking; no id changes.
- **Phase 2a (sync.py aggregate pass)** — `_resolve_org_player()` looks a participant up by `(org, grassroots_id)` and mints `id = uuid5(org, guid)` **only when the raw GUID is already a player id in another club** (the real collision); otherwise it keeps the raw-GUID id. So ordinary new players are unchanged and the **game-level scorecard sync (participantId == player id) keeps working untouched**. The aggregate pass deletes+reinserts per season, so a **re-sync moves a shared player's seasons off the first club's row onto his new per-club row** — the second club then shows the right career total. The first club is unaffected (it keeps the raw-GUID id and its own seasons).
- **Phase 2b (done)** — `sync_grassroots_game_level_data` now translates scorecard `participantId` (raw GUID) → per-club `uuid5` id before every game-level insert, so a per-club player gets per-innings rows (batting/bowling/fielding/FOW/partnerships/appearances/bowler-wickets) too. Implemented via a single `_team_pid(guid)` closure + a `pid_by_guid` map built in discovery (and threaded into `extract_bowler_wickets`, whose 3rd arg is now `gate_pids` + a new `pid_by_guid`; `app/scripts/rebuild_bowler_wickets.py` updated to match). **Identity for legacy single-club orgs** (`grassroots_id == id` ⇒ `pid_by_guid[g] == g` ⇒ `_team_pid` returns the same value the old `guid in our_team_pids` checks used), so their game-level attribution is byte-for-byte unchanged. The aggregate pass runs before the GR pass in `sync_organisation`, so the per-club player row exists before its game-level rows reference it (FK-safe). **Still verify on a data copy before prod**: confirm a normal club's per-game counts are unchanged and the shared player's per-game rows land on his per-club id. Game-level only re-attaches on a **Full Rebuild** (the GR sync skips already-synced games), so the cutover for a club with a shared player is Full Rebuild → merge the duplicate.

**Rollout / cutover** (after deploying phases 1+2a):
1. **Re-sync the second club** (Sync Now, or Full Rebuild) — mints the per-club player and moves his aggregate seasons onto it. The club's career number corrects (junior → 56).
2. (After Phase 2b) Full Rebuild the club for game-level consistency.

**⚠️ Do NOT merge the legacy-GUID duplicate into the per-club record when their seasons OVERLAP.** Discovered Jun 2026 on Matthew Watt: the post-migration GUID's per-club record (`eddde526…`, a uuid5 — note the `5` in the 3rd group) already held the **complete** 56-match junior career (CA back-fills full history onto the post-migration PlayHQ GUID). The legacy MyCricket GUID (`09ce6a6c…`, a v4 raw GUID) was a **duplicate of the older seasons** — but under **different season records**, because MyCricket and PlayHQ assign different season GUIDs to the same real season. `merge_players` dedupes by raw `season_id` (admin.py ~205), so it didn't recognise the dup, **moved** the 30 over and the career read **86 = 56 + 30**. Recovery: **undo-merge** (restores 56). The two records can't be cleanly merged until the duplicate *seasons* are reconciled (season-alias / migration-season-dedup is the unbuilt proper fix); the merge is only safe for genuinely **disjoint** registrations.

**`undo-merge` grassroots_id fix** (Jun 2026): the undo re-creates the removed player and **must** set `grassroots_id` (= `id::text`, correct for any legacy raw-GUID player), or the next sync won't find it by `(org, grassroots_id)` and will mint *another* per-club duplicate. Fixed in `admin.py::undo_merge`.

**Anti-pattern reminder**: don't reintroduce a global `session.get(Player, raw_guid)` create/lookup in sync — use `_resolve_org_player`. `players.id` is no longer guaranteed to equal the CA GUID (it's `uuid5(org, guid)` for per-club rows); the raw GUID lives in `grassroots_id`.

<!-- END original CLAUDE.md L12839-12865 -->
<!-- BEGIN original CLAUDE.md L12866-12881 -->
## June 2026 Cross-Club Grade Collision Fix (v2.16.1)

**Symptom**: a newly-onboarded club (High Wycombe) showed only the 3 grades *unique* to it (Year 8/9) in the dashboard Grade dropdown and BetterSelect auto-seed, even though it plays ~16 grades. Recent-matches (PlayHQ-partner, live) and the season summary (participant-stats, whole-club) looked correct, so only the grade-scoped surfaces were starved.

**Root cause — grades had the SAME shared-GUID collision Seasons and Players already solved.** A CA **grade is a competition-wide entity**: one grade GUID (`/scores/grades/{id}/matches` returns every match between *all* clubs in it — verified 10 clubs share HW's "1st Grade") is returned by `get_teams` for *every* club in the grade. But `grades.id` used the raw shared GUID as a **global** primary key, and sync's `session.get(Grade, grade_id)` was a **global** lookup — so the **first club to sync a grade created the row, and every later club's sync skipped it**, leaving the grade attached to whoever synced first. Applecross was onboarded before HW, so HW's 12 shared grades (1st/3rd/5th Grade, One Day 2/3/5, Colts, RJR T20, Year 5/6/9-Central) sat on Applecross's seasons; HW only created the 3 Applecross didn't have. The aggregate season stats (`player_season_stats`) survived because they come from the **participant**-scoped stats endpoint (whole club, grade-agnostic), not from grades.

**Fix — per-club grade ids, exactly mirroring the Season/Player scheme** (phased, mint-on-collision so the 50+ single-club orgs are byte-for-byte unchanged):
- **Migration 067** — add `grades.grassroots_id` (raw CA grade GUID), backfill from `id` (which IS the raw GUID for every legacy row), + `UNIQUE (season_id, grassroots_id)`. Non-breaking; no id changes.
- **`sync._resolve_org_grade()`** (mirrors `_resolve_org_player`) replaces the global `session.get(Grade, guid)` skip in the aggregate grade-seeding loop. Looks a grade up by `(org, grassroots_id)`; mints `id = uuid5(org, guid)` **only** when the raw GUID is already a grade in another club; else keeps the raw GUID. `org_grade_map` is built once per sync alongside `org_player_map`.
- **The raw GUID is what every grassroots API call must use** (not the per-club PK). Switched: per-grade stats `gradeId` (sync.py), the scores pass `get_grade_matches` (uses `grassroots_id`; scorecard `grade.id` → per-club id via a `grade_id_by_guid` map so `games.grade_id` is the per-club id), `iq_opponent._target_season_grades`/`_our_games_vs`/`_grade_name`, `ladders.py` (team + grade-ladder), `iq.opponent_ladder`. Every one is `COALESCE(grassroots_id, id)` ⇒ identical for legacy grades.
- **`rebuild_bowler_wickets.py` is unaffected** — it iterates *game* ids and only joins grades via the DB FK.

**Cutover for an affected (2nd+) club**: deploy + migrate, then **Sync Now** (re-runs the aggregate grade-seeding → mints the per-club grades, so the dropdown + per-grade stats fill immediately; the scores pass then discovers the never-before-synced shared-grade games and pulls them). A **Full Rebuild** is the guaranteed-complete version. **Known residue**: a match between two *both-synced* clubs (e.g. HW vs Applecross) is one shared `games.id` (= match GUID) owned by whoever synced it first, so the 2nd club won't get its own row for that one game — pre-existing game-identity limitation, separate from grades; HW-vs-unsynced-club games (the vast majority) are unaffected.

**Anti-pattern reminder**: don't reintroduce a global `session.get(Grade, raw_guid)` create/skip in sync — use `_resolve_org_grade`. `grades.id` is no longer guaranteed to equal the CA GUID (it's `uuid5(org, guid)` for per-club rows); the raw GUID lives in `grassroots_id`, which is what `/scores/grades/{id}/matches`, the ladder API, and the per-grade stats `gradeId` are keyed on.

<!-- END original CLAUDE.md L12866-12881 -->
