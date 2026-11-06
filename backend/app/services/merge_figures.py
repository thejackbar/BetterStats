"""What a player has done, counted the way the profile counts it, for the Merge Duplicates cards.

The cards used to count only Cricket Australia's season rows and the synced batting innings. A
player who exists only in a club's scorebook (a CricketStatz import, a typed card) has neither,
so both players of a pair read 0 seasons, 0 runs, 0 wickets and 0 innings beside a profile that
holds 20 matches. A person deciding "same player or not" had nothing to go on.

This reads the same `v_effective_*` views the profile does, one bound array of ids for the whole
list (`= ANY(CAST(:ids AS uuid[]))`, never a per-player probe), and adds the span of dates so
"1990 to 2008" and "1950 to 2012" can be told apart at a glance.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.game_status import appearance_counts_as_match

_PLAYED = appearance_counts_as_match("ga")


def empty_figures() -> dict:
    return {"seasons_count": 0, "total_runs": 0, "total_wickets": 0, "total_matches": 0,
            "game_level_innings": 0, "games_held": 0, "first_game": None, "last_game": None}


async def scorebook_figures(db: AsyncSession, player_ids) -> dict:
    """``{player_id: figures}`` for every id, the zero figures for a player with nothing."""
    ids = list(dict.fromkeys(str(p) for p in (player_ids or [])))
    out = {i: empty_figures() for i in ids}
    if not ids:
        return out
    params = {"ids": ids}

    for r in (await db.execute(text("""
        SELECT player_id::text AS pid,
               COUNT(DISTINCT season_id) AS seasons,
               COALESCE(SUM(runs), 0) AS runs,
               COALESCE(SUM(wickets), 0) AS wkts,
               COALESCE(SUM(matches), 0) AS matches
        FROM v_effective_player_season_stats
        WHERE player_id = ANY(CAST(:ids AS uuid[]))
        GROUP BY player_id"""), params)).mappings():
        o = out[r["pid"]]
        o["seasons_count"] = int(r["seasons"] or 0)
        o["total_runs"] = int(r["runs"] or 0)
        o["total_wickets"] = int(r["wkts"] or 0)
        o["total_matches"] = int(r["matches"] or 0)

    for r in (await db.execute(text("""
        SELECT player_id::text AS pid, COUNT(*) AS innings
        FROM v_effective_batting_innings
        WHERE player_id = ANY(CAST(:ids AS uuid[]))
        GROUP BY player_id"""), params)).mappings():
        out[r["pid"]]["game_level_innings"] = int(r["innings"] or 0)

    for r in (await db.execute(text(f"""
        WITH ap AS (
            SELECT bi.player_id, bi.game_id FROM v_effective_batting_innings bi
            WHERE bi.player_id = ANY(CAST(:ids AS uuid[]))
            UNION
            SELECT bs.player_id, bs.game_id FROM v_effective_bowling_spells bs
            WHERE bs.player_id = ANY(CAST(:ids AS uuid[]))
            UNION
            SELECT fs.player_id, fs.game_id FROM v_effective_fielding_stats fs
            WHERE fs.player_id = ANY(CAST(:ids AS uuid[]))
            UNION
            SELECT ga.player_id, ga.game_id FROM game_appearances ga
            WHERE ga.player_id = ANY(CAST(:ids AS uuid[])) AND {_PLAYED}
        )
        SELECT ap.player_id::text AS pid, COUNT(DISTINCT ap.game_id) AS games,
               MIN(g.played_at) AS first_game, MAX(g.played_at) AS last_game
        FROM ap JOIN v_effective_games g ON g.id = ap.game_id
        GROUP BY ap.player_id"""), params)).mappings():
        o = out[r["pid"]]
        o["games_held"] = int(r["games"] or 0)
        o["first_game"] = r["first_game"].isoformat() if r["first_game"] else None
        o["last_game"] = r["last_game"].isoformat() if r["last_game"] else None
    return out


async def fill_figures(db: AsyncSession, cards) -> None:
    """Overwrite the figure keys on each card dict (a player's dict may be shared by several pairs)."""
    cards = list(cards)
    figs = await scorebook_figures(db, [c["id"] for c in cards])
    for c in cards:
        c.update(figs.get(str(c["id"])) or empty_figures())
