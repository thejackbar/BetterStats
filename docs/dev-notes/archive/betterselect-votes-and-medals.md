# Archive: betterselect-votes-and-medals

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: Vote collection, medals, awards night, public voting.
Read the distilled rules first: `docs/dev-notes/guides/betterselect-votes-and-medals.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L6450-6568 -->
## A club runs several medals, in both sports (migration 267, v9.33.0 / v9.34.0, Aug 2026)

`vote_settings` had `organisation_id` as its PRIMARY KEY, so a club held exactly
one ballot shape, one voter mode, one counting method and one public link. A
club running a Club Champion on 3-2-1 alongside a Colts medal on 5-4-3-2-1 had
no way to express it, and its two counts could only be told apart by filtering
the one leaderboard down to a grade after the fact.

### `vote_medals` is the record, and `vote_settings` is history

- **Every settings column moves across UNCHANGED IN NAME**, which is what lets
  `votes.effective_config` read a medal with no edit. Plus `name`, `grade_ids`
  and `position`. `vote_settings` is left in place and **nothing reads it after
  267** — the same call migration 230 made for `club_objectives.plan`.
- **A ballot belongs to ONE medal** (per direct instruction). A fixture counting
  towards two collects a separate ballot for each, so a 3-2-1 medal and a
  5-4-3-2-1 medal can genuinely disagree about who was best. The two "one live
  ballot per voter per fixture" partial uniques are rebuilt with `medal_id` in
  front, and `vote_fixture_overrides` moves from a `fixture_id` primary key to
  `(medal_id, fixture_id)` — locking a count is a decision about that medal, not
  about the fixture in the abstract.
- **GRADES ARE PER-SEASON ROWS, so a medal must not match on stored grade ids.**
  Next season's "Colts" is a different id, and a medal keyed on ids alone would
  silently stop counting the day the new season's grades are created —
  mid-rollover, with nothing to see. `medal_grade_ids` expands the stored ids
  through their NAMES to every grade of that name in the club, which is what
  makes a medal a standing award. The picker therefore offers each grade NAME
  once (`club_grade_options`), not once per season, and each medal reports its
  `grade_names` so a screen can re-tick a selection whose stored id belongs to
  an older season's row. **An EMPTY `grade_ids` means EVERY grade** — that is
  what a club's only medal means before anyone has thought about grades, and it
  is what the migrated row has to mean so an existing count doesn't narrow.
- **A grade-restricted medal's screens drop the fixtures it doesn't count**
  rather than showing them at zero ballots, which reads as "nobody voted"
  instead of "not part of this count". Resolve grades BEFORE narrowing, or a
  fixture carrying its grade only on its synced game falls out of every
  restricted medal (`effective_grade_ids` is the fallback).
- **An existing club keeps everything.** Its settings row becomes its first
  medal, `link_token` included, so ballots already cast still count and the link
  already in players' hands still works. A club with ballots or overrides but no
  settings row (an admin typing paper votes never opened the settings screen)
  gets a medal too, or the `NOT NULL` would have nothing to point those rows at.
- **The DDL lives in ONE list both alembic and the lifespan run**
  (`services/vote_medal_ddl.py`), in the same order, so the two copies cannot
  drift. Every statement stays idempotent because the lifespan re-runs the whole
  list on every boot; the backfills are no-ops once a club has a medal.
- **`merge_players`' ballot de-dup needed the medal in its key.** It matched on
  fixture alone, so merging two records of one person who had voted for both
  medals on a fixture would have deleted one of their two legitimate ballots.
- **`main.py`'s mirror deliberately no longer creates the two OLD per-fixture
  ballot uniques.** 267 drops them a few statements later, and rebuilding a
  unique index over the whole table on every API restart just to drop it again
  is real cost for nothing.

### asyncpg cannot type a bare `:param IS NULL`

Found by the verification, and it would have 500'd in production: an optional
filter written as `(:medal IS NULL OR medal_id = :medal)` raises
`AmbiguousParameterError` at execute time — asyncpg infers a bound parameter's
type from how it is used and that gives it nothing. **Any "param IS NULL OR col
= param" needs an explicit `CAST(:param AS uuid)`.**

### BetterFootball got the same engine, and a team-list service (v9.34.0)

- **The counting rules are IMPORTED from `services/votes.py`, never re-typed.**
  `tally_ballots`, `award_weekly_points`, `clean_ballot_values`,
  `round_sort_key` and the vocabularies are pure functions with no cricket in
  them. A second copy is how the two sports start disagreeing about what a
  countback is. Change a rule there and both sports move.
- **Football's ballots key on `games` directly** — cricket keys on `fixtures`,
  BetterSelect's own scheduling table, which the AFL silo has no equivalent of.
- **There is no eligibility SOURCE to choose.** Cricket picks among the
  scorecard, a saved XI and the published side. Football has one team list, and
  the sync already stores it: PlayHQ's
  `gameView.statistics.{home,away}.players[]` becomes `afl_player_game_lines`,
  both sides, with jumper number and captain flag. So
  `services/afl/lineups.py` is a plain read of held data — no upstream call, no
  cache, and it keeps working when PlayHQ is down. **Scope every team-list read
  to `afl_game_details.our_side`**: the opposition's own named side sits on the
  same game row, so a read that forgets is one that lists them as ours.
- **A season is the `seasons` row the game's grade belongs to**, not cricket's
  Jul→Jun window. Football runs inside one calendar year, so the summer-spanning
  maths would file a whole season under the wrong label.
- **`publish_lineup` was already selected by the gameView query and discarded.**
  Stored now, because it is what separates "this club never named a side" from
  "we haven't synced this game" — both render as an empty list, only one is
  worth chasing.
- **Post-game only, per direct instruction.** The sync only fetches games PlayHQ
  marks FINAL, so a scheduled match reads as not played rather than as a side
  nobody named. Pulling a pre-game side would mean a gameView call per upcoming
  game per sync.
- **No AFL lifespan change was needed**: `create_all` makes the new ORM tables
  and `_sync_missing_columns` self-heals `afl_game_details.publish_lineup`.
- **Capabilities are shared**, so `MANAGE_VOTES` / `VIEW_VOTE_RESULTS` gate the
  football surface with no new vocabulary.

### Verification

Cricket: 59 checks against a real Postgres through the shipped statements and
route bodies (267 applied three times to a populated pre-267 table, the link
token and settings carried across, the old uniques gone and the new ones holding
both ways, the two counts staying apart, per-medal overrides and nudge
cooldowns, next season's grade of the same name still counted, the delete
guards) and 17 driven in Chromium. Football: 47 and 27.

**Both harnesses build their tables from the ORM models**, never by hand — the
one exception being the five vote tables in the cricket suite, which have to
start in their PRE-267 shape for the migration to have anything to do.

Three real findings came from running them rather than reading the code: the
asyncpg cast above, the self-vote rule refusing a fixture whose voter picked
themselves, and rank conversion (the default) not being a raw tally — three
voters all giving 3-2-1 to the same three players is still 3+2+1 for that game,
not 18.

**Noticed, NOT fixed**: the cricket Games hub's filter row overflows at 390px (a
`ml-auto` select reaching 446px). Confirmed pre-existing by re-running the same
check with the change stashed — identical element, identical width.

<!-- END original CLAUDE.md L6450-6568 -->
<!-- BEGIN original CLAUDE.md L13201-13421 -->
## BetterSelect — Vote collection (v8.92.0, migration 193, Jul 2026)

Brownlow-style best-player votes per fixture, its own "Votes" menu item in
BetterSelect. Everything is **derived on read** from raw ballots + the club's
current `vote_settings` (no stored weekly results or season points), so a
mid-season config change restates the whole season — same philosophy as
BetterFees' derived allocation.

- **Migration 193** (+ idempotent `main.py` lifespan mirror): `vote_settings`
  (org singleton: `enabled`/`link_token`/`require_pin`, `voter_mode`
  'players'|'captain', `ballot_values` JSONB default `[3,2,1]` — fully custom,
  best-first, ≤10 positions — `counting_method` 'rank'|'tally', `tie_policy`
  'share'|'countback', `allow_self_vote` default false,
  `allow_non_participants` default false, `auto_close_days` default 7),
  `vote_ballots` (one per voter per fixture — `voter_player_id` for a club
  player OR bare `voter_name` for a non-participant; partial uniques per
  identity space; `source` 'self'|'admin'), `vote_ballot_picks` (ranked
  positions only — values derived from config at count time),
  `vote_fixture_overrides` ('locked'|'reopened' on top of the auto-close
  window).
- **Eligibility = the synced scorecard** (per direct instruction, not the
  saved lineup): a fixture is votable once its game has landed in `games`
  (manual fixtures aren't votable yet), and the votable/voter list is
  `services/votes.eligible_players` — the union of `game_appearances` +
  batting/bowling/fielding rows, **org-scoped through `players.organisation_id`**
  (the shared-game cross-club leak rule). Captain-only mode uses
  `game_appearances.is_captain`, falling back to the lineup's captain when the
  sync predates the flag. **`games.id` is NOT `fixture.id`** for a synced
  fixture — see `services.votes.match_ref_id` below; this was wrong at launch
  and is fixed in the v8.94.5 note further down.
- **Counting** (`services/votes.py`, pure functions, unit-checked offline):
  'tally' = season points are the raw sum (10 voters' 3s = 30). 'rank' =
  weekly conversion — top raw vote-getter earns `ballot_values[0]`, etc.;
  'share' ties use standard competition ranking (both take the higher value,
  next value(s) consumed), 'countback' breaks on most-of-the-highest-value
  then down the ballot, dead heats still share. Season year = Jul→Jun
  (`season_year_for`); rounds group on `fixtures.round` (label else date) and
  the leaderboard can replay standings "as at" any round (`through_round`).
- **Two capabilities**: `MANAGE_VOTES` (settings/link, ballot entry + delete,
  lock/reopen, per-fixture ballot detail — which shows who voted for whom) and
  `VIEW_VOTE_RESULTS` (leaderboard) — the Main Admin hands the latter out per
  user since many clubs keep the count secret (club_admins implicitly hold
  both). New `require_any_cap(*caps)` factory in `auth/capabilities.py`;
  `BetterSelectLayout` NAV gained `anyCaps` support. **No tallies on any
  public surface** — leaderboard is admin-app only, by decision.
- **Routers**: `routers/votes.py` (`/votes/*`, mounted with
  `require_module("select")`) — settings GET/POST/regenerate, fixtures list
  (season-year filter + state + ballot counts), fixture detail, admin ballot
  upsert (paper votes / captain texting in — works after close, any named
  voter, but picks still restricted to who played + the self-vote rule),
  ballot delete (spoof moderation), lock/reopen, leaderboard.
  `routers/public_votes.py` (`/public/votes/*`, unauthenticated — resolves
  club from `vote_settings.link_token`, checks entitlement + enabled itself,
  404-tells-nothing): landing, PIN verify (same lockout/rate limits as
  availability, own `bs_vote` cookie), per-fixture state, ballot submit.
  Verified players vote as themselves ('captain' mode restricts to the
  captain); a typed name is accepted only when `allow_non_participants` — a
  verified player who didn't play also counts as a non-player ballot (stronger
  identity than a typed name). Self-vote + played-only + open-window all
  enforced server-side.
- **Frontend**: `pages/admin/betterselect/AdminVotes.jsx`
  (`/admin/betterselect/votes` — Fixtures / Leaderboard / Settings tabs; the
  settings tab has the link+QR panel and points at the Users page for
  leaderboard access) and `pages/PublicVoting.jsx` (`/vote/:token`,
  standalone/no-navbar like `/avail/`): pick game → verify (or "I didn't
  play" name entry when allowed) → assign positions one at a time ("Who gets
  your 3?") → review → submit; resubmitting updates the same ballot.
- **Eligibility source is a club choice** (v8.94.0, **migration 194**): the
  votable list comes from `vote_settings.eligibility_source` —
  **`scorecard`** (default, who actually played) | **`lineup`** (the saved
  BetterSelect `fixture_lineups` XI) | **`playhq`** (the team list the club
  published on Play.Cricket, live via `services/lineups.our_lineup_players`).
  The last two are ready on match day, so a club can vote on the night instead
  of waiting for the weekly sync. Per-fixture override on
  `vote_fixture_overrides.eligibility_source` (its `status` went nullable so a
  row can carry a source alone); `POST /votes/fixtures/{id}/source` ('' clears
  back to the club default). `votes.resolve_eligibility` picks the requested
  source and **falls back to the first other source that has players**,
  reporting `requested`/`used`/`fell_back`/`counts`/`unmatched` so the admin
  page shows which list is really in play; `check_all=True` (admin detail only)
  also counts the unused sources, which costs one live Play.Cricket fetch.
  `fixture_vote_state`'s old `awaiting_sync` is now **`awaiting_team`** (no
  votable list from ANY source yet) and takes `ready` rather than `has_game`.
  **The list views compute `ready` cheaply** (`has_game or has_lineup`, or
  played-and-`playhq`) — a live per-fixture upstream call per row would be one
  request per fixture, so an unpublished Play.Cricket side is reported when the
  ballot page is actually opened.
- **`merge_players` reassigns vote rows** (`admin.py::_merge_players_core`):
  both vote FKs are ON DELETE CASCADE, so without the reassignment a routine
  merge would silently destroy the removed record's ballots and every vote
  cast for them. De-dups (keep's ballot/pick wins) then moves; deliberately
  NOT in the undo log — an undone merge leaves votes on the kept player
  (same human, no vote lost).
- **Known gap** (deliberate v1): manual fixtures/games aren't votable — the
  votable probe needs a real synced game (see `match_ref_id` below), and a
  manual fixture has no upstream match at all.
- **Fixed: `fixture.id` was never the real match GUID (v8.94.5)** — reported
  live: a played fixture (Darwin CC 2nd XI vs Waratah Warriors B, already
  fully scorecarded on Play.Cricket) showed **0** for all three eligibility
  sources — "Match scorecard", "BetterSelect XI" AND "Play.Cricket team
  list" — even though the match had a live team list AND a completed
  scorecard, confirmed by fetching the Grassroots match directly. Root
  cause: `routers/fixtures.py::sync_fixtures` (the only automated path that
  creates `Fixture` rows) sets `source='grassroots'` and mints a **random
  `uuid4()`** for `Fixture.id`, storing the REAL Grassroots match GUID in
  `Fixture.playhq_id` instead (so two clubs playing each other keep separate
  fixture rows despite sharing one `games.id`) — the Fixture model's own
  docstring ("`id == the CA/PlayHQ game GUID`") describes a scheme that was
  never actually implemented this way. `services/votes.py` took that
  docstring at face value: `game_exists`/`eligible_players` (scorecard
  source) and the live `our_lineup_players` call (Play.Cricket source) both
  cross-referenced bare `fixture.id` against `games.id` / a live Grassroots
  fetch — which never matches, so both sources always read empty for any
  auto-synced fixture, regardless of whether the game was actually synced or
  published. Fixed with `services.votes.match_ref_id(fixture)` — returns
  `fixture.playhq_id` (parsed to a UUID) when set, else `fixture.id` for a
  manual fixture (correctly never matches a real game) — used everywhere
  `eligible_from_source`, `routers/votes.py::list_vote_fixtures`'s `synced`
  set, and `routers/public_votes.py::_open_fixtures`'s `synced` set
  previously used the bare Fixture PK. `fixture_lineups` (BetterSelect XI)
  is untouched — it's keyed on the Fixture's own PK throughout, which is
  self-consistent regardless of `playhq_id`.
- **Fixtures tab filters (v8.94.5)**: with the id bug fixed, clubs running
  several grades hit the next problem — one flat, unfilterable list of every
  played fixture across every team for the season. `GET /votes/fixtures`
  gained `grade_id`/`round_key`/`q` (free-text opponent search); the
  response's `grades`/`rounds` option lists are always built from the WHOLE
  season regardless of the other filters, so the dropdowns never collapse to
  the current selection. `AdminVotes.jsx`'s Fixtures tab grew Team/Grade,
  Round and a search box alongside the existing season-year picker; picking
  a grade resets the round filter, since round options are scoped to it.
- **Ballot entry now respects "Captain only" voting (v8.94.6)**: reported
  live — with "Who votes" set to Captain only, the "Enter a ballot" voter
  dropdown still listed every player who played, not just the captain.
  `admin_enter_ballot` was always deliberately looser than the public page on
  who it lets vote (any named voter, so an admin can transcribe paper votes
  from any source) — nothing server-side actually enforces `voter_mode`
  there, so this is a frontend-only default, not a new backend restriction.
  `BallotEntryForm` now defaults the voter picker to just the fixture's
  captain(s) when `settings.voter_mode === 'captain'` and any are known,
  with a "Show all players" link for the edge case (vice-captain filling in,
  a sync predating the captain flag leaving `eligible[].is_captain` all
  false, in which case it falls back to showing everyone rather than an
  empty list).
- **Fixed: round order + a missing grade filter (v8.94.7)**: reported live —
  the Round dropdown listed rounds out of numeric order ("Round 13, 15, 12,
  14, 11, 7, 10…"), and the Team/Grade filter didn't appear at all. Both
  traced to the same underlying gap: `routers/fixtures.py::sync_fixtures`
  (the only automated path that creates `Fixture` rows) never populated
  `Fixture.grade_id` at all — it only auto-attributes `team_id` (BetterSelect's
  own team concept) — so every auto-synced fixture read `grade_id = NULL`,
  starving the grade dropdown of any options; and several grades' fixtures
  routinely share one match date (ordinary Saturday club cricket), so the old
  date-only round sort left same-date rounds in undefined order, exposing
  that a numeric label ("Round 13") was being tie-broken as a plain string
  ("Round 10" < "Round 7" alphabetically). Fixed three ways:
  1. `services.votes.round_sort_key(label, date)` sorts numerically on the
     label first (falls back to a large sentinel for a non-numeric label like
     a final, so it sorts after every numbered round), date second — used by
     both `list_vote_fixtures`'s round options and `build_leaderboard`'s
     round grouping.
  2. `services.votes.effective_grade_ids(db, fixtures)` resolves a fixture's
     grade from its own `grade_id` when set, else falls back to the synced
     game's `grade_id` (via `match_ref_id` — the game-level sync is a
     separate, correct pipeline that always sets this). Used everywhere
     `list_vote_fixtures`/`build_leaderboard` build grade options, filter by
     grade, or label a fixture's grade — so the filter/leaderboard grade chip
     both work retroactively for already-synced fixtures, no backfill needed.
  3. `sync_fixtures` itself now also stamps `Fixture.grade_id` going forward,
     via a new `db_grade_id` field threaded through
     `services.fixtures_source.org_grassroots_fixtures` (our own `grades.id`
     for the fixture's grade — NOT the raw CA grade guid the function already
     returned under `grade_id`, which can differ on a cross-club collision,
     see the grade-collision note above).
- **Entering ballots on a closed/locked round already worked, made obvious
  (v8.94.7)**: asked live whether a club admin or super admin can catch up on
  end-of-season voting for rounds that auto-closed. Turns out
  `admin_enter_ballot` never had a voting-state gate at all ("works whatever
  the voting state — paper votes often arrive after close", already in its
  own docstring) and `build_leaderboard`/`tally_ballots` count every stored
  ballot regardless of the fixture's current state — so a late-entered ballot
  on a closed round already counted correctly, no code change needed there.
  What was missing was that the UI never SAID so: `FixtureDetail` now shows a
  plain note on a closed/locked fixture that ballots can still be entered
  below without reopening, and that "Reopen voting" is only needed if players
  should be able to self-serve vote via the public link again.
- **Direct fixture/team links + filters on the public voting page (v8.94.8)**:
  per direct request — one club-wide link (`vote_settings.link_token`) was the
  only way in, so every player had to wade through the whole season's games to
  find their own team's, and there was no way to point someone straight at a
  single match. Rather than mint a token per fixture/team (a real proliferation
  for a multi-grade club), the SAME base link now takes optional query params
  that scope it — no new token, no new settings row:
  - `?fixture=<id>` — `PublicVoting.jsx` auto-opens straight into that game's
    ballot once the landing data loads (skips the games list entirely), via
    the existing `GET .../fixtures/{id}` endpoint (unchanged). Reached
    directly rather than via the games list's `disabled={!open}` guard, so a
    link to a not-yet-open or already-closed game needs its own message —
    added a `fixture.fixture.state !== 'open'` check ahead of the existing
    role check, reusing `fixture_vote_state`'s state values.
  - `?team=<grade_id>` (+ `?round=`/`?q=`) — scopes the landing list itself.
    `GET /public/votes/{token}` gained `team`/`round_key`/`q` params, threaded
    into `_open_fixtures`, which now ALSO returns `grades`/`rounds` option
    lists (built from the whole lookback window regardless of the current
    filter, same pattern as the admin Fixtures tab) by reusing
    `services.votes.effective_grade_ids`/`round_sort_key` — no new backend
    logic, just wiring the same v8.94.7 fix into the public path too.
  - The public landing page shows Team/Round selects (+ a search box) when
    there's more than one option, changing a filter updates the URL's query
    params (`replace: true`, so it doesn't spam browser history) — which is
    what makes the "team link" shareable: filter down once, copy the address
    bar. `updateFilter`/`backToGames` centralise all the URL-parameter
    bookkeeping so every "back to games" button in the flow keeps the
    team/round filter but drops `?fixture=`.
  - Admin-side generation: `FixtureDetail` gets a "Copy link" button
    (`?fixture=`) next to Lock/Reopen; the Fixtures tab's grade filter gets
    "Copy this team's link" (`?team=`) once a grade is picked. Both reuse
    `data.settings.token`/`detail.settings.token` (already returned by
    `list_vote_fixtures`/`fixture_detail`) and only show once the link itself
    is enabled.

<!-- END original CLAUDE.md L13201-13421 -->
<!-- BEGIN original CLAUDE.md L13422-13500 -->
## Votes redesign — Games hub, podium leaderboard, awards night, one-screen ballot (Jul 2026)

The three-tab admin screen (Fixtures/Leaderboard/Settings) and the public
stepper ballot were rebuilt from the `docs/design_handoff_betterselect_votes`
handoff. Every existing endpoint/field keeps its shape — this is additive.

- **Games hub** (was "Fixtures", `?tab=hub`, `VotesHub.jsx`): a 4-cell counter
  strip (open now / ballots this round / awaiting team / rounds counted, from
  the new `GET /votes/fixtures` `summary` block), a status segmented control
  (client-side filter, so counts stay stable while flicking) + grade chips +
  round/search/season selects (server-side), a fixture table with a
  `<BallotProgress>` bar per row (`voters_expected`/`outstanding_count`,
  computed batch-per-page — see below), multi-select bulk open/lock
  (`POST /votes/bulk-state`), and one `ShareVotePanel` (WhatsApp/SMS/copy/QR/
  socials, all client-side URL schemes — no backend send) + `OutstandingVoters`
  chase card for whichever open fixture is "in focus".
- **`voters_expected`/`outstanding_count`** (new fixture-list fields): batch
  SQL across the whole season's fixtures (`services/votes.py::
  scorecard_voter_counts`/`lineup_voter_counts`/`player_ballot_counts`) rather
  than one live-eligibility call per row. `'playhq'`-sourced fixtures read 0 in
  the list (a live Play.Cricket fetch per row isn't worth the round trips) —
  same "cheap readiness" trade-off the pre-existing `ready` flag already made;
  the fixture DETAIL view (one fixture, one fetch) resolves it exactly via
  `resolve_eligibility`. `summary`'s counters are computed over the WHOLE
  season regardless of the hub's own grade/round/search filters, matching how
  `grades`/`rounds` options already work.
- **Leaderboard** (`VotesLeaderboard.jsx`): a 1st/2nd/3rd `PodiumCard` row
  (gold/silver/bronze — the one new hex is `#c98b4a` bronze), a standings table
  with rank movement (▲/▼ vs the previous counted round) and a per-player form
  sparkline (last 5 counted rounds), and a `RaceChart` (hand-rolled inline SVG,
  cumulative points for the top 5 — no charting library pulled in for five
  polylines). All of `movement`/`tied`/`form`/`cumulative`/`round_gain`/
  `grade`/`grade_short` are computed inside `build_leaderboard` from a rank
  snapshot taken after every counted round — no new storage, still fully
  derived-on-read like the rest of this feature. `last_round` (the race card's
  "what just happened" block) is the last counted round's own results.
- **Awards night** (`AwardsNight.jsx`, `?tab=leaderboard` → Presentation mode):
  full-screen, forced-dark stage (re-declares `color`, not just the `--pb-*`
  tokens, since `color` inherits), reveals the count one round at a time via
  `through_round` replay (→/Space/←/Esc). `board.club_name`/`club_short`/
  `season_label`/`grade_name`/`grade_id` are stamped onto the leaderboard
  payload by the router (`_club_short` falls back to initials when the club
  has no `short_name`); `grade_id` on the board is what fixes the awards-night
  reveal actually replaying the SAME grade the leaderboard was scoped to
  (without it, a grade-filtered presentation would silently replay whole-club
  standings on every reveal).
- **Public ballot, one screen** (`PublicVoting.jsx`): the old per-position
  stepper is replaced by 3 tap-targets (3/2/1) above the team list — tap a
  name to fill the next empty slot, tap a filled slot/chosen name to clear it,
  Submit once full. No API change; `picks` is still the same fixed-length
  array submitted as-is.
- **`POST /votes/bulk-state`** — `{fixture_ids, action: 'open'|'lock'}`, same
  per-fixture rules as the existing single lock/reopen endpoints; a fixture
  that can't open (no team list) is reported in `skipped`, not a hard failure.
- **`POST /votes/nudge`** — `{fixture_id, player_ids}` or `{fixture_ids}` (every
  outstanding voter across several fixtures). **Deviates from the design
  brief on purpose**: the brief assumed automated SMS/WhatsApp reminders, but
  this codebase has no SMS/WhatsApp sending integration at all (BetterComms is
  email-only, `services/email_service.py`) — so a nudge is a reminder EMAIL to
  the player's stored address (`services/votes.py::send_nudge`), and a player
  with no email simply reads `channel: 'none'` and can't be nudged this way
  (`reason: 'no_contact'`). Rate-limited to one nudge per player per fixture
  per 24h via the new **`vote_nudges`** table (migration 196, mirrored in
  `main.py`'s lifespan) — the send log both backs the cooldown and makes the
  count auditable, same posture as the BetterComms usage policy.
- **`OutstandingVoters` on the hub tab** needed its own fixture-detail fetch
  (`fixture.outstanding` only exists on `GET /votes/fixtures/{id}`, not the
  list) — `VotesHub` fetches it for whichever open fixture is "in focus" and
  merges it in, rather than the list row's bare `outstanding_count`. Manage-
  only (nudging is a `MANAGE_VOTES` action; a `VIEW_VOTE_RESULTS`-only user
  never triggers the extra fetch).
- **"Post to socials"** (phase 2 in the brief — no standings-card renderer
  exists yet in BetterSocials): `ShareVotePanel` copies the message and
  deep-links to the plain `/admin/social-post` composer instead of doing
  nothing.
- Capabilities unchanged: `MANAGE_VOTES` gates the hub's write actions/bulk/
  nudge/fixture detail/settings; `VIEW_VOTE_RESULTS` gates the leaderboard and
  presentation mode. No tallies anywhere on the public page.

<!-- END original CLAUDE.md L13422-13500 -->
