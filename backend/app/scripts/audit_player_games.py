"""For every game a player holds, does CA's team sheet actually carry that player? Read only.

Built for a record that reads far more games than CA credits (Leederville's Jonah
Cumming: 48 held, 12 on CA's own totals, three grades on one day). It does not guess how
the games got there. For each game the player has a row or a team-sheet entry in, it asks
CA for the scorecard and checks the sheets for the player's participant id, and for any id
that was merged into them (`merge_logs`, not undone):

  ON SHEET     the player's own id is on the card (a team sheet entry or a row): the game is theirs.
  VIA MERGE    an id merged into them is on the sheet: theirs through a merge.
  NOT ON SHEET neither is. Their rows came from somewhere else; for each batting or bowling
               row we hold, the CA row it matches (same innings, position and score, or same
               figures) is printed with the name and id CA gives it, so a redacted
               participant (`********`, id 00000000-...-0001) or another person is visible.
  NO CARD      CA returned nothing for the game, or the card names nobody. Nothing can be judged.

One paced request per game (the client caches). Writes nothing.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -m app.scripts.audit_player_games <org_id_or_slug_or_auto> <player-id> [--limit 80]

Pass `auto` as the club to use the player's own club.
"""
import argparse
import asyncio
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import game_attribution, grassroots_scores_client as gr
from app.services.club_grades import club_game_sql


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


def _name_of(p: dict) -> str:
    return str(p.get("playerShortName") or p.get("displayName") or p.get("name") or "")


async def audit(org_ref: str, player_id: str, limit: int) -> None:
    if org_ref in ("auto", "-"):
        # The player's own club, so any club's player can be audited without knowing its slug.
        async with async_session_maker() as s0:
            found = (await s0.execute(text(
                "SELECT organisation_id::text FROM players WHERE id = CAST(:p AS UUID)"), {"p": player_id})).scalar()
        if not found:
            raise SystemExit("No such player id")
        org = found
    else:
        org = await _resolve_org(org_ref)
    async with async_session_maker() as s:
        me = (await s.execute(text(
            "SELECT COALESCE(display_name_override, name) AS name, grassroots_id FROM players WHERE id = CAST(:p AS UUID)"),
            {"p": player_id})).mappings().first()
        if not me:
            raise SystemExit("No such player id")
        own = {(me["grassroots_id"] or player_id).lower()}
        redirects = {str(r[0]): str(r[1]) for r in (await s.execute(text(
            "SELECT removed_player_id, keep_player_id FROM merge_logs "
            "WHERE org_id = CAST(:o AS UUID) AND undone_at IS NULL"), {"o": org})).all()}
        merged_in = game_attribution.merged_into(redirects, player_id)
        print(f"{me['name']}  ids that count as theirs: {sorted(own)}"
              + (f"  plus {len(merged_in)} merged in" if merged_in else ""))

        games = (await s.execute(text(f"""
            WITH held AS (
                SELECT bi.game_id FROM v_effective_batting_innings bi WHERE bi.player_id = CAST(:p AS UUID)
                UNION SELECT bs.game_id FROM v_effective_bowling_spells bs WHERE bs.player_id = CAST(:p AS UUID)
                UNION SELECT fs.game_id FROM v_effective_fielding_stats fs WHERE fs.player_id = CAST(:p AS UUID)
                UNION SELECT ga.game_id FROM game_appearances ga WHERE ga.player_id = CAST(:p AS UUID))
            SELECT g.id::text AS id, g.played_at::text AS d, gr.name AS grade, g.source
            FROM held h JOIN v_effective_games g ON g.id = h.game_id LEFT JOIN grades gr ON gr.id = g.grade_id
            WHERE {club_game_sql('g', 'org')} AND g.source = 'api'
            ORDER BY g.played_at DESC LIMIT :lim"""), {"p": player_id, "org": org, "lim": limit})).mappings().all()
        print(f"{len(games)} synced games held (newest first); asking CA about each\n")

        tally = {"ON": 0, "MERGE": 0, "OFF": 0, "NONE": 0}
        off_lines = []
        for g in games:
            sc = await gr.get_match_scorecard(g["id"])
            await asyncio.sleep(0.3)
            if not sc:
                tally["NONE"] += 1
                print(f"  {g['d']}  {str(g['grade']):<18} NO CARD  {g['id']}")
                continue
            verdict = game_attribution.classify(sc, own, merged_in, uuid.UUID(org))
            if verdict == "EMPTY":
                tally["NONE"] += 1
                print(f"  {g['d']}  {str(g['grade']):<18} NOBODY NAMED ON THE CARD  {g['id']}")
                continue
            if verdict == "ON":
                tally["ON"] += 1
                continue
            if verdict == "MERGE":
                tally["MERGE"] += 1
                print(f"  {g['d']}  {str(g['grade']):<18} VIA MERGE  {g['id']}")
                continue
            tally["OFF"] += 1
            line = f"  {g['d']}  {str(g['grade']):<18} NOT ON SHEET  {g['id']}"
            print(line)
            off_lines.append(g["id"])
            bat = (await s.execute(text(
                "SELECT innings_number, batting_position, runs FROM batting_innings WHERE game_id = CAST(:g AS UUID) "
                "AND player_id = CAST(:p AS UUID) AND NOT COALESCE(did_not_bat, FALSE)"), {"g": g["id"], "p": player_id})).mappings().all()
            for mb in bat:
                for inn in sc.get("innings") or []:
                    if (inn.get("inningsOrder") or inn.get("inningsNumber") or 1) != mb["innings_number"]:
                        continue
                    for row in inn.get("batting") or []:
                        if row.get("batOrder") == mb["batting_position"] and (row.get("runsScored") or 0) == (mb["runs"] or 0):
                            print(f"       our batting row (pos {mb['batting_position']}, {mb['runs']}) = CA "
                                  f"{_name_of(row)!r} id={(row.get('participantId') or '').lower()}")

        print(f"\nsummary: on sheet {tally['ON']}, via merge {tally['MERGE']}, NOT ON SHEET {tally['OFF']}, no card {tally['NONE']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("org", help="club id or slug, or 'auto' for the player's own club")
    ap.add_argument("player", help="BetterStats player id")
    ap.add_argument("--limit", type=int, default=80, help="most games to check (newest first)")
    a = ap.parse_args()
    asyncio.run(audit(a.org, a.player, a.limit))


if __name__ == "__main__":
    main()
