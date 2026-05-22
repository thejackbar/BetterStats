#!/usr/bin/env python3
"""
Diagnostic: find all games in the last 3 seasons where a player was listed
as captain (or appeared but was NOT marked captain), comparing game_appearances
against the raw Grassroots scorecard.

Usage:
    python scripts/find_captain_games.py [player_id]

player_id defaults to Tristram Fletcher: b763a2d6-8c2e-4104-8419-3095ee9bbfc9
"""

import os
import sys
import uuid
import json
import urllib.request

import psycopg2
import psycopg2.extras

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://cricket:cricket@localhost/betterstats"
).replace("postgresql+asyncpg://", "postgresql://")

PLAYER_ID = sys.argv[1] if len(sys.argv) > 1 else "b763a2d6-8c2e-4104-8419-3095ee9bbfc9"

GR_BASE = "https://grassrootsapiproxy.cricket.com.au/scores"


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "BetterStats/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status == 204:
                return None
            return json.loads(r.read())
    except Exception as e:
        print(f"  [fetch error] {url}: {e}")
        return None


def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 1. Resolve player
    cur.execute(
        "SELECT id, name, display_name_override FROM players WHERE id = %s",
        (PLAYER_ID,),
    )
    player = cur.fetchone()
    if not player:
        print(f"Player {PLAYER_ID} not found in DB")
        sys.exit(1)

    display = player["display_name_override"] or player["name"]
    print(f"\n{'='*60}")
    print(f"Player: {display}  (id={PLAYER_ID})")
    print(f"{'='*60}\n")

    # 2. Get last 3 seasons
    cur.execute(
        """
        SELECT DISTINCT s.id, s.name, s.year
        FROM seasons s
        JOIN grades gr ON gr.season_id = s.id
        JOIN games g ON g.grade_id = gr.id
        JOIN game_appearances ga ON ga.game_id = g.id
        WHERE ga.player_id = %s
        ORDER BY s.year DESC NULLS FIRST
        LIMIT 3
        """,
        (PLAYER_ID,),
    )
    seasons = cur.fetchall()
    if not seasons:
        # Fallback: last 3 seasons by year
        cur.execute(
            """
            SELECT id, name, year FROM seasons
            WHERE organisation_id = (
                SELECT organisation_id FROM players WHERE id = %s
            )
            ORDER BY year DESC NULLS FIRST
            LIMIT 3
            """,
            (PLAYER_ID,),
        )
        seasons = cur.fetchall()

    season_ids = [str(s["id"]) for s in seasons]
    season_names = ", ".join(s["name"] for s in seasons)
    print(f"Checking seasons: {season_names}\n")

    # 3. All game_appearances in those seasons
    cur.execute(
        """
        SELECT
            ga.game_id,
            ga.is_captain,
            ga.is_wicket_keeper,
            ga.team_name,
            g.played_at,
            g.home_team,
            g.away_team,
            g.result,
            COALESCE(gr_dn.display_name_override, gr.name) AS grade_name,
            s.name AS season_name,
            g.raw_payload IS NOT NULL AS has_raw_payload
        FROM game_appearances ga
        JOIN games g ON g.id = ga.game_id
        JOIN grades gr ON gr.id = g.grade_id
        LEFT JOIN grades gr_dn ON gr_dn.id = gr.id
        JOIN seasons s ON s.id = gr.season_id
        WHERE ga.player_id = %s
          AND s.id = ANY(%s)
        ORDER BY g.played_at DESC NULLS LAST
        """,
        (PLAYER_ID, season_ids),
    )
    appearances = cur.fetchall()

    captain_games = [r for r in appearances if r["is_captain"]]
    non_captain_games = [r for r in appearances if not r["is_captain"]]

    print(f"game_appearances rows in these seasons: {len(appearances)}")
    print(f"  → marked is_captain=TRUE : {len(captain_games)}")
    print(f"  → marked is_captain=FALSE: {len(non_captain_games)}\n")

    print("GAMES MARKED AS CAPTAIN:")
    print("-" * 60)
    for r in captain_games:
        print(
            f"  {r['played_at']}  {r['grade_name']:20s}  "
            f"{r['home_team'] or '?':20s} vs {r['away_team'] or '?':20s}  "
            f"[{r['result'] or '—':4s}]  id={r['game_id']}"
        )

    # 4. Check Grassroots API for each non-captain game to see if roles differ
    print(f"\nCHECKING NON-CAPTAIN GAMES AGAINST GRASSROOTS API:")
    print("-" * 60)

    missed = []
    for r in non_captain_games:
        gid = str(r["game_id"])
        data = fetch_json(f"{GR_BASE}/matches/{gid}?responseModifier=includeScorecard")
        if not data:
            print(f"  {r['played_at']}  {r['grade_name']:20s}  game_id={gid}  → 204/no scorecard")
            continue

        # Look for this player in the roster
        teams = (data.get("matchSummary") or {}).get("teams") or []
        found_as_captain = False
        for team in teams:
            for roster_p in (team.get("players") or []):
                if roster_p.get("participantId") == PLAYER_ID:
                    roles = roster_p.get("roles") or []
                    is_cap = any("captain" in (r2 or "").lower() for r2 in roles)
                    if is_cap:
                        found_as_captain = True
                        missed.append(r)
                        print(
                            f"  *** MISSED CAPTAIN ***  {r['played_at']}  "
                            f"{r['grade_name']:20s}  "
                            f"roles={roles}  id={gid}"
                        )
                    else:
                        print(
                            f"  {r['played_at']}  {r['grade_name']:20s}  "
                            f"roles={roles}  (not captain in GR)  id={gid}"
                        )

    # 5. Also check: games with batting/bowling/fielding but no game_appearance
    cur.execute(
        """
        SELECT DISTINCT g.id AS game_id, g.played_at, g.home_team, g.away_team,
               COALESCE(gr.display_name_override, gr.name) AS grade_name,
               s.name AS season_name
        FROM batting_innings bi
        JOIN games g ON g.id = bi.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE bi.player_id = %s AND s.id = ANY(%s)
          AND g.id NOT IN (SELECT game_id FROM game_appearances WHERE player_id = %s)
        UNION
        SELECT DISTINCT g.id, g.played_at, g.home_team, g.away_team,
               COALESCE(gr.display_name_override, gr.name), s.name
        FROM bowling_spells bs
        JOIN games g ON g.id = bs.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE bs.player_id = %s AND s.id = ANY(%s)
          AND g.id NOT IN (SELECT game_id FROM game_appearances WHERE player_id = %s)
        ORDER BY played_at DESC NULLS LAST
        """,
        (PLAYER_ID, season_ids, PLAYER_ID, PLAYER_ID, season_ids, PLAYER_ID),
    )
    orphan_games = cur.fetchall()

    if orphan_games:
        print(f"\nGAMES WITH STATS BUT NO game_appearances ROW ({len(orphan_games)}):")
        print("-" * 60)
        for r in orphan_games:
            gid = str(r["game_id"])
            print(
                f"  {r['played_at']}  {r['grade_name']:20s}  "
                f"{r['home_team'] or '?'} vs {r['away_team'] or '?'}  id={gid}"
            )
            # Check GR for captain role
            data = fetch_json(f"{GR_BASE}/matches/{gid}?responseModifier=includeScorecard")
            if not data:
                print(f"    → no scorecard from GR")
                continue
            teams = (data.get("matchSummary") or {}).get("teams") or []
            for team in teams:
                for roster_p in (team.get("players") or []):
                    if roster_p.get("participantId") == PLAYER_ID:
                        roles = roster_p.get("roles") or []
                        is_cap = any("captain" in (r2 or "").lower() for r2 in roles)
                        status = "*** CAPTAIN ***" if is_cap else "not captain"
                        print(f"    → GR roles={roles}  ({status})")

    # 6. Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"  Captain games in DB : {len(captain_games)}")
    print(f"  Non-captain games   : {len(non_captain_games)}")
    print(f"  Orphan (no appear.) : {len(orphan_games)}")
    print(f"  Missed captaincies  : {len(missed)}")
    if missed:
        print(f"\n  Fix: run a targeted re-sync or update game_appearances.is_captain")
        print(f"  for game IDs:")
        for r in missed:
            print(f"    {r['game_id']}")
    print()

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
