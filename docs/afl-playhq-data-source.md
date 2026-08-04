# AFL Expansion — PlayHQ Data Source (Aug 2026 investigation)

How Australian club AFL data is published, and what's collectible for a
BetterStats AFL expansion. Investigated against a live game centre page:

`https://www.playhq.com/afl/org/southern-football-netball-league/southern-football-netball-league-2026/division-2-senior/game-centre/b4929cec`
(East Malvern Seniors 92 (14.8) def Hampton Seniors 86 (13.8), Div 2 Senior,
Round 16, SFNL, 1 Aug 2026).

**TL;DR**
- AFL club football runs on **PlayHQ** — same platform BetterStats already
  reverse-engineered for cricket (see "Data Source Topology" in `CLAUDE.md`).
  It's a client-rendered SPA (`www.playhq.com`) backed by **two public,
  unauthenticated GraphQL endpoints**.
- **`https://api.playhq.com/graphql`** (the "discover" API) — one query,
  `gameView`, returns essentially everything requested: match info, result,
  period (quarter) scores, best players, and full per-player statistics
  (including the lineup). Needs one header: `tenant: afl`.
- **`https://spectator.playhq.com/graphql`** — a second, separate public API
  for the **live play-by-play event feed** (`gameEventsSpectator`). Needs
  `X-PHQ-Tenant: afl` instead of `tenant`.
- **No API key, no login, no rate-limit push-back observed.** Both endpoints
  answered a cold curl with a browser `Origin` header and nothing else.
