"""A club tags a match as a normal game, a final or the grand final, and premierships follow. Real Postgres.

Reported by a new club (Piara Waters): four or five premierships were never written automatically,
and typing them by hand left no link back to the match. Automatic premierships only read a round
Cricket Australia names "Grand Final" with a winner on the card.

Drives the SHIPPED route bodies (`routers/honours.put_match_tag`, `list_match_tags`, `get_match_tag`)
and `services/premierships` over a real Postgres:

  * a decider played as "Round 16" writes nothing today; tagged as the grand final from a pasted
    play.cricket.com.au link, everyone on our team sheet gets the flag, linked to the match;
  * a flag the club had typed for one of them is linked, not doubled;
  * a washed-out grand final with no winner says why it gives nothing, and "we won" writes the flags;
  * a match Cricket Australia calls "Grand Final" that the club tags as a final loses the automatic
    flags (they are ours to remove);
  * removing a tag takes back the automatic flags and unlinks the typed one, which stays;
  * a playhq.com link, junk, and another club's match are refused and change nothing;
  * every change writes an audit row.

Control run: against the previous commit the routes do not exist (read through getattr), so every
tag check fails and the before-state checks still pass.

Run:  DATABASE_URL=postgresql+asyncpg://root@/matchtags?host=/var/run/postgresql \
      python verification/verify_match_tags.py
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

from fastapi import HTTPException
from sqlalchemy import text

import verify_club_records as base   # its engine and build_schema (tables + effective views)
from app.models.db import Organisation, User
from app.routers import honours as honours_router
from app.services import premierships as prem

Session, engine, check = base.Session, base.engine, base.check

OURS, OTHER, THIRD = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
S, G, G2, S3, G3 = (uuid.uuid4() for _ in range(5))
G_R16, G_WASH, G_MISLABEL, G_THIRD = (uuid.uuid4() for _ in range(4))
USER = uuid.uuid4()
P = {k: uuid.uuid4() for k in ("ann", "ben", "cal", "dee", "foe")}
NAME = {"ann": "Ann Able", "ben": "Ben Bold", "cal": "Cal Cole", "dee": "Dee Dunn", "foe": "Fred Foe"}

put_tag = getattr(honours_router, "put_match_tag", None)
list_tags = getattr(honours_router, "list_match_tags", None)
get_tag = getattr(honours_router, "get_match_tag", None)


async def schema() -> None:
    await base.build_schema()
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID, player_name TEXT NOT NULL,
                season TEXT, category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL,
                detail TEXT, created_at TIMESTAMPTZ DEFAULT NOW())"""))
        for col in ("season_end TEXT", "import_batch_id UUID", "club_role_id UUID"):
            await conn.execute(text(f"ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS {col}"))
        from app.services.premierships_ddl import STATEMENTS as PREM_DDL
        from app.services.junior_hiding_ddl import STATEMENTS as JUNIOR_DDL
        from app.services.audit_ddl import STATEMENTS as AUDIT_DDL
        try:
            from app.services.stand_breaks_ddl import STATEMENTS as TAG_DDL
        except ImportError:   # control run
            TAG_DDL = []
        for stmt in list(PREM_DDL) + list(JUNIOR_DDL) + list(AUDIT_DDL) + list(TAG_DDL):
            await conn.execute(text(stmt))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for oid, name, slug in ((OURS, "Piara Waters CC", "piara"), (OTHER, "Rivals CC", "rivals"),
                                (THIRD, "Third CC", "third")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=name, s=slug)
        await ex("INSERT INTO users (id, username, display_name, failed_login_count) VALUES (:i, 'admin', 'Club Admin', 0)", i=USER)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, '2025/26', 2025)", i=S, o=OURS)
        await ex("INSERT INTO grades (id, season_id, name) VALUES (:i, :s, 'Women''s A Grade')", i=G, s=S)
        await ex("INSERT INTO grades (id, season_id, name) VALUES (:i, :s, 'Women''s T20')", i=G2, s=S)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, '2025/26', 2025)", i=S3, o=THIRD)
        await ex("INSERT INTO grades (id, season_id, name) VALUES (:i, :s, 'A Grade')", i=G3, s=S3)
        for k in ("ann", "ben", "cal", "dee"):
            await ex("INSERT INTO players (id, name, organisation_id) VALUES (:i, :n, :o)", i=P[k], n=NAME[k], o=OURS)
        await ex("INSERT INTO players (id, name, organisation_id) VALUES (:i, :n, :o)", i=P["foe"], n=NAME["foe"], o=OTHER)
        games = [  # id, grade, date, round, is_final, status, winner, home org, away org
            (G_R16, G, date(2026, 3, 14), "Round 16", False, "COMPLETED", "Piara Waters", OURS, OTHER),
            (G_WASH, G, date(2026, 3, 21), "Grand Final", True, "ABANDONED", None, OURS, OTHER),
            (G_MISLABEL, G2, date(2025, 12, 6), "Grand Final", True, "COMPLETED", "Piara Waters", OURS, OTHER),
            (G_THIRD, G3, date(2026, 3, 14), "Round 16", False, "COMPLETED", "Third", THIRD, OTHER),
        ]
        for gid, gr, d, rnd, fin, st, win, ho, ao in games:
            await ex("""
                INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, away_org_id,
                                   winning_team, is_final, status, round_name)
                VALUES (:i, :g, :d, :h, 'Rivals', :ho, :ao, :w, :f, :st, :r)""",
                     i=gid, g=gr, d=d, h="Third" if ho == THIRD else "Piara Waters", ho=ho, ao=ao, w=win,
                     f=fin, st=st, r=rnd)
        for gid in (G_R16, G_WASH, G_MISLABEL):
            # Ben has a typed Women's A Grade flag; he is kept off the T20 card so the one flag can only be the A Grade one.
            for k in (("ann", "cal") if gid == G_MISLABEL else ("ann", "ben", "cal")):
                await ex("INSERT INTO game_appearances (game_id, player_id, team_name, is_captain) VALUES (:g, :p, 'Piara Waters', :c)",
                         g=gid, p=P[k], c=(k == "ann"))
            await ex("INSERT INTO game_appearances (game_id, player_id, team_name) VALUES (:g, :p, 'Rivals')", g=gid, p=P["foe"])
        # What the club typed itself, before any of this: Dee's flag (she was not on the sheet) and Ben's.
        for k in ("ben", "dee"):
            await ex("""
                INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory, achievement)
                VALUES (:o, :p, :n, '2025/26', 'Premiership', 'Women''s A Grade', 'Premiership')""",
                     o=OURS, p=P[k], n=NAME[k])
        await s.commit()


