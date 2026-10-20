"""BetterFantasyCricket price movement.

A player's price is DERIVED from their starting price (``base_price``) and the
rounds scored so far, never added to as a running total that a correction could
leave wrong. ``recompute_prices`` replays every scored round in order and writes
``current_price`` and ``price_change`` (the latest scored round's move). Settling,
re-settling and unsettling a round all just call it again, which is what makes a
late scorecard safe: the same rounds always give the same prices.

The rule, per round, is RELATIVE TO THE OTHER PLAYERS WHO PLAYED THAT ROUND:
  * everyone who played has a score per game and the price they started the round on;
  * the round's own scoring is used to work out what a price is worth that round: a
    straight line through the players' (price, points) pairs, steadied towards the
    scale the starting prices were built on when only a few played;
  * a player's surprise is their points minus what that line gives for their price,
    so it averages out to nothing across the round and prices cannot all drift up
    (or down) together, whatever the club's scoring runs at;
  * the move is the surprise over ``MOVE_SCALE``, rounded to 0.1 and held to
    ``MAX_MOVE``: a hundred earns the full 0.5, an ordinary good day a tenth or two,
    and double the score is worth about double the move.
A player who did not play does not move; nobody falls below ``PRICE_MIN``; a round
with fewer than ``MIN_PEERS`` players moves nobody. A price an admin typed in by hand
(``price_locked``) is never changed but still counts as a data point.

A manager's sale realises the player's CURRENT price (see ``public_fantasy``), so a
rise while owned banks the extra budget and a fall costs it.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Price band the starting prices map into; tuned so a balanced 12 fits a 100 budget
# but the premiums can't all be afforded. Heuristic, easy to retune once a club plays.
PRICE_MIN, PRICE_MAX, PRICE_FLOOR, PRICE_K = 4.0, 15.0, 4.0, 0.12

MAX_MOVE = 0.5        # the most a price moves after one round, up or down
MOVE_SCALE = 200.0    # points above (or below) what the price implies per 1.0 of price
MIN_PEERS = 6         # players who must have played for a round to move any price
SLOPE_SHRINK = 15     # how many players' worth of the starting-price scale to mix in


def peer_moves(sample: dict[str, tuple[float, float]]) -> dict[str, float]:
    """One round's moves. ``sample`` maps each player who played to
    (points per game, price at the start of the round). Returns each player's move
    (before the price floor), in steps of 0.1, held to ``MAX_MOVE``."""
    n = len(sample)
    if n < MIN_PEERS:
        return {pid: 0.0 for pid in sample}
    mean_pts = sum(v[0] for v in sample.values()) / n
    mean_price = sum(v[1] for v in sample.values()) / n
    var = sum((v[1] - mean_price) ** 2 for v in sample.values())
    prior = 1.0 / PRICE_K    # points per 1.0 of price the starting prices were built on
    if var < 1e-9:
        slope = prior
    else:
        cov = sum((v[0] - mean_pts) * (v[1] - mean_price) for v in sample.values())
        slope = (n * max(cov / var, 0.0) + SLOPE_SHRINK * prior) / (n + SLOPE_SHRINK)
    slope = min(slope, 3 * prior)
    out = {}
    for pid, (pts, price) in sample.items():
        surprise = pts - (mean_pts + slope * (price - mean_price))
        out[pid] = round(max(-MAX_MOVE, min(MAX_MOVE, surprise / MOVE_SCALE)), 1) + 0.0
    return out


def replay_season(start: dict[str, float], fixed: set[str],
                  rounds: list[tuple[int, dict[str, float]]]) -> dict[str, dict]:
    """Every player's price after the scored rounds, from their starting prices.

    ``start`` maps every pool player to the price they start on (a locked player's
    is the price they hold); ``fixed`` is the locked players, who never move;
    ``rounds`` is the scored rounds in order as (round number, {player: points per
    game}). Returns ``{player: {"price", "last", "history"}}`` where ``last`` is the
    move in the latest scored round and ``history`` is ``[(round, move, price after)]``
    for the rounds the player played."""
    price = {pid: round(float(p), 1) for pid, p in start.items()}
    hist: dict[str, list] = defaultdict(list)
    last = {pid: 0.0 for pid in price}
    for rn, scored in rounds:
        sample = {pid: (pts, price[pid]) for pid, pts in scored.items() if pid in price}
        moves = peer_moves(sample)
        last = {pid: 0.0 for pid in price}
        for pid, mv in moves.items():
            if pid in fixed:
                continue
            new = round(max(PRICE_MIN, price[pid] + mv), 1)
            last[pid] = round(new - price[pid], 1) + 0.0
            price[pid] = new
            hist[pid].append((rn, last[pid], new))
    return {pid: {"price": price[pid], "last": last[pid], "history": hist.get(pid, [])} for pid in price}


async def _load(session: AsyncSession, fs):
    """The season's pool and its scored rounds' points per game, in round order."""
    fs_id = str(fs.id)
    round_numbers = [int(r[0]) for r in (await session.execute(
        text("SELECT round_number FROM fantasy_rounds WHERE fantasy_season_id = CAST(:fs AS UUID) "
             "AND status = 'scored' ORDER BY round_number"), {"fs": fs_id})).all()]
    pool = (await session.execute(
        text("SELECT player_id, base_price, current_price, price_change, price_locked FROM fantasy_pool_players "
             "WHERE fantasy_season_id = CAST(:fs AS UUID)"), {"fs": fs_id})).all()
    by_round: dict[int, dict[str, float]] = defaultdict(dict)
    if round_numbers:
        for pid, rn, total, games in (await session.execute(
            text("""SELECT prs.player_id, r.round_number, prs.total_points, prs.games_counted
                    FROM fantasy_player_round_scores prs
                    JOIN fantasy_rounds r ON r.id = prs.round_id
                    WHERE r.fantasy_season_id = CAST(:fs AS UUID) AND r.status = 'scored'
                      AND (prs.games_counted > 0 OR prs.breakdown->>'manual' IS NOT NULL)"""),
            {"fs": fs_id})).all():
            by_round[int(rn)][str(pid)] = float(total) / max(int(games or 0), 1)
    rounds = [(rn, by_round.get(rn, {})) for rn in round_numbers]
    return rounds, pool


async def season_history(session: AsyncSession, fs) -> dict:
    """Read-only: every pool player's replayed price, latest move and per-round
    history, for the admin price movements page. Same maths as ``recompute_prices``."""
    rounds, pool = await _load(session, fs)
    start = {str(pid): (float(cur) if locked else float(base)) for pid, base, cur, _chg, locked in pool}
    fixed = {str(pid) for pid, _b, _c, _chg, locked in pool if locked}
    return {"rounds": [rn for rn, _ in rounds], "players": replay_season(start, fixed, rounds)}


async def recompute_prices(session: AsyncSession, fs, apply: bool = True) -> dict:
    """Replay the season's scored rounds into every pool player's price.

    Idempotent. Writes only the players whose price or last move changed, and
    returns ``{"rounds", "players", "changed", "moves"}`` where ``moves`` lists the
    changes (player id, before, after, last move) so a dry run can show them."""
    fs_id = str(fs.id)
    rounds, pool = await _load(session, fs)
    start = {str(pid): (float(cur) if locked else float(base)) for pid, base, cur, _chg, locked in pool}
    fixed = {str(pid) for pid, _b, _c, _chg, locked in pool if locked}
    res = replay_season(start, fixed, rounds)

    ids, prices, changes, moves = [], [], [], []
    for pid, _base, cur, chg, locked in pool:
        if locked:
            continue
        new, last = res[str(pid)]["price"], res[str(pid)]["last"]
        if abs(new - float(cur)) > 1e-6 or abs(last - float(chg)) > 1e-6:
            ids.append(str(pid)); prices.append(new); changes.append(last)
            moves.append({"player_id": str(pid), "before": float(cur), "after": new, "change": last})
    if apply and ids:
        await session.execute(
            text("""
                UPDATE fantasy_pool_players pp SET
                    current_price = ROUND(v.price::numeric, 1),
                    price_change = ROUND(v.chg::numeric, 1),
                    updated_at = NOW()
                FROM (SELECT unnest(CAST(:ids AS uuid[])) AS id,
                             unnest(CAST(:prices AS float8[])) AS price,
                             unnest(CAST(:chgs AS float8[])) AS chg) v
                WHERE pp.fantasy_season_id = CAST(:fs AS UUID) AND pp.player_id = v.id
                  AND pp.price_locked = false
            """),
            {"fs": fs_id, "ids": ids, "prices": prices, "chgs": changes},
        )
    return {"rounds": len(rounds), "players": len(pool), "changed": len(ids), "moves": moves}
