# Guide: Match scorecards, fill-in players, public fixtures and lineups

**Read this before**:
- Editing `routers/games.py::get_scorecard` or `GET /games/{id}/scorecard` (live Grassroots rebuild, team classification, `innings_totals`).
- Editing `frontend/src/pages/MatchScorecard.jsx` (`splitSides`, `marginText`, `MatchHeader`, `TeamCard`, `WinnerTag`, `FillInBadge`, `ClaimFillInModal`).
- Touching `services/grassroots_scores_client.py` caches (`_SCORECARD_TTL`, `_MATCH_TTL`).
- Fill-in players, `********` redacted juniors, `is_fill_in`, `is_redacted`, `POST /players/claim-fill-in`, `include_fill_ins_in_stats`.
- Public Fixtures and Lineups pages, `services/lineups.py`, `services/player_aliases.py`, `player_name_aliases`.
- Symptoms: total not matching the batting card, missing second innings, duplicate bowler, a real player shown as FILL-IN, a manual card returning 500, the wrong crest on a card.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/scorecards-fixtures-and-lineups.md`. Grep hints: `two-day match's other two innings`, `caught_behind`, `Public Fixtures + Lineups`, `player_name_aliases`, `Fill-in players on the game scorecard`, `claim-fill-in`, `Scorecard endpoint rewritten`, `_scorecard_looks_incomplete`, `property object`, `SC3 Dashboard`, `_our_tid`, `WinnerTag`, `auto_generate_and_publish_recent_yearbooks`.

**Related guides**: shared-fixture / cross-club player scoping (a fixture is one `games` row owned by whoever synced first); sync architecture (`_resolve_org_player`, MyCricket/PlayHQ dual GUIDs); manual entries and the scorecard photo reader; BetterSocials (lineup posts); yearbooks; votes (uses `lineups.our_lineup_players`).

## Standing rules

**Scorecard endpoint precedence (current behaviour)**
1. When the live Grassroots fetch succeeds, BOTH teams' batting, bowling and innings totals are built entirely from it. Stored `batting_innings`/`bowling_spells` are only the fallback. Why: the DB never holds fill-ins, the opposition half or mid-edit corrections.
2. Team membership is decided by Grassroots' roster for that match (`our_team_roster_pids` / `opp_roster_pids`), never by whether a GUID is a `players` row. A registered player who guested for the opposition belongs on the opposition card.
3. `players` is consulted only via `_resolve_linked_id(pid_str, name)` to attach a hyperlink to an already classified row: literal id, `grassroots_id`, `player_name_aliases`, the team sheet's FULL name when one player holds it (`participant_names`), then `(surname, first_initial)` only when one player fits and the first names agree (Ashton is not Angus). It must never move a row between teams or change numbers.
4. `_our_tid` (which GR team is ours): org-name word (`org_word`) is PRIMARY; DB overlap is only the fallback when the org cannot be resolved. Why: a few contaminated stored rows swing an overlap count and swap crests and every fill-in flag.
5. Bat-only `runs` is summed from rows and NEVER replaced by GR `runsScored` (batters plus extras; the frontend adds extras again). Wickets and extras prefer GR's `numberOfWicketsFallen` / `totalExtras` for both sides. Our innings totals are recomputed from the final `batting_flat` after fill-in injection.
6. DB-built rows are swapped for GR-built ones only after the whole GR rebuild succeeds. That rebuild is inside a broad `try/except`, so any bug in it silently falls back to DB-only rendering. Null-check everything inside (`org` can be None).
7. Innings are keyed 1 to 4 (two-day matches). Never take only `innings[0]`/`innings[1]`.

**Cache**
8. `get_match_scorecard` caches `_SCORECARD_TTL` (900 s) and never caches a response failing `_scorecard_looks_incomplete` (real totals, zero batting rows: a scorer mid-save). `force=True` bypasses. A no-TTL cache pins a half-saved snapshot for the process life.
9. Match detail (`get_match_detail`/`get_matches_detail`) is separate, `_MATCH_TTL` 300 s (team lists change until the first ball).