- The URL's short code (`b4929cec`) **is the real `gameID`** — no separate
  alias-resolution step needed (unlike cricket's PlayHQ Partner API, where the
  short game-centre code isn't the real GUID).
- Every field in the six requested screenshots (Match Information, Result,
  Period Scores, Best Players, Player Statistics, Play-by-play, Line-up) was
  reproduced byte-for-byte from these two queries against the live game.

---

## 1. How it was found

`www.playhq.com` is a Vite-built React SPA — the same shell architecture as
Cricket Australia's `play.cricket.com.au` (both are PlayHQ products). A direct
fetch of the game-centre URL returns just the SPA shell (`<div id="root">`);
the real data comes from GraphQL calls the bundle fires after load.

`GET https://www.playhq.com/config.js` (loaded before the app bundle) exposes
the environment's endpoints in plain text:

```js
window.__APP_CONFIG__ = {
  GRAPH_ENDPOINT: "https://api.playhq.com/graphql",
  SEARCH_ENDPOINT: "https://search.playhq.com/graphql",
  SPECTATOR_ENDPOINT: "https://spectator.playhq.com/graphql",
  SPECTATOR_WS_ENDPOINT: "wss://spectator.playhq.com/graphql",
  ...
};
```

The actual GraphQL query documents (field selections) are embedded as plain
template-literal strings in the built JS chunks — not minified away — so they
can be read directly out of `/assets/index.<hash>.js` and the lazy-loaded
`GameCentre.<hash>.js` / `GameView.<hash>.js` / `Innings.utils.<hash>.js`
chunks (`grep -o "query [A-Za-z]\+"` finds every operation name at a glance).
**Chunk hashes change on every PlayHQ deploy** — one was observed to roll
mid-investigation (`index.887856df.js` → `index.c837c178.js` within ~30
minutes), so a chunk filename copied from one page load can 404 (`NoSuchKey`)
minutes later; always re-fetch the current `index.html` first if a chunk
lookup goes stale.

## 2. `api.playhq.com/graphql` — the `gameView` query

One query gets match info, result, quarter-by-quarter scores, best players,
and every player's stat line, in a single round trip.

```
POST https://api.playhq.com/graphql
Content-Type: application/json
tenant: afl          <-- lowercase, matches the URL's sport slug

{
  "operationName": "gameView",
  "variables": {
    "gameId": "b4929cec",
    "gameStatisticsFilter": { "classification": "TOTAL" }
  },
  "query": "query gameView($gameId: ID!, $gameStatisticsFilter: GameStatisticsFilter!) { discoverGame(gameID: $gameId) { ... } }"
}
```

Without the `tenant` header the API 500s with `"Bolt adapter map not found in
container"` — the same opaque "Bolt adapter" error CLAUDE.md's cricket
investigation hit on `discoverGradeFixture`/`discoverTeamFixture`. There it
was read as "needs a session the website holds"; here it just needed the
tenant header — worth re-checking on the cricket endpoints too, since PlayHQ
is multi-sport and every `discoverX` query likely needs this same header
(cricket's working calls may have gotten it implicitly from a browser
session/cookie during that investigation). The header value is the tenant
enum, **lowercase** (`afl`, not `AFL` — the uppercase enum member name from
the JS bundle fails with a *different* error, `"Unable to find bolt adapter
for tenant: null"`).

### Field mapping to the six requested data types

| Requested | GraphQL path | Confirmed against the live game |
|---|---|---|
| **Match Information** | `discoverGame.round.{name,abbreviatedName}`, `.round.grade.{name,day,season.name,season.competition.name}`, `.date`, `.allocation.{time,court.name,court.venue}` | `"Round 16"` / `"Division 2 Senior"` / `"2026"` / `"Southern Football Netball League"` / `"2026-08-01"` / `"14:00:00"` / `"DW Lucas Oval (Darling Park) 1"` — exact |
| **Result** | `discoverGame.result.{winner,outcome}`, `.result.home/away.{score,statistics,gameOutcomeDescription}` | `home.score=92`, `away.score=86`, `winner.value="HOME"`, **`gameOutcomeDescription="East Malvern Seniors won by 6 points"` — the exact margin sentence, pre-written by PlayHQ, no computation needed** |
| **Period Scores** | `discoverGame.statistics.{home,away}.periods[].statistics[type.value="TOTAL_SCORE"].count`, one row per `period.value` (`FIRST_QTR`…`FOURTH_QTR`) | Home per-quarter: 12 / 29 / 37 / 14 → cumulative 12, 41, 78, 92, matching the screenshot exactly (these are **per-quarter deltas**, not running totals — sum them in order) |
| **Best Players** | `discoverGame.statistics.{home,away}.bestPlayers[] { participant, ranking }` | Home: Sam Anderson, Daniel Wigney, Isaac Morrisby, Jesse Smith. Away: Daniel Jones, Henry Grenville, Archer Grant, joshua datt, Connor Maher, Corey Smith — exact, in rank order |
| **Player Statistics** | `discoverGame.statistics.{home,away}.players[] { playerNumber, player, playerPoints, statistics[] }` — `playerPoints` = the PP column; `statistics` entries typed `1_POINT_SCORE` (behinds) / `6_POINT_SCORE` (goals) / `TOTAL_SCORE` = the G / score columns | Isaac Morrisby: `playerPoints=1`, `6_POINT_SCORE.count=6` → PP 1, G 6 — exact. Nicholas Gauci: PP 1, G 1 — exact |
| **Line-up** | Same `statistics.{home,away}.players[]` array (`playerNumber` + `player.profile.{firstName,lastName}`) | Identical 22-player roster, same order, as the Player Statistics tab — the site's "Statistics"/"Line-up" toggle is two views over one array, not two data sources. `playerPosition`/`captain`/`lineupOrder` are in the schema but were `null` for every player in this game (not populated by this competition's scorer) |
| **Play-by-play** | **Not in `gameView` at all** — see §3, a separate endpoint | n/a |

Also present in `gameView` but not asked for: full org/venue/address details,
club logos (`res.cloudinary.com` URLs, several sizes), season/competition
hierarchy, `bestPlayers.max` (how many best-player slots the comp allows),
and a `gameStatisticsConfiguration.gameStatistics` glossary (every stat type
this game type tracks, with display labels — useful for building a
type-code → human-label map without hardcoding one).

One asymmetry worth flagging: the **home** team's `bestPlayers` entries came
back as a bare `{ name: "Sam Anderson" }` with no `participant.id`, while the
**away** team's came back fully linked (`id`, `profile.id`, `firstName`,
`lastName`). Likely means the home club's best-player entries were recorded
as free-text rather than picked from a registered participant list for this
game — a data-quality variance to expect per-club, not a schema difference.

## 3. `spectator.playhq.com/graphql` — the `gameEventsSpectator` query

