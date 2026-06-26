"""BetterIQ — Teammates: who a player has shared a side with, and how they go
together.

Two read-only views over data we already hold (``game_appearances`` + results +
the per-innings tables), org-scoped via grades→seasons:

- ``teammates(player)`` — every player the focal player has been in the same XI
  with, most games together first, with the team's record over those shared
  games. The "who have I played with" list.
- ``with_split(player, teammate)`` — the focal player's own batting & bowling and
  the team's record split by whether the teammate was also in the side. The
  "does P go better with X" comparison, the Compare tool pointed at a context
  rather than a second player.

All-time (career) — a teammate list scoped to one season would mostly be the
current XI, which Selection already covers. ``game_appearances`` only ever holds
our own club's players (sync gates inserts on the team-sheet), so every pairing
here is between two of our players.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bowling_style import bowling_class, bowling_label


def _win_pct(w: int, dec: int) -> float | None:
    return round(100 * w / dec, 1) if dec else None


def _overs_str(balls: int) -> str:
    return f"{balls // 6}.{balls % 6}" if balls % 6 else f"{balls // 6}"


async def _player_name(session: AsyncSession, org_id: str, player_id: str) -> str | None:
    r = await session.execute(
        text("SELECT COALESCE(display_name_override, name) AS name FROM players WHERE id = CAST(:pid AS UUID) AND organisation_id = CAST(:org AS UUID)"),
        {"pid": player_id, "org": org_id},
    )
    return r.scalar()


async def teammates(session: AsyncSession, org_id: str, player_id: str) -> dict | None:
    """Every player the focal player has shared a game with, most games first."""
    name = await _player_name(session, org_id, player_id)
    if name is None:
        return None
    res = await session.execute(
        text(
            """
            WITH og AS (
                SELECT g.id, g.result
                FROM v_effective_games g
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org AS UUID)
            ),
            mine AS (SELECT DISTINCT game_id FROM game_appearances WHERE player_id = CAST(:pid AS UUID)),
            shared AS (SELECT og.id, og.result FROM og JOIN mine ON mine.game_id = og.id)
            SELECT ga.player_id::text AS id,
                   COALESCE(p.display_name_override, p.name) AS name,
                   p.player_role, p.bowling_action, p.bowling_type,
                   COUNT(*) AS games,
                   COUNT(*) FILTER (WHERE shared.result = 'WIN') AS wins,
                   COUNT(*) FILTER (WHERE shared.result = 'LOSS') AS losses,
                   COUNT(*) FILTER (WHERE shared.result IN ('DRAW', 'TIE')) AS draws
            FROM shared
            JOIN game_appearances ga ON ga.game_id = shared.id AND ga.player_id <> CAST(:pid AS UUID)
            JOIN players p ON p.id = ga.player_id
            GROUP BY ga.player_id, name, p.player_role, p.bowling_action, p.bowling_type
            ORDER BY games DESC, wins DESC, name
            """
        ),
        {"org": org_id, "pid": player_id},
    )
    mates = []
    for r in res.mappings():
        wins, losses, draws = int(r["wins"] or 0), int(r["losses"] or 0), int(r["draws"] or 0)
        mates.append({
            "player_id": r["id"], "name": r["name"], "role": r["player_role"],
            "bowling_style": bowling_label(r["bowling_action"], r["bowling_type"]),
            "bowling_class": bowling_class(r["bowling_type"]),
            "games": int(r["games"] or 0), "wins": wins, "losses": losses, "draws": draws,
            "win_pct": _win_pct(wins, wins + losses),
        })
    return {"player": {"player_id": player_id, "name": name}, "teammates": mates}


# Shared CTE block for the with/without split — the focal player's org games,
# each tagged with whether the teammate was also in the side.
_SPLIT_CTES = """
    WITH og AS (
        SELECT g.id, g.result
        FROM v_effective_games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = CAST(:org AS UUID)
    ),
    pg AS (SELECT DISTINCT game_id FROM game_appearances WHERE player_id = CAST(:p AS UUID)),
    xg AS (SELECT DISTINCT game_id FROM game_appearances WHERE player_id = CAST(:x AS UUID)),
    pgames AS (
        SELECT og.id, og.result, (og.id IN (SELECT game_id FROM xg)) AS with_x
        FROM og JOIN pg ON pg.game_id = og.id
    )
