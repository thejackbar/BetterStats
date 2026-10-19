"""Diagnostic: why does a player's games-played figure read higher than it should?

Reported by Leederville CC: after a weekend sync every player on 99 games read 101,
CA's own profile read 100, and the club expects 99 because a round 1 game last year
was rained off. A washed-out game can sneak back into the count three ways, and each
leaves a different mark on the rows this prints:

  1. The game's `status` is something other than ABANDONED or CANCELLED (a club that
     enters a washout as NO RESULT, or a sync that left the column NULL). The season
     view only subtracts ABANDONED and CANCELLED, so the game is simply counted.
  2. The status is right but the named player has a batting row for the game. A
     did-not-bat row counts as "recorded something", so the correction skips them.
  3. CA's own aggregate moved (a new `player_season_stats` row or a bumped `matches`)
     and the correction was never the problem.

For one player this prints, per season, CA's stored `matches` beside the figure the
effective view hands the profile (the gap is the washout correction doing its work),
then every game the player was named in that looks like it might not have been played,
with the fields each rule reads and whether each rule would count it. A final section
counts the club's games by status, so a status the code does not know about shows up.

Read-only: writes nothing, calls nothing upstream.

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.diagnose_games_played <org_id_or_slug> "<player name>" [--all]

`--all` lists every game the player was named in; the default keeps only the ones that
could have been a washout (a called-off status, no status, NO RESULT, or an empty card).
"""
import argparse
import asyncio
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services.club_grades import club_game_sql
from app.services.game_status import (
    NOT_PLAYED_SQL_LIST, _scored_innings_sql, appearance_counts_as_match, not_played_game_sql,
)


async def _resolve_org(org_ref: str) -> str:
    """An org id, or a club slug looked up to one. A slug that matches nothing stops the run."""
    try:
        return str(uuid.UUID(org_ref))
    except ValueError:
        pass
    async with async_session_maker() as session:
        found = (await session.execute(
            text("SELECT id::text FROM organisations WHERE slug = :s"), {"s": org_ref})).scalar()
    if not found:
        raise SystemExit(f"No club with slug {org_ref!r}")
    return found


