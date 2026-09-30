# Guide: Data sources and sync (Cricket Australia, PlayHQ, Play-Cricket)

**Read this before**:
- Touching `backend/app/services/sync.py`, `auto_sync.py`, `sync_drift.py`, `grassroots_scores_client.py`, `playhq_client.py` or `jobs/scheduler.py::sync_all_organisations`.
- Changing what "Sync Now", "Fix Missing Totals" or "Full Rebuild" does on `/admin/sync`, or the `sync_runs` kinds.
- Anything that parses a Grassroots `/scores/*` payload (scorecards, `matchSummary`, `matchType`, `isHome`, dismissal text, keeper catches).
- A missing, doubled or wrong-format game, or a match that returns HTTP 204 from the scores API.
- Pasting or resolving a PlayHQ `game-centre/<short code>` link (BetterPosts import).
- Planning UK / Play-Cricket support, or any new upstream feed.
- `games.match_format`, `fees.derive_fee_format`, `merge_logs` redirect maps in a sync.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/data-sources-and-sync.md`. Grep hints: `match_format never written`, `scheduled sync pulls the period`, `game-centre link`, `swallowed query error`, `keep_player_id`, `Data Source Topology`, `UK Expansion`, `Sync Architecture`, `owns_run`, `caught-behind`, `Partner API`, `May 2026 Audit`, `Historical Data Fix`, `org_recent`, `match_pull_failed`.

**Related guides**: fees (match-day charges read `match_format`, `recompute_fee_match_days`); stats aggregation and filters (`v_effective_*` views, grade/season collision schemes); imports and manual entries (BetterImport reconcile runs at the tail of a sync); social posts (BetterPosts scorecard import); BetterIQ (opposition dossiers read the same `/scores/*` cards).

## Standing rules

**Sources and identity**
1. Club cricket data comes from Cricket Australia's Grassroots proxy `grassrootsapiproxy.cricket.com.au`. Use only the `/scores/*` and `/fixturesladders/grades/{id}...` paths. The restricted paths (`/fixturesladders/games/{id}`, `/participants/games/{id}/batting`, `/scorecards/...`) return 403 "API key does not have access". Do not try them.
2. Match discovery is `/scores/grades/{grade_id}/matches` (works for every season back to 1975, and needs no fixturesladders call). Scorecards are `/scores/matches/{id}?responseModifier=includeScorecard`. HTTP 204 means the match is in the PlayHQ namespace and Grassroots does not hold it.
3. `jsconfig=eccn:true` is a ServiceStack camelCase flag, not an API key. Without it a bare curl returns PascalCase and `data.get("matches")` reads empty.
4. `apiv2.cricket.com.au` is the international stats API (Ashes, BBL). It holds no club cricket. Skip it.
5. A PlayHQ `game-centre/<8 hex>` short code is a different id namespace from the Grassroots GUID. Nothing derives one from the other (checked on a real match). Do not try to convert one. This contradicts `docs/afl-playhq-data-source.md` ("the short code IS the real gameID"); that holds for the AFL tenant only.
6. Do not build a club-facing button on PlayHQ's public `discoverGame` GraphQL. It sits behind a CloudFront WAF that 403s after about three requests. `discoverGradeFixture`/`discoverTeamFixture` 500 on cricket ("Bolt adapter map not found") and introspection is blocked.
7. So a PlayHQ link resolves locally: `services/social_match_lookup.py` + `GET /admin/social/match-lookup`. A full UUID resolves straight through. A PlayHQ link returns the club's own recent completed matches to pick from, narrowed by slugifying the grade in the URL against our grade names (sponsor suffix tolerated by an either-side-prefix fallback). Lookback is 240 days (`_LOOKBACK_DAYS`), not the roundup's 90. Candidates come from `_current_grade_rows` + `gr.get_grade_results`, the Results roundup machinery. Do not write a second "which matches are ours".
8. Pagination: never trust PlayHQ `links.next` alone (it can return forever, seen past page 1100). Loops cap and stop on the first short batch (the cap is `max_pages=200` in `club_directory.discover_clubs`).
9. `upsert_organisation` keys on whatever id it is given. A PlayHQ UUID after a Grassroots GUID would create a duplicate org. `find_matching_organisation` layers the check: primary id, then `playhq_id`, then case-insensitive name. `include_archived=False` is for the self-serve "already registered" checks only.
10. `players.id`, `grades.id` and `seasons.id` are per-club (uuid5 on collision) and the raw CA guid lives in `grassroots_id`. Use `_resolve_org_grade` / `_resolve_org_player` in sync, never a global `session.get(Grade|Player, raw_guid)`. API calls must use the raw guid.

**Parsing the scores payload**
11. `isHome` lives on `matchSummary.teams`, not the top-level `teams` array. The wrong field fails silently and leaves `home_team` empty.
12. On a `/scores/*` match, `result`/`venue`/`date` are NOT on `matchSummary` (it carries only `resultText` + `teams`). They are top-level: `raw.venue`, `raw.matchSchedule[0].startDateTime`, `matchSummary.resultText`. Format is `matchType` (never hardcode T20). Round label gets a "ROUND " prefix only when the name has no letters. Overs is the longest innings bowled.
13. "Absent" / "Did Not Bat" dismissals (they carry `dismissalTypeId > 0` but no ball faced) are not innings. Filter them from batting inserts and from `_derive_partnerships_grassroots`, or per-game counts overshoot CA's aggregate by 1 or 2.
14. CA does NOT mark the keeper in `dismissalText` (plain `"c: C Cecchi b: A Ricci"`, no dagger, verified on 6597 catches). Caught-behind is structural: a catch is caught-behind iff the catcher is the fielder whose row has `wicketKeeperCatches > 0` (or a stumping). Use `_innings_keeper_names(inn["fielding"])` + `_caught_by_keeper(dismissalText, keeper_names)`.
15. `batting_innings.caught_behind` and `bowler_wickets.caught_behind` are nullable bools (migrations 075, 076). NULL means unknown and every reader treats it as a plain catch. Keep the flag off the `dismissal_type` string so the many "count caught" readers stay untouched.
16. Every call site builds `keeper_names` from the same innings' `fielding` rows: the sync batting insert, `_extract_bowler_wickets`, `backfill_caught_behind`, `iq_opponent` (live dossier) and `games.py` (scorecard opposition rows). A new consumer must do the same.
17. Catches vs keeper catches are fully held: `fielding_stats.catches`/`catches_wk` per game, `player_season_stats.catches`/`catches_wk`/`catches_non_wk` per season. Outfield = `catches - catches_wk`. `player_season_grade_stats` holds combined catches only (cannot back a grade-filtered keeper split). Milestones, rankings and composite MVP measures stay combined by design.

**`match_format`**
18. Format is per FIXTURE and a grade cannot answer it (one grade plays 32 one-day and 26 two-day fixtures in a season). The grade-level `fee_format` override is only for telling a women's grade from a men's one and for excluding a grade from fees. Never set a mixed grade to `two_day`.
19. `games.match_format` is written from the grade match LIST (`get_grade_matches` returns `matchType`: "One Day" / "Two Day" / "T20"), so it costs no extra call and covers fixtures whose card is never opened. Store the string (consumers substring-parse it: `fees.derive_fee_format`, `iq_team._fmt_of`, and the manual-entry form writes free text).
20. Never store "BYE" (it appears as a `matchType`). It is not a format, every consumer would read it as a one-dayer, and a bye has no scorecard so no `games` row.
21. Setting `match_format` on `Game()` alone fixes almost nothing: an already-synced game never reaches the per-game block (appearances-done gate). The write is ALSO a bulk `UPDATE ... WHERE match_format IS DISTINCT FROM` beside the `is_final` one. Any per-fixture field from the match list needs that same bulk pass.
22. Do not edit fee rows directly. `recompute_fee_match_days` re-derives them and leaves admin-overridden (`auto_derived=False`) and already-paid rows alone.
23. A migration's docstring is intent, not proof. Migration 033 claimed the sync backfilled `match_format`; no such code existed. Grep for the writer.

**Scheduled sync (`services/auto_sync.py` decides who and how far back)**
24. The scheduled job runs in Perth time, Sunday AND Monday 01:00 (`sun`/`mon`, ids `weekly_sync` and `monday_results_sync`), not UTC. The same job both days, since each run asks "what happened since this club's last sync".
25. Eligibility reuses `auth.modules.org_core_live` (cancelled or paused Core, expired Core trial, org master switch). It fails OPEN for clubs whose subscription rows predate the per-module scheme, so no long-established club is dropped by accident. Also `archived_at IS NULL` and `is_active`. Skips are counted and logged by reason.
26. The watermark is the last run that PULLED MATCHES, of kinds `org_recent` / `org_full` / `org_hard_refresh` (a manual Sync Now counts). An errored, cancelled or restart-interrupted run does not, so the next run re-covers the gap. `OVERLAP_HOURS = 26` is subtracted (catches late-typed results, and Monday re-covers Sunday). No watermark: `DEFAULT_LOOKBACK_DAYS = 7`. Behind by more than `MAX_LOOKBACK_DAYS = 90` escalates to a full run.
27. "Successful run" is not "pulled matches". `sync.py` swallows a game-level pass failure to keep the season aggregates, so it stamps `match_pull_failed` on the run stats and `auto_sync.last_sync_at` ignores such a run (`_pulled_matches_ok`). `ever_full` deliberately does NOT apply that filter (it means "seasons and grades were seeded"), or a club whose game pass keeps failing would get a full sync twice a week for ever.
28. `plan_run` never escalates to a full run twice: if a full run already completed since the watermark and the club is still behind it returns `full_sync_did_not_catch_up` and stays incremental at the cap.
29. `kind = 'org_recent'` is deliberately not one of the full kinds. `org_full`/`org_hard_refresh` mean "whole history pulled" and the Setup Wizard gate (`onboarding_wizard._sync_ready`), `wizard_analytics` and `club_admin._FULL_SYNC_KINDS` read them as ready. `main.py`'s restart self-heal resumes only the two full kinds (a dropped incremental needs no resume, its watermark never moved). The same reasoning applies to any new run kind: keep it out of `_FULL_SYNC_KINDS`.
30. Incremental mode is the SAME code path with smaller inputs: `since` filters the season list via `auto_sync.season_in_window` (`SEASON_SPAN_DAYS = 400`, so a straddling season or late final is not filtered out) and `sync_grassroots_game_level_data(since=, season_ids=)` restricts the grade fan-out and drops out-of-window fixtures. The grade fan-out (a `/scores/grades/{id}/matches` call per grade per run) is as much of the saving as the scorecards.
31. On an incremental run that added no games, skip the whole-club tail passes (`_backfill_missing_season_stats`, `reconcile_imported_totals`, the bare `ANALYZE`). Milestones are scoped to the players whose aggregates were rewritten, not skipped.
32. `auto_sync.fixtures_in_window` asks "did the club play anything since its last pull" first, and its grade lists are cached in-process so the sync reuses them. This is deliberately NOT an "is the season over" model. Every branch that returns "sync anyway" is load-bearing: a CA season we do not hold or hold with no grades, and every grade returning `[]` (`get_grade_matches` returns `[]` for a transient failure and for an empty grade alike). Future-dated fixtures do not count.
33. An idle check still records a successful `org_recent` run so the watermark moves. Without it the window grows until it crosses 90 days and hands the club a quarterly full rebuild for doing nothing.
34. Historical drift is DETECTED, not re-pulled (per direct instruction, no periodic full sync). `services/sync_drift.py` (monthly job `check_all_organisations_drift`) compares CA season aggregates with stored `player_season_stats`, per player and only for participants CA reports. It ignores `_backfill_missing_season_stats` rows and any participant in a live merge. CA returning nothing is `unavailable`, never drift. Acknowledging survives a re-check that still finds drift and clears when a season is clean. It never writes stats.

**Sync internals**
35. Two passes per full sync: the Grassroots aggregate pass (`playhq_client.get_*_stats`, source of `player_season_stats`) then the scores pass (`sync_grassroots_game_level_data`). Per-game session pattern avoids async session deadlock.
36. `sync_runs`: `update_sync_run` and `finish_sync_run` MERGE stats into the existing row. Stale `running` rows are marked `error` at startup. `owns_run = run_id is None` inside `sync_organisation`: when the caller passes `run_id`, the CALLER must call `finish_sync_run` (the hard-refresh handler does, on its true-success branch).
37. Merge maps (`merge_logs`, columns `removed_player_id` / `keep_player_id`, NOT `kept_`): filter `undone_at IS NULL` and resolve transitively with a cycle break, in both the aggregate pass and the game pass. A stale or single-hop map silently drops seasons or per-game stats for the kept player. The game pass checks `known_player_ids` first then falls back to `merged_away` at all five `participantId` consumers (batting, bowling, fielding, fall of wickets, derived partnerships).
38. An `except` that hides a database error must roll back AND hand back objects the rest of the request can read. A bare `db.rollback()` expires every loaded instance (even with `expire_on_commit=False`), and the next attribute read is a lazy refresh: `greenlet_spawn has not been called`. Use `_rollback_keeping(db, *instances)` (`routers/admin.py`): roll back, then `await db.refresh(...)` what the caller still holds.

**Play-Cricket / UK (design only)**
39. Do not scrape Play-Cricket HTML (server-rendered Rails, no client JSON, terms breach). The tap is the official API v2 (`play-cricket.com/api/v2/*.json`), token-gated per club. Full detail: `docs/uk-play-cricket-data-source.md`.
40. There are NO statistics endpoints. The UK has scorecards only, so every season aggregate must be computed by us (promote the "Fix Missing Totals" rollup to primary). `match_detail` maps almost 1:1 onto our per-game tables and adds toss and full extras (both absent from CA `/scores/*`).
41. Ids are integers: raw id in `grassroots_id`, `id = uuid5(org, raw_id)` on collision. Season is a query param, so derive `Season.year` from `match_date` (DD/MM/YYYY).
42. A token authenticates us; `site_id`/`match_id`/`division_id` picks whose data. You are data controller for your own club only. In-scope cross-club data is the opponent half of your own games. A full opponent dossier needs the opponent's token, a league-site token or partner access. Onboarding a league is the highest-leverage unit.
43. REJECTED: one shared club key for every English club (breaches the host club's agreement, single point of failure, UK-GDPR-unlawful for members incl. children). Use league or partner tokens.
44. Strategy per ECB advice: Phase 1 BYO per-club token (`playcricket_api_token` + `playcricket_site_id` on the org, a token-authed `playcricket_scores_client`), Phase 2 partner access. Low traffic, minimise retained PII (we would be a processor).

## Traps and failure signatures

- Every match day charged as one day, "Fee Format = One Day" on two-day grades: `games.match_format` was NULL (no writer). Fixed by rules 18 to 21. A club onboarded after the fix needs no backfill.
- Pasting a PlayHQ game-centre link gives "Paste a match URL or a match ID": handlers matched full UUIDs only. Rule 7.
- Imported social post shows blank date, blank ground and bare "RESULT", or "ROUND Round 7", or a 50-over final labelled T20: reading from `matchSummary` and hardcoding format. Rule 12.
- `Scorecard parse error: greenlet_spawn has not been called` on every scorecard fetch for every club: the merge-redirect query used the column `kept_player_id` (real name `keep_player_id`), `UndefinedColumnError` was swallowed, then a bare rollback expired `club`. Fix the column, and use `_rollback_keeping`. A merged-away player also stopped resolving quietly.
- Blank `home_team`/`away_team` on every game: `isHome` read from the wrong array. Rule 11.
- Duplicate batting rows (one player ~280 rows vs ~200): the Partner and Grassroots sync both ran and the same physical match has different UUIDs in each. Never run two game-level sources.
- A player shows only 3 seasons in `player_season_stats` while per-game rows are right: a stale/undone or single-hop `merge_logs` entry redirected aggregate stats to a player that no longer exists. Rule 37. One-off cleanup: `UPDATE merge_logs SET undone_at = NOW() WHERE undone_at IS NULL AND removed_player_id IN (SELECT id FROM players)`. Per-game counts over CA's aggregate by 1 or 2: "Absent"/"DNB" rows (rule 13). One-off cleanup: `DELETE FROM batting_innings WHERE dismissal_type IN ('absent','did not bat','dnb')`.
- Successful Full Rebuild sat at `running` for ever: caller never called `finish_sync_run` (rule 36).
- A club quietly stops receiving results after one failed scorecard pull: the run counted as success and the watermark stepped over it. Rule 27.
- A club that plays nothing gets a full rebuild every quarter: idle runs must still record a run (rule 33).
- Club stops syncing the day its new season opens: "nothing played" decided from grades we have not created yet. Keep the "sync anyway" branches (rule 32).
- Sync landed at 11:00 Sunday WA time: the old job ran 03:00 UTC. Rule 24.
- `Player.display_name`-style ORM properties in a `select()` raise `Column expression ... got <property object>`. Select the mapped columns and compute in Python.

## How to verify a change here

- Real-Postgres suites named in the archive (in `backend/verification/`): the auto-sync suite (migration 258 applied three times plus lifespan mirror, every eligibility branch incl. fail-open legacy club, watermark ignoring errored and `match_pull_failed` runs, anti-escalation, season/fixture filtering asserted inside the real `sync_grassroots_game_level_data` with stubbed CA responses, every empty-period branch, drift false-positive guards). Confirm the exact file names by grepping `backend/verification` for `auto_sync` and `sync_drift` (not checked here).
- For scorecard or social import changes, run the SHIPPED function body over a real Grassroots payload for a known match (extract it from the router, retype nothing) and add a control run that reproduces the reported failure.
- Live-CA checks are the only way to know an upstream shape (`match_format` was verified against six real grades). Reproduce through `grassroots_scores_client` (or pass `jsconfig=eccn:true`), not a bare curl.
- A harness that only replays row-building logic in plain Python will not catch a SQLAlchemy query-construction bug or a bad column name. Execute the real query.
- Diagnostic order that worked for a "my fix has no effect" report: confirm the deployed code (`docker compose exec ... grep` a distinctive string), then read `docker compose logs <service> --since Nm` for the real traceback before rereading source.
- Scores API cache: `_SCORECARD_TTL = 900`, `_MATCH_TTL = 300`, `_LADDER_TTL = 3600`, `force=True` bypasses. A half-saved upstream snapshot must not be cached.

## Operator commands and scripts

- `python -m app.scripts.backfill_match_format <org-id-or-slug>`: dry run by default. Flags `--apply`, `--recompute` (re-derive fee match days), `--season YYYY`, `--all-seasons`. Default scope is the seasons carrying `fee_member_seasons` rows plus the club's latest season (do not reach back further for fees). Writes only games under the club's OWN grades (a grade match list is competition-wide).
- `python -m app.scripts.backfill_caught_behind <org_id|all>`: re-reads scorecards and sets `batting_innings.caught_behind` in place (network cost of a Full Rebuild).
- `python -m app.scripts.rebuild_bowler_wickets <org_id|all>`: re-derives `bowler_wickets` including the caught-behind flag.
- `python -m app.scripts.list_skipped_matches`: lists matches the scores API 204'd for a club or grade (no fallback exists, see Flags).
- `python -m app.scripts.reconcile_imports <org>`: rebuilds imported deltas (tail of sync).
- Admin buttons on `/admin/sync`: Sync Now = `POST /organisations/{id}/sync`; Fix Missing Totals = `POST /club-admin/backfill-aggregates` (recomputes `player_season_stats` from per-game rows, no CA fetch); Full Rebuild = `POST /club-admin/hard-refresh` (wipes per-game tables and re-pulls, an hour or more). Renamed Apr to May 2026 from "Sync" / "Backfill Aggregates" / "Hard Refresh"; internal names and `sync_runs.kind` unchanged.
- Deploy runs the committed script; nothing sync-specific needs a manual step for the scheduler (the old UTC `weekly_sync` job is replaced by id).

## Open follow-ups

- Post-migration PlayHQ-namespace matches that return 204 stay missing across every sync and Full Rebuild (no fallback since the Partner path was removed).
- Play-Cricket Phase 1 (per-club token client) and Phase 2 (partner access) are not built.
- `/fixturesladders/grades/{id}/ladders` was "not yet synced" per the archive (ladder is fetched live and cached; verify before relying on either statement).

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-SYNC-1] "`playhq_partner_client.py` is still used by the games router, records router and organisations router" and "Live scorecard view for Partner-only games: PlayHQ Partner API via games router" | No `playhq_partner_client` file exists in `backend/app/services` and nothing imports it (grep). `routers/games.py` has no Partner call. | PlayHQ Partner API — May 2026 Audit (L12780-12799) | retire that bullet; the live-view fallback is gone.
- [FLAG-SYNC-2] "`suggest_phq_ids()` powers the PHQ ID Match admin page `/admin/phq-match`" | `suggest_phq_ids` is not in `sync.py` or anywhere in `backend/app`; no phq-match route found. | PlayHQ Partner API — May 2026 Audit (L12780-12799) | retire.
- [FLAG-SYNC-3] "`deep_sync_player()` calls the PlayHQ Partner API, only ~3 seasons" | Code now delegates to `sync_organisation(kind="player_deep")` (Partner path retired, docstring says so). Still routed from `club_admin.py`. | Sync Architecture (L12745-12779); Partner Audit (L12780-12799) | keep as "delegates to the org Grassroots sync".
- [FLAG-SYNC-4] "The 204 gap is minimal, the Partner sync was not needed" | A later code comment in `sync.py` (~L1806) says a 204'd match has NO fallback and stays missing on every sync including Full Rebuild, and `list_skipped_matches` exists for it. The two views disagree on how much it matters. | PlayHQ Partner API — May 2026 Audit (L12780-12799); Sync Architecture | verify per club with `list_skipped_matches`; treat as a known gap, not "minimal".
- [FLAG-SYNC-5] "`participantId` is the same GUID as `players.id`" and "`grade_id` is the same UUID as `grades.id`" | True only for legacy single-club rows. Per-club ids are uuid5 on collision, raw guid in `grassroots_id` (`_resolve_org_player`, `_resolve_org_grade` exist; game pass uses `pid_by_guid`). The archive's Sync Architecture line "uses `session.get(Grade, ...)`" predates this. | Data Source Topology (L12708-12733); Sync Architecture (L12745-12779) | keep with rule 10 as the correction.
- [FLAG-SYNC-6] "Full sync ... scheduled weekly" and "the weekly job" | Now Sun and Mon 01:00 Perth, incremental `org_recent` by default (job `sync_all_organisations`, `hour=1` in `PERTH`). | Sync Architecture (L12745-12779) vs scheduled-sync section (L7293-7402) | keep the newer section; treat "weekly" as history.
- [FLAG-SYNC-7] The "Sync Architecture" "two passes" list says Grassroots scores "no longer depends on fixturesladders" while the scheduled-sync section and `auto_sync.fixtures_in_window` also call fixturesladders-adjacent season/grade data | not a conflict in code found, but the season list and grades come from the aggregate pass first | Sync Architecture vs scheduled-sync | verify if changing discovery.
- [FLAG-SYNC-8] Migration 258 and "resumes only the two full kinds" in `main.py` | Not re-checked here; `_FULL_SYNC_KINDS` in `club_admin.py` and `_FULL_KINDS` in `auto_sync.py` both confirmed as (`org_full`, `org_hard_refresh`). | scheduled sync (L7293-7402) | verify `main.py` self-heal before adding a kind.
- [FLAG-SYNC-9] UK section describes a `playcricket_scores_client` and org columns as the plan | none exist in code (grep of `backend/app`). `docs/uk-play-cricket-data-source.md` exists. | UK Expansion (L12734-12744) | keep as design only.
- [FLAG-SYNC-10] "Guarded since commit ceadd84" (org duplication) | Commit not checked. `find_matching_organisation` with the layered check exists in `sync.py`. | Data Source Topology (L12708-12733) | keep.
- [FLAG-SYNC-11] Applecross measurements (3957 games, 41423 batting rows, ~52 seasons, "Jack Barendse 200/168/93") and Partner key "~3 seasons" | one-off May 2026 evidence, will have drifted. | May 2026 Historical Data Fix (L12820-12838); Data Source Topology | do not treat as current figures.
- [FLAG-SYNC-12] The scheduled-sync section cites `docs/afl-playhq-data-source.md` contradiction only for short codes; also `routers/afl/social.py` has its own `/admin/social/match-lookup`, so the resolver is duplicated per sport. | AFL route confirmed at `routers/afl/social.py:236`. | game-centre link (L8075-8164) | verify which sport a change targets.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| `games.match_format` was never written, so every match was a one-dayer (L7213-7271) | rules extracted | Standing rules 18 to 23, Traps bullet 1, Operator commands (backfill_match_format) |
| The scheduled sync pulls the period's results, not the club's whole history (L7293-7402) | rules extracted | Standing rules 24 to 34, Traps bullets 8 to 10, Flags SYNC-6, SYNC-8 |
| A PlayHQ game-centre link is a different id namespace (L8075-8164) | rules extracted | Standing rules 5 to 7, 12, Traps bullets 2 and 3, Flag SYNC-12 |
| &nbsp;&nbsp;&nbsp;### A swallowed query error, reported as a greenlet crash (v9.53.5.1) | rules extracted | Standing rule 38, Traps bullet 4 |
| Data Source Topology (May 2026 investigation) (L12708-12733) | rules extracted | Standing rules 1 to 4, 8, 9, 10, Flags SYNC-5, SYNC-10, SYNC-11 |
| UK Expansion, Play-Cricket Data Source (Jun 2026 investigation) (L12734-12744) | rules extracted | Standing rules 39 to 44, Open follow-ups, Flag SYNC-9 |
| Sync Architecture (L12745-12779) | rules extracted | Standing rules 11, 13 to 17, 35 to 37, Operator commands (buttons, scripts), Traps bullets 5 to 7, Flags SYNC-3, SYNC-5, SYNC-6, SYNC-7 |
| &nbsp;&nbsp;&nbsp;### Admin UI button names (Sync Actions card) | rules extracted | Operator commands (admin buttons) |
| PlayHQ Partner API, May 2026 Audit (L12780-12799) | superseded by Sync Architecture and later code (Partner path fully gone) | Standing rule 35, Flags SYNC-1 to SYNC-4, Open follow-ups |
| May 2026 Historical Data Fix, Resolution Log (L12820-12838) | rules extracted (fixes 1 to 3 as rules) | Standing rules 11, 36; Traps bullets 5 to 7; Flag SYNC-11 |