**Fill-in players and redacted juniors**
10. A roster participant with no `players` row renders on our card as `player_id: null`, `is_fill_in: true`. A redacted participant (blank or all-asterisk name) renders literally `"********"`, `is_redacted: true`, NO badge. `_classify_unlinked_name(raw_name, batting_position)` returns `(display_name, is_fill_in, is_redacted)` and is the single rule for batting, bowling, fielding and partnerships.
11. `_looks_redacted()` names must be excluded from `our_batting_fingerprints`/`_nk_to_player`, or all redacted participants collide on `_name_key("********")`. A stale `players` row named `********` is normalised in a final pass over `batting_flat`/`bowling_flat`.
12. A known player with no `batting_innings` row for the game gets a SCORED row injected from GR stats (`our_missing_rows`), not only a DNB row.
13. CLAIM (`POST /players/claim-fill-in`, cap `MANAGE_PLAYERS`) is for participants with no `players` row and never for `is_redacted`. It reuses `_resolve_org_player` identity (raw GR GUID as id, `uuid5(org, guid)` only on a real cross-club collision, `grassroots_id` = raw GUID) so a later sync attaches. Idempotent. `existing_player_id` calls `admin.merge_players` as a plain function. `players.claim_note` is stored verbatim, never parsed. `get_scorecard` stays unauthenticated; the button is gated client-side on `CAP.MANAGE_PLAYERS`. PlayHQ URL auto-resolution was shelved (CSR SPA behind CloudFront; the game-centre short code is not the GUID).
14. `organisations.include_fill_ins_in_stats` (migration 147, default on) controls only whether a fill-in's NAME shows in partnerships and fielding cards; batting and bowling always show. Storage: `partnerships.batter1_name/batter2_name`, `fielding_stats.player_name` (only when id is NULL), always-NULL twins on `manual_partnerships`/`manual_fielding_stats` so `v_effective_*` unions line up. `fielding_stats.player_id` FK is `ON DELETE SET NULL`.
15. Sync uses `our_team_roster_guids` (raw GR strings) to tell "ours but unregistered" from "opposition", because `_team_pid` returning None cannot. A partnership is dropped only when NEITHER side has an id or a name.
16. Records boards inner-join `players` scoped to the org, so name-only fill-in rows never reach them.

**Manual cards, fall of wickets, partnerships**
17. `get_scorecard` shares one row builder for synced and manual tables (`BI = ManualBattingInnings if is_manual else BattingInnings`). Any column read there must exist on BOTH tables or every manual card 500s. NULL `caught_behind` means the card does not say and reads as a plain catch (see Flag 1).
18. `get_game_fall_of_wickets` and `get_game_partnerships` take `org_id` and scope the `players` join (`AND (:org_id IS NULL OR p.organisation_id = :org_id)`). Unscoped, another club's player showed on our card and wickets doubled. Fall of wickets also de-dupes by `(innings_number, wicket_number)`. A row that loses its link and has no stored name reads "Unknown", never a wrong person.

**Frontend scorecard**
19. `splitSides` files an innings under whoever batted (team name); alternating is only the fallback. A follow-on has one side batting twice in a row.
20. `marginText` works from each side's AGGREGATE: innings win, chase (wickets in hand from the LAST innings), defence (runs). The backend supplies no margin string.
21. The WON badge is decided once per match from the same split (`teamsMatch(game.winning_team, teamName)`), so a side's innings cannot disagree.
22. Per direct instruction: `MatchHeader` home-left/away-right; `TeamCard` row in batting order; two columns means one column per team. Header repeating the score is intentional. See Flag 3.
23. Crests: `teams[].owningOrganisation.logoUrl` (the "team" name is often a sponsor), bare `logoUrl/logo/imageUrl/image` fallback; our own side prefers `org.logo_url`, else `/images/organisations/{id}/logo` if `logo_data`. Carried on `innings_totals[n].logo_url`. `components/TeamBadge.jsx` falls back to initials on `onError`.
24. Link a partnership row to `/players/{id}` only when it has an id (a name without an id is legal).

