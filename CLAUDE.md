# BetterStats — Claude Session Notes

## Server Deploy Command

Always use the **central** compose file. Never use `/srv/docker/betterstats/docker-compose.yml`.

```bash
git -C /srv/docker/betterstats pull origin main && \
docker compose -f /srv/docker/docker-compose.yaml build --no-cache betterstats-frontend betterstats-backend && \
docker compose -f /srv/docker/docker-compose.yaml up -d --force-recreate betterstats-frontend betterstats-backend
```

- `--no-cache` on the build step is required to avoid stale Docker layer cache
- Only rebuild the two betterstats services, not the whole stack
- nginx-proxy-manager routes `betterstats.cricket` → `betterstats-frontend` container on `docker-shared-net` (apex is the canonical domain; `www.betterstats.cricket` should 301-redirect to it)
- The backend container name is `betterstats-backend` — this is the correct hostname in `nginx.conf`

## Public Domain

The canonical public domain is **`https://betterstats.cricket`** (no `www`). The old `betterstats.bltbox.com` domain is retired.

- Hardcoded references live in `frontend/src/hooks/usePageMeta.js` (`BASE_URL`) and `frontend/index.html` (`og:url`) — keep both on the apex domain.
- `CORS_ORIGINS` should be `https://betterstats.cricket` in the server `.env`, but note CORS is dormant in practice: the frontend calls the API via a same-origin relative `/api` path, so cross-origin checks never fire. Updating it is hygiene, not a functional requirement.
- Any new build/config that references the public URL must point to `betterstats.cricket`.

## Version Numbers

Each release lives in its own file under **`frontend/src/data/changelog/`** — never hand-edit `frontend/src/version.js` (it derives `SITE_VERSION` from the highest-sortKey entry in that folder). Drop a new `v-X-Y-Z.js` file when you ship:
- Small fix: `+0.0.0.1`
- Medium change: `+0.0.1`
- Large change: `+0.1`

See "Feature Changelog" below for the file format.

## Branch

Active development branch: `claude/fix-historical-game-data-QEN3b`
Push to this branch AND to `main` via MCP after each change.

## Architecture

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (`backend/`)
- **Frontend**: React + Vite + Tailwind CSS (`frontend/`)
- **API**: Grassroots API proxy (`grassrootsapiproxy.cricket.com.au`) — season-aggregate stats freely accessible; game-level paths exist but the proxy's upstream API key is restricted
- `jsconfig=eccn:true` is a ServiceStack formatting flag, NOT an API key

## Data Source Topology (May 2026 investigation)

Cricket Australia hosts club cricket data across **two separate backends**, both reached via `play.cricket.com.au`:

1. **PlayHQ** (post-migration, ~2023+): GUID-keyed. Reachable via:
   - Partner REST API `api.playhq.com/v1/...` — public key only returns ~3 seasons (Summer 23/24, 24/25, 25/26). `/teams` is 401 with public key. `/grades` (org-level) is 404. `/v2/games/{id}/summary` works for IDs in this universe.
   - Public GraphQL `api.playhq.com/graphql` — `discoverGame` works for current games, `discoverGradeFixture` and `discoverTeamFixture` 500 with "Bolt adapter map not found" (require session/cookie auth the website holds). Schema introspection disabled.

2. **MyCricket / Pulselive Play Community** (legacy / pre-migration): GUID-keyed throughout (different namespace from PlayHQ). Data confirmed to reach back to at least 1975. Reachable via the same `grassrootsapiproxy.cricket.com.au` host we already use — just on a different path prefix than the proxy's restricted endpoints:
   - **`/scores/grades/{grade_id}/matches`** — all matches in a grade. ✓ unauthenticated. **Primary match discovery path** — grade_id is the same UUID as `grades.id` in our DB, works for all seasons including pre-2000. Confirmed 200 OK for a 1996 Applecross 8th Grade game.
   - **`/scores/teams/{team_id}/matches`** — list of matches a team played that season. ✓ unauthenticated. Secondary/fallback; team IDs require a fixturesladders call first.
   - **`/scores/matches/{match_id}?responseModifier=includeScorecard`** — full scorecard (batting, bowling, fielding, fall-of-wickets). ✓ unauthenticated. Returns **HTTP 204 No Content** for post-migration PlayHQ-namespace IDs, which is a clean "not mine" signal.
   - **`/fixturesladders/grades/{grade_id}/ladders`** — grade ladder (win/loss/points standings). ✓ unauthenticated 200 OK. Useful for future ladder feature — not yet synced.
   - **`/fixturesladders/grades/{grade_id}`** — grade metadata. ✓ unauthenticated 200 OK.
   - `participantId` in the response **is the same GUID as `players.id` in our DB** — no extra mapping needed.
   - The restricted paths (`/fixturesladders/games/{id}`, `/participants/games/{id}/batting`, `/scorecards/...`) all return `403 "API key does not have access"`. **Don't try those.** The `/scores/*` path is the one that works.
   - `apiv2.cricket.com.au` — has Swagger UI at `/`, OpenAPI at `/openapi.json`. Looks promising at first glance but is the **international** stats API (Ashes, BBL, Sheffield Shield) — does NOT contain club cricket data. Skip.
   - `api.playcommunity.pulselive.com` — verified `/registration` only; broader scope unknown.
   - `crm-communitycricket-cdn.cricket.com.au` — referenced by the bundle, scope unknown.

   **How to find the real API call**: the play.cricket.com.au website is a CSR Pulselive SPA (`window.API_ACCOUNT = 'playcommunity'`, bundle at `/resources/playcricket/v1.28.6/scripts/bundle-es.min.js`). HTML is just a shell. Anonymous server-side curls of `ca.playhq.com/*` and JS bundles get 403'd. Network-tab the request from a real browser load to recover the URL — that's how we found `/scores/*`.

