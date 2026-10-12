"""BetterFantasyCricket price movement.

A player's price is DERIVED from their starting price (``base_price``) and the
rounds scored so far, so it is never stored as a running total that a correction
could leave wrong. ``recompute_prices`` replays every scored round in order and
writes ``current_price`` and ``price_change`` (the latest scored round's move).
Settling, re-settling and unsettling a round all just call it again, which is what
makes a late scorecard safe: the same rounds always give the same prices.

The rule, per round a player played:
  * ``form`` = their points over the last ``FORM_ROUNDS`` rounds they played, with
    ``PRIOR_ROUNDS`` rounds at the points their starting price implies mixed in, so
    one big or small game does not swing a price on its own;
  * the price that form is worth = ``PRICE_FLOOR + form * PRICE_K`` (the same scale
    the starting price is built on);
  * the price steps ``DAMP`` of the way towards it, rounded to 0.1 and held to
    ``MAX_MOVE`` either way, never below ``PRICE_MIN``.
A player who did not play in a round does not move. A price an admin typed in by
hand (``price_locked``) is never touched.

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

MAX_MOVE = 0.5      # the most a price moves after one round, up or down
FORM_ROUNDS = 3     # played rounds that make up a player's form
PRIOR_ROUNDS = 2    # rounds of "what the starting price implies" mixed into form
DAMP = 0.5          # how far towards the form price a round moves it


def step_price(price: float, base: float, recent: list[float]) -> tuple[float, float]:
    """One round's move. ``recent`` is the points from the player's last up-to
    ``FORM_ROUNDS`` played rounds, newest last, including the round being priced.
    Returns (new price, move)."""
    expected = max(0.0, (float(base) - PRICE_FLOOR) / PRICE_K)
    form = (sum(recent) + PRIOR_ROUNDS * expected) / (len(recent) + PRIOR_ROUNDS)
    target = max(PRICE_MIN, PRICE_FLOOR + form * PRICE_K)
    move = round(max(-MAX_MOVE, min(MAX_MOVE, (target - float(price)) * DAMP)), 1)
    new = round(max(PRICE_MIN, float(price) + move), 1)
    return new, round(new - float(price), 1) + 0.0


def replay(base: float, per_round: list[float | None]) -> tuple[float, float]:
    """A player's price after the scored rounds, and the latest round's move.
    ``per_round`` has one entry per scored round in order: their points, or None
    for a round they did not play."""
    price, last, recent = round(float(base), 1), 0.0, []
    for pts in per_round:
        if pts is None:
            last = 0.0
            continue
        recent = (recent + [float(pts)])[-FORM_ROUNDS:]
        price, last = step_price(price, base, recent)
    return price, last


async def recompute_prices(session: AsyncSession, fs, apply: bool = True) -> dict:
    """Replay the season's scored rounds into every pool player's price.

    Idempotent. Writes only the players whose price or last move changed, and
    returns ``{"rounds", "players", "changed", "moves"}`` where ``moves`` lists the
    changes (name-free: player id, before, after) so a dry run can show them."""
    fs_id = str(fs.id)
    rounds = [int(r[0]) for r in (await session.execute(
        text("SELECT round_number FROM fantasy_rounds WHERE fantasy_season_id = CAST(:fs AS UUID) "
             "AND status = 'scored' ORDER BY round_number"), {"fs": fs_id})).all()]
    pool = (await session.execute(
        text("SELECT player_id, base_price, current_price, price_change FROM fantasy_pool_players "
             "WHERE fantasy_season_id = CAST(:fs AS UUID) AND price_locked = false"),
        {"fs": fs_id})).all()
    pts: dict[str, dict[int, float]] = defaultdict(dict)
    if rounds:
        for pid, rn, total in (await session.execute(
            text("""SELECT prs.player_id, r.round_number, prs.total_points
                    FROM fantasy_player_round_scores prs
                    JOIN fantasy_rounds r ON r.id = prs.round_id
                    WHERE r.fantasy_season_id = CAST(:fs AS UUID) AND r.status = 'scored'
                      AND (prs.games_counted > 0 OR prs.breakdown->>'manual' IS NOT NULL)"""),
            {"fs": fs_id})).all():
            pts[str(pid)][int(rn)] = float(total)

    ids, prices, changes, moves = [], [], [], []
    for pid, base, cur, chg in pool:
        played = pts.get(str(pid), {})
        new, last = replay(float(base), [played.get(rn) for rn in rounds])
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