**Public Fixtures and Lineups**
25. Live off Grassroots, nothing persisted, so no lineup history. `GET /organisations/{id}/lineups` is bounded on purpose (every match is a live fetch).
26. Source is the PLAIN match record `GET /scores/matches/{id}` WITHOUT `responseModifier=includeScorecard`: `teams[].players[]` (`participantId, name, shortName, roles`), `nonPlayingMembers[]`, `officials`. An empty `players` list means "not named yet", a normal state. `isHome/isWinner/scoreText` live on `matchSummary.teams`.
27. `services/lineups.py`: our side by `owningOrganisation.id` (our `organisations.id` IS the CA org GUID) then `club_match_keys`. `resolve_participants` is org-scoped by `id`/`grassroots_id`, then `player_name_aliases`, then `(surname, first_initial)`. CA may issue a DIFFERENT participant GUID on this route than the scorecard sync stored, so GUID-only matching is never enough. `our_lineup_players` returns `(players, unmatched)`.
28. `mode=upcoming` falls back to recent games when nothing is scheduled; `mode=past` takes `season_id/grade_id/offset/limit`. Category filter resolves once to a `grade_id` list via `grade_labels.org_grade_categories` (keyed on sponsor-stripped name, `strip_sponsor_suffix`) because a category may be an unconfirmed `suggest_category` guess and cannot go into SQL; Finals uses `is_final`. Both apply in `_played()` for past and as a Python filter over `org_grassroots_fixtures()` for upcoming. `categories` in the response lists only what the org has.
29. `SeasonSelector` opt-outs `showGenderFilter/showFinalsFilter/showCaptainFilter` (default true). Lineups turns them off: Gender/Games/Captain drive leaderboard params a fixture list never fetches, so they rendered and did nothing.
30. Lineup cards link to `/games/{match_id}` only when `status === 'COMPLETED'`. Fixtures rows deep-link `/{slug}/lineups?match={id}` (`GET /organisations/{id}/lineups/{match_id}`). Keep the category pill list in separate frontend state so pills do not flash empty on refetch.
31. BetterPosts lineup posts can use BetterSelect XI or the Play.Cricket list with no extra fetch. An unpublished side shows with a disabled button, never an empty post.

