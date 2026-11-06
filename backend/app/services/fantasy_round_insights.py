"""Round insights for the Fantasy public page: the top scorers of a round, the players managers traded in and
out most, and the biggest price risers and fallers.

Read only and derived on every call, like `fantasy_round_rank`: nothing is stored, so a corrected score, an
unsettled round or a re-settle changes the answer the next time it is asked.

Scope is the club-wide salary-cap league's squads.

* Points are `fantasy_player_round_scores.total_points`, the player's own score before captaincy. `picked_by`
  is how many teams had the player in the lineup they locked for the round (the stored squad round lineup).
* Trades are the `transfer_in` / `transfer_out` rows, counted against the round the player was traded FOR (the
  round the manager will play them in). A transfer made after a round locks is queued and only becomes a row
  when the round settles, so nothing a manager has queued is visible here. A transfer taken back when a round
  was unsettled (`transfer_undone`) is not counted. Wildcard and free hit rebuilds are not transfers and are
  not counted.
* Price moves are replayed from the scored rounds (`fantasy_pricing.season_history`), the same maths as the
  nightly recompute, so a move shown here is the move that round made. A player whose price an admin typed in
  is locked and never moves.

Points, ownership and price moves exist only for a scored round; a round not yet scored shows trades so far.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import fantasy_pricing

TOP_N = 10

_NAME = "COALESCE(NULLIF(p.display_name_override, ''), p.name)"


async def round_options(db: AsyncSession, season_id) -> list[dict]:
    """The rounds that can be looked at, oldest first: every scored round, plus the round being picked for
    or played now (the first one not scored) because trades into it are already in."""
    rows = (await db.execute(
        text("""SELECT id, round_number, name, status, start_date, end_date, lock_at
                FROM fantasy_rounds WHERE fantasy_season_id = CAST(:fs AS UUID) ORDER BY round_number"""),
        {"fs": str(season_id)},
    )).mappings().all()
    out, open_taken = [], False
    for r in rows:
        if r["status"] == "scored":
            state = "scored"
        elif not open_taken:
            open_taken = True
            state = "live"
        else:
            continue
        out.append({
            "id": str(r["id"]), "number": r["round_number"], "name": r["name"], "status": state,
            "start_date": r["start_date"].isoformat() if r["start_date"] else None,
            "end_date": r["end_date"].isoformat() if r["end_date"] else None,
        })
    return out


async def _top_scorers(db: AsyncSession, round_id: str, league_id: str) -> list[dict]:
    rows = (await db.execute(
        text(f"""
            SELECT prs.player_id, {_NAME} AS pname, p.photo_url, COALESCE(pp.role, 'batter') AS role,
                   prs.total_points, prs.games_counted,
                   (SELECT COUNT(*) FROM fantasy_squad_round_scores srs
                      JOIN fantasy_squads s ON s.id = srs.squad_id AND s.league_id = CAST(:lg AS UUID)
                     WHERE srs.round_id = prs.round_id
                       AND srs.lineup @> jsonb_build_array(jsonb_build_object('player_id', prs.player_id::text))) AS picked_by
            FROM fantasy_player_round_scores prs
            JOIN players p ON p.id = prs.player_id
            JOIN fantasy_rounds r ON r.id = prs.round_id
            LEFT JOIN fantasy_pool_players pp ON pp.player_id = prs.player_id AND pp.fantasy_season_id = r.fantasy_season_id
            WHERE prs.round_id = CAST(:rid AS UUID)
              AND (prs.games_counted > 0 OR prs.breakdown->>'manual' IS NOT NULL)
            ORDER BY prs.total_points DESC, pname
            LIMIT :n
        """),
        {"rid": round_id, "lg": league_id, "n": TOP_N},
    )).mappings().all()
    return [{
        "player_id": str(r["player_id"]), "name": r["pname"], "photo_url": r["photo_url"], "role": r["role"],
        "points": float(r["total_points"]), "games": int(r["games_counted"] or 0), "picked_by": int(r["picked_by"] or 0),
    } for r in rows]


async def _traded(db: AsyncSession, round_id: str, league_id: str, kind: str) -> list[dict]:
    rows = (await db.execute(
        text(f"""
            SELECT t.player_id, {_NAME} AS pname, p.photo_url, COALESCE(pp.role, 'batter') AS role,
                   COUNT(*) AS n, pp.current_price
            FROM fantasy_transactions t
            JOIN fantasy_squads s ON s.id = t.squad_id AND s.league_id = CAST(:lg AS UUID)
            JOIN players p ON p.id = t.player_id
            JOIN fantasy_rounds r ON r.id = t.round_id
            LEFT JOIN fantasy_pool_players pp ON pp.player_id = t.player_id AND pp.fantasy_season_id = r.fantasy_season_id
            WHERE t.round_id = CAST(:rid AS UUID) AND t.type = :kind
              AND NOT EXISTS (
                  SELECT 1 FROM fantasy_transactions u
                  WHERE u.squad_id = t.squad_id AND u.type = 'transfer_undone'
                    AND t.detail->>'queued' IS NOT NULL AND u.detail->>'queued' = t.detail->>'queued'
                    AND u.created_at > t.created_at)
            GROUP BY t.player_id, {_NAME}, p.photo_url, pp.role, pp.current_price
            ORDER BY n DESC, pname
            LIMIT :n
        """),
        {"rid": round_id, "lg": league_id, "kind": kind, "n": TOP_N},
    )).mappings().all()
    return [{
        "player_id": str(r["player_id"]), "name": r["pname"], "photo_url": r["photo_url"], "role": r["role"],
        "count": int(r["n"]), "price": float(r["current_price"]) if r["current_price"] is not None else None,
    } for r in rows]


def split_moves(history: dict[str, dict], round_number: int, info: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Risers and fallers for one round from the replayed price history. ``history`` is
    ``fantasy_pricing.season_history()["players"]``; ``info`` maps player id to name, photo and role. A player
    who did not move, or is not in the pool, is left out. Biggest move first; ties on name."""
    ups, downs = [], []
    for pid, h in history.items():
        meta = info.get(pid)
        if meta is None:
            continue
        for rn, move, price in h.get("history", []):
            if rn != round_number or not move:
                continue
            row = {"player_id": pid, **meta, "move": round(float(move), 1), "price": float(price)}
            (ups if move > 0 else downs).append(row)
    ups.sort(key=lambda r: (-r["move"], r["name"].lower()))
    downs.sort(key=lambda r: (r["move"], r["name"].lower()))
    return ups[:TOP_N], downs[:TOP_N]


