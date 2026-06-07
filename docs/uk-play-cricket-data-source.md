# UK Expansion — Play-Cricket Data Source (Jun 2026 investigation)

How England & Wales club cricket data is published, and how BetterStats could
consume it to expand into the UK. This is the UK counterpart to the **Cricket
Australia** "Data Source Topology" section in `CLAUDE.md`.

**TL;DR**
- UK club cricket runs on **Play-Cricket** (`{club}.play-cricket.com`), an
  ECB-run, **server-rendered Rails** platform. The pages carry no rich client
  JSON — the only XHR you see in the network tab is third-party telemetry.
- The real data tap is the official **Play-Cricket API v2**
  (`https://play-cricket.com/api/v2/*.json`), **token-gated per club**.
- It exposes **full scorecards but NO statistics endpoints** — every season
  aggregate must be computed from the per-innings data.
- Access is for **clubs/leagues to export their own data**; third-party
  aggregation needs an ECB exception. **The ECB's own advice is the BYO-token
  model** (clubs paste in their own token) until you reach hundreds of clubs /
  thousands of users, then approach them for partner access.
- **Scope**: a token authenticates *you*, the `site_id`/`match_id`/`division_id`
  you pass selects *whose* data — published cross-club data *appears* broadly
  readable, but you're contractually the data controller for **your own club
  only**. The clean, in-scope cross-club data is the **opponent half of your own
  games**; a full opponent dossier needs a **league-site token** (covers every
  member club). See §4.
- This is **not** a drop-in for the Australian "open proxy, pull every club"
  pipeline — it's per-club, authenticated, and scorecard-only.

---

## 1. How play-cricket.com serves data

Play-Cricket is a **server-rendered Rails app**, one subdomain per club
(`maidenheadbray.play-cricket.com`). Scorecards and the `/player_stats/...`
pages are baked into the HTML on the server — there is **no internal client-side
JSON API** feeding the page the way Cricket Australia's Pulselive SPA does.

Consequence: a browser network capture of a Play-Cricket page shows **only
telemetry**, never data. Observed beacons (all noise for our purposes):

| Host | What it is |
|---|---|
| `bam.nr-data.net` | New Relic browser RUM (page-load timing / JS errors). The `perf={…timing…}` blob and `af=err,spa,xhr,stn,ins`. |
| `google-analytics.com/g/collect` | GA4 page-view pings (`en=page_view`). |
| `cdn-ukwest.onetrust.com/consent/….json` | OneTrust cookie-consent config. |

The only useful signal in those captures is the **page URLs in the `ref=`/`dl=`
params**, which reveal the id scheme:
- `…/website/results/494955` → a match (`match_id` 494955)
- `…/player_stats/batting/1031804` → a player record (`player_id` 1031804)

**Scraping the HTML is possible but brittle and a terms breach — don't.** The
API gives strictly more than the rendered pages.

## 2. The Play-Cricket API v2

- **Base URL**: `https://play-cricket.com/api/v2/`
- **Format**: everything is `.json`
- **Auth**: every call requires `api_token` (issued per club/league — see §4;
  not openly registerable).

| Endpoint | Key params | Returns |
|---|---|---|
| `matches.json` | `site_id`, `season` | Fixture list (upcoming + played), no result detail. **Discovery / fixtures.** |
| `result_summary.json` | `site_id`, `season` | Results + match meta + per-team points + per-innings scores + a **`last_updated`** to poll on. **Primary incremental discovery.** |
| `match_detail.json` | `match_id` | **Full scorecard** — fixture, team sheets, batting/bowling/FOW for both teams. The rich one (see §3). |
| `league_table.json` | `division_id` | League standings (→ ladders). |
| `players.json` | `site_id` | Roster + `player_id`. |
| `teams.json` / `teams_in_division.json` | `site_id` / `division_id` | Team metadata. |
| `divisions.json` / `cups.json` / `competitions.json` | league / season | Competition structure. |
| `sites.json` / `clubs.json` | search | Club → `site_id` lookup. |