Play-by-play is **not** part of `gameView` — `statistics.shared` (the field
that looked like the obvious home for it) came back empty on every
`classification` value tried (`TOTAL`, `EVENT`). It's actually served by a
wholly separate public GraphQL API — the same one PlayHQ uses for its
live-scoring "ball by ball"/commentary feed (the component that renders it is
literally named `ballbyball` in the bundle's i18n keys, a naming leftover
from the cricket product this UI is shared with).

```
POST https://spectator.playhq.com/graphql
Content-Type: application/json
X-PHQ-Tenant: afl          <-- different header name AND casing from the discover API

{
  "operationName": "gameEventsSpectator",
  "variables": { "gameID": "b4929cec" },
  "query": "query gameEventsSpectator($gameID: ID!, $after: Int, $filters: EventFilter, $order: EventOrder) { game(id: $gameID) { clock { period } } gameEvents(gameID: $gameID, after: $after, filters: $filters, order: $order) { id title description visible requireReload sportEventStamp eventSection timestamp previousEventID side period ... on ScoreEvent { progressiveScore score } ... on FoulEvent { type } } }"
}
```

Returned the **entire match's event stream in one call** (52 events, no
pagination needed for this game — `after`/`previousEventID` exist for
incremental polling of a live game), each event carrying everything the
screenshot shows:

```json
{
  "title": "East Malvern Seniors",
  "description": "6. Isaac Morrisby",
  "sportEventStamp": "05:32",
  "eventSection": "4th Quarter",
  "period": "FOURTH_QTR",
  "side": "HOME",
  "progressiveScore": "85 - 49",
  "score": "Goal"
}
```

`title` = scoring team, `description` = "`{number}. {scorer name}`" (`null`
for a behind with no attributed scorer, matching the unattributed rows in the
screenshot's play-by-play list), `sportEventStamp` = the countdown clock
shown, `score` = `"Goal"`/`"Behind"`, `progressiveScore` = the running score
string exactly as displayed. Verified: every single row (times, scorers,
running score, quarter headers) matched the reported game's Play-by-play tab
exactly, home and away interleaved by `timestamp`.

The query also supports `... on FoulEvent { type }`, `... on DismissalEvent`,
`... on ExtraEvent`, `... on PositionEvent { changeDescription }`, and `... on
PeriodSummaryEvent` — the last three are cricket-specific event types on the
same shared schema (this API clearly serves every PlayHQ sport off one event
model); irrelevant for AFL but harmless to leave in the query.

## 4. What this means for a BetterStats AFL module

- **Both endpoints are open** — no `api_token`, no OAuth, no session cookie
  observed to be required for either query on this public game. This is a
  meaningfully easier starting position than the UK Play-Cricket API (token
  gated per club) and even easier than cricket's own PlayHQ Partner API
  (public key, ~3 seasons only) — closer to the AU Grassroots `/scores/*`
  cricket pattern BetterStats already leans on (open, GUID-keyed, full
  history via the discover surface).
- **Game discovery** (finding every `gameID` for a grade/round, the AFL
  equivalent of cricket's `/scores/grades/{id}/matches`) wasn't chased in
  this pass — the `gradeAllRounds`/`gradeRounds` queries seen alongside
  `gameView` in the same JS bundle are the obvious next thing to test; they
  follow the identical `discoverGrade(gradeID: ...)` shape already
  confirmed working for cricket, so a `grade_id` → round → games walk is
  very likely to just work the same way.
- **One quarter-scores gotcha to carry into any importer**: `periods[]` is
  unordered in the response (this game returned `SECOND_QTR, FIRST_QTR,
  FOURTH_QTR, THIRD_QTR`) and each entry is a **per-quarter score**, not a
  running total — sort by the known period sequence and accumulate, don't
  trust array order or assume the values are cumulative.
- **Two different tenant headers for two different services** is an easy
  trap: `tenant: afl` on `api.playhq.com`, `X-PHQ-Tenant: afl` on
  `spectator.playhq.com`. Get either wrong and the error message doesn't
  hint at the fix (`"Bolt adapter map not found"` / `null` tenant).
- **Rate limits / ToS**: not tested here beyond a handful of calls — same
  politeness posture BetterStats already applies to the Grassroots proxy
  (semaphores, caching, capped page walks) should be assumed necessary before
  any real sync job is built against this.