async def diagnose(org_ref: str, who: str, show_all: bool) -> None:
    org = await _resolve_org(org_ref)
    async with async_session_maker() as session:
        players = (await session.execute(text("""
            SELECT id::text AS id, COALESCE(display_name_override, name) AS name
            FROM players
            WHERE organisation_id = CAST(:org AS UUID)
              AND COALESCE(display_name_override, name) ILIKE :who
            ORDER BY 2"""), {"org": org, "who": f"%{who}%"})).mappings().all()
        if not players:
            raise SystemExit(f"No player matching {who!r} in that club")
        print(f"{len(players)} player(s) match {who!r}:")
        for p in players:
            print(f"  {p['id']}  {p['name']}")

        for p in players:
            pid = p["id"]
            print(f"\n==== {p['name']} ({pid}) ====")

            print("\n-- per season: CA's stored matches against what the profile is given")
            seasons = (await session.execute(text("""
                SELECT s.year, s.name AS season, pss.source AS stored_source, pss.matches AS stored,
                       COALESCE((SELECT SUM(v.matches) FROM v_effective_player_season_stats v
                                 WHERE v.player_id = pss.player_id AND v.season_id = pss.season_id
                                   AND v.source = 'api'), 0) AS after_view
                FROM player_season_stats pss
                JOIN seasons s ON s.id = pss.season_id
                WHERE pss.player_id = CAST(:pid AS UUID)
                ORDER BY s.year DESC, s.name"""), {"pid": pid})).mappings().all()
            total_stored = total_view = 0
            for r in seasons:
                total_stored += r["stored"] or 0
                total_view += int(r["after_view"] or 0)
                gap = (r["stored"] or 0) - int(r["after_view"] or 0)
                print(f"  {r['season']:<28} stored={r['stored']!s:<4} profile={int(r['after_view'])!s:<4}"
                      f" source={r['stored_source']}" + (f"   (washouts taken off: {gap})" if gap else ""))
            print(f"  TOTAL                        stored={total_stored}  profile={total_view}")

            print("\n-- games the player was named in that could have been a washout")
            where_extra = "" if show_all else f"""
              AND (g.status IS NULL
                   OR g.status NOT IN ('COMPLETED', 'LIVE', 'UPCOMING')
                   OR {_scored_innings_sql('g')} = 0)"""
            games = (await session.execute(text(f"""
                SELECT g.id::text AS game_id, g.played_at::text AS played_at, gr.name AS grade,
                       COALESCE(g.match_format, '') AS fmt, g.status, g.result,
                       {_scored_innings_sql('g')} AS scored_innings,
                       (SELECT COUNT(*) FROM batting_innings b WHERE b.game_id = g.id AND b.player_id = ga.player_id
                           AND NOT COALESCE(b.did_not_bat, FALSE)) AS bat_real,
                       (SELECT COUNT(*) FROM batting_innings b WHERE b.game_id = g.id AND b.player_id = ga.player_id
                           AND COALESCE(b.did_not_bat, FALSE)) AS bat_dnb,
                       (SELECT COUNT(*) FROM bowling_spells w WHERE w.game_id = g.id AND w.player_id = ga.player_id) AS bowl,
                       (SELECT COUNT(*) FROM fielding_stats f WHERE f.game_id = g.id AND f.player_id = ga.player_id) AS field,
                       (SELECT COUNT(*) FROM batting_innings b WHERE b.game_id = g.id
                           AND NOT COALESCE(b.did_not_bat, FALSE)) AS bat_real_anyone,
                       (SELECT COUNT(*) FROM bowling_spells w WHERE w.game_id = g.id) AS bowl_anyone,
                       {not_played_game_sql('g')} AS reader_says_not_played,
                       ({appearance_counts_as_match('ga')}) AS reader_counts,
                       (g.status IN ({NOT_PLAYED_SQL_LIST})
                        AND NOT EXISTS (SELECT 1 FROM batting_innings b WHERE b.game_id = ga.game_id AND b.player_id = ga.player_id)
                        AND NOT EXISTS (SELECT 1 FROM bowling_spells w WHERE w.game_id = ga.game_id AND w.player_id = ga.player_id)
                        AND NOT EXISTS (SELECT 1 FROM fielding_stats f WHERE f.game_id = ga.game_id AND f.player_id = ga.player_id)
                       ) AS season_view_takes_off
                FROM game_appearances ga
                JOIN games g ON g.id = ga.game_id
                JOIN grades gr ON gr.id = g.grade_id
                WHERE ga.player_id = CAST(:pid AS UUID){where_extra}
                ORDER BY g.played_at DESC"""), {"pid": pid})).mappings().all()
            if not games:
                print("  none")
            for g in games:
                note = []
                if g["status"] is None:
                    note.append("STATUS NULL: season view cannot subtract it")
                elif g["status"] not in ("COMPLETED", "ABANDONED", "CANCELLED", "LIVE", "UPCOMING"):
                    note.append(f"status {g['status']!r} is not one the rules know")
                if g["bat_dnb"] and not g["bat_real"] and not g["bowl"] and not g["field"]:
                    note.append("ONLY a did-not-bat row: counts as 'recorded something'")
                if g["status"] in ("ABANDONED", "CANCELLED") and not g["season_view_takes_off"]:
                    note.append("called off but NOT taken off the season total")
                print(f"  {g['played_at']}  {g['grade']:<24} {g['fmt']:<8} status={g['status']!s:<10} result={g['result']!s:<8}"
                      f" scored_innings={g['scored_innings']}")
                print(f"      player rows: bat={g['bat_real']} dnb={g['bat_dnb']} bowl={g['bowl']} field={g['field']}"
                      f"   game rows (anyone): bat={g['bat_real_anyone']} bowl={g['bowl_anyone']}")
                print(f"      readers count it: {g['reader_counts']}   season view takes it off: {g['season_view_takes_off']}"
                      + (f"   <-- {'; '.join(note)}" if note else ""))

        print("\n==== club games by status (all seasons held) ====")
        for r in (await session.execute(text(f"""
            SELECT COALESCE(g.status, '(null)') AS status, COUNT(*) AS games,
                   COUNT(*) FILTER (WHERE {_scored_innings_sql('g')} = 0) AS no_scored_innings,
                   COUNT(*) FILTER (WHERE g.played_at < CURRENT_DATE) AS in_the_past
            FROM games g
            JOIN v_effective_games vg ON vg.id = g.id
            WHERE {club_game_sql('vg', 'org')}
            GROUP BY 1 ORDER BY 2 DESC"""), {"org": org})).mappings().all():
            print(f"  {r['status']:<12} games={r['games']:<6} with no scored innings={r['no_scored_innings']:<6} dated in the past={r['in_the_past']}")

        print("\n==== the same fixture held twice (same grade and teams, dates within 8 days) ====")
        print("A second row for one match counts twice in every held-games figure while CA counts it once.")
        dupes = (await session.execute(text(f"""
            SELECT a.id::text AS a_id, b.id::text AS b_id, a.played_at::text AS a_date, b.played_at::text AS b_date,
                   gr.name AS grade, a.home_team, a.away_team, a.source AS a_src, b.source AS b_src,
                   a.status AS a_status, b.status AS b_status
            FROM v_effective_games a
            JOIN v_effective_games b ON b.id > a.id AND b.grade_id = a.grade_id
                 AND b.home_team = a.home_team AND b.away_team = a.away_team
                 AND ABS(b.played_at::date - a.played_at::date) <= 8
            JOIN grades gr ON gr.id = a.grade_id
            WHERE {club_game_sql('a', 'org')} AND a.played_at >= CURRENT_DATE - 400
            ORDER BY a.played_at DESC LIMIT 60"""), {"org": org})).mappings().all()
        if not dupes:
            print("  none found")
        for d in dupes:
            print(f"  {d['grade']:<24} {d['home_team']} v {d['away_team']}")
            print(f"      {d['a_date']} {d['a_id']} source={d['a_src']} status={d['a_status']}")
            print(f"      {d['b_date']} {d['b_id']} source={d['b_src']} status={d['b_status']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("org", help="club id or slug")
    ap.add_argument("player", help="part of the player's name")
    ap.add_argument("--all", action="store_true", help="list every game the player was named in")
    a = ap.parse_args()
    asyncio.run(diagnose(a.org, a.player, a.all))


if __name__ == "__main__":
    main()
