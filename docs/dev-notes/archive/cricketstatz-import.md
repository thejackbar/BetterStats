# Archive: cricketstatz-import

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: The CricketStatz history import and its many follow-ups (matching, pairing, superseding, merges, honours).
Read the distilled rules first: `docs/dev-notes/guides/cricketstatz-import.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L10637-12118 -->
## A club brings its history across from CricketStatz (migration 285, v9.67.0, Sep 2026)

Asked for directly: a club pastes the address of its own CricketStatz stats
page (`https://www2.cricketstatz.com/ss/w?mode=104&club=93931&team=0&season=`)
and BetterCricket pulls ALL of its data across, the record book included.

- **THE PUBLIC REPORTS ARE MACHINE-READABLE, AND THE CHAIN IS THREE DEEP.**
  Every report is served by the documented embed endpoint
  `/ss/linkreport?mode=<N>&club=<id>&web=1`, which answers with
  `document.write("<table>…")` — HTML tables in a JS string. Mode 12 is the
  match list, each row linking `mode=100&match=<id>`, which is the full
  two-team scorecard. 182 modes exist; ~180 of them are record boards.
- **`limit` CAPS A REPORT AT 999 ROWS, so matches are pulled SEASON BY
  SEASON.** An all-time pull of a club with a long history silently truncates,
  and a truncated history is worse than a slow one. The club's own page carries
  the season dropdown, but it lists every season back to **1860 regardless of
  the club**, so it is a list of CANDIDATES to probe, never trusted. One
  all-time pull answers it for most clubs; only a club that overflows 999 needs
  every season walked.
- **COLUMN LAYOUTS VARY BY ERA, and reading them positionally is silently
  wrong.** A modern card is `R M B SR 4s 6s`; a 1995 one is `R M 4s 6s`, with
  no balls faced and no strike rate. `_column_map` reads the header row —
  without it, boundaries are filed as balls faced and nothing complains.
- **A DISMISSAL IS READ CLAUSE BY CLAUSE, from each `span.ss_block`'s own
  how-out marker.** A modern card links the fielder and bowler (each carrying a
  stable `playerid`); an older one prints a bare name, or `N/A` where the
  scorer recorded none. Reading roles off the markers rather than by position
  is what still credits the bowler when the fielder did not resolve.
  **Splitting on the block's OPENING tag is load-bearing** — a clause nests its
  own `ss_howout` span, so a non-greedy match to the first `</span>` stops
  inside it and loses every name. The first cut did exactly that and lost all
  102 bowler credits in the corpus.
- **CAPTAIN / KEEPER / DUCK ARE `title=` ATTRIBUTES, never the emoji.** The
  glyphs vary by era and encoding; `title='Duck'` does not. Caught behind is
  then derived structurally — the keeper is marked on the FIELDING side's own
  batting card — the same signal `sync.py` takes from CA's fielding rows.
- **ONLY OUR OWN PLAYERS GET `players` ROWS.** A card carries both sides, and
  minting a row per opponent is the cross-club leak `purge_foreign_members`
  exists to clean up. The opposition half is kept on
  `manual_games.extracted_payload`, which the match view already renders from.
- **IDENTITY IS CRICKETSTATZ'S OWN `playerid`**, not the printed name — their
  reports abbreviate inconsistently across eras ("Tommy A McSwain").
  `manual_games.cricketstatz_match_id` makes a re-import correct rather than
  double.
- **A PLACEHOLDER IS NOT A PERSON.** A real Under-9 card recorded no names at
  all — every batter reads `N/A`. They all resolved to one player and the
  second innings row hit `uq_manual_batting_game_inns_player`. With no id
  behind it there is nothing to identify, so the row is left out; the match
  still imports with its result and its full card.
- **A ROLLBACK DISCARDS THE SEASON THE CACHE IS STILL HOLDING, and that is how
  one bad card cost 97 good ones.** The failure above rolled back, taking the
  flushed season and grade with it, while `caches` went on serving their ids —
  so every later match in that season failed on a dangling FK. **Clear the
  caches on rollback**, and commit **one match at a time**: the commit costs
  nothing beside the fetch that precedes it, and it is the honest unit of work.
  **Found by running it against a real club, not by reading it** — 137 walked,
  40 written.
- **`py_compile` AND `vite build` BOTH PASSED ON A DEAD FEATURE.** The first
  real run failed on `ManualGame.cricketstatz_match_id` not existing: the
  columns were added in raw-SQL DDL and never mapped on the ORM model — the
  same trap the `fee_members.archived_at` note already documents.
- **NUMBERED 285, NOT 282.** Local was at 281 while `origin/main` had reached
  284; two migrations sharing a revision id break Alembic outright. Check
  `origin/main` before numbering one.
- **THE RECORD BOOK IS CAPTURED GENERICALLY** (`cricketstatz_records`: title,
  headers, rows as JSONB, one live copy per club per mode) — there are ~180
  report shapes and modelling each is neither possible nor useful. Kept as its
  own archive rather than merged into our computed records: ours come from the
  scorecards we now hold, theirs cover whatever their data covers, and a record
  book that silently blends two sources cannot be checked against either.
- **REPORTS GO DARK WHEN A SUBSCRIPTION LAPSES** — `Error: Subscription
  expired`, which is exactly the state a club switching away lands in.
  `unwrap` raises a typed error for it so "their subscription ended" is not
  read as "this club has no matches". Their FAQ also says the database is
  deleted 12 months after expiry.
### The club already held its players, spelled its own way (v9.67.4)

Reported off the live leaderboard: Brad Quinsee read 9,850 runs where
CricketStatz says 10,444 — and the board listed him TWICE, along with "Michael
B. White" beside "Michael White", "Shannon J. McCleish" beside "Shannon
McCleish", and Ryan Docherty twice.

- **EVERY DUPLICATE WAS A uuid5 BESIDE A uuid4, which names the cause exactly.**
  A v5 id is one this import derived; a v4 is a row the club already had. Read
  off the live API: `Brad Quinsee`/`Quinsee, Brad`, `Michael B. White`/`White,
  Michael`, `Shannon J. McCleish`/`McCleish, Shannon`. **The club holds its
  players surname-first and CricketStatz writes them first-name-first**, so
  matching on the raw spelling matched none of them and minted a second record
  for every player the club already had — each then carrying half a career.
- **`resolve_player` DID AN EXACT `ilike` AND NOTHING ELSE.** The fix is not a
  cleverer regex, it is to use `import_ingest.match_players` — the pipeline
  BetterImport, the scorecard reader and Merge Duplicates already share, whose
  `_normalise_name` turns "Quinsee, Brad" into "brad quinsee" and whose
  `_middles_compatible` reads "Michael B. White" as "Michael White". **This is
  what "create names like the other stat import pages do" means**, and it is
  the one part of that instruction the first cut missed while doing seasons and
  grades properly.
- **ONLY `exact` IS TAKEN, and that is the matcher's own rule rather than
  caution.** Its `exact` already covers the middle-initial case. Below that it
  deliberately returns no id: an initial is not an identity, so "Crosta, T"
  must not swallow a Torey, a Tim and a Tom, and two of the club's own records
  sharing a name is the shape of a father and son. Those get their own record
  and are REPORTED by name in the import's notes, pointing at Merge Duplicates.
- **A ROLLBACK DROPS THE ROSTER CACHE TOO.** It holds players flushed since the
  last commit, so a stale copy would match against rows that no longer exist —
  the same reason the season and grade caches are cleared there.
- **A NEWLY CREATED PLAYER IS APPENDED TO THE ROSTER**, or the next card
  spelling the same new name differently mints a second row inside one import.
- **A RE-IMPORT DOES NOT REPAIR A CLUB ALREADY IN THIS STATE**, which is worth
  knowing before suggesting one: `resolve_player` finds its own row by the
  CricketStatz id before it ever looks at a name.
  `python -m app.scripts.merge_cricketstatz_duplicates <org|all> [--apply]` is
  the repair, merging through the SAME `_merge_players_core` the Merge
  Duplicates screen uses, so every per-game table is reassigned and the merge is
  undoable. The club's own record is the one KEPT — it carries the photo, the
  squad and the committee role. Dry run by default.
- **`plan_for_org` IS PURE AND THE ROUTER IMPORT IS DEFERRED INTO `main`**, so
  the planning half can be verified without dragging the auth stack in.
