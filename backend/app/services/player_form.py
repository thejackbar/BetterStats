"""A player's recent form, for the selection snapshot on the admin profile.

Last five batting innings, last five bowling spells, and the season's fielding.

Everything reads the `v_effective_*` views and the club's own games, the same
rows the public profile's innings list reads, so the snapshot cannot disagree
with it:

* a "did not bat" or "absent" row is not an innings (it used to draw a red 0);
* a hand-typed game and a paired import count, as they do everywhere else;
* a game the player played for another club does not.

"This season" is the season of the club's most recent game, read as a (year,
kind) pair (services/season_kind.py), because "latest by year then name" lands
on "Winter 2026" over "Summer 2026/27": both are year 2026 and W sorts after S.
A club that amalgamates its seasons gets the whole year.

Fielding is the higher of the scorecards we hold and CA's own season total for
that season, per figure. CA's total can run a few days behind a card we already
hold (and a card can be missing one CA counted), and neither should win by
being first.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.club_grades import club_game_sql
from app.services.season_kind import season_key_sql
from app.services.session_safety import rollback_keeping

LIMIT = 5

_NOT_AN_INNINGS = "LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')"


async def _club_org(session: AsyncSession, player_id: str):
    res = await session.execute(
        text("SELECT organisation_id FROM players WHERE id = CAST(:pid AS UUID)"),
        {"pid": player_id},
    )
    return res.scalar()


async def recent_batting(session: AsyncSession, player_id: str, club_org, limit: int = LIMIT) -> list[dict]:
    res = await session.execute(
        text(f"""
            SELECT bi.runs, bi.not_out, bi.balls, g.played_at::text AS played_at, g.id::text AS game_id
            FROM v_effective_batting_innings bi
            JOIN v_effective_games g ON g.id = bi.game_id
            WHERE bi.player_id = CAST(:pid AS UUID)
              AND bi.did_not_bat IS NOT TRUE
              AND {_NOT_AN_INNINGS}
              AND {club_game_sql('g')}
            ORDER BY g.played_at DESC NULLS LAST, bi.innings_number DESC NULLS LAST
            LIMIT :lim
        """),
        {"pid": player_id, "club_org": str(club_org) if club_org else None, "lim": limit},
    )
    return [
        {
            "runs": int(r["runs"] or 0),
            "not_out": bool(r["not_out"]),
            "balls": r["balls"],
            "date": r["played_at"],
            "game_id": r["game_id"],
        }
        for r in res.mappings()
    ]


async def recent_bowling(session: AsyncSession, player_id: str, club_org, limit: int = LIMIT) -> list[dict]:
    res = await session.execute(
        text(f"""
            SELECT bs.wickets, bs.runs, bs.overs, g.played_at::text AS played_at, g.id::text AS game_id
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id
            WHERE bs.player_id = CAST(:pid AS UUID)
              AND {club_game_sql('g')}
            ORDER BY g.played_at DESC NULLS LAST, bs.innings_number DESC NULLS LAST
            LIMIT :lim
        """),
        {"pid": player_id, "club_org": str(club_org) if club_org else None, "lim": limit},
    )
    return [
        {
            "wickets": int(r["wickets"] or 0),
            "runs": int(r["runs"] or 0),
            "overs": float(r["overs"]) if r["overs"] is not None else None,
            "date": r["played_at"],
            "game_id": r["game_id"],
        }
        for r in res.mappings()
    ]


async def season_fielding(session: AsyncSession, player_id: str, club_org) -> dict:
    """Catches (with the keeper split), run outs and stumpings in the club's current season."""
    zero = {"season_id": None, "season_name": None,
            "catches": 0, "catches_wk": 0, "run_outs": 0, "stumpings": 0}
    if not club_org:
        return zero
    amalgamate = bool((await session.execute(
        text("SELECT amalgamate_seasons FROM organisations WHERE id = CAST(:o AS UUID)"),
        {"o": str(club_org)},
    )).scalar())
    key = (lambda a: f"({a}.year * 10)") if amalgamate else (lambda a: season_key_sql(f"{a}.year", f"{a}.name"))
    params = {"pid": player_id, "club_org": str(club_org)}

    # The season of the club's newest game that has been played.
    latest = (await session.execute(
        text(f"""
            SELECT s.id::text AS season_id, s.name, s.year, {key('s')} AS skey
            FROM v_effective_games g
            JOIN seasons s ON s.id = g.season_id
            WHERE {club_game_sql('g')}
              AND g.played_at IS NOT NULL AND g.played_at <= CURRENT_DATE
            ORDER BY g.played_at DESC
            LIMIT 1
        """),
        params,
    )).mappings().first()
    if not latest:
        return zero
    params["sid"] = latest["season_id"]
    params["skey"] = latest["skey"]
    # A season with no year has no key; it stands alone.
    same_season = ("s.id = CAST(:sid AS UUID)" if latest["skey"] is None
                   else f"{key('s')} = CAST(:skey AS INTEGER)")

    held = (await session.execute(
        text(f"""
            SELECT COALESCE(SUM(fs.catches), 0) AS catches,
                   COALESCE(SUM(fs.catches_wk), 0) AS catches_wk,
                   COALESCE(SUM(fs.run_outs), 0) AS run_outs,
                   COALESCE(SUM(fs.stumpings), 0) AS stumpings
            FROM v_effective_fielding_stats fs
            JOIN v_effective_games g ON g.id = fs.game_id
            JOIN seasons s ON s.id = g.season_id
            WHERE fs.player_id = CAST(:pid AS UUID)
              AND {club_game_sql('g')}
              AND {same_season}
        """),
        params,
    )).mappings().first() or {}
    ca = (await session.execute(
        text(f"""
            SELECT COALESCE(SUM(pss.catches), 0) AS catches,
                   COALESCE(SUM(pss.catches_wk), 0) AS catches_wk,
                   COALESCE(SUM(pss.run_outs), 0) AS run_outs,
                   COALESCE(SUM(pss.stumpings), 0) AS stumpings
            FROM v_effective_player_season_stats pss
            JOIN seasons s ON s.id = pss.season_id
            WHERE pss.player_id = CAST(:pid AS UUID)
              AND s.organisation_id = CAST(:club_org AS UUID)
              AND {same_season}
        """),
        params,
    )).mappings().first() or {}

    def best(field: str) -> int:
        return max(int(held.get(field) or 0), int(ca.get(field) or 0))

    return {
        "season_id": latest["season_id"],
        "season_name": latest["name"],
        "catches": best("catches"),
        "catches_wk": best("catches_wk"),
        "run_outs": best("run_outs"),
        "stumpings": best("stumpings"),
    }


async def recent_form(session: AsyncSession, player_id: str, *keep) -> dict:
    """The three blocks, each failing on its own into an empty answer.

    `keep` are the request's loaded ORM objects: a rollback expires them, and a
    later attribute read on an expired one is lazy IO (`MissingGreenlet`)."""
    club_org = await _club_org(session, player_id)
    out: dict = {"batting": [], "bowling": [], "fielding": None}
    for key, fn in (("batting", recent_batting), ("bowling", recent_bowling)):
        try:
            out[key] = await fn(session, player_id, club_org)
        except Exception:
            await rollback_keeping(session, *keep)
            out[key] = []
    try:
        out["fielding"] = await season_fielding(session, player_id, club_org)
    except Exception:
        await rollback_keeping(session, *keep)
        out["fielding"] = None
    return out
