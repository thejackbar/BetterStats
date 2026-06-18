# BetterFantasyCricket — design and build spec

Status: shipped (v8.21.x). Salary-cap, snake-draft and auction-draft modes are
all live, end to end (admin setup, the priced pool and rounds, member play,
settlement, the ladders, mini-leagues, the draft rooms, waivers and trades).

BetterFantasyCricket is a standalone module that runs an internal fantasy
cricket competition inside a single club, scored off the club's own real games.
It is the first Better module whose players are the club's own playing list and
whose "matches" are the club's own fixtures across every grade. The scoring data
already lives in BetterStats (per-innings batting, bowling, fielding and
dismissals), so the module computes fantasy points from data we hold rather than
a new feed.

This doc captures every decision taken during scoping, the data model, the
scoring and pricing maths, both game engines, and the phased build order. Keep it
in sync as the build proceeds.

## Decisions (locked during scoping)

| Area | Decision |
|------|----------|
| Module | Standalone paid module, key `fantasy`, capability `manage_fantasy`, brand cyan. Admin surface under `/admin/fantasy`, public surface under `/fantasy/:token`. |
| Audience | Members and supporters, not only players. Participants play through a public per-club link plus a self-set credential (the BetterSelect public pattern, extended so a manager does not have to be a player). |
| Engines | Both salary cap and draft, both in v1. A club can run either or both. |
| Player pool | The whole club, every included grade pooled. Admin chooses which grades count (default all). |
| Grade weighting | None. A run or wicket in 5th grade scores exactly what it does in 1st grade. Performance is all that counts. |
| Cadence | Season long with weekly rounds. Points settle after the weekly scorecard sync, not live during play. |
| Squad | 12 players: 1 keeper, 4 batters, 3 all-rounders, 4 bowlers, plus a captain. Each round scores the squad's best 11 point-getters, so the weakest or non-playing pick drops out automatically. |
| Captain | Captain scores double. The double is applied before the best 11 are chosen. A vice-captain takes over the double if the captain does not take the field. |
| Scoring | Role-weighted, format-independent. One base points table; output outside a player's specialism is multiplied (default 1.5x). |
| All-rounders / keepers | All-rounders score batting and bowling at base. Keepers get the off-role boost on keeping dismissals and on their batting. |
| Roles | Decided per player per season: start from the saved `player_role` on the profile, fall back to a stat-derived guess where it is blank, admin can override. |
| Pricing | Salary cap only. Auto baseline from a player's BetterStats history, then prices rise and fall through the season on form and ownership. |
| Transfers | FPL style: one free transfer per round, roll over up to a cap, extra transfers cost a points hit (default 4), plus chips. |
| Chips | Two wildcards (one per half-season) and a triple captain (once per half). No bench boost, since there is no bench. |
| Leagues | One club-wide ladder, plus private mini-leagues members create with a join code. |
| Draft type | Both snake and auction, the club chooses per draft league. |
| Draft event | Async timed picks: a draft window with a per-pick clock, auto-pick of the manager's top available player if the clock runs out. |
| Draft scoring | Head-to-head or total points, the club chooses per draft league. |
| Draft management | Waivers (reverse-ladder priority) plus manager-to-manager trades. |
| Registration | Join anytime. A late joiner builds a squad and scores from their first round on. |
| Prizes | Free to enter, bragging rights or club-donated prizes. No money handling, which keeps us clear of gambling and trade-promotion law. |

## The round model

A round is a club weekend. Every club game whose date falls in the round's
window scores toward that round.

- Rounds are generated from the real fixture and game calendar: games are grouped
  by weekend (default the Saturday plus Sunday window, configurable).
- A round locks at the start time of its first game. Transfers confirmed after
  the lock apply to the next round.
- A player who turns out in more than one game in a round has those points summed
  before the best-11 selection.
- A two-day game counts in the round where the match finishes, so a full scorecard
  stays in one round.
- A picked player who does not take the field that round scores 0, which is why
  the squad is 12 and only the best 11 count.

## Roles and classification

Every pickable player gets a fantasy role for the season: `keeper`, `batter`,
`allrounder` or `bowler`. The role drives squad composition, the scoring
multiplier and the price baseline, so it has to cover the bulk of a club's list.

Classification cascade (highest priority first):

1. **Admin override.** A role set by hand on the fantasy pool always wins.
2. **Saved profile.** `players.is_wicket_keeper` true gives `keeper`;
   `players.player_role` maps where it is set.