**Integrator pattern** (and the ECB's recommended usage): poll
`result_summary` for the fixture list + `last_updated`, then call `match_detail`
per match **only when it has changed**. This is the same shape as our CA flow
("grade → `/scores/grades/{id}/matches` → `/scores/matches/{id}` per match"),
just per-club and token-authed.

### IDs are integers, not GUIDs
Play-Cricket ids (`match_id`, `player_id`, `competition_id`, `team_id`, …) are
integers. They slot into our existing per-club collision scheme: store the raw
id in `grassroots_id` and mint `id = uuid5(org, raw_id)` on collision, exactly
as we already do for AU players/grades/seasons.

## 3. `match_detail.json` → BetterStats schema map

The payload is a near-perfect fit for our existing tables (full field list in
the ECB's "Match Detail API" PDF; example below is abridged):

| Play-Cricket field | BetterStats target | Notes |
|---|---|---|
| `match_details[].id` / `match_id` | `games.id` | Integer → `uuid5(org, id)` per-club. |
| `competition_id` / `competition_name` | `grades` | "competition" = our grade; `league_id`/`league_name` is the parent league. |
| `match_date` (DD/MM/YYYY) | `games.played_at` + derive `Season.year` | **Season is a query param, not in the payload** — derive the year from the date (same fallback we use for CA). Note UK date format. |
| `ground_name` / `ground_id` | venue | |
| `home_team_*` / `away_team_*` / `home_club_*` / `away_club_*` | `games.home_team` / `away_team` | Both team *and* club ids — richer than CA. |
| `result` / `result_description` / `result_applied_to` | `games.result` | `match_result_types[]` enumerates the codes. |
| **`toss` / `toss_won_by_team_id` / `batted_first`** | *new column(s)* | **CA's `/scores/*` does NOT carry toss** (CLAUDE.md notes toss analysis is "out" for AU). Play-Cricket gives it → unlocks BetterIQ toss/captaincy analysis (brief §4). |
| `players[].home_team[]/away_team[]` → `player_id`, `captain`, `wicket_keeper`, `position` | `players`, `game_appearances.is_captain` | `player_id` is a person id; treat as potentially shared across clubs (reuse `grassroots_id`/uuid5). |
| `innings[]` → `runs`, `wickets`, `overs`, `declared`, `extra_byes`/`extra_leg_byes`/`extra_wides`/`extra_no_balls`/`extra_penalty_runs`, `total_extras`, `revised_target_runs`/`overs` | innings totals | **Extras ARE present** — `iq_team` notes "extras we don't store" for AU; here we can reconstruct exact scores. |
| `innings[].bat[]` → `batsman_id`, `runs`, `fours`, `sixes`, `balls`, `how_out`, `fielder_id`, `bowler_id`, `position` | `batting_innings` | `how_out` codes (`b`, `ct`, `no` = not out, plus `lbw`/`st`/`ro`/`hw`/`dnb`/`absent`) need a dismissal-code map → `dismissal_type`. Apply the same "absent/DNB aren't innings" filter we use for AU. |
| `innings[].bowl[]` → `overs` ("9.5" notation), `maidens`, `runs`, `wides`, `wickets`, `no_balls` | `bowling_spells` | Cricket-notation overs → balls, same `_overs_to_balls` (10.2 = 62). |
| `innings[].fow[]` → `runs`, `wickets`, `batsman_out_id`, `batsman_in_id`, `batsman_in_runs` | fall-of-wickets / `partnerships` | Comes with the incoming batter's score at the fall — feeds partnership reconstruction directly. |
| derived from `bat[].fielder_id` + `how_out` + `bowler_id` | `fielding_stats`, `bowler_wickets` | Same derivation we already do from CA cards. |
| `points[]` (game / penalty / bonus, incl. 2nd-innings) + `league_table.json` | ladders / `ladders.py` | League points are first-class here. |

**`match_detail` returns BOTH teams' full scorecards** — so the BetterIQ
opponent-dossier model (keep the opponent half of the card; our `our_team_pids`
gate) ports directly, and we'd own the data legitimately instead of scraping it.

Abridged example shape:
```jsonc
{ "match_details": [ {
  "id": 123456, "status": "New", "last_updated": "01/02/2018",
  "league_name": "...", "competition_name": "Division 1", "competition_id": "71400",
  "match_date": "10/06/2017", "ground_name": "...",
  "home_team_name": "3rd XI", "home_club_name": "Chingford CC",
  "away_team_name": "2nd XI", "away_club_name": "Chingford Quackers CC",
  "toss": "...won the toss and elected to bat", "batted_first": "12640",
  "result": "W", "result_applied_to": "208057",
  "points": [ { "team_id": "12640", "game_points": "0", "bonus_points_batting": "3", ... } ],
  "players": [ { "home_team": [ { "position": 1, "player_name": "...", "player_id": 3778631,
                                  "captain": false, "wicket_keeper": false }, ... ] },
               { "away_team": [ ... ] } ],
  "innings": [ {
    "team_batting_name": "Chingford CC - 3rd XI", "team_batting_id": "12640",
    "innings_number": 1, "runs": "100", "wickets": "2", "overs": "10", "declared": false,
    "bat":  [ { "position": "1", "batsman_id": "3778631", "how_out": "b",
                "bowler_id": "3778926", "runs": "30", "fours": "2", "sixes": "1", "balls": "21" }, ... ],
    "fow":  [ { "runs": "40", "wickets": 1, "batsman_out_id": "3778631",
                "batsman_in_id": "3778630", "batsman_in_runs": "10" }, ... ],
    "bowl": [ { "bowler_id": "3778926", "overs": "5", "maidens": "2",
                "runs": "50", "wides": "0", "wickets": "1", "no_balls": "0" }, ... ]
  }, ... ]
} ] }
```

## 4. Token scope — what a club token can actually see

A token authenticates **you**; the `site_id` / `match_id` / `division_id` you
pass selects **whose** data. The open-source `pyplaycricket` client confirms the
mechanism: every request is `single configured api_token` + a caller-supplied id
(`config.MATCHES_URL.format(site_id=…, api_key=self.api_key)` etc.) — there is no
per-id authorisation in the client, and its README tells you how to find
*another* club's `site_id` "if you want to return all the fixtures for another
club." So **technical reach** and **contractual scope** are two different things,
and both bind:

- **Technically**: the API serves **published** data fairly openly to any valid
  token — other clubs' rosters, fixtures, results, league tables and published
  scorecards appear reachable by passing their `site_id`/`match_id`/`division_id`.
  *(Confidence: community-reported via `pyplaycricket`, NOT tested against a live
  token. The server may reject unfamiliar `site_id`s and the ECB has been
  tightening — verify with a real token.)*
- **Contractually**: the grant is *"a club … to extract **their own** data … as
  data controllers."* You are the data controller for **your club only**. Even
  where another club's published data is fetchable, building a product on it with
  a single club's token is **outside the authorisation**, and they suspend on
  "irregular patterns." For a commercial product the contract is the binding
  constraint, not the technical reach.

Scope by data type, with **one club's** token:

| Data | Your own club | Opponent **within your games** | **Any other club** |
|---|---|---|---|
| Fixtures / results | ✅ `matches.json`/`result_summary.json?site_id=you` | ✅ same fixture | ⚠️ *appears reachable* — pass their `site_id` (published) |
| Full scorecards | ✅ `match_detail.json?match_id=` | ✅ **both teams in every card** | ⚠️ *appears reachable* if you know the `match_id` |
| Players (roster) | ✅ `sites/{site_id}/players` | ✅ team sheets in card | ⚠️ *appears reachable* — pass their `site_id` |
| **Player statistics** | ❌ **no endpoint** — compute from scorecards | ❌ compute from scorecards | ❌ **no stats endpoint for anyone** |
| Club info | ✅ `clubs.json`/teams | ✅ club ids in card | ⚠️ `clubs.json` is a cross-club **directory** (reference data) |
| Venue info | ✅ `ground_name`/`ground_id` | ✅ | ⚠️ embedded in any match you can fetch (no standalone venue endpoint) |
| League tables | ✅ `league_table.json?division_id=` | — | ✅ **inherently multi-club** — a division's table lists every club in it |

**Two hard limits that apply to everyone** (own club *and* others):
1. **No statistics endpoint at all** — you can never pull pre-computed
   player/club stats; you compute from scorecards. "View another club's player
   statistics" is therefore only possible by fetching their scorecards and
   aggregating yourself.
2. **Private/unpublished data is presumably own-site only** — member PII
   (emails/phones), unpublished matches, contact details. The published →
   private boundary is the main thing **not yet verified** without a token.

**Implication for opposition scouting (BetterIQ):**
- *Authorised, no caveats*: opponents **within your own fixtures** — `match_detail`
  carries both team sheets and both innings, so you get full head-to-head
  scouting of anyone you've played (the mirror of the AU `our_team_pids` trick,
  but here we keep both halves of *our* games).
- *A full opponent dossier* (their form across all their games, not just vs us)
  cleanly needs the **opponent's** token, a **league/competition-site token**
  (one token → every member club's fixtures/results/tables/scorecards, filtered
  by `division_id`/`cup_id`), or partner access (Phase 2). **Onboarding a whole
  league is the most powerful in-scope unit** — it restores the AU-like
  "scout anyone in the competition" capability legitimately.

## 5. Access policy (the constraints that shape strategy)

Quoting the ECB help centre (verbatim):

- **No statistics endpoints.** *"A club can access the full scorecards of their
  games but we do not offer endpoints for statistics, which remains a
  Play-Cricket only functionality."* → The `/player_stats/...` pages are **not**
  available via API; **we must compute every aggregate ourselves** from
  `match_detail`.
- **Per-club, agreement-gated.** *"If your club wishes to access the API, then a
  main admin or committee member will need to contact the help desk … to sign an
  agreement on the club's behalf and authorise access to the club's data. We can
  then issue you with a[n] API key."* Access is granted to **clubs/leagues as
  data controllers** to export **their own** data.
- **Not real-time, low-traffic.** *"The Play-Cricket API is not available for
  real-time use-cases. We are only able to support low-traffic data transfers
  such as consuming match results after play has finished, or syncing
  competitions overnight."* No explicit rate limit **yet**, but reserved; they
  ask us to **minimise data retrieved and retained "in line with UK Law"** (GDPR
  data-minimisation — we'd be a processor of named amateurs' PII).
- **Revocable.** They suspend on *"irregular or dangerous patterns of
  activity"* to prevent DoS / protect privacy.
- **No integration support.** *"The ECB is not a technology company and is unable
  to provide guidance or technical support."*
- **Commercial use needs an exception.** *"Play-Cricket is not offered to third
  parties for commercial purposes, whether for or not-for profit, apart from by
  exception where it can be proven to be in the interest of the game of cricket
  … unless there is a compelling reason (usually in the form of a
  well-established customer base)."* Cold approaches from start-ups /
  experimental / educational projects are currently declined.

## 6. Strategy — the ECB's own recommended path

The commercial-access page lays out the route explicitly:

> *"Our advice to smaller-scale products/projects would be to consider allowing
> clubs to add in their own API tokens for their specific data while you grow,
> and to reach out to us if you can achieve growth with this approach."*
>
> *"For products with hundreds of club accounts, or thousands of existing
> cricket users, please do reach out via the helpdesk."*

**Phase 1 — Bring-Your-Own-Token (now, no ECB relationship required).**
Each onboarding UK club's admin signs the Play-Cricket agreement, obtains their
`api_token`, and pastes it into BetterStats. We sync only that club's `site_id`.
This is the ECB's recommended model for a product at our stage and maps onto our
existing per-org sync. Within scope this gives full own-club data + head-to-head
opposition intel (the opponent half of our games — see §4).

**Onboarding unit — prefer leagues where possible.** A *league/competition* is
also a Play-Cricket "site" with its own token, and that token covers **every
member club** (fixtures, results, tables, scorecards, filtered by
`division_id`/`cup_id`). Onboarding a league therefore lights up many clubs at
once **and** unlocks full opposition dossiers across the whole competition — in
scope — which per-club tokens can't (they're limited to head-to-head). Where a
league will partner, it's the higher-leverage unit; per-club BYO-token is the
fallback for clubs whose league won't.

