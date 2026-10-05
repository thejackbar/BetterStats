# Archive: imports-manual-entries-and-data-tidy

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: Scorebook and CSV imports, manual games and adjustments, seasons and grades tidy-up, duplicate detection, the scorecard reader.
Read the distilled rules first: `docs/dev-notes/guides/imports-manual-entries-and-data-tidy.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L32-75 -->
## A game that does not add up is warned about, never refused (v9.99.2, Sep 2026)

Reported off Hamilton Veterans' 23 Oct 2011 game: Portland and Mt Gambier both
read 142/7 in 40 overs. Asked whether the opposition total had been forgotten
and copied across; it had not.

- **THE OPPOSITION TOTAL WAS ENTERED AND RIGHT. OUR INNINGS CARRIED A COPY.**
  `_merge_manual_innings` lets a recorded `total_runs` replace the batters' sum
  on any innings, and the form draws the total boxes only when "Who batted" is
  Opposition. Type a total while an innings is Opposition, flip it to Our
  innings, and the boxes vanish while the values stay and are saved. Both rows
  then held 142/7/40 and the card totalled 125/8 nowhere.
- **THE FIX IS AT THE SOURCE, NOT IN THE MERGE.** A scorebook CSV import
  legitimately records OUR total (`innings_total`), so the merge still honours
  one. The hand-entry path stops storing it instead: `_replace_game_children`
  nulls total/wickets/overs on any innings whose side is "us", the form clears
  them when the side is flipped (`setInningsSide`) and never sends them
  (`buildPayload`).
- **WARNINGS ONLY.** A club entering a scorebook often lacks a figure, so
  nothing here can refuse a save. `services/manual_game_check.check_game` is
  the one definition, read by `POST /manual-entries/games/check` (writes
  nothing) which the form calls, debounced, and shows in an amber box and again
  in the save confirm. A failed check draws nothing and does not stop a save.
  It reports: an opposition innings with no total (skipped for a photo upload,
  which carries their whole card), our bowlers' runs plus byes, leg byes and
  penalties not reaching their total (or exceeding it when extras are not
  itemised), overs not matching, an innings set to the wrong side for the rows
  under it, and a result line that disagrees with the totals (one innings each
  only).
- **`scripts/fix_stray_innings_totals <org|all> [--apply]`** repairs stored
  games, on a narrow signature: our innings carries the SAME runs, wickets and
  overs as the opposition's, our batters are listed, and batters plus extras do
  not already equal it. A legitimate total and a tie are left alone. It only
  NULLs the three columns and writes an audit entry with before and after, so
  the Audit tab can undo it.
- **Verified** (`verify_manual_game_check.py`, 36 through the shipped writer,
  scorecard, route and script against a real Postgres; control with the writer
  change neutered fails 3, reporting Portland at 142/7) and in Chromium
  (`verify_manual_game_check_browser.mjs`, 24; control fails 11). Neighbours:
  manual innings 20, winner 25, side names 24, CSV innings 31.
- **Noticed, not fixed**: `settle_manual_game` reads the same totals, so a stray
  copy could have flipped a winner. It reads correctly once the copy is gone.


<!-- END original CLAUDE.md L32-75 -->
<!-- BEGIN original CLAUDE.md L190-238 -->
## An importer pre-selects "Steve" for the club's "Steven" (v9.97.2, Sep 2026)

Reported off Shoalwater Bay's re-import: the archive writes "Salter, Steve",
"Staines, Ken", "Cribbs, Rod"; the synced roster holds Steven, Kenneth,
Rodney. The matcher offered each as a close match (or, for Chris against
Christopher at 0.80, as no match at all), and "Create all as new players" swept
them into second records, each holding half a career, which the milestone
reconcile then read as milestones to delete.

- **A SEPARATE STEP, NOT A CHANGE TO `match_players`.** Twelve callers use it
  (CricketStatz, awards, the scorecard reader, AFL); only the two stats
  importers opt in, through `import_ingest.short_form_suggestions` and
  `apply_short_form_suggestions`. Every other caller's output is byte-for-byte
  what it was.
- **`import_ingest.is_short_form` IS THE ONE RULE**, and Merge Duplicates'
  `admin._first_name_link` now calls it, so the importer and the name-variant
  merge pairs cannot disagree about what a short form is: same surname, one
  first name a prefix of the other, at least 3 letters, middles compatible.
  A nickname that is not a prefix (Bob/Robert) is never claimed.
- **PRE-SELECTED, NEVER SILENT** (status `suggested`, with a note naming both
  careers). Refused outright where two club players fit, or where another name
  on the SAME SHEET reaches that player (a sheet naming both "Steve" and
  "Steven" is telling us they are two people).
- **CAREERS MORE THAN `MAX_CAREER_GAP_YEARS` (5) APART ARE OFFERED, NOT
  CHOSEN** (`import_reconcile.career_years`, every source on the effective
  view, ids bound as an array). A 1990s Greg and a 2023 Gregory is the shape
  of a son under his father's name. An undated career does not block.
  **Overlap does not block either**, deliberately: an archive and CA cover the
  same seasons for the same person all the time, so an overlap cannot tell a
  father and son apart. That residual risk is why it is pre-selected on
  screen rather than written.
- **Run BEFORE the overrides**, so a person's own answer always wins, and
  "Create all" only ever reached rows with no player_id, so a suggested row is
  untouched by it with no frontend logic of its own.
- **Measured on real rosters before building**: Shoalwater's 350 archive names
  find exactly the 10 real pairs (Fletcher Greg/Gregory, 23 years apart, is
  offered not chosen); Applecross's 1,633 players hold only 2 same-surname
  pairs the rule could even reach.
- **Verified against a real Postgres** (`verify_short_form_match.py`, 39
  checks through both importers' shipped route bodies, incl. the reported
  Create-all-then-import ending on the club's own record with no second
  Salter) **with a control run**: 12 fail with the pre-selection off, the
  import minting "Salter, Steve". **Driven in Chromium**
  (`verify_short_form_match_browser.mjs`, 11; control: 3 fail). Neighbours:
  manual games import 194, CricketStatz 305, team labels 17.
- **Shoalwater still holds seven such pairs from the re-import** (Boddy,
  Fletcher, Hankey, Johnson, Marwood, Spinks, Trigg). They need Merge
  Duplicates; Fletcher Greg / Gregory is the one to check before merging.

<!-- END original CLAUDE.md L190-238 -->
<!-- BEGIN original CLAUDE.md L239-398 -->
## A scorebook import carries the opposition, the score and the stands (migration 311, v9.97.0, Sep 2026)

Reported off Shoalwater Bay's CSFW archive: an imported fixture showed no
opposition team, no opposition score and no partnerships, so none of those
matches could appear in Highest Partnerships. Built rather than asking the club
for more data; the fix is a re-import of the converted archive.

- **THE ARCHIVE HAD IT ALL ALONG; THE CSV SHAPE COULD NOT CARRY IT.** CSFW's
  `.AV` stores both innings blocks (total, wickets, overs, extras) and the fall
  of wickets as (score, batting position out). The match CSV had columns for our
  batting and bowling rows and nothing else, so the converter had nowhere to put
  the rest. `GAME_CSV_COLUMNS` gained `opp_innings_number`,
  `batting_order_known`, `innings_*` / `opp_*` figures and `fow_wicket` /
  `fow_score`, written to the existing `manual_innings` (310),
  `manual_fall_of_wickets` and `manual_partnerships` tables, which already flow
  through the `v_effective_*` views to the match page and the record boards.
- **READ BEFORE THE BLANK-PLAYER SKIP.** A match where nobody on our side is
  named still carries the opposition's innings, so the innings meta is taken off
  every row, and "nobody named" rows still carry it.
- **OUR BOWLERS ARE FILED UNDER THE OPPOSITION'S INNINGS NUMBER.** They were
  filed under our own innings, which is why they read as bowling at our batters.
  A sheet giving opposition figures with no `opp_innings_number` is refused, as
  is one innings given as both sides'.
- **`innings_no` IS NOT BATTING ORDER, and the data proved it.** In 51 clear
  chases the chasing winner carried innings_no 1 in 48. So the converter numbers
  by leg (ours 2n-1, theirs 2n) and sends `batting_order_known=false`;
  `manual_games.innings_order_known` (311) records it and the match page draws
  "INNINGS" unnumbered, no winning margin, no HOME/AWAY for blank home/away
  teams, and a note saying why. NULL (every existing game) reads as known, so no
  other match changes.
- **PARTNERSHIPS ARE DERIVED AND REFUSED WHEN THEY DO NOT RECONCILE.**
  `services/scorebook_innings.derive_partnerships` walks the batting order
  against the fall of wickets and returns None on a gap, a batter out who is not
  at the crease, a score going backwards or a wicket count disagreeing. A stand
  credited to the wrong pair sits on a record board under two names that never
  batted together, which is worse than none. 889 of 917 innings derive, 8,011
  stands; the other 28 keep their fall of wickets.
- **Undo restores them.** `_EXTRA_GAME_CHILDREN` puts the three child tables in
  the edit/delete snapshot, so an undone or restored game keeps them.
- **THE MATCH PAGE NAMING THE OPPOSITION WAS NOT ENOUGH (v9.97.1).** The
  Games page, the Team pages and the innings tables on a player's profile read
  `home_team`/`away_team` straight off `v_effective_games`, and a scorebook
  import leaves both blank, so every imported match still listed as "— vs —"
  there. `services/game_sides.sides_sql` is the one rule: a blank pair on a
  manual game with an opposition is named from the club and its opposition,
  with `home_away_known=false` on the row. Used by `get_org_results` and the
  two innings-history queries in `aggregations`; `_fetch_manual_games_as_list`
  applies it in Python. Found by auditing every reader of the two columns, not
  by the report, which was about the match page. Suite is 47; a control with
  the readers reverted fails 4, reporting `home_team: None`.
- **Verified against a real Postgres** (`verify_scorebook_innings.py`, 43
  checks through the shipped import route, `get_scorecard` and `get_records`:
  the rule on its own, the reported match, a non-reconciling innings refused, an
  older sheet importing unchanged, self-contradicting sheets refused, and the
  snapshot round trip) **with a control run**: 28 fail against the previous
  commit, the card reading "None v None" with no opposition innings. **Driven in
  Chromium** (`verify_scorebook_import_browser.mjs`, 19, against the payload the
  backend suite wrote) **with a control run**: 4 fail, reporting numbered
  innings, HOME/AWAY and "won by 65 runs". Neighbours re-run: manual games
  import 194, manual innings 20, manual scorecard 25, scorecard innings total
  15, the converter's own 30.
- **Recovery for Shoalwater**: undo the earlier CSFW import batch, re-import the
  regenerated `manual_games_scorecards.csv`, then re-run `repair_overwrite_pairs`
  and `reconcile_milestones` for the club.

### The template a club downloads, a single sundries figure, edit undo (v9.98.2)

Asked off Hamilton Veterans' support thread: should the CSV carry every
sundry a club has? It already did, itemised, through the columns above. A
second scheme was written for this before `origin/main` was re-checked and
found to have shipped these; it was thrown away rather than shipped beside
them. **Fetch `origin/main` before building on an import format.**

- **THE TEMPLATE'S EXAMPLE WAS POSITIONAL AND HAD DRIFTED.** 32 values against
  53 columns, one column out from `batting_caught_behind` onwards, and not one
  innings or `opp_*` column filled. Imported as-is, it filed the example's
  bowlers in innings 1 against their own batters, which is the reported bug.
  It is built from dicts keyed on the column name now, uses the downloading
  club's name, and models `opp_innings_number` for bowling.
- **`innings_extras` / `opp_extras` → `manual_innings.extras_total`**, the CSV
  twin of the hand-entry form's "Or total". Itemised figures still win, per
  `_merge_manual_innings`.
- **UNDOING AN EDIT NOW RESTORES THE INNINGS FIGURES**; delete and overwrite
  already did. `_restore_extra_children` is the one restore loop. **It only
  replaces a child table the snapshot holds**: an edit logged before these
  were snapshotted has no keys, and reading that as "there were none" would
  delete a scorebook import's fall of wickets the edit never touched.
- **Verified** (`verify_csv_innings_import.py`, 31: the template imported end
  to end and its scorecard to the run, the single figure both sides, itemised
  winning, and all three undos) **with three controls**: the previous commit
  fails 26; the edit snapshot alone removed fails 1; the key guard alone
  removed fails 1. Neighbours: manual games import 194, scorebook innings 47,
  manual innings 20, manual scorecard 25, template route 4.

### Our innings is named for the team the match says, not the club (v9.98.6)

Reported by Hamilton Veterans, who play as "Portland Over 60s": on entered
games the header drew each side's score under the other side's name, and the
cards called our side "Hamilton Veterans Cricket Club".

- **THE STORED DATA WAS RIGHT; ONLY THE PAGE WAS WRONG.** Every innings, total
  and batting side read correctly off the live payload. `get_scorecard` labelled
  our innings with `org.name`, a name the match's home/away does not use, so the
  header could not place it and fell back to "innings 1 is home".
- **"60s" WAS READ AS A CLUB WORD.** `distinctiveTeamWords` kept "60s", so
  "Mt Gambier Over 60s" scored as a partial match for "Portland Over 60s" and the
  header swapped the scores even when Portland batted first. `AGE_TOKEN`
  (`/^[uo]?\d+s?$/`) is generic now.
- **`games._manual_side_names` is the one rule**: ours is whichever of home/away
  is not the opposition (punctuation-insensitive), else the side sharing a
  non-generic word with the club's name, else a single named side that is not
  the opposition, else the club's name as before.
- **The header judges both sides against both teams** (`sidesSwapped`); a tie no
  longer means "innings 1 is home". `splitSides` files by exact normalised name
  first, and with only one side seen it needs every distinctive word shared, or
  both innings of a match between two "Over 60s" sides land on one side (the
  control run shows exactly that).
- **The team cards stay in batting order** under a home/away header, per the
  v8.79.2 instruction. The club's feedback also asked for the cards to sit under
  their header columns; that reverses a deliberate call and was raised, not built.
- **`bowling_order` on the match CSV.** Spells are held and written in that
  order, and every read of manual spells orders by `id` (the scorecard, the edit
  form, the edit and delete snapshots), so a later edit or undo keeps it. No
  migration: insertion order is the order.
- **Games page "All seasons" defaulted again on every null season** and snapped
  back to the newest. Defaults once now (`seasonDefaulted` ref).
- **Verified** (`backend/verification/verify_manual_side_names.py`, 24 through
  the shipped routes against a real Postgres; control: 12 fail) and in Chromium
  (`frontend/verification/verify_manual_scorecard_sides_browser.mjs`, 56, over
  the club's six real payloads with the club name and with the team name, plus
  the live Games page; control: 17 fail, reporting the reported 20 Mar and 5 Feb
  swaps and 2026/27 coming back). Neighbours: CSV innings 31, scorebook 47,
  manual innings 20, manual scorecard 25, games import 194, template 4, innings
  total 15, scorecard innings 28, scorebook browser 19.

### A recorded winner the result and the scores both contradict (v9.98.7)

Reported off Hamilton Veterans' 7 Feb 2012 CSV game: winning_team Portland,
result "Lost by 7 Runs", scores Portland 159 v Vic Country 166. The importer
copies `winning_team` verbatim and every screen reads it, so one wrong field
beat two right ones.

- **`services/manual_result.py` is the one rule**, applied by the CSV import,
  the hand-entry create/update and `python -m app.scripts.settle_manual_winners
  <org|all> [--apply]` (dry run by default). The winner changes only when the
  result line opens with Won/Lost (a line naming a team is not read), the
  recorded winner names the other side, it is one innings each, and the scores
  agree with the result line. A tie, a missing total or a rain-rule result
  where the lower score won is left as entered.
- **Cheap on a big import**: scores are worked out (via the shipped
  `get_scorecard`) only for a game whose winner and result line already
  disagree. The import lists each change in its warnings.
- **Card layout stays as it is**: header home/away, team cards in batting
  order. That is the standard (Wisden and Cricinfo list the fixture home v
  away, then the innings in the order they were batted).
- **Verified** (`verify_manual_winner.py`, 25) **with a control run**: 7 fail,
  the winner staying Portland. Neighbours: side names 24, CSV innings 31,
  scorebook 47, manual innings 20, manual scorecard 25, games import 194.
- **Run the script for Hamilton after deploying.**

<!-- END original CLAUDE.md L239-398 -->
<!-- BEGIN original CLAUDE.md L641-788 -->
## A RE-SOURCED SEASON COUNTS PER MATCH, NOT PER SEASON (migration 309, v9.90.3, Sep 2026)

Reported off Shoalwater Bay after their CSFW archive went in through the CSV
import's OVERWRITE mode: on most players "All" read LOWER than "Men's", which
no filter should be able to do. Diagnosed on the live database
(`ops/diagnostics/csv_import_unpaired.sql`) before a line was changed.

- **THE PAGE WAS NOT DOUBLE-COUNTING "ALL". IT WAS DROPPING MATCHES FROM IT.**
  An overwrite import marks each season it touches `import_authoritative`,
  which stepped the WHOLE season's Cricket Australia summary aside in
  `v_effective_player_season_stats`. So every synced match the file did not
  hold — 83 junior-grade games the archive never tracked, and 32 senior
  matches the matcher missed — vanished from "All", while "Men's" (an explicit
  scope, so read from the per-innings views) kept them. Two definitions of one
  season, and a filter that raises a total is the tell.
- **A SEASON TOTAL HAS NO PER-MATCH GRANULARITY, so the only way to replace
  SOME of a season is to count the whole season from scorecards.** The new
  `api_scorecard` branch rolls up every synced game in a re-sourced season that
  has no preferred imported twin, from `batting_innings` / `bowling_spells` /
  `fielding_stats` / `game_appearances` — the four sources `_scoped_games_played`
  already unions — org-scoped through `players`. The import's own rollup counts
  the matches the file held; the two are disjoint by construction. The "and,
  not or" rule the pairing already keeps, applied at the aggregate level.
- **EACH TABLE IS AGGREGATED ON ITS OWN BEFORE THE THREE ARE JOINED.** The
  manual rollup beside it LEFT JOINs batting, bowling and fielding rows side by
  side on one `(player, game)` key, which multiplies a player who batted twice
  and bowled twice in one match into four rows and doubles every sum. Noticed,
  NOT fixed there — it is migration 037's shape and its own change.
- **A FIXTURE THE OTHER CLUB SYNCED FIRST IS KEYED ONTO OUR OWN SEASON** for
  the same real season, CA season guid first and year second, through a
  `LATERAL ... LIMIT 1` so a year with two season rows cannot count it twice.
  It is filed on THEIR grade id, which the by-grade grid already resolves by
  name.
- **THE MATCHER HAD THREE REAL GAPS, and the diagnostic named them with
  counts**: `_existing_game_index` read `v_effective_games.organisation_id`,
  so a fixture the OTHER club synced first was never a candidate (19); an
  opponent the two sources spell with no shared word never matched (11:
  "Rockingham Hornets Cricket Club" against "Hillman"); and a two-day match
  each source dates differently never matched (2). The index is now the club's
  season OR either side of the fixture, and a sheet match the date rule leaves
  unmatched gets a SECOND LOOK through `match_pairing.assign` — the CricketStatz
  matcher's own rules, never a second copy — on a `(player_id, runs)`
  signature built from the sheet's resolved players. `match_pairing.load_synced`
  is the one query all three readers of the synced side now share.
- **RE-IMPORTING THE SAME FILE USED TO UNPAIR EVERYTHING.** An overwrite of a
  manual duplicate deleted the old row and wrote a fresh one with no pairing,
  so the synced copy came straight back beside the sheet's version. The
  replacement inherits the old row's pair now, exactly as it was.
- **`python -m app.scripts.repair_overwrite_pairs <org|all> [--apply]`** is the
  same second look run after the fact, over what an earlier import left
  unpaired. Only matches an IMPORT created are candidates — read off the
  import's own audit rows — never a game somebody typed in, and only in a
  re-sourced season. Dry run by default. **Run it on the box after this
  deploys**, for the 32 already counted twice.
- **AFTER THE FACT, A PAIR NEEDS A SHARED SCORE (v9.90.4).** The live dry run
  proposed pairing an imported Pinjarra match to a synced "Pinjarra Junior
  Cricket Club" fixture eight days later with 0 shared scores, through the
  matcher's same-club-no-card rule. Every imported match here carries the
  sheet's own card, so a zero-score pair can only be a cardless synced game,
  which in a re-sourced season is usually one of the junior fixtures the
  archive never tracked. The script now holds those back and prints them under
  "held back, check by hand". The live matcher is unchanged.
- **A MATERIALISED CTE IS A WALL THE PLAYER'S ID CANNOT PASS (v9.90.4).**
  Reported as "the player page takes much longer to load now": once a club
  leaves juniors out by default, every profile read is scoped and reads
  `v_effective_player_season_stats` several times over. Both rollup branches
  (`manual_game`, `api_scorecard`) were `WITH` chains whose CTEs are
  referenced more than once, so Postgres MATERIALISED them and the outer
  `WHERE player_id = X` never reached inside: every single-player read rolled
  up every re-sourced season on the platform, then threw it away. `EXPLAIN`
  showed `CTE auth_games` / `CTE ours` / `CTE counts_here` with unfiltered
  scans of `batting_innings` and friends. Every player-dependent CTE in both
  branches is `NOT MATERIALIZED` now; the same EXPLAIN shows a
  `player_id = X` filter on every per-innings scan, which the suite asserts
  by reading the plan. **No index was needed**: the wall, not the tables.
- **BUT `auth_games` STAYS MATERIALISED, and the first deploy without that
  took the page from slow to 45 SECONDS (measured live on `/stats`).** It
  does not depend on the player, so inlining buys no pushdown and costs one
  evaluation per reference: four arms of `player_games` times four readers
  of `ours` is sixteen scans per view read, and its shared-fixture arm was
  a scan of every game on the platform with a LATERAL per row. It is
  `AS MATERIALIZED` (once per read, small) and that arm is driven FROM the
  re-sourced seasons through the indexed `home_org_id`/`away_org_id`, with
  `DISTINCT ON (g.id)` keeping the one-season-per-game rule. **Inline a CTE
  only when there is a predicate to push into it.**
- **THE VIEW WAS NOT THE 6 SECONDS. `player_categories` WAS, and it was
  found by timing endpoints, not by reading.** After the view fix every
  profile endpoint still took ~6s, INCLUDING ones that never read the
  season-stats view (dismissals, by-position) and on Applecross, which has
  no import at all; the same endpoint with an explicit `?categories=` took
  1.1s. The one thing a club-default read does that an explicit one does
  not is the auto-widen probe, and `player_categories` asked "does this
  player have a row in one of your games" as a correlated EXISTS over
  `v_effective_games` for EVERY grade row the club holds — hundreds of
  subplans per call, thirteen calls per page. It starts from the player's
  own rows now (indexed on player_id), collects their grades, and names
  them: zero SubPlans in the plan. **When every endpoint on a page is
  uniformly slow, look for the thing they all call, not the thing that
  changed.**
- **THE 037-SHAPE FAN-OUT IS FIXED, not only noticed.** The `manual_game`
  rollup LEFT JOINed batting, bowling and fielding side by side on one
  (player, game) key; a player who batted twice and bowled once in a two-day
  imported match read 2 bowling innings, 4 wickets and 2 catches. It is now
  the `api_scorecard` shape: each table aggregated on its own, then joined.
- **STATLAB COUNTED A MATCH FROM `game_appearances` ALONE, and an imported
  match never has one.** So on a grade-filtered summary every innings of a
  club's archive counted while the match did not, and five A-grade players
  read "a lot more innings than games played" (Guest, Rob in the suite: 2
  innings, 0 matches). The `appear` CTE unions the four sources
  `_scoped_games_played` unions now, the called-off rule kept on the roster
  arm alone. Two innings per two-day match is still the correct gap.
- **THE STAGE WAS WRONG FOR EVERY CLUB, NOT ONE.** The view is applied by the
  lifespan on every boot, and the matcher and re-import fixes live in the
  importer, so a deploy fixes every club. What is per club is the after-the-
  fact repair of pairs an EARLIER import left unpaired: only Shoalwater Bay
  had `repair_overwrite_pairs` run. `python -m app.scripts.repair_overwrite_pairs
  all` (dry run) lists every club with a re-sourced season; run it with
  `--apply` after reading the held-back list.
- **Verified** (`verify_manual_games_import.py` is 194 checks: the one spell
  reading 1 and 2 rather than 2 and 4, the catch not doubled, a plan with no
  CTE Scan and the id on every scan, and StatLab reading 1 match for the
  imported two-day match) **with a control run**: 6 fail against the
  previous commit, reporting `(2, 4, 2)`, `matches: 0` beside 2 innings, and
  `Seq Scan on batting_innings ... rows=590` with no filter. StatLab's live
  path needs the lifespan-only `grade_merge_logs`, copied into the harness.
- **THE COMMIT'S WARNING SAID THE OPPOSITE OF WHAT IS NOW TRUE.** It warned that
  uncovered matches "are no longer counted"; they are, and it says so, naming
  separately the ones that carry no scorecard of ours and so add nothing.
- **Verified against a real Postgres** (`verify_manual_games_import.py` is 185
  checks: the uncovered games counted from their scorecards including the
  bowling, the aggregate view agreeing with the per-innings views TO THE RUN,
  the other club's fixture under our season on their grade with their batter's
  99 never ours, all three miss shapes paired, a same-day match sharing no
  score NOT paired, a re-import keeping every pair, and the repair script's dry
  run writing nothing then apply pairing it once) **with a control run**: 19
  fail against the previous commit, reporting `aggregate 1/20 vs scorecards
  3/110` and the three misses as `{'total': 0}`; the script is REPORTED absent
  rather than crashing the run. Neighbours re-run: match coverage 66,
  cricketstatz import 305.
- **THE SUITES SHARE ONE DATABASE AND THEIR STUB TABLES COLLIDE, hit again.**
  `verify_cricketstatz_import.py` died on `player_achievements.org_id` because
  the manual-games suite had left its own four-column stub of that table
  behind. Not the change; it passes on a fresh database. Run a suite whose
  stubs differ on its own database.
- **THE JUNIOR GAMES ARE RIGHT TO STAY LIVE.** They were never in the archive,
  the Men's filter leaves them out anyway, and they are exactly what "All"
  should hold beyond "Men's". Nothing here touches them.

<!-- END original CLAUDE.md L641-788 -->
<!-- BEGIN original CLAUDE.md L1531-1576 -->
## A SHEET SPLIT BY TEAM IS NOT A SHEET SPLIT BY GRADE (v9.89.1, Sep 2026)

Reported off The Basin's Import Stats review: Leigh Cook's sheet says 240 and
the preview read ONLINE 135, RESIDUAL +0, FINAL 355. His profile had already
gone to 433 from an earlier commit.

- **THE SHEET AND THE ONLINE DATA AGREE SEASON FOR SEASON**, and checking the
  real spreadsheet against his live grid is what named the cause. The sheet
  labels rows by the club's own TEAMS (1XI / 2XI / 3XI / 4XI / 20/20). CA files
  the same side under a different GRADE name most years ("Division 3",
  "4 Norm Reeves Shield Reserve", "Community 1"...). Grade-scoped
  reconciliation (migration 154) mapped each label to ONE grade name and
  compared against that grade alone, so ONLINE read 135 of his ~256 and every
  season spent under another name was emitted as a season delta on top.
  `final = GR + emitted + residual` has no cap on `emitted`, so the "can never
  exceed the club's total" promise on the review screen only held while the
  season test was right.
- **`import_reconcile.is_team_labelled` IS THE SWITCH**: an org whose imported
  rows name two or more grade labels is reconciled per player against their
  WHOLE GR record (the ungraded path), season by season. The labels are still
  stored; pre-GR season deltas keep the team their row named
  (`season_rows_by_grade`); the career residual carries no grade. A club that
  uploaded ONE competition's book keeps the grade-scoped path unchanged. Both
  the commit and the preview (`routers/imports.py::_resolve`) make the same
  call, the preview reading the club's earlier uploads too since the commit
  reconciles all of them. **Accepted cost**: a club uploading its 1sts and 2nds
  as separate sheets is now read as its whole book, so a grade CA has that the
  sheets omit is not topped up per grade.
- **`covered_by_year`**: a season is covered when GR holds that YEAR under any
  season row. An id-only test read a hand-made "2015/16" beside the synced
  "Summer 2015/16" as missing (267 against 256 in the control run).
- **THE EXPECTED RESULT IS THE ONLINE FIGURE, NOT THE SHEET'S**, whenever
  online holds more: for Leigh that is 256 (2009/10's 11 games are online and
  not in the sheet, plus five seasons one game apart). "GR wins per season" is
  the documented rule; making the sheet win would be a different rule.
- **Recovery needs no re-import**: `reconcile_imported_totals` rebuilds every
  delta from `imported_stats`, and runs at the end of every sync;
  `python -m app.scripts.reconcile_imports <org>` does it now.
- **Verified against a real Postgres**
  (`backend/verification/verify_import_team_labels.py`, 17 checks through the
  shipped `reconcile_imported_totals`, Leigh's real rows and his real online
  seasons) **with a control run**: with the year widening removed, 5 fail and
  his career reads 267. The fuller control (team switch off too) goes down the
  grade path, which needs the lifespan views this harness does not build, so
  that half was replayed through the pure functions instead.

<!-- END original CLAUDE.md L1531-1576 -->
<!-- BEGIN original CLAUDE.md L2887-2995 -->
## Suggested duplicate grades: the discriminator rule (migration 294, v9.70.1, Sep 2026)

Asked for on Manage Grades: a smarter way of merging potential duplicates by
suggesting them, and whether Cricket Australia's grade ID could help. Merging
was two manual dropdowns and nothing computed a candidate pair.

- **THE CA GRADE GUID CANNOT DO THIS, AND THAT WAS MEASURED BEFORE ANYTHING WAS
  BUILT.** It is minted FRESH EVERY SEASON: across three seasons of a real club's
  live `fixturesladders/organisations/{org}/teams` payload, **0 of 43 grade guids
  repeated**, while the same grade NAME carried three different guids. The unique
  index on `(season_id, grassroots_id)` already forbids a repeat inside a season,
  so there is no pair of rows a shared guid could ever link. **The
  `owningOrganisation.id` on the very same payload IS stable across all three
  seasons** — that is the CA id this uses, and it was already stored as
  `grades.association_id` (migration 283).
- **EDIT DISTANCE IS NOT MERELY WEAKER ON GRADE NAMES, IT IS BACKWARDS.** Scored
  against a real club's own grade list, the genuinely DIFFERENT grades outscore
  the real duplicates: `One Day Grade 2`/`One Day Grade 4` **0.933**,
  `Twenty20 Div 2`/`Div 3` 0.929, `PSWL South A`/`South B` 0.917 — against
  `A Grade`/`A Grade (Gatorade)` **0.560** and `F Grade`/`F Grade Colts Cup`
  0.583. **No threshold separates the two columns.** At the player matcher's 0.90
  the screen would offer to merge a club's One Day Grade 2 into its Grade 4 while
  missing the sponsor suffix entirely. **So `admin._fuzzy_name_pairs` must never
  be pointed at grade names.** The reason is structural: a player's names differ
  by SPELLING VARIANCE, where an edit distance means something; a grade's differ
  by a DISCRIMINATOR — a number, a letter, a colour — that IS the whole meaning of
  the name, and edit distance reads it as noise.
- **THE RULE IS THEREFORE TOKEN-AWARE: the discriminating tokens must be
  IDENTICAL, and only decoration may differ.** Every tier in
  `services/grade_duplicates.py` is gated on that one test, which is what makes
  even the loosest of them safe. Three tiers: `same_name` (identical once
  decoration is stripped), `extra_words` (one name says everything the other does
  and more) and `word_typo` (one word differs and is ≥0.80 alike — consulted
  ONLY after the discriminators have matched, so it cannot repeat the mistake
  this module exists to avoid).
- **A NUMBER, A BARE LETTER AND A COLOUR ARE DISCRIMINATORS.** "One Day Grade 5
  Black" and "... 5 Gold" are two real grades whose names are otherwise
  identical, so a colour has to count.
- **SO IS THE MATCH FORMAT THE NAME ANNOUNCES, and leaving it out was a real
  bug the first run caught.** "1st Grade" and "One Day Grade 1" share a number
  and differ only by the words "one day", so a word-subset rule alone read the
  second as the first with decoration and offered to merge a club's whole one-day
  competition into its two-day one. Format is an axis this platform filters on, so
  naming one is identity. Read off the RAW name via `suggest_formats`, which is
  what catches `A Grade (One Day)` — a parenthetical the sponsor strip removes.
- **EVERY SYNONYM EXPANDS AN ABBREVIATION; none contracts one.** Folding
  `division` to `div` left the misspelt `Divsion` compared against a three-letter
  stub (0.60, reads as a different word); expanding compares like with like
  (0.93). `_PREFIX_SYNONYMS` is separate and only fires on letters stuck to a
  number (U14, Yr9), so a BARE "u" is still read as a grade tier the way "A
  Grade" is. **Both found by running it, not by reading it.**
- **THE ASSOCIATION IS A VETO; THE CATEGORY IS ONLY A CAUTION.** Two names run by
  associations we KNOW to be different are not one grade, whatever they are
  called. A classification clash is NOT a veto — a club really does merge a
  junior-sounding cup name into the senior grade it belongs to (this file's own
  shared-fixture note records "F Grade Colts Cup" merged into senior "F Grade"),
  and refusing it would block a merge the platform has already seen happen.
  Coexisting in a season is a caution too, never a veto: CA's older spelling
  turning up mid-season is real.
- **ONLY `same_name` IS EVER BULK-SAFE**, and not even then if the two coexisted
  in a season — `BULK_SAFE_KINDS` is an allowlist, mirroring `MergeTools`'
  `isExactPair`, so a tier added later is manual-confirm until somebody decides
  otherwise.
- **THE DIRECTION IS A SUGGESTION, NOT A DECISION.** The fuller record is kept
  (games, then the newer season, then the shorter name) and the card offers to
  flip it, because which spelling a club wants on its own leaderboard is the
  club's call.
- **THE PAIRS ARE BUILT FROM WHAT THE SCREEN ALREADY DRAWS** (`list_grades_with_stats`),
  so a pair can never name a grade the table does not list and an already-merged
  group is one row and therefore never suggested against itself. A merged group
  answers for every name in it, so it carries its aliases' seasons and
  associations too.
- **`grade_merge_pair_ignores` (294) keys on NAMES, not grade ids**, because a
  grade name spans one row per season and every merge here is name-to-name.
  Stored sorted, so dismissing a pair either way round is one row.
  `services/grade_ignore_ddl.py` is the ONE copy alembic and the lifespan mirror
  both run, per the `vote_medal_ddl` rule.
- **NUMBERED 294 after checking `origin/main`**, which had reached 293 — two
  migrations sharing a revision id break Alembic outright.
- **Verified against a real Postgres**
  (`backend/verification/verify_grade_duplicates.py`, 67 checks through the
  shipped service and route bodies: the whole calibration table re-run as checks
  both ways, every discriminator rule, the DDL applied three times and again over
  a POPULATED table, the sponsored spelling and the punctuation-only rename
  offered, the junior cup offered with its clash as a caution, the three
  destructive pairs refused, the association veto, cross-club both ways,
  dismissal in both directions landing one row, two refusals, and an
  already-merged group not suggested against itself) **with two control runs**:
  with the token rule swapped for the player matcher's 0.90 SequenceMatcher, **18
  of the 67 fail — four of them offering to merge genuinely different grades**;
  with the service absent the suite REPORTS it by name rather than dying on the
  first ImportError.
- **Driven in Chromium** (`frontend/verification/verify_grade_duplicates_browser.mjs`,
  29: the exact merge on the wire, flipping the direction sending the other way
  round, a dismissal going to the ignore endpoint and never a merge, the weaker
  tier's warning drawn once and not twice, a club with nothing to sort out shown
  no panel at all, and no overflow at 390px) **with a control run**: with the
  panel removed it reports 23 missing checks rather than crashing — which it DID
  on the first cut, dying on the first absent locator after two checks, so every
  interaction goes through `press()` now.
- **NOTICED, NOT BUILT**: opponent overlap. Two grades that are really one tier
  play largely the same set of clubs, which is the strongest confirmation
  available from our own data — but it needs club-name matching against
  `home_team`/`away_team` (`club_match_keys` territory) and a wrong-looking stat
  on a merge card is worse than none. The season span shown on each card is the
  cheap half of the same idea. The AFL silo's own Merge Grades screen
  (`routers/afl/merge.py`) is untouched and would need its own pass — its
  categories are single-valued and it has no association column.

<!-- END original CLAUDE.md L2887-2995 -->
<!-- BEGIN original CLAUDE.md L6940-7000 -->
## A duplicate whose first name is shortened is invisible to edit distance (v9.26.1, Aug 2026)

Reported from the Leaderboard: "Brad K Mant" (15,542 runs) and "Bradley Mant"
(10,341, same high score of 194) are one person, Manual Merge finds them in a
second, and Merge Duplicates never suggested them.

- **Nothing was broken — the pair scores 0.78 and the gate is 0.90.** They pass
  every other gate in `_fuzzy_name_pairs` (same first-letter block, length
  difference 1), so the miss is purely the threshold.
- **Edit distance degrades MULTIPLICATIVELY, which is the whole lesson.** Two
  differences stack here: a short form and a middle initial. Alone, `brad mant`
  vs `bradley mant` is **0.857** and `brad k mant` vs `brad mant` is **0.90** —
  either would have been caught. Together they are **0.783**. So a
  two-difference duplicate is not "slightly harder" to catch than a
  one-difference one, it is off the scale, and **lowering
  `FUZZY_MERGE_THRESHOLD` is not the fix** — 0.78 across a 1,500-player roster
  buries the real pairs in strangers.
- **`_name_variant_pairs` compares the name's PARTS instead of the whole
  string**, blocked on (surname, first initial) — free, because every rule in
  `_first_name_link` already requires the first letter to agree. It is a THIRD
  tier (`kind: "name_variant"`), beside exact and fuzzy, not a loosening of
  either.
- **`_first_name_link` is deliberately narrow: a bare initial, or a genuine
  prefix of at least 3 characters.** A nickname that is not a prefix
  ("Bob"/"Robert", "Bill"/"William") is NOT claimed. It would need a curated
  list, and every entry on such a list is a judgement call that produces a
  confidently wrong pair the day it misses. Two characters is too short —
  "Jo"/"John"/"Joe" are three people.
- **Never bulk-mergeable, and that is not caution for its own sake.** A surname
  plus one initial is exactly the shape of two brothers, or a father and son.
  The screen says so in the badge rather than implying a match it cannot make.
- **`_name_parts`/`_middles_compatible` are IMPORTED from
  `services/import_ingest.py`**, not re-typed. That module is the
  historical-import matcher and already decides whether two sets of middle
  initials could be one person; a second copy is how the two start disagreeing
  about what a name is. It is DB-free, so importing it into a router is cheap.
  **Its own `match_players` would ALSO have missed this pair** — the first+last
  tier needs identical first names, and `_parse_initial_form` needs a bare
  single-letter token in first or last position, which "Brad K Mant" (initial in
  the middle) does not have.
- **Detection grouped on `p.name` while the cards render `p.display_name`.**
  So a renamed player was only ever compared under the name the sync wrote, and
  their duplicate read as unlisted even though both cards on screen said the
  same thing. `_name_keys(p)` files a player under BOTH spellings; a player
  therefore enters several blocks, which is why the fuzzy pass now keeps the
  BEST ratio per pair rather than whichever was reached first, and why the
  endpoint carries an `emitted` set so one pair cannot be listed twice.
- **Bulk Approve is an allowlist now (`isExactPair`), not `kind !== 'fuzzy'`.**
  The denylist meant this new tier would have been silently bulk-mergeable the
  moment it shipped. A tier added later must be manual-confirm by default.
- **Verified** against the real shipped functions (39 checks: the reported pair,
  every shape it should and should not catch, the ignore and de-dup rules, one
  read per player however many pairs they are in, and 8ms over a 1,500-player
  roster returning 1 pair) and **driven in Chromium** (16: all three tiers'
  labels, the reason text, Bulk Approve counting only the exact pair, no page
  errors, no overflow at 390px).
- **Not addressed**: `_enrich_player` counts `player_season_stats` and
  `batting_innings` only, so a BetterImport club's player reads 0/0/0/0 on these
  cards even when they have a career in `imported_stats` (the
  `_RESIDUAL_SOURCES` split the junior-stats note describes). That is a display
  gap on the merge screen, not a detection one.
<!-- END original CLAUDE.md L6940-7000 -->
<!-- BEGIN original CLAUDE.md L7749-7780 -->
## Season list tidy-up script (v9.19.4.2, Aug 2026)

Reported for Yarraville: the seasons page was a mix of synced "Summer 1968/69"
rows and bare "1968/69" rows the historical import created (grassroots_id NULL,
no year), interleaved and duplicated. **`python -m app.scripts.cleanup_seasons
<org-id-or-slug>`** (dry-run by default, `--apply` to act) makes the list
uniform:

- **Only manually-created seasons are ever written** (`grassroots_id IS NULL` —
  the documented "not from a sync" marker). A synced season is never renamed,
  re-yeared or aliased, and the merge target is chosen among synced siblings
  first.
- **A duplicate is MERGED, not renamed** — an alias row through the club's own
  Merge Seasons machinery (`season_aliases`), so stats aggregate under the
  canonical season and the merge is undoable from Admin → Seasons. The script
  mirrors the endpoint's chain rule: anything previously merged INTO the manual
  season is re-pointed at the new canonical so resolution stays single-hop.
- **A manual season with no synced sibling is renamed** to "Summer YYYY/YY" and
  given its `year` (which is what fixes the sort order — `_season_sort_key`
  reads the 4-digit year out of the name, and `resolve_season_filter` expands
  year siblings). Two manual seasons for one year: the exact-named or fullest
  one becomes canonical, the other is aliased into it.
- **Two things it refuses to guess**: a year with several synced seasons and
  none named plain "Summer YYYY/YY" (e.g. a masters comp under its own CA
  season id — merging into the wrong one would co-mingle comps), and a manual
  name with no recognisable "YYYY/YY" token. Both are reported and left alone.
- **Verified against a real Postgres** (13 checks: the merge with data counts,
  the rename+year, `1960-61` dash form, year-fill on an already-right name,
  two-manual collapse, the ambiguous-synced skip, exact-name preference among
  two synced, the chain re-point, a pre-existing alias untouched, another
  club untouched, idempotent re-run, slug and org-id resolution).

<!-- END original CLAUDE.md L7749-7780 -->
<!-- BEGIN original CLAUDE.md L7781-7812 -->
## Seasons are editable and deletable from the Seasons page (v9.19.5, Aug 2026)

Follow-up to the cleanup script: Admin → Seasons only ever offered reorder and
merge, so fixing one season's name or year meant a script or SQL.

- **`PATCH /club-admin/seasons/{id}`** (`manual_entries.update_season`, cap
  `MANAGE_MANUAL_ENTRIES`, mirrors AFL's `rename_season`) edits name and/or
  year, with a case-insensitive org-scoped duplicate-name 409. **Deliberately
  not restricted to manual seasons** — the sync never overwrites an existing
  season's name (it only backfills a NULL year, see `sync.py`'s season upsert),
  so a tidied name on a synced season sticks. Audited via `_log_edit`.
- **Delete reuses the existing `delete_manual_season`** (manual-only + empty-
  only), now surfaced as a per-row button. **`_season_in_use` gained
  `player_season_stats` and `imported_stats`** — the deletable seasons are
  exactly the ones BetterImport writes aggregate rows against, both FKs
  cascade, and neither table was checked, so a season full of imported history
  deleted straight through before this.
- **`GET /club-admin/seasons` now returns `synced`** (`grassroots_id IS NOT
  NULL`) so the page only offers Delete on rows the endpoint could ever
  accept. `synced_at` alone was the wrong proxy for this — it's a display
  field.
- **Frontend**: `AdminSeasons.jsx`'s row became `SeasonRow` — inline name/year
  edit (Enter saves, Escape cancels, only changed fields are sent), Delete
  behind a `window.confirm` with the server's refusal reason shown inline.
- **Verified against a real Postgres** (20 route-level checks: rename+audit,
  synced rename persisting, year-only patch, dup/blank/foreign/junk-id
  rejections, cross-club name reuse allowed, the two new in-use guards, all
  three delete refusals, the actual delete, and the `synced` flag) **and
  driven in Chromium** (14 checks: the exact PATCH payload on the wire,
  no-change save sending nothing, confirm dismiss/accept, a refused delete's
  reason rendered, Delete absent on synced rows, no overflow at 390px).

<!-- END original CLAUDE.md L7781-7812 -->
<!-- BEGIN original CLAUDE.md L7813-7853 -->
## Undoing a stats import deletes the players it minted (migration 234, v9.19.4.1, Aug 2026)

Reported from the Leeming Spartans demo: a mis-mapped BetterImport upload
created dozens of surname-only players, and undoing the import left every one
of them behind — `/undo` only ever deleted `imported_stats`, and nothing
recorded WHICH players a batch had created, so it couldn't have known.

- **`players.import_batch_id` (migration 234) is the marker** — set only when
  the import commit itself mints the row, NULL for every synced or hand-added
  player, `ON DELETE SET NULL` so a deleted batch never takes a player with
  it. **A re-import moves the marker forward**: latest-upload-wins re-homes the
  player's rows onto the new batch, so undoing THAT batch is what would leave
  them empty, and the marker has to follow (only where it was already non-NULL
  — a synced player is never stamped).
- **`services/import_cleanup.py` is the one deletability rule**, shared by both
  undo endpoints and the retroactive script. A batch-created player is deleted
  by the undo ONLY when nothing real has attached since: ~40 `BLOCKING_REFS`
  (stats from any source, membership, votes, lineups, achievements, merge
  history…) plus a profile check (photo, contact details, squad, skill
  positions) and a hard stop on any synced identity (`grassroots_id` /
  `playhq_id`). Derivative rows (`import_effective_deltas`, `milestones`,
  aliases) are deliberately NOT blocking — they cascade away with the player.
  Kept players are reported with the reasons, and the undo's audit row names
  both the deleted and the kept.
- **The emptiness check runs after `db.flush()`** — it must not see the
  imported rows the same transaction just deleted, or every player reads as
  still holding data and nothing is ever cleaned up.
- **`python -m app.scripts.purge_import_only_players <org-id-or-slug>`** is the
  retroactive cleanup for batches undone before the marker existed (Leeming's
  case). Candidates are never-synced players only; the same `deletable_players`
  check decides; dry-run by default, `--apply` to act; one club at a time on
  purpose — a hand-added player with genuinely nothing recorded yet is
  indistinguishable from import residue by data alone, so a person reads the
  list first.
- **Verified against a real Postgres** (23 checks: the migration applied three
  times, commit stamping + the pre-existing player NOT stamped, the re-import
  marker move, whole-batch and per-player undo deleting the empty player and
  keeping the one with an achievement, the audit naming both, a synced player
  never deletable, and the script's dry-run/apply against marker-less
  leftovers).

<!-- END original CLAUDE.md L7813-7853 -->
<!-- BEGIN original CLAUDE.md L10460-10557 -->
## THE SHEET IS PARSED ONCE, NOT CARRIED BY THE BROWSER (migration 302, v9.77.0, Sep 2026)

A club's recovered archive is 97 seasons, 7,915 matches and **184,661 rows** in
one `manual_games_scorecards.csv` of about 24 MB, and it could not be imported
at all: `_MAX_GAME_UPLOAD_BYTES` refused anything over 8 MB, so it had to be
split into 92 per-season sheets.

- **RAISING THE CAP ALONE WOULD HAVE DONE NOTHING, AND MEASURING IS WHAT SHOWED
  IT.** The import is preview -> resolve -> commit and **only preview takes a
  file**; the browser held the parsed rows and posted every one of them back as
  JSON on the other two steps. Measured on a 33 MB, 182,154-row fixture: the
  same rows as a request body are **145.6 MB**, because all 33 column names
  repeat on every row. And `resolve` fires AGAIN on every override change, so
  that body went up the wire once per player matched, season picked and grade
  named.
- **THE SERVER-SIDE WORK WAS NEVER THE PROBLEM.** `_resolve_games` over that
  whole sheet is **1.9s**. The entire interactive cost was the upload, which is
  why the fix is to stop sending it rather than to make the matching faster.
- **SO THE ROWS ARE STAGED AND THE TWO LATER STEPS NAME THEM BY TOKEN.**
  Measured end to end through the shipped route bodies: the wizard now sends
  **159 bytes** per resolve/commit instead of 145.6 MB.
- **`rows` STAYS ON THE REQUEST, AND THAT IS WHAT MAKES THE CHANGE SAFE.**
  `GameResolveRequest` takes EITHER; `_rows_for` prefers the token and falls
  back. The pre-existing 90-odd checks in the suite all drive the rows path, so
  their passing unchanged IS the proof a direct caller is unaffected, and the
  suite additionally asserts the two shapes resolve byte-for-byte alike.
- **A TABLE, NOT THE MEDIA VOLUME, AND THE REASON IS THE OPPOSITE ONE.** These
  rows live for one sitting and are deleted the moment the import commits, so
  they must never be backed up;
  `/mnt/media/bettercricket/internal/videos` sits outside the backup because a
  video is PERMANENT and merely too big to dump. A table also makes expiry and
  club scoping one DELETE rather than a directory walk, and this is text.
- **SCOPED IN THE WHERE CLAUSE, NEVER FETCHED THEN CHECKED**, so another club's
  token, another user's, an expired one and one that never existed are
  indistinguishable. An expired row reads as absent BEFORE any sweep runs: the
  sweep (on preview, the one moment somebody is already paying for a large
  write) is a tidy-up, never the thing that enforces the deadline.
- **THE TOKEN IS DISCARDED IN THE SAME TRANSACTION AS THE GAMES**, so a
  rolled-back import keeps its staged rows and can be retried, and a landed one
  can never be imported twice.
- **THE COMMIT WAS ALREADY FINE, AND THAT WAS MEASURED RATHER THAN ASSUMED.**
  `_write_games` gives each game its OWN savepoint and flushes as it goes, so
  nothing accumulates: `db.commit()` at the end is **instant** and no chunking
  is needed. Per-request resident memory is ~460-620 MB across the three steps.
- **BUT THE WRITE IS 68-124s, PAST nginx's OWN 60s `proxy_read_timeout`
  DEFAULT** — which would hand the browser a 504 while the backend carried on
  and finished, the exact "Gateway Time-out on a job that was working" shape
  this deployment has already been bitten by once. Found by timing the write,
  not by reading the config. So resolve and commit get their own locations for
  the TIMEOUT, not for the body size.
- **BOTH CAPS HAVE TO MOVE OR THE RAISE IS INVISIBLE.** `client_max_body_size
  20m` on `location /api/` refuses the body before FastAPI is reached. The
  suite asserts the app constant and the nginx block agree, so they cannot
  drift.
- **AN EXACT `location =`, BECAUSE A TRAILING-SLASH PREFIX ONE 301s A POST.**
  nginx redirects `/games/import` to `/games/import/` whenever a trailing-slash
  prefix location with a `proxy_pass` exists, and a 301 on a POST drops the
  body — which would have broken the strict single-shot `POST /games/import`
  beside it, silently. **Written as a prefix first and caught by running nginx
  against a stub backend**, not by reading the config: eight probes across four
  routes at 10/30/70 MB. That endpoint is deliberately left on the ordinary
  /api/ limits, since it has no app-level size cap and raising nginx's would
  let an unbounded body reach a route with no guard.
- **THE PREVIEW'S OWN `rows` REPLY IS CAPPED AT THE OLD 8 MB LIMIT.** Returning
  them for a 24 MB archive is a ~100 MB download nobody reads. The KEY stays on
  the wire whatever the size (the `plan_report.unassigned` rule), and no caller
  can regress because a sheet over the old cap was refused outright and so
  never received them.
- **Verified against a real Postgres** (`verify_manual_games_import.py` is 121
  checks now: the DDL applied three times over a populated table, a deleted
  club's staged rows going with it, the whole sheet staged in the shape
  `_resolve_games` reads, a token with NO rows resolving it, the same again on
  the next override change, all four scoping refusals, an expired token absent
  before the sweep, the commit spending its token so the same archive cannot
  land twice, and the two request shapes resolving byte-for-byte alike) **with
  two control runs**: with the service absent it REPORTS it and the other 92
  still pass; with the token ignored, **11 fail** on exactly that behaviour.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN, HIT TWICE IN ONE
  CHANGE.** `preview_manual_games` takes a session now, so the first control
  died on an unexpected keyword at check 1 and said nothing about the other
  118 — a `preview()` wrapper reads the shipped signature instead. Then the
  neutered run died on a 422 from `commit_manual_games`; every commit call in
  that section reports the refusal rather than raising.
- **A CHECK THAT PASSES AGAINST THE BROKEN CODE IS NOT A CHECK.** "the override
  landed" was trivially true of an EMPTY sheet, because an override is applied
  to the match map whether or not a row was found. It asserts the player's
  `sheet` figures too now, which are summed from the rows themselves.
- **A CHECK THAT MEASURES THE HARNESS IS NOT A CHECK EITHER.** The nginx probe
  first reported 500s that were its own scratchpad temp dirs being unwritable
  by `www-data`, and the end-to-end run died on `v_effective_player_season_stats`
  missing — both harness gaps, not the feature's. `_view_ddl.py` is what the
  suites use for the second.
- **NOTICED, NOT BUILT**: nothing expires a staged sheet except the next
  preview, so a club that uploads once and never returns leaves its rows until
  somebody else imports. A nightly sweep is the obvious follow-up and was not
  worth its own job for a table that is empty almost always. The strict
  single-shot `POST /games/import` still has no app-level size cap of its own.

<!-- END original CLAUDE.md L10460-10557 -->
<!-- BEGIN original CLAUDE.md L10558-10636 -->
## A game brings its own season with it (v9.54.2, Aug 2026)

Reported straight after the uploaded-card fix above: the 1974 game is filed
under **Summer 1999/00**, and the club's season list starts at 1996/97 — so
there is no filter that finds it.

- **NOTHING WAS BROKEN. THE FORM COULD NOT EXPRESS THE RIGHT ANSWER.**
  `manual_games.season_id` is NOT NULL and the Upload Scorecard form requires
  a season, but the dropdown only ever offers seasons the club already holds.
  A 1974 card at a club whose history starts in 1996 therefore HAD to go in
  under something wrong. Verified against the live row before touching a line
  of it: `season_name` reads "Summer 1999/00" for a `played_at` of 1974-11-30.
- **THE PAGE HAD ITS OWN SEASON BOUNDARY, AND IT DISAGREED WITH THE REST OF
  THE APP.** `AdminScorecardUpload`'s local `seasonStartYear` used Sep–Dec,
  while `votes.season_year_for` and `selection_rules`' default `start_month`
  both count a club year from **July** — so the two answered differently for a
  July or August fixture. The rule is server-side now
  (`services/season_resolve.py`) and the page asks rather than deriving.
- **`season_resolve` IS ONE DEFINITION, NOT A SECOND ONE.** `canonical_name`
  and `season_start_year` MOVED there out of `scripts/cleanup_seasons`, which
  imports them back — a tidied season list and a newly uploaded card cannot
  end up disagreeing about what 1968/69 is called.
- **A SEASON'S YEAR IS READ OFF ITS NAME FIRST, THEN THE `year` COLUMN.** A
  manually created season can carry a NULL year (one of the states
  `cleanup_seasons` exists to repair), so matching on the column alone mints
  a duplicate beside a season the club already has. The suite seeds a bare
  "1980/81" with a NULL year and asserts a 1980 game JOINS it.
- **A YEAR CAN HOLD SEVERAL SEASONS** (Summer and Winter, or a masters comp
  under its own CA id), so the canonically named one wins, then a synced one,
  then whatever is left. Picking arbitrarily is how a game lands in the wrong
  competition.
- **`season_id` IS OPTIONAL ON THE WIRE NOW, and that is the real fix.** Omit
  it and `_resolve_game_season` files the game under the season its own date
  falls in, creating it when the club has none — so any caller gets it right,
  not just the browser. **An explicit season still wins**: an admin filing a
  game somewhere deliberate is not something to override.
- **THE GRADE IS THE OTHER HALF, and forgetting it would have left the fix
  half-done.** A season minted for a 1974 card has NO grades, so the game
  would be ungraded and still missing from every grade filter. `grade_name`
  creates it inside the resolved season — and writes `category` AND
  `categories`, per the rule that a site setting one must set the other.
- **THE LOOKUP ENDPOINT IS READ-ONLY ON PURPOSE.** `GET
  /manual-entries/seasons/for-date` is asked the moment a card is read, long
  before anybody has decided to import it; minting seasons for cards that are
  never imported would be worse than the bug. The CREATE happens on the
  screen's own explicit call, and again server-side at import.
- **A MISMATCH IS SAID OUT LOUD RATHER THAN REFUSED.** Picking a season the
  date does not fall in is still allowed — a club may file a game
  deliberately — but the screen now names both the season picked and the one
  the date belongs to. Silence there is what let this happen.
- **The date can be corrected after the read, and the season follows it.**
  Otherwise fixing a misread year leaves the game filed under the year that
  was misread.
- **`python -m app.scripts.refile_manual_game_seasons <org|all>`** moves games
  already filed wrongly, carrying the grade across BY NAME (pointing at the old
  grade row would leave the game's grade and season contradicting each other).
  Dry-run by default: a game an admin deliberately filed outside its date's
  season is indistinguishable from a mistake by data alone, so a person reads
  the list first — the `purge_import_only_players` posture.
- **Verified against a real Postgres** (`backend/verification/verify_season_resolve.py`,
  42 checks through the shipped route bodies and services: the reported case
  replayed end to end, the July boundary at both edges, an existing season
  reused rather than duplicated, a second game joining the season just made,
  an explicit choice honoured, both refusals, another club's season never
  offered, the NULL-year name match, the sibling-season preference, and the
  repair script's dry run / apply / grade carry / idempotent re-run / leave a
  correctly filed and an undated game alone) **with a control run** that
  reproduces the report exactly: the old `ManualGameIn` refuses a card with no
  season, and a 1974-11-30 card then files under "Summer 1999/00".
- **Driven in Chromium** (`frontend/verification/verify_scorecard_season_browser.mjs`,
  20 checks: the for-date call on the wire, the exact create payload, the
  season selected and the note shown, no create for a year the club already
  has, the mismatch note naming both seasons, the season following a corrected
  date, and no overflow at 390px) **with a control run**: 10 fail against the
  previous commit, including the season field reading "— choose —".
- **`text=Season` ALSO MATCHES THE SIDEBAR'S "2026/27 SEASON"**, which at
  390px lives inside a closed drawer and never becomes visible — the probe
  waits on the review form's own date field instead.

<!-- END original CLAUDE.md L10558-10636 -->
<!-- BEGIN original CLAUDE.md L15560-15609 -->
## Uploaded scorecard missing from the public Games page (migration 169, v8.76.1, Jul 2026)

Reported: a scorecard uploaded via `/admin/upload-scorecard` for Legana
Cricket Club never showed up on `/legana-cricket-club/games`.

**Root cause**: the upload form (`AdminScorecardUpload.jsx`) lets Grade be
left as "— none —" (Season is required, Grade isn't). `GET
/organisations/{id}/results` (`organisations.py::get_org_results`, what
`GamesPage.jsx` calls, and it always applies a season filter — it
auto-selects the most recent season on load) derived season purely by
joining `grades gr ON gr.id = g.grade_id` then `seasons s ON s.id =
gr.season_id`. With `grade_id` NULL, both `gr` and `s` came back NULL, so the
season filter (`s.id = :season_id ...`) could never match — even though
`manual_games.season_id` itself is a required, always-set column. The row
was silently excluded under every season, on every page load.

**Also found while fixing it**: the same query's org-ownership check had a
bare `g.source = 'manual'` clause with no organisation check at all, so
literally any club's manual game read as "ours" on every other club's
results/W-L-D headline — a cross-club data leak. `games.py::list_games`'s
`api_games` sub-query had the identical clause even though manual games are
already fetched separately and correctly (org-scoped) by
`_fetch_manual_games_as_list` in the same function, so that endpoint doubly
leaked (any org's manual games) and duplicated (this org's own manual games,
once via each path). `manual_entries.py`'s upload-time duplicate-check
(`check_scorecard_duplicate`) had the same grade-required join, so it also
couldn't detect an existing grade-less manual game on re-upload.

**Fix**: `v_effective_games` now carries `season_id`/`organisation_id`
columns directly (migration 169 — for `games`, derived via
grade→season same as before; for `manual_games`, its own always-set
columns), appended at the end so no existing consumer (none `SELECT *`
against this view) is affected. `get_org_results`, `_club_results`
(aggregations.py, the headline W/L/D — explicitly mirrors `get_org_results`
so the two agree) and `check_scorecard_duplicate` now join season off the
view's own `season_id` and check `g.organisation_id = :org_id` instead of
the blanket `g.source = 'manual'`. `list_games`'s `api_games` sub-query now
scopes to `g.source = 'api'` only, since manual games are handled entirely
by the separate, already-correct fetch. Verified end-to-end against a real
local Postgres instance (base schema + the view + sample cross-org data)
before shipping — confirmed the bug reproduced against the old query and no
longer does against the new one, including a regression check that an
ordinary graded API-synced game is unaffected.

**Anti-pattern reminder**: a manual game can legitimately have no
`grade_id` (Grade is optional on upload) but always has a `season_id` and
`organisation_id` — don't derive either one by joining through `grade_id`
for a `v_effective_games` row; read the view's own `season_id`/
`organisation_id` columns instead.

<!-- END original CLAUDE.md L15560-15609 -->
<!-- BEGIN original CLAUDE.md L15610-15645 -->
## Uploaded scorecards log — edit/undo from the upload page (v8.76.2, Jul 2026)

`/admin/upload-scorecard` (`AdminScorecardUpload.jsx`) was a one-shot flow —
upload, review, import, done — with no way to see or revisit what had already
been uploaded from that page short of finding it in the general-purpose
"Manual Games" tab on `/admin/manual-entries`. It now has its own list,
scoped to just the scorecards that came through the photo-upload flow.

- **`GET /club-admin/manual-entries/games`** (`list_manual_games`) gained
  `is_photo_upload` (whether `manual_games.extracted_payload` is set — the
  AI reader's saved match+innings JSON, present only for a photo upload, not
  a hand-typed manual game) and `created_by_name` (a `LEFT JOIN users`,
  mirroring the pattern `list_audit` already used). The list keeps the full
  `extracted_payload` blob out of the response (popped after computing the
  boolean) — it's only needed in full when a single game is reopened via
  `GET /games/{id}` (already returned it; unchanged).
- **Jump back in ("Edit")**: since `extracted_payload` is the exact
  `{match, innings}` shape the review screen already edits in memory,
  reopening a past upload replays it through the SAME review UI used at
  upload time — no separate "already-imported" editor to keep in sync. The
  WK-catch split (`wkByPid`, not itself persisted) is reconstructed from the
  saved `fielding_stats.catches_wk` per player. Saving calls `PATCH
  /games/{id}` instead of `POST /games`; a fresh photo read always clears
  `editingId` first so it can't accidentally overwrite a prior edit target.
- **Duplicate check gained `exclude_id`** (`check_scorecard_duplicate`) — 
  editing an already-saved game used to flag the game against itself as a
  "possible duplicate" on the same date, since the query had no way to
  exclude the row being edited.
- **Delete** reuses the existing `DELETE /games/{id}`; the list's own footer
  points at `/admin/manual-entries#audit` for restoring a deleted or edited
  entry rather than re-implementing undo/restore on this page too — one
  audit trail, not two.
