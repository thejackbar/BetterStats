"""Show what Cricket Australia's scorecard says about one player in one match. Read only.

For a game where a club's count and CA's disagree about whether a player "played": the
team sheet entry (position, roles), every batting, bowling and fielding row for them on
either side, and who else on their side has no batting row, so a 12th man or a substitute
fielder can be told from a member of the XI.

One request to CA per match (the scorecard client caches and paces it). Writes nothing.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -m app.scripts.inspect_scorecard_player <match-id> <player-id>

`match-id` is `games.id` (the CA match GUID); `player-id` is the BetterStats player id.
"""
import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import grassroots_scores_client as gr


def _short(row: dict, keys: tuple) -> dict:
    return {k: row.get(k) for k in keys if k in row}


async def run(match_id: str, player_id: str) -> None:
    async with async_session_maker() as s:
        me = (await s.execute(text(
            "SELECT COALESCE(display_name_override, name) AS name, grassroots_id FROM players WHERE id = CAST(:p AS UUID)"),
            {"p": player_id})).mappings().first()
    if not me:
        raise SystemExit("No such player id")
    guid = (me["grassroots_id"] or "").lower()
    print(f"{me['name']}  participant id {guid or '(none stored)'}")

    sc = await gr.get_match_scorecard(match_id, force=True)
    if not sc:
        raise SystemExit("Cricket Australia returned no scorecard for that match")
    print(f"match status={sc.get('status')!r}  grade={(sc.get('grade') or {}).get('name')!r}")

    for team in sc.get("teams") or []:
        players = team.get("players") or []
        mine = [i for i, p in enumerate(players) if (p.get("participantId") or "").lower() == guid]
        print(f"\nteam {team.get('displayName') or team.get('name')!r}: {len(players)} on the team sheet"
              + ("  <-- his side" if mine else ""))
        if not mine:
            continue
        i = mine[0]
        print(f"  his place on the sheet: {i + 1} of {len(players)}; roles={players[i].get('roles')}")

    batted = set()
    print("\nrows naming him, by innings")
    for n, inn in enumerate(sc.get("innings") or [], start=1):
        for kind, keys in (
            ("batting", ("batOrder", "dismissalTypeId", "dismissalType", "runsScored", "ballsFaced")),
            ("bowling", ("oversBowled", "runsConceded", "wicketsTaken")),
            ("fielding", ("totalCatches", "catches", "wicketKeeperCatches", "runOuts", "stumpings")),
        ):
            for row in inn.get(kind) or []:
                pid = (row.get("participantId") or "").lower()
                if kind == "batting":
                    batted.add(pid)
                if pid == guid:
                    print(f"  innings {n} {kind}: {_short(row, keys)}  name={row.get('playerShortName')!r}")
    print("\n(no lines above means CA holds no row for him in that kind)")

    for team in sc.get("teams") or []:
        players = team.get("players") or []
        if not any((p.get("participantId") or "").lower() == guid for p in players):
            continue
        extra = [p.get("playerShortName") or p.get("displayName") or p.get("name") for p in players
                 if (p.get("participantId") or "").lower() not in batted]
        print(f"\non his side, named but with NO batting row anywhere ({len(extra)}): {', '.join(map(str, extra))}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    asyncio.run(run(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    main()