**Phase 2 — Partner access (after growth).**
At hundreds of clubs / thousands of users, approach the helpdesk for
partner-level access (one credential set, broader feed, their data-sharing
exchange). Our **established Australian customer base** is a direct fit for the
"well-established customer base" exception; Phase 1's UK club count is the
concrete growth they want to see. They also mention a future **self-service
integration platform** — track it, but it's unscheduled, so don't plan around
it.

Net: the UK can launch with **zero dependency on an ECB relationship** and
graduate into one later.

## 7. Architectural deltas vs the Australian pipeline

| | Australia (current) | UK (Play-Cricket) |
|---|---|---|
| Auth | Open `grassrootsapiproxy.cricket.com.au` (unauthenticated) | **Per-club `api_token`** |
| Discovery | Global grade sweep, all clubs | **Per-club** by `site_id` / `season` |
| Aggregates | CA aggregate API → `player_season_stats` | **None — compute from scorecards** (promote "Fix Missing Totals" rollup to primary) |
| Scorecards | `/scores/matches/{id}` | `match_detail.json?match_id=` (both teams) |
| IDs | GUIDs | Integers (still fit `grassroots_id` + uuid5) |
| Toss | Not available | **Available** (`toss`, `batted_first`) |
| Extras | Not stored | **Available** (byes/leg-byes/wides/no-balls/penalty) |
| Real-time | n/a | Explicitly disallowed; fetch post-match, cache overnight |

