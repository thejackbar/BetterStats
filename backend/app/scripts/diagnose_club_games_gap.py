"""Diagnostic: how many players' games-played figures differ between the two counts, and why. Read only.

BetterStats has two ways to count a player's matches. The unfiltered profile sums
Cricket Australia's own season totals (`v_effective_player_season_stats`, washouts taken
off). A filtered header, and many other screens, count the games we HOLD for the player
(a batting, bowling or fielding row, or a team-sheet entry in a game that was played).
For most players they agree. They differ when we hold a game CA does not credit to this
player: typically the player has two CA registrations that were merged here, and CA keeps
each on its own profile. This puts a number on how widespread that is for one club.

Prints:
  1. how many players are off, by how much (held minus profile);
  2. of the players who are off, how many have a merge recorded into them, and how many do not;
  3. the biggest gaps, with their merge counts;
  4. merges recorded in the last 21 days (by hand, and automatic after a sync), since a burst
     of merges would move many players at once.

Players off with NO merge need another explanation; the per-player `diagnose_games_played`
and `inspect_scorecard_player` scripts take it from there.

Read only. Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -m app.scripts.diagnose_club_games_gap <org_id_or_slug> [--top N] [--since-year 2025]
"""
import argparse
import asyncio
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services.club_grades import club_game_sql
from app.services.game_status import appearance_counts_as_match


async def _resolve_org(org_ref: str) -> str:
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