async def _pool_info(db: AsyncSession, season_id) -> dict[str, dict]:
    rows = (await db.execute(
        text(f"""SELECT pp.player_id, {_NAME} AS pname, p.photo_url, pp.role
                 FROM fantasy_pool_players pp JOIN players p ON p.id = pp.player_id
                 WHERE pp.fantasy_season_id = CAST(:fs AS UUID)"""),
        {"fs": str(season_id)},
    )).mappings().all()
    return {str(r["player_id"]): {"name": r["pname"], "photo_url": r["photo_url"], "role": r["role"]} for r in rows}


async def insights_for_round(db: AsyncSession, fs, league_id, rnd: dict) -> dict:
    """Everything for one round from ``round_options``. Points, ownership and price moves are empty for a
    round that is not scored yet; trades are always read."""
    rid, lg = rnd["id"], str(league_id)
    scored = rnd["status"] == "scored"
    teams = int((await db.execute(
        text("""SELECT COUNT(*) FROM fantasy_squads s
                WHERE s.league_id = CAST(:lg AS UUID) AND (s.joined_round IS NULL OR s.joined_round <= :n)"""),
        {"lg": lg, "n": rnd["number"]},
    )).scalar() or 0)
    out = {
        **rnd, "teams": teams,
        "traded_in": await _traded(db, rid, lg, "transfer_in"),
        "traded_out": await _traded(db, rid, lg, "transfer_out"),
        "top_scorers": [], "risers": [], "fallers": [],
    }
    if scored:
        out["top_scorers"] = await _top_scorers(db, rid, lg)
        hist = await fantasy_pricing.season_history(db, fs)
        out["risers"], out["fallers"] = split_moves(hist["players"], rnd["number"], await _pool_info(db, fs.id))
    return out
