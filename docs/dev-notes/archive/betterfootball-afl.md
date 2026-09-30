# Archive: betterfootball-afl

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: The AFL / BetterFootball silo and everything ported to it.
Read the distilled rules first: `docs/dev-notes/guides/betterfootball-afl.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L76-150 -->
## BetterSelect on BetterFootball: a ground, a bench and football's rules (v9.100.0, Sep 2026)

Asked for as "port across BetterSelect and make everything football": 18 on the
ground and up to 10 on the bench, players classified by position rather than as
batters and bowlers, fixtures from PlayHQ, AFL-compliant selection rules.

- **FOOTBALL'S OWN MODULE, NOT CRICKET'S SCREENS.** Cricket's selection pool,
  availability matrix and rules engine all read cricket per-innings tables
  (`game_appearances`, batting, bowling) and cricket rule kinds (bowling
  workload, overseas, nets), so none of them could be mounted. Football has
  `services/afl/select.py`, `services/afl/select_rules.py`,
  `routers/afl/select.py` (`/afl-select/*`, behind `require_module("select")`,
  writes on `MANAGE_SELECTIONS`) and five screens under
  `frontend/src/afl/pages/admin/select/`. The sport-neutral SHARED tables are
  reused as they are: `fixtures`, `teams`, `team_members`, `player_availability`,
  `player_availability_periods`.
- **A SIDE IS A FIELD, SO THE TEAM SHEET IS ITS OWN TABLE** (`afl_lineup_slots`:
  slot = a field position, `INT` bench or `EMG` emergency; captain and
  vice-captain). `fixture_lineups` is an ordered batting list and is not
  touched. Six lines (B, HB, C, HF, F, Followers); a smaller side drops
  positions in a fixed order (`_DROP_ORDER`: wings, then ruck rover...) so a
  16-a-side junior grade is played without wings.
- **FIXTURES ARE THE GAMES THE SYNC ALREADY HOLDS.** The football sync writes
  every game on the draw into `games` whether played or not. `sync_fixtures`
  (end of every sync, and the Update from PlayHQ button) upserts a `fixtures`
  row keyed on the GAME'S OWN ID, so a side picked for a fixture is the side
  for that game. A fixture is never deleted by a sync.
- **FORM IS OUR SIDE ONLY** — `afl_player_game_lines` carries both teams, so
  every read joins `l.side = d.our_side`. The control run (join removed) reads
  the opposition's line as ours: 4 games for 3, a best on ground that isn't his.
- **"HIGHER SIDE" IS THE SQUADS ORDER.** `grade_ranks` maps a grade to the
  `teams.sequence` of the side that plays in it, directly or by the `afl_teams`
  name PlayHQ filed under that grade in any season. Seeding orders reserves
  before "Premier": a grade called "Premier C Reserves" is a reserves grade.
- **THE RULES** (`RULE_KINDS`): team_size (info; default 18/10/3), age (as at
  1 January of the season by default, the AFL community basis), finals
  qualification (home-and-away games, in this grade / this grade or higher /
  club), higher_grade_limit, concussion (21 days by default, counted from a
  dated `incident` entry, a `permit` is the medical clearance), registration,
  fees, custom. Silence where the data can't answer, as cricket keeps.
- **THE PLAYER'S OWN LINK IS CRICKET'S** (`public_availability` mounted on
  football, `PublicAvailability` at `/avail/:token` in the football app). Its
  dormancy rule (`availability.dormant_player_ids`) now also reads football's
  match record when `afl_player_game_lines` exists; without that every football
  player read as never-played and nobody was ever dormant.
- **Verified against a real Postgres** (`verify_afl_select.py`, 73 checks
  through the HTTP stack: module gate, sides seeded and ordered, fixtures keyed
  on the game, squads filed, availability and periods, the ground, save and
  refusals, the clash, the team sheet, every rule, the player's link) **with a
  control run**: our-side scoping and football dormancy removed, 4 fail. Driven
  in Chromium (`verify_afl_select_browser.mjs`, 54, seeded by
  `seed_afl_select_browser.py`) **with a control run**: 42 of the 54 fail
  against the previous build, reported rather than crashed.
- **THE SWEEP OF WHAT WAS PORTED EARLIER.** The shared services that seed a club's
  starter data were cricket-only: qualifications, role types and roles, committee
  titles ("Vice President - Men's Football"), starter facilities and gear, the
  club diary's months, the roster's Match Day roles (goal and boundary umpire,
  timekeeper, team manager) and the "Football Operations" department. Each reads
  `settings.sport`, so cricket is byte-for-byte unchanged. On the frontend:
  BetterSocials offers football positions in place of batter/bowler/keeper, strips
  "Football Club"/FC/AFC/JFC off an opposition name, and hides the scorecard
  post; fee formats read as football ones; the Xero and Square callback URLs
  carry the `/afl/` base; a club segment on a cricket-only field is not offered;
  "nets" is not a facility type; copy that named BetterCricket reads
  `PLATFORM_NAME`.
- **THE EARLIER BROWSER SUITES NEED THEIR OWN FIXTURE.** They assert on named data
  (a "Rivals" opponent, a club holding every BetterAdmin module), so run against
  the Select seed they fail for the fixture, not the code. With the club given
  the modules BetterAdmin is 132/132; `seed_afl_socials_browser.py` rebuilds the
  Socials fixture and that suite is 23/23. Every backend football suite re-run
  green (select 73, social 27, shared modules 28, settings 41, admin extras 28,
  competitions 37, seasons 21, fee match days 8, manual entries 75, profile 21).
- **NOTICED, NOT BUILT**: football votes could offer the picked side as an
  eligibility source on game night (they read the synced team list); nothing
  pushes a side back to PlayHQ.
<!-- END original CLAUDE.md L76-150 -->
<!-- BEGIN original CLAUDE.md L4666-4751 -->
## BetterFootball gets Manual Entries — a delta, not a replacement (v9.43.0, Aug 2026)

Asked for by pointing at cricket's `/admin/manual-entries#season` and saying
"build this for betterat.football". That hash is the **Adjustments** tab: add
or correct a player's totals, season blank for a career-only one.

- **ONE table, `afl_manual_adjustments`, because `season_id` is nullable and
  that IS the distinction.** Cricket needs `manual_season_adjustments` AND
  `manual_career_adjustments` because its career deltas carry a different
  column set; football's don't. One table is what lets the screen offer "leave
  the season blank" as a plain choice rather than two forms that look the same,
  and it is why the cricket UI already merges its two lists back together.
- **AN ADJUSTMENT IS ADDITIVE, and that is the whole design.** It carries no
  `NOT EXISTS` gate against the synced rollup anywhere it is read, unlike
  `afl_imported_stats`, whose rows only ever fill a gap the sync hasn't
  covered. An adjustment is a delta an admin typed BECAUSE of what the sync
  holds, so suppressing it where the sync already covers that player-season
  would do nothing in exactly the case it was entered for. Correcting a season
  means entering the SHORTFALL, and every confirm on the screen says so.
- **`services/afl/manual_stats.py::manual_branch` is the one definition of the
  UNION arm**, pasted by name into all thirteen reads. Thirteen hand-written
  copies of the same arm is how the leaderboard and the record book start
  disagreeing about a player's career. Each entry in `columns` is either a name
  from its map (aliased, so the arm lines up with the branch above it) or a raw
  expression passed through — a UNION matches by POSITION, so the two kinds
  interleave in whatever order the caller already uses.
- **A career-only row needs no exclusion clause anywhere.** A season-scoped read
  binds `m.season_id = :season` and a season-keyed one INNER JOINs `seasons`;
  both drop a NULL season for free. What's left is the career reads, which is
  exactly where it belongs.
- **`season_by_season` needed two things nothing else did.** A season can now
  produce more than one grade-less row (the sync's rollup plus a whole-season
  adjustment), which rendered the same year TWICE on the profile — they fold.
  And an adjustment entered against ONE grade of a season still belongs in that
  season's headline: the synced rollup was computed without it, and the
  existing synthesis only fires for a season with no whole-season row at all.
  So a `src` marker rides along, the per-grade manual deltas are held aside
  before the merge-group fold loses it, and applied after. The suite asserts
  the season table sums to the career total.
- **`most_goals_in_a_season` now SUMS per player-season before ranking.** An
  imported row can't coexist with a synced one for the same player-season (the
  gate), but an adjustment can — that is what a correction is — so without the
  grouping a +5 correction listed as its own 5-goal season in the record book.
- **`manual_edit_logs` is reused, not reinvented.** It is ORM-mapped on the
  shared Base, so it already exists in an AFL database. The undo is richer than
  cricket's on one point: an import snapshots each row's BEFORE state, so
  undoing an upload puts an overwritten adjustment back rather than leaving the
  overwrite standing.
- **Deliberately NOT unique on (player, season, grade).** Merging two players
  legitimately brings two rows onto one key, and additive rows read correctly as
  two; the alternative is refusing a legitimate merge or silently summing rows
  nobody asked to combine. A second one created BY HAND is refused (409), which
  is where a duplicate would be a mistake rather than a merge.
- **A merge MUST move them, and the reason is the opposite of the imported
  case.** `afl_imported_stats` has no FK, so forgetting it orphans rows;
  `afl_manual_adjustments` DOES cascade on `players`, so forgetting it DELETES
  the removed player's corrections outright. `_move_side_tables` carries them
  and `afl_merge_logs.adjustment_ids` (idempotent ALTER in the lifespan) is what
  lets an undo hand back exactly those rows. A split moves a season's
  adjustment; a career-only one has no season to attribute and stays put, same
  as an imported row whose season never resolved.
- **No new season endpoint.** The Import Stats wizard already owns
  `POST /club-admin/imports/seasons` and creates the identical row. A grade
  create is new (`/manual-entries/grades`) because nothing else offered one.
- **Deliberately NOT built: per-game manual entry.** Football's answer to
  "type a match in" is Import Results, which writes real `games` rows from the
  club's own register — a better answer than a hand-typed scorecard, and not
  what `#season` points at.
- **Noticed, NOT fixed**: `merge._enrich_player` counts `afl_player_season_stats`
  only, so a club whose history came from an import or an adjustment reads
  0/0/0/0 on the Merge Duplicates cards. Pre-existing, and the same gap cricket
  documents for its own `_enrich_player`.
- **Verified against a real Postgres** (75 checks through the shipped route
  bodies and read helpers, with the schema built by the real AFL lifespan run
  twice: every refusal, the audit summary, additivity against a synced season,
  the season table reconciling with the career total, the leaderboard both
  scoped and not, the vote board, the record book's summed season row, the
  dashboard panels, the admin roster, cross-club isolation, the season-delete
  guard, the CSV template round-tripping through the importer's own parser, a
  re-upload correcting rather than doubling, all five undo paths, and merge /
  undo-merge / split carrying the rows) and **driven in Chromium** (47: the
  exact payload on the wire for create and for the spreadsheet's CSV, the
  career-only confirm wording, a dismissed confirm sending nothing, an inline
  season create, the delete and undo requests, the deep-linked tab, no page
  errors, no overflow at 390px).

<!-- END original CLAUDE.md L4666-4751 -->
<!-- BEGIN original CLAUDE.md L6644-6759 -->
## BetterFootball: a re-graded team's first rounds, club competitions, navbar search, splitting a player (migration 262, v9.30.0, Aug 2026)

Four things reported off Hampton Hammers' page. The first is the one worth
remembering.

### `discoverTeams` reports the grade a team is in NOW, and that loses rounds

Reported: Hampton's Under 19s show from round 6 of 2026 and the first five
rounds are simply absent. They opened the year in **Under 19s Division 1** and
were re-graded to **Division 2** from round 6.

- **Nothing was broken. The grade was unreachable.** `discoverTeams` answers
  with each team's CURRENT grade and carries no history at all, so the division
  the side started in never enters `grade_infos`, `_discover_grade_games` is
  never pointed at its fixture, and those games are never discovered. Verified
  live: `discoverTeams(season aea5195c, org f0727a8b)` returns exactly three
  teams, the U19s under Division 2 alone.
- **`discoverTeamFixture(teamID)` is the fix and it WORKS on the AFL tenant**
  (it does not on cricket's Grassroots API, per the note further down about the
  two APIs disagreeing). It returns the team's whole season round by round with
  **the grade on each round**, which is the only place PlayHQ says a team
  changed division. For the U19s it returns 19 rounds: 5 in Division 1
  (a9823a21) and 14 in Division 2 (c1d73395).
- **`_former_grades_for_team` filters two ways, and both are load-bearing.**
  Every game in a round comes back, not just ours, so it keeps only rounds where
  the team id is actually one of the two sides. And it drops a grade whose
  `round.grade.season.id` is not the season being synced, so a team id PlayHQ
  reuses across years can't drag another season's grade in.
- **A former grade becomes an ordinary entry in `by_grade`**, so the existing
  game-discovery walk picks it up with no special-casing, and a plain **Sync
  Now** is what pulls the missing rounds in. What it must NOT do is move the
  team ROW: `afl_teams.grade_id` holds one grade, and that is the division the
  side is in now, so `is_current` guards the write. Current grades are inserted
  into `by_grade` first, so a brand-new team row is always created under its
  current grade.
- **`link_grade_manually` (paste a PlayHQ match link) still exists** and is
  still the way in for a grade even this can't see. It is no longer the only
  way, which is the point: nobody knew to use it.
- **`stats["former_grades"]` counts what was found**, so a re-grade the club
  never mentioned reads as something the sync discovered rather than an
  unexplained jump in the grade count.
- **Verified against live PlayHQ** through the shipped functions: the reported
  pair found (`{'a9823a21': 'Under 19s Division 1'}`), nothing found for the
  Seniors or Reserves (no false positives), the current grade never re-reported
  as a former one, the season guard, and the Division 1 fixture yielding exactly
  the 5 missing Hampton games, rounds 1 to 5.

### `organisations.competitions` (migration 262)

- **The same `{name, from_year, to_year}` shape as `previous_names`, sharing
  ONE validator** (`club_history._clean_year_spans`) rather than a second copy
  of rules about what a year is. Its own column because a club changes
  competition far more often than it changes its name.
- Shown beside the season picker on the dashboard, not under the club name: the
  left column is the club's identity, and a league list is what the page is
  scoped by, like the season. Renders nothing when a club has filled none in.
- **Only the seasons PlayHQ ran are synced**, so a league a club left before
  that has no other way onto the page, and the settings copy says so.
- Verified against a real Postgres (12 checks: migration 262 applied three times
  to a populated table, an existing club reading NULL, the trim/coerce/backwards-
  span rules through the real settings routes, competitions and former names not
  disturbing each other, the public payload, and clearing storing NULL rather
  than `[]`) and driven in Chromium (15, against the LIVE club payload with
  competitions injected: the card in the reported empty space above the season
  picker, a closed span, an open-ended one, no empty bracket on a yearless one).

### Splitting a player, and the merge bug it uncovered

Reported: "Graeme Cole" holds 1961-64 AND 1988-89 and was never merged. He never
was: **Import Stats resolves a sheet row to a player by NAME**, so a father and
son land on one record and there is no merge to undo.

- **A SEASON is the unit that moves.** Every AFL stat hangs off one, and two
  people's playing years under one name do not overlap. Moves
  `afl_imported_stats`, `afl_player_game_lines` (via their games' season) and
  `player_achievements`, then recomputes `afl_player_season_stats` with the
  sync's own rollup, exactly as a merge does.
- **No undo log, deliberately.** A split leaves two records with the same name,
  which is precisely what Merge Players lists as an exact-name pair, so merging
  them back IS the undo and it is already built.
- **An honour's `season` is free text holding EITHER the season's id (the Awards
  screen) or its name (an import)**, so the split matches both rather than
  assuming one.
- **The new record deliberately gets no `playhq_id`** — that belongs to whoever
  the sync has been matching all along, and handing it over would put the next
  sync's games on the wrong man.
- **Splitting off EVERY season is refused.** That is a rename with extra steps,
  and it would leave the original record empty.
- **The bug this uncovered, and it was live: `_merge_players_core` only ever
  moved the game lines.** `afl_imported_stats` and `player_achievements` are
  raw-SQL tables carrying a bare `player_id` with NO foreign key, so nothing
  moved or cleared them and they were left pointing at a deleted player — where
  every read that joins `players` (career totals, the profile, the leaderboards)
  drops them without a word. **A BetterImport club lost the removed player's
  whole career to a routine duplicate merge.** Both now move with the rest, and
  their ids are recorded on `afl_merge_logs` (two new JSONB columns, mirrored
  idempotently) so the undo hands back exactly those rows. A log written before
  those columns existed reads as `[]`, which is the right answer for it.
- **Verified against a real Postgres** (28 checks through the shipped route
  bodies: the reported career split at the right year, the preview's ordering
  and counts, three guards, an unattributable seasonless imported row staying
  put, another club's row never touched, each honour following its own career,
  the two halves coming back as an exact-name merge pair, and the round trip
  split → merge → undo landing byte-for-byte on the original) and driven in
  Chromium (16).

### Player search in the navbar

`AflPlayerSearch` is BetterCricket's `NavbarPlayerSearch` pointed at the AFL
roster and the club-scoped `/{slug}/players/{id}` route. The roster is fetched
once and filtered locally, same as cricket. Each result carries games and goals,
because a football club has several people with the same name and the numbers
are what tells them apart. **The navbar's breakpoint moved from `md` to `lg`**:
with a search box in the bar there is no room for six links at 768px, and
splitting the two would have left that width with neither.

<!-- END original CLAUDE.md L6644-6759 -->
<!-- BEGIN original CLAUDE.md L8590-8664 -->
## BetterFootball — Import Results (v9.7.0, Aug 2026)

A club's own results register (one row per match, going back as far as the
club's records do) imported as **real games**, not a parallel store. Sibling
of Import Stats (`routers/afl/imports.py`, season totals per player). Built
against a real 3,044-row 1947–2023 register from an AFL club.

- **`routers/afl/result_imports.py`** (`/club-admin/result-imports/*`, cap
  `MANAGE_MANUAL_ENTRIES`) — preview → resolve → commit → undo, plus a
  template. Seasons come from Import Stats' own `/club-admin/imports/seasons`
  endpoints; there is deliberately no second copy of season listing/creation.
- **Rows land in the shared `games` table + `afl_game_details`**, so they show
  on the public results list, the dashboard W/L/D and records exactly like a
  synced game. Three columns on `afl_game_details` carry the distinction:
  `source` ('playhq' | 'import'), `import_batch_id`, plus `import_ref`,
  `is_bye`, `is_forfeit`, `result_note` (what the club actually wrote —
  "Won on Forfiet"). `playhq_id` went **nullable** (an imported game has no
  PlayHQ game behind it). All idempotently ALTERed in `afl_main.py`'s
  lifespan, since `create_all` never retrofits a column.
- **The game id is `uuid5(org, "import-game:" + season|team|date|opponent|round)`**
  — so re-uploading a corrected sheet UPDATES the same rows instead of
  duplicating them. Round is in the key because a re-scheduled fixture carried
  at its original date is otherwise indistinguishable from its twin.
- **The already-synced guard must include the TEAM, not just date+opponent.**
  Found in testing: a club's Seniors and Reserves play the same opposition on
  the same afternoon, so date+opponent alone read the whole day's card as one
  already-synced game and silently dropped every other team's result. Matching
  is (date, opponent, grade name); a game against the same club that day under
  a *different* grade still imports, with a `check` warning naming the other
  grade in case the two are the one match under two labels.
- **Warning kinds mirror the scorecard reader**: `sheet_error` (the sheet's own
  figures disagree — goals×6+behinds ≠ total, a "Won" against level scores, a
  margin that doesn't match) vs `check` (a result worked out from the scores
  because the outcome column was blank, a 0-0 game, a neutral-ground final).
  Nothing is auto-corrected; the import button reads "IMPORT N, KEEP AS
  WRITTEN" when errors remain. A row that genuinely can't import (no date, no
  season) is `blocked` and named, never silently dropped.
- **Outcome vocabulary is matched on substrings**, since a register hand-kept
  since 1947 spells things its own way — the reference sheet writes "Forfiet"
  throughout. Cancelled/unscored rows are always skipped; forfeits import as
  the W/L they were (toggle); byes are opt-in and stored with
  `status='BYE'` + NULL result, which is what keeps them out of BOTH the
  W/L/D tallies and the played count.
- **Blank home/away is neutral, not an error** — 103 rows of the reference
  sheet are finals at a third club's ground. Stored with our club as the
  nominal home side (affects only which column the name prints in) and
  reported once as a summary warning.
- **Column auto-mapping is a GLOBAL best-assignment, not per-field.**
  "HamPoints" and "OppPoints" both score 0.8 against the plain synonym
  "points", so picking each field's own best header independently is a coin
  flip; taking the strongest pair in the whole matrix first resolves both.
  Plus a **content sniff** for a header that says nothing ("Column1" — which
  is exactly how a real club's result column arrives): a column whose VALUES
  are ≥60% a known vocabulary is that field. All 18 columns of the reference
  sheet map with no human input.
- **`frontend/src/afl/pages/admin/importMatching.jsx`** is the extracted shared
  wizard kit (`SearchSelect`, `MatchTable`, `FieldRow`, `StatusBadge`,
  `parseSeasonGuess`, …) now used by BOTH import wizards — `AflAdminImport`
  was refactored onto it rather than a second copy being written.
- **Undo deletes the games** (details/periods/lines/events cascade), scoped to
  `source='import'` so a game the sync has since taken over is never removable
  by undoing the upload that first created it. Because ids are derived, a
  re-upload restamps rows with the new batch — undo removes what that batch
  last wrote, and the older batch's log entry remains.
- **`GET /resolve` caps per-row detail at `ROW_DETAIL_LIMIT` (5000)**; every
  count, and the commit itself, always covers the whole sheet.
- **Verified end to end against a real Postgres** (22 checks): the lifespan's
  new ALTERs, the full 3,044-row sheet, season/grade creation and reuse, the
  one genuine sheet error caught, the synced-game guard, re-import
  idempotency (0 new / 2875 updated), byes on/forfeits off, and undo leaving
  the synced game intact.
- **Not built**: no cricket equivalent (Core already has Upload Scorecard and
  manual games for this), and an imported result carries no player lines —
  it's the match record, not a scorecard.

<!-- END original CLAUDE.md L8590-8664 -->
<!-- BEGIN original CLAUDE.md L9137-9217 -->
## BetterFootball — Import Awards (v9.9.0, Aug 2026)

A club's honour board imported as real `player_achievements` rows. Third
sibling of Import Stats (`routers/afl/imports.py`) and Import Results
(`routers/afl/result_imports.py`), built against a real 7,360-row 1959–2026
awards register from an AFL club.

- **`routers/afl/award_imports.py`** (`/club-admin/award-imports/*`, cap
  `MANAGE_AWARDS`) — preview → resolve → commit → undo, plus a template.
  **No schema change**: it writes the existing `player_achievements` +
  `org_award_definitions` + `achievement_import_batches` tables, so an
  imported award is indistinguishable from one typed into the Awards screen.
- **An award the catalogue doesn't carry is CREATED** (`org_award_definitions`),
  which is what stops a historical trophy existing on player rows and nowhere
  in the club's own award list. A label already there is reused and **keeps its
  own category** — the Award Types screen owns filing, and an upload retyping
  a category the club set up by hand is the wrong way round. Only an award
  being created has its category/subcategory editable on the wizard.
- **`_award_key` collapses case AND "&"/"and"**, which is why 43 raw trophy
  spellings in the reference sheet resolve to 39 awards ("Runner up Best &
  Fairest" / "Runner Up Best & Fairest" are one trophy). A near-miss offers a
  suggestion at ≥0.80 but still DEFAULTS to creating the label — "Best
  Clubman" and "Best Clubperson" are two real trophies at plenty of clubs.
- **Identity is the sheet's own player id where one is mapped**, not the name.
  A register spells one person several ways, and — the dangerous half — holds
  two different people under one name (two Jack Reeds). But **one id does not
  always mean one person either**: nine ids in the reference sheet cover two
  genuinely different names each (an id reused after someone left), so
  `_build_identities` only lets an id unify rows whose names agree once case
  is set aside, and splits it per name otherwise. A NAME covering more than
  one identity is never auto-matched — it comes back `clash` with the roster
  player offered as a candidate for each.
- **A row naming no award is skipped, not invented into a nameless one** —
  6,241 of the reference sheet's 7,360 rows are the club's record of who
  turned out, not honours. Counted and reported, never silently dropped.
- **Re-upload is safe**: a row already on the honour board for that person,
  season and award reads as `exists`. Matched on the player id when there is
  one and on the name ONLY for someone about to be created — checking both
  would read one Jack Reed's honour as already recorded because the other
  has it.
- **`players_unresolved` counts only people who actually won something.** An
  unmatched name with no trophy against it has nothing riding on the decision,
  and counting it sends an admin hunting for a problem that isn't there.
- **Undo removes the awards only.** Players and award types the import created
  are left — a player record is a person, and a catalogue entry may already be
  in use elsewhere. Same call Import Stats makes.
- **`PlayerMatch` was extracted from `AflAdminImport.jsx` into
  `importMatching.jsx`** and is now shared by Import Stats and Import Awards
  (`sheetLine` prop for the per-name context line, `key`-based overrides so an
  id-carrying sheet can hold two people under one name). `SearchSelect` gained
  an `award` kind. New page `AflAdminAwardsImport.jsx` at
  `/admin/import-awards`; the Awards screen's old one-shot CSV uploader was
  replaced by a link to it, so there's one award-import path rather than two.
  `POST /achievements/import` and its template endpoint still exist and are
  unchanged — nothing in the UI calls them now.
- **The honour board on the public player profile** (v9.9.1) — an imported
  award was reaching `player_achievements` and nowhere else, because the AFL
  profile never read them. `GET /afl-players/{id}` now returns `achievements`
  and `frontend/src/afl/components/honours.jsx` renders both surfaces Core
  has: the coloured pills under the player's name and a full Honour board
  section, grouped honour / award / milestone / role on the same `--pb-cat-*`
  tokens and the same `styles/honour-badge.css` cards. Three rules worth
  keeping: **repeated wins of one trophy are ONE entry** carrying every year
  (a nine-time winner is not nine cards; past three years the pill reads
  "N× · first–last"); the **display_name rename is resolved in Python, not a
  join** — a club holding two definitions with the same name would otherwise
  fan one award row into two; and the **name fallback only applies to a row
  with no `player_id` at all**, so one of two same-named players' honours can
  never surface on the other's profile. `afl/components/honours.css` widens
  the shared 160px card to 196px and allows a third title line, scoped under
  `.afl-honours` — football trophy names ("3rd Runner Up Best & Fairest") were
  being clipped mid-name by Core's two-line clamp.
- **Verified end to end** against a real Postgres (28 checks) with the full
  7,360-row sheet, and driven through the real app in a browser: auto-mapping
  all four columns incl. "PayerID", 1,119 awards written, 39 award types
  created, 25 players created, the shared-name split, a re-upload importing 0,
  a sheet with no id column, a sheet naming its own categories, and undo
  leaving the award types intact. The honour board has its own 7 checks (the
  rename, the duplicate-definition fan-out, the name fallback and the
  same-name guard) and was checked in both light and dark themes.

<!-- END original CLAUDE.md L9137-9217 -->
<!-- BEGIN original CLAUDE.md L9925-9974 -->
## Multi-sport: the AFL silo (Aug 2026)

**One codebase, per-sport operational silos.** BetterStats now also serves AFL
(BetterFootball, betterat.football) from THIS repo — separate docker services
(`bs-afl-frontend` / `bs-afl-backend` / `bs-afl-database`), separate database,
same source. Full architecture + product decisions:
**`docs/afl-betterstats-plan.md`**; the PlayHQ AFL API investigation behind it:
**`docs/afl-playhq-data-source.md`**. Key facts:

- **Backend**: `app/afl_main.py` is the AFL entrypoint (`uvicorn
  app.afl_main:app`, env `SPORT=afl` + its own `DATABASE_URL`) — cricket's
  `app/main.py` is untouched and must stay that way. AFL reuses the shared
  models (organisations/users/auth/seasons/grades/games/players/sync_runs) and
  the whole `routers/auth.py` stack; AFL-specific code lives in
  `models/afl.py`, `services/afl/`, `routers/afl/`. The AFL DB is created by
  `create_all` on first boot (cricket tables exist empty there by design).
- **Identity**: every AFL synced row's PK is `uuid5(org, playhq_id)` from day
  one (org itself `uuid5(AFL_NS, org_code)`) — the cricket shared-GUID
  collision saga cannot recur. Raw PlayHQ ids live in
  `grassroots_id`/`playhq_id` columns and are what API calls use. Players key
  on the PlayHQ *profile* id (stable per person), not participant id.
- **PlayHQ AFL API**: two public unauthenticated GraphQL endpoints —
  `api.playhq.com/graphql` (header `tenant: afl`, lowercase) and
  `spectator.playhq.com/graphql` (header `X-PHQ-Tenant: afl`) for
  play-by-play. GraphQL rejects unused variables (a trimmed query that keeps
  a var declaration 400s every call). Old games (pre-~2024) legitimately
  return "not electronically scored" from the spectator API — empty events
  are a normal state.
- **`afl_game_details.synced_at` is the incremental-sync signal** (NULL =
  discovered, stats not yet pulled) — it must never get a server default.
- **Frontend**: one app, sport picked at build time — `VITE_SPORT=afl` mounts
  `src/afl/AflApp.jsx` (App.jsx early-returns it; cricket bundle unchanged).
  AFL pages reuse the shared theme tokens/contexts/components. Dockerfile
  args: `VITE_SPORT=afl` + `VITE_BASE=/afl/` + `NGINX_CONF=nginx.afl.conf` +
  `WEB_ROOT=.../html/afl` (nginx proxies /afl/api to
  `bs-afl-backend` — never the cricket backend).
- **Stats model (pass 1, per product decision)**: games played, goals,
  behinds, Best on Ground (flat count; per-game ranking stored for future
  weighted views), quarter scores + play-by-play per game. No StatLab, no
  Yearbook, no Website module for AFL. Season aggregates are OUR rollup from
  per-game lines (`afl_player_season_stats`, recomputed every sync).
- **Ops**: service definitions to merge into the central compose file:
  `ops/afl/docker-compose.afl.yml`. First admin + club:
  `python -m app.scripts.afl_bootstrap <playhq_org_id> <user> '<pw>' --sync`.
  Test club: Curtin Uni Wesley, PlayHQ org code `d14445c4`.
- **Next passes (agreed direction)**: public self-serve registration wired to
  betterat.football; weekly sync scheduler; BetterSelect AFL (drag-and-drop
  field whiteboard — FF/HF/C/HB/FB + Followers, 12–18 on field, up to 20
  bench); then the other modules, each with an AFL review before enabling.

<!-- END original CLAUDE.md L9925-9974 -->
<!-- BEGIN original CLAUDE.md L9975-10040 -->
## BetterFootball runs the BetterStats admin, BetterAdmin and BetterSocials (v9.94.0 / v9.95.0, Sep 2026)

Asked for in two steps: port BetterSocials and BetterAdmin to the football app
and fill the BetterStats admin gaps, then "port across the remaining BetterStats
Admin gaps and push everything to main".

- **THE CRICKET ROUTERS ARE MOUNTED, NOT COPIED.** BetterAdmin (fees, comms,
  merch, CRM, directory, roster, committee, events, facilities, diary) and
  BetterSocials run on `afl_main.py` as cricket's own routers.
  `services/afl/cricket_schema_mirror.apply` replays cricket's additive raw-SQL
  DDL into the football database so those routers find their tables; football's
  own DDL runs after it. A per-club module switch decides which a club gets.
- **WHERE A SHARED ROUTE WOULD READ CRICKET DATA, A FOOTBALL ONE READS FOOTBALL
  DATA.** BetterSocials pulls fixtures, results, best on ground and team lists
  from `afl_*` tables and scores the football way (12.8 (80), margins in
  points); posts that only mean something for cricket are not offered. BetterFees
  counts a football game from `afl_player_game_lines` (our side only, per
  `afl_game_details.our_side`) because nothing on football writes
  `game_appearances`; the helper keys on that table EXISTING, so cricket's
  recompute is byte-for-byte what it was. The football sync runs the recompute
  after its rollup, the step cricket's scheduler takes.
- **FOOTBALL SERVES THE SAME PATHS CRICKET'S ADMIN CALLS**, which is what lets a
  shared component run on either: `/admin/competitions*`,
  `/club-admin/seasons/merges*`, the settings PATCH. Cricket route bodies are
  reused by importing them lazily inside a football wrapper and calling them with
  explicit keyword dependencies.
- **A FOOTBALL SEASON IS ONE COMPETITION'S SEASON** ("VAFA 2026"), so one year
  can arrive as two rows. Season merges reuse cricket's `season_aliases`, and
  every football filter expands a picked season to its merge group with
  `services/afl/season_groups.season_group`, bound as `= ANY(:season)`. The sync
  no longer overwrites an existing season's name.
- **COMPETITIONS ARE SEEDED FROM THE SEASON NAME, NOT AN ASSOCIATION.** Cricket
  seeds one per CA association; PlayHQ football carries no association but its
  season already names the competition, so `services/afl/competitions` strips the
  year ("VAFA 2026" -> "VAFA"). `CompetitionManager` is now a shared component
  (`components/admin/CompetitionManager.jsx`) both sports mount; football answers
  `/admin/competitions/grouping` with nothing to do. **A picked competition is an
  INCLUSION like a picked grade**: it replaces the grade-type default rather than
  stacking on it, and an id that is not this club's fails closed to nothing.
  `create_all` gives `club_competitions.id` no default, so the football lifespan
  sets `gen_random_uuid()` before running `competition_ddl`.
- **STATS BY GRADE ON FOOTBALL** (`services/afl/grade_scope.py`) sums the per-grade
  season rows it keeps when a category is left out, and only when nothing is
  picked. `stats_left_out` on the club payload names only categories the club
  actually fields, and the public note disappears the moment a grade or
  competition is picked.
- **Player profile fields**: date of birth (admin only, never public), jumper
  number (text, "07" kept), positions (FB..UTIL, public only with
  `public_show_role`) and an action photo. **Settings**: draft mode behind a
  4-digit PIN (the shared `ClubPinGate`, a 423 from `/clubs/{slug}`), typography
  (`settingsKit.jsx`, shared with cricket), primary admin transfer. The trial-ended
  unpause queue was NOT ported; it is a Super Admin sales flow.
- **A FOOTBALL URL IS API-RELATIVE.** Images are stored as `images/...` and drawn
  through `aflApi.mediaUrl`; a cricket `/api/...` URL (a font, a logo from a shared
  helper) must go through `rebaseApiUrl` or it resolves against the cricket API.
- **Verified against a real Postgres** through the real AFL boot path and HTTP
  stack (`backend/verification/verify_afl_*.py`: competitions 37, fee match days 8,
  seasons 21, settings 41, player profile 21, admin extras 28, social 27, shared
  modules 28, manual entries 75), each **with a control run** that reports rather
  than crashes, and **driven in Chromium** against the football production build
  (`frontend/verification/verify_afl_*_browser.mjs`: admin gaps 33, BetterAdmin
  132, socials 23, admin edits 20).
- **NOTICED, NOT BUILT**: the Directory's squad filter reads BetterSelect `teams`,
  which football does not have, so it simply does not draw there. Milestones are
  not scoped by the grade-type default (career facts, as on cricket).

<!-- END original CLAUDE.md L9975-10040 -->