3. **Stat-derived guess.** From the player's BetterStats record, mirroring the
   existing `iq_team._all_rounders` logic: a player who clears both a batting and
   a bowling floor is an `allrounder`; otherwise whichever discipline dominates
   their output decides batter vs bowler; a keeper signal (keeper catches /
   stumpings) gives `keeper`.

`role_source` is stored (`admin` / `profile` / `auto`) so the admin screen can
show why a player landed where they did and flag the auto guesses for review.

## Scoring model

One base points table, applied to the stats we already store. Format does not
change the table. Grade does not change the table.

### Base points

Batting
- +1 per run
- +1 per four, +2 per six
- +16 on reaching 50, +32 on reaching 100 (milestone bonuses, not cumulative with each other)
- duck (dismissed for 0) −4

Bowling
- +25 per wicket
- +8 for a three-wicket haul, +16 for five wickets
- +8 per maiden over

Fielding
- +8 per catch
- +12 per stumping
- +12 per run-out

Appearance
- +4 for taking the field in the round

Captain
- captain points doubled (triple with the triple-captain chip), applied before the best 11 are chosen

All point values live in the season's scoring config (a JSONB blob seeded from
these defaults) so they can be tuned later without a migration.

### Role weighting

A player's output outside their specialism is multiplied by the off-role
multiplier (default 1.5x). On-role output is at base.

- **Batter**: batting at base, bowling boosted.
- **Bowler**: bowling at base, batting boosted.
- **All-rounder**: batting and bowling both at base (both are the job).
- **Keeper**: keeping dismissals (stumpings and wicket-keeper catches) boosted,
  batting boosted, bowling at base.

Fielding by a non-keeper, the appearance point and the captain multiplier are not
role-weighted.

### Worked examples (off-role 1.5x)

Batting/bowling component only. Each player also gets +4 for taking the field,
which is added on top and is never role-weighted.

- Specialist batter, 50 off 5 fours: 50 + 5 + 16 (fifty bonus) = **71**.
- Specialist bowler, the same 50: 71 × 1.5 = **106.5**.
- Specialist bowler, 3 wickets: 75 + 8 (haul bonus) = **83**.
- Specialist batter, the same 3 wickets: 83 × 1.5 = **124.5**.
- All-rounder doing both (50 and 3 wickets): 71 + 83 = **154**, both at base.

So a bowler's runs and a batter's wickets are worth half again as much as the
same feat by a specialist, exactly the intent. A player's round score sums their
components across every game they played in the round. A squad's round score sums
its best 11 player round scores, with the captain's score doubled before the cut.

## Pricing (salary cap only)

Each player carries a price for the season. Draft mode ignores price.

- **Baseline.** At season setup we compute each player's expected fantasy output
  per round from their BetterStats history (recent seasons weighted heavier) and
  map it onto a price band. A player with no usable history gets a role baseline.
- **Budget.** A fixed salary cap (default 100.0 credits) sized so a balanced 12
  is affordable but a manager cannot field every premium player.
- **Live movement.** After each scored round prices drift on a blend of form
  (recent points vs price) and net ownership change. Movement is capped per round
  so prices move gradually.
- **Sell-on.** When a manager sells a player they realise the purchase price plus
  part of any profit (FPL convention: half the rise, rounded), so the budget
  reflects good early buys without making trading free money.

## Salary-cap engine

- Every entrant builds one squad of 12 within the budget and the role quota.
- A club-wide ladder ranks all salary-cap squads by cumulative round points.
- Mini-leagues are private leaderboards over the same squads. A member creates one
  and shares a join code; the mini-league ranks its members' existing squads.
- Transfers: one free per round, roll over up to a cap (default 2 banked), extra
  transfers cost a points hit (default 4 each). A wildcard makes a round's
  transfers free and unlimited. Triple captain triples the captain for one round.
- Round scoring takes the best 11 of 12, captain doubled before the cut, with the
  vice-captain inheriting the double if the captain did not play.

## Draft engine

A draft league has its own pool ownership: each player is owned by one squad in
that league. The league size is capped by the pool (12 per squad, so the cap is
floor(pool / 12) teams).

- **Draft type** per league: snake (turns reverse each round) or auction (each
  manager has a draft budget and bids; highest bid wins the player).
