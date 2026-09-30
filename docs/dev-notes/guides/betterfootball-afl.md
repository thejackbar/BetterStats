# Guide: BetterFootball / the AFL silo

**Read this before** (concrete triggers):
- Editing `backend/app/afl_main.py`, `models/afl.py`, `services/afl/*`, `routers/afl/*`, `frontend/src/afl/*`, or anything built with `VITE_SPORT=afl`.
- Porting a cricket screen, router or service to football (BetterAdmin, BetterSocials, BetterSelect, fees, votes, competitions).
- Touching the football sync (`services/afl/sync.py`, `sync_fixtures`, `_former_grades_for_team`, `discoverTeams`, `discoverTeamFixture`), PlayHQ GraphQL calls, or `afl_game_details`.
- Football Import Stats, Import Results, Import Awards, Manual Entries (`afl_manual_adjustments`), merge or split of football players.
- Symptoms: early rounds missing after a re-grade, stats reading the opposition's lines, a football page calling the cricket API, a merge that lost a career.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/betterfootball-afl.md`. Grep hints: `BetterSelect on BetterFootball`, `afl_lineup_slots`, `a delta, not a replacement`, `afl_manual_adjustments`, `discoverTeamFixture`, `Splitting a player`, `Import Results`, `import-game:`, `Import Awards`, `_award_key`, `Multi-sport: the AFL silo`, `afl_bootstrap`, `cricket_schema_mirror`, `season_group`.

**Related guides**: the cricket guides in `docs/dev-notes/guides/` that own behaviour football reuses (competitions and grade scope, votes, BetterSocials, BetterFees, merge carry rules).

## Standing rules

**Silo and identity**
1. One codebase, per-sport silos. Football is separate services (`bs-afl-frontend`, `bs-afl-backend`, `bs-afl-database`), separate database, same source. Cricket's `app/main.py` must stay untouched by football work.
2. Entry is `app/afl_main.py` (`uvicorn app.afl_main:app`, `SPORT=afl`, own `DATABASE_URL`). It reuses shared models and the whole `routers/auth.py` stack. Football code lives in `models/afl.py`, `services/afl/`, `routers/afl/`. `create_all` builds the DB on first boot; cricket tables exist empty by design.
3. Every football synced row's PK is `uuid5(org, playhq_id)` (org is `uuid5(AFL_NS, org_code)`). Raw PlayHQ ids live in `grassroots_id` / `playhq_id` and are what API calls use. Players key on the PlayHQ profile id, not the participant id.
4. `afl_game_details.synced_at` is the incremental-sync signal (NULL means discovered, not yet pulled). It must never get a server default.
5. Sport is chosen at build time: `VITE_SPORT=afl` mounts `src/afl/AflApp.jsx` (App.jsx early-returns, cricket bundle unchanged). Build args `VITE_SPORT=afl`, `VITE_BASE=/afl/`, `NGINX_CONF=nginx.afl.conf`, `WEB_ROOT=.../html/afl`. nginx proxies `/afl/api` to `bs-afl-backend`, never the cricket backend.
6. Football URLs are API-relative. Images are stored as `images/...` and drawn through `aflApi.mediaUrl`. A cricket `/api/...` URL (font, logo from a shared helper) must go through `rebaseApiUrl` or it resolves against the cricket API.
7. Stats model: games, goals, behinds, Best on Ground, quarter scores, play-by-play. No StatLab, Yearbook or Website module. Season aggregates are our rollup from per-game lines (`afl_player_season_stats`, recomputed every sync).

**PlayHQ API and sync**
8. Two public unauthenticated GraphQL endpoints: `api.playhq.com/graphql` (header `tenant: afl`, lowercase) and `spectator.playhq.com/graphql` (`X-PHQ-Tenant: afl`, play-by-play). GraphQL rejects unused variables: a trimmed query that keeps a declaration 400s every call. Pre-2024 games legitimately return "not electronically scored", so empty events are normal.
9. `discoverTeams` returns a team's CURRENT grade only, so a team re-graded mid-season loses its early rounds. `discoverTeamFixture(teamID)` works on the AFL tenant and gives every round with its grade. `_former_grades_for_team` keeps only rounds where the team id is one of the two sides, and drops a grade whose `round.grade.season.id` is not the season being synced (team ids can be reused across years). Both filters are load-bearing.
10. A former grade becomes an ordinary `by_grade` entry and a plain Sync Now pulls the rounds. It must NOT move the team row: `afl_teams.grade_id` holds the current division only (`is_current` guards it). Insert current grades first so a new team row lands under its current grade. `link_grade_manually` (paste a match link) remains the fallback.

