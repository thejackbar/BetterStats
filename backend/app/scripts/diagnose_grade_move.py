"""Why did Sync fixtures not move a team that Cricket Australia put in another grade? Read only.

Runs the same fetch the Sync fixtures button runs (fresh match lists, one call per
current grade, the client paces them) and then, for each stored synced fixture that
CA no longer lists, says what `fixtures_reconcile` would do with it and why:

  * which grades were read, and whether any failed (a grade that failed to load
    leaves its fixtures alone);
  * the grades the club holds: a team CA moved into a grade we do not hold yet is
    invisible to the sync until Sync Now has created that grade;
  * each stored fixture CA no longer lists (stale or already CANCELLED): date,
    grade, our team name, squad, and whether an XI, draft, votes or a note sit on it;
  * the games CA lists that day in a DIFFERENT grade for the club, with the team name
    CA gives, and the verdict: moves, or the reason it does not (no game that day,
    team name differs, more than one row or game that day, grade unknown to us).

Writes nothing.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -m app.scripts.diagnose_grade_move <org-id-or-slug> ["8th XI"]

The optional second argument keeps only the STORED rows whose team name contains it. Every game CA lists
for the club on those days is shown, so a team CA has renamed can be seen.
"""
import asyncio
import sys
import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy import select, text

from app.models.db import Fixture, Organisation, Team, async_session_maker
from app.routers.fixtures import _derive_all_sides
from app.services import fixtures_reconcile as fr
from app.services import grade_move
from app.services.fixtures_source import _current_grade_rows, org_grassroots_fixtures_checked


async def run(ref: str, only: str | None) -> None:
    async with async_session_maker() as db:
        try:
            club = await db.get(Organisation, uuid.UUID(ref))
        except ValueError:
            club = (await db.execute(select(Organisation).where(Organisation.slug == ref))).scalars().first()
        if club is None:
            raise SystemExit("No such club")
        today = date.today()
        print(f"{club.name}  today {today}")

        held = await _current_grade_rows(db, club.id)
        print("\ngrades we hold for the latest season (the sync reads only these)")
        for guid, gid, gname, sname in sorted(held, key=lambda r: str(r[2])):
            print(f"  {gname:<32} {sname}  our id {gid}")

        games, listing = await org_grassroots_fixtures_checked(db, club, force=True)
        print(f"\ngrades read ok: {len(listing['grades'])}   failed to load: {listing['failed']}")
        incoming = {str(g['id']) for g in games if g.get("id") and g.get("played_at")}

        rows = list((await db.execute(select(Fixture).where(Fixture.organisation_id == club.id))).scalars().all())
        squads = {str(t.id): t.name for t in (await db.execute(
            select(Team).where(Team.organisation_id == club.id))).scalars().all()}
        grade_name = {str(g[1]): g[2] for g in held}
        gname_all = {str(r[0]): r[1] for r in (await db.execute(text(
            "SELECT gr.id, gr.name FROM grades gr JOIN seasons s ON s.id = gr.season_id "
            "WHERE s.organisation_id = :o"), {"o": club.id})).fetchall()}

        stale = fr.find_stale(rows, incoming, listing, today)
        movable = fr.find_moved(rows, incoming, stale, today)
        work = await fr.fixtures_with_work(db, movable)

        def keep(name: str) -> bool:
            return not only or only.lower() in (name or "").lower()

        print(f"\nstored synced fixtures CA no longer lists ({len(movable)}); stale = CA dropped it, "
              "cancelled = already CANCELLED")
        stale_ids = {str(f.id) for f in stale}
        shown = []
        for f in sorted(movable, key=lambda f: (f.played_on, f.id)):
            ours = grade_move.our_side_name(f.home_away, f.home_team, f.away_team)
            if not keep(ours):
                continue
            shown.append(f)
            tag = "stale" if str(f.id) in stale_ids else "cancelled"
            print(f"  {f.played_on}  {tag:<9} grade={gname_all.get(str(f.grade_id), '?'):<26} team={ours!r}  "
                  f"squad={squads.get(str(f.team_id), '-')!r}  vs {f.opponent_name!r}  "
                  f"{'HAS WORK' if str(f.id) in work else 'empty'}")
        if not shown:
            print("  none for that team: either CA still lists them in the old grade, or the old grade "
                  "failed to load, or they were already removed.")

        by_key = defaultdict(list)
        for f in shown:
            ours = grade_move.our_side_name(f.home_away, f.home_team, f.away_team)
            if f.played_on and ours and f.grade_id:
                by_key[(f.played_on, ours)].append(f)

        print("\nwhat CA lists for the club on those days")
        for day in sorted({k[0] for k in by_key} | {f.played_on for f in shown}):
            cands = []
            for g in games:
                if not g.get("id") or not g.get("played_at") or str(g["played_at"])[:10] != day.isoformat():
                    continue
                sides = _derive_all_sides(g, club)
                for ha, opp in sides:
                    ours = grade_move.our_side_name(ha, g.get("home_team"), g.get("away_team"))
                    cands.append((g, ours, len(sides), opp))   # every team of the club: a renamed team must show
            print(f"  {day}")
            for g, ours, n, opp in cands:
                known = "grade known" if g.get("db_grade_id") else "GRADE NOT HELD (run Sync Now)"
                print(f"     {g.get('grade_name') or '?':<26} team={ours!r}  vs {opp!r}"
                      f"  [{known}]{'  in-house' if n > 1 else ''}  id {g['id']}")
            for (d, ours), rs in by_key.items():
                if d != day:
                    continue
                same = [c for c in cands if c[1] == ours and c[0].get("db_grade_id")
                        and str(c[0]["db_grade_id"]) != str(rs[0].grade_id) and c[2] == 1]
                if len(rs) != 1:
                    verdict = f"NOT MOVED: {len(rs)} stored rows for {ours!r} that day (never guessed)"
                elif len(same) == 1:
                    verdict = f"MOVES onto {same[0][0]['id']} in {same[0][0].get('grade_name')}"
                elif len(same) > 1:
                    verdict = "NOT MOVED: more than one game that day for that team (never guessed)"
                else:
                    others = [c for c in cands if c[0].get("db_grade_id")
                              and str(c[0]["db_grade_id"]) != str(rs[0].grade_id)]
                    if not cands:
                        verdict = "NOT MOVED: CA lists no game for the club that day"
                    elif not others:
                        verdict = ("NOT MOVED: the day's games are in the grade we hold for it or in a grade "
                                   "we do not hold (run Sync Now first)")
                    else:
                        names = ", ".join(sorted({c[1] for c in others}))
                        verdict = (f"NOT MOVED: no game in another grade under the team name {ours!r}; "
                                   f"CA names the team {names} that day")
                print(f"     -> row {rs[0].id}: {verdict}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    asyncio.run(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
