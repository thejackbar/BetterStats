"""BetterIQ — Teammates: who a player has shared a side with, and how they go
together.

Two read-only views over data we already hold (``game_appearances`` + results +
the per-innings tables), the games universe scoped by the canonical ownership
predicate (``_OG_CTE``, mirroring ``aggregations._club_results``):

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

# The focal games universe ("og") — canonical ownership predicate + re-derived
# result, mirroring aggregations._club_results (migrations 167/169). grades are
# LEFT JOINed and the season comes off the view's own g.season_id, so a shared
# fixture whose grade belongs to the club that synced it first, and a grade-less
# manual game, both count; the CASE re-derives WIN/LOSS against OUR home/away
# side since g.result is relative to whichever club's sync wrote it.
_OG_CTE = """
    og AS (
        SELECT g.id,
               CASE
                   WHEN g.winning_team IS NULL THEN g.result
                   WHEN g.home_org_id = CAST(:org AS UUID) AND g.winning_team = g.home_team THEN 'WIN'
                   WHEN g.home_org_id = CAST(:org AS UUID) AND g.winning_team = g.away_team THEN 'LOSS'
                   WHEN g.away_org_id = CAST(:org AS UUID) AND g.winning_team = g.away_team THEN 'WIN'
                   WHEN g.away_org_id = CAST(:org AS UUID) AND g.winning_team = g.home_team THEN 'LOSS'
                   ELSE g.result
               END AS result
        FROM v_effective_games g
        LEFT JOIN grades gr ON gr.id = g.grade_id
        LEFT JOIN seasons s ON s.id = g.season_id
        WHERE (
            g.organisation_id = CAST(:org AS UUID)
            OR g.home_org_id = CAST(:org AS UUID)
            OR g.away_org_id = CAST(:org AS UUID)
            OR s.organisation_id = CAST(:org AS UUID)
            OR EXISTS (
                SELECT 1 FROM game_appearances oga
                JOIN players op ON op.id = oga.player_id
                WHERE oga.game_id = g.id AND op.organisation_id = CAST(:org AS UUID)
            )
        )
    )
"""


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
            f"""
            WITH {_OG_CTE},
            mine AS (SELECT DISTINCT game_id FROM game_appearances WHERE player_id = CAST(:pid AS UUID)),
            shared AS (SELECT og.id, og.result FROM og JOIN mine ON mine.game_id = og.id)
            SELECT p.id::text AS id,
                   COALESCE(p.display_name_override, p.name) AS name,
                   p.player_role, p.bowling_action, p.bowling_type,
                   COUNT(*) AS games,
                   COUNT(*) FILTER (WHERE shared.result = 'WIN') AS wins,
                   COUNT(*) FILTER (WHERE shared.result = 'LOSS') AS losses,
                   COUNT(*) FILTER (WHERE shared.result IN ('DRAW', 'TIE')) AS draws
            FROM shared
            JOIN game_appearances ga ON ga.game_id = shared.id AND ga.player_id <> CAST(:pid AS UUID)
            -- Org-scope the teammate. A shared fixture between two synced clubs is
            -- one `games` row holding both sides' appearances, so without this the
            -- opposition reads as people you have played alongside.
            JOIN players p ON p.id = ga.player_id AND p.organisation_id = CAST(:org AS UUID)
            GROUP BY p.id
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