**Name aliases**
32. `player_name_aliases` (migration 195, org-scoped, `alias_key -> player_id`, `normalise_name_key` is lowercase and word-order independent) is an explicit tier ahead of surname+initial in `lineups.resolve_participants` and `_resolve_linked_id` (display only).
33. Auto-seeded by `seed_alias_on_rename` (`ON CONFLICT DO NOTHING`) from `rename_player`, `update_player_profile` (`display_name_override`) and `admin._merge_players_core` (removed player's name onto the kept player). Older renames need the alias by hand in "Also known as" (`AliasManager`, `GET/POST/DELETE /players/{id}/aliases`, cap `MANAGE_PLAYERS`).
34. Aliases are deliberately NOT wired into `sync.py::_team_pid` (gates every stats insert). A renamed player whose stats were never linked needs an alias by hand, then a Full Rebuild.

**Other**
35. On a Full Rebuild's true-success branch only, `hard_refresh_org._run` calls `auto_generate_and_publish_recent_yearbooks(s, org_id, count=3)` in its own try/except and fresh session (a yearbook failure must not look like a sync failure). Sync Now does not. Existing narrative is never overwritten; it publishes even if narrative generation fails. (Yearbooks guide owns this.)
36. `get_scorecard` returns `fielding` (per player: `catches`, `catches_wk`, `run_outs`, `stumpings`) and `MatchScorecard.jsx` draws it as `FieldingSection`. A scorebook import records catches as a per-player tally, never which batter each got out, so its dismissal text is a bare `c`; this section is where those catches show. The CSFW converter stores keeper catches in `catches_wk` with `catches` blank, so the section shows `max(catches, catches_wk)`. Row dividers use `pb-hairline-t`, never `border-t pb-hairline` (no such colour class).

## Traps and failure signatures

- Wrong total that changes after each fix: (1) `docker exec ... grep` a distinctive string to confirm what is deployed; (2) `docker compose logs betterstats-backend --since Nm | grep -A 30 <your log line>`. A traceback beats re-reading source. Three real causes for one symptom: a guest for the opposition swept on by `known_ids`, an `org.name` deref on `org=None` swallowed by the broad except, and the `@property` query below.
- `ArgumentError ... got <property object>`: `Player.display_name` is a Python `@property`. Select `display_name_override` and `name`, apply `or` in Python. `py_compile` cannot catch it.
- Live fetch timing (~1 to 1.5 s) but the old DB-only shape (opposition absent, extras equal only our bowlers' wides plus no-balls): the rebuild crashed and fell back. Read the logs.
- Total off by exactly the extras (202 not 197): `runsScored` went into bat-only `runs`.
- Duplicate bowler (one linked, one FILL-IN): different GUID for the same person; every loop (bowling, first-pass DNB, batting) must use `_resolve_linked_id`.
- Redacted batters missing or merged: `********` name-key collision.
- Wrong crest on both cards and the other team shown as FILL-IN: `_our_tid` chose by DB overlap.
- Only innings 1 and 2, margin "won by 71 runs" for a 7-wicket win: frontend read `innings[0..1]` only.
- Every manual card 500 with `AttributeError`: a column read that a manual table lacks. Blast radius was confirmed by probing every game of the club.
- Lineup player with 100+ games has no photo or link: GUID mismatch on the plain match route; renamed player unresolved: needs an alias.

## How to verify a change here

- `backend/verification/verify_manual_scorecard.py`: shipped `get_scorecard` route body over a manual game seeded as the upload commit writes it, real Postgres. Control (fix stashed) dies at check 1 on the `AttributeError`.
- `frontend/verification/verify_scorecard_innings_browser.mjs` (Chromium, the reported match's live payload: four innings in batting order, winner on both its cards, "31 & 128", 7-wicket margin, one-day unchanged). Control fails on "got 2" innings and the wrong margin.
- The GR rebuild was once verified by replaying loop logic offline in plain Python; that never ran a real SQLAlchemy `select()`, which hid the `@property` bug. Exercise the real route body against Postgres.
- Gotchas: `fours=None` on the ORM does not store NULL (`server_default "0"` applies), force NULL in SQL; `font-display` also matches crest initials, address the name by its `.truncate`.
- Visual check: point the dev server `/api` proxy (`vite.config.js`) at `https://betterat.cricket` for one session, screenshot with the `playwright` CLI, restore. Raw GR calls need `jsconfig=eccn:true` (camelCase). Compare raw `grassrootsapiproxy.cricket.com.au/scores/matches/{id}?responseModifier=includeScorecard` with `/api/games/{id}/scorecard`.

## Operator commands and scripts

none specific to this area. A Full Rebuild (`POST /club-admin/hard-refresh`) is needed after adding an alias for a renamed player, and it triggers yearbook auto-generation.

## Open follow-ups

- Fill-in stats never land in stored per-game tables (`sync_grassroots_game_level_data` gates inserts on `our_team_pids`); the live scorecard fix is view-only.
- `fielding_stats` has no live GR merge in `get_scorecard` (DB only).
- No admin flow to edit a fill-in's name or match a PlayHQ profile by pasted URL.
- `_manual_opp_from_payload` sets no `logo_url`, so uploaded cards draw initials.
- `records.py::top_partnerships` requires both batters' `organisation_id` to match, yet a phantom stand can still surface for a club when two contaminated players never played for it in that match. Needs a platform audit and probably a sync-side fix. The contaminated stored rows were not cleaned up.
- Undoing a merge does not remove the alias it seeded.
- `matchSummary.teams` carries `wonToss`/`battedFirst` (opening for BetterIQ toss analysis); toss and Player of the Match are not shown.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-SCORE-1] Archive: `caught_behind` is synced-only and the fix was NULL with "not a new column" | Code now reads `bi.caught_behind` unconditionally with a comment that it is a real column on both tables (migration 291); the manual dict at `routers/games.py:550` sets `None` | "A two-day match's other two innings..." L10379-10459 | verify migration 291, retire the "no new column" wording, keep the shared-builder lesson
- [FLAG-SCORE-2] v8.79.0: badges are initials because "we hold no team logos" | Superseded by v8.79.1 (crests) | "Match scorecard page redesigned..." L14402-14593 | keep rule 23
- [FLAG-SCORE-3] v8.79.2: header is home-left/away-right ALWAYS | `MatchScorecard.jsx` now has `sidesSwapped(nameA, nameB, homeTeam, awayTeam)` (~line 294) and other CLAUDE.md notes (v9.98.6, not in this archive) say the header judges both sides against both teams | same section, v8.79.2 | verify against the file before relying on rule 22 for the header
- [FLAG-SCORE-4] v8.60.0: our innings `runs` prefer GR's total | Wrong, corrected in v8.60.1 (double-counted extras); rule 5 is current | "Fill-in players on the game scorecard" L14030-14128 | retire the v8.60.0 wording
- [FLAG-SCORE-5] v8.60.x "Not done": no partnership name column, fielding skipped for fill-ins | Superseded by v8.61.0 (migration 147) | L14129-14217 | retire; keep only the sync-still-gated item
- [FLAG-SCORE-6] v8.78.0 org-crash fix made DB overlap the primary "ours" signal | Reversed in v8.79.3; code at `routers/games.py:1053-1060` matches the reversal | L14218-14401 and L14402-14593 | keep rule 4
- [FLAG-SCORE-7] v8.78.0 first follow-up presents the TTL cache fix | The TTL and `_scorecard_looks_incomplete` (`grassroots_scores_client.py:49, 293`) exist but were not the cause of the "16/0" symptom | L14218-14401 | keep rule 8, do not cite as that fix
- [FLAG-SCORE-8] Lineups section leans on a "GR path can't see the toss" note from another archive | `wonToss`/`battedFirst` exist on `matchSummary.teams` | L13038-13200 | verify before repeating the no-toss claim
- [FLAG-SCORE-9] Yearbook auto-generation text sits inside the v8.79.3 scorecard section | Misfiled; code still matches (`club_admin.py:5084`) | L14402-14593 | move to the yearbooks guide, verify count=3 there

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| A two-day match's other two innings, and a card that would not open (v9.54.1) (L10379-10459) | rules extracted | Rules 7, 17, 19 to 21; Traps 7, 8 |
| - `manual_batting_innings` has no `caught_behind` | rules extracted (partly superseded) | Rule 17; Flag 1 |
| - verification and harness notes | rules extracted | How to verify |
| Public Fixtures + Lineups pages, and the CA team-list route (v8.94.0) (L13038-13200) | rules extracted | Rules 25 to 34 |
| - Name-fallback fix; Category + Finals filters; Cross-linking | rules extracted | Rules 27 to 30 |
| - Player name aliases (v8.94.2, migration 195); merge seeds alias (v8.94.3) | rules extracted | Rules 32 to 34 |
| - BetterPosts lineup source (v8.94.4); Not built | rules extracted | Rule 31; Open follow-ups; Flag 8 |
| Fill-in players on the game scorecard (v8.60.0 to v8.60.3) (L14030-14128) | rules extracted | Rules 10 to 12; Flags 4, 5 |
| - v8.60.1 follow-up (extras, stale redacted row); v8.60.3 (redacted not fill-in) | rules extracted | Rules 5, 10, 11 |
| Fill-in players: partnerships/fielding toggle + claim-a-fill-in (v8.61.0) (L14129-14217) | rules extracted | Rules 13 to 16, 24 |
| Scorecard endpoint rewritten to trust Grassroots, not our own DB, for both teams (v8.78.0) (L14218-14401) | rules extracted | Rules 1 to 6 |
| - Follow-up 1 (cache no expiry) | rules extracted | Rule 8; Flag 7 |
| - Follow-up 2 (`org.name` crash); Follow-up 3 (`@property` in select); diagnostic order | rules extracted | Rules 4, 6; Traps 1 to 3; Flag 6 |
| Match scorecard page redesigned around the SC3 Dashboard layout (v8.79.0) (L14402-14593) | rules extracted | Rules 20, 22; Flags 2, 3 |
| - v8.79.1 crests and header; v8.79.2 winner and ordering | rules extracted | Rules 21 to 23 |
| - v8.79.3 cross-club leak in team classification | rules extracted | Rules 4, 18; Open follow-ups |
| - Yearbook auto-generation after Full Rebuild (misfiled) | rules extracted | Rule 35; Flag 9 |
