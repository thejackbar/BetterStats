"""Which Fantasy pool players have no stats, and who holds them instead.

A player added to the pool by hand ("Add new player") is a brand-new club record
with no games. When their real games are synced they land on a different record
(their own Cricket Australia id), so the hand-added one scores nothing while its
twin holds every run and wicket. This finds the pool players with no games this
season and any other club player with the same name who has games: the pair to
merge. Read only.
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def name_key(name: str | None) -> str:
    """Case, spacing and "Last, First" insensitive: the words of the name, sorted."""
    words = re.findall(r"[a-z0-9']+", (name or "").lower())
    return " ".join(sorted(words))


async def zero_stat_pool_players(db: AsyncSession, org_id) -> list[dict]:
    season = (await db.execute(text("""
        SELECT id, season_year FROM fantasy_seasons WHERE organisation_id = CAST(:o AS UUID)
        ORDER BY season_year DESC LIMIT 1"""), {"o": str(org_id)})).first()
    if season is None:
        return []
    fs_id, year = season
    game_ids = [r[0] for r in (await db.execute(text("""
        SELECT g.id FROM v_effective_games g
        JOIN grades gr ON gr.id = g.grade_id JOIN seasons s ON s.id = gr.season_id
        WHERE (g.organisation_id = CAST(:o AS UUID) OR g.home_org_id = CAST(:o AS UUID)
               OR g.away_org_id = CAST(:o AS UUID)) AND s.year = :y"""), {"o": str(org_id), "y": year})).all()]
    games: dict[str, int] = {}
    if game_ids:
        for pid, n in (await db.execute(text("""
            SELECT player_id, COUNT(DISTINCT game_id) FROM (
                SELECT player_id, game_id FROM game_appearances WHERE game_id = ANY(:g)
                UNION ALL SELECT player_id, game_id FROM v_effective_batting_innings WHERE game_id = ANY(:g)
                UNION ALL SELECT player_id, game_id FROM v_effective_bowling_spells WHERE game_id = ANY(:g)
                UNION ALL SELECT player_id, game_id FROM v_effective_fielding_stats WHERE game_id = ANY(:g)
            ) x WHERE player_id IS NOT NULL GROUP BY player_id"""), {"g": game_ids})).all():
            games[str(pid)] = int(n)
    players = (await db.execute(text("""
        SELECT p.id, p.name, pp.id IS NOT NULL AS in_pool, pp.role_source
        FROM players p LEFT JOIN fantasy_pool_players pp ON pp.player_id = p.id AND pp.fantasy_season_id = :f
        WHERE p.organisation_id = CAST(:o AS UUID) AND p.is_player IS NOT FALSE"""), {"o": str(org_id), "f": fs_id})).mappings().all()
    by_key: dict[str, list] = {}
    for p in players:
        by_key.setdefault(name_key(p["name"]), []).append(p)
    out = []
    for p in players:
        if not p["in_pool"] or games.get(str(p["id"]), 0) > 0:
            continue
        twins = [t for t in by_key.get(name_key(p["name"]), []) if t["id"] != p["id"] and games.get(str(t["id"]), 0) > 0]
        picks = (await db.execute(text(
            "SELECT COUNT(*) FROM fantasy_squad_players WHERE player_id = :p"), {"p": p["id"]})).scalar()
        out.append({
            "player_id": str(p["id"]), "name": p["name"], "added_by_hand": p["role_source"] == "admin", "picked_by": int(picks),
            "twins": [{"player_id": str(t["id"]), "name": t["name"], "games": games[str(t["id"])]} for t in twins],
        })
    out.sort(key=lambda r: (not r["twins"], -r["picked_by"], r["name"]))
    return out