3. **Pagination quirk**: PlayHQ's `links.next` is sometimes returned forever even when the data is exhausted (observed paginating past page 1100 on a single grade). Our pagination loops cap at MAX_PAGES=200 and stop on the first short batch — never trust `links.next` alone.

4. **Org duplication trap**: `upsert_organisation` keys on whatever `id` is passed in, so calling sync with a PlayHQ UUID after the org was already created with a Grassroots GUID would create a duplicate row (one with `playhq_id=NULL` matching the other org's `id`). Detected May 2026 for Applecross, cleaned up via direct DELETE. Guarded since commit ceadd84 — layered check on (a) primary id, (b) existing org's `playhq_id` matching incoming id, (c) name match (case-insensitive) before inserting.

## Sync Architecture

### Admin UI button names (Sync Actions card)

The three buttons on `/admin/sync` map to backend endpoints as follows. When
the user says one of the UI names, this is what they mean:

| UI button             | Backend route                                  | What it does                                                        |
|-----------------------|------------------------------------------------|---------------------------------------------------------------------|
| **Sync Now**          | `POST /organisations/{id}/sync`                | Pull latest games & stats. Safe to run anytime — the weekly job.    |
| **Fix Missing Totals**| backfill aggregates endpoint (`/club-admin/...`) | Recomputes `player_season_stats` from existing per-game rows. No CA fetch. Use when a player shows 0 matches/runs despite having scorecards. |
| **Full Rebuild**      | `POST /club-admin/hard-refresh`                | Wipes per-game tables and re-pulls everything from CA. Slow (hour+). Use after sync-logic changes. |

(Renamed Apr–May 2026; old labels were "Sync" / "Backfill Aggregates" /
"Hard Refresh". Internal endpoint names and the `kind` field on `sync_runs`
are unchanged.)

- **Full sync** (`POST /organisations/{id}/sync`) / **Hard refresh** (`POST /club-admin/hard-refresh`): scheduled weekly + on-demand. Two passes:
  1. **Grassroots aggregate** (`playhq_client.get_*_stats`) — season totals for all 52 seasons. Source of `player_season_stats`.
  2. **Grassroots scores** (`grassroots_scores_client` + `sync_grassroots_game_level_data`) — game-level scorecards confirmed back to at least 1975. Iterates grades from DB (all seasons, all grades), calls `/scores/grades/{grade_id}/matches` for each to get match IDs, fetches `/scores/matches/{id}?includeScorecard` for each. Skips PHQ-namespace IDs that 204. Per-game session pattern to avoid async session deadlock. Uses `session.get(Grade, ...)` to avoid stale-cache FK violations. No longer depends on fixturesladders for discovery, so pre-2000 seasons are fully covered.
- **PlayHQ Partner game-level sync** is **removed** from `sync_organisation` (May 2026 audit). The public API key only exposed ~3 seasons of history vs Grassroots's 50+, AND because the same physical match has different UUIDs in PHQ vs Grassroots, running both produced duplicate batting rows. `sync_game_level_data`, `_backfill_player_playhq_ids`, and `process_game_updated_webhook` were deleted from sync.py — see git history if ever needed again.
- **Per-player deep sync**: `deep_sync_player()` — admin-triggered, still present but pre-dates the Grassroots unlock. Calls PlayHQ Partner API; only covers ~3 recent seasons. Low value now that Grassroots covers everything including 25/26.
- **Sync runs persisted** in `sync_runs` table (migration 005). `update_sync_run` and `finish_sync_run` MERGE stats into the existing row (don't replace) so sub-phases accumulate. Stale `running` rows are marked `error` on backend startup.
- **`owns_run` gotcha**: inside `sync_organisation`, `owns_run = run_id is None`. So when a caller passes `run_id` (e.g. the hard-refresh handler that calls `start_sync_run` itself), sync_organisation only ever calls `update_sync_run` on success and NEVER `finish_sync_run`. The **caller** is responsible for finishing the run. The hard-refresh handler (`club_admin.py:_run`) used to only call `finish_sync_run` in the exception branch, so every successful hard-refresh sat at `running` forever — fixed May 2026.
- **Merge-aware GR sync** (May 2026, v3.0.2): `sync_grassroots_game_level_data` now builds a `merged_away: removed_player_id → keep_player_id` map from `merge_logs WHERE undone_at IS NULL` (with transitive resolution) during discovery. Each of the five `participantId` consumers (batting, bowling, fielding, fall-of-wickets, derived partnerships) checks `known_player_ids` first and falls back to `merged_away` before skipping. Without this, scorecards referencing a previously-merged player_id silently dropped those stats, leaving the kept player short on innings/wickets/catches/fall-of-wickets.
- **Aggregate-sync merge map** (v3.0.2.1) was previously NOT filtering `merge_logs` by `undone_at IS NULL` AND was building only a single-hop redirect dict. Two consequences:
  1. Stale entries (e.g. a merge that was reversed by a later re-merge in the opposite direction) poisoned the map — observed for Cooper Jnr (`92F`) where a 04:59 merge `KEEP=09c REMOVED=92F` redirected his aggregate stats to `09c` (which no longer exists), silently dropping every season except those keyed under a different ID that resolved cleanly. Symptom: per-game `batting_innings` correct (different sync path), but `player_season_stats` summary showed only 3 seasons.
  2. Multi-step merges (A→B→C) would redirect A to B only; if B was later merged away, the insert hit the safety net and got dropped.
  Fix: filter by `undone_at IS NULL` and resolve transitively with cycle break — same pattern as the GR sync function. Manual cleanup also needed for already-poisoned rows: `UPDATE merge_logs SET undone_at = NOW() WHERE undone_at IS NULL AND removed_player_id IN (SELECT id FROM players)` to mark entries where the "removed" player is back in the players table.
- **"Absent" / "DNB" dismissals aren't innings** (v3.0.2.2): GR scorecards mark a batter "Absent" or "Did Not Bat" with `dismissalTypeId > 0` but no ball faced. CA's aggregate API correctly excludes these, but our per-game parser used to insert `batting_innings` rows for them — causing per-game counts to over-shoot aggregate by 1-2 rows for any player who's ever been Absent. Now filtered in both the batting-row insert and `_derive_partnerships_grassroots` (since absent batters were never at the crease). Existing over-counted rows need a one-time `DELETE FROM batting_innings WHERE dismissal_type IN ('absent', 'did not bat', 'dnb')` to clean up.
- **GR scorecard team-name parsing**: `isHome` lives on `matchSummary.teams`, NOT on the top-level `teams` array. Reading from the wrong field is silently OK (no error) but produces empty `home_team`.

## PlayHQ Partner API — May 2026 Audit

**Finding**: Grassroots `/scores/*` IS returning scorecards for recent seasons (25/26 confirmed). The "204 for post-migration games" gap is minimal in practice — Applecross's May 2026 hard refresh got 4204 GR matches, 3947 new games, across all seasons including recent ones. The Partner sync was not needed.

**What was removed (May 2026)**:
- `sync_game_level_data()` — the disabled PHQ Partner game-level sync (was called with `all_games=[]`)
- `_backfill_player_playhq_ids()` — PHQ ID backfill from game appearances, never called in sync flow
- `process_game_updated_webhook()` — empty stub

**What was kept (still live)**:
- `deep_sync_player()` in sync.py — admin-triggered per-player resync via Partner API; low value now, but still callable from admin UI
- `suggest_phq_ids()` in sync.py — powers the "PHQ ID Match" admin page (`/admin/phq-match`)
- `playhq_partner_client.py` — still used by games router (live scorecard view for the rare Partner-only games), records router, and organisations router
- `playhq_id` on Player/Organisation models — retained as nullable legacy field; harmless and used for display in admin

**Data layer summary**:
- Season-aggregate stats (`player_season_stats`): Grassroots aggregate API → all 52 seasons ✓
- Game-level stats (`batting_innings`, `bowling_spells`, `fielding_stats`): Grassroots `/scores/*` → all seasons including 25/26 ✓ (204 gap is minimal)
- Live scorecard view for Partner-only games: PlayHQ Partner API via games router (rarely hit)

## Key Notes

- PlayHQ public game summary API is "not applicable to Cricket" — no scorecards without a partner JWT
- PostgreSQL `ORDER BY year DESC` defaults to NULLS FIRST — always use `.nullslast()`
- API field names: `bowlingEconomyRate`, `fieldingTotalCatches`, no `bowlingOvers` (derive from `bowlingBalls`)
- `Season.year` is NULL when Grassroots doesn't return `startDate` — extract from name (`"Summer 2010/11"` → `2010`) as a fallback
- `stats["player_seasons"]` in sync is `len(player_data)` summed across seasons, i.e. player-season records, not unique players. With 52 seasons × ~3.4 avg seasons/player ≈ 5326 (which Applecross actually shows). Renamed from `stats["players"]` to match what it counts.

## May 2026 Historical Data Fix — Resolution Log

**Problem**: post-migration, every historical game had blank `home_team`/`away_team` AND Jack Barendse had ~280 batting rows instead of the expected 200. Two root causes.

**Fix 1 — duplicate batting rows from running both sync paths**:
PlayHQ Partner game-level sync was disabled in `sync_organisation` (see Sync Architecture above). Same physical match has different UUIDs in PHQ vs Grassroots; the existing-game skip is UUID-based; running both produced duplicate batting rows.

**Fix 2 — `isHome` lookup on wrong field**:
GR scorecard parser was reading `isHome` from the top-level `teams` array — silently absent, so every game's `home_team` was empty. The flag actually lives on `matchSummary.teams`. Fixed and re-parses cleanly.

**Verification (Applecross, post-wipe + hard refresh)**:
- games: 3957 (was 4418 — old number was bloated by PHQ/GR duplicates)
- batting_innings: 41423, bowling_spells: 26862, fielding_stats: 15495
- games with empty home_team: **0**
- Barendse, Jack: **200 batting / 168 bowling / 93 fielding** ✓

**Fix 3 — successful hard-refresh stuck at `running`** (discovered during the verification of Fixes 1+2):
`sync_organisation` only calls `finish_sync_run` when it owns the run (i.e. when called without a `run_id`). The hard-refresh handler owns the run itself but only called `finish_sync_run` in its exception branch. Fixed `club_admin.py::hard_refresh_org._run` to call `finish_sync_run(run_id, stats)` after a successful `await sync_organisation(...)`.

## June 2026 Cross-Club Player Over-Count Fix (v7.32.1)

**Symptom**: a player who turned out for two synced clubs (e.g. Applecross **Cricket Club** *and* Applecross **Junior Cricket Club**) showed his *combined* career on each club's page — 7 ACC matches displayed as 63 (7 + 56 junior).

**Root cause — players have the SAME shared-GUID collision that Seasons already solved.** `players.id` is the raw Cricket Australia participant GUID used as a **global** primary key, but CA reuses one participant GUID for a person across every club they play for. Both clubs' org-scoped aggregate feeds (`/participants/organisations/{org}/...-statistics`) therefore return that one GUID. Whichever club syncs first **creates** the single `players` row (and sets its `organisation_id`); the other club's sync then finds it by PK — `session.get(Player, pid)` is a **global** lookup, not org-scoped (sync.py ~538/558) — and attaches *its* seasons' `player_season_stats` to the same row. Every career query then did `SUM(player_season_stats.matches) … WHERE player_id = :pid` with **no organisation filter**, so the total double-counted across both clubs. (Seasons dodge this via a per-club derived id `uuid5(org, grassroots_id)`; players were never given that treatment.)

**Fix — enforce the invariant "a player's effective season stats are only the rows whose season belongs to the player's own org", once at the view + at every base-table reader that summed by org-*membership* instead of by *season's* org:**
- **Migration 060** redefines `v_effective_player_season_stats` so the base-table branch only emits a row when `EXISTS (player.organisation_id IS NULL OR player.org = season.org)`. This is the single point that fixes **every** view consumer — `get_career_*` / `get_season_by_season` (player profile), `records.py` (club records), `get_player_team_breakdown`'s aggregate count. Non-destructive (filters on read; base rows untouched), so it self-corrects and survives a re-sync — **no data cleanup or re-sync needed**.
- Base-table readers that bypass the view were scoped to the org's seasons individually: `players.py` upcoming-milestones, `sync.py::_compute_milestones` (stops minting inflated milestone rows), `iq.py::_their_key_players`, `statlab.py` (career + per-season + family + minutes), `iq_trends.py` active-players overview, `selection_pool.py` latest-season form snapshot, `club_admin.py` milestone projection.
- **Anti-pattern to avoid in new queries**: summing `player_season_stats` for a player filtered only by `players.organisation_id = :org` (player *membership*) without also constraining the **season** to that org. Read the view, or join `seasons s` and filter `s.organisation_id`. Queries that filter `WHERE s.organisation_id = :org` or `WHERE pss.season_id = <specific org season>` were already correct (yearbooks, iq_trends trajectory/breakout, iq_selection, the sync backfill).

**Deeper (deferred) fix**: give players a per-club derived id like Seasons (`uuid5(org, participant_guid)`, with the raw GUID kept for scorecard `participantId` matching). That stops the co-mingling at the source, but it's a large migration (every game-level FK, merge_logs, `/players/{id}` URLs, the GR-sync hot path) — out of scope for the display bug. The view/query scoping makes the symptom impossible to display regardless.

## BetterFees — Match-Fee Auto-Allocation (v7.32.0, Jun 2026)

A recorded match-fee payment settles a member's games automatically, **oldest game first**. Per-game Paid / Part-paid / Unpaid is **derived on read, not stored** — there is no per-row paid flag any more.

- **Single source of truth**: the sum of a member-season's `match_day` `fee_payments`. `allocate_match_days(charges, match_paid)` in `services/fees.py` walks the games oldest-first (`played_at` nullslast, then `id`), paying each in full while money lasts; the boundary game is `partial`, the rest `unpaid`, and a $0 game (rate $0 / no tier) is `na`. Money left once every game is covered = **credit** ("in the Green").
- `routers/fees.py::get_member` computes this on read and returns per-row `status` + `amount_covered` + `charge`. `_financials` now surfaces `membership_credit` / `match_fee_credit` / `credit` / `in_credit` (overpayment is **no longer clamped to 0**). Buckets are **kept separate** — match-fee credit never offsets membership owing. No tier ⇒ no credit claimed.
- Because status is derived, adding/removing a payment or editing `days_played` re-allocates automatically — **no migration, no stored flag to keep in sync**.
- **Legacy, still live**: the `paid_payment_id` column and the `mark-paid` / `unmark` / `payments/bulk` endpoints still exist and still create `match_day` payments (which feed allocation), but no longer drive the per-row display. The old per-row MARK PAID / UNMARK buttons were removed from the member page in favour of a single "Record match-fee payment" box (`RecordMatchFeeForm`). The bulk-payment page still works (it reads the derived `is_paid` and creates payments).

## BetterIQ — Opposition, Selection & Player Trends (v2.1.0, June 2026)

Best-tier analytics module (master-plan Phase 4). Gated by `require_module("iq")` + the `MANAGE_IQ` cap. Module surface mirrors BetterSelect — own `IQLayout` (violet `--pb-accent` override), dashboard tile + sidebar entry flip on automatically once `MODULE_INFO`/`MODULE_META` have `built: true`. Routes under `/admin/betteriq` (Overview + Opposition + Selection + Player trends). **NL Q&A is the one remaining phase** (still needs an LLM-provider decision — open in the spec).

**Selection & Player trends (v2.1.0)** — two more read-only surfaces, both pure reads over held data (org-scoped via grades→seasons over the `v_effective_*` views):
- `iq_selection.py` (`/iq/selection/*`) analyses a fixture's saved BetterSelect lineup (`fixture_lineups`). **It reuses BetterSelect's own pool** — `services/selection_pool.assemble_selection` (extracted v2.2.0 from `routers/selection.py`, which now delegates to it) — so eligibility (12-month recency wall, women's/men's gender wall, squad tier, per-date availability incl. period fallback) is **identical** to the selection board. Re-deriving it earlier let ghosts through (a women's player / years-dormant names appearing as promote picks for a men's 2nd XI). On top it computes XI **balance** (pace/spin, keeper, openers, all-rounders, LH/RH from `skill_positions`+`bowling_type`), last-5 **form**, **warnings** (no keeper, thin attack `<5`, plus ineligible-pick flags: wrong-grade/inactive/dormant/unavailable, out-of-form bat `<15`), **promote** (`autofill_eligible` + available + in form, never selected), **rest** (ineligible/out-of-form picks), playing up/down via the pool `tier`, and a **match-up** column (each player's record vs the fixture's opponent via `resolve_opponent` + `opp_key`). `_resolve_opp_key` prefers explicit opponent so this stays correct.
- `iq_trends.py` (`/iq/trends/*`) reuses `aggregations.get_season_by_season` / `get_career_*` / `get_upcoming_milestones_for_org` + `milestone_rules`: per-player season-by-season **trajectory**, **breakout/decline** (latest season vs prior-career baseline, min-sample gated: bat ≥5 recent / ≥10 prior inns, bowl ≥6/≥15 wkts), and **milestone forecasting**. No new tables.
- **Opponent match-to-club**: `_resolve_opp_key` now prefers an explicit `opponent` over `fixture_id` (identity from the chosen club; the fixture only supplies the grade), so the Opposition UI's "Match club" search can link an unlinked upcoming fixture to a known `opp_key`.
- **Deeper analytics (v2.3.0)** — all read-only: **Trends** add recent-form sparklines (`_player_recent`), milestone **ETA** (career per-game rate, `_eta_games`), peak season + **consistency** (σ of season avg), **role-evolution** (bat/bowl share, first vs last third), and an **"emerging"** shelf (`_emerging`). **Selection** adds `_best_available_xi` — a greedy best XI from the `autofill_eligible` pool (keeper + ≥5 bowlers enforced) diffed against the picked XI (`suggest_in`/`suggest_out`). **Opposition** adds `_venues_vs` (W/L by venue) and `_our_bowler_dominance` (our-bowler × their-batter repeat-dismissal grid from `bowler_wickets`; merged with main's parallel whole-club opposition rework).
- **Live dossier depth (v2.4.0)** — `iq_opponent.py` (main's whole-club scout) now also parses opponent **fall-of-wickets** into a partnership-by-wicket / collapse map (`season_fow` → `partnerships` + `_partnership_insight`) and a team-wide **dismissal breakdown** (`dismissal_breakdown`, summed from the per-batter `dism` counters). Frontend `KeyPlayersCard.jsx` — a Uiverse crypto-card-inspired, IQ-themed showcase — flicks through the danger batters/bowlers with a headline stat, vs-us record and a drawn recent-form sparkline.
- **Scouting synthesis (v2.5.0)** — rule-based, scorecard-derived, **no LLM** (NL Q&A stays parked). In `iq_opponent._assemble`: `_enrich_batter`/`_enrich_bowler` add a `key_note` + recommended `plan` + `risk` + `confidence` (sample-gated per the brief's §19.5) onto each danger player; `_how_they_win_lose` + `_game_plan` produce team tendencies (top-order reliance, strongest/fragile partnership, thin attack) and a "How to beat them" one-pager (`remove_early` / `see_off` / `target_bowler` / `key_warning` / `one_liner`). Surfaced via `GamePlan` + `WinLose` in `OppositionScout`, enriched on the frontend with head-to-head + best venue + our-performers from the instant report. **North-star vision doc: `docs/community-cricket-analytics-brief.md`** — the full "digital cricket analyst" roadmap. Reality filter: our data is **scorecard-level, not ball-by-ball**, so phase/ball-matchup/pressure/win-probability features (brief §1.2–1.3, §2.2–2.4, §10.1, §15.1) are out of reach; the matchup proxy that survives is `_our_bowler_dominance` (our-bowler dismissals of their batters).
- **Team self-analysis (v2.6.0)** — brief §7/§8, the opposition lens pointed at us. `iq_team.py` (`/iq/team/*`, page `TeamAnalysis.jsx` at `/admin/betteriq/team`) reconstructs **our** team score from `SUM(batting_innings.runs)` and the **opponent's** from `SUM(bowling_spells.runs)` (runs our bowlers conceded), so bat-first vs chase, "what score wins" bands and defending/chasing all come from stored per-innings data (no live fetch) — close-but-not-exact (extras we don't store are excluded). One per-game pull (`_per_game`, org-scoped via grades→seasons over `v_effective_*`), aggregated in Python into record/home-away, batting profile (top/mid/lower split via `batting_position`, boundary%), bowling, bat-first/chase win%, score-band win rates, venue records, partnership-by-wicket (`partnerships.is_club_innings`), and a `_how_we_win_lose` synthesis.
- **Player deep-dive (v2.7.0)** — brief §1.4/1.5/1.9/1.10. `iq_trends.player_deep_dive` (`GET /iq/trends/player/{id}/deep`) does ONE innings pull (runs, not_out, dismissal_type, batting_position, opp_key) and derives in Python: **starts & conversion** (reach-25 %, 25→50, 50→100, score bands), **dismissal breakdown**, **batting by position** (Opening/First-drop/Middle/Lower/Tail buckets + best position), **by-opposition** (best/worst by avg, min 2 inns) and a rule-based **scouting note** (CricViz card §16.9). Surfaced as extra cards in the `PlayerTrends` detail view (lazy-loaded alongside the trend). Dossier `DOSSIER_VERSION` bumped so the v2.5 opposition synthesis (game plan / win-lose / scouting notes) rebuilds for **every** cache key — whole-club and each team — instead of waiting on the 7-day TTL.
- **Captain's Cheat Sheet (v2.8.0)** — brief §16.6. `CheatSheet.jsx` at `/admin/betteriq/opposition/cheatsheet?opponent=…&fixture=…&team=…` — a **print-ready, light-themed one-pager** composed entirely from the existing report + dossier payloads (no new backend): game plan, danger batters/bowlers (with their plan), our bowler match-ups (`bowler_dominance` → "save X for Y"), how-they-win/lose, our edge (`our_performers`) and head-to-head + best venue. `window.print()` + a `@media print` block (hides chrome, fits A4). "Cheat sheet" button in `OppositionScout` passes the current opponent/fixture/team through the URL.
- **Danger/false-threat alerts (v2.9.0)** — brief §16.2/16.3. `_enrich_batter` now adds an `alert` (`danger` reasons: in hot form / averages big vs us; `caution`/"paper tiger" reasons: not-out-inflated average, leans on one big score, low-confidence sample, slow SR); `_enrich_bowler` flags the main threat. `DOSSIER_VERSION` → 3 so caches rebuild. Surfaced as a Danger / "Paper tiger?" badge + reason line on `KeyPlayersCard`.
- **More scorecard analytics (v2.10.0)** — **Fielding/keeping** (brief §3/§9): `iq_team._team_fielding` → top fielders, keepers, run-out specialists + fielder→bowler catching combos (from `bowler_wickets.fielder_id`), in `team_overview.fielding`. **Opposition memory** (§16.10): `iq._last_meeting` → most-recent meeting result, our/their score (`SUM(batting_innings.runs)` / `SUM(bowling_spells.runs)`), our top bat & bowler that game, in the instant report. **Selection value** (§6.2): `iq_trends.player_deep_dive` adds `selection_value` — team win% with vs without the player (`game_appearances` vs all org games) + swing.
- **All-rounder analysis (v2.10.1)** — brief §5. `iq_team._all_rounders`: players who clear both a batting-innings and a wickets floor (4/4 per season, 10/10 all-time) over the per-game `v_effective_*` tables; bat avg recomputed exactly from `batting_innings.not_out`, bowl avg from `runs_conceded/wickets`; ranked by the classic bat_avg−bowl_avg diff and role-classified (genuine / batting / bowling all-rounder). In `team_overview.all_rounders`, board on the Team page.
- **Batting partnership pairs (v2.10.2)** — brief §11.1. `iq_team._batting_pairs`: groups `partnerships` (is_club_innings) by the unordered `LEAST/GREATEST(batter1_id, batter2_id)` pair, org-scoped via games→grades→seasons; per pair → stands, total runs, avg-per-stand, best, 50+ stands, and an `opening` flag (≥half their stands at the 1st wicket). `team_overview.batting_pairs`, board on the Team page.
- **Similar player search (v2.10.3)** — brief §15.8. `iq_trends._similar_players`: club-internal nearest neighbour over a career profile (bat avg [innings-weighted from `batting_average`], bat SR, bowl avg, economy — all from `player_season_stats`), z-scored across the squad and compared only on features both players have (≥2 shared), distance→similarity `100/(1+d)`. In `player_deep_dive.similar_players`, card in the Player trends detail.
- **Club MVPs / player impact (v2.11.0)** — brief §15.3 (the scorecard-reachable subset; ball-level inputs like phase/pressure/dot-balls are out of reach). `iq_team.player_impact` (route `GET /iq/team/mvp`, optional `season_id`, defaults to latest season via `team_seasons`): per-player per-match rates over `player_season_stats` (runs, wickets, fielding dismissals) + economy (≥30 balls), z-scored across the squad (`statistics.pstdev`), blended `1.0·bat + (0.9·wkt + 0.45·inv-econ) + 0.35·field`, min-max scaled 0–100, role-tagged (Batting/Bowling/All-round/Fielding). Headline board on `BetterIQHome`, rows deep-link to `trends?player=`.
- **Matchup advantage matrix (v2.11.1)** — brief §16.5. Frontend-only reshape of the instant report's `matchups.bowler_dominance` (already a flat bowler→batter pairing list) into a heatmap grid in `OppositionScout` (`buildMatrix`/`MatchupMatrix`): top 6 our-bowlers × top 8 their-batters, cells shaded by dismissal count, Matrix/List toggle (matrix when ≥2 bowlers and ≥2 batters). No backend change.
- **Collapse analysis (v2.11.2)** — brief §7.5. `iq_team._collapses`: reconstructs fall-of-wickets per club innings from stored `partnerships` runs (keyed by `(game_id, innings_number)`, is_club_innings), finds the worst 3-consecutive-wicket span (sum of three contiguous partnership runs), flags a collapse when ≤15, and reports collapse %, worst collapse, and a start-wicket histogram ("where the wheels come off"). `team_overview.collapses`, card on the Team page.
- **Batting reliability (v2.11.3)** — brief §6.1 (scorecard-reachable subset). `iq_trends.player_deep_dive` adds `reliability` computed from the SAME innings pull (no extra query): floor/median/ceiling via `_percentile` (25th/50th/90th of the runs distribution), failure rate (dismissed <10), 20+ contribution rate, and a boom-or-bust/steady/balanced `profile` from the coefficient of variation. Card in the Player trends detail.
- **Milestone watch on home (v2.11.4)** — frontend-only. `BetterIQHome` calls `iqTrendsOverview()` and renders the top upcoming milestones (`{needed} to {target} {type}`) in a panel beside the Club MVPs; rows deep-link to `trends?player=`. No backend change.

**Two data layers** (`backend/app/services/`):
- `iq.py` — *instant* report from data we already hold: head-to-head vs an opponent (W/L/D, home/away split, recent meetings) + our players' record vs them (selection intel). Opponent identity = `COALESCE(opp_org_id, opp_club_name)` (`opp_key`), org-scoped via grades→seasons over the `v_effective_*` views — same pattern as `aggregations.get_player_by_opposition`.
- `iq_opponent.py` — *live* opponent dossier. Opponents aren't synced, but they play in grades we already track and the Grassroots `/scores/*` scorecards carry BOTH teams (sync discards the opponent half: `if pid not in our_team_pids: continue`). So we fetch the fixture's grade matches, keep the opponent (the `teams[]` entry whose `owningOrganisation.id` ≠ ours, or matched by club name), and aggregate their current-season batting/bowling/fielding per `participantId` — the mirror of sync's `our_team_pids` gate. Plus deep head-to-head: re-fetch our stored games vs them (capped) and parse the opponent cards → each opponent player annotated with their record vs us. A never-played-but-fixtured opponent is still scoutable (key the dossier on the name + fixture grade).

**Dossier cache** (`opposition_dossiers`, migration 059): built on demand in a detached `asyncio` task (its own `async_session_maker` session; tasks held in `_BUILD_TASKS` to dodge GC). `status` building→ready/error drives a frontend poll — `GET /iq/opposition/dossier` returns `{status:'building'}` until ready, then the payload. TTL 7 days + a Refresh button (`force=True`, `POST .../dossier/refresh`). Opponent player stats are NOT normalised into tables — this JSON cache is the only place live opponent data lands (keeps the data-rights surface small, no opponent-stats schema).

**Ceiling**: we hold scorecards, not ball-by-ball — so form / averages / SR / conversion / dismissal-patterns / vs-us / venue, but NO phase or ball-level matchup data. The UI says so (`coverage.notes`).

**Bounds** (CA-proxy politeness + latency): `MAX_OPP_SEASON_MATCHES=18`, `MAX_HEAD_TO_HEAD_GAMES=25`; reuses `grassroots_scores_client`'s in-process scorecard cache + semaphore(6). First build ~10–40s, then cached. Overs maths: `_overs_to_balls(10.2)=62` (10 overs + 2 balls).

## Notification Centre (v7.7.3, May 2026)

Bell icon in the AdminLayout header + drop-down panel that auto-opens on login when there's something new.

**Architecture** — no dedicated notifications table:
- `User` model gains `last_notification_seen_at TIMESTAMP` and `last_seen_app_version TEXT` (migration `029`).
- Three endpoints under `/club-admin/notifications/`:
  - `GET /count` — cheap badge poll (runs every 60s). Counts sync runs + milestones + pending sync requests since last seen. Returns `{ unseen_count, last_seen_version }`.
  - `GET /summary` — full data fetched only when the modal opens. Returns sync runs, new milestones, upcoming milestones (top 5), pending count.
  - `POST /seen` — sets `last_notification_seen_at = now()` and `last_seen_app_version = <passed version>`.
- "Since last visit" window defaults to 14 days if user has never dismissed notifications.

**Feature Changelog** (`frontend/src/data/changelog/`):
- One file per release, Vite glob-imported and sorted by `sortKey` desc in `index.js`. Each file default-exports `{ version, date, sortKey, title, items[] }`.
- `SITE_VERSION` (in `frontend/src/version.js`) is derived from `CHANGELOG[0].version` — never hand-edited. `Navbar.jsx` still re-exports it for backwards compat.
- The bell computes `newChangelogCount` (entries with version > `last_seen_version`) client-side and adds it to the backend `unseen_count` for the badge.
- Auto-open on login fires if `unseen_count > 0 || any changelog entry is newer than last_seen_version`.

**Adding a new changelog entry**: drop a single file in `frontend/src/data/changelog/`, e.g. `v1-0-5-beta.js`:
```js
export default {
  version: 'v1.0.5 Beta',
  date: '2026-05-29',
  sortKey: '2026-05-29T12:00:00Z', // any ISO string > current top entry; `new Date().toISOString()` works
  title: '...',
  items: ['...'],
}
```
Branches never touch a shared file, so parallel work merges cleanly. `index.js` re-sorts on every build — whichever PR ships latest naturally becomes `CHANGELOG[0]`.

**Open follow-ups worth investigating**:
- `deep_sync_player` (admin-triggered per-player resync via PHQ Partner API) still has a UI surface but is low value now that Grassroots covers all seasons including 25/26. Could be retired or repointed at GR. Low priority — no data pollution.
- Season-alias URL redirects: visiting `/yearbook/{alias_season_id}` still loads the alias's hidden yearbook record + alias-only stats. The stats queries auto-expand when visiting the canonical URL, but no redirect from alias URL → canonical URL exists yet. Old bookmarks to merged-away seasons are the corner case.
