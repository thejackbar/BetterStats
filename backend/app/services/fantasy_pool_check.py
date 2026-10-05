"""Which Fantasy pool players have no stats, and who holds them instead.

A player added to the pool by hand ("Add new player") is a brand-new club record
with no games and no Cricket Australia or PlayHQ id (that is what "added by hand"
means here; an admin changing a pool player's role does not make them one). When their real games are synced they land on a different record
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
    # Only games in the grades that count for this season's scoring: a twin who has
    # only played a switched-off grade would not score either.
    from app.models.db import FantasySeason
    from app.services import fantasy_engine
    grades = await fantasy_engine._grade_scope(db, await db.get(FantasySeason, fs_id))
    game_ids = [r[0] for r in (await db.execute(text(f"""
        SELECT g.id FROM v_effective_games g
        JOIN grades gr ON gr.id = g.grade_id JOIN seasons s ON s.id = gr.season_id
        WHERE (g.organisation_id = CAST(:o AS UUID) OR g.home_org_id = CAST(:o AS UUID)
               OR g.away_org_id = CAST(:o AS UUID)) AND s.year = :y{fantasy_engine._grade_clause(grades)}"""),
        {"o": str(org_id), "y": year, "grades": grades})).all()]
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
        SELECT p.id, p.name, pp.id IS NOT NULL AS in_pool,
               (p.grassroots_id IS NULL AND p.playhq_id IS NULL) AS no_ca_id
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
            "player_id": str(p["id"]), "name": p["name"], "added_by_hand": bool(p["no_ca_id"]), "picked_by": int(picks),
            "twins": [{"player_id": str(t["id"]), "name": t["name"], "games": games[str(t["id"])]} for t in twins],
        })
    out.sort(key=lambda r: (not r["twins"], -r["picked_by"], r["name"]))
    return out


async def trace_player(db: AsyncSession, org_id, term: str) -> dict:
    """Follow one player through every filter Fantasy scoring applies, so a player
    who played and is on 0 can be explained rather than guessed at. ``term`` is a
    player id, or a name (every club player whose name has all of its words, so
    both "Gardner, David" and "David Gardner" find both records). Read only.

    Per player: who they are (ids, whether they are in the pool and how many teams
    picked them, merges they were part of). Per game they have any row in: whether
    it is in the effective games view, is the club's, is in the season year, is in a
    grade that counts, falls inside a round, and has rows in the effective views for
    them. The first filter a game fails is the reason it does not count."""
    from app.models.db import FantasySeason
    from app.services import fantasy_engine

    season = (await db.execute(text("""
        SELECT id FROM fantasy_seasons WHERE organisation_id = CAST(:o AS UUID)
        ORDER BY season_year DESC LIMIT 1"""), {"o": str(org_id)})).scalar()
    if season is None:
        return {"error": "No fantasy season for this club."}
    fs = await db.get(FantasySeason, season)
    scope = await fantasy_engine._grade_scope(db, fs)
    rounds = (await db.execute(text("""
        SELECT round_number, status, start_date, end_date FROM fantasy_rounds
        WHERE fantasy_season_id = :f ORDER BY round_number"""), {"f": fs.id})).mappings().all()

    words = set(name_key(term).split())
    cands = (await db.execute(text("""
        SELECT p.id, p.name, p.grassroots_id, p.playhq_id, p.is_player, p.organisation_id
        FROM players p WHERE p.organisation_id = CAST(:o AS UUID) OR p.id::text = :t"""),
        {"o": str(org_id), "t": term.strip()})).mappings().all()
    found = [p for p in cands if str(p["id"]) == term.strip() or (words and words <= set(name_key(p["name"]).split()))]
    out = {"season_year": fs.season_year, "grade_scope": scope,
           "rounds": [{"n": r["round_number"], "status": r["status"], "start": r["start_date"], "end": r["end_date"]} for r in rounds],
           "players": []}
    for p in found:
        pid = p["id"]
        pool = (await db.execute(text("""
            SELECT role, role_source, total_points FROM fantasy_pool_players
            WHERE fantasy_season_id = :f AND player_id = :p"""), {"f": fs.id, "p": pid})).mappings().first()
        picks = (await db.execute(text("SELECT COUNT(*) FROM fantasy_squad_players WHERE player_id = :p"), {"p": pid})).scalar()
        merges = [dict(r) for r in (await db.execute(text("""
            SELECT id, merged_at, removed_player_name, keep_player_name, removed_player_id = :p AS was_removed, undone_at
            FROM merge_logs WHERE keep_player_id = :p OR removed_player_id = :p ORDER BY merged_at"""), {"p": pid})).mappings().all()]
        # Every game this record has a row in, from the EFFECTIVE views so an imported
        # or hand-typed card (manual_* tables, keyed by a manual game) is found as well
        # as a synced one, plus the raw synced tables so a row the views hide (a synced
        # game replaced by a paired import) still shows up and can be explained.
        gids = [r[0] for r in (await db.execute(text("""
            SELECT game_id FROM v_effective_batting_innings WHERE player_id = :p UNION
            SELECT game_id FROM v_effective_bowling_spells WHERE player_id = :p UNION
            SELECT game_id FROM v_effective_fielding_stats WHERE player_id = :p UNION
            SELECT game_id FROM batting_innings WHERE player_id = :p UNION
            SELECT game_id FROM bowling_spells WHERE player_id = :p UNION
            SELECT game_id FROM fielding_stats WHERE player_id = :p UNION
            SELECT game_id FROM game_appearances WHERE player_id = :p"""), {"p": pid})).all() if r[0]]
        games = []
        if gids:
            for g in (await db.execute(text("""
                SELECT e.id, e.played_at, e.home_team, e.away_team, e.grade_id, gr.name AS grade, s.year, e.source,
                       e.organisation_id AS e_org, e.home_org_id AS e_home, e.away_org_id AS e_away,
                       (SELECT COUNT(*) FROM v_effective_batting_innings x WHERE x.game_id = e.id AND x.player_id = :p) AS bat,
                       (SELECT COUNT(*) FROM v_effective_bowling_spells x WHERE x.game_id = e.id AND x.player_id = :p) AS bowl,
                       (SELECT COUNT(*) FROM v_effective_fielding_stats x WHERE x.game_id = e.id AND x.player_id = :p) AS field
                FROM v_effective_games e
                LEFT JOIN grades gr ON gr.id = e.grade_id
                LEFT JOIN seasons s ON s.id = COALESCE(gr.season_id, e.season_id)
                WHERE e.id = ANY(CAST(:g AS uuid[])) ORDER BY e.played_at"""), {"p": pid, "g": [str(x) for x in gids]})).mappings().all():
                o = str(org_id)
                verdict = "counts"
                day = g["played_at"].date() if hasattr(g["played_at"], "date") else g["played_at"]
                rnd = next((r["round_number"] for r in rounds if r["start_date"] and r["end_date"] and r["start_date"] <= day <= r["end_date"]), None)
                if g["year"] != fs.season_year:
                    verdict = f"season year {g['year']}, not {fs.season_year}"
                elif not (str(g["e_org"]) == o or str(g["e_home"]) == o or str(g["e_away"]) == o):
                    verdict = "the game is not the club's (own fixture or one of the two sides)"
                elif scope is not None and str(g["grade_id"]) not in scope:
                    verdict = f"grade '{g['grade']}' is switched off or not in the included grades"
                elif rnd is None:
                    verdict = "no round covers this date"
                elif not (g["bat"] or g["bowl"] or g["field"]):
                    verdict = "only an appearance row: counts the appearance point, no batting, bowling or fielding rows in the effective views"
                games.append({"date": day, "match": f"{g['home_team']} v {g['away_team']}", "grade": g["grade"], "year": g["year"],
                              "round": rnd, "source": g["source"], "game_id": str(g["id"]),
                              "rows": f"bat {g['bat']}, bowl {g['bowl']}, field {g['field']}", "verdict": verdict})
            # A synced game the effective games view does not show: say why. The usual
            # reason is a paired import that is preferred (its rows count instead, under
            # whichever record the import named), or a washed-out game.
            shown = {g["game_id"] for g in games}
            for g in (await db.execute(text("""
                SELECT g.id, g.played_at, g.home_team, g.away_team, gr.name AS grade, s.year, g.status,
                       (SELECT mg.id FROM manual_games mg WHERE mg.superseded_by_game_id = g.id AND mg.pair_prefers_import LIMIT 1) AS import_id
                FROM games g LEFT JOIN grades gr ON gr.id = g.grade_id LEFT JOIN seasons s ON s.id = gr.season_id
                WHERE g.id = ANY(CAST(:g AS uuid[])) ORDER BY g.played_at"""), {"g": [str(x) for x in gids]})).mappings().all():
                if str(g["id"]) in shown:
                    continue
                day = g["played_at"].date() if hasattr(g["played_at"], "date") else g["played_at"]
                why = (f"hidden from scoring: an imported match ({g['import_id']}) is paired to this game and preferred, so the import's rows count instead"
                       if g["import_id"] else f"not in v_effective_games (status {g['status']}: washed out, or not played)")
                games.append({"date": day, "match": f"{g['home_team']} v {g['away_team']}", "grade": g["grade"], "year": g["year"],
                              "round": None, "source": "api", "game_id": str(g["id"]), "rows": "synced rows hidden", "verdict": why})
            games.sort(key=lambda x: x["date"])
        stored = [dict(r) for r in (await db.execute(text("""
            SELECT r.round_number, prs.total_points, prs.breakdown->>'manual' IS NOT NULL AS manual
            FROM fantasy_player_round_scores prs JOIN fantasy_rounds r ON r.id = prs.round_id
            WHERE prs.player_id = :p AND prs.fantasy_season_id = :f ORDER BY r.round_number"""), {"p": pid, "f": fs.id})).mappings().all()]
        out["players"].append({
            "id": str(pid), "name": p["name"], "grassroots_id": p["grassroots_id"], "playhq_id": p["playhq_id"],
            "is_player": p["is_player"], "in_pool": pool is not None, "pool": dict(pool) if pool else None,
            "picked_by": int(picks), "merges": merges, "games": games, "stored": stored,
        })
    return out
