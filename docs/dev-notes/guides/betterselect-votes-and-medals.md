# Guide: BetterSelect votes, medals, awards night and public voting

**Read this before** (concrete triggers):
- Editing `backend/app/services/votes.py`, `routers/votes.py`, `routers/public_votes.py`, `services/vote_medal_ddl.py`, or the football twins `services/afl/votes.py`, `services/afl/lineups.py`, `routers/afl/votes.py`.
- Touching `vote_medals`, `vote_settings`, `vote_ballots`, `vote_ballot_picks`, `vote_fixture_overrides`, `vote_nudges`, or migrations 193, 194, 196, 267.
- Frontend: `pages/admin/betterselect/AdminVotes.jsx`, `VotesHub.jsx`, `VotesLeaderboard.jsx`, `AwardsNight.jsx`, `pages/PublicVoting.jsx` (`/vote/:token`).
- Symptoms: a fixture shows 0 eligible voters from every source, rounds out of numeric order, a medal that stops counting after the season rolls over, `AmbiguousParameterError` on an optional filter, votes vanishing after a player merge.
- Anything that reads `fixture.id` and treats it as `games.id`.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/betterselect-votes-and-medals.md`. Grep hints: `vote_medals`, `medal_grade_ids`, `AmbiguousParameterError`, `our_side`, `match_ref_id`, `eligibility_source`, `awaiting_team`, `round_sort_key`, `effective_grade_ids`, `?fixture=`, `bulk-state`, `vote_nudges`, `PodiumCard`, `through_round`.

**Related guides**:
- Player merge (`_merge_players_core`, `merge_carry`): ballots and picks must move with a merge.
- BetterFootball / AFL silo: football votes reuse the counting engine.
- Fixtures sync (`routers/fixtures.py::sync_fixtures`, `fixtures_source`): the fixture id scheme.
- Player availability (`public_availability`): same PIN, lockout and cookie pattern as the vote link.
- BetterComms (email only): nudges are emails.
- Shared-game cross-club rule (a fixture is one `games` row for both clubs).

## Standing rules

**Counting and derivation**
1. Everything is derived on read from raw ballots plus the current medal config. There are no stored weekly results or season points, so a mid-season config change restates the whole season. Do not add stored totals.
2. Counting rules live in `services/votes.py` as pure functions (`tally_ballots`, `award_weekly_points`, `clean_ballot_values`, `round_sort_key`, vocabularies). Football imports them; never re-type them. A second copy is how the sports disagree about a countback.
3. `counting_method` 'tally' = season points are the raw sum. 'rank' (the default) = weekly conversion: the top raw vote-getter earns `ballot_values[0]` and so on. Three voters all giving 3-2-1 to the same three players is still 3+2+1 for that game, not 18.
4. Ties: 'share' uses standard competition ranking (both take the higher value, the next value(s) consumed). 'countback' breaks on most of the highest value, then down the ballot; dead heats still share.
5. Season year is Jul to Jun for cricket (`season_year_for`). Rounds group on `fixtures.round` (label, else date). The leaderboard replays "as at" any round through `through_round`.
6. Round order is `round_sort_key(label, date)`: numeric on the label first, sentinel for a non-numeric label (a final sorts after numbered rounds), date second. Never sort round labels as strings ("Round 10" < "Round 7") and never by date alone (several grades share a match date).
7. `movement`, `tied`, `form`, `cumulative`, `round_gain`, `grade`, `grade_short` and `last_round` are computed inside `build_leaderboard` from a rank snapshot after each counted round. No new storage.

**Medals (migration 267)**
8. `vote_medals` is the record. `vote_settings` is history: nothing reads it (see FLAG-VOTES-1). Medal columns keep the old settings column names so `votes.effective_config` reads a medal unchanged. Do not write to `vote_settings`.
9. A ballot belongs to exactly one medal (per direct instruction). A fixture counting towards two medals collects a separate ballot per medal, so a 3-2-1 and a 5-4-3-2-1 medal may disagree about who was best.
10. The two "one live ballot per voter per fixture" partial uniques lead with `medal_id`. `vote_fixture_overrides` is keyed `(medal_id, fixture_id)`: locking a count is a decision about that medal.
11. A medal must not match on stored grade ids. Grades are per-season rows, so next season's "Colts" has a new id and the medal would silently stop counting at rollover. `medal_grade_ids` expands stored ids through their NAMES to every grade of that name in the club. The picker offers each grade name once (`club_grade_options`); each medal reports `grade_names` so a screen can re-tick a selection whose stored id is an older season's.
12. An EMPTY `grade_ids` means EVERY grade. That is what a club's only medal means before anyone thinks about grades, and what the migrated row must mean.
13. A grade-restricted medal's screens drop the fixtures it does not count instead of showing them at zero ballots (zero reads as "nobody voted"). Resolve grades BEFORE narrowing, or a fixture whose grade lives only on its synced game falls out of every restricted medal (`effective_grade_ids` is the fallback).
14. Migration 267 turns an existing club's settings row into its first medal, `link_token` included, so ballots already cast and links already shared keep working. A club with ballots or overrides but no settings row also gets a medal, or the `NOT NULL` `medal_id` has nothing to point at.
15. The DDL lives in one list, `services/vote_medal_ddl.py`, run by both alembic and the lifespan in the same order. Every statement stays idempotent (the lifespan re-runs it every boot). `main.py`'s mirror deliberately does not create the two OLD per-fixture ballot uniques, since 267 drops them.
16. `merge_players` must reassign vote rows (both vote FKs are ON DELETE CASCADE, so a merge would destroy ballots and votes cast for the removed player). De-dup keeps the keeper's ballot/pick, then moves. The ballot de-dup key includes `medal_id`, or a person who voted for both medals on a fixture loses one legitimate ballot. Votes are deliberately not in the merge undo log: an undone merge leaves votes on the kept player.
17. asyncpg cannot type a bare `:param IS NULL`. Any "param IS NULL OR col = param" needs `CAST(:param AS uuid)` (see `routers/votes.py` and `services/votes.py` medal filters).

**Eligibility (who can be voted for or vote)**
18. `fixture.id` is NOT `games.id` for a synced fixture. `sync_fixtures` mints a random uuid4 for `Fixture.id` and stores the real Grassroots match GUID in `Fixture.playhq_id`. Always go through `services.votes.match_ref_id(fixture)` (returns `playhq_id` parsed to a UUID, else `fixture.id` for a manual fixture, which correctly never matches a game). Use it in `eligible_from_source`, `list_vote_fixtures`' `synced` set and `public_votes._open_fixtures`' `synced` set. The Fixture model's docstring claiming `id == game GUID` is wrong. `fixture_lineups` is keyed on the Fixture PK and is self-consistent.
19. Scorecard eligibility (default, per direct instruction, not the saved lineup): a fixture is votable once its game is in `games`. The list is the union of `game_appearances` and batting/bowling/fielding rows, org-scoped through `players.organisation_id` (shared-game cross-club rule). Captain-only mode uses `game_appearances.is_captain`, falling back to the lineup captain when the sync predates the flag.
20. Eligibility source is the club's choice (`vote_settings.eligibility_source`, migration 194, now on the medal): `scorecard` | `lineup` (saved BetterSelect XI) | `playhq` (live Play.Cricket team list via `services/lineups.our_lineup_players`). Per-fixture override on `vote_fixture_overrides.eligibility_source` (its `status` is nullable so a row can carry a source alone); `POST /votes/fixtures/{id}/source` with '' clears to the club default.
21. `votes.resolve_eligibility` falls back to the first other source that has players and reports `requested`/`used`/`fell_back`/`counts`/`unmatched`. `check_all=True` (admin detail only) counts the unused sources and costs one live Play.Cricket fetch.
22. `fixture_vote_state` uses `awaiting_team` (no votable list from ANY source; old name `awaiting_sync`) and takes `ready`, not `has_game`. List views compute `ready` cheaply (`has_game or has_lineup`, or played-and-`playhq`). Never do a live upstream fetch per list row.
23. Manual fixtures and manual games are not votable (deliberate v1): no upstream match to probe.

**Ballot rules and access**
24. Self-vote, played-only and open-window are enforced server-side on the public path. Verified players vote as themselves ('captain' mode restricts to the captain). A typed name is accepted only when `allow_non_participants`; a verified player who did not play also counts as a non-player ballot.
25. `admin_enter_ballot` is deliberately looser than the public page: any named voter, any voting state (paper votes arrive after close), picks still restricted to who played and the self-vote rule. The captain-only default in `BallotEntryForm` is frontend-only, with a "Show all players" fallback. A late ballot on a closed round counts (the leaderboard counts every stored ballot); the UI says so.
26. Capabilities: `MANAGE_VOTES` (settings, links, ballot entry/delete, lock/reopen, per-fixture detail showing who voted for whom, bulk-state, nudge) and `VIEW_VOTE_RESULTS` (leaderboard, presentation). Football shares them. `require_any_cap(*caps)` is in `auth/capabilities.py`. No tallies on any public surface, by decision.
27. Public routes (`/public/votes/*`) are unauthenticated: resolve the club from the medal `link_token`, check entitlement and enabled flag themselves, and 404 without telling. PIN verify uses the availability lockout and rate limits and its own `bs_vote` cookie.
28. One club-wide link takes optional query params instead of a token per fixture or team: `?fixture=<id>` opens that ballot directly (needs its own message when not `open`), `?team=<grade_id>` plus `?round=`/`?q=` scopes the landing list. Filters update the URL with `replace: true`. `updateFilter`/`backToGames` keep team/round and drop `?fixture=`. Admin "Copy link" and "Copy this team's link" reuse `settings.token` and only show when the link is enabled.

**Games hub, nudges, awards night**
29. `GET /votes/fixtures` `grades`/`rounds` option lists and the `summary` counters are built from the WHOLE season regardless of the other filters, so dropdowns and counts never collapse to the current selection. Picking a grade resets the round filter.
30. `voters_expected`/`outstanding_count` are batch SQL over the season (`scorecard_voter_counts`, `lineup_voter_counts`, `player_ballot_counts`). `playhq`-sourced fixtures read 0 in the list; the detail view resolves exactly. `OutstandingVoters` needs its own detail fetch (`outstanding` exists only on the detail payload) and is manage-only.
31. `POST /votes/bulk-state` `{fixture_ids, action: 'open'|'lock'}` applies the single-fixture rules; a fixture that cannot open is reported in `skipped`, not a hard failure.
32. A nudge is a reminder EMAIL (`send_nudge`), because there is no SMS/WhatsApp integration (a deliberate deviation from the design brief). A player with no email reads `channel: 'none'`, `reason: 'no_contact'`. One nudge per player per fixture per 24h, backed by `vote_nudges` (migration 196, mirrored in the lifespan).
33. `ShareVotePanel` uses client-side URL schemes only (no backend send). "Post to socials" copies the message and links to `/admin/social-post`; no standings-card renderer exists.
34. Awards night is a forced-dark stage (re-declare `color`, not only the `--pb-*` tokens, since `color` inherits). The router stamps `club_name`, `club_short` (initials fallback), `season_label`, `grade_name`, `grade_id` on the board; `grade_id` is what makes the reveal replay the same grade the leaderboard was scoped to.
35. Public ballot is one screen: 3 tap targets above the team list, `picks` is still the same fixed-length array. The `RaceChart` is hand-rolled inline SVG; do not pull in a chart library for it.

**Football twin (v9.34.0)**
36. Football ballots key on `games` directly (cricket keys on `fixtures`). There is no eligibility source to choose: one team list, read by `services/afl/lineups.py` from `afl_player_game_lines` (PlayHQ `gameView.statistics.{home,away}.players[]`, both sides). It is a plain read of held data: no upstream call, works when PlayHQ is down.
37. Scope every football team-list read to `afl_game_details.our_side`, or the opposition's named side is listed as ours.
38. A football season is the `seasons` row the game's grade belongs to, not the Jul to Jun window (football runs inside one calendar year).
39. `publish_lineup` is stored so "club never named a side" can be told from "game not synced". Football voting is post-game only (per direct instruction): the sync fetches only FINAL games.
40. No AFL lifespan change was needed: `create_all` makes the ORM tables and `_sync_missing_columns` self-heals `afl_game_details.publish_lineup`.

## Traps and failure signatures
- A played, scorecarded fixture shows 0 for scorecard, BetterSelect XI and Play.Cricket sources: code used `fixture.id` as the match id. Use `match_ref_id` (rule 18).
- Round dropdown reads 13, 15, 12, 14, 11, 7, 10 and no Team/Grade filter appears: `sync_fixtures` never set `Fixture.grade_id` and rounds were string-sorted. Fixed by `round_sort_key`, `effective_grade_ids` and stamping `grade_id` (via `db_grade_id` from `fixtures_source`, our own `grades.id`, not the raw CA guid).
- `AmbiguousParameterError` at execute time on an optional filter: bare `:x IS NULL` (rule 17). Would have been a production 500.
- A medal counts fine, then stops after the new season's grades are created: matching on stored grade ids (rule 11).
- An existing club's count narrows after 267: empty `grade_ids` must mean every grade (rule 12).
- A grade-restricted medal shows fixtures at zero ballots, or a fixture disappears from it: grade resolved after narrowing, or `effective_grade_ids` not used (rule 13).
- Merging two records of one person deletes one of their two ballots: de-dup key lacked `medal_id` (rule 16).
- Football team list names the opposition players: read forgot `our_side` (rule 37).
- A game's points read 18 where 6 is right (three voters all giving 3-2-1): raw tally used where 'rank' conversion is the default (rule 3).
- Grade-filtered awards night replays whole-club standings: `grade_id` missing from the board payload (rule 34).

## How to verify a change here
- Suites named in the archive were run against a real Postgres through the shipped statements and route bodies (cricket 59 checks plus 17 in Chromium; football 47 and 27). The scripts are in `backend/scripts/`, not `backend/verification/`: `verify_vote_medals.py` and `verify_afl_votes.py` (Postgres) and `drive_vote_medals.py` and `drive_afl_votes.py` (browser drivers). Nothing under `frontend/verification` matches votes. Run the matching pair before and after a change here.
- Build harness tables from the ORM models, never by hand. The one exception: the five vote tables in the cricket suite must start in their PRE-267 shape or the migration has nothing to do. Apply 267 three times to a populated pre-267 table and check the old uniques are gone, the new ones hold, link token and settings carry across, and two medals' counts stay apart.
- Checks that found real bugs: the asyncpg cast, the self-vote rule refusing a fixture whose voter picked themselves, rank conversion not being a raw tally. Cover: per-medal overrides and nudge cooldowns, next season's same-named grade still counted, delete guards.
- A control run should fail on: counting against the old single settings row, ballots leaking across medals, and `fixture.id` used as the match id.

## Operator commands and scripts
None. Migrations 193, 194, 196, 267 apply through alembic and the lifespan mirror; no manual step recorded.

## Open follow-ups
- The cricket Games hub filter row overflows at 390px (a `ml-auto` select reaches 446px). Pre-existing.
- Football votes could offer the picked side as an eligibility source; noted in the football select work, not built.
- Manual fixtures and games are not votable.
- No standings-card renderer in BetterSocials for "Post to socials".
- No automated SMS/WhatsApp nudges (email only).

## Flags: conflicting, superseded or possibly obsolete guidance
- [FLAG-VOTES-1] The v8.92 section describes `vote_settings` as an org singleton with the settings, link and QR on a Settings tab | Superseded by migration 267 (`vote_medals`, `vote_settings` unread). `routers/votes.py` now has `/medals` CRUD, `/medals/{id}/regenerate`, and still exposes `/settings` GET/POST (line ~263, ~274), so check whether `/settings` is a compatibility shim before relying on it | BetterSelect — Vote collection (v8.92.0, migration 193, Jul 2026), L13201-13421 | fix the docstring in a code change (documentation-only here, so not done)
- [FLAG-VOTES-2] Archive cites verification suites (59/17 cricket, 47/27 football) | RESOLVED during the split: an agent first reported them missing after searching only `backend/verification` and `frontend/verification`; they exist as `backend/scripts/verify_vote_medals.py`, `verify_afl_votes.py`, `drive_vote_medals.py` and `drive_afl_votes.py`. Their check counts were not re-run | A club runs several medals, L6450-6568 | keep; note that the suites live in `backend/scripts/`
- [FLAG-VOTES-3] The redesign and v8.94 notes describe leaderboard/hub behaviour in terms of `data.settings.token` and "the club link" | With medals each medal has its own `link_token`; a share panel or copy-link should be per medal. Not checked in the frontend | Votes redesign, L13422-13500; v8.94.8 sub-note in L13201-13421 | verify
- [FLAG-VOTES-4] The v8.92 section says `fixture.id == game GUID` is wrong "at launch" and fixed in v8.94.5, yet the Fixture model docstring still says otherwise | Checked: the `Fixture` docstring in `backend/app/models/db.py` (around line 1516) still says `id == the CA/PlayHQ game GUID` for the 'playhq' source, while synced 'grassroots' fixtures mint a random uuid4 and keep the match GUID in `playhq_id`. The docstring is stale for the grassroots source | L13201-13421 (v8.94.5 bullet) | fix the docstring in a code change (this split is documentation-only, so not done here)

## Section coverage
| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| A club runs several medals, in both sports (migration 267, v9.33.0 / v9.34.0, Aug 2026), L6450-6568 | rules extracted | Standing rules 8 to 17, 36 to 40; Traps; How to verify; Open follow-ups |
| - `vote_medals` is the record, and `vote_settings` is history (sub-section) | rules extracted | Rules 8 to 16 |
| - asyncpg cannot type a bare `:param IS NULL` (sub-section) | rules extracted | Rule 17, Traps |
| - BetterFootball got the same engine, and a team-list service (v9.34.0) (sub-section) | rules extracted | Rules 2, 36 to 40 |
| - Verification (sub-section) | rules extracted | How to verify; Open follow-ups; FLAG-VOTES-2 |
| BetterSelect — Vote collection (v8.92.0, migration 193, Jul 2026), L13201-13421 | rules extracted (partly superseded by the medals section, see FLAG-VOTES-1) | Rules 1 to 7, 18 to 28 |
| - Eligibility source is a club choice (v8.94.0, migration 194) | rules extracted | Rules 20 to 22 |
| - `merge_players` reassigns vote rows | rules extracted | Rule 16 |
| - Fixed: `fixture.id` was never the real match GUID (v8.94.5) | rules extracted | Rule 18, Traps, FLAG-VOTES-4 |
| - Fixtures tab filters (v8.94.5) | rules extracted | Rule 29 |
| - Ballot entry respects "Captain only" voting (v8.94.6) | rules extracted | Rule 25 |
| - Fixed: round order + a missing grade filter (v8.94.7) | rules extracted | Rules 6, 13, Traps |
| - Entering ballots on a closed/locked round (v8.94.7) | rules extracted | Rule 25 |
| - Direct fixture/team links + filters on the public voting page (v8.94.8) | rules extracted | Rule 28, FLAG-VOTES-3 |
| Votes redesign — Games hub, podium leaderboard, awards night, one-screen ballot (Jul 2026), L13422-13500 | rules extracted | Rules 7, 26, 29 to 35 |