- Verified end-to-end against a real local Postgres instance: the
  `is_photo_upload`/`created_by_name` join, and the `exclude_id` fix to the
  duplicate check, both before shipping.

<!-- END original CLAUDE.md L15610-15645 -->
<!-- BEGIN original CLAUDE.md L15646-15737 -->
## Scorecard reader — multi-format, PDFs, fielding column, eval set (v8.80.0, Jul 2026)

`scorecard_ocr.py` (the Upload Historical Scorecard reader) taught about more than
the WACA-style scorebook, prompted by a Toowoomba club's archive (1976 scorebook
pages + a 1993 TCA "Official Summary of Match" form). Full how-to-improve-it doc:
**`docs/scorecard-reader-eval.md`**.

- **Prompt knows three format families**: the two-page scorebook, the association
  match-summary form (one club's side only + opposition as a bare "10/111" totals
  line → an innings with totals and an EMPTY batting list), and "anything else,
  note the layout in read_notes". Also warned about: tally strokes in extras
  boxes (the numeral total column wins), wickets-first "7/164" notation,
  two-digit years → 1900s, two-day matches (first day = match.date), and
  **pre-1980 Australian 8-ball overs** → new `match.balls_per_over` (reconcile's
  overs check + `overs_to_balls(o, balls_per_over)` honour it; DB storage is
  unchanged — overs stay as written on the card).