async def diagnose(org_ref: str, top: int, since_year: int | None) -> None:
    org = await _resolve_org(org_ref)
    # Only seasons from this year on (a season's `year` is its starting calendar year), on BOTH
    # sides, so a player's old career, which CA counts and we never synced, does not read as a gap.
    held_since = "AND se.year >= CAST(:since AS INT)" if since_year is not None else ""
    prof_since = "WHERE se.year >= CAST(:since AS INT)" if since_year is not None else ""
    async with async_session_maker() as s:
        await s.execute(text("SET LOCAL statement_timeout = '120s'"))
        await s.execute(text(f"""
            CREATE TEMP TABLE _gap AS
            WITH club_players AS (
                SELECT id, COALESCE(display_name_override, name) AS name FROM players
                WHERE organisation_id = CAST(:org AS UUID)
            ),
            held AS (
                SELECT bi.player_id, bi.game_id FROM v_effective_batting_innings bi JOIN club_players p ON p.id = bi.player_id
                UNION SELECT bs.player_id, bs.game_id FROM v_effective_bowling_spells bs JOIN club_players p ON p.id = bs.player_id
                UNION SELECT fs.player_id, fs.game_id FROM v_effective_fielding_stats fs JOIN club_players p ON p.id = fs.player_id
                UNION SELECT ga.player_id, ga.game_id FROM game_appearances ga JOIN club_players p ON p.id = ga.player_id
                      WHERE {appearance_counts_as_match('ga')}
            ),
            held_n AS (
                SELECT h.player_id, COUNT(DISTINCT h.game_id) AS held
                FROM held h JOIN v_effective_games g ON g.id = h.game_id
                JOIN seasons se ON se.id = g.season_id
                WHERE {club_game_sql('g', 'org')} {held_since}
                GROUP BY 1
            ),
            prof AS (
                SELECT v.player_id, COALESCE(SUM(v.matches), 0) AS profile
                FROM v_effective_player_season_stats v JOIN club_players p ON p.id = v.player_id
                LEFT JOIN seasons se ON se.id = v.season_id
                {prof_since}
                GROUP BY 1
            ),
            mer AS (
                SELECT keep_player_id AS player_id, COUNT(*) AS merges
                FROM merge_logs WHERE org_id = CAST(:org AS UUID) AND undone_at IS NULL GROUP BY 1
            )
            SELECT p.id, p.name, COALESCE(h.held, 0) AS held, COALESCE(pr.profile, 0) AS profile,
                   COALESCE(h.held, 0) - COALESCE(pr.profile, 0) AS gap, COALESCE(m.merges, 0) AS merges
            FROM club_players p
            LEFT JOIN held_n h ON h.player_id = p.id
            LEFT JOIN prof pr ON pr.player_id = p.id
            LEFT JOIN mer m ON m.player_id = p.id
            WHERE COALESCE(h.held, 0) > 0 OR COALESCE(pr.profile, 0) > 0"""), {"org": org, "since": since_year} if since_year is not None else {"org": org})

        total = (await s.execute(text("SELECT COUNT(*) FROM _gap"))).scalar()
        print(f"{total} players with any games in this club"
              + (f", counting seasons from {since_year} on" if since_year is not None else ", all seasons") + "\n")

        print("== held minus profile, per player")
        for r in (await s.execute(text("""
            SELECT LEAST(GREATEST(gap, -3), 3) AS g, COUNT(*) AS n FROM _gap GROUP BY 1 ORDER BY 1"""))).mappings():
            label = {-3: "-3 or lower", 3: "+3 or higher"}.get(r["g"], f"{r['g']:+d}" if r["g"] else "0 (agree)")
            print(f"  {label:<14} {r['n']} players")

        print("\n== players who are OFF (gap not 0), by whether a merge was recorded into them")
        for r in (await s.execute(text("""
            SELECT (merges > 0) AS has_merge, COUNT(*) AS n,
                   COUNT(*) FILTER (WHERE gap > 0) AS held_higher, COUNT(*) FILTER (WHERE gap < 0) AS held_lower
            FROM _gap WHERE gap <> 0 GROUP BY 1 ORDER BY 1 DESC"""))).mappings():
            print(f"  {'merged into' if r['has_merge'] else 'NO merge':<12} {r['n']} players "
                  f"({r['held_higher']} with held higher, {r['held_lower']} with held lower)")
        agree = (await s.execute(text("SELECT COUNT(*) FILTER (WHERE merges > 0) FROM _gap WHERE gap = 0"))).scalar()
        print(f"  (for comparison, {agree} players who agree DO have a merge into them)")

        print(f"\n== held HIGHER with NO merge recorded: the unexplained group (top {top})")
        for r in (await s.execute(text("""
            SELECT name, held, profile, gap FROM _gap WHERE gap > 0 AND merges = 0
            ORDER BY gap DESC, name LIMIT :n"""), {"n": top})).mappings():
            print(f"  {r['name']:<28} held={r['held']:<4} profile={int(r['profile']):<4} gap={r['gap']:+d}")

        print(f"\n== biggest gaps either way (top {top})")
        for r in (await s.execute(text("""
            SELECT name, held, profile, gap, merges FROM _gap WHERE gap <> 0
            ORDER BY ABS(gap) DESC, name LIMIT :n"""), {"n": top})).mappings():
            print(f"  {r['name']:<28} held={r['held']:<4} profile={int(r['profile']):<4} gap={r['gap']:+d}  merges into them={r['merges']}")

        print("\n== merges recorded in the last 21 days")
        n_manual = (await s.execute(text("""
            SELECT COUNT(*) FROM merge_logs WHERE org_id = CAST(:org AS UUID) AND merged_at > NOW() - INTERVAL '21 days'"""),
            {"org": org})).scalar()
        n_auto = (await s.execute(text("""
            SELECT COUNT(*) FROM audit_logs WHERE org_id = CAST(:org AS UUID) AND action = 'auto_merge_hand_added'
              AND created_at > NOW() - INTERVAL '21 days'"""), {"org": org})).scalar()
        print(f"  {n_manual} merge log rows ({n_auto} of them automatic, after a sync)")
        for r in (await s.execute(text("""
            SELECT merged_at::date::text AS d, COUNT(*) AS n, COUNT(*) FILTER (WHERE undone_at IS NOT NULL) AS undone
            FROM merge_logs WHERE org_id = CAST(:org AS UUID) AND merged_at > NOW() - INTERVAL '21 days'
            GROUP BY 1 ORDER BY 1 DESC"""), {"org": org})).mappings():
            print(f"    {r['d']}: {r['n']} merges ({r['undone']} since undone)")
        for r in (await s.execute(text("""
            SELECT merged_at::date::text AS d, keep_player_name, removed_player_name, undone_at IS NOT NULL AS undone
            FROM merge_logs WHERE org_id = CAST(:org AS UUID) AND merged_at > NOW() - INTERVAL '21 days'
            ORDER BY merged_at DESC LIMIT 30"""), {"org": org})).mappings():
            print(f"  {r['d']}  {r['keep_player_name']} <- {r['removed_player_name']}" + ("  (undone)" if r["undone"] else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("org", help="club id or slug")
    ap.add_argument("--top", type=int, default=25, help="how many of the biggest gaps to list")
    ap.add_argument("--since-year", type=int, default=None,
                    help="only count seasons starting this year or later (2025 = the 2025/26 and 2026/27 seasons)")
    a = ap.parse_args()
    asyncio.run(diagnose(a.org, a.top, a.since_year))


if __name__ == "__main__":
    main()