- **Draft event**: async over a window. Each pick has a clock; if it lapses the
  system auto-picks the manager's highest-ranked still-available player (snake) or
  passes/min-bids (auction). Managers set a ranked wishlist beforehand to drive
  auto-picks.
- **Auction mechanics (as built)**: managers take turns nominating one player and
  opening the bidding. The nominator is the opening high bidder, so an uncontested
  lot is theirs and the clock can never deadlock. Others bid up; every bid resets
  the lot's anti-snipe clock so the rest get a chance to reply; the high bidder
  when it lapses wins at their bid. A manager's **max bid is held back** by the
  floor bid for each still-empty slot, so they can never strand themselves with an
  unfillable squad; role quotas are enforced as they buy. Per-manager budget is
  **derived from the lots already won** (no extra table). If a nominator's clock
  lapses, the system auto-nominates their top wishlist player, or the priciest
  still-available player in a role they still need, at the floor bid. The lot
  clock defaults to one hour (`rules["auction_lot_seconds"]`, vs the snake
  per-pick clock); the daily settle job's draft tick advances lapsed lots and
  nominations. Each settled lot is appended to `fantasy_draft_picks` (winner +
  `bid_amount`), then the shared finalisation turns every manager's lots into a
  squad (captain = priciest buy, leftover budget kept) and the league plays out on
  the same ladder/waiver/trade machinery as snake.
- **In-season**: a waiver wire for unowned and dropped players with reverse-ladder
  priority, processed once a round; plus manager-to-manager trades (propose,
  accept or reject, optional admin veto window).
- **Scoring** per league: head-to-head (each round draws two squads, higher score
  wins, win-loss-draw ladder with finals) or total points (cumulative ladder).
  Both use the same per-player round scores as the salary-cap game.

## Participation and auth

Managers are members and supporters, who do not hold BetterStats accounts. They
play through the public per-club link, extending the BetterSelect public pattern:

- The club has a `fantasy_link_token` (rotatable, pinned publicly by QR or group
  chat) that resolves the club and the open fantasy season.
- A manager self-registers once per club with a display name plus a credential
  (email optional; a PIN or passphrase they set). The credential is hashed.
- A signed HttpOnly cookie (`bs_fantasy`, JWT `{club, mgr, typ:'fantasy'}`) keeps
  them signed in, the same shape as BetterSelect's `bs_avail`.
- The public router resolves the club from the token and checks
  `org_has_module(club, "fantasy")` plus the season's open flag itself, so a
  disabled or downgraded club's link 404s.
- Failure lockout and per-IP throttling reuse `services/rate_limit.FailureTracker`,
  exactly as the BetterSelect public verify does.

The club admin (capability `manage_fantasy`) configures the season, picks the
grades, oversees pricing and roles, runs draft leagues and settles rounds from
the gated admin surface.

## Data model

New tables, all prefixed `fantasy_`. Phase 1 lands the salary-cap and shared spine
(scoring, pricing, rounds, leagues, squads); the draft mechanics tables land with
the draft phase. Every table is org-scoped and mirrored idempotently in the
`main.py` lifespan, the house pattern.

Shared spine and salary cap (phase 1 migration):

- `fantasy_seasons` — one per (org, season_year). Holds status, included grade
  ids (JSONB, null = all), the scoring config (JSONB), budget, squad size, role
  quota (JSONB), best-N, transfer rules, chip allowance, registration flag.
- `fantasy_managers` — a human entrant, per org: display name, optional email,
  credential hash, last seen.
- `fantasy_leagues` — a competition grouping: `kind`
  (`global_salary_cap` / `mini_salary_cap` / `draft`), name, join code,
  draft_type, scoring_type, settings (JSONB), created_by manager. The global
  salary-cap league is auto-created with the season.
- `fantasy_league_members` — manager ↔ league ↔ the squad ranked there.
- `fantasy_pool_players` — the pickable pool, one row per player per season: role,
  role_source, base_price, current_price, season points, owned count, last-round
  points, availability.
- `fantasy_squads` — a manager's team in a league: team name, budget remaining
  (salary cap), free transfers banked, chips used.
- `fantasy_squad_players` — current picks: player, role slot, captain / vice flag,
  purchase price, added round.
- `fantasy_rounds` — generated from the game calendar: round number, lock time,
  window, status, scored_at.
- `fantasy_round_lineups` (+ `_players`) — the per-round snapshot of a squad: the
  12 as they stood at lock, captain and vice, so scoring and history are
  reproducible after later transfers.