- **Result inference is the ONE allowed deviation from transcribe-only**: blank
  result box + completed innings that decide it → model may fill `result` and
  set `result_inferred`, which the review screen flags ("worked out from the
  scores, check it"). Everything else stays faithful-transcription-only.
- **New `innings[].fielding` section** ({name, catches, catches_wk, stumpings,
  run_outs}) for cards that credit fielders separately from dismissals (OWN
  CATCHES column, W/K = keeper). Attached to the innings where that side was
  FIELDING. The extract endpoint adds these names to the roster-suggestion set;
  the review screen shows them as an editable, player-matchable table, and
  import merges them with the dismissal-derived fielding by **max per stat** so
  the same catch seen both ways counts once. Re-editing a saved upload seeds
  this table from the saved `fielding_stats` so a re-save can't drop
  column-sourced fielding.
- **PDF uploads work end to end**: `guess_media_type` recognises `.pdf`,
  `extract_scorecard` sends PDFs as native `document` blocks (no rasterising;
  anthropic 0.40.0 passes the dict through), the file input accepts them and
  previews show a file chip. Mind the API's ~32MB request cap for huge scans.
- **Eval harness** `python -m app.scripts.scorecard_eval <cases_dir>`: local
  (never committed) case folders of scans + a verified `expected.json`; only
  keys present in the truth file are scored, rows matched by normalised name.
  Run before/after any prompt/schema/model change to the reader — that's the
  training loop, since the model itself never learns from uploads.
- **Tracked-fields toggles (v8.80.1, migration 184)**: a "This card tracks"
  panel on the review screen (balls faced / 4s & 6s / maidens / bowler
  wides+no-balls). Unticked → the column is hidden AND imports as **NULL, not
  0** — `manual_batting_innings.fours/sixes` and
  `manual_bowling_spells.maidens/wides/no_balls` went nullable (the synced
  tables always were, so every effective-view reader already copes). The
  pydantic defaults stay `Optional[int] = 0`, so the CSV import and hand-typed
  manual-game form (which omit rather than null the fields) are byte-for-byte
  unchanged; only an EXPLICIT null means "not recorded". Toggle defaults come
  from whether the reader found any value; re-editing a saved upload recovers
  the choice from the stored rows' nulls. The prompt also tells the model to
  leave untracked stats null, never 0.
- **Card-error vs misread flags (v8.80.3)**: `reconcile()` now returns
  `list[dict]` `{kind, text}` instead of `list[str]` — `kind` is `card_error`
  (the card's OWN figures don't reconcile: batting≠total, wickets≠FOW count,
  bowling≠total, overs mismatch — a decades-old scorer slip, fix-or-keep) or
  `misread` (a value the READER likely got wrong: dismissal bowler not in the
  analysis, boundaries>runs, keeper catches>catches — worth fixing). The reader
  still transcribes faithfully; nothing auto-corrects. Frontend
  (`AdminScorecardUpload.jsx`) renders two boxes: amber "the original scorecard
  doesn't add up here (correct below or import as-is to keep the card's
  figures)" and red "likely misreads — worth fixing above", and the import
  confirm spells out the keep-or-fix choice (button reads "Import, keep
  original" when only card errors remain). The eval prints `w["text"]`. Old
  plain-string warnings tolerated on the frontend via `asWarn`. Per direct
  request: read exactly what the card says, flag where it's wrong, let the user
  choose.
- **Name cross-referencing across the card (v8.80.2)**: the standout
  handwriting win, from a real correction pass — the same person is written
  many times (batting order, bowling analysis, a "c Smith" catcher, a "b Jones"
  wicket-taker, fall-of-wickets) with wildly varying legibility. The prompt now
  says to read EVERY occurrence and use the clearest as the true spelling, then
  use it everywhere: the **bowling analysis is authority for bowler names** (a
  dismissing bowler is always one of the analysed bowlers), the **batting order
  authority for batter names** — but never collapse two players who merely share
  a surname (N Ziebell ≠ R Ziebell). `reconcile()` backs it with an advisory:
  `_name_close` (surname-level `SequenceMatcher`, ≥0.6) flags a dismissal bowler
  whose name isn't among that innings' analysed bowlers — the exact
  "S Willingslow" that's really "G Wittingslow" case. Worked examples baked into
  the prompt (Wittingslow, Houser/Heuser, Pascoe initials). Verified truth file
  for the 1976 Railways match kept locally as the first eval golden case.
- **Roster matching = the historical-import engine (v8.80.1)**: the extract
  endpoint now runs card names through `import_ingest.match_players` (the same
  exact → middle-initial-tolerant → "Surname Initial" form → blocked
  SequenceMatcher pipeline BetterImport and the Merge Players fuzzy pairs
  use) instead of the old bespoke `_suggest_player` token matcher.
  Auto-fill policy: exact hits, plus a single candidate at confidence ≥0.9
  (the unique "G Evans" surname+initial case — parity with the old matcher);
  everything else ships as `result["match_info"]` candidates, which
  `PlayerSelect` shows as a one-click "CLOSE MATCHES" group with confidence %
  at the top of every picker (batters, bowlers, dismissal fielders, own-catches
  rows). `_suggest_player` still exists for `_replace_game_children`'s
  import-time FOW/partnership name resolution — unchanged on purpose.

<!-- END original CLAUDE.md L15646-15737 -->

## One sheet line filed under two same-name players (Oct 2026, script only)

Leederville's Paul K Jones showed 512 matches and 4,324 runs against the club sheet's 258 and 1,165. Paul G Jones, a different person with the stored name "Jones, Paul", was correct. Paul K's season-less "Prior Seasons & Adjustments" line was 338 matches and 3,360 runs: his own 84 and 201 plus Paul G's sheet line (254 games, 3,159 runs). Paul K's profile total minus Paul G's profile total equalled the sheet figure for matches, innings, wickets and catches. The reconciler sums every `imported_stats` row a player holds, so a copy of another player's line adds that career. `app/scripts/remove_cross_attached_imports.py` removes the keeper's rows that are exact copies of the other player's, with an audit entry holding each row. The cause of the original mis-filing was not established (no production database access in the session). The matcher already flags two same-name players as ambiguous, so a manual pick at import time or an older import is the likely source. Targets for Paul K's season-less line after the fix: matches 84, innings 65, not outs 10, runs 201, wickets 64, runs conceded 1,357, catches 30.