# Shared CTE block for the with/without split — the focal player's org games
# (canonical ownership universe, see _OG_CTE), each tagged with whether the
# teammate was also in the side.
_SPLIT_CTES = f"""
    WITH {_OG_CTE},
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

    # Column lists shared by the focal split and the teammate's shared-games line,
    # so one block-builder formats both.
    _BAT_COLS = """
        COALESCE(SUM(bi.runs), 0) AS runs,
        COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE) AS inns,
        COUNT(*) FILTER (WHERE bi.not_out) AS not_outs,
        COALESCE(SUM(bi.balls), 0) AS balls,
        COALESCE(SUM(bi.fours), 0) AS fours,
        COALESCE(SUM(bi.sixes), 0) AS sixes,
        MAX(bi.runs) AS high,
        COUNT(*) FILTER (WHERE bi.runs >= 50 AND bi.runs < 100) AS fifties,
        COUNT(*) FILTER (WHERE bi.runs >= 100) AS hundreds
    """
    _BOWL_COLS = """
        COALESCE(SUM(bs.wickets), 0) AS wkts,
        COALESCE(SUM(bs.runs), 0) AS conceded,
        COALESCE(SUM((FLOOR(bs.overs) * 6 + ROUND((bs.overs - FLOOR(bs.overs)) * 10))::int), 0) AS balls
    """

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
        text(_SPLIT_CTES + f"""
            SELECT pgm.with_x, {_BAT_COLS}
            FROM v_effective_batting_innings bi
            JOIN pgames pgm ON pgm.id = bi.game_id
            WHERE bi.player_id = CAST(:p AS UUID) AND bi.did_not_bat IS NOT TRUE
            GROUP BY pgm.with_x
        """),
        params,
    )).mappings()}

    bowl = {bool(r["with_x"]): r for r in (await session.execute(
        text(_SPLIT_CTES + f"""
            SELECT pgm.with_x, {_BOWL_COLS}
            FROM v_effective_bowling_spells bs
            JOIN pgames pgm ON pgm.id = bs.game_id
            WHERE bs.player_id = CAST(:p AS UUID) AND bs.overs IS NOT NULL
            GROUP BY pgm.with_x
        """),
        params,
    )).mappings()}

    # The teammate's own output over the games they shared (both played).
    tbat = (await session.execute(
        text(_SPLIT_CTES + f"""
            SELECT {_BAT_COLS}
            FROM v_effective_batting_innings bi
            JOIN pgames pgm ON pgm.id = bi.game_id AND pgm.with_x IS TRUE
            WHERE bi.player_id = CAST(:x AS UUID) AND bi.did_not_bat IS NOT TRUE
        """),
        params,
    )).mappings().first()
    tbowl = (await session.execute(
        text(_SPLIT_CTES + f"""
            SELECT {_BOWL_COLS}
            FROM v_effective_bowling_spells bs
            JOIN pgames pgm ON pgm.id = bs.game_id AND pgm.with_x IS TRUE
            WHERE bs.player_id = CAST(:x AS UUID) AND bs.overs IS NOT NULL
        """),
        params,
    )).mappings().first()

    def _bat_block(b) -> dict:
        runs = int(b["runs"]) if b else 0
        inns = int(b["inns"]) if b else 0
        no = int(b["not_outs"]) if b else 0
        outs = inns - no
        balls = int(b["balls"]) if b else 0
        return {
            "innings": inns, "runs": runs, "not_outs": no,
            "average": round(runs / outs, 1) if outs > 0 else None,
            "strike_rate": round(100 * runs / balls, 1) if balls > 0 else None,
            "high": int(b["high"]) if (b and b["high"] is not None) else None,
            "fifties": int(b["fifties"]) if b else 0, "hundreds": int(b["hundreds"]) if b else 0,
            "fours": int(b["fours"]) if b else 0, "sixes": int(b["sixes"]) if b else 0,
        }

    def _bowl_block(bo) -> dict:
        wkts = int(bo["wkts"]) if bo else 0
        conceded = int(bo["conceded"]) if bo else 0
        balls = int(bo["balls"]) if bo else 0
        return {
            "wickets": wkts, "runs": conceded, "overs": _overs_str(balls),
            "average": round(conceded / wkts, 1) if wkts > 0 else None,
            "economy": round(conceded * 6 / balls, 2) if balls > 0 else None,
            "strike_rate": round(balls / wkts, 1) if wkts > 0 else None,
        }

    def _side(flag: bool) -> dict:
        rc = rec.get(flag)
        wins = int(rc["wins"]) if rc else 0
        losses = int(rc["losses"]) if rc else 0
        return {
            "record": {
                "games": int(rc["games"]) if rc else 0,
                "wins": wins, "losses": losses, "draws": int(rc["draws"]) if rc else 0,
                "win_pct": _win_pct(wins, wins + losses),
            },
            "batting": _bat_block(bat.get(flag)),
            "bowling": _bowl_block(bowl.get(flag)),
        }

    with_side = _side(True)
    return {
        "player": {"player_id": player_id, "name": name_p},
        "teammate": {"player_id": teammate_id, "name": name_x},
        "with": with_side,
        "without": _side(False),
        # How they combine in the games they shared — both players' output.
        "together": {
            "games": with_side["record"]["games"],
            "player": {"batting": with_side["batting"], "bowling": with_side["bowling"]},
            "teammate": {"batting": _bat_block(tbat), "bowling": _bowl_block(tbowl)},
        },
        "note": "All-time, this club only. 'With' is games the teammate also played; 'without' is games the player turned out and the teammate did not.",
    }
