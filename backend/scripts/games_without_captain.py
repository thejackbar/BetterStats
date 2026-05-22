#!/usr/bin/env python3
"""
Report all games in the last 3 seasons where no captain was assigned.

Two flavours:
  - Games with zero game_appearances rows (roster never loaded)
  - Games with appearances rows but none marked is_captain=TRUE

Usage:
    python scripts/games_without_captain.py [org_slug_or_id]
"""

import os
import sys

import psycopg2
import psycopg2.extras

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://cricket:cricket@localhost/betterstats"
).replace("postgresql+asyncpg://", "postgresql://")

ORG_FILTER = sys.argv[1] if len(sys.argv) > 1 else None


def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Resolve org
    if ORG_FILTER:
        cur.execute(
            "SELECT id, name FROM organisations WHERE id::text = %s OR slug = %s",
            (ORG_FILTER, ORG_FILTER),
        )
        org = cur.fetchone()
        if not org:
            print(f"Org '{ORG_FILTER}' not found")
            sys.exit(1)
        org_clause = "AND s.organisation_id = %s"
        org_params = [str(org["id"])]
        print(f"Organisation: {org['name']}")
    else:
        # All orgs
        org_clause = ""
        org_params = []
        print("All organisations")

    # Last 3 seasons by year
    cur.execute(
        f"""
        SELECT DISTINCT s.id, s.name, s.year
        FROM seasons s
        WHERE 1=1 {org_clause}
        ORDER BY s.year DESC NULLS FIRST
        LIMIT 3
        """,
        org_params,
    )
    seasons = cur.fetchall()
    if not seasons:
        print("No seasons found")
        sys.exit(1)

    season_ids = [str(s["id"]) for s in seasons]
    print(f"Checking: {', '.join(s['name'] for s in seasons)}\n")

    # ── 1. Games with game_appearances but no captain ────────────────────────
    cur.execute(
        f"""
        SELECT
            g.id AS game_id,
            g.played_at,
            g.home_team,
            g.away_team,
            g.result,
            g.is_final,
            COALESCE(gr.display_name_override, gr.name) AS grade_name,
            s.name AS season_name,
            COUNT(ga.player_id) AS appearance_count
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        JOIN game_appearances ga ON ga.game_id = g.id
        WHERE s.id = ANY(%s)
          {org_clause}
          AND NOT EXISTS (
            SELECT 1 FROM game_appearances ga2
            WHERE ga2.game_id = g.id AND ga2.is_captain = TRUE
          )
        GROUP BY g.id, g.played_at, g.home_team, g.away_team, g.result,
                 g.is_final, gr.display_name_override, gr.name, s.name
        ORDER BY s.name, g.played_at DESC NULLS LAST
        """,
        ([season_ids] + org_params),
    )
    no_captain_with_appearances = cur.fetchall()

    # ── 2. Games with scorecard data but zero game_appearances rows ──────────
    cur.execute(
        f"""
        SELECT
            g.id AS game_id,
            g.played_at,
            g.home_team,
            g.away_team,
            g.result,
            g.is_final,
            COALESCE(gr.display_name_override, gr.name) AS grade_name,
            s.name AS season_name
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.id = ANY(%s)
          {org_clause}
          AND NOT EXISTS (SELECT 1 FROM game_appearances ga WHERE ga.game_id = g.id)
          AND (
            EXISTS (SELECT 1 FROM batting_innings bi WHERE bi.game_id = g.id)
            OR EXISTS (SELECT 1 FROM bowling_spells bs WHERE bs.game_id = g.id)
            OR EXISTS (SELECT 1 FROM fielding_stats fs WHERE fs.game_id = g.id)
          )
        ORDER BY s.name, g.played_at DESC NULLS LAST
        """,
        ([season_ids] + org_params),
    )
    no_appearances_at_all = cur.fetchall()

    # ── Print ────────────────────────────────────────────────────────────────
    total = len(no_captain_with_appearances) + len(no_appearances_at_all)
    print(f"{'='*70}")
    print(f"GAMES WITH NO CAPTAIN ASSIGNED: {total}")
    print(f"{'='*70}\n")

    if no_captain_with_appearances:
        print(f"HAS APPEARANCES BUT NO CAPTAIN ({len(no_captain_with_appearances)} games):")
        print(f"(roster was loaded but captain role not set in Grassroots data)")
        print("-" * 70)
        cur_season = None
        for r in no_captain_with_appearances:
            if r["season_name"] != cur_season:
                cur_season = r["season_name"]
                print(f"\n  [{cur_season}]")
            final_flag = " [FINAL]" if r["is_final"] else ""
            print(
                f"  {str(r['played_at'] or '?'):12s}  "
                f"{(r['grade_name'] or '?'):22s}  "
                f"{(r['home_team'] or '?'):22s} vs {(r['away_team'] or '?'):22s}"
                f"{final_flag}"
                f"  ({r['appearance_count']} players)  id={r['game_id']}"
            )

    if no_appearances_at_all:
        print(f"\nHAS STATS BUT NO APPEARANCES TABLE ROWS ({len(no_appearances_at_all)} games):")
        print(f"(game was synced but roster rows were never written — re-sync needed)")
        print("-" * 70)
        cur_season = None
        for r in no_appearances_at_all:
            if r["season_name"] != cur_season:
                cur_season = r["season_name"]
                print(f"\n  [{cur_season}]")
            final_flag = " [FINAL]" if r["is_final"] else ""
            print(
                f"  {str(r['played_at'] or '?'):12s}  "
                f"{(r['grade_name'] or '?'):22s}  "
                f"{(r['home_team'] or '?'):22s} vs {(r['away_team'] or '?'):22s}"
                f"{final_flag}  id={r['game_id']}"
            )

    if total == 0:
        print("  No games found without a captain — all good!")

    print(f"\n{'='*70}")
    print(f"Summary: {len(no_captain_with_appearances)} with roster but no captain, "
          f"{len(no_appearances_at_all)} with no roster rows at all")
    print()

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