**Mounting cricket code**
11. BetterAdmin (fees, comms, merch, CRM, directory, roster, committee, events, facilities, diary) and BetterSocials are cricket's own routers mounted on `afl_main.py`, not copied. `services/afl/cricket_schema_mirror.apply` replays cricket's additive raw-SQL DDL into the football DB, then football's own DDL runs. A per-club module switch decides what a club gets.
12. Where a shared route would read cricket data, football reads football data. Socials uses `afl_*` tables and football scoring (12.8 (80), margins in points) and hides cricket-only posts. BetterFees counts a football game from `afl_player_game_lines` (our side only, per `afl_game_details.our_side`) because nothing writes `game_appearances` on football. The helper keys on that table EXISTING so cricket's recompute is unchanged. The football sync runs the recompute after its rollup.
13. Football serves the same paths cricket's admin calls (`/admin/competitions*`, `/club-admin/seasons/merges*`, settings PATCH) so shared components run on either. Cricket route bodies are reused by lazy import inside a football wrapper with explicit keyword dependencies.
14. Shared starter-data services read `settings.sport` (qualifications, role types, committee titles, facilities and gear, diary months, roster Match Day roles, "Football Operations"); cricket output must stay unchanged. Copy naming BetterCricket reads `PLATFORM_NAME`. Xero and Square callback URLs carry `/afl/`. "nets" is not a facility type.
15. The player's availability link is cricket's `public_availability` (`/avail/:token`). `availability.dormant_player_ids` also reads `afl_player_game_lines` when it exists; without that every football player reads as never played.

**Seasons, competitions, grade scope**
16. A football season is one competition's season ("VAFA 2026"), so one year can be two rows. Merges reuse `season_aliases`; every football filter expands a picked season via `services/afl/season_groups.season_group`, bound as `= ANY(:season)`. The sync must not overwrite an existing season's name.
17. Competitions are seeded from the season name (`services/afl/competitions` strips the year), not an association. `CompetitionManager` is shared (`components/admin/CompetitionManager.jsx`); football answers `/admin/competitions/grouping` with nothing to do. A picked competition is an INCLUSION: it replaces the grade-type default and a foreign id fails closed to nothing. `create_all` gives `club_competitions.id` no default, so the lifespan sets `gen_random_uuid()` before `competition_ddl`.
18. `services/afl/grade_scope.py` sums per-grade season rows when a category is left out, only when nothing is picked. `stats_left_out` names only categories the club fields.
19. `organisations.competitions` (migration 262) is a JSON list `{name, from_year, to_year}` sharing ONE validator with `previous_names` (`club_history._clean_year_spans`). Shown beside the season picker, blank when unfilled.
20. Profile fields: date of birth (admin only, never public), jumper number (text, "07" kept), positions (public only with `public_show_role`), action photo. Draft mode uses a 4-digit PIN via shared `ClubPinGate` (423 from `/clubs/{slug}`). The trial-ended unpause queue was deliberately not ported.

**BetterSelect on football**
21. Football has its own selection module because cricket's pool, matrix and rules read cricket per-innings tables: `services/afl/select.py`, `select_rules.py`, `routers/afl/select.py` (`/afl-select/*`, `require_module("select")`, writes on `MANAGE_SELECTIONS`), five screens in `frontend/src/afl/pages/admin/select/`. Shared tables reused as is: `fixtures`, `teams`, `team_members`, `player_availability`, `player_availability_periods`.
22. The team sheet is its own table, `afl_lineup_slots` (slot is a field position, `INT` bench or `EMG` emergency, plus captain and vice). `fixture_lineups` is a batting list and is not touched. Six lines (B, HB, C, HF, F, Followers). A smaller side drops positions in `_DROP_ORDER` (`select.py`, wings first) so a 16-a-side grade plays without wings.
23. Fixtures are the games the sync already holds (it writes every game on the draw, played or not). `sync_fixtures` (end of every sync, and Update from PlayHQ) upserts a `fixtures` row keyed on the GAME'S OWN ID. A sync never deletes a fixture.
24. Form is OUR side only: `afl_player_game_lines` carries both teams, so every read joins `l.side = d.our_side`.
25. "Higher side" is the Squads order: `grade_ranks` maps a grade to the `teams.sequence` of the side playing it, directly or via the `afl_teams` name PlayHQ filed under that grade in any season.
26. `RULE_KINDS` (`select_rules.py`): team_size (info, 18/10/3), age (1 January of the season by default), finals qualification (in this grade / this grade or higher / club), higher_grade_limit, concussion (21 days from a dated `incident`, a `permit` clears), registration, fees, custom. Silence where the data cannot answer.

