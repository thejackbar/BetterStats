#!/usr/bin/env python3
"""
Diagnostic: find all games in the last 3 years where a player was listed
as captain (or appeared but was NOT marked captain), comparing game_appearances
against the raw Grassroots scorecard.

Usage:
    python3 scripts/find_captain_games.py [player_id]

player_id defaults to Tristram Fletcher: b763a2d6-8c2e-4104-8419-3095ee9bbfc9
"""

import os
import sys
import json
import urllib.request

import psycopg2
import psycopg2.extras

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://cricket:cricket@localhost/betterstats"
).replace("postgresql+asyncpg://", "postgresql://")

PLAYER_ID = sys.argv[1] if len(sys.argv) > 1 else "b763a2d6-8c2e-4104-8419-3095ee9bbfc9"
SINCE = "2022-09-01"  # start of Summer 2022/23

GR_BASE = "https://grassrootsapiproxy.cricket.com.au/scores"
# jsconfig=eccn:true is a ServiceStack flag that returns camelCase keys
# (without it the API returns PascalCase and all dict lookups fail)
_GR_PARAMS = "jsconfig=eccn%3Atrue"


def fetch_json(url):
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(
        f"{url}{sep}{_GR_PARAMS}",
        headers={"User-Agent": "BetterStats/1.0"},
    )
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
        "SELECT id, name, display_name_override FROM players WHERE id = %s::uuid",
        (PLAYER_ID,),
    )
    player = cur.fetchone()
    if not player:
        print(f"Player {PLAYER_ID} not found in DB")
        sys.exit(1)

    display = player["display_name_override"] or player["name"]
    print(f"\n{'='*60}")
    print(f"Player: {display}  (id={PLAYER_ID})")
    print(f"Checking games played_at >= {SINCE}")
    print(f"{'='*60}\n")

    # 2. Sanity check: how many batting/bowling rows exist at all?
    cur.execute(
        "SELECT COUNT(*) AS n FROM batting_innings WHERE player_id = %s::uuid",
        (PLAYER_ID,),
    )
    bat_total = cur.fetchone()["n"]
    cur.execute(
        "SELECT COUNT(*) AS n FROM bowling_spells WHERE player_id = %s::uuid",
        (PLAYER_ID,),
    )
    bowl_total = cur.fetchone()["n"]
    cur.execute(
        "SELECT COUNT(*) AS n FROM game_appearances WHERE player_id = %s::uuid",
        (PLAYER_ID,),
    )
    appear_total = cur.fetchone()["n"]

    print(f"All-time DB rows for this player:")
    print(f"  batting_innings   : {bat_total}")
    print(f"  bowling_spells    : {bowl_total}")
    print(f"  game_appearances  : {appear_total}")
    print()

    # 3. All game_appearances since SINCE (filter by played_at, not season year)
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
            COALESCE(gr.display_name_override, gr.name) AS grade_name,
            s.name AS season_name
        FROM game_appearances ga
        JOIN games g ON g.id = ga.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE ga.player_id = %s::uuid
          AND g.played_at >= %s
        ORDER BY g.played_at DESC NULLS LAST
        """,
        (PLAYER_ID, SINCE),
    )
    appearances = cur.fetchall()

    captain_games = [r for r in appearances if r["is_captain"]]
    non_captain_games = [r for r in appearances if not r["is_captain"]]

    print(f"game_appearances rows since {SINCE}: {len(appearances)}")
    print(f"  → marked is_captain=TRUE : {len(captain_games)}")
    print(f"  → marked is_captain=FALSE: {len(non_captain_games)}\n")

    if captain_games:
        print("GAMES MARKED AS CAPTAIN:")
        print("-" * 60)
        for r in captain_games:
            print(
                f"  {r['played_at']}  {(r['grade_name'] or '?'):22s}  "
                f"{(r['home_team'] or '?'):20s} vs {(r['away_team'] or '?'):20s}  "
                f"[{r['result'] or '—':4s}]  id={r['game_id']}"
            )
        print()

    # 4. Check Grassroots API for each non-captain game
    if non_captain_games:
        print(f"CHECKING NON-CAPTAIN GAMES AGAINST GRASSROOTS API:")
        print("-" * 60)

        missed = []
        for r in non_captain_games:
            gid = str(r["game_id"])
            data = fetch_json(f"{GR_BASE}/matches/{gid}?responseModifier=includeScorecard")
            if not data:
                print(f"  {r['played_at']}  {(r['grade_name'] or '?'):22s}  → 204/no GR scorecard  id={gid}")
                continue

            teams = data.get("teams") or []
            found = False
            for team in teams:
                for roster_p in (team.get("players") or []):
                    if roster_p.get("participantId") == PLAYER_ID:
                        found = True
                        roles = roster_p.get("roles") or []
                        is_cap = any("captain" in (role or "").lower() for role in roles)
                        if is_cap:
                            missed.append(r)
                            print(
                                f"  *** MISSED CAPTAIN ***  {r['played_at']}  "
                                f"{(r['grade_name'] or '?'):22s}  roles={roles}  id={gid}"
                            )
                        else:
                            print(
                                f"  {r['played_at']}  {(r['grade_name'] or '?'):22s}  "
                                f"roles={roles}  id={gid}"
                            )
            if not found:
                print(
                    f"  {r['played_at']}  {(r['grade_name'] or '?'):22s}  "
                    f"→ not in GR roster  id={gid}"
                )
    else:
        missed = []

    # 5. Games with batting/bowling rows but no game_appearances entry
    cur.execute(
        """
        SELECT DISTINCT g.id AS game_id, g.played_at, g.home_team, g.away_team,
               COALESCE(gr.display_name_override, gr.name) AS grade_name,
               s.name AS season_name
        FROM batting_innings bi
        JOIN games g ON g.id = bi.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE bi.player_id = %s::uuid
          AND g.played_at >= %s
          AND NOT EXISTS (
            SELECT 1 FROM game_appearances ga
            WHERE ga.game_id = g.id AND ga.player_id = %s::uuid
          )
        UNION
        SELECT DISTINCT g.id, g.played_at, g.home_team, g.away_team,
               COALESCE(gr.display_name_override, gr.name), s.name
        FROM bowling_spells bs
        JOIN games g ON g.id = bs.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE bs.player_id = %s::uuid
          AND g.played_at >= %s
          AND NOT EXISTS (
            SELECT 1 FROM game_appearances ga
            WHERE ga.game_id = g.id AND ga.player_id = %s::uuid
          )
        ORDER BY played_at DESC NULLS LAST
        """,
        (PLAYER_ID, SINCE, PLAYER_ID, PLAYER_ID, SINCE, PLAYER_ID),
    )
    orphan_games = cur.fetchall()

    if orphan_games:
        print(f"\nGAMES WITH STATS BUT NO game_appearances ROW ({len(orphan_games)}):")
        print("(these games were synced before the appearances table existed, or roster step was skipped)")
        print("-" * 60)
        for r in orphan_games:
            gid = str(r["game_id"])
            print(
                f"  {r['played_at']}  {(r['grade_name'] or '?'):22s}  "
                f"{r['home_team'] or '?'} vs {r['away_team'] or '?'}  id={gid}"
            )
            data = fetch_json(f"{GR_BASE}/matches/{gid}?responseModifier=includeScorecard")
            if not data:
                print(f"    → no GR scorecard (204)")
                continue
            teams = data.get("teams") or []
            found = False
            for team in teams:
                for roster_p in (team.get("players") or []):
                    if roster_p.get("participantId") == PLAYER_ID:
                        found = True
                        roles = roster_p.get("roles") or []
                        is_cap = any("captain" in (role or "").lower() for role in roles)
                        status = "*** CAPTAIN ***" if is_cap else "not captain"
                        print(f"    → GR roles={roles}  ({status})")
            if not found:
                print(f"    → not found in GR roster for this game")
    else:
        print(f"\nNo orphan games (all stat rows have a game_appearances entry).")

    # 6. If everything is zero, show recent batting games as a sanity check
    if appear_total == 0 and bat_total == 0:
        print(f"\nWARNING: no batting or appearance data at all for this player.")
        print(f"Check the player ID is correct or run a sync.")
    elif appear_total == 0 and bat_total > 0:
        print(f"\nWARNING: {bat_total} batting rows exist but 0 game_appearances rows.")
        print(f"The appearances table was likely created after the last sync.")
        print(f"A full re-sync (Hard Rebuild) will populate it.")
        # Show the most recent batting games regardless of date
        cur.execute(
            """
            SELECT g.played_at, g.home_team, g.away_team,
                   COALESCE(gr.display_name_override, gr.name) AS grade_name,
                   s.name AS season_name, bi.runs, bi.not_out, g.id AS game_id
            FROM batting_innings bi
            JOIN games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE bi.player_id = %s::uuid
            ORDER BY g.played_at DESC NULLS LAST
            LIMIT 10
            """,
            (PLAYER_ID,),
        )
        recent = cur.fetchall()
        print(f"\nMost recent 10 batting innings in DB:")
        for r in recent:
            print(f"  {r['played_at']}  {(r['grade_name'] or '?'):22s}  "
                  f"{r['runs']}{'*' if r['not_out'] else ''}  ({r['season_name']})")

    # 7. Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"  Captain games in DB : {len(captain_games)}")
    print(f"  Non-captain games   : {len(non_captain_games)}")
    print(f"  Orphan (no appear.) : {len(orphan_games)}")
    print(f"  Missed captaincies  : {len(missed)}")
    if missed:
        print(f"\n  UPDATE statements to fix:")
        for r in missed:
            print(f"    UPDATE game_appearances SET is_captain = TRUE")
            print(f"    WHERE game_id = '{r['game_id']}' AND player_id = '{PLAYER_ID}';")
    print()

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
