"""Head to head: our past results against one opponent, for BetterPosts.

Asked for (November 2026): past results against the opponent on the Head to Head
post and the other match-day layouts. Runs the SHIPPED route body
(`admin.get_social_head_to_head`) over `v_effective_games` on a real Postgres.

The traps it is written against:
  * A fixture between two synced clubs is ONE games row. When the opponent synced
    it first, the row sits in THEIR season and its `result` reads 'WIN' from THEIR
    side. It must count, and as our LOSS (re-derived from `winning_team`).
  * A tie has no winner: taken from the symmetric result word.
  * A hand-typed game spells the club differently ("Subiaco Floreat Cricket Club")
    and must still be the same opponent.
  * Another club's game, a future fixture and a game between two other clubs never
    count. A grade narrows the record.
  * A name that fits two clubs equally ("Perth": North Perth, South Perth) is not
    guessed.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:5433/bstest \
  python verification/verify_social_head_to_head.py
Control: against the previous commit the route does not exist; every check reports
FAIL (read through a presence-safe accessor) instead of crashing.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_records_timing as base
from app.routers import admin as admin_router
from app.services import superseded_ddl

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {label}")
    else:
        FAIL += 1
        print(f"FAIL {label}" + (f"  {detail}" if detail else ""))


U = lambda n: uuid.UUID(f"5a000000-0000-0000-0000-{n:012d}")
ORG, SUBI, GOS, NP, SP = U(1), U(2), U(3), U(4), U(5)
S_OURS, S_SUBI, S_GOS = U(11), U(12), U(13)
G_A, G_B, G_SUBI_A, G_GOS = U(21), U(22), U(23), U(24)
today = date.today()
D = lambda days: today - timedelta(days=days)


async def seed() -> None:
    async with base.Session() as s:
        ex = lambda q, **kw: s.execute(text(q), kw)
        for oid, name, short, slug in ((ORG, "Willetton Cricket Club", "Willetton", "willetton"),
                                       (SUBI, "Subiaco-Floreat Cricket Club", "Subiaco-Floreat", "subi"),
                                       (GOS, "Gosnells Cricket Club", "Gosnells", "gos"),
                                       (NP, "North Perth Cricket Club", "North Perth", "np"),
                                       (SP, "South Perth Cricket Club", "South Perth", "sp")):
            await ex("INSERT INTO organisations (id, name, short_name, slug, is_active) VALUES (:i, :n, :s, :g, true)", i=oid, n=name, s=short, g=slug)
        for sid, org in ((S_OURS, ORG), (S_SUBI, SUBI), (S_GOS, GOS)):
            await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, '2025-26', 2025)", i=sid, o=org)
        for gid, sid, nm in ((G_A, S_OURS, 'A Grade'), (G_B, S_OURS, 'B Grade'), (G_SUBI_A, S_SUBI, 'A Grade'), (G_GOS, S_GOS, 'A Grade')):
            await ex("INSERT INTO grades (id, season_id, name) VALUES (:i, :s, :n)", i=gid, s=sid, n=nm)

        async def game(n, grade, days, home, away, home_org, away_org, winner, result, status='COMPLETED'):
            await ex("""INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_club, away_club,
                        home_org_id, away_org_id, winning_team, result, status, is_final)
                        VALUES (:i, :g, :d, :h, :a, :h, :a, :ho, :ao, :w, :r, :st, false)""",
                     i=U(100 + n), g=grade, d=D(days), h=home, a=away, ho=home_org, ao=away_org, w=winner, r=result, st=status)
        # 1. Ours, at home, we won.
        await game(1, G_A, 10, 'Willetton 1st XI', 'Subiaco-Floreat 1st XI', ORG, None, 'Willetton 1st XI', 'WIN')
        # 2. Shared: Subiaco synced it first, so it is in THEIR season and result is THEIR 'WIN'.
        await game(2, G_SUBI_A, 40, 'Subiaco-Floreat 1st XI', 'Willetton 1st XI', SUBI, ORG, 'Subiaco-Floreat 1st XI', 'WIN')
        # 3. A tie, no winner.
        await game(3, G_A, 70, 'Willetton 1st XI', 'Subiaco-Floreat 1st XI', ORG, None, None, 'TIE')
        # 4. Ours against another club.
        await game(4, G_A, 20, 'Willetton 1st XI', 'Gosnells 1st XI', ORG, None, 'Gosnells 1st XI', 'LOSS')
        # 6. Ours in another grade, we won.
        await game(6, G_B, 15, 'Willetton 2nd XI', 'Subiaco-Floreat 2nd XI', ORG, None, 'Willetton 2nd XI', 'WIN')
        # 7. A future fixture.
        await game(7, G_A, -7, 'Willetton 1st XI', 'Subiaco-Floreat 1st XI', ORG, None, None, None, 'UPCOMING')
        # 8. Between two other clubs, in Gosnells' season.
        await game(8, G_GOS, 12, 'Gosnells 1st XI', 'Subiaco-Floreat 1st XI', GOS, SUBI, 'Gosnells 1st XI', 'WIN')
        # 9/10. Two clubs that share the word Perth.
        await game(9, G_A, 30, 'Willetton 1st XI', 'North Perth 1st XI', ORG, None, 'Willetton 1st XI', 'WIN')
        await game(10, G_A, 31, 'South Perth 1st XI', 'Willetton 1st XI', None, ORG, 'South Perth 1st XI', 'LOSS')
        # 5. Hand-typed, the club spelled another way, our word for the result.
        await ex("""INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, home_team, away_team,
                    opposition, winning_team, result, is_final)
                    VALUES (:i, :o, :s, :g, :d, 'Willetton', 'Subiaco Floreat', 'Subiaco Floreat Cricket Club', NULL, 'WIN', false)""",
                 i=U(105), o=ORG, s=S_OURS, g=G_A, d=D(100))
        await s.commit()


async def h2h(opponent: str, grade: str = "") -> dict:
    fn = getattr(admin_router, "get_social_head_to_head", None)
    if fn is None:
        return {}
    club = SimpleNamespace(id=str(ORG), name="Willetton Cricket Club", short_name="Willetton", playhq_id=None, workspace_kind=None)
    async with base.Session() as s:
        return await fn(opponent=opponent, grade=grade, db=s, club=club)


async def main() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))
    await seed()

    r = await h2h("SUBIACO-FLOREAT 1ST XI")
    g = r.get
    check("the opponent is found from a ladder-style name", g("found") is True and "Subiaco" in (g("opponent") or ""), str(r)[:200])
    check("five meetings: two grades, synced and hand-typed, past games only", g("meetings") == 5, str(g("meetings")))
    check("three wins, one loss, one tie", (g("wins"), g("losses"), g("ties")) == (3, 1, 1), str((g("wins"), g("losses"), g("ties"))))
    rec = g("recent") or []
    shared = next((x for x in rec if x.get("home_away") == "AWAY" and x.get("their_team", "").startswith("Subiaco") and x.get("outcome") == "L"), None)
    check("the shared fixture in their season counts, as OUR loss (their result said WIN)", shared is not None, str([(x.get('played_at'), x.get('outcome')) for x in rec]))
    check("the tie with no winner reads as a tie", any(x.get("outcome") == "T" for x in rec))
    check("the hand-typed game with another spelling is the same club, and a win", any(x.get("source") == "manual" and x.get("outcome") == "W" for x in rec))
    check("newest first, and the future fixture is not in it", [x.get("played_at") for x in rec] == sorted([x.get("played_at") for x in rec], reverse=True) and all(x.get("played_at") <= today.isoformat() for x in rec))
    check("form is the last five decided, newest first", g("form") == ["W", "W", "L", "T", "W"], str(g("form")))
    check("a game against another club never counts", not any("Gosnells" in (x.get("their_team") or "") for x in rec))

    a = await h2h("Subiaco-Floreat", "A Grade")
    check("a grade narrows it: four A Grade meetings, the B Grade win left out", a.get("meetings") == 4 and a.get("wins") == 2, str((a.get("meetings"), a.get("wins"))))

    amb = await h2h("Perth")
    check("a name that fits two clubs equally is not guessed", amb.get("found") is False and amb.get("meetings") == 0, str(amb)[:160])
    one = await h2h("North Perth")
    check("and the full name picks the right one", one.get("found") is True and one.get("meetings") == 1 and one.get("wins") == 1, str(one)[:160])

    none = await h2h("Never Played CC")
    check("a club we have never played says so, with no record", none.get("found") is False and none.get("meetings") == 0 and none.get("reason"), str(none)[:160])

    print(f"\n{PASS} passed, {FAIL} failed")
    await base.engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