**Manual entries, imports, merge**
27. `afl_manual_adjustments` is one table with nullable `season_id` (blank means career-only). It is ADDITIVE: no `NOT EXISTS` gate against the synced rollup (unlike `afl_imported_stats`, which only fills gaps). Correcting a season means entering the SHORTFALL.
28. `services/afl/manual_stats.py::manual_branch` is the one UNION arm, used by name in all thirteen reads. A UNION matches by POSITION, so keep the caller's column order. Career-only rows need no exclusion clause (season-scoped reads bind `m.season_id`, season-keyed ones INNER JOIN `seasons`).
29. `season_by_season` folds duplicate grade-less rows of one year and applies a per-grade manual delta to the season headline after the merge-group fold (a `src` marker rides along). `most_goals_in_a_season` SUMS per player-season before ranking, or a +5 correction lists as its own season.
30. `manual_edit_logs` is reused; import undo snapshots BEFORE state so undo restores an overwritten adjustment. The table is deliberately NOT unique on (player, season, grade) (a merge brings two rows onto one key); a second created BY HAND is refused with 409. No per-game manual entry (Import Results is the answer).
31. A merge MUST move adjustments: the table cascades on `players`, so forgetting it DELETES corrections. `_move_side_tables` carries them; `afl_merge_logs.adjustment_ids` (idempotent lifespan ALTER) lets undo return exactly those rows. A split moves a season's adjustment; a career-only one stays.
32. Football `_merge_players_core` must also move `afl_imported_stats` and `player_achievements`: raw-SQL tables with a bare `player_id` and NO foreign key, so they orphan and reads that join `players` drop them silently. Their ids are recorded on `afl_merge_logs` (two JSONB columns); older logs read `[]`.
33. Split a player by SEASON: moves `afl_imported_stats`, `afl_player_game_lines` (via game season) and `player_achievements`, then recomputes `afl_player_season_stats`. An honour's `season` is free text (season id OR name), so match both. The new record gets NO `playhq_id`. Splitting off EVERY season is refused. No undo log by design: the two records are an exact-name pair, so merging back is the undo.
34. Import Results (`routers/afl/result_imports.py`, `/club-admin/result-imports/*`, `MANAGE_MANUAL_ENTRIES`; preview, resolve, commit, undo, template). Rows land in `games` plus `afl_game_details` so they appear like synced games. `afl_game_details` gained `source` ('playhq'|'import'), `import_batch_id`, `import_ref`, `is_bye`, `is_forfeit`, `result_note`; `playhq_id` is nullable. Idempotent ALTERs in `afl_main.py`.
35. Import game id is `uuid5(org, "import-game:" + season|team|date|opponent|round)` so corrected re-uploads UPDATE. The already-synced guard matches (date, opponent, grade name): Seniors and Reserves play the same club the same day, and date+opponent alone drops results. A different-grade game that day imports with a `check` warning.
36. Warnings: `sheet_error` (sheet figures disagree) versus `check` (inferred or odd result). Nothing is auto-corrected. A row that cannot import is `blocked` and named, never dropped silently.
37. Outcomes match on substrings ("Forfiet"). Cancelled and unscored rows always skip; forfeits import as their W/L; byes are opt-in, `status='BYE'` with NULL result (out of W/L/D and played count). Blank home/away is neutral (club stored as nominal home). `GET /resolve` caps row detail at `ROW_DETAIL_LIMIT` (5000); commit covers the whole sheet.
38. Column auto-mapping is a GLOBAL best assignment (strongest pair first, since "HamPoints" and "OppPoints" tie on "points"), plus a content sniff (60 percent of values in a known vocabulary).
39. Import Results undo deletes the games (children cascade), scoped to `source='import'` so a game the sync has taken over is never removed.
40. Import Awards (`routers/afl/award_imports.py`, `/club-admin/award-imports/*`, `MANAGE_AWARDS`; no schema change) writes `player_achievements`, `org_award_definitions`, `achievement_import_batches`. Unknown awards are CREATED; an existing label is reused and keeps its category. `_award_key` collapses case and "&"/"and". A near-miss (0.80 or more) is only a suggestion, since "Best Clubman" and "Best Clubperson" are different trophies.
41. Award identity: the sheet's player id where mapped, but an id can cover two people, so `_build_identities` only unifies rows whose names agree ignoring case. A name covering more than one identity is never auto-matched (`clash`, roster player as candidate for each). Rows naming no award are skipped and counted. Re-upload reads existing honours as `exists` (match on id when present, on name ONLY for someone about to be created). `players_unresolved` counts only winners. Undo removes awards only.
42. `importMatching.jsx` (`frontend/src/afl/pages/admin/`) is the shared wizard kit for Import Stats, Results and Awards (`SearchSelect`, `MatchTable`, `FieldRow`, `StatusBadge`, `PlayerMatch`, `parseSeasonGuess`). No second copy. Awards page: `AflAdminAwardsImport.jsx` at `/admin/import-awards`.
43. Football profile honour board: `GET /afl-players/{id}` returns `achievements`, drawn by `frontend/src/afl/components/honours.jsx`. Repeated wins of one trophy are ONE entry with every year. Resolve `display_name` in Python, not a join (duplicate definitions fan rows out). Name fallback only for a row with NO `player_id`. `honours.css` (scoped `.afl-honours`) widens the card to 196px and allows a third title line.
44. Navbar `AflPlayerSearch` is cricket's search pointed at the AFL roster and `/{slug}/players/{id}`, filtered locally, results show games and goals. Navbar breakpoint is `lg` (six links plus search do not fit at 768px).