"""


async def with_split(session: AsyncSession, org_id: str, player_id: str, teammate_id: str) -> dict | None:
    """The focal player's batting & bowling and the team's record, split by
    whether the teammate was also in the side. All-time, this club only."""
    name_p = await _player_name(session, org_id, player_id)
    name_x = await _player_name(session, org_id, teammate_id)
    if name_p is None or name_x is None or player_id == teammate_id:
        return None
    params = {"org": org_id, "p": player_id, "x": teammate_id}

    rec = {bool(r["with_x"]): r for r in (await session.execute(
        text(_SPLIT_CTES + """
            SELECT with_x,
                   COUNT(*) AS games,
                   COUNT(*) FILTER (WHERE result = 'WIN') AS wins,
                   COUNT(*) FILTER (WHERE result = 'LOSS') AS losses,
                   COUNT(*) FILTER (WHERE result IN ('DRAW', 'TIE')) AS draws
            FROM pgames GROUP BY with_x
        """),
        params,
    )).mappings()}

    bat = {bool(r["with_x"]): r for r in (await session.execute(
        text(_SPLIT_CTES + """
            SELECT pgm.with_x,
                   COALESCE(SUM(bi.runs), 0) AS runs,
                   COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE) AS inns,
                   COUNT(*) FILTER (WHERE bi.not_out) AS not_outs,
                   COALESCE(SUM(bi.balls), 0) AS balls,
                   COALESCE(SUM(bi.fours), 0) AS fours,
                   COALESCE(SUM(bi.sixes), 0) AS sixes,
                   MAX(bi.runs) AS high
            FROM v_effective_batting_innings bi
            JOIN pgames pgm ON pgm.id = bi.game_id
            WHERE bi.player_id = CAST(:p AS UUID) AND bi.did_not_bat IS NOT TRUE
            GROUP BY pgm.with_x
        """),
        params,
    )).mappings()}

    bowl = {bool(r["with_x"]): r for r in (await session.execute(
        text(_SPLIT_CTES + """
            SELECT pgm.with_x,
                   COALESCE(SUM(bs.wickets), 0) AS wkts,
                   COALESCE(SUM(bs.runs), 0) AS conceded,
                   COALESCE(SUM((FLOOR(bs.overs) * 6 + ROUND((bs.overs - FLOOR(bs.overs)) * 10))::int), 0) AS balls
            FROM v_effective_bowling_spells bs
            JOIN pgames pgm ON pgm.id = bs.game_id
            WHERE bs.player_id = CAST(:p AS UUID) AND bs.overs IS NOT NULL
            GROUP BY pgm.with_x
        """),
        params,
    )).mappings()}

    def _side(flag: bool) -> dict:
        rc = rec.get(flag)
        b = bat.get(flag)
        bo = bowl.get(flag)
        games = int(rc["games"]) if rc else 0
        wins = int(rc["wins"]) if rc else 0
        losses = int(rc["losses"]) if rc else 0
        draws = int(rc["draws"]) if rc else 0
        runs = int(b["runs"]) if b else 0
        inns = int(b["inns"]) if b else 0
        outs = inns - (int(b["not_outs"]) if b else 0)
        bballs = int(b["balls"]) if b else 0
        wkts = int(bo["wkts"]) if bo else 0
        conceded = int(bo["conceded"]) if bo else 0
        oballs = int(bo["balls"]) if bo else 0
        return {
            "record": {
                "games": games, "wins": wins, "losses": losses, "draws": draws,
                "win_pct": _win_pct(wins, wins + losses),
            },
            "batting": {
                "innings": inns, "runs": runs,
                "average": round(runs / outs, 1) if outs > 0 else None,
                "strike_rate": round(100 * runs / bballs, 1) if bballs > 0 else None,
                "high": int(b["high"]) if (b and b["high"] is not None) else None,
                "fours": int(b["fours"]) if b else 0, "sixes": int(b["sixes"]) if b else 0,
            },
            "bowling": {
                "wickets": wkts, "runs": conceded, "overs": _overs_str(oballs),
                "average": round(conceded / wkts, 1) if wkts > 0 else None,
                "economy": round(conceded * 6 / oballs, 2) if oballs > 0 else None,
            },
        }

    return {
        "player": {"player_id": player_id, "name": name_p},
        "teammate": {"player_id": teammate_id, "name": name_x},
        "with": _side(True),
        "without": _side(False),
        "note": "All-time, this club only. 'With' is games the teammate also played; 'without' is games the player turned out and the teammate did not.",
    }
