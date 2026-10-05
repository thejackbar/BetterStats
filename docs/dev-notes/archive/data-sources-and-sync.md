# Archive: data-sources-and-sync

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: Cricket Australia / PlayHQ / Play-Cricket data sources, the sync architecture, id namespaces, sync writers.
Read the distilled rules first: `docs/dev-notes/guides/data-sources-and-sync.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L7213-7271 -->
## `games.match_format` was never written, so every match was a one-dayer (v9.25.2, Aug 2026)

Reported from Applecross Accounts: grades that play two-day cricket all showed a
Fee Format of One Day, and it "used to be right". Every match day was being
charged as one day.

- **The column has no writer.** `derive_fee_format(grade.fee_format,
  game.match_format)` is correct and always was; `games.match_format` was NULL
  for every synced row, and its own fallback is "everything else (One Day,
  blank, unknown) is treated as a single day". So the bug reads as a wrong
  format rather than a missing one, which is why it looks like a settings
  problem and isn't. **Migration 033's docstring claims the sync backfills this
  ("also opportunistically backfilled during incremental syncs") — that code
  does not exist in this tree.** The docstring is the only trace of it; treat a
  migration's prose as intent, not proof, and grep for the writer.
- **The format is per FIXTURE, and a grade cannot answer it.** Applecross 5th
  Grade 2025/26 is **32 One Day and 26 Two Day** fixtures (verified live against
  `/scores/grades/{id}/matches`); 1st Grade is 39/32. So the grade-level
  `fee_format` override is NOT the fix — setting a mixed grade to `two_day`
  would double-charge its one-day half. Leave that override for what it is for:
  telling a women's grade from a men's one, and excluding a grade from fees.
- **Read from the match LIST, not the scorecard.** `get_grade_matches` already
  returns `matchType` ("One Day" / "Two Day" / "T20") and the discovery loop
  already fetches it, so this costs no extra call and also covers a fixture
  whose scorecard is never opened. `matchTypeId` (1 = Two Day, 2 = One Day) is
  there too; the string is stored because every consumer substring-parses this
  column (`fees.derive_fee_format`, `iq_team._fmt_of`) and the manual-entry form
  writes free text into it.
- **"BYE" is also a `matchType`** (48 of Colts T20's 87 entries) and is
  deliberately NOT stored — it is not a format, and every consumer would parse
  it as a one-dayer. A bye has no scorecard so it never becomes a `games` row
  anyway; the guard just keeps the column honest.
- **Setting it on `Game()` alone would have fixed almost nothing.** An
  already-synced game never reaches the per-game block (the appearances-done
  gate short-circuits it), so the write is ALSO a bulk pass beside the existing
  `is_final` one — the same reason that one exists. That is what corrects a
  club's existing season on an ordinary Sync Now.
- **`python -m app.scripts.backfill_match_format <org-id-or-slug>`** (dry-run,
  `--apply`, `--recompute`, `--season YYYY`, `--all-seasons`) is the retroactive
  half, for the seasons an incremental run no longer scans. It restricts writes
  to games under the club's OWN grades — a grade match list is competition-wide
  and names plenty of fixtures that are not ours.
- **It deliberately does NOT default to the whole history.** A club collects
  fees for the season it is in and maybe the one before, so the default scope is
  **the seasons carrying `fee_member_seasons` rows, plus the club's latest
  season** — the latter because a club setting up this season's fees has no fee
  rows in it yet. Reaching back to 2011 spends a CA call per grade correcting
  money nobody is collecting. `--all-seasons` is there for the stats side
  (StatLab / BetterIQ format filters, migration 033's original purpose), not for
  fees. **A club onboarded after this shipped needs none of it** — its games get
  the format at creation.
- **Fee rows are not edited directly** — `recompute_fee_match_days` re-derives
  them and already leaves an admin-overridden (`auto_derived=False`) or
  already-paid row alone. Nothing new was needed for that; don't reimplement it.
- **Verified against live Cricket Australia data** (7 checks over six real
  Applecross 25/26 grades through the shipped `derive_fee_format`: the bug
  reproduced from a NULL, all three formats mapping, the mixed grade proving the
  per-fixture requirement, and the women's/exclude overrides still winning).

<!-- END original CLAUDE.md L7213-7271 -->
<!-- BEGIN original CLAUDE.md L7293-7402 -->
## The scheduled sync pulls the period's results, not the club's whole history (migration 258, v9.25.0, Aug 2026)

`jobs/scheduler.py::sync_all_organisations` was `select(Organisation)` with no
WHERE and a full historical `sync_organisation` per club, at 03:00 **UTC** —
11:00 Sunday morning in WA, so a club's weekend results landed most of a day
late. Four separate problems, and the fix for each lives in
**`services/auto_sync.py`**, which is now the one place "who gets synced, and
how far back" is decided.

- **Perth, not UTC.** `PERTH` is module-level in scheduler.py and every
  club-facing job uses it. Sunday AND Monday 01:00 — same job both days, since
  each run asks the same question ("what has happened since this club's last
  sync") and doesn't need to know which day it is.
- **Eligibility reuses `auth.modules.org_core_live`** rather than inventing a
  second idea of "lapsed". That function already knows about a cancelled or
  paused Core row, an expired Core trial and the org-level master switch, and
  **it fails OPEN** for a club whose subscription rows predate the per-module
  scheme — so no long-established club is dropped by accident. Plus
  `archived_at IS NULL` and `is_active`. Skips are counted and logged by
  reason; a club quietly falling out of the sync with no trace is how you end
  up debugging "why is this club three months old" from scratch.
- **The watermark is the last run that actually PULLED MATCHES** — of
  `org_recent`/`org_full`/`org_hard_refresh`, a manual Sync Now counts, and an
  errored, cancelled or restart-interrupted run does NOT, so the next run
  automatically re-covers the gap instead of leaving a hole. A club whose last
  run failed therefore asks for fourteen days rather than seven, with no state
  to keep. `OVERLAP_HOURS = 26` is subtracted, which catches a result typed in
  hours after the last ball and makes Monday re-cover Sunday's fixtures.
- **"Successful run" is NOT the same as "pulled matches", and that gap was a
  real hole.** `sync.py` deliberately swallows a failure of the game-level
  pass so the season aggregates it already wrote are kept — which meant the
  run finished as a plain success, the watermark stepped over the period whose
  scorecards had just failed, and the club was quietly short those results
  forever. It now stamps **`match_pull_failed`** on the run's stats, and
  `auto_sync.last_sync_at` ignores a run carrying it (`_pulled_matches_ok`).
  **`ever_full` deliberately does NOT apply that filter** — "has this club's
  history ever been pulled" is about whether seasons and grades were seeded,
  and filtering it would hand a club whose game-level pass keeps failing a
  fresh full historical sync twice a week forever. For the same reason
  `plan_run` will not escalate to a full run twice: if a full run has already
  completed since the watermark and the club is still behind, it returns
  `full_sync_did_not_catch_up` and stays incremental at the `MAX_LOOKBACK_DAYS`
  cap rather than looping.
- **`kind = 'org_recent'` is deliberately NOT one of the existing kinds.**
  `org_full`/`org_hard_refresh` mean "this club's whole history has been
  pulled", which the Setup Wizard's own sync gate (`onboarding_wizard._sync_ready`),
  `wizard_analytics` and All Clubs' `_FULL_SYNC_KINDS` all read as their
  ready signal. An incremental run must not satisfy those. Same reason
  `main.py`'s restart self-heal still only resumes the two full kinds — a
  dropped incremental run needs no resume, because its watermark never moved.
- **Incremental mode is the SAME code path with a smaller input set**, never a
  different one: `since` filters the API season list through
  `auto_sync.season_in_window` (400-day span, so a straddling season or a late
  final can't be filtered out), and `sync_grassroots_game_level_data` takes
  `since` + `season_ids` to restrict the grade fan-out and drop out-of-window
  fixtures. **The grade fan-out is as much of the saving as the scorecards** —
  an established club has hundreds of grades across its seasons, each costing a
  `/scores/grades/{id}/matches` call on every run before a single scorecard.
- **Three whole-club tail passes are skipped when an incremental run added no
  games** (`_backfill_missing_season_stats`, `reconcile_imported_totals`, the
  bare `ANALYZE` that walks the whole DB). They derive from per-game data that
  by definition did not change. **Milestones are scoped, not skipped**:
  `_compute_milestones` runs a query per player, so an incremental run passes
  only the players whose season aggregates it just rewrote.
- **Nothing played in the period, nothing pulled.**
  `auto_sync.fixtures_in_window` asks the cheap question first — did this club
  play anything since its last pull — and the grade match lists it fetches are
  cached in-process, so when the answer is yes the sync that follows reuses
  them. **This is deliberately NOT a notion of "is the season over".** A club
  has an empty period for many ordinary reasons (the off-season, the Christmas
  break, a bye, a washed-out round, a team between grades) and every one has
  the same right answer. Modelling season boundaries per club and per
  competition would be more code reaching the same outcome only some of the
  time. **Every branch that returns "sync anyway" is load-bearing**: a CA
  season we don't hold yet or hold with no grades (deciding "nothing played"
  from grades we haven't created is how a club silently stops syncing the day
  its new season opens), and every grade returning an empty list
  (`get_grade_matches` returns `[]` for a transient failure and for a
  genuinely empty grade alike, so "whole card empty" is "could not tell").
  A fixture dated in the future doesn't count — it isn't a result to pull.
- **An idle check still records a successful `org_recent` run, and that is not
  bookkeeping for its own sake** — it moves the watermark. Without it a club
  that plays nothing for a stretch has its window grow every run until it
  crosses `MAX_LOOKBACK_DAYS` (90) and is handed a full historical rebuild,
  quarterly, forever, for having done nothing.
- **Historical drift is DETECTED, not blindly re-pulled** (per direct
  instruction — no periodic full sync). `services/sync_drift.py` compares CA's
  season aggregates against our stored `player_season_stats`, monthly, ~12
  seasons per club per run rotating oldest-checked-first, three calls per
  season and no scorecards. **The naive "sum the season and compare" reports
  drift on healthy clubs**, so it compares per player and only for
  participants CA itself reports: `_backfill_missing_season_stats` rows (for
  players CA omits) are ignored, and any participant caught up in a live merge
  is skipped, since the aggregate pass keeps one side's figures and drops the
  other's. CA returning nothing is `unavailable`, never drift. Surfaced as a
  banner on Data Sync with a Full Rebuild button; **acknowledging survives a
  re-check that still finds drift** (no monthly nag) and is cleared by one
  that finds the season clean.
- **Verified against a real Postgres** (77 checks: migration 258 applied three
  times and matching the lifespan mirror, every eligibility branch incl. the
  fail-open legacy club, the watermark ignoring an errored run AND a
  successful run whose match pull failed, the anti-escalation guard, the
  season and fixture filtering asserted inside the real
  `sync_grassroots_game_level_data` against stubbed CA responses, every
  empty-period probe branch incl. a mid-season break and a bye, the drift
  check's backfill/merge false-positive guards, the acknowledge semantics, and
  the scheduler choosing the right run per club) and **driven in Chromium**
  (13: the notice's copy and examples, dismiss posting to the endpoint, no
  page errors, no overflow at 390px).

<!-- END original CLAUDE.md L7293-7402 -->
<!-- BEGIN original CLAUDE.md L8075-8164 -->
## A PlayHQ game-centre link is a different id namespace (v9.18.0.2, Aug 2026)

Reported: pasting `playhq.com/.../a-grade-gatorade/game-centre/abecedd5` into
BetterPosts → Final Score got "Paste a match URL or a match ID". Both import
handlers matched a full UUID and nothing else, so a PlayHQ link was a dead end.

- **The short code is NOT a prefix of the Grassroots GUID, and nothing derives
  one from the other.** Checked against the reported match rather than assumed:
  PlayHQ `abecedd5` is Grassroots `ef9b6401-787f-4f93-b9b8-8de0316f3686`
  (D&DCC A Grade semi-final, 31 May 2026, found by walking
  org search → seasons → teams → `/scores/grades/{guid}/matches`). The grade
  short code `596e3b20` likewise has nothing to do with the grade GUID
  `f1d5d3aa-…`. **This contradicts the AFL note in `docs/afl-playhq-data-source.md`
  ("the short code IS the real gameID") — that holds for the AFL tenant's own
  discover API, not for cricket's Grassroots API.**
- **PlayHQ's public `discoverGame` GraphQL does answer for a short code**
  (`tenant: ca`, returns date/grade/round), **but do not build on it.** It sits
  behind a CloudFront WAF that started 403-ing this environment's IP after
  about three requests and never recovered — an import button a club presses
  cannot depend on that. Schema introspection is blocked too.
- **So the resolution is local**: `services/social_match_lookup.py` +
  `GET /admin/social/match-lookup`. A full UUID (a Play.Cricket link, or a
  pasted id) resolves straight through exactly as before; a PlayHQ link comes
  back as the club's own recent completed matches for the admin to pick from,
  narrowed by slugifying the grade out of the URL and matching it against our
  grade names ("A Grade (Gatorade)" → `a-grade-gatorade`, with a
  either-side-prefix fallback for a sponsor suffix one side carries). Candidate
  discovery reuses `_current_grade_rows` + `gr.get_grade_results`, the same
  machinery behind the Results roundup, so there is no second copy of "which
  matches are ours". Lookback is 240 days, not the roundup's 90 — the reported
  match was a semi-final ~10 weeks old.
- **Bug found while verifying, in the same import path**: `_get_social_scorecard_inner`
  read `result`/`venue`/`date` off `matchSummary`, which on a `/scores/*` match
  only carries `resultText` + `teams`. All three live at the TOP level
  (`raw.venue`, `raw.matchSchedule[0].startDateTime`, `matchSummary.resultText`),
  so every imported post had a blank date, a blank ground and a bare "RESULT".
  Fixed as extra fallbacks, matchSummary still tried first. `format` now reads
  `matchType` instead of hardcoding "T20" (a 50-over final was labelled T20),
  `overs` takes the longest innings bowled, and the round label only gets a
  "ROUND " prefix when the name has no letters — it used to emit
  "ROUND Round 7" and "ROUND Semi Finals".
- **Verified against live Cricket Australia data end to end**, then driven in a
  real browser (Chromium, the dev server with the API stubbed but the actual
  resolver and scorecard parser running): the reported link narrows to 10 A
  Grade matches, picking the semi-final fills 9/243 v 227 with both sides' top
  three batters and bowlers, MOTM, Kahlin Oval and 31 May; a Play.Cricket URL
  still loads with no picker; junk input reports plainly; no page errors, no
  overflow at 390px.

### A swallowed query error, reported as a greenlet crash (v9.53.5.1)

Reported off BetterPosts → Scorecard: pasting a match link returned
`Scorecard parse error: greenlet_spawn has not been called; can't call
await_only() here`.

- **THE COLUMN IS `keep_player_id`, NOT `kept_player_id`.** The merge-redirect
  map `_get_social_scorecard_inner` builds is the only SQL in the tree that
  spelled it `kept_` — every other reader (`sync.py` ×2, `sync_drift`, the undo
  log, both backfill scripts) has it right, and `merge_logs`' own DDL in the
  lifespan settles it. So the query raised `UndefinedColumnError` on EVERY
  scorecard fetch, for every club, from the day it was written.
- **THE ERROR ON SCREEN IS THE TIDY-UP, NOT THE FAULT, and that is the whole
  reason it reads as unrelated.** The failure was swallowed into a
  best-effort `except` that calls `await db.rollback()` — and **a rollback
  expires every object the session has loaded, whatever `expire_on_commit`
  says**. `club` is one of them (`get_current_club` loaded it on this same
  session), so `_org_for_team`'s first line, two hundred lines later, reads
  `club.id` on an expired instance, which is a lazy refresh, which in an async
  request is `greenlet_spawn has not been called`. The real error was in the
  log the whole time. **Same family as the `audit_logs` and `get_club` traps
  this file already documents** — an `except` that hides a database error must
  roll back, and must also hand back objects the rest of the request can read.
- **`_rollback_keeping(db, *instances)` is that rule named**: roll back, then
  `await db.refresh(...)` whatever the caller still holds. One awaited query,
  and the caller's next attribute read is not IO. Both swallowed reads in the
  scorecard builder go through it; neither calls `db.rollback()` bare any more.
- **A merged-away player now resolves again.** With the map permanently empty,
  a participant whose record had been merged fell through to whatever the feed
  spelled rather than the name the club kept — quieter than the crash, and
  fixed by the same one-word change.
- **Verified against a real Postgres** by running the SHIPPED function body
  (extracted from the router, nothing retyped) over the real Grassroots payload
  for the reported match: 16 checks — both innings on the right side, 194 each
  on a tied game, wickets, overs, twelve batters and seven bowlers a side, the
  result/grade/format/date/venue, each club's own crest and accent, our player
  matched to their id, a merged participant landing on the kept player, and the
  club still readable afterwards — plus 11 on the query and the rollback rule,
  **with a control run**: putting the old column name and the bare rollback
  back reproduces the reported greenlet error exactly.

<!-- END original CLAUDE.md L8075-8164 -->
<!-- BEGIN original CLAUDE.md L12708-12733 -->
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

<!-- END original CLAUDE.md L12708-12733 -->
<!-- BEGIN original CLAUDE.md L12734-12744 -->
## UK Expansion — Play-Cricket Data Source (Jun 2026 investigation)

UK club cricket runs on **Play-Cricket** (ECB), a **server-rendered Rails** app, one subdomain per club (`{club}.play-cricket.com`). The pages carry **no client JSON** — a browser network capture shows only telemetry (New Relic `bam.nr-data.net`, GA4 `g/collect`, OneTrust consent), never data. **Don't scrape the HTML** (brittle + terms breach). Full investigation: **`docs/uk-play-cricket-data-source.md`**.

- **The data tap is the official Play-Cricket API v2**: `https://play-cricket.com/api/v2/*.json`, **token-gated per club** (`api_token` required on every call; a club admin signs an agreement → key issued). Key endpoints: `result_summary.json?site_id=&season=` (discovery + `last_updated`), `match_detail.json?match_id=` (**full scorecard, both teams**), `matches.json` (fixtures), `league_table.json?division_id=` (ladders), `players.json`/`teams.json`. Integrator pattern = poll `result_summary`, fetch `match_detail` only when `last_updated` changes — same shape as our CA grade→matches→scorecard flow.
- **NO statistics endpoints** — *"a club can access the full scorecards of their games but we do not offer endpoints for statistics."* So unlike AU (CA aggregate API → `player_season_stats`), **the UK has scorecards only and we must compute every season aggregate ourselves** (promote the "Fix Missing Totals" rollup to primary). `match_detail` maps almost 1:1 onto our tables (`games`/`grades`/`players`/`batting_innings`/`bowling_spells`/`fielding_stats`/`bowler_wickets`/`partnerships`/FOW) — see the schema map in the doc.
- **IDs are integers, not GUIDs** — slot into the existing per-club collision scheme (raw id in `grassroots_id`, `id = uuid5(org, raw_id)` on collision). **Season** is a query param, not in the payload — derive `Season.year` from `match_date` (DD/MM/YYYY).
- **Bonus data vs AU**: `match_detail` carries **toss** (`toss`/`toss_won_by_team_id`/`batted_first`) and **extras** (byes/leg-byes/wides/no-balls/penalty) — both unavailable on CA's `/scores/*`, so UK data unlocks BetterIQ toss/captaincy analysis (brief §4) and exact score reconstruction.
- **Token scope** (technical reach ≠ contractual scope): a token authenticates *you*; the `site_id`/`match_id`/`division_id` you pass picks *whose* data. Published cross-club data *appears* broadly readable (any `site_id`/`match_id` — community-reported via `pyplaycricket`, not live-tested), but you're contractually data controller for **your own club only**. **No stats endpoint for anyone** (own or other clubs — always compute from scorecards). In-scope cross-club data = the **opponent half of your own games** (`match_detail` has both teams) → full head-to-head scouting; a **full** opponent dossier (their form vs everyone) needs the opponent's token, a **league-site token** (one token → every club in the competition, via `division_id`/`cup_id`), or partner access. **Onboarding a league is the highest-leverage in-scope unit** — restores AU-like "scout anyone in the comp". Private/unpublished fields (PII, unpublished matches) presumably own-site only — unverified without a token. **REJECTED shortcut**: reusing ONE shared club key for all English clubs (token authenticates us, `site_id` picks the data) — unverified technically, breaches the host club's agreement, single point of nationwide failure, and UK-GDPR-unlawful (processing other clubs' members — incl. children — with no lawful basis). Use league/partner tokens, never a shared club key. (Doc §6.)
- **Access policy & strategy**: API is for **clubs/leagues to export their own data**; third-party commercial use needs an ECB exception ("compelling reason … well-established customer base"). The ECB's own advice is the **BYO-token model** — *"allow clubs to add in their own API tokens for their specific data while you grow"* — then approach the helpdesk at "hundreds of clubs / thousands of users." So **Phase 1 = per-club token** (add `playcricket_api_token`+`playcricket_site_id` to the org; new token-authed `playcricket_scores_client`; no ECB relationship needed), **Phase 2 = partner access** (our AU customer base is the exception lever). Not real-time / low-traffic only; minimise retained PII (UK GDPR — we'd be a processor).

<!-- END original CLAUDE.md L12734-12744 -->
<!-- BEGIN original CLAUDE.md L12745-12779 -->
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
- **Caught-behind (caught by the keeper)** (migration 075): **CA does NOT mark the keeper in `dismissalText`** — it reads plain `"c: C Cecchi b: A Ricci"`, no dagger, no `(wk)` (an early assumption that a `†` was present was WRONG — verified against live data Jun 2026: 6597 catches, 0 daggers). The real signal is **structural**: the innings' **fielding rows carry `wicketKeeperCatches`**, so a catch is "caught behind" **iff its catcher is the fielder with `wicketKeeperCatches > 0`** (or a stumping). `sync._innings_keeper_names(inn["fielding"])` builds the keeper short-name set; `sync._caught_by_keeper(dismissalText, keeper_names)` extracts the catcher (between `c` and `b`) and matches it (apostrophe-normalised) against that set. Persists `batting_innings.caught_behind` (nullable bool, surfaced through `v_effective_batting_innings`; manual branch → NULL; kept OFF the `dismissal_type` string so the many "count caught" readers are untouched). `NULL` = unknown → readers treat it as a plain catch. The four call-sites all build `keeper_names` from the same innings' `fielding` rows: the batting insert + `_extract_bowler_wickets` (sync), `backfill_caught_behind`, `iq_opponent` (live dossier) and `games.py` (scorecard opp rows). Readers that split out a "caught behind" slice: `aggregations.get_dismissal_breakdown` (the profile "HOW I GET OUT" donut), `iq_trends.player_deep_dive` (also un-collapsed `_DISM_MAP`, which used to map `"caught behind"→"caught"`, and added the missing short-code keys `c`/`b`/`st`), `yearbooks` season breakdown, and `iq_team` team batting breakdown (`_dismissal_key`, now also short-code-aware). **Backfill history** with `python -m app.scripts.backfill_caught_behind <org_id>` (or `all` / no arg for every org — re-reads scorecards, sets the flag in place; same network cost as a Full Rebuild but only touches `batting_innings.caught_behind`; new games get it automatically on sync).
- **Caught-behind, bowling side** (migration 076): `bowler_wickets.caught_behind` (nullable bool) is the mirror — set in `_extract_bowler_wickets` via the same `_caught_by_keeper(dismissalText, keeper_names)` on the `method == "caught"` branch (keeper_names from that innings' fielding rows). Splits the "HOW I TAKE WICKETS" donut (`aggregations.get_bowling_dismissal_breakdown`), the `iq_trends.bowler_deep_dive` scouting note, `iq_team._wickets_quality` (team "how we take wickets"), and the **live opponent dossier** (`iq_opponent` matches the opponent batter's catcher against our keeper in the live scorecard; `_DISMISSAL_ADVICE["caught behind"]` now fires, `DOSSIER_VERSION` bumped to 4 so caches rebuild). `bowler_wickets` is read directly (no effective view), so no view change. **Backfill** by re-running `python -m app.scripts.rebuild_bowler_wickets <org_id|all>` (re-derives the table with the flag). Also split: `iq._our_bowler_dominance` `how` array (matchup dismissal methods) and the **match scorecard** — `games.py` returns `batting_innings.caught_behind` on each of our batters' rows and `MatchScorecard.fmtDismissal` shows "(wk)" when caught-behind isn't already daggered (our players' live-enriched text and opposition rows already carry the `†` straight from the scorecard). NOT split (deliberate, low value): StatLab's derived caught/catcher leaderboards.
- **Fielding catches vs WK catches are fully held** — `fielding_stats.catches`/`catches_wk` per-game (from the scorecard's `wicketKeeperCatches`/`totalCatches`), `player_season_stats.catches`/`catches_wk`/`catches_non_wk` per-season (from `fieldingTotalCatches`/`fieldingCatchesWK`/`fieldingCatchesNonWK`). Outfield = `catches − catches_wk`. Split is shown on PlayerProfile/Leaderboard/TeamDetail/Yearbook/PlayerComparison/ShareCard/TeamAnalysis, plus (v8.5) BetterIQ Player Trends, the shared `PlayerProfilePanel` snapshot (`players.py` now returns `season_catches_wk`), AdminManualEntries review tables, and StatLab (`catches_wk`/`catches_non_wk` metrics). Combined-only surfaces that stay combined **by design**: catches milestones, player rankings, MVP/all-rounder/dismissals composites. `player_season_grade_stats` stores combined catches only (count-only use; can't back a grade-filtered WK split).

<!-- END original CLAUDE.md L12745-12779 -->
<!-- BEGIN original CLAUDE.md L12780-12799 -->
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

<!-- END original CLAUDE.md L12780-12799 -->
<!-- BEGIN original CLAUDE.md L12820-12838 -->
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

<!-- END original CLAUDE.md L12820-12838 -->

## Quick Sync button on /admin/sync (v9.105.2)

Clubs wanted new results almost at once without a whole-history Sync Now. `POST /organisations/{id}/sync/quick` (cap `RUN_SYNC`) starts a run through `_sync_safe` with `since = today - auto_sync.QUICK_LOOKBACK_DAYS` (7), the same incremental path the scheduled sync uses. It has its own run kind, `org_quick` (`auto_sync.QUICK_KIND`), kept out of `_WATERMARK_KINDS` and `_FULL_KINDS`. Reason: a quick run only looks 7 days back, so if it moved the watermark, a club that had been silent for a month and then pressed Quick Sync would have the month hidden from every later scheduled run. It shares `_org_sync_running` with Sync Now, so the two cannot overlap. Labels added in `SyncRunCard`, `NotificationModal` and `usage._SYNC_KIND_LABEL`. Checked by `backend/verification/verify_quick_sync.py` (route body, `_sync_safe` forwarding, real `plan_run` watermark with an `org_recent` control run) and in Chromium at 390px.

## Scheduled sync skipped Leederville's Round 1: the probe judged "nothing played" from grades we held (v9.106.5.1)

Leederville played Round 1 2026/27 on Sat 3 Oct 2026 in six grades. The Sun 4 Oct and Mon 5 Oct scheduled runs both recorded `no_fixtures_in_window` ("No fixtures played since ..., nothing to pull", 4ms and 7ms). CA's grade match lists held all six fixtures, each dated 2026-10-03 with `owningOrganisation` = Leederville, so the data was never the problem.

Cause: `auto_sync.fixtures_in_window` took its grade list from OUR `grades` table for the in-play season. A season row is created the first time a sync sees it, often in the pre-season when only one team has a grade (Leederville's PSWL North-East B side, first game 11 Oct). The A to I Grade teams appear when the draw is made. The probe saw one held grade, nothing in the window, and answered "nothing played" on every run. Only the season loop in `sync_organisation` (teams feed, `_resolve_org_grade`) creates grade rows, and the probe was what gated that loop. The existing guards covered a season we do not hold and a season held with NO grades, not one held with SOME. Every idle run also records a successful `org_recent` watermark, so nothing looked wrong. `skip_reason` is stored in the run's stats but `SyncRunCard` prints the same sentence for every idle reason.

Second defect found on the way: `grassroots_scores_client._grade_matches_cache` had no expiry, so a grade's match list lived until the next deploy and was shared by the probe, the sync, BetterIQ, social rounds and fantasy. It did not cause this miss (the probe counts a fixture by date, not status) but a list cached before a draw was published, or before a fixture turned COMPLETED, would hide the round from all of them.

Fix: `fixtures_in_window` now reads the club's teams from CA for each in-play season (`_ca_grade_guids`, same `grades` plus `grade` shape `sync_organisation` seeds from, non-UUID ids skipped) and returns `sync: True, reason: new_grade_to_seed` when CA lists a grade we do not hold. An empty teams answer adds nothing and falls back to the held grades. Cost: one `get_teams` call per in-play season per club per scheduled run. The grade match list cache is now `(fetched_at, matches)` with `_GRADE_MATCHES_TTL = 1800`; `force=True` still bypasses it.

Checked by `backend/verification/verify_probe_new_grade.py` against a real Postgres with only the CA calls stubbed and Leederville's real ids. Control run on the previous commit returned `{'sync': False, 'reason': 'no_fixtures_in_window'}` for a season held with only the PSWL grade, and the two TTL checks failed; all 11 checks pass after. `verify_quick_sync` still 18 of 18.

Not fixed here: a club already in this state stays missing until a sync runs. Quick Sync (last 7 days) on the club seeds the grades and pulls the round; the next scheduled run would also do it now. Other clubs may have the same gap for this weekend: look for `org_recent` runs with `no_fixtures_in_window` since the season opened.