## Traps and failure signatures
- Early rounds of a team absent after a re-grade: `discoverTeams` only knows the current grade (rules 9, 10).
- Best on ground or games belong to the opposition: a read lacks `l.side = d.our_side` (control run reads 4 games for 3).
- Every football player "dormant" on the availability link: `dormant_player_ids` not reading `afl_player_game_lines`.
- Seniors and Reserves results vanish on Import Results: guard omitted the team (rule 35).
- A club loses a removed player's career after a merge: FK-less side tables not moved (rule 32); cascade tables DELETE instead (rule 31).
- Same year drawn twice, or a +5 correction listed as a 5-goal season: fold and per-season SUM (rule 29).
- Football page calls the cricket API for a font or logo: missing `rebaseApiUrl`.
- `create_all` tables lack `gen_random_uuid()` defaults or later columns: set them idempotently in the football lifespan.
- GraphQL 400 on every PlayHQ call: an unused variable is still declared.
- One trophy drawn as several cards, a namesake's honours on another profile, or a clipped trophy name: rule 43.
- One sheet id reused by two people unifies them: rule 41.

## How to verify a change here
Backend suites in `backend/verification/`, each on a real Postgres through the real AFL boot path and HTTP stack, each with a control run that must REPORT, not crash: `verify_afl_select.py` (control: our-side scoping and football dormancy removed, 4 fail), `verify_afl_manual_entries.py`, `verify_afl_competitions.py`, `verify_afl_seasons.py`, `verify_afl_settings.py`, `verify_afl_player_profile.py`, `verify_afl_admin_extras.py`, `verify_afl_social.py`, `verify_afl_shared_modules.py`, `verify_afl_fee_match_days.py`. Re-run all after touching shared code.
Browser suites (Chromium, football production build) in `frontend/verification/`: `verify_afl_select_browser.mjs` (seeded by `seed_afl_select_browser.py`; control fails most checks against the previous build), `verify_afl_betteradmin_browser.mjs`, `verify_afl_socials_browser.mjs` (fixture from `seed_afl_socials_browser.py`), `verify_afl_admin_gaps_browser.mjs`, `verify_afl_admin_edits_browser.mjs`.
Gotchas: earlier browser suites assert on named data (a "Rivals" opponent, a club holding every BetterAdmin module), so on the Select seed they fail for the fixture, not the code. Build the schema through the real AFL lifespan, run twice.

