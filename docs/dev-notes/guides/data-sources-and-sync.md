# Guide: Data sources and sync (Cricket Australia, PlayHQ, Play-Cricket)

**Read this before**:
- Touching `backend/app/services/sync.py`, `auto_sync.py`, `sync_drift.py`, `grassroots_scores_client.py`, `playhq_client.py` or `jobs/scheduler.py::sync_all_organisations`.
- Changing what Sync Now, Fix Missing Totals or Full Rebuild does on `/admin/sync`, or the `sync_runs` kinds.
- Parsing a Grassroots `/scores/*` payload (`matchSummary`, `matchType`, `isHome`, dismissal text, keeper catches).
- A missing, doubled or wrong-format game, or a match the scores API returns HTTP 204 for.
- Resolving a PlayHQ `game-centre/<short code>` link (BetterPosts import).
- Planning UK / Play-Cricket support or any new upstream feed.
- `games.match_format`, `fees.derive_fee_format`, `merge_logs` redirect maps in a sync.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/data-sources-and-sync.md`. Grep hints: `match_format never written`, `scheduled sync pulls the period`, `game-centre link`, `swallowed query error`, `keep_player_id`, `Data Source Topology`, `UK Expansion`, `Sync Architecture`, `owns_run`, `caught-behind`, `Partner API`, `May 2026 Audit`, `Historical Data Fix`, `org_recent`, `match_pull_failed`.

**Related guides**: fees (match-day charges read `match_format`); stats aggregation and filters (`v_effective_*` views, per-club id schemes); imports and manual entries (BetterImport reconcile runs at the tail of a sync); social posts (BetterPosts scorecard import); BetterIQ (opposition dossiers read the same cards).

## Standing rules

**Sources and identity**
1. Club cricket comes from CA's Grassroots proxy `grassrootsapiproxy.cricket.com.au`. Use only `/scores/*` and `/fixturesladders/grades/{id}...`. Restricted paths (`/fixturesladders/games/{id}`, `/participants/games/{id}/batting`, `/scorecards/...`) return 403. Do not try them.
2. Discovery is `/scores/grades/{grade_id}/matches` (all seasons back to 1975). Scorecards are `/scores/matches/{id}?responseModifier=includeScorecard`. HTTP 204 means a PlayHQ-namespace match Grassroots does not hold.
3. `jsconfig=eccn:true` is a ServiceStack camelCase flag, not a key. A bare curl without it returns PascalCase and `data.get("matches")` reads empty.
4. `apiv2.cricket.com.au` is the international stats API (no club cricket).
5. A PlayHQ `game-centre/<8 hex>` short code is a different id namespace. This contradicts `docs/afl-playhq-data-source.md` ("short code IS the real gameID"); that holds for the AFL tenant only.
6. Do not build a club button on PlayHQ's public `discoverGame` GraphQL: a CloudFront WAF 403s after about three requests. `discoverGradeFixture`/`discoverTeamFixture` 500 on cricket and introspection is blocked.
7. So a PlayHQ link resolves locally: `services/social_match_lookup.py` + `GET /admin/social/match-lookup`. A full UUID passes straight through. A PlayHQ link returns the club's recent completed matches to pick from, narrowed by slugifying the grade in the URL against our grade names (either-side-prefix fallback for sponsor suffixes). `_LOOKBACK_DAYS = 240`. Candidates reuse `_current_grade_rows` + `gr.get_grade_results`; do not write a second "which matches are ours".
8. Never trust PlayHQ `links.next` alone (it can loop past page 1100). Loops cap and stop on the first short batch (`max_pages=200` in `club_directory.discover_clubs`).
9. `upsert_organisation` keys on the id given. A PlayHQ UUID after a Grassroots GUID would duplicate the org. `find_matching_organisation` checks primary id, then `playhq_id`, then case-insensitive name. `include_archived=False` is for self-serve "already registered" checks only.
10. `players.id`, `grades.id`, `seasons.id` are per-club (uuid5 on collision); the raw CA guid is in `grassroots_id`. In sync use `_resolve_org_grade` / `_resolve_org_player`, never a global `session.get(Grade|Player, raw_guid)`. API calls use the raw guid.

**Parsing the scores payload**
11. `isHome` is on `matchSummary.teams`, not top-level `teams`. Wrong field fails silently (empty `home_team`).
12. `result`/`venue`/`date` are NOT on `matchSummary` (only `resultText` + `teams`). They are `raw.venue`, `raw.matchSchedule[0].startDateTime`, `matchSummary.resultText`. Format is `matchType` (never hardcode T20). Round gets "ROUND " only when the name has no letters. Overs is the longest innings bowled.
13. "Absent" / "Did Not Bat" dismissals (`dismissalTypeId > 0`, no ball faced) are not innings. Filter them from batting inserts and `_derive_partnerships_grassroots`.
14. CA does NOT mark the keeper in `dismissalText` (plain `"c: C Cecchi b: A Ricci"`; 6597 catches, 0 daggers). Caught-behind is structural: the catcher is the fielder whose row has `wicketKeeperCatches > 0`, or a stumping. Use `_innings_keeper_names(inn["fielding"])` + `_caught_by_keeper(dismissalText, keeper_names)`.
15. `batting_innings.caught_behind` and `bowler_wickets.caught_behind` are nullable bools (migrations 075, 076). NULL is unknown and readers treat it as a plain catch. Keep the flag off the `dismissal_type` string so "count caught" readers stay untouched.
16. Every consumer builds `keeper_names` from the same innings' `fielding` rows: sync batting insert, `_extract_bowler_wickets`, `backfill_caught_behind`, `iq_opponent`, `games.py` scorecard opposition rows.
17. Catches vs keeper catches: `fielding_stats.catches`/`catches_wk` per game, `player_season_stats.catches`/`catches_wk`/`catches_non_wk` per season. Outfield = `catches - catches_wk`. `player_season_grade_stats` holds combined catches only. Milestones, rankings and composite MVP stay combined by design.

**`match_format`**
18. Format is per FIXTURE; a grade cannot answer it (one grade plays both). The grade `fee_format` override is only for women's vs men's and excluding a grade. Never set a mixed grade to `two_day`.
19. Write `games.match_format` from the grade match LIST (`matchType`: "One Day" / "Two Day" / "T20"): no extra call, covers unopened cards. Store the string (consumers substring-parse it: `fees.derive_fee_format`, `iq_team._fmt_of`; the manual form writes free text).
20. Never store "BYE" (appears as a `matchType`; not a format; no scorecard so no `games` row).
21. Setting it on `Game()` alone fixes almost nothing: an already-synced game skips the per-game block. Also do a bulk `UPDATE ... WHERE match_format IS DISTINCT FROM` beside the `is_final` one. Any per-fixture field from the match list needs that bulk pass.
22. Do not edit fee rows directly. `recompute_fee_match_days` re-derives and leaves `auto_derived=False` and already-paid rows alone.
23. A migration's docstring is intent, not proof (033 claimed a sync backfill that never existed). Grep for the writer.

**Scheduled sync (`services/auto_sync.py` decides who and how far back)**
24. Scheduled job runs in Perth time, Sun AND Mon 01:00 (ids `weekly_sync`, `monday_results_sync`), not UTC. Same job both days: each run asks "what happened since this club's last sync".
25. Eligibility reuses `auth.modules.org_core_live` (cancelled/paused Core, expired Core trial, org switch) and fails OPEN for legacy clubs. Plus `archived_at IS NULL` and `is_active`.
26. Watermark = last run that PULLED MATCHES, kinds `org_recent` / `org_full` / `org_hard_refresh` (manual Sync Now counts). Errored, cancelled or restart-interrupted runs do not count. `OVERLAP_HOURS = 26` is subtracted. No watermark: `DEFAULT_LOOKBACK_DAYS = 7`. Behind more than `MAX_LOOKBACK_DAYS = 90` escalates to a full run.
27. "Successful" is not "pulled matches". `sync.py` swallows a game-pass failure to keep season aggregates, so it stamps `match_pull_failed` and `auto_sync.last_sync_at` ignores that run (`_pulled_matches_ok`). `ever_full` deliberately does NOT use that filter, or a club whose game pass keeps failing gets a full sync twice a week for ever.
28. `plan_run` never escalates to full twice: if a full run completed since the watermark and the club is still behind it returns `full_sync_did_not_catch_up` and stays incremental.
29. `org_recent` is deliberately not a full kind. Setup Wizard `_sync_ready`, `wizard_analytics` and `club_admin._FULL_SYNC_KINDS` read `org_full`/`org_hard_refresh` as "history pulled". Keep any new run kind out of that tuple. `main.py` restart self-heal resumes only the two full kinds.
30. Incremental is the SAME code path with smaller inputs: `auto_sync.season_in_window` (`SEASON_SPAN_DAYS = 400`) and `sync_grassroots_game_level_data(since=, season_ids=)`. The grade fan-out (one match-list call per grade per run) is as much of the saving as the scorecards.
31. An incremental run that added no games skips `_backfill_missing_season_stats`, `reconcile_imported_totals` and the bare `ANALYZE`. Milestones are scoped to players whose aggregates changed, not skipped.
32. `fixtures_in_window` asks "did the club play anything since its last pull" first (grade lists cached in-process for the sync). It is NOT an "is the season over" model. Every "sync anyway" branch is load-bearing: a CA season we do not hold or hold without grades, and every grade returning `[]` (`get_grade_matches` returns `[]` for a transient failure and an empty grade alike). Future fixtures do not count. Also: a season held with only SOME of the grades CA lists teams for (`new_grade_to_seed`, read from the teams feed via `_ca_grade_guids`), because only the sync this probe gates ever creates a grade row; deciding from held grades alone hid Leederville's whole Round 1 (archive: grep `Leederville's Round 1`).
33. An idle check still records a successful `org_recent` run so the watermark moves; otherwise the window reaches 90 days and the club gets a quarterly full rebuild for doing nothing.
34. Drift is DETECTED, not re-pulled (per direct instruction, no periodic full sync). `services/sync_drift.py` (monthly `check_all_organisations_drift`) compares CA season aggregates with `player_season_stats`, per player and only for participants CA reports; ignores `_backfill_missing_season_stats` rows and participants in a live merge; CA returning nothing is `unavailable`, never drift. Acknowledging survives a re-check that still finds drift. It never writes stats.

**Sync internals**
35. Two passes per full sync: Grassroots aggregate (`playhq_client.get_*_stats`, source of `player_season_stats`), then the scores pass (`sync_grassroots_game_level_data`). Per-game session pattern avoids async session deadlock. Never run a second game-level source (same match, different UUIDs, duplicate rows).
36. `sync_runs`: `update_sync_run`/`finish_sync_run` MERGE stats. Stale `running` rows become `error` at startup. `owns_run = run_id is None`: when a caller passes `run_id`, the CALLER must call `finish_sync_run` (hard-refresh does, on its true-success branch).
37. `merge_logs` maps (columns `removed_player_id` / `keep_player_id`, NOT `kept_`): filter `undone_at IS NULL`, resolve transitively with a cycle break, in both the aggregate and game passes. The game pass checks `known_player_ids` then `merged_away` at all five `participantId` consumers (batting, bowling, fielding, FOW, derived partnerships).
38. An `except` that hides a DB error must roll back AND hand back objects the request still reads. A bare `db.rollback()` expires every loaded instance; the next attribute read raises `greenlet_spawn has not been called`. Use `_rollback_keeping(db, *instances)` (`routers/admin.py`).

**Play-Cricket / UK (design only, see `docs/uk-play-cricket-data-source.md`)**
39. Do not scrape Play-Cricket HTML. Use the official API v2 (`play-cricket.com/api/v2/*.json`), token-gated per club.
40. No statistics endpoints: the UK has scorecards only, so we compute every season aggregate (promote the Fix Missing Totals rollup). `match_detail` adds toss and full extras (absent from CA).
41. Ids are integers: raw in `grassroots_id`, `id = uuid5(org, raw_id)` on collision. Season is a query param; derive `Season.year` from `match_date` (DD/MM/YYYY).
42. A token authenticates us; `site_id`/`match_id`/`division_id` picks whose data. We are controller for our own club only. A full opponent dossier needs the opponent's token, a league-site token or partner access.
43. REJECTED: one shared club key for all English clubs (breaches the host agreement, single point of failure, UK-GDPR-unlawful incl. children's data).
44. Plan: Phase 1 per-club BYO token (`playcricket_api_token` + `playcricket_site_id` on org, token-authed `playcricket_scores_client`), Phase 2 partner access. Low traffic, minimise PII.

**Added after the split (v9.100.1)**
45. The Cricket Australia seasons feed (`fixturesladders/organisations/{org}/seasons`) ignores both `offset` and `limit` and returns the club's whole history every call, so "the page was full" never means there is another page. `playhq_client.get_seasons` ends when a page adds no new id and is capped by `_MAX_SEASON_PAGES` (20). The normal sync, `auto_sync`, `iq_scout` and the teaser pull all call it. Never trust a full page as proof of more, and dedupe paged results on id (same trap as the `links.next` note). Archive: grep `seasons feed ignores paging` in `archive/club-directory-onboarding-and-admin-shell.md`.

**Quick Sync (v9.105.2)**
46. Quick Sync (`POST /organisations/{id}/sync/quick`) is an incremental run over the last `QUICK_LOOKBACK_DAYS` (7) under its own kind `org_quick`. Keep it out of `_WATERMARK_KINDS` and `_FULL_KINDS`: it cannot vouch for the gap since the club's last real run. Archive: grep `Quick Sync button`.

47. `grassroots_scores_client._grade_matches_cache` expires after `_GRADE_MATCHES_TTL` (30 min); `force=True` bypasses it. It used to live for the whole process, shared by the probe, the sync, BetterIQ, social rounds and fantasy, so never rely on a list being as old as the process. A new `sync_runs.skip_reason` of `no_fixtures_in_window` on a club that CA shows playing is this bug's signature.

## Traps and failure signatures

- Two-day grades all billed as One Day: `match_format` had no writer. Rules 18 to 21.
- PlayHQ game-centre link gives "Paste a match URL or a match ID": handlers matched full UUIDs only. Rule 7.
- Social post with blank date/ground, bare "RESULT", "ROUND Round 7" or a 50-over final labelled T20: read from `matchSummary` and hardcoded format. Rule 12.
- `Scorecard parse error: greenlet_spawn has not been called` for every club: query used `kept_player_id` (real `keep_player_id`), the swallowed error plus a bare rollback expired `club`. Merged-away players also silently stopped resolving. Rule 38.
- One player with ~280 batting rows instead of ~200: two game-level sources ran (rule 35).
- Player shows only 3 seasons in `player_season_stats`: stale or single-hop `merge_logs` redirect. One-off cleanup: `UPDATE merge_logs SET undone_at = NOW() WHERE undone_at IS NULL AND removed_player_id IN (SELECT id FROM players)`.
- Per-game counts over CA's aggregate by 1 or 2: Absent/DNB rows. One-off: `DELETE FROM batting_innings WHERE dismissal_type IN ('absent','did not bat','dnb')`.
- Club silently short results after a failed scorecard pull: watermark stepped over it (rule 27).
- Club stops syncing when its new season opens: "nothing played" decided from grades not yet created (rule 32).
- `Column expression ... got <property object>` from `select(Player.display_name)`: it is a Python property. Select mapped columns, compute in Python.

## How to verify a change here

- Real-Postgres auto-sync suite (eligibility incl. fail-open legacy club, watermark ignoring errored and `match_pull_failed` runs, anti-escalation, filtering asserted inside the real `sync_grassroots_game_level_data` with stubbed CA responses, drift false-positive guards). Run queries for real, not replayed in plain Python. File name not stated in the archive; grep `backend/verification` for `auto_sync` and `sync_drift`.
- For scorecard or social import changes, run the SHIPPED function body over a real Grassroots payload (extract from the router, retype nothing), with a control run that reproduces the reported failure (old column name plus bare rollback reproduces the greenlet error).
- Only live CA calls show an upstream shape. Reproduce through `grassroots_scores_client` (or add `jsconfig=eccn:true`).
- "My fix had no effect": confirm deployed code (`docker compose exec ... grep`), then read `docker compose logs <service> --since Nm` for the real traceback before rereading source.

## Operator commands and scripts

- `python -m app.scripts.backfill_match_format <org-id-or-slug>`: dry run by default; `--apply`, `--recompute` (re-derive fee match days), `--season YYYY`, `--all-seasons`. Default scope: seasons with `fee_member_seasons` rows plus the latest season. Writes only games under the club's OWN grades.
- `python -m app.scripts.backfill_caught_behind <org_id|all>`: re-reads scorecards, sets `batting_innings.caught_behind` (Full Rebuild network cost).
- `python -m app.scripts.rebuild_bowler_wickets <org_id|all>`: re-derives `bowler_wickets` with the flag.
- `python -m app.scripts.list_skipped_matches`: lists matches the scores API 204'd (no fallback).
- `/admin/sync` buttons: Quick Sync = `POST /organisations/{id}/sync/quick` (last 7 days, kind `org_quick`); Sync Now = `POST /organisations/{id}/sync`; Fix Missing Totals = `POST /club-admin/backfill-aggregates` (recomputes `player_season_stats` from per-game rows, no CA fetch); Full Rebuild = `POST /club-admin/hard-refresh` (wipes per-game tables, re-pulls, an hour or more). Internal names and `sync_runs.kind` are unchanged from the old labels.

## Open follow-ups

- 204'd PlayHQ-namespace matches stay missing across every sync and Full Rebuild.
- Play-Cricket Phases 1 and 2 not built.
- Ladders: archive says `/fixturesladders/grades/{id}/ladders` "not yet synced"; `get_grade_ladder` now fetches it live with a 1 hour cache. Verify before relying on either.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-SYNC-1] "`playhq_partner_client.py` still used by games, records and organisations routers; live scorecard view for Partner-only games" | No such file exists in `backend/app/services` and nothing imports it; `routers/games.py` has no Partner call | PlayHQ Partner API — May 2026 Audit (L12780-12799) | retire.
- [FLAG-SYNC-2] "`suggest_phq_ids()` powers the PHQ ID Match page `/admin/phq-match`" | `suggest_phq_ids` is not in `backend/app`; no phq-match route found | PlayHQ Partner API — May 2026 Audit (L12780-12799) | retire.
- [FLAG-SYNC-3] "`deep_sync_player()` calls the Partner API, ~3 seasons" | Now delegates to `sync_organisation(kind="player_deep")`; docstring says the Partner path is retired; still routed from `club_admin.py` | Sync Architecture (L12745-12779) | keep as "delegates to the org sync".
- [FLAG-SYNC-4] "The 204 gap is minimal, Partner sync not needed" | `sync.py` (~L1806) says a 204'd match has NO fallback and stays missing on every sync incl. Full Rebuild; `list_skipped_matches` exists | PlayHQ Partner API — May 2026 Audit (L12780-12799); Sync Architecture | verify per club with the script; treat as a known gap.
- [FLAG-SYNC-5] "`participantId` is the same GUID as `players.id`", "`grade_id` is the same UUID as `grades.id`", "uses `session.get(Grade, ...)`" | True only for legacy single-club rows; per-club uuid5 ids and `grassroots_id` now exist (`_resolve_org_grade`, `_resolve_org_player`) | Data Source Topology (L12708-12733); Sync Architecture (L12745-12779) | keep, with rule 10 as the correction.
- [FLAG-SYNC-6] "Full sync scheduled weekly, the weekly job" | Now Sun and Mon 01:00 Perth, incremental `org_recent` by default | Sync Architecture (L12745-12779) vs scheduled sync (L7293-7402) | keep the newer section.
- [FLAG-SYNC-7] "`main.py` restart self-heal resumes only the two full kinds" | Not re-checked; `_FULL_SYNC_KINDS` and `auto_sync._FULL_KINDS` are (`org_full`, `org_hard_refresh`) | The scheduled sync pulls the period's results (L7293-7402) | verify before adding a kind.
- [FLAG-SYNC-8] UK plan names `playcricket_scores_client` and org columns | Neither exists in `backend/app` | UK Expansion — Play-Cricket Data Source (L12734-12744) | keep as design only.
- [FLAG-SYNC-9] Applecross counts (3957 games, 41423 batting rows), "~3 seasons", "52 seasons" | One-off May 2026 evidence, drifted | May 2026 Historical Data Fix (L12820-12838); Data Source Topology | do not treat as current.
- [FLAG-SYNC-10] Match-lookup is described for cricket only | `routers/afl/social.py:236` has its own copy | A PlayHQ game-centre link (L8075-8164) | verify the sport.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| `games.match_format` was never written, so every match was a one-dayer (L7213-7271) | rules extracted | Standing rules 18 to 23, Traps 1, Operator commands |
| The scheduled sync pulls the period's results, not the club's whole history (L7293-7402) | rules extracted | Standing rules 24 to 34, Traps 8 to 10, Flags SYNC-6, SYNC-7 |
| A PlayHQ game-centre link is a different id namespace (L8075-8164) | rules extracted | Standing rules 5 to 7, 12, Traps 2 and 3, Flag SYNC-10 |
| &nbsp;&nbsp;&nbsp;### A swallowed query error, reported as a greenlet crash (v9.53.5.1) | rules extracted | Standing rule 38, Traps 4 |
| Data Source Topology (May 2026 investigation) (L12708-12733) | rules extracted | Standing rules 1 to 4, 8 to 10, Flags SYNC-5, SYNC-9 |
| UK Expansion — Play-Cricket Data Source (Jun 2026 investigation) (L12734-12744) | rules extracted | Standing rules 39 to 44, Open follow-ups, Flag SYNC-8 |
| Sync Architecture (L12745-12779) | rules extracted | Standing rules 11, 13 to 17, 35 to 37, Operator commands, Traps 5 to 7, Flags SYNC-3, SYNC-5, SYNC-6 |
| &nbsp;&nbsp;&nbsp;### Admin UI button names (Sync Actions card) | rules extracted | Operator commands (`/admin/sync` buttons) |
| PlayHQ Partner API — May 2026 Audit (L12780-12799) | superseded by Sync Architecture and later code (Partner path fully gone) | Standing rule 35, Flags SYNC-1 to SYNC-4, Open follow-ups |
| May 2026 Historical Data Fix — Resolution Log (L12820-12838) | rules extracted | Standing rules 11, 35, 36, Traps 5 to 7, Flag SYNC-9 |
48. A stored game is repaired on every pass: when `our_appearances_done` skips it, `participant_relink.repair_stored_game` first attaches any player the team sheet names whom the club now holds (resolved by `_team_pid`, scorecard already fetched, no extra request). Never add a second "who is on the sheet" resolver. A full-name match to a record with no CA id stamps the participant id on it (`adopt_identity`) so the feed does not mint a twin. Archive: grep `sync repairs dropped players itself`.