Concrete code shape for a Phase-1 spike (not yet built):
- Add `playcricket_api_token` + `playcricket_site_id` to the organisation.
- New `playcricket_scores_client` mirroring `grassroots_scores_client`, but
  token-authed and keyed on `site_id` / `match_id` / `division_id` (ints).
- A `match_detail` → tables parser (the §3 map) + a `how_out` → `dismissal_type`
  code map.
- An aggregate roll-up so `player_season_stats` is **derived** from
  `batting_innings` / `bowling_spells` (no aggregate feed exists).
- Reuse the `uuid5(org, raw_id)` / `grassroots_id` collision machinery unchanged.

## 8. Open questions / not yet verified

These all need a **live club token** to settle:

- **The published → private boundary.** Does a token actually return other
  clubs' published data when you pass their `site_id`/`match_id` (community
  reports yes), and exactly which fields are gated to your own site (member PII,
  unpublished matches)? This is the single most decision-relevant unknown for
  scope (§4).
- **Server-side `site_id` enforcement** — does the API reject `site_id`s your
  token "doesn't own", or only the contract restricts use?
- Exact `how_out` code vocabulary beyond the PDF sample (`b`, `ct`, `no`) —
  enumerate (`lbw`, `st`, `ro`, `hw`, `rh`, `dnb`, `absent`, …).
- Whether `player_id` is truly global across clubs (it almost certainly is, like
  CA participant ids) — confirms the collision-scheme need.
- `players.json` / `teams.json` / `clubs.json` exact field sets and whether
  `clubs.json` is a full directory or a name/county search (docs are bot-blocked).
- League-points / ladder shape from `league_table.json` for a ladders feature.
- Historical depth available per club via the API (CA reaches to 1975; unknown
  for Play-Cricket).

## Sources

- ECB Play-Cricket help centre: "Do You Have an API to Access Play-Cricket
  Data?", "Play-Cricket API: Access for commercial / non-profit projects",
  "Match Summary / Result Summary / Match Detail / Players / Teams / Clubs API".
- "Match Detail API" PDF (full scorecard field list) — ECB.
- Open-source clients (endpoint corroboration): `ewanharris12/pyplaycricket`,
  `c-m-hunt/play-cricket`, `Crickly/crickly-playcricket`.