## Operator commands and scripts
- `python -m app.scripts.afl_bootstrap <playhq_org_id> <user> '<pw>' --sync`: first admin and club, optional first sync. Test club: Curtin Uni Wesley, org code `d14445c4`.
- Compose definitions: `ops/afl/docker-compose.afl.yml`. Design docs: `docs/afl-betterstats-plan.md`, `docs/afl-playhq-data-source.md`.

## Open follow-ups
- Football votes could offer the picked side as an eligibility source on game night.
- Nothing pushes a picked side back to PlayHQ.
- `merge._enrich_player` counts `afl_player_season_stats` only, so import or adjustment history reads 0/0/0/0 on Merge Duplicates cards.
- The Directory squad filter reads BetterSelect `teams`, which football lacks, so it does not draw.
- Milestones are not scoped by the grade-type default (career facts, as on cricket).
- Imported results carry no player lines.

## Flags: conflicting, superseded or possibly obsolete guidance
- [FLAG-AFL-1] Next passes listed: self-serve registration, weekly sync scheduler, BetterSelect AFL, other modules | BetterSelect, BetterAdmin, Socials, votes, manual entries have since shipped; self-serve and scheduler not checked | Multi-sport: the AFL silo, L9925-9974 | verify
- [FLAG-AFL-2] `organisations.competitions` (JSON display history, 262) versus `club_competitions` table and `services/afl/competitions` (filter grouping) | two different "competitions" concepts in football, easy to confuse | re-graded team section L6644-6759 and admin port L9975-10040 | keep both
- [FLAG-AFL-3] `_DROP_ORDER` described as "wings, then ruck rover"; code holds position codes (`LW`, `RW`, `RR`, `LBP`...) in `services/afl/select.py` | consistent, read the constant | BetterSelect on BetterFootball L76-150 | keep
- [FLAG-AFL-4] `discoverTeamFixture` works on the AFL tenant but not cricket's Grassroots API | cross-archive claim, not re-verified live | re-graded team section L6644-6759 | verify if PlayHQ changes
- [FLAG-AFL-5] Old `POST /achievements/import` and its template remain but nothing in the UI calls them | may be dead, but cricket's Core Awards may use them | Import Awards L9137-9217 | verify before deleting

## Section coverage
| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| BetterSelect on BetterFootball: a ground, a bench and football's rules (v9.100.0), L76-150 | rules extracted | Rules 14, 15, 21 to 26; Traps 2, 3; Verify; Open follow-ups; Flag 3 |
| BetterFootball gets Manual Entries, a delta not a replacement (v9.43.0), L4666-4751 | rules extracted | Rules 27 to 31; Traps 5, 6; Open follow-ups 3 |
| BetterFootball: a re-graded team's first rounds, club competitions, navbar search, splitting a player (v9.30.0), L6644-6759 | rules extracted | Rules 9, 10, 19, 32, 33, 44; Flags 2, 4 |
| - `discoverTeams` reports the grade a team is in NOW | rules extracted | Rules 9, 10; Traps 1 |
| - `organisations.competitions` (migration 262) | rules extracted | Rule 19; Flag 2 |
| - Splitting a player, and the merge bug it uncovered | rules extracted | Rules 32, 33; Traps 5 |
| - Player search in the navbar | rules extracted | Rule 44 |
| BetterFootball, Import Results (v9.7.0), L8590-8664 | rules extracted | Rules 34 to 39; Traps 4; Open follow-ups 6 |
| BetterFootball, Import Awards (v9.9.0), L9137-9217 | rules extracted | Rules 40 to 43; Traps 10 to 12; Flag 5 |
| - Honour board on the public player profile (v9.9.1) | rules extracted | Rule 43 |
| Multi-sport: the AFL silo (Aug 2026), L9925-9974 | rules extracted | Rules 1 to 5, 7, 8; Operator commands; Flag 1 |
| BetterFootball runs the BetterStats admin, BetterAdmin and BetterSocials (v9.94.0/v9.95.0), L9975-10040 | rules extracted | Rules 6, 11 to 13, 16 to 18, 20; Traps 7, 8; Verify |