- `fantasy_player_round_scores` — computed points per player per round: component
  breakdown (JSONB), base, role-multiplied total, games counted. Idempotent upsert,
  recomputed on re-sync.
- `fantasy_squad_round_scores` — per squad per round: best-11 total, dropped
  player, transfers made, transfer hit, chip used.
- `fantasy_transactions` — transfer / waiver / draft-pick / trade / chip audit log.

Draft mechanics (draft phase migration):

- `fantasy_drafts` — per draft league: type, status, pick clock, order, timing.
  Auction adds (migration 089) the live-lot state: `nomination_index` (whose turn
  to nominate), `lot_player_id` / `lot_high_bid` / `lot_high_bidder_id` /
  `lot_nominator_id` / `lot_deadline` (the player up for auction, its running bid
  and anti-snipe clock) and `lot_auto` (auto-nominated by the clock).
- `fantasy_draft_picks` — pick index, manager, player, deadline, auto-picked flag,
  bid amount (auction).
- `fantasy_waiver_claims` — add/drop, priority, status, processed round.
- `fantasy_trades` — proposer / receiver squads, the offer both ways, status.
- `fantasy_h2h_fixtures` — per round draws for head-to-head draft leagues.

## Scoring pipeline and sync integration

- A service `services/fantasy_scoring.py` computes a player's fantasy points for a
  game from `batting_innings` / `bowling_spells` / `fielding_stats` /
  `bowler_wickets`, reading the org-scoped `v_effective_*` views so merges and
  adjustments are respected. It sums per-game into per-round.
- Round settlement runs after the weekly sync completes for the club, and can be
  triggered manually by the admin. It is idempotent: re-running after a re-synced
  or corrected scorecard recomputes `fantasy_player_round_scores` in place and
  re-totals affected squads.
- Pricing recompute runs in the same settle step.

## Surfaces

Member (public, link + PIN):
- Build / edit squad, transfers and chips, my team and round breakdown, the club
  ladder, mini-leagues (create, join, view), fixtures and player prices, draft
  room (async picks), waivers and trades.

Admin (gated, `manage_fantasy`):
- Enable the module and create the season, choose grades, review and override
  roles, oversee pricing, open and close registration, generate rounds, settle a
  round, create and run draft leagues, moderate trades.

Cross-feature:
- Notification bell: round scored, price changes, draft on the clock, waiver
  results, trade offers.
- BetterSocials tie-in (later): team-of-the-round and ladder share cards.

## Legal and prizes

v1 is free to enter with non-cash prizes, so there is no payment handling and no
gambling or trade-promotion exposure in AU or the UK. Paid entry as a club
fundraiser is a deliberately deferred, jurisdiction-gated follow-up and is out of
scope for v1.

## Build status

1. **Foundation** — done. Module registration, gating, brand, admin router, spec.
2. **Data model** — done. Migrations 087 (spine) and 088 (draft), ORM models,
   lifespan mirror.
3. **Scoring and pricing core** — done. `fantasy_scoring` (pure, role-weighted)
   and `fantasy_engine` (round generation, priced pool, settlement). Pure scoring
   maths verified locally.
4. **Salary-cap engine** — done. Season setup, squad build and validation,
   transfers, chips, the club ladder, mini-leagues, per-round snapshots.
5. **Public participation** — done. The `/fantasy/:token` member app (register,
   build, transfers, chips, ladder, mini-leagues).
6. **Draft engine** — done for snake and auction. Draft leagues, the async draft
   rooms (snake's auto-pick clock; auction's nominate-and-bid with budget, role
   quota, anti-snipe clock and auto-nomination), finalisation to squads,
   total-points and head-to-head ladders, waivers and trades.
7. **Automation** — done. A daily settle job and a draft tick (advances snake
   auto-picks and auction lots/nominations).

Remaining follow-ups: notifications-bell and BetterSocials share-card hooks; the
public module price in `pricing.js`; and a full verify pass on a deployed
database (the engine, drafts and member app could not be run in the build
sandbox — the auction's pure budget/nomination maths are unit-checked, but the
DB-bound bid/award/finalise flow needs a live run).

## Open defaults to confirm (non-blocking)

- Public price model for the module itself (the club-facing add-on price) — left
  out of `pricing.js` until set, so no number is invented.
- Exact budget (default 100.0), off-role multiplier (default 1.5), transfer hit
  (default 4) and milestone bonuses — all live in config and easy to tune once a
  club has played a season.
