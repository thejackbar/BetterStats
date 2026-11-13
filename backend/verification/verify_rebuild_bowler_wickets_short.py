"""rebuild_bowler_wickets --short / --force pick the right games.

The default selection (games with no caught_behind value stored) skips every game a club has
already been through, so a parser change never reached them. `--short` picks the games where the
card's stored fielding totals exceed the catches and stumpings paired to a fielder, or where a
catch or stumping has no fielder; `--force` picks every game of the club.

  S1  stumping credited, no pairing held                      -> picked
  S2  stumping credited and paired                            -> not picked
  S3  caught-and-bowled only (fielding row counts it)         -> not picked
  S4  a caught with no fielder, fielding totals agree         -> picked
  S5  catch credited, pairing held, one more credit missing   -> picked
  S6  another club's game with a shortfall                    -> never picked

Run:  DATABASE_URL=postgresql+asyncpg://root@/pl_verify?host=/var/run/postgresql \
      python verification/verify_rebuild_bowler_wickets_short.py
Control: CONTROL=1 uses the default selection, which skips S4 and S5 (their rows already carry the flag).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_records_partnership_grade_names as base
from app.scripts import rebuild_bowler_wickets as rb

check = base.check
ORG, OPP = base.ORG, base.OPP


async def main() -> None:
    await base.build_schema()
    A, B, K = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    games = {}
    async with base.Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for oid, nm, sl in ((ORG, "Us CC", "us"), (OPP, "Them CC", "them")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i,:n,:s,true)", i=oid, n=nm, s=sl)
        seasons = {}
        for oid in (ORG, OPP):
            sid, gid = uuid.uuid4(), uuid.uuid4()
            seasons[oid] = gid
            await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:s,:o,'S 2025',2025)", s=sid, o=oid)
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:g,:s,'1st',:x,'senior',ARRAY['senior'])", g=gid, s=sid, x=str(gid))
        for pid, org in ((A, ORG), (B, ORG), (K, ORG)):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:p,:o,:n,:g,'active')",
                     p=pid, o=org, n=str(pid)[:6], g=str(pid))

        async def game(label, org=ORG):
            g = uuid.uuid4()
            games[label] = g
            await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, status) "
                     "VALUES (:g,:gr,:d,'Us','Them','COMPLETED')", g=g, gr=seasons[org], d=date(2025, 10, 1))
            return g

        async def field(g, st=0, ct=0, who=K):
            await ex("INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, run_outs, stumpings) "
                     "VALUES (:g,:p,:c,0,0,:s)", g=g, p=who, c=ct, s=st)

        async def wicket(g, dt, fielder):
            await ex("INSERT INTO bowler_wickets (game_id, innings_number, bowler_id, fielder_id, batter_name, dismissal_type) "
                     "VALUES (:g,1,:b,:f,'X',:d)", g=g, b=A, f=fielder, d=dt)
            # A club already through a rebuild has the flag set on every row, which is what the
            # default selection (no flag stored yet) skips.
            await ex("UPDATE bowler_wickets SET caught_behind = FALSE WHERE game_id = :g", g=g)

        g = await game("S1"); await field(g, st=1)
        g = await game("S2"); await field(g, st=1); await wicket(g, "stumped", K)
        g = await game("S3"); await field(g, ct=1, who=A); await wicket(g, "caught and bowled", None)
        g = await game("S4"); await field(g, ct=1); await wicket(g, "caught", None)
        g = await game("S5"); await field(g, ct=2); await wicket(g, "caught", K)
        g = await game("S6", OPP); await field(g, st=1)
        await s.commit()

    async def picked(sql):
        async with base.Session() as s:
            ids = {r[0] for r in (await s.execute(text(sql), {"org_id": str(ORG)})).all()}
        return {k for k, v in games.items() if v in ids}

    sql = rb._ALL_GAMES_SQL if False else (rb._SHORT_GAMES_SQL if not os.environ.get("CONTROL") else
        "SELECT DISTINCT g.id FROM games g JOIN grades gr ON gr.id=g.grade_id JOIN seasons s ON s.id=gr.season_id "
        "WHERE s.organisation_id = :org_id AND NOT EXISTS (SELECT 1 FROM bowler_wickets bw WHERE bw.game_id = g.id "
        "AND bw.caught_behind IS NOT NULL)")
    got = await picked(sql)
    print("\n-- --short --")
    check("picks the game with a credited stumping and no pairing (S1)", "S1" in got, str(sorted(got)))
    check("picks the game with a catch that has no fielder (S4)", "S4" in got, str(sorted(got)))
    check("picks the game one credit short (S5)", "S5" in got, str(sorted(got)))
    check("leaves a fully paired game (S2)", "S2" not in got, str(sorted(got)))
    check("leaves a game that is only a caught-and-bowled (S3)", "S3" not in got, str(sorted(got)))
    check("never picks another club's game (S6)", "S6" not in got, str(sorted(got)))

    allg = await picked(rb._ALL_GAMES_SQL)
    print("\n-- --force --")
    check("every game of the club, none of another's", allg == {"S1", "S2", "S3", "S4", "S5"}, str(sorted(allg)))
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
