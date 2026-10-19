"""Show what Cricket Australia's scorecard says about one player in one match. Read only.

For a game where a club's count and CA's disagree about whether a player "played".
CA keys every row on a participant id, and a club can hold the same person under a
different id (a new registration, a merge, a name match), so this does not stop at the
id BetterStats holds. It prints, for each team sheet, every entry whose name shares a
word with the player (and the entry with the player's own id, if there is one), every
batting, bowling and fielding row under those ids, and for each such id how BetterStats
knows it: a player record under that id, or a merge that redirects it.

That answers "is the person CA credits with this game the person we credit it to".

One request to CA per match (the scorecard client paces it). Writes nothing.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -m app.scripts.inspect_scorecard_player <match-id> <player-id>

`match-id` is `games.id` (the CA match GUID); `player-id` is the BetterStats player id.
"""
import asyncio
import sys
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import grassroots_scores_client as gr


def _short(row: dict, keys: tuple) -> dict:
    return {k: row.get(k) for k in keys if k in row}


def _name_of(p: dict) -> str:
    return str(p.get("playerShortName") or p.get("displayName") or p.get("name") or "")


async def run(match_id: str, player_id: str) -> None:
    async with async_session_maker() as s:
        me = (await s.execute(text(
            "SELECT COALESCE(display_name_override, name) AS name, grassroots_id, organisation_id::text AS org "
            "FROM players WHERE id = CAST(:p AS UUID)"), {"p": player_id})).mappings().first()
        if not me:
            raise SystemExit("No such player id")
        guid = (me["grassroots_id"] or player_id).lower()
        words = [w.lower() for w in me["name"].replace(",", " ").split() if len(w) > 2]
        print(f"{me['name']}  BetterStats id {player_id}  participant id {guid}")

        sc = await gr.get_match_scorecard(match_id, force=True)
        if not sc:
            raise SystemExit("Cricket Australia returned no scorecard for that match")
        print(f"match status={sc.get('status')!r}  grade={(sc.get('grade') or {}).get('name')!r}")

        # Everything CA says ABOUT the match that is not a roster or a scorecard line: a flag
        # for a friendly, a practice game, an exhibition or a grade that keeps no player stats
        # would be here, and is the answer to "why does CA not count this game".
        print("\nwhat CA says about the match itself")
        for k, v in sc.items():
            if k in ("teams", "innings", "matchSchedule"):
                continue
            if isinstance(v, dict):
                flat = {a: b for a, b in v.items() if not isinstance(b, (dict, list))}
                print(f"  {k}: {flat}")
                for a, b in v.items():
                    if isinstance(b, dict):
                        print(f"  {k}.{a}: { {x: y for x, y in b.items() if not isinstance(y, (dict, list))} }")
            elif isinstance(v, list):
                print(f"  {k}: list of {len(v)}")
            else:
                print(f"  {k}: {v!r}")
        print(f"  matchSchedule: {[ {a: b for a, b in (e or {}).items() if not isinstance(b, (dict, list))} for e in (sc.get('matchSchedule') or [])]}")

        interesting: dict[str, str] = {}
        for team in sc.get("teams") or []:
            players = team.get("players") or []
            print(f"\nteam {team.get('displayName') or team.get('name')!r}: {len(players)} on the team sheet")
            for i, p in enumerate(players, start=1):
                pid = (p.get("participantId") or "").lower()
                nm = _name_of(p)
                own = pid == guid
                near = any(w in nm.lower() for w in words)
                if own or near:
                    interesting[pid] = nm
                    print(f"  {i:>2}. {nm!r}  participantId={pid}  roles={p.get('roles')}"
                          + ("   <-- HIS OWN ID" if own else "   <-- shares a name word"))
            if not any((p.get('participantId') or '').lower() in interesting for p in players):
                print("  nobody on this sheet matches his id or a word of his name")

        print("\nrows under those ids, by innings")
        found = False
        for n, inn in enumerate(sc.get("innings") or [], start=1):
            for kind, keys in (
                ("batting", ("batOrder", "dismissalTypeId", "dismissalType", "runsScored", "ballsFaced")),
                ("bowling", ("oversBowled", "runsConceded", "wicketsTaken")),
                ("fielding", ("totalCatches", "catches", "wicketKeeperCatches", "runOuts", "stumpings")),
            ):
                for row in inn.get(kind) or []:
                    pid = (row.get("participantId") or "").lower()
                    if pid in interesting or any(w in _name_of(row).lower() for w in words):
                        found = True
                        print(f"  innings {n} {kind}: {_short(row, keys)}  name={_name_of(row)!r} id={pid}")
        if not found:
            print("  none")

        print("\nhow BetterStats knows each of those ids")
        for pid, nm in interesting.items():
            try:
                u = str(uuid.UUID(pid))
            except ValueError:
                print(f"  {nm!r} {pid}: not a UUID")
                continue
            rows = (await s.execute(text(
                "SELECT id::text AS id, COALESCE(display_name_override, name) AS name, grassroots_id, organisation_id::text AS org "
                "FROM players WHERE id = CAST(:u AS UUID) OR grassroots_id = :t"), {"u": u, "t": u})).mappings().all()
            merges = (await s.execute(text(
                "SELECT id, merged_at::text AS at, keep_player_name, keep_player_id::text AS keep_id, undone_at::text AS undone "
                "FROM merge_logs WHERE removed_player_id = CAST(:u AS UUID) ORDER BY merged_at"), {"u": u})).mappings().all()
            print(f"  {nm!r} {pid}")
            for r in rows:
                mark = "  <-- this player" if r["id"] == player_id else ""
                print(f"     player record: {r['name']} ({r['id']}) ca_id={r['grassroots_id']}{mark}")
            for m in merges:
                print(f"     merge #{m['id']} {m['at']}: this id was merged INTO {m['keep_player_name']} ({m['keep_id']})"
                      + (f" (undone {m['undone']})" if m['undone'] else ""))
            if not rows and not merges:
                print("     no player record and no merge: a name match would be the only link")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    asyncio.run(run(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    main()