- **Verified** (the suite is 127 checks: the club's held player matched rather
  than duplicated, the middle-initial case, the bare initial deliberately NOT
  merged and reported instead, and the repair finding the reported pair while
  keeping the club's own record).

### The preview's "earliest" was the earliest of the most recent 999 (v9.67.3)

Reported off the preview card: **EARLIEST 2014** for a club whose history runs
back to 1953/54.

- **THE ALL-TIME LIST IS CAPPED AT 999 MATCHES, so its earliest date says
  nothing about how far the club goes back** — only how far 999 matches
  reaches. For a busy club that is about a decade. The figure was not
  approximate, it was answering a different question.
- **THE RECORD BOARDS ARE THE FLOOR, AND A FLOOR IS HONEST WHERE A GUESS IS
  NOT.** A record dated 1954 is proof there was a season in 1954, so the
  minimum year across a handful of all-time boards can only ever UNDERSTATE the
  span, never overstate it. The card says "back to at least 1954" and the first
  pass then reports the real answer (1953). Same reasoning that kept the boards
  out of the season-probing decision: sound as a floor, unsound as a bound.
- **Five boards, not all 41** — this runs on a preview, before the club has
  committed to anything, and they are cached for the import that follows.
- **A CHECK THAT MATCHES MORE THAN IT MEANS IS NOT PRECISE.** "Back to at
  least" appears in the card's label AND in the note under it, so asserting it
  appears exactly once failed against correct output. It asserts the phrase is
  present and that the old flat `Earliest` label is gone.

### THE TWO SOURCES COMPLETE EACH OTHER. IT IS AN AND (migration 293, v9.70.0, Sep 2026)

Said directly, after a per-season either/or was proposed and costed: **"You
shouldn't lose any? They should compliment each other. It shouldn't be an or,
it should be an and."** The user was right, and every note below this one that
describes choosing a winner per season describes the design this replaces.

- **CHOOSING A SOURCE PER SEASON REMOVED THE DOUBLE COUNT BY THROWING MATCHES
  AWAY, and that was measured before it was believed.** Across five of Keon
  Park's seasons, Cricket Australia holds **401** matches and CricketStatz
  **473**, each with genuine gaps the other fills — 2002 85/86, 2005 91/104,
  2011 91/117, 2019 65/82, 2024 69/84. `seasons.stats_source = 'cricketstatz'`
  hid a season's whole synced side, so a season where CA held five matches
  CricketStatz lacked lost all five.
- **SO THE DUPLICATE IS REMOVED PER MATCH.**
  `manual_games.superseded_by_game_id` pairs an imported match to the synced
  game that IS that match, `pair_prefers_import` says which half of the pair
  counts, and everything unpaired from BOTH sides counts. The club's record is
  the union.
- **THE SCORECARD IS THE IDENTIFIER, NOT THE DATE, and that is what makes the
  pairing possible at all.** A two-day match is dated by one source under the
  day it started and by the other under the day it finished — measured on the
  real data at 1 March against 8 March for the same match — so a date key
  paired only about two thirds of them. Three of our own batters with identical
  scores in one season is not a coincidence. Four ways in, deliberately
  different in kind: three shared scores at any distance; one shared score plus
  the same club within ten days; the same day against the same club (what
  carries a season CA holds no scorecards for); two shared scores close
  together (the two sources name a grade and an opposition differently often
  enough that this has to stand alone).
- **A FIFTH WAY IN EXISTS ONLY WHERE NO CARD COMPARISON IS POSSIBLE** — the
  same club within ten days when one side has no card at all. Guarded on that,
  because two cards sharing NOTHING is a strong signal these are two different
  matches against the same club. It recovers 398 of 2,800 duplicates in the
  awkward case with no wrong pairs.
- **A TIE IS REFUSED RATHER THAN GUESSED**, and the trade-off is stated rather
  than assumed: leaving a true pair unpaired counts the match twice, which is
  visible; pairing the wrong one hides a match that really happened, which is
  not. A wrong pair still counts each match once — it only mis-attributes which
  fixture it was — so the count, which is what a club checks, stays right
  either way.
- **CRICKET AUSTRALIA WINS A PAIR BY DEFAULT** because it is the live source
  and keeps its copy current. `pair_prefers_import` is the one exception: where
  the synced game carries no scorecard of ours and the imported one does, the
  import is the better record of that match and the synced game steps aside
  instead. That is "if PlayHQ is incomplete, use CricketStatz to complete",
  decided per match rather than per season.
- **CA'S OWN SEASON TOTALS ARE ALWAYS COUNTED NOW, and that is what makes the
  union work at the aggregate level.** `player_season_stats` covers Cricket
  Australia's matches and nothing else; the `manual_game` rollup beside it
  counts only the imported matches that are NOT paired, i.e. the ones CA does
  not have. Neither half can reach the other's matches, so no third branch and
  no suppression is needed. **CORRECTED in v9.70.6 below: the first cut of that
  filter also kept a paired match whose pair `pair_prefers_import`, which counts
  it twice — a season total has no row for CA's copy to step aside with. At this
  level a paired match is never counted from the import at all.** The same reasoning retires `services/season_source.py`
  — CA's per-grade aggregate (`player_season_grade_stats`) is counted in full
  and the imported scorecards paired away before they reach the grid's `held`
  side, so the by-grade cell is a union rather than a sum of two records of one
  thing.
- **THE PER-INNINGS VIEWS GOT SIMPLER, NOT MORE COMPLEX.** The pair test needs
  neither `grades` nor `seasons`, so all six lost two joins; the synced side is
  one indexed lookup against a partial unique index that is EMPTY for a club
  that has imported nothing.
- **IT RE-DERIVES; IT NEVER ACCUMULATES.** Either side can arrive after the
  other — a club has imported while a Full Rebuild was still running, which is
  how the previous design's one-shot snapshot went stale. So the pass starts
  from the data as it stands, clears the pairs it can no longer justify, and is
  idempotent. It runs per season as an import walks it (leaving a run that
  stops halfway with the seasons it reached correct), once more over the whole
  club at the end, after a full sync and a Full Rebuild, once at BOOT for every
  club holding an import (which is what stops the deploy carrying 293 showing a
  club its duplicates until something paired them), and on a button.
- **`seasons.stats_source` IS LEFT IN PLACE AND READ BY NOTHING**, the call
  migration 267 made for `vote_settings`. Rows already carrying a value are
  left as they are — destroying a club's own earlier choice to tidy up would be
  its own bug — and `superseded_years` still reads it only so the screen can
  stop reporting a decision that no longer decides anything.
- **Measured at club scale, both ways** (3,500 matches each side, 2,800 of them
  genuinely the same match): where CA holds its scorecards, all 2,800 pair to
  the right game with none wrong, in **377ms**. With a THIRD of the synced games
  carrying no card and a QUARTER of the imported ones dated a week off, 2,566
  pair correctly, 6 to a neighbouring fixture and 234 are missed, in **291ms**.
  Quadratic comparison is avoided by two indexes — a date bucket and a
  (player, runs) index — so it is near-linear rather than 12M comparisons.
- **Verified against a real Postgres**
  (`backend/verification/verify_cricketstatz_import.py`, 262 checks: every
  matching rule and both refusals, one-to-one assignment, the tie refused, the
  reported failure replayed — an import running while `games` is empty and the
  sync landing on top — the pass finding the pair afterwards and a second pass
  changing nothing, a match only CricketStatz has and a match only Cricket
  Australia has both still counted, the per-innings views keeping the synced
  side and dropping the imported twin, a synced fixture with no card preferring
  the imported copy, CA's per-grade figure counted in full with only the gap
  match added beside it, an import pairing each season as its matches land with
  a run cut off part way, undo bringing back a synced game its import had
  replaced, and the wiring asserted structurally) **with two control runs**:
  with the matcher neutered 23 of the 262 fail, reporting the reported
  `{'api': 1, 'manual': 1}`; with the hooks unwired, 3.
- **A CHECK NEEDS A REAL DUPLICATE IN THE FIXTURE.** "A season already walked is
  paired before the run moves on" failed on the first cut because the captured
  cards for that club share no date or opposition with the seeded synced games
  — there was nothing to pair, so the check could never have passed. The
  fixture seeds a synced game that IS one of the imported matches now.
- **A CHECK THAT MATCHES THE COLUMN NAME RATHER THAN THE WRITE CANNOT PASS.**
  "Nothing marks a season any more" first matched `stats_source = 'cricketstatz'`,
  which is also the WHERE clause of the read `superseded_years` still makes. It
  matches the write.
- **The neighbouring suites were re-run rather than assumed**: club records 93,
  season fold 65, shared fixtures 38, retired not out 71, rate coverage 105,
  match coverage 66, records timing 47, competitions 136.
- **NOTICED, NOT FIXED**: 234 missed pairs per 3,500 in the awkward case are
  matches still counted twice, and nothing on screen names them. The obvious
  follow-up is a "these look like the same match — are they?" review list, built
  from the near misses the matcher already scores and declines.

### THE PAIRING WAS RIGHT AND NEVER RAN (v9.70.4, Sep 2026)

Reported after v9.70.2 deployed: still 547 matches and 28 hundreds, and the
club's 2002/03 still holding all 171 games. **The code was correct — replaying
that club's four real seasons through the SHIPPED `reconcile_org` against a
local Postgres takes 706 games to 404 and writes 302 pairs.** So the pass had
simply not run, and nothing anywhere said so.

- **A SILENT LOG CANNOT TELL "RAN AND FOUND NOTHING" FROM "NEVER RAN", and that
  is what cost the round trip.** The boot sweep logged only when `changed` was
  non-zero. It logs the club count on the way in and every club's result on the
  way out now, and a failure logs its traceback rather than one line.
- **A BARE `asyncio.create_task` IS NOT KEPT ALIVE.** The loop holds a weak
  reference, so a task that suspends on its first await can be collected before
  it runs — the trap `iq_opponent`'s own `_BUILD_TASKS` already documents.
  `main._BACKGROUND_TASKS` holds it and discards it on completion.
- **A CARD QUERY BOUND TO THE CLUB'S PLAYERS ALONE SCANNED THE WHOLE
  PLATFORM'S `batting_innings`.** `_SYNCED_CARD_SQL` filtered on
  `players.organisation_id` and nothing else, so one club's question read every
  innings on the platform. Both card queries bind the ids of the games already
  loaded (`= ANY(CAST(:ids AS UUID[]))`), which is the plain restriction the
  planner pushes into the index — the same lesson the record boards' timing
  work records, and the reason `load_sides` now reads its rows BEFORE their
  cards.
- **MATCHING A WHOLE HISTORY IS SECONDS OF SOLID CPU AND MUST NOT SIT ON THE
  EVENT LOOP.** Measured with a realistic card distribution (a squad of 60,
  scores skewed low, so the (player, runs) index buckets are big): 217
  candidates per imported match at the median and **6.7s** for 3,500 each side.
  Inline, that freezes every other request the API is serving, the health check
  a deploy waits on included. `asyncio.to_thread` — verified by running a 50ms
  heartbeat alongside it, which ticked 119 times during the pass.
- **AND IT IS RETRIED NIGHTLY** (`jobs/scheduler.pair_all_imported_matches`,
  02:50 Perth). A pass that only ever fires at boot leaves a club counting both
  sources indefinitely if that one firing is lost, which is exactly what
  happened. Costs nothing once it has run: it re-derives and writes only what
  changed, and a club holding no import never appears in the list.
- **`python -m app.scripts.pair_imported_matches [<org|all>] [--apply]`** is
  the way to fix a club now and to see what happened, without waiting on any
  trigger. Dry run by default, per the house rule; a club that fails is named
  with its error rather than taking the run down.
- **THE CAUSE OF THE ONE LOST FIRING IS STILL NOT ESTABLISHED** — the log
  carried nothing to establish it with, which is the first thing fixed above.
  Every one of the four changes stands on its own merits regardless.
- **Verified** (the suite is 277 checks now: both card queries bound to an id
  list, the matching off the event loop, the boot task held, the sweep
  reporting whether or not anything changed, and the nightly retry registered)
  and the four real seasons replayed end to end through the shipped
  `reconcile_org` and the shipped script: 706 games -> 404, 302 pairs written.

### AN OLDER DEFINITION CAN NO LONGER REPLACE THE VIEW (v9.70.10, Sep 2026)

Reported plainly, after four rounds of diagnosis: *we should just be fixing the
duplicates.* Right. The duplicate logic was correct and verified; what kept
bringing them back was a process on the server rewriting two view definitions,
and an hourly repair only puts them back AFTER a club has seen the wrong
figure.

- **THE OVERWRITE SUCCEEDS ONLY BECAUSE THE COLUMN LISTS MATCH.** The pairing
  clause is a join and a WHERE, so our `v_effective_games` has exactly the
  columns a 266-era definition has, and `CREATE OR REPLACE VIEW` accepts it
  without a word. A 169-era one, which lacks `status`, already fails with
  `cannot drop columns from view` — the failure this whole hunt was read off.
- **SO BOTH VIEWS NOW CARRY `pairing_applied`, a column no older definition
  has.** `CREATE OR REPLACE VIEW` can append a column and cannot drop one, so
  ours replaces what is there and nothing older can replace ours. The overwrite
  fails loudly in the database log instead of silently doubling a career.
  Nothing selects `*` from either view and nothing depends on them, both
  checked before adding it.
- **THE DOWNGRADE HAS TO DROP FIRST**, for the same reason — a `CREATE OR
  REPLACE` back to the pre-pairing shape is exactly what is now refused. Same
  call migration 266's downgrade already had to make.
- **THE HOURLY REPAIR STAYS.** It is the net for a database that was already
  overwritten before this shipped, and for anything that drops and recreates
  rather than replacing. Belt and braces, not one or the other.
- **AND THE SUITE PROVES THE GUARD RATHER THAN DESCRIBING IT**: it takes the
  pre-pairing definition out of `DOWNGRADE`, turns it back into a `CREATE OR
  REPLACE`, applies it, and asserts it is REFUSED and the clause survives.
  Three harness sites that used to break a view by replacing it now have to
  drop it first, which is itself the guard working.
- **Verified against a real Postgres** (the suite is 304 checks) and every
  neighbouring suite re-run against the changed views: club records 93, match
  coverage 66, competitions 136, rate coverage 105, season fold 65, shared
  fixtures 38, retired not out 71, boundary counts 27.
- **STILL NOT ESTABLISHED, and now it does not matter as much**: which process
  writes the old definitions. It will announce itself in the database log the
  next time it tries, and a club's figures no longer depend on finding it.

### IT WAS OUR OWN BOOT PATH, TWO THOUSAND LINES LATER (v9.70.11, Sep 2026)

`app/main.py` applies the superseded views at **line 4319** and verifies them
three lines on — which is why the boot honestly logged `8 of 8`. At **line
5786** the migration 266 mirror loads that migration's module by file path and
re-executes `EFFECTIVE_GAMES_WITH_STATUS` and `SEASON_STATS_NET_OF_UNPLAYED`:
266's own, pre-pairing definitions of the same two views. Every boot, on every
club holding both sources, that put the duplicates straight back.

- **IT SUCCEEDS SILENTLY BECAUSE THE COLUMN LISTS MATCH.** The pairing clause
  is a join and a WHERE, not a column, so 266's version has exactly the columns
  ours has and `CREATE OR REPLACE VIEW` takes it without a word. The six
  per-innings views were never touched because 266 does not define them — which
  is the "six current, two stale" state that matches no version of this code
  and sent four rounds of diagnosis looking for an external process.
- **THE FIX IS ORDER OF OWNERSHIP, NOT A GUARD.** `superseded_ddl` owns both
  views now, so the mirror applies 266's COLUMN and INDEX and nothing else. The
  module that owns them guarantees `games.status` itself, since it runs first.
- **THE GUARD COLUMN WAS THE WRONG ANSWER AND IT TOOK THE SITE DOWN.** Adding a
  column no older definition has makes the overwrite fail loudly instead of
  silently — sound reasoning, and it turned a silent revert into a crash-loop
  at boot, because the process doing the overwriting was ours. Reverted within
  minutes. **A guard that converts a silent failure into a hard one has to be
  preceded by knowing who trips it.**
- **AND THAT CRASH IS WHAT NAMED IT.** Four rounds of instrumenting the app,
  reading the database log and chasing a second compose project found nothing;
  one hard failure printed the offending statement and the traceback pointed at
  the lifespan. Worth remembering both ways: the guard was premature AND it
  answered the question.
- **THE GREP THAT MISSED IT.** `grep "v_effective_games" app/main.py` returns
  one comment — the SQL lives in the migration file and main.py only names the
  CONSTANTS. **Searching a lifespan for a view's own name is not enough when a
  mirror imports its statements.** Search for what executes, not only for what
  is written.
- **The hourly `repair_effective_views` (v9.70.8) stays.** It is the net for a
  database already overwritten, and for anything that drops and recreates
  rather than replacing.
- **Verified against a real Postgres** (the suite is 305 checks: the mirror no
  longer naming either view, still applying the column and index, and the
  owning module guaranteeing that column itself) **with a control run**: with
  the two view statements put back in the mirror, the check fails. Every
  neighbouring suite re-run: club records 93, match coverage 66, competitions
  136, rate coverage 105, season fold 65, shared fixtures 38, retired not out
  71, boundary counts 27.

### AND POSTGRES'S OWN LOG NAMED THE SHAPE OF IT (v9.70.8, Sep 2026)

The boot check logged **8 of 8** and two of the views were the pre-pairing
definition again minutes later, on a running system. `log_statement` is off, so
Postgres only records a statement that ERRORS — and the database log already
held the answer, once per minute, on a fresh backend pid each time:

    ERROR:  cannot drop columns from view
    STATEMENT:  CREATE OR REPLACE VIEW v_effective_games AS ...
                mg.season_id AS season_id, mg.organisation_id AS organisation_id
                FROM manual_games mg

- **THAT DEFINITION IS MIGRATION 169's**, ending at `organisation_id` with no
  `status` column — the one 266 added. So a process outside this codebase was
  applying a PRE-266 definition, failing, and retrying every 60 seconds.
- **AND IT EXPLAINS WHY ONLY TWO OF THE EIGHT MOVED.** Our
  `v_effective_games` adds no COLUMNS — the pairing clause is a join and a
  WHERE — so a **266-era** definition has the identical column list and
  `CREATE OR REPLACE` accepts it silently, taking the pairing clause with it. A
  **169-era** one fails loudly. Same for the season-stats view. The six
  per-innings views are newer than anything that process knows about, so it
  never touches them. Six current and two stale, which no version of this code
  can produce, is exactly what an older one overwriting two of them looks like.
- **A SILENT SUCCESS IS INVISIBLE UNTIL YOU ASK FOR IT.** `log_statement =
  'ddl'` (a reload, no restart) is what makes the writer name itself —
  `log_line_prefix` carrying `%h` and `%a` gives the client host and
  application. **The failing statements were free evidence that had been in the
  log the whole time**; reach for the DATABASE log before instrumenting the
  application.
- **WHAT IS STILL OPEN**: which process. The pre-266 loop had stopped by the
  time this was found (zero occurrences the following day), and the successful
  writes were never logged. `log_statement='ddl'` is on now, so the next one is
  named.
- **SO THE APP STOPS DEPENDING ON THE BOOT GETTING IT RIGHT.**
  `jobs/scheduler.repair_effective_views` runs hourly: `superseded_ddl.verify`,
  and where a view has lost its clause it re-applies the SHIPPED `STATEMENTS`
  and logs what it repaired. It writes nothing when nothing is wrong, which is
  every deployment that holds no import. **This is not a substitute for finding
  the process** — it is what stops a club's career doubling in the meantime,
  because the cost of waiting is paid by whoever reads their own total.
- **THE JOB IS EXERCISED, NOT GREPPED FOR.** The suite applies the pre-pairing
  definitions out of `superseded_ddl.DOWNGRADE` — the same shape the older
  image writes — asserts the boot's own check sees them, runs the SHIPPED
  `repair_effective_views`, and asserts all eight come back and a second run
  writes nothing.
- **Verified against a real Postgres** (the suite is 302 checks) **with a
  control run**: with the job removed, 3 fail and the rest are REPORTED rather
  than crashing on the import.
- **A FUNCTION INSERTED MID-BODY SPLITS THE ONE IT LANDS IN.** The first cut
  put `verify_view_repair` after a check inside `verify_matcher`, so the rest of
  that function became part of the new one and died on a `NameError` for a local
  defined above the split. Caught by running it; a structural check would not
  have seen it.

### THE VIEW IN THE DATABASE WAS NOT THE VIEW IN THE CODE (v9.70.7, Sep 2026)

The end of the same report, and the most expensive part of it. Brad Quinsee's
career read **547 matches, 15,333 runs, 28 hundreds** against an innings list
of 336, 9,914 and 16 — his club's own hand count — with **nine shared seasons
at exactly 2.000x on BOTH runs and innings at once**. Two fixes were shipped
against it (v9.70.5, v9.70.6), both real bugs, neither this one.

- **THE PAIRING WAS RIGHT AND THE VIEW COULD NOT ACT ON IT.** Read off
  production: `v_effective_batting_innings` and its five per-innings siblings
  carried the pairing clause (`superseded_by_game_id` twice each);
  `v_effective_games` and `v_effective_player_season_stats` carried it **zero
  times** — they were the pre-pairing definitions. So every imported match was
  correctly paired, correctly dropped from the innings list, and still counted
  in the season aggregate beside Cricket Australia's own figure for the same
  match.
- **A STATE NO VERSION OF THIS CODE CAN PRODUCE, WHICH IS WHY IT TOOK SO
  LONG.** All eight views are applied by one loop over
  `superseded_ddl.STATEMENTS` inside a single `engine.begin()` transaction,
  with no try/except anywhere around it — verified by parsing the AST, not by
  reading. Six current and two stale is not a partial application; it is the
  two having been replaced afterwards by something. **What that something is
  is NOT established** — the deployed module's own statements were confirmed
  correct (`x2` and `x3`) and applying them by hand succeeded immediately.
- **THE REPAIR IS THOSE TWO STATEMENTS, AND NOTHING ELSE.** No migration, no
  re-pairing, no re-import: `CREATE OR REPLACE VIEW` with the column list
  untouched. Brad went to **372 / 344 / 10,152 / 17** the moment they ran,
  against CricketStatz's own 10,444, with `without_scorecard` falling from 173
  to 0.
- **THE BOOT CHECK HAD BEEN FINDING IT EVERY BOOT AND SAYING SO TO NOBODY.**
  `superseded_ddl.verify` has reported both views since v9.69.5 — and only ever
  logged on FAILURE, so "ran and found nothing" and "never ran" were
  indistinguishable from outside, and a `grep SCHEMA MISMATCH` over the last
  day found nothing at all. It logs the count on every boot now, missing views
  named. **Exactly the lesson v9.70.4 records for the pairing sweep, in the
  check written to catch that same class of problem.**
- **THREE CHECKS COULD NOT HAVE FAILED, AND EACH ONE COST A ROUND TRIP.** The
  diagnostic asked whether the deployed view still carried `pair_prefers_import`
  — absent from the fixed view AND from the pre-pairing one, so it answered
  False for both and read as "the fix is live". The needle that separates the
  three states is how many times the view mentions `superseded_by_game_id`:
  **3 for the current aggregate view, 2 for a current per-innings view, 0 for a
  pre-pairing one.** `VERIFIED_VIEWS` already needles that column, which is why
  `verify()` was right all along and the hand-rolled probe was not.
- **`python -m app.scripts.inspect_player_aggregate <player> [year]`** is the
  read-only diagnostic that ended it: the career header split per branch of the
  view, every row emitted for one season, the raw `player_season_stats` rows
  behind them, and what `pg_get_viewdef` actually holds. **`ops/` is not in the
  backend image** — only `backend/` is copied — so a diagnostic has to live in
  `app/scripts/` to be runnable in the container at all.
- **THE ORDER THAT WORKED, after three that did not**: measure the ratio per
  season (nine at exactly 2.000 is arithmetic, not coverage); split the figure
  by the view's own `source` column; then read the view definition back out of
  Postgres. The first two say WHICH branch, the third says WHY — and only the
  third can catch a database that disagrees with the code.
- **STILL OPEN**: what replaces those two view definitions after the lifespan
  has applied them. Until that is found, a deploy can silently put a club back
  to counting both its sources — which is what the every-boot log line now
  makes visible within seconds rather than after a club reports a doubled
  career.

### PREFERRING THE IMPORTED COPY IS A PER-INNINGS DECISION, NEVER AN AGGREGATE ONE (v9.70.6, Sep 2026)

Reported off Brad Quinsee's profile once the pairing was finally running: the
innings list read **336 innings, 9,914 runs and 16 hundreds** — the club's own
hand count — while the career header two inches above it read **508, 15,333 and
28**, and the Players list said 547 matches.

- **MEASURED PER SEASON, AND THE SHAPE NAMED THE CAUSE BEFORE ANY CODE WAS
  READ.** Every season up to 2001/02 — the years only CricketStatz covers —
  matched the innings list almost exactly. Every season from 2002/03, exactly
  the era BOTH sources hold, was **double the innings beneath it, to the run**:
  914 against 457, 1,136 against 568, 1,064 against 532, 4 hundreds against 2.
  So the per-innings views were pairing correctly and
  `v_effective_player_season_stats` was not.
- **`pair_prefers_import` IS WHY, AND THE HOLE IS IN THE DESIGN RATHER THAN THE
  WIRING.** The per-innings views are per-MATCH, so a paired synced game steps
  aside (`_SYNCED_SOURCE_JOIN`) and the imported copy answers — which is the
  whole point of preferring it where Cricket Australia holds no scorecard of
  ours. `player_season_stats` is a SEASON TOTAL with no per-match granularity:
  **there is no row to drop**, so CA's own figure carries that match whatever
  we do. Keeping the imported copy beside it in the `manual_game` rollup is the
  same match counted twice.
- **SO AT THE AGGREGATE LEVEL A PAIRED MATCH IS NEVER COUNTED FROM THE IMPORT,
  `pair_prefers_import` OR NOT.** The rule there is CA's totals PLUS the
  imported matches CA does not have at all. **Preferring the imported copy is a
  decision about which scorecard to SHOW**, and it stays where there is a row
  to drop. The v9.70.0 note claimed "neither half can reach the other's
  matches, so no suppression is needed" — true only while the flag is false,
  and it is corrected in place rather than left to mislead the next reader.
- **THE HEADER AND THE LIST ARE THEN DRAWN FROM DIFFERENT ROWS FOR THE SAME
  MATCH, AND THAT IS FINE.** For a prefer-import pair the header counts CA's
  figure and the list shows the imported card. They describe one match and
  agree on the total, which the suite asserts directly rather than checking
  each in isolation. Where they legitimately differ — CA counting a match we
  hold no scorecard for at all — `match_coverage` already explains it.
- **NOTHING IS RE-PAIRED, RE-IMPORTED OR MIGRATED.** It is a view definition,
  `CREATE OR REPLACE`d by the lifespan on every boot with the column list
  untouched, so a deploy is the whole fix and every club's figures correct
  themselves on the next page load.
- **THE GAP EXISTED BECAUSE THE SUITE ONLY EVER CHECKED `v_effective_games`
  THERE.** The prefer-import fixture asserted the synced fixture stepped aside
  and counted the manual rows, and never once summed the season aggregate — so
  six views were verified and the seventh was not. It is asserted now, on runs,
  innings, hundreds and matches.
- **Verified against a real Postgres** (the suite is 294 checks: a prefer-import
  pair counted once on all four figures, the innings list beneath it reading the
  same runs, and a match only CricketStatz holds still added on top) **with a
  control run**: with the flag put back into the aggregate branch, 6 fail —
  reporting 240 runs and 2 hundreds where 120 and 1 are right, the reported
  doubling in miniature.

### AND THEN IT REFUSED ITS OWN WORK (v9.70.5, Sep 2026)

Reported by running the script: **Cockburn Cricket Club AND Keon Park** both
failed with `duplicate key value violates unique constraint
"uq_manual_games_superseded_by_game"`, and the pairing had written nothing on
either. So the pass shipped in v9.70.4 ran the first time and then gave up
silently on every run after it — the boot sweep, the nightly job, the button
and the script alike.

- **A RE-DERIVATION MOVES A GAME FROM ONE IMPORTED MATCH TO ANOTHER, AND THE
  INDEX ONLY ALLOWS ONE HOLDER.** The write was row by row, so the new holder's
  UPDATE could land while the old one still carried the game — two rows on one
  game for an instant, the unique index refuses it, and the WHOLE transaction
  rolls back having written nothing. Nothing partial, nothing logged beyond the
  error: a club counting both its sources with the pass reporting a failure
  nobody was reading.
- **CLEAR EVERY CHANGING ROW FIRST, THEN SET THEM IN ONE STATEMENT.** A row
  keeping its pair cannot be the conflict — the assignment is one-to-one, so a
  game moving to a new holder means the old holder's own value changes too,
  which puts it in the same list. The set is one `unnest` UPDATE rather than a
  loop, which takes every lock it needs in one scan, the shape
  `apply_associations` was rewritten into after the v9.62.6 deadlock.
- **AND THE ASSIGNMENT WAS NOT STABLE BETWEEN RUNS**, which is the quieter half
  of the same report: `--apply` wrote 302 rows and a second `--apply` wrote 2
  more, for ever. Where several of our sides play one club on one day with no
  scorecards, every combination scores identically, so which imported match
  takes which synced game came down to the order equally-scored candidates were
  walked in — and that followed frozenset iteration, which is not stable
  between processes. **The ids are the final tiebreak now**, so the same data
  always gives the same assignment and a settled club is never rewritten.
- **A THREE-PASS CHECK IN ONE PROCESS CANNOT CATCH IT, and finding that out is
  what made the check honest.** Within one process the hash seed is fixed, so
  the DB idempotency checks pass against the broken code. What fails is
  `assign` run over the SAME rows in three different ORDERS — the property
  actually at stake — since the sort was stable and a tie therefore kept
  whatever order it was handed. The DB pass-writes-nothing checks are kept
  beside it: they are a real property of the write path, just not this bug's.
- **Verified against a real Postgres** (the suite is 287 checks now: two
  imported matches each holding the other's game re-derived without dying on
  the index and each landing on its own, a four-way cluster paired off one for
  one, a second and third pass writing nothing, and the same rows in three
  orders giving one assignment) **with two control runs**: with the row-by-row
  write restored, 3 fail reporting the club's own error verbatim; with the id
  tiebreak removed, the order check fails and every DB check still passes,
  which is exactly why it is there.

### A COUNT THAT CANNOT FIT THE RUNS IS NOT A COUNT (v9.70.3, Sep 2026)

Reported off StatLab's most-sixes board: Nathan Sammit **30 sixes in an innings
of 8 runs**, and Rasika Thanippullige 11 sixes off 7.

- **IT IS CRICKET AUSTRALIA'S OWN DATA, AND THAT WAS ESTABLISHED BEFORE
  ANYTHING WAS CHANGED.** The reported innings was traced to one match (Cameron
  U12 v Keon Park U12, 17 Nov 2006), which BOTH sources hold. CricketStatz's own
  card reads `R 8, M 0, 4s 1, 6s 0` and our import stored exactly that; the
  synced row for the same match reads `runs 8, balls 0, fours 1, sixes 30`,
  confirmed by fetching it live rather than inferred from the code. A scorer
  twenty years ago typed something else into the sixes box and CA has carried it
  since. **No re-sync repairs it and no parser fix reaches it.**
- **SIX RUNS PER SIX IS ARITHMETIC, NOT A JUDGEMENT.** `fours * 4 + sixes * 6 <=
  runs` holds for every innings ever played, so a count that breaks it is not a
  boundary count. `services/boundary_counts.clean` is the one rule, applied by
  the sync's per-innings write, by the season aggregate a career's totals are
  summed from, and by the CricketStatz import.
- **IT READS AS NOT RECORDED, NEVER AS ZERO** — the same call `sync.py` already
  makes for a missing ball count. A 0 says the batter hit no boundaries, which
  is a different claim from "this column cannot be read", and a NULL keeps it
  out of a total without asserting anything.
- **EACH COLUMN IS JUDGED ON ITS OWN FIRST.** In the reported innings the single
  four fits the 8 runs perfectly well and only the sixes do not, so nulling both
  would throw away a good figure. Only where the pair still cannot fit together
  (6 fours and a six in 24 runs) does the other go too.
- **THE RUNS ARE NEVER TOUCHED.** They are what every other figure on the row is
  reconciled against, and a bad boundary count is no reason to doubt them.
- **`python -m app.scripts.backfill_boundary_counts <org|all> --apply`** repairs
  what is stored — no network at all, since the runs are on the row beside the
  counts. Dry run by default, per the house rule.
- **Verified against a real Postgres**
  (`backend/verification/verify_boundary_counts.py`, 27 checks through the
  shipped rule and the shipped backfill: the reported innings losing only the
  count that cannot fit, an ordinary innings untouched, a genuine none kept as a
  none, six-off-one-ball standing and a six in a five-run innings not, the pair
  that is possible apart and not together, the runs unchanged on the stored row,
  another club's rows not this club's to repair, a second run repairing nothing,
  and **the SQL mirror and the Python rule agreeing on all 300 randomised rows**)
  **with a control run**: with the rule neutered 6 of the 27 fail.
- **NOTICED, NOT FIXED**: nothing flags these rows to a club. The counts simply
  stop being published. A "these figures could not be read" list would be its
  own change, and the same arithmetic would build it.

### OUR OWN CLUB'S NAME IS ON BOTH SIDES OF EVERY MATCH (v9.70.2, Sep 2026)

Reported off the live site after v9.70.0: no duplicate high scores, but a
career of 547 matches and 28 hundreds where the club counts about 370 and 16.
Measured, not inferred: the club's 2002/03 read **171 games — exactly Cricket
Australia's 85 plus CricketStatz's 86**. Nothing had been paired at all.

- **THE MATCHER COMPARED OUR OWN CLUB'S NAME AND SO AGREED WITH EVERYTHING.**
  `load_sides` handed `teams_agree` the concatenated `home_team + away_team` of
  both sides, and every match a club plays has that club's name on it — so
  "Keon Park 4th-XI v Croxton Utd" and "Rosebank v Keon Park" read as the same
  fixture. Every one of a Saturday's ten fixtures then looked identical, the
  tie guard refused the lot, and **6 of 86 paired**. `split_sides` takes our own
  club off first — a stored opposition wins, the club-name test is the
  fallback — which alone took it to 62.
- **ONE SHARED WORD IS NOT A CLUB.** On one real Saturday the club played
  Preston Trinity, Preston Druids, Preston YCW and West Preston. `teams_agree`
  agreed on any overlap, so all four read as one another. It now needs one name
  CONTAINED in the other ("Preston YCW" in "Preston YCW District 2nd XI") or
  two identifying words in common. An age group is stripped first, so "Preston
  U17 Trinity" and "Preston Trinity" still agree. 62 → 65.
- **WHICH OF OUR SIDES PLAYED IS WHAT TELLS ONE SATURDAY'S FIXTURES APART**, and
  it is the ONE hard no in the matcher: our 2nd XI's match is never our 1st
  XI's, however well the date and the opposition agree. `side_marker` reads it
  from either spelling ("2nd-XI", "2nd XI", "1's", "U17") and says nothing for a
  bare "Keon Park". 65 → 77.
- **A GRADE LETTER IS NEVER READ AS A TEAM NUMBER.** A Grade is not always the
  1st XI — this club's 3rd XI plays D Grade and its 4th plays E — so mapping the
  letters onto team numbers would confidently pair the wrong fixtures. Only a
  number the name itself carries counts.
- **A CLUSTER THAT CANNOT BE TOLD APART IS PAIRED OFF, NOT REFUSED, and that
  reverses v9.70.0.** Refusing a tie sounds safer and is not: Cricket Australia
  writes both of a Saturday's fixtures as a bare "Keon Park", and refusing every
  such tie left 2011/12 reading 149 games against a true ~117. Pairing them off
  gets the COUNT right whichever way round they go, because both fixtures are in
  both sources, and the strongest-first order means the scorecards decide it
  wherever there are any. **The cost is stated rather than hidden**: where one
  source alone holds one of two indistinguishable fixtures and the other source
  alone holds the other, pairing them loses a match — which needs a club to have
  played one opposition twice in a day with each source missing a different one,
  and is worth less than the double count refusing guarantees.
- **Measured on the club's own seasons, with no scorecards read at all**:
  2002/03 171 → 89 (CA 85, CS 86), 2006/07 180 → 108, 2011/12 208 → 122,
  2019/20 147 → 85; four seasons, **706 → 404**. In production the scorecards
  are loaded too and are the stronger signal.
- **Measured at scale in the worst realistic shape** — four of our sides out
  against ONE opposition club every Saturday, Cricket Australia writing every
  one as a bare "Keon Park", a third carrying no card of ours and a quarter
  dated a week off: **all 2,800 matches pair, none missed, and the club counts
  2,800 rather than 5,600**, in under a second. 468 pair to a sibling fixture
  from the same day — a mis-attribution, not a miscount.
- **Verified** (the suite is 272 checks now: our own side and the opposition
  told apart whichever way round the fixture is written, a stored opposition
  taken at its word, two clubs sharing one word not the same club, a name
  contained in another still agreeing, an age group not telling two clubs apart,
  the side marker read from every spelling, a grade letter never read as a team
  number, our firsts' match never paired to our seconds', and a cluster nothing
  can tell apart still counted once each) **with two control runs**: with the
  matcher neutered 25 of the 272 fail; with our own name compared and one shared
  word agreeing — the reported bug — 3 fail on exactly that.
- **A MEASUREMENT NEEDS A REALISTIC FIXTURE.** The scale test's opposition clubs
  were named "Club 12", whose only token an age-group strip removes, so the
  harder run read 1,866 of 2,800 for a reason that exists nowhere outside the
  harness. Real names are what it measures now.
- **NOTICED, NOT OURS**: Cricket Australia's own feed carries impossible
  boundary counts on some old junior cards — verified live, `runs: 8, balls: 0,
  fours: 1, sixes: 30` on a 2006 Under 12 innings — which tops the most-sixes
  record board. The CricketStatz import reads that same card correctly (8, 1
  four, 0 sixes). See the note below.

### A SEASON CHANGES OVER AS ITS OWN MATCHES LAND (v9.69.2, Sep 2026)

Reported off Keon Park's Records with the import still going: duplicate high
scores again, on **season 57 of 73**, with the count "past 1900 scorecards and
we're way over what I expect".

- **THE IMPORT WAS FINE. MY OWN CHANGEOVER WAS THE BUG, and it is the mistake
  v9.68.4 warns about pointed the other way.** That note argues against marking
  the seasons UP FRONT, correctly: the views act the instant the marker lands,
  so a season not yet walked would read from neither source. It then landed as
  one write at the END of the whole run — which leaves every season ALREADY
  walked reading from BOTH for the forty-odd minutes the rest of it takes. A
  club watching its own record board sees exactly that and reports duplicates.
- **THE EVIDENCE SAID WHICH HALF WAS WRONG BEFORE ANY CODE WAS READ.** The
  board doubled 2002/03 — a season the run had passed — and showed 2011/12 and
  2013/14 singly, seasons it had not reached. Only the walked seasons were
  double, which is the signature of a changeover that has not happened yet, not
  of an import writing twice.
- **PER SEASON, AFTER ITS OWN MATCHES COMMIT, THERE IS NO WINDOW FOR EITHER.**
  A season is on Cricket Australia or fully across, never both and never
  neither — and a run that stops halfway leaves precisely that state rather
  than a club to repair. It is the same unit the matches already commit in:
  one match at a time inside a season, one marker per season.
- **THE END-OF-RUN WRITE STAYS AS A BACKSTOP**, for a season whose own year
  cannot be read off its label — which would otherwise be imported and then
  never marked at all.
- **THE SCREEN SAYS HOW FAR THROUGH THE CHANGEOVER IT IS** (`replaced_done`),
  because the changeover is now something a club can watch happen. The caption
  used to promise it in the future tense, which is exactly the reading that
  makes a doubled board look like a fault rather than a queue.
- **Verified against a real Postgres** (the suite is 200 checks now: the run cut
  off part way by refusing a scorecard from the LAST season in the plan — a real
  network failure, the one exception `run_import` re-raises rather than noting —
  then the walked season marked and the unreached one left to the sync) **with
  TWO control runs, one per check**: marking only at the end fails "a season
  already walked is marked before the run moves on"; marking up front fails "a
  season the run never reached is left to the sync". The pair fails both ways,
  which is what stops either wrong design passing.
- **A CONTROL THAT DOES NOT ACTUALLY STOP THE RUN PROVES NOTHING.** The first
  cut raised from a patched `import_match`, which sits inside a `try/except
  Exception` that notes the failure and carries on — so every season was still
  walked, the end-of-run backstop marked everything, and both checks passed
  against the broken code. It refuses a SCORECARD now, the one place a
  `CricketStatzError` propagates.
- **A CHECK THAT LEAVES THE FIXTURE CHANGED BREAKS ITS NEIGHBOURS.** The
  part-way run clears the markers and re-marks only one year, so it runs at the
  END of its section rather than in the middle of it — three later checks read
  as failing until it was moved.
- **Driven in Chromium** (52: the count of shared seasons moved so far while
  running, the future-tense promise gone, and the count dropped once every one
  has moved) **with a control run**: 2 fail.
- **NOT FIXED BY THIS, and worth saying plainly**: an import already in flight
  when this deploys still doubles until it finishes, because its remaining
  seasons are marked by the old end-of-run write. The board corrects itself the
  moment the run completes.

### EVERY EFFECTIVE VIEW APPLIES THE SEASON'S SOURCE (migration 291, v9.69.8, Sep 2026)
**SUPERSEDED BY v9.70.0 above — the source rule is now a per-MATCH pairing,
not a season's marker. The eight views and the boot check still exist; what
they test changed.**


Reported off the record boards with a screenshot: Heath Shephard's 270 listed
TWICE for 2002/03, Princely Emmanuel's 206\* twice, David Nelson's 171 twice,
and a career at **14,806 runs from 527 matches**. Said plainly: *we should
NEVER double count games.*

- **287 FILTERED TWO VIEWS AND THERE ARE EIGHT.** `v_effective_games` and
  `v_effective_player_season_stats` carried the rule; the six PER-INNINGS
  views — batting, bowling, fielding, fall of wickets, partnerships, bowler
  wickets — never did. So for a season read from CricketStatz both the synced
  innings and the imported innings were present, and every century, wicket and
  catch was counted from two sources. The record boards read per-innings rows,
  which is why they doubled while the club's game count looked right.
- **THE FIX IS THE RULE APPLIED EVERYWHERE, NOT ANOTHER PATCH.** All eight now
  live in `superseded_ddl.STATEMENTS`, and `VERIFIED_VIEWS` names all eight, so
  the boot check that reads the schema back covers every one of them. A ninth
  effective view added later must join this list or the check will not know
  about it.
- **EACH IS TAKEN FROM THE MIGRATION THAT LAST DEFINED IT** (075, 038, 147,
  092, 147, 093), the rule this file already records — `CREATE OR REPLACE VIEW`
  cannot change the output columns, so re-issuing an older definition aborts.
- **EVERY COLUMN IS QUALIFIED, because joining `games` makes a bare `id`
  ambiguous.** The originals selected unqualified names; the filtered form
  cannot.
- **LEFT JOIN THROUGHOUT, and that half is load-bearing.** An innings whose
  game has no grade is ordinary — a manual upload need not carry one — and an
  inner join would drop it silently. With a LEFT JOIN the season is NULL and
  `NULL IS DISTINCT FROM 'cricketstatz'` is TRUE, so it is kept, exactly as
  `v_effective_games` already does it. The suite pins it.
- **THE JOINS ARE ALL ON PRIMARY KEYS, so they add no rows.** A view that
  fanned out would inflate every figure it feeds rather than deflating it.
- **THE DOWNGRADE HAD TO LEARN THEM TOO.** Undoing 287 drops
  `seasons.stats_source`, which fails while six views still reference it —
  found by running it. `_per_innings(..., filtered=False)` regenerates the same
  column list with the joins removed, from the SAME spec list, so the two
  directions cannot drift.
- **Verified against a real Postgres** (the suite is 234 checks now: the same
  270 from both sources counted once under each choice, all six views dropping
  the superseded side, and an innings on a grade-less game kept) **with a
  control run**: with the per-innings views left unfiltered, 18 fail —
  reporting the reported `{'api': 1, 'manual': 1}` and the boot check naming
  all six.
- **FIVE OF THE NEW CHECKS COULD NOT HAVE FAILED AS FIRST WRITTEN.** They
  asserted 0 rows in the five non-batting views for a game that had no rows in
  those tables at all. The fixture seeds one synced row in each now.
- **The neighbouring suites were re-run rather than assumed**: club records 93,
  season fold 65, shared fixtures 38, retired not out 71, rate coverage 105,
  match coverage 66.
- **THIS MODULE NOW OWNS `v_effective_batting_innings`, WHICH MEANS IT CARRIES
  EVERYONE ELSE'S CHANGES TO IT.** Migration 291 landed on `main` in parallel,
  giving `manual_batting_innings` its own `caught_behind` and re-issuing the
  view to select it. `superseded_ddl` re-issues that view LAST in the lifespan,
  so selecting `NULL::boolean` there would silently revert that feature on
  every boot. The suite pins it structurally. **A change to any of these eight
  views has to be made HERE, or it lasts until the next restart.** The
  migration was renumbered 291 → 292 for the same collision — check
  `origin/main` at the moment you merge, not only when you first number one.

### THE PER-GRADE AGGREGATE IS A SECOND TABLE, AND IT DOUBLED TOO (v9.69.7, Sep 2026)

Reported after an undo and a fresh import: a career back to nearly 600 games.
Not the career header this time — the **by-grade grid**, which was reading
2002/03 as 28 where CricketStatz has 14, every shared season exactly doubled,
with the header two inches above it correct.

- **`player_season_grade_stats` IS CRICKET AUSTRALIA'S OWN PER-GRADE AGGREGATE
  AND THE EFFECTIVE VIEWS DO NOT COVER IT.** Migration 287 filters
  `v_effective_games` and `v_effective_player_season_stats`; this is a third
  table, read directly by the grid and by two record boards. Marking a season
  as read from CricketStatz did nothing to it.
- **THE GRADE NAMES DO NOT MATCH, WHICH IS WHY IT ADDS RATHER THAN ONE
  WINNING.** Cricket Australia files the season under "NMCA - Jika Shield";
  CricketStatz files the same cricket under "A-GRADE". The grid's own
  `max(held, claimed)` reconciles per (season, GRADE), so it never compares
  them — they land in different cells and sum. A reconciliation that looks
  safe is not safe across two sources that name their grades differently.
- **`services/season_source.ca_aggregate_clause(alias)` is the one definition**,
  the same shape `grade_scope` and `game_status` already use. Expressed against
  a `seasons` alias the query already joins, **never as a correlated EXISTS** —
  these run on the record boards, where a per-row subplan is the trap
  `records.py`'s own timing notes document.
- **One of the two record boards joined no `seasons` row at all** and had to be
  given one; the other already had it.
- **THE SECOND `JOIN seasons sc` IN THE GRID IS NOT THIS TABLE.** It belongs to
  the manual per-grade adjustment read, which goes through
  `v_effective_player_season_stats` and is therefore already filtered. Patching
  by text match hit both; it is patched by position.
- **Verified against a real Postgres** (the suite is 225 checks now: CA's
  figure read on its own, the season switched to CricketStatz dropping those
  rows AND the grade they were filed under, and handing the season back
  counting them again) **with a control run**: with the clause emptied, both
  fail and the grid reports the reported 14 alongside the imported cricket.
- **NOTICED, NOT FIXED**: `iq_team` and `iq_trends` read the same table for
  internal analytics, and `import_reconcile` for its own reconciliation. None
  is a club-facing stats figure and each needs its own look.

### THE HONOUR BOARD RUNS ON ITS OWN (v9.69.6, Sep 2026)

Asked while checking the awards: a club whose whole CricketStatz history had
imported — 3,556 matches — read **zero honours on every player**.

- **THE NOTES PASS IS THE LAST PHASE OF AN IMPORT, so it is the first thing a
  run loses.** Matches, then the record book, then the honour board. A redeploy,
  a stop or a network failure after the matches are in leaves a club with its
  whole history and no honours, and the only recovery was to re-import — which
  re-pulls every scorecard for a pass that needs none of them. `NOT BUILT: no
  endpoint runs the notes pass alone` is what the v9.68.0 note said; this is it.
- **IT REUSES THE IMPORT'S OWN BATCH ID**, so the honours it writes are removed
  by undoing that import exactly as if they had been read during it, and the
  Awards screen lists them under the same batch. A separate batch would leave a
  club able to undo the import and keep an honour board pointing at it.
- **IT RUNS AGAINST THE MOST RECENT IMPORT THAT HAS NOT BEEN UNDONE**, and
  refuses when there is none: the honour board is read off the players the
  import creates, so there is nothing to read notes for.
- **A SECOND PASS RE-STAMPS RATHER THAN DUPLICATING**, the same guard the
  import's own re-read already uses.
- **THE BUTTON IS ONLY OFFERED WHERE THERE IS NOTHING TO SHOW** — a club whose
  honours are already in does not need it, and a control that can only answer
  "everything is fine" is worse than none.
- **Verified against a real Postgres** (the suite is 221 checks now: a club that
  has lost its honour board, the pass putting all 12 back, NO scorecard re-pulled
  to do it, the run reporting itself finished, the honours filed under the
  import's own batch so undo still takes them, and a second pass adding nothing)
  **with a control run**: with the pass removed, 2 fail — the board stays empty
  and the undo reports no honours to remove.
- **NOT ESTABLISHED**: why the live run's notes phase produced nothing. It may
  never have been reached. The pass is now recoverable either way, which is the
  part that matters to a club.

### A MIGRATION RECORDED AS APPLIED IS NOT EVIDENCE ITS EFFECT IS THERE (v9.69.5, Sep 2026)

The end of the same report, and the most expensive part of it. The club's
seasons were correctly marked — 73 of 74 reading `cricketstatz` — and
`v_effective_games` **carried no clause to act on them**. The marker was live,
the view was not, and every screen counted both sources.

- **THE DDL WAS NEVER WRONG.** Run by hand against that same database, all five
  statements applied cleanly and the site was correct within seconds: 2002/03
  went 171 to 86, 2011/12 208 to 117, the club 5,345 games to 3,563, and
  Michael White's career landed on CricketStatz's own figures exactly
  (325/324/8,405). So the boot path had simply not run them — while
  `alembic_version` said 290.
- **AND NOTHING ANYWHERE NOTICED, WHICH IS WHAT MADE IT EXPENSIVE.** Three
  rounds were spent inferring a cause from the outside — a snapshot that went
  stale, a run predating a deploy, a marker that would not set — each plausible,
  each wrong, because production's schema could disagree with the code and no
  surface reported it. **The one question that settled it took a single
  `pg_get_viewdef`.**
- **SO THE BOOT READS THE SCHEMA BACK.** `superseded_ddl.verify(conn)` asks
  `pg_get_viewdef` what Postgres actually holds, and the lifespan logs a
  SCHEMA MISMATCH error naming the view and the consequence. It reports and
  never raises — a check that stops the app is worse than the thing it checks
  for, and this one exists precisely because a silent mismatch is survivable
  for months.
- **A view absent from the database reads as False rather than raising**, for
  the same reason: `to_regclass` returns NULL rather than erroring on a name
  that is not there.
- **Verified against a real Postgres** (the suite is 215 checks now: a sound
  view reported sound, a view deliberately replaced with its pre-287 definition
  caught, and the shipped statements putting it back) **with a control run**: a
  `verify` that always answers "fine" fails the middle check, which is the only
  one of the three that can catch a real mismatch.
- **NOT ESTABLISHED, and worth saying plainly**: why the boot path did not run
  the statements on that deploy is still unknown. The check now reports it the
  moment it happens rather than after a club reports doubled figures.

### ONE SOURCE PER SEASON, DECIDED BY THE DATA (migration 290, v9.69.4, Sep 2026)
**SUPERSEDED BY v9.70.0 above. Choosing one source per season is exactly what
lost the matches only the other source held; kept here because the reasoning
about snapshots going stale is still why the pairing re-derives.**


Reported off Keon Park's Records with the import running: duplicates again, and
a career at **14,966 runs against CricketStatz's 10,444** — the exact figure
v9.68.3 was supposed to have settled.

- **MEASURED, NOT INFERRED, AND THE MEASUREMENT NAMED THE CAUSE.** Every shared
  season held EXACTLY synced + imported — 2002: 85 + 86 = 171, 2005: 91 + 104 =
  195, 2011: 91 + 117 = 208, 2013: 81 + 95 = 176, 2019: 65 + 82 = 147 — against
  CricketStatz's own per-season counts fetched live. Pre-2000 seasons, which
  the sync does not reach, held the imported copy alone. So the import was
  faithful and nothing was being written twice: the synced side simply was not
  stepping aside.
- **THE CHOICE WAS A SNAPSHOT TAKEN ONCE, AND THAT IS THE WHOLE BUG.**
  `synced_coverage` ran at the START of the run and the overlap was frozen from
  it. A club whose synced games were not in `games` at that instant — a Full
  Rebuild still running, a sync that had not landed — read as having NO overlap,
  so nothing was skipped, nothing was marked, and once the synced side arrived
  the club counted both with nothing on screen to say so. v9.69.2 moved the
  marking earlier and could not help: the list it marks from was already wrong.
- **SO THE RULE IS AN INVARIANT NOW, NOT A STEP.** A season that receives a
  CricketStatz match is set to `'cricketstatz'` **in the same transaction as the
  match**, in `import_match`. There is no ordering to get right, no end-of-run
  write, nothing to recompute, and a run that dies halfway leaves every season
  it walked correct.
- **UNCONDITIONAL, WHICH IS WHAT REMOVES THE DEPENDENCE.** A season the sync
  does not reach has no synced games to step aside, so marking it costs nothing
  — and the marker then owes nothing to the overlap having been worked out
  right. The club's PlayHQ-or-CricketStatz choice is expressed by whether the
  matches are imported at all (`skip` writes none into a shared season), which
  is the honest expression of it.
- **THREE STATES, AND NULL IS ONLY SAFE BECAUSE OF THE INVARIANT.**
  `'cricketstatz'` counts the imported side, `'playhq'` counts the synced side,
  NULL counts both — which can never double, because NULL and imported matches
  cannot coexist.
- **HANDING A SEASON BACK SETS `'playhq'`, NOT NULL, and the old confirm
  admitted the bug in writing**: "both will be counted until you undo the
  import". A club asking for PlayHQ back was being given the double count. The
  imported side steps aside instead, so exactly one source is counted whichever
  way the club decides.
- **IT IS NEVER APPLIED TO A SEASON THE SYNC DOES NOT REACH.** There is nothing
  to hand back to, and `'playhq'` there would hide the imported matches and
  leave the season empty — the "neither source" failure from the far end.
- **THE BACKFILL IS IN `STATEMENTS`, SO IT SELF-HEALS ON EVERY BOOT.** Any
  season holding a CricketStatz match with no source recorded is one the club is
  counting twice, whatever put it there. Guarded on NULL, so it never overrides
  a decision the club has made and a second run writes nothing. **It repairs the
  reported club with no re-import.**
- **MIGRATION 290 RE-RUNS 287'S OWN STATEMENT LIST.** Every statement is
  idempotent, so a database already at 287 picks up the added clauses and the
  backfill; the lifespan mirror does the same on every boot.
- **`resolve_season` HANDS BACK A `Season`, NOT AN ID**, so the first cut's raw
  `UPDATE ... WHERE id = :s` bound a repr and raised — swallowed by the
  per-match `except` as a note, with **zero matches written**. Setting it on the
  ORM row instead needs no cast and leaves no stale in-memory copy. Found by
  running it.
- **THE SUITE HAS TO UNWIND NEWEST-FIRST.** 287's views read
  `manual_games.cricketstatz_import_id`, so 285's downgrade cannot drop that
  column while they stand. Alembic gets this right for free; the suite did not.
- **Verified against a real Postgres** (`verify_cricketstatz_import.py`, 212
  checks: the reported failure replayed — the import writing while `games` is
  empty, then the sync landing on top — every season it wrote into marked, the
  synced side not counted with it, handing back counting the synced game
  INSTEAD of as well, a season with no synced games left alone, and the repair
  asserted to be part of the shipped statement list rather than reached for
  directly) **with two control runs**: the snapshot design fails 5, reporting
  the reported `{'api': 1, 'manual': 1}`; hand-back clearing to NULL fails 2.
- **A CHECK THAT MATCHES MORE THAN IT MEANS IS NOT A CHECK.** "the repair is
  part of the shipped statement list" first looked for a statement carrying both
  `cricketstatz_import_id` and `stats_source` — which the VIEWS now do, so it
  passed with the backfill unwired. It matches `UPDATE seasons` now.

### AND UNDOING ONE HAD TO HAND THOSE SEASONS BACK (v9.69.3, Sep 2026)

Found while checking a live club's figures after the fix above, not from a
report — and it is the same "neither source" failure reached from the other
end.

- **UNDO REMOVED THE IMPORTED MATCHES AND LEFT THE MARKER STANDING.** Making
  CricketStatz the record only ever HIDES the synced copy (migration 287), so
  an undo that deletes the imported matches without clearing
  `seasons.stats_source` leaves the season reading from NEITHER — empty on
  every screen, with nothing to say why, and the club's own Cricket Australia
  data sitting there untouched and invisible. The recovery was a Super Admin
  pressing "hand back", which nobody would know to do.
- **CLEARED PER SEASON, NEVER CLUB-WIDE.** A season still holding an imported
  match from ANOTHER import is still genuinely read from CricketStatz and keeps
  its marker; only a season this undo has just emptied goes back to the sync.
  `NOT EXISTS (... cricketstatz_import_id IS NOT NULL)` is the whole test.
- **THE UNDO SAYS WHICH SEASONS WENT BACK** (`seasons_handed_back`), and the
  confirm says it will happen before it does — a season quietly changing source
  is exactly the kind of move that reads as data going missing.
- **Verified against a real Postgres** (the suite is 205 checks now: two
  superseded seasons with their synced games hidden, undo handing back only the
  one it emptied, the synced games counted again, the count reported, and the
  season another import still covers keeping CricketStatz as its record) **with
  a control run**: with the clear removed, all 4 fail — the club's synced games
  read as 0 with the imported ones gone too.

### AND WHICH SOURCE IS THE RECORD IS THE CLUB'S CALL (migration 287, v9.68.4)
**SUPERSEDED BY v9.70.0 above. `seasons.stats_source` is read by nothing now.**


Asked for straight after: "CricketStatz should overwrite PlayHQ in the same way
a historical import does where we believe the CricketStatz data more than the
PlayHQ data."

- **`seasons.stats_source = 'cricketstatz'` IS THAT DECISION, AND IT IS APPLIED
  ON READ.** The same call migration 060 made for cross-club scoping and 266
  for washouts: correct it in the effective view, once, so every reader moves
  together. Nothing is deleted, the sync keeps running and keeps the synced copy
  current underneath, and clearing the marker puts it straight back with no
  re-pull and no migration. A club changing its mind is one UPDATE.
- **TWO VIEWS CARRY IT, AND BOTH ALREADY HAD THE JOIN.** `v_effective_games`'s
  synced branch already `LEFT JOIN`s seasons, and
  `v_effective_player_season_stats`'s `api` branch already has a `WHERE EXISTS`
  reaching the season for the org check — so this is one extra condition in each
  rather than a new join, and it costs nothing on a club that has superseded
  nothing.
- **BOTH HALVES ARE NEEDED AND THEY ARE DIFFERENT HALVES.** The games view stops
  the synced MATCHES being counted; the season-stats view stops Cricket
  Australia's own season AGGREGATES being counted. Suppressing only the games
  would leave every career total still reading from both, since a career sums
  `v_effective_player_season_stats`. The suite pins each separately, and the
  control run fails on exactly those two.
- **THE IMPORTED SEASON IS STILL COUNTED — ONCE.** The view's own `manual_game`
  branch (migration 037) rolls the imported matches up per (player, season,
  grade), so stepping the synced side aside leaves the CricketStatz figures
  standing rather than emptying the season.
- **THE SEASONS ARE MARKED AFTER THE MATCHES ARE IN, never before.** The views
  act the moment the marker lands, so marking first would leave the club looking
  at a season with neither source in it for as long as the import took — and a
  run that died halfway would leave it that way for good. **This shipped as one
  write at the END of the whole run, which is the other half of the same
  mistake and was reported the same week — see v9.69.2 above.** It is per
  SEASON now, as each one's own matches land.
- **THERE IS DELIBERATELY NO OPTION THAT KEEPS BOTH.** The earlier
  `include_synced_years` boolean had one, and holding two copies IS the double
  count this exists to prevent. It is `synced_years: 'skip' | 'cricketstatz'`
  now — leave those seasons to the sync, or make CricketStatz the record for
  them.
- **HANDING A SEASON BACK IS INSTANT** (`POST /superseded/clear`), because the
  marker was the only thing hiding the synced copy. The confirm says the
  imported matches stay imported, so both will count until the import is undone
  — which is true, and is the one thing a club could otherwise get wrong.
- **The sync is deliberately NOT stopped for a superseded season.** Keeping it
  running is what makes handing the season back instant and complete; stopping
  it would trade that for a saving nobody asked for and a Full Rebuild later.
- **Verified against a real Postgres** (`verify_cricketstatz_import.py` is 193
  checks now: the seasons marked, the synced games and CA's own season totals
  both stopping being counted, the imported matches still counted, the raw rows
  still present, and handing them back counting the synced games again) **with
  two control runs**: with the two view clauses removed 2 fail, and with the
  'cricketstatz' branch neutered, 4.
- **A CHECK WITH NOTHING TO SUPPRESS CANNOT FAIL.** The first cut had no
  `player_season_stats` row in the fixture at all, so "CA's own season totals go
  too" passed with the clause removed. The fixture seeds one per synced season
  now, and asserts the raw rows survive.
- **`games.raw_payload` IS `JSON` ON THE ORM MODEL AND `JSONB` IN THE DATABASE
  THE MIGRATIONS BUILD**, so a `create_all` harness gets the narrower type and
  the view's own `NULL::jsonb` cannot union with it. The suite reconciles it;
  the app is unaffected, but the divergence is real and is worth a look on its
  own.

### THE SAME CRICKET FROM TWO SOURCES COUNTS IT TWICE (v9.68.3, Sep 2026)

Reported off Keon Park's Records mid-import: the Highest Individual Scores
board listed every top score twice — Heath Shephard 270 twice, Princely
Emmanuel 206* twice, David Nelson 171 twice — and Brad Quinsee's career read
**14,966 runs from 495 innings where CricketStatz has 10,444 from 367**.

- **THE IMPORT WAS FAITHFUL. THE CLUB WAS HOLDING THE SAME MATCHES FROM TWO
  SOURCES.** Established by measurement, not inference: CricketStatz serves
  **3,556** matches for club 93931 across all 167 seasons and exactly **4** on
  15 Mar 2003; BetterCricket held **5,416** and **8**. Grouping the club's
  games by grade name splits cleanly into three families — the shouty
  CricketStatz names (`A-GRADE`, `UNDER 12`, 2,324 games, 1953-2026, every one
  with `games.status` NULL), and Cricket Australia's own (`NMCA - Jika Shield`,
  `03 - All Things Safety Wear Mash Shield`, ~3,000 games, every one carrying a
  status). **The club syncs from CA and imported its whole CricketStatz history
  on top.** Every match from the year the sync reaches back to existed twice.
- **THE OLD SEASONS WERE THE TELL.** 1969/70, 1991/92 and 1994/95 appeared
  ONCE on the board while 2002/03, 2011/12 and 2013/14 appeared twice — exactly
  the years CA covers. A pure query fan-out would have doubled all of them.
- **RULED OUT FIRST, EACH BY A QUERY RATHER THAN BY READING THE CODE**: the
  source (999 all-time rows, 999 distinct ids, no fixture repeated in one
  response, no match id under two seasons), a duplicated game (5,020 of 5,037
  fixtures had exactly one row — the 17 with two are a real U12 and U14 side
  playing the same club on one day), a repeated innings in a card (25 cards of
  2002S, none), the team matcher (correct on twelve real names), and a JOIN
  fan-out (`v_effective_games` and `v_effective_batting_innings` are plain
  UNION ALLs, and every join in `records.py`'s batting chain is on a primary
  key). The paging artefact that briefly suggested a fan-out was mine:
  `/organisations/{id}/results` ignores `limit`, so concatenated "pages" are
  the same rows over again.
- **SO THE IMPORT SKIPS THE SEASONS THE SYNC ALREADY COVERS**, keyed on the
  SEASON's year so a November and the following March land together
  (`synced_coverage`). CricketStatz is for the history the sync cannot
  reach — a club onboarded through Cricket Australia typically has a decade,
  and CricketStatz has seventy years.
- **IT IS A SKIP, NOT A MERGE, AND THAT IS THE HONEST LINE.** Deciding which of
  two records of one match wins would mean matching a CricketStatz fixture to a
  CA one across two naming schemes ("Keon Park 1's 'A-Grade'" against "Keon
  Park CC 1st XI") and then overwriting a live, self-maintaining source with a
  frozen snapshot. Leaving the covered years alone keeps one record of each
  match and needs no guess.
- **A CLUB CAN ASK FOR THEM ANYWAY** (`include_synced_years`), because a club
  that trusts CricketStatz over its own sync is entitled to — but it is opt-in,
  the checkbox says it will hold both, and the default can never double a
  club's records by accident.
- **THE OVERLAP IS ON SCREEN BEFORE ANYTHING RUNS.** `inspect_club` reports
  `synced_games` and `synced_years`, so the preview names how many matches the
  club already syncs and which years are being left out — rather than the club
  discovering it later as a career total half as large again as it should be.
  The running import repeats it, and it lands in the import's own notes.
- **RECOVERY for a club already in this state**: undo the CricketStatz import
  (it removes exactly what that import wrote, matches, record boards and
  honours alike) and run it again. The default now leaves the synced years
  alone.
- **Verified against a real Postgres** (`verify_cricketstatz_import.py` is 186
  checks now: the covered years known and a year the sync cannot reach not
  claimed, the covered seasons left out of the plan, no manual game written in
  them, the older history still imported, the club told, the opt-in bringing
  them across, and a club that has never synced having nothing to skip) **with
  a control run**: 3 of the 186 fail with the guard neutered, and the seasons
  the sync covers are imported on top.
- **NOTICED, NOT FIXED**: nothing detects the overlap for a club that ALREADY
  holds both. The undo-and-re-import above is the path; a screen that reports
  "these N matches are held twice" would be its own change.
- **ALSO NOTICED**: `v_effective_batting_innings` emits `batting_innings.id`
  and `manual_batting_innings.id` unchanged, and both are `SERIAL` — so the
  view's `id` is NOT unique for a club holding both. Nothing in the record
  queries keys on it today, which is why this has never bitten, but it is one
  `DISTINCT ON (id)` away from being a real bug.

### A MERGE MOVES A RECORD; IT MUST NEVER DELETE ONE (v9.68.1)

Reported off Brad Quinsee's profile the day after the duplicate fix: merging
his two records dropped roughly half his career — 178 matches and 4,925 runs
where CricketStatz has 367 innings and 10,444 runs, and a season table starting
in 2002/03 for a man capped in 1982-83.

- **`_merge_players_core` WAS WRITTEN FOR THE SYNCED CAREER AND NEVER TOUCHED
  THE MANUAL ONE.** It reassigns `batting_innings`, `bowling_spells`,
  `game_appearances`, `player_season_stats` and friends — and not one
  `manual_*` table, which is where an uploaded scorecard AND **every match a
  CricketStatz import writes** actually live. All of them are `ON DELETE
  CASCADE` on `players.id`, so the delete at the end of the merge **destroyed**
  the removed record's whole career rather than moving it, with nothing in the
  undo log to hand back. **This is the fourth time this function has had this
  bug** (`bowler_wickets`, `player_season_grade_stats`, `imported_stats` before
  it) and the AFL merge's own note documents the fifth.
- **THE HONOUR BOARD WENT THE OTHER WAY AND WAS JUST AS LOST.**
  `player_achievements` has no foreign key at all, so its rows were ORPHANED
  rather than deleted — quieter, and invisible on every screen, since each read
  joins `players`.
- **`services/merge_carry.CARRIED` IS THE LIST, and it is one definition shared
  by the merge and the undo** so the two cannot disagree about what moved. A
  table that records what a player DID belongs on it. `merge_logs.carried_row_ids`
  is one JSONB blob keyed `"<table>.<column>"` rather than a column per table,
  since the shape is uniform.
- **THE KEEPER'S ROW WINS A COLLISION, and the join is `IS NOT DISTINCT FROM`,
  not `=`.** Part of a unique key can be NULL — a season adjustment with no
  grade is the club's whole-season correction — and `=` never matches it, so
  the duplicate would slip through and the move would then fail on the very
  index the de-dup exists for.
- **AN ID'S TYPE SURVIVES THE JSONB ROUND TRIP, deliberately.** asyncpg infers a
  bound array's type from its ELEMENTS, so a list of strings cannot be cast to
  `int[]` at the other end however the SQL is written. Integer ids are kept as
  integers and only the UUID table's as strings. Found by running it.
- **A TABLE THAT IS NOT THERE IS SKIPPED, not a 500.** `player_achievements` and
  `club_honour_entries` are lifespan-created raw SQL, so a database that has not
  run it has not got them; `to_regclass` is what stops a merge failing over one.
- **THE IMPORT'S OWN IDENTITY MOVES ONTO THE KEEPER** when the keeper has none,
  the same call the existing code makes for `playhq_id` — the column is uniquely
  indexed per club, so two identities cannot sit on one row, and the undo takes
  it back off.
- **RECOVERY FOR A CLUB THIS HAS ALREADY HIT: re-run the CricketStatz import.**
  Match ids are deterministic (`cricketstatz_match_id`) and `import_match`
  upserts, so every deleted innings is written again — onto the ONE kept record,
  since `resolve_player` no longer finds the removed CricketStatz id and the
  name now matches the keeper exactly. Undoing the merge cannot help: those
  merge_logs rows were written before `carried_row_ids` existed, and the rows
  they would point at are gone.
- **Verified against a real Postgres** (`backend/verification/verify_merge_carry.py`,
  21 checks through the SHIPPED `_merge_players_core` and `undo_merge` bodies:
  the reported shape replayed — one person held twice, each with part of the
  career — no innings destroyed, the bowling and fielding carried, an innings
  both records held kept once, the hand-typed season and career corrections
  alive, the honour following the person, the import identity moved, the merge
  log naming exactly what moved, no row left pointing at a player who no longer
  exists, and undo handing every one of them back while the keeper keeps its
  own) **with a control run**: 14 of the 21 fail against the previous
  behaviour, the keeper left with only its own 2 innings of 7.
- **A CHECK THAT PASSES AGAINST THE BROKEN CODE IS NOT A CHECK.** "the honour
  goes back with it" is trivially true when the honour was orphaned rather than
  moved — it asserts the keeper has none now. The orphan sweep moved ABOVE the
  undo for the same reason: after the removed player is re-created, an orphan is
  no longer an orphan.
- **THE AUDIT IS REPEATABLE and is what found the rest.** Walk every
  `ForeignKey("players.id")` in `models/db.py`, resolve each to its table AND
  its ORM class, and flag any the merge body names neither of. It reported 41.
- **NOTICED, NOT FIXED**: the merge still does not carry `net_attendance`,
  `team_members`, `family_members`, `player_availability`,
  `player_availability_periods`, `fixture_lineups`, `fee_members`,
  `comms_contacts`, `merch_movements` or any of the eleven fantasy tables.
  Those describe where a person stands NOW rather than what they did, the keeper
  usually has its own, and each needs its own de-dup decision — which is a
  different change from stopping a career being deleted.

### The honour board is written in the notes (v9.68.0)

Asked for with the duplicate fix: "the notes in CricketStatz contain some
awards - it's worth us being smart at reading this notes and converting them
to awards/honours".

- **A CLUB THAT KEEPS ITS NOTES PROPERLY HAS WRITTEN ITS HONOUR BOARD THERE.**
  Sampled live before designing anything: **64 of 75 players carry notes, 143
  lines**, in one house style — `LIFE MEMBER ~ 1992-93`, `A-GRADE CAP AND DEBUT
  #102 (1982-83)`, `5x TED GARLAND BATTING AVERAGE WINNER`, `SENIOR HEAD COACH
  (2011-15, 2023-25)`, `N.M.C.A. - HALL OF FAME`.
- **AN UNRECOGNISED NOTE IS NOT AN AWARD, and that is the whole design.** The
  same block carries plain biography — `COLLINGWOOD FC (313 Games)`,
  `ESSENDON FC / MELBOURNE FC (95/3 Games)`, `wk` — and a football career on a
  cricket club's honour board is worse than reading nothing. 111 of the 117
  distinct lines classify; the six that do not are left alone and REPORTED, so
  a club can see what its notes said that we did not file.
- **A TWO-YEAR TOKEN IS A SEASON ONLY WHEN THE SECOND HALF IS THE FIRST PLUS
  ONE.** `1982-83` is a season; `2011-15` is a five-year coaching stint. The
  one test separates them and holds at the century (`1999-00` is a season,
  `1998-00` is a two-year span) — getting it wrong files a stint under a season
  that never existed. `_span_end` rolls the century over for the far end, or
  `1998-00` ends in 1900.
- **AN `Nx` PREFIX MEANS THE LINE IS SOMETHING WON N TIMES, NEVER A ROLE.**
  That is what separates `2x N.M.C.A. TEAM OF THE YEAR - CAPTAIN` (an award
  that happens to name a role) from `INAUGURAL K.P.C.C. 'A' GRADE CAPTAIN
  (1962-63)` (a captaincy). Checked before the role vocabulary, deliberately.
- **A TROPHY WON FIVE TIMES IS ONE HONOUR THAT SAYS SO, not five season-less
  rows.** There is no per-season breakdown behind an `Nx`, so five rows nobody
  could check is the wrong answer; `Won 5 times` in the detail is the honest
  one.
- **EVERY HONOUR IS ADDED TO THE CLUB'S OWN AWARD CATALOGUE**
  (`ensure_award_definition`), or an imported trophy exists on a player and
  nowhere in the list the Awards screen offers — so a second winner could only
  be added by retyping its name. Subcategories are `ROLE_TYPE_TO_SUBCATEGORY`'s
  own (`Captains`, `Coaches`), so `office_bearers.sync_award_definitions`
  reconciles them into BetterClubhouse's role catalogue rather than minting a
  parallel vocabulary.
- **A RE-IMPORT CARRIES AN HONOUR ONTO THE NEW IMPORT, the way it already
  carries its matches and its record boards.** Found by running it: without the
  re-stamp, undoing the latest import removes the matches and leaves the honour
  board behind pointing at an import that is gone. **Only ever a row a
  CricketStatz import wrote** (`ci.organisation_id` checked): an honour the club
  typed in by hand is not the import's to claim, and claiming it would let an
  undo delete the club's own record.
- **THE BATCH ROW COUNTS WHAT NOW CARRIES IT, not what this pass created.** A
  re-import creates nothing and carries twelve, and a batch holding twelve that
  reports none reads as a mistake.
- **The award DEFINITIONS survive an undo.** A trophy now in the catalogue may
  already have a second winner typed in by hand, and a catalogue entry holds no
  claim about anybody.
- **The page's own URL carries the player's name as a slug and the name is
  decoration** — the club number and the player id resolve it, so a fixed
  placeholder is used rather than re-deriving a slug we would have to keep in
  step with however the club spells them.
- **The notes pass is its own phase and cannot lose a history already
  written.** It runs after the matches and the record book, on its own session,
  and a failure is noted rather than raised — one request per player is the
  longest part of an import and an honour board is not what the import is for.
- **Verified against a real Postgres** (`verify_cricketstatz_import.py` is 178
  checks now: every line of the real captured notes read off the page, both
  season rules and both spans, the life membership, the cap and its number, the
  emoji not riding into an award's name, the trophy won thirteen times, the
  initialisms and `McFarlane` kept as the club wrote them, the captaincy and the
  coaching stint as roles, the football career and `wk` left alone, the
  catalogue filled, a re-read creating nothing, and undo taking the honours,
  marking the batch undone and keeping the catalogue) **with two control runs**:
  with the classifier neutered 36 of the 178 fail; with only the re-stamp
  neutered, 5 — the undo leaving twelve honours behind.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN.** The first cut read
  `classify_note(...)["season"]` directly, so with nothing classifying it died
  on the first subscript and said nothing about the other thirty. Every read
  goes through `got()` now. Two checks also PASSED against the broken code — "a
  cap with no season still reads as a cap" and "the emoji does not ride into the
  name" are both trivially true of `None` — so each asserts the classification
  exists as well.
- **A HARNESS TABLE THAT MERELY LOOKS RIGHT IS WORSE THAN NONE.** The three
  awards tables are lifespan-created raw SQL, invisible to `create_all`; they
  are copied into the suite column for column from `main.py`.
- **THE STUB REMEMBERS WHICH PLAYER GOT WHICH NOTES.** Keyed on call order it
  served nothing at all on the second import, so the carry-over checks were
  measuring the harness rather than the code.
- **NOT BUILT**: no endpoint runs the notes pass alone. A club that imported
  before this shipped gets its honour board by re-importing — matches are
  recognised and updated rather than doubled — which is the same path the
  record book already takes. The player page also carries `Batting: Right
  Handed` and `Bowling: Right Arm Pace`, which map onto `players.batting_hand`
  and `.bowling_type`; that is a different change from the one asked for.

### An imported grade is classified on the way in (v9.67.3)

Asked for directly: create grades, seasons and players the way the other stat
import pages do.

- **A GRADE WITH NO CATEGORY CANNOT BE TOLD APART BY THE GRADE TYPE FILTER**,
  so a club's imported juniors would sit inside its senior careers — the exact
  thing migration 228 exists to prevent. The importer was writing a bare
  `Grade(name=…)`.
- **BOTH COLUMNS, per the rule this file already sets**: `category=
  suggest_category(name)` AND `categories=list(suggest_categories(name))`, or a
  "Girls Under 16" lands as junior alone and loses its women's half.
- **`grassroots_id=None` is written explicitly** on both the season and the
  grade — the documented "not from a sync" marker every other importer sets.
- Players needed nothing: the reference importers create a bare
  `Player(id, organisation_id, name)` and let the column defaults stand.

### Find out what there is before pulling it (v9.67.2)

Asked while watching a live run: "it says season 10 of 167 but I know there
are 40-50 seasons for Cockburn, so why is it parsing all 167" — and is a first
pass that works out where the data is, then plans the pull, worth building.

- **IT IS, AND THE REASON IS THE PROGRESS BAR, NOT THE SAVING.** The 167
  candidate probes are ~1 minute of a ~60 minute run. What discovering
  seasons as it went really cost was the DENOMINATOR: `matches_total` only
  counted the seasons walked so far, so it climbed with `matches_done` and any
  bar drawn against it sat near full from the first season. A first pass gives
  the real total up front, which is what makes every figure after it mean
  something.
- **`plan_seasons` PROBES EVERY CANDIDATE, CONCURRENTLY.** 167 candidates in
  **56 seconds** against the live site, under the client's own semaphore. It
  keeps each season's match rows, so the import that follows re-reads nothing —
  the plan IS the work list.
- **EVERY CANDIDATE IS PROBED, and the temptation not to was measured and
  rejected.** Bounding the range by the dates on the all-time record boards
  looked clean and cut 167 to 73 — but those boards are top-100 lists, so a
  quiet early season need never appear on one. Checked against the live club:
  the boards span **1954-2026** while the club's real earliest season is
  **1953**. It would have silently dropped a season, which is the one thing
  this must not do. A history can have gaps, so stopping at a run of empty
  years is out for the same reason.
- **WHAT IT FOUND FOR THE REPORTED CLUB**: 73 seasons actually played,
  1953-2025, 3,556 matches, ~59 minutes — with 94 candidate seasons skipped as
  empty. The club sees that before committing, and the bar then runs against
  3,556 rather than a figure that grows underneath it.
- **THE PLAN IS ORDERED OLDEST FIRST**, so a club watching sees its history
  fill forwards rather than arriving backwards.
- **Verified** (the suite is 113 checks: the played seasons found and the empty
  candidates left out, the rows kept, the oldest-first order, the summary's
  total, span and estimate, and — structurally — that every candidate is
  probed rather than a guessed range) and **driven in Chromium** (40: the first
  pass counting candidates and NOT pretending to a matches figure it has not
  worked out yet, then the bar against the real total, and the plan's own line).

### A working import that read as a hung one (migration 286, v9.67.1)

Reported off a live run with a screenshot: Cockburn on **season 10 of 167**, a
bar sitting at 94%, and the badge still reading "working out which seasons you
played" after 1,227 matches.

- **NOTHING WAS HUNG. THE SCREEN COULD NOT SAY OTHERWISE, and that is the
  actual defect.** A full history is thousands of matches at roughly one
  scorecard a second, so the same figures sitting there for a minute is the
  ordinary case. There was no record of when the row last moved, so neither a
  club nor I could tell a long run from a dead one.
- **`updated_at` IS THE ONE THING THAT ANSWERS IT.** Every progress write is
  now a heartbeat, and `/status` returns the seconds since it. The screen says
  "still going" under 90 seconds and names the gap after that.
- **THE BAR WAS MEASURED AGAINST A TOTAL THAT GROWS WITH IT.**
  `matches_total` only counts the seasons walked SO FAR, so `matches_done /
  matches_total` sits near full from the first season — 1227/1298 is 94% on
  season 10 of 167. Seasons are the bounded, monotonic measure and are what
  the bar tracks now. **The control run reads 95% against the old
  expression**, which is the reported screenshot.
- **THE PHASE BADGE READ THE COLUMN AND THE RUN ONLY UPDATED THE BLOB.** The
  `phase` column was set to `seasons` once and then not again until `done`, so
  it was stuck for the whole import. Both move together now, and the screen
  prefers the blob.
- **THE PLAYERS FIGURE WAS THE CURRENT SEASON'S CACHE**, so it fell back every
  season instead of climbing. Counted from the club's own rows now.
- **A RUN WHOSE PROCESS DIED LOCKED THE CLUB OUT FOR EVER.** The
  already-running guard had no notion of a stale row, so a redeploy mid-import
  left `status='running'` with nothing behind it and every later attempt got a
  409. A run silent past `STALL_AFTER_SECONDS` (5 minutes — one 30s request
  plus a season probe is the longest honest gap) is closed out as errored and
  the new one starts. There is a Stop button too.
- **A SCORECARD IS NO LONGER CACHED.** It is fetched once per import and never
  again, so holding thousands of ~20KB bodies for the cache's TTL kept a whole
  club's history in memory for nothing.
- **THE HEARTBEAT ALSO BEATS MID-SEASON**, every 5 matches rather than only
  between seasons — a season of 130 matches was 90 seconds of apparent
  silence.
- **Verified** (the suite is 104 checks: the heartbeat recorded, a 90-minute
  silence reading as stalled, a just-moved run NOT reading as stalled, and the
  threshold being minutes rather than seconds) and **driven in Chromium** (34,
  the reported run replayed exactly: the bar on seasons, the "still going"
  line, the stalled notice, and the Stop control) **with a control run**: the
  old bar reports 95%.

- **IT LIVES ON DATA SYNC, not a screen of its own.** Bringing a history in is
  a sync action like the others — it just points at another platform instead of
  Cricket Australia — so `components/admin/CricketStatzImport.jsx` is a panel
  mounted inside `AdminSync.jsx` rather than a route. The first cut made it its
  own page with a card on Data Sync linking across, which is a second place to
  look for one job.
- **THE CLIENT SAYS WHO IT IS AND GOES GENTLY** — concurrency 3, a delay
  between requests, a 30-minute cache so a preview and the import that follows
  share one pull. This is a club exporting its OWN records, one club at a time,
  on demand. **Their `robots.txt` disallows `/ss/`**, which was raised before
  building and the call was made to proceed on the data-portability reading; it
  is why the design never enumerates club ids or sweeps the site.
- **Verified against a real Postgres** (99 checks through the shipped parsers,
  import service and route bodies over real captured reports: a modern card, a
  1995 one, an abandoned innings, a result-only match, an unnamed junior card,
  the record boards, the migration applied three times, a re-import doubling
  nothing, and undo taking the matches while keeping the people) and **driven
  in Chromium** (30: the exact address on the wire, the preview's cap notice,
  a running import's progress and polling, the record boards, a dismissed undo
  sending nothing, no page errors, no overflow at 390px) — plus a **live run
  against the real club**: 137 of 137 matches, 2 seasons, 16 grades, 148
  players, 1,426 innings, 41 record boards, nothing unreadable.
- **Two browser checks passed against a broken page first**: `/sync-runs` and
  `/sync-logs` answer with bare ARRAYS, and stubbing them as objects rendered
  the error boundary and then measured that.
- **NOTICED, NOT BUILT**: `mode=106` is a **Ball by Ball** report — richer than
  anything CA gives us, and the one thing that would lift the phase/matchup
  analysis the BetterIQ brief calls out of reach. Also unbuilt: their
  league-scoped JSON API (`/ss/getplayers.aspx` etc., reference data only, no
  stats) and the full JSON database extract a level-8 CricketStatz account can
  download, which would be the sanctioned path if a club would rather hand over
  a file than a link.

<!-- END original CLAUDE.md L10637-12118 -->
