"""Verification for the sponsors a BetterPosts post starts with (migration 320),
against a real Postgres.

Runs the SHIPPED `services/post_sponsors.py`, `services/post_sponsors_ddl.py` and
the shipped route bodies in `routers/club_admin.py`: `get_post_defaults`,
`put_post_defaults` and `get_post_default`.

The club has a Major with a logo, a Gold with a logo, a Major with NO logo, a
Silver and a Supporter. A second club's sponsor guards against a leak. Every
"X is not chosen" check is paired with a check that X IS chosen elsewhere, so a
check cannot pass by choosing nothing (rule 21).

CONTROL MODE. Run against the commit BEFORE this change the service does not
exist; it is read through find_spec and new keys through presence-safe
accessors, so the control reports the missing behaviour as failed checks.

Run:  DATABASE_URL=postgresql+asyncpg://root@/postsp_test?host=/var/run/postgresql \
      python verification/verify_post_sponsors.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, ClubMembership, Organisation, Sponsor, User
from app.routers import club_admin as ca

HAVE = importlib.util.find_spec("app.services.post_sponsors") is not None
if HAVE:
    from app.services import post_sponsors as ps
    from app.services.post_sponsors_ddl import STATEMENTS as DDL
else:
    ps = None
    DDL = []

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


OURS, OTHER = uuid.uuid4(), uuid.uuid4()
ID = {k: uuid.uuid4() for k in ("major", "gold", "major_nologo", "silver", "supporter", "other")}
LOGO = "/images/sponsors/x/logo"


async def http_status(coro):
    try:
        await coro
    except HTTPException as e:
        return e.status_code
    return None


def sid(k: str) -> str:
    return str(ID[k])


async def call(fn, db, club, **kw):
    kw.setdefault("current_user", None)
    return await fn(club=club, db=db, **kw)


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS grade_merge_logs (
            id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
            org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
            alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))

    print("== migration DDL")
    if HAVE:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE organisations DROP COLUMN post_sponsor_defaults"))
            for _ in range(2):
                for stmt in DDL:
                    await conn.execute(text(stmt))
            n = (await conn.execute(text(
                "SELECT count(*) FROM information_schema.columns WHERE table_name='organisations' AND column_name='post_sponsor_defaults'"))).scalar()
            check("the column is added and the DDL list is idempotent", n == 1)
    else:
        check("the DDL module exists", False)

    async with engine.begin() as conn:
        for oid, name, slug in ((OURS, "Our Club", "ourclub"), (OTHER, "Other Club", "other")):
            await conn.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i,:n,:s,true)"),
                               {"i": oid, "n": name, "s": slug})
        season = uuid.uuid4()
        await conn.execute(text("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i,:o,'Summer 2026/27',2026)"), {"i": season, "o": OURS})
        for gname in ("A Grade", "Under 14 Boys"):
            await conn.execute(text("INSERT INTO grades (id, season_id, name) VALUES (:i,:s,:n)"), {"i": uuid.uuid4(), "s": season, "n": gname})
        for tname, seq in (("1st XI", 1), ("2nd XI", 2)):
            await conn.execute(text("INSERT INTO teams (id, organisation_id, name, sequence, is_active, source) VALUES (:i,:o,:n,:q,true,'manual')"),
                               {"i": uuid.uuid4(), "o": OURS, "n": tname, "q": seq})
        for key, org, name, order, tier, logo in (
            ("major", OURS, "Big Major", 1, "major", LOGO),
            ("gold", OURS, "Gold Co", 2, "gold", LOGO),
            ("major_nologo", OURS, "Logoless Major", 3, "major", None),
            ("silver", OURS, "Silver Co", 4, "silver", LOGO),
            ("supporter", OURS, "Small Supporter", 5, "supporter", LOGO),
            ("other", OTHER, "Other Sponsor", 1, "major", LOGO),
        ):
            await conn.execute(text(
                "INSERT INTO org_sponsors (id, organisation_id, name, display_order, logo_url, tier) VALUES (:i,:o,:n,:d,:l,:t)"),
                {"i": ID[key], "o": org, "n": name, "d": order, "l": logo, "t": tier})

    print("== service")
    async with Session() as db:
        club = (await db.execute(select(Organisation).where(Organisation.id == OURS))).scalar_one()
        rows = list((await db.execute(select(Sponsor).where(Sponsor.organisation_id == OURS).order_by(Sponsor.display_order))).scalars().all())
        if HAVE:
            mine = [str(s.id) for s in rows]
            check("club default: Major and Gold with logos, tier order",
                  ps.club_default_ids(rows) == [sid("major"), sid("gold")], str(ps.club_default_ids(rows)))
            check("club default: a Major with no logo is never chosen (it cannot be drawn)", sid("major_nologo") not in ps.club_default_ids(rows))
            silver_only = [s for s in rows if s.tier in ("silver", "supporter")]
            check("club default: with no Major or Gold, falls back to the top sponsor with a logo",
                  ps.club_default_ids(silver_only) == [sid("silver")], str(ps.club_default_ids(silver_only)))
            check("club default: a club with nothing drawable gets nothing", ps.club_default_ids([s for s in rows if not s.logo_url]) == [])
            gold = next(s for s in rows if s.tier == "gold")
            gold.placements = {"posts": False}
            check("club default: a hand-set switch takes a sponsor off", ps.club_default_ids(rows) == [sid("major")], str(ps.club_default_ids(rows)))
            sup = next(s for s in rows if s.tier == "supporter")
            sup.placements = {"posts": True}
            check("club default: a hand-set switch puts a supporter on",
                  ps.club_default_ids(rows) == [sid("major"), sid("supporter")], str(ps.club_default_ids(rows)))
            gold.placements = None
            sup.placements = None

            pins = ps.clean_assignments({"teams": {"  1st   XI ": [sid("silver"), sid("silver"), sid("other"), "junk"]},
                                         "grades": {"A Grade": [sid("gold")], "Empty": []}}, mine)
            check("pins: duplicates and another club's sponsor are dropped",
                  pins["teams"]["1st xi"]["sponsor_ids"] == [sid("silver")], str(pins))
            check("pins: a name with no sponsors left is not stored", "empty" not in pins["grades"])
            check("pins: the display name is kept tidy", pins["teams"]["1st xi"]["name"] == "1st XI")
            check("pins: an unknown kind is refused", _raises(lambda: ps.clean_assignments({"squads": {"x": [sid("gold")]}}, mine)))
            check("pins: nothing left reads NULL", ps.clean_assignments({"teams": {"x": ["nope"]}}, mine) is None)
            nine = [str(uuid.uuid4()) for _ in range(9)]
            capped = ps.clean_assignments({"teams": {"t": nine}}, nine)["teams"]["t"]["sponsor_ids"]
            check("pins: each pin is capped at 6, keeping the first six in order", capped == nine[:6], str(len(capped)))

            ids, src = ps.resolve(pins, rows, team="1st XI", grade="A Grade")
            check("resolve: the team's pin wins over the grade's", (ids, src) == ([sid("silver")], "team"), f"{ids} {src}")
            ids, src = ps.resolve(pins, rows, team="3rd XI", grade="a  grade")
            check("resolve: the grade's pin is used when the team has none (case and spaces ignored)", (ids, src) == ([sid("gold")], "grade"), f"{ids} {src}")
            ids, src = ps.resolve(pins, rows, team="3rd XI", grade="B Grade")
            check("resolve: nothing pinned falls to the club default", (ids, src) == ([sid("major"), sid("gold")], "club"), f"{ids} {src}")
            ids, src = ps.resolve(None, silver_only, team="x", grade="y")
            check("resolve: a club with no Major or Gold reports its top sponsor", (ids, src) == ([sid("silver")], "top"), f"{ids} {src}")
            ids, src = ps.resolve(None, [], team="x", grade="y")
            check("resolve: no sponsors at all is none", (ids, src) == ([], "none"))
            stale = {"teams": {"1st xi": {"name": "1st XI", "sponsor_ids": [str(uuid.uuid4())]}}}
            ids, src = ps.resolve(stale, rows, team="1st XI")
            check("resolve: a pin to a deleted sponsor falls through to the default", src == "club", f"{ids} {src}")
            nologo = {"teams": {"1st xi": {"name": "1st XI", "sponsor_ids": [sid("major_nologo")]}}}
            ids, src = ps.resolve(nologo, rows, team="1st XI")
            check("resolve: a pin to a sponsor with no logo falls through", src == "club" and sid("major_nologo") not in ids, f"{ids} {src}")
        else:
            check("the post_sponsors service exists", False)

    print("== admin routes")
    async with Session() as db:
        club = (await db.execute(select(Organisation).where(Organisation.id == OURS))).scalar_one()
        if HAVE:
            view = await call(ca.get_post_defaults, db, club)
            check("options list the club's teams in order", view["options"]["teams"] == ["1st XI", "2nd XI"], str(view["options"]))
            check("options list the club's grades", view["options"]["grades"] == ["A Grade", "Under 14 Boys"], str(view["options"]))
            check("nothing is pinned to start with", view["assignments"] == {"teams": {}, "grades": {}}, str(view["assignments"]))
            check("the club default is reported", view["club_default_ids"] == [sid("major"), sid("gold")], str(view["club_default_ids"]))

            body = ca.PostDefaultsPut(teams={"1st XI": [sid("silver"), sid("other")]}, grades={"A Grade": [sid("gold")]})
            view = await call(ca.put_post_defaults, db, club, data=body)
            check("a save pins the team and the grade", view["assignments"] == {"teams": {"1st XI": [sid("silver")]}, "grades": {"A Grade": [sid("gold")]}}, str(view["assignments"]))
            check("another club's sponsor was dropped on save", sid("other") not in str(view["assignments"]))
            r = await call(ca.get_post_default, db, club, team="1st XI", grade="B Grade")
            check("the route answers a team with its pin", r == {"sponsor_ids": [sid("silver")], "source": "team"}, str(r))
            r = await call(ca.get_post_default, db, club, team="2nd XI", grade="A Grade")
            check("the route answers a grade with its pin", r == {"sponsor_ids": [sid("gold")], "source": "grade"}, str(r))
            r = await call(ca.get_post_default, db, club, team="2nd XI", grade="B Grade")
            check("the route answers anything else with the club default", r["source"] == "club" and r["sponsor_ids"] == [sid("major"), sid("gold")], str(r))
            r = await call(ca.get_post_default, db, club, team=None, grade=None)
            check("the route answers a post with no team or grade", r["source"] == "club", str(r))

            view = await call(ca.put_post_defaults, db, club, data=ca.PostDefaultsPut(teams={}, grades={"A Grade": [sid("gold")]}))
            check("a save replaces the pins (the team's is gone)", view["assignments"]["teams"] == {} and view["assignments"]["grades"] == {"A Grade": [sid("gold")]}, str(view["assignments"]))
            view = await call(ca.put_post_defaults, db, club, data=ca.PostDefaultsPut())
            check("an empty save clears every pin", view["assignments"] == {"teams": {}, "grades": {}}, str(view["assignments"]))

            await call(ca.put_post_defaults, db, club, data=ca.PostDefaultsPut(teams={"1st XI": [sid("silver")]}))
            await db.execute(text("DELETE FROM org_sponsors WHERE id=:i"), {"i": ID["silver"]})
            await db.commit()
            view = await call(ca.get_post_defaults, db, club)
            check("a deleted sponsor drops out of the pins on read", view["assignments"]["teams"] == {}, str(view["assignments"]))

            dep = inspect.signature(ca.put_post_defaults).parameters["current_user"].default.dependency
            uid_no, uid_yes = uuid.uuid4(), uuid.uuid4()
            db.add(User(id=uid_no, username="nocap", email="a@b.co", password_hash="x"))
            db.add(User(id=uid_yes, username="hascap", email="c@d.co", password_hash="x"))
            await db.flush()
            db.add(ClubMembership(club_id=OURS, user_id=uid_no, role="club_member", capabilities=[]))
            db.add(ClubMembership(club_id=OURS, user_id=uid_yes, role="club_member", capabilities=["manage_sponsors"]))
            await db.commit()
            check("pinning without manage_sponsors is refused", await http_status(dep(current_user=await db.get(User, uid_no), db=db)) == 403)
            yes = await db.get(User, uid_yes)
            check("pinning with manage_sponsors passes", (await dep(current_user=yes, db=db)) is yes)
        else:
            check("the post-defaults routes exist", hasattr(ca, "put_post_defaults"))

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        print("FAILED:\n  - " + "\n  - ".join(FAILURES))
        sys.exit(1)


def _raises(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


if __name__ == "__main__":
    asyncio.run(main())