async def flags(game=None) -> list[dict]:
    async with Session() as s:
        rows = (await s.execute(text("""
            SELECT player_id, player_name, linked_game_id, auto_created FROM player_achievements
             WHERE org_id = :o AND category = 'Premiership' AND achievement = 'Premiership'"""), {"o": OURS})).mappings().all()
    rows = [dict(r) for r in rows]
    return [r for r in rows if game is None or r["linked_game_id"] == game]


def who(rows) -> set:
    return {r["player_name"] for r in rows}


async def call(fn, **kw):
    if fn is None:
        return None, "missing"
    import inspect
    async with Session() as s:
        if "user" in inspect.signature(fn).parameters:
            kw["user"] = await s.get(User, USER)
        try:
            return await fn(db=s, club=Organisation(id=OURS), org_id=OURS, **kw), None
        except HTTPException as e:
            await s.rollback()
            return None, e


async def tag(match, kind, won=False):
    body = getattr(honours_router, "MatchTagIn", None)
    if body is None:
        return None, "missing"
    return await call(put_tag, body=body(match=match, kind=kind, won=won))


async def main() -> None:
    await schema()
    await seed()
    async with Session() as s:
        await prem.reconcile(s, OURS, apply=True)   # what the nightly sync does today

    print("Before any tag")
    check("the Round 16 decider gives no flag", await flags(G_R16) == [], str(await flags(G_R16)))
    check("the washed-out grand final gives no flag", await flags(G_WASH) == [], str(await flags(G_WASH)))
    check("the match CA calls Grand Final does (the automatic path works)",
          who(await flags(G_MISLABEL)) >= {"Ann Able", "Cal Cole"}, str(await flags(G_MISLABEL)))

    print("1. Tag the Round 16 decider from a pasted play.cricket.com.au link")
    res, err = await tag(f"https://play.cricket.com.au/match/{G_R16}/piara-waters-v-rivals", "grand_final")
    check("saves", err is None and res is not None, str(err))
    check("everyone of ours on the sheet holds the flag, linked to the match",
          who(await flags(G_R16)) == {"Ann Able", "Ben Bold", "Cal Cole"}, str(await flags(G_R16)))
    ben = [r for r in await flags() if r["player_name"] == "Ben Bold"]
    check("Ben's typed flag is the one linked (not doubled)",
          len([r for r in ben if r["linked_game_id"] == G_R16]) == 1
          and all(r["auto_created"] is False for r in ben if r["linked_game_id"] == G_R16), str(ben))
    check("the opposition player gets nothing", "Fred Foe" not in who(await flags()))
    check("the reply says three players", (res or {}).get("players") == 3 and (res or {}).get("kind") == "grand_final",
          str(res))
    res, err = await call(get_tag, game_id=G_R16) if get_tag else (None, "missing")
    check("the match page reads it", err is None and (res or {}).get("kind") == "grand_final", str(res or err))

    print("2. A washed-out grand final")
    res, err = await tag(str(G_WASH), "grand_final")
    check("tagged without 'we won': no flag, and the reason says what to do",
          await flags(G_WASH) == [] and "we won" in ((res or {}).get("reason") or ""), str(res))
    res, err = await tag(str(G_WASH), "grand_final", won=True)
    check("with 'we won' the flags are written", who(await flags(G_WASH)) == {"Ann Able", "Ben Bold", "Cal Cole"},
          str(await flags(G_WASH)))

    print("3. A match CA calls Grand Final that was not the decider")
    res, err = await tag(str(G_MISLABEL), "final")
    check("tagged as a final, its automatic flags go", [r for r in await flags(G_MISLABEL) if r["auto_created"]] == [],
          str(await flags(G_MISLABEL)))
    res, err = await call(list_tags) if list_tags else (None, "missing")
    tags = (res or {}).get("tags", [])
    check("the admin list shows the three tagged matches, newest first",
          [t["game_id"] for t in tags] == [str(G_WASH), str(G_R16), str(G_MISLABEL)], str(tags))
    check("each with its grade and what it gives",
          [t.get("grade_name") for t in tags] == ["Women's A Grade", "Women's A Grade", "Women's T20"]
          and tags[-1]["players"] == 0 and tags[1]["players"] == 3, str(tags))

    print("4. Refusals change nothing")
    before = await flags()
    for label, ref in (("a playhq.com link", "https://www.playhq.com/cricket-australia/org/x/y/z/game-centre/abc123"),
                       ("junk", "not a match"),
                       ("another club's match", str(G_THIRD))):
        res, err = await tag(ref, "grand_final", won=True)
        code = getattr(err, "status_code", None)
        check(f"{label}: refused ({code})", code in (404, 422), str(err))
    check("no honour changed", sorted(map(str, before), key=str) == sorted(map(str, await flags()), key=str))

    print("5. Removing a tag")
    res, err = await tag(str(G_R16), None)
    check("removes", err is None, str(err))
    check("the automatic flags from it go", [r for r in await flags(G_R16) if r["auto_created"]] == [],
          str(await flags(G_R16)))
    ben = [r for r in await flags() if r["player_name"] == "Ben Bold"]
    check("Ben's typed flag stays, unlinked from the match",
          any(r["auto_created"] is False and r["linked_game_id"] is None for r in ben), str(ben))
    async with Session() as s:
        n = (await s.execute(text("SELECT count(*) FROM audit_events WHERE action = 'match_tag'"))).scalar() \
            if put_tag else 0
    check("every change is on the audit trail (5 saves)", n == 5, str(n))

    print("6. A hand-typed partnership record linked to its match")
    from app.routers import club_admin
    from app.routers.records import get_records

    async def board_rows():
        async with Session() as s:
            p = await get_records(
                str(OURS), season_id=None, grade_id=None, grade_name=None, finals_only=False,
                captain_only=False, gender=None, categories="all", formats=None, competitions=None,
                debug_timing=False, db=s, viewer=None)
        return [r for r in p["partnerships"]["top_partnerships"] if r.get("is_manual")]

    async def admin(fn, **kw):
        async with Session() as s:
            user = await s.get(User, USER)
            try:
                return await fn(current_user=user, club=Organisation(id=OURS), db=s, **kw), None
            except HTTPException as e:
                await s.rollback()
                return None, e

    Create, Patch = club_admin.ManualPartnershipCreate, club_admin.ManualPartnershipPatch
    rec = dict(batter1_name="Ann Able", batter2_name="Ben Bold", grade_name="Women's A Grade",
               season_year=2025, wicket_number=8, runs=41, is_not_out=True)
    res, err = await admin(club_admin.create_partnership_record,
                           data=Create.model_validate({**rec, "match": f"https://play.cricket.com.au/match/{G_R16}"}))
    check("a record saves with a pasted match link", err is None, str(err))
    rows = await board_rows()
    check("on the Records board it opens that match, with its not-out mark",
          [(r["runs"], r.get("game_id"), r.get("not_out")) for r in rows] == [(41, str(G_R16), True)], str(rows))
    res, err = await admin(club_admin.create_partnership_record,
                           data=Create.model_validate({**rec, "runs": 39, "match": str(G_THIRD)}))
    check("another club's match is refused (422)", getattr(err, "status_code", None) == 422, str(err))
    res, err = await admin(club_admin.create_partnership_record, data=Create.model_validate({**rec, "runs": 38}))
    check("a record with no link still saves, and opens nothing",
          err is None and [r.get("game_id") for r in await board_rows() if r["runs"] == 38] == [None],
          str(await board_rows()))
    async with Session() as s:
        rid = (await s.execute(text("SELECT id FROM manual_partnership_records WHERE runs = 41"))).scalar()
        rid38 = (await s.execute(text("SELECT id FROM manual_partnership_records WHERE runs = 38"))).scalar()
    await admin(club_admin.patch_partnership_record, record_id=rid, data=Patch.model_validate({"notes": "v Rivals"}))
    check("an edit that does not send the link leaves it alone",
          [r.get("game_id") for r in await board_rows() if r["runs"] == 41] == [str(G_R16)])
    await admin(club_admin.patch_partnership_record, record_id=rid38, data=Patch.model_validate({"match": str(G_WASH)}))
    check("an edit can add a link", [r.get("game_id") for r in await board_rows() if r["runs"] == 38] == [str(G_WASH)])
    await admin(club_admin.patch_partnership_record, record_id=rid, data=Patch.model_validate({"match": None}))
    check("and sending it empty takes it off", [r.get("game_id") for r in await board_rows() if r["runs"] == 41] == [None])

    print()
    print(f"{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
