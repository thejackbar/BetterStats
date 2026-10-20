"""Verification for a club's own section names, linked to a sponsor (migration 319),
against a real Postgres.

Runs the SHIPPED `services/section_names.py`, `services/section_names_ddl.py` and
the shipped route bodies: the public sponsors endpoint, the club admin
section-names routes, the fantasy landing and the og_preview club card.

The club under test renames Fantasy ("Froth Fantasy Cricket", linked to a sponsor
with a logo) and the Leaderboard (name only), links a sponsor to Records with no
name, and leaves Compare alone. Every "X is not renamed" check is paired with a
check that a renamed section IS renamed, so a check cannot pass by renaming
nothing (rule 21).

CONTROL MODE. Run against the commit BEFORE this change the service does not
exist; it is read through find_spec and new keys through presence-safe accessors,
so the control reports the missing behaviour as failed checks and does not crash.

Run:  DATABASE_URL=postgresql+asyncpg://root@/sections_test?host=/var/run/postgresql \
      python verification/verify_section_names.py
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
from starlette.requests import Request

from app.models.db import Base, ClubMembership, Organisation, Sponsor, User
from app.routers import club_admin as ca
from app.routers import clubs as clubs_router
from app.routers import og_preview
from app.routers import public_fantasy

HAVE = importlib.util.find_spec("app.services.section_names") is not None
if HAVE:
    from app.services import section_names as sn
    from app.services.section_names_ddl import STATEMENTS as DDL
else:
    sn = None
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
S_FROTH, S_BANK, S_NOLOGO, S_OTHER = (uuid.uuid4() for _ in range(4))


def request() -> Request:
    return Request({"type": "http", "headers": [], "query_string": b""})


async def http_status(coro):
    try:
        await coro
    except HTTPException as e:
        return e.status_code
    return None


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    print("== migration DDL")
    if HAVE:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE organisations DROP COLUMN section_names"))
            for stmt in DDL:
                await conn.execute(text(stmt))
            for stmt in DDL:
                await conn.execute(text(stmt))
            col = (await conn.execute(text(
                "SELECT count(*) FROM information_schema.columns WHERE table_name='organisations' AND column_name='section_names'"))).scalar()
            check("the column is added, and the DDL list is idempotent", col == 1)
    else:
        check("the DDL module exists", False)

    async with engine.begin() as conn:
        for oid, name, slug in ((OURS, "Scarborough CC", "scarborough"), (OTHER, "Other CC", "otherclub")):
            await conn.execute(text(
                "INSERT INTO organisations (id, name, slug, is_active) VALUES (:i,:n,:s,true)"),
                {"i": oid, "n": name, "s": slug})
        await conn.execute(text("UPDATE organisations SET fantasy_link_token='tok123', module_overrides=jsonb_build_array('fantasy'), subscription_status='active' WHERE id=:i"), {"i": OURS})
        for sid, org, name, logo in (
            (S_FROTH, OURS, "Froth Craft", "/images/sponsors/froth/logo"),
            (S_BANK, OURS, "Big Bank", "/images/sponsors/bank/logo"),
            (S_NOLOGO, OURS, "No Logo Co", None),
            (S_OTHER, OTHER, "Other Sponsor", "/images/sponsors/other/logo"),
        ):
            await conn.execute(text(
                "INSERT INTO org_sponsors (id, organisation_id, name, logo_url, display_order) VALUES (:i,:o,:n,:l,1)"),
                {"i": sid, "o": org, "n": name, "l": logo})

    print("== service")
    if HAVE:
        mine = [str(S_FROTH), str(S_BANK), str(S_NOLOGO)]
        out = sn.clean_input({"fantasy": {"name": "  Froth   Fantasy Cricket ", "sponsor_id": str(S_FROTH)}}, mine)
        check("a name is tidied and kept with its sponsor", out == {"fantasy": {"name": "Froth Fantasy Cricket", "sponsor_id": str(S_FROTH)}}, str(out))
        check("a name equal to the standard one is no rename", sn.clean_input({"leaderboard": {"name": "leaderboard"}}, mine) is None)
        check("another club's sponsor is dropped, the name stays",
              sn.clean_input({"fantasy": {"name": "X", "sponsor_id": str(S_OTHER)}}, mine) == {"fantasy": {"name": "X", "sponsor_id": None}})
        check("a section with no name and no sponsor is not stored", sn.clean_input({"records": {"name": " ", "sponsor_id": None}}, mine) is None)
        check("a sponsor alone is stored (presented by, no rename)",
              sn.clean_input({"records": {"sponsor_id": str(S_BANK)}}, mine) == {"records": {"name": None, "sponsor_id": str(S_BANK)}})
        check("an unknown section is refused, not ignored", _raises(lambda: sn.clean_input({"homepage": {"name": "x"}}, mine)))
        check("a name is clipped to 60 characters", len(sn.clean_name("x" * 200)) == 60)
        check("control characters and newlines are flattened", sn.clean_name("A\nB\x00C") == "A B C")
    else:
        check("the section_names service exists", False)

    print("== admin routes")
    async with Session() as db:
        club = (await db.execute(select(Organisation).where(Organisation.id == OURS))).scalar_one()
        if HAVE:
            view = await ca.get_section_names(current_user=None, club=club)
            keys = [s["key"] for s in view["sections"]]
            check("every section is listed with its standard name",
                  "fantasy" in keys and "leaderboard" in keys and {s["key"]: s["default_label"] for s in view["sections"]}["honour_board"] == "Honour Board")
            body = ca.SectionNamesPut(sections={
                "fantasy": ca.SectionNameEntry(name="Froth Fantasy Cricket", sponsor_id=str(S_FROTH)),
                "leaderboard": ca.SectionNameEntry(name="Big Bank Leaderboard"),
                "records": ca.SectionNameEntry(sponsor_id=str(S_BANK)),
                "compare": ca.SectionNameEntry(),
            })
            view = await ca.put_section_names(data=body, current_user=None, club=club, db=db)
            got = {s["key"]: s for s in view["sections"]}
            check("a save stores the renames", got["fantasy"]["name"] == "Froth Fantasy Cricket" and got["leaderboard"]["name"] == "Big Bank Leaderboard")
            check("a section sent empty is left standard (Compare)", got["compare"]["name"] is None and got["compare"]["sponsor_id"] is None)
            check("a sponsor-only section keeps its sponsor", got["records"]["sponsor_id"] == str(S_BANK) and got["records"]["name"] is None)
            check("an unknown section is a 422", await http_status(ca.put_section_names(
                data=ca.SectionNamesPut(sections={"homepage": ca.SectionNameEntry(name="x")}), current_user=None, club=club, db=db)) == 422)
            check("a 422 leaves the saved names alone", (await ca.get_section_names(current_user=None, club=club))["sections"][0] is not None
                  and {s["key"]: s for s in (await ca.get_section_names(current_user=None, club=club))["sections"]}["fantasy"]["name"] == "Froth Fantasy Cricket")
            view = await ca.put_section_names(data=ca.SectionNamesPut(sections={
                "fantasy": ca.SectionNameEntry(name="Froth Fantasy Cricket", sponsor_id=str(S_OTHER)),
                "leaderboard": ca.SectionNameEntry(name="Big Bank Leaderboard"),
                "records": ca.SectionNameEntry(sponsor_id=str(S_BANK)),
            }), current_user=None, club=club, db=db)
            got = {s["key"]: s for s in view["sections"]}
            check("another club's sponsor cannot be linked", got["fantasy"]["sponsor_id"] is None and got["fantasy"]["name"] == "Froth Fantasy Cricket")
            await ca.put_section_names(data=ca.SectionNamesPut(sections={
                "fantasy": ca.SectionNameEntry(name="Froth Fantasy Cricket", sponsor_id=str(S_FROTH)),
                "leaderboard": ca.SectionNameEntry(name="Big Bank Leaderboard"),
                "records": ca.SectionNameEntry(sponsor_id=str(S_BANK)),
            }), current_user=None, club=club, db=db)

            dep = inspect.signature(ca.put_section_names).parameters["current_user"].default.dependency
            uid_no, uid_yes = uuid.uuid4(), uuid.uuid4()
            db.add(User(id=uid_no, username="nocap", email="a@b.co", password_hash="x"))
            db.add(User(id=uid_yes, username="hascap", email="c@d.co", password_hash="x"))
            await db.flush()
            db.add(ClubMembership(club_id=OURS, user_id=uid_no, role="club_member", capabilities=[]))
            db.add(ClubMembership(club_id=OURS, user_id=uid_yes, role="club_member", capabilities=["manage_sponsors"]))
            await db.commit()
            check("saving names without manage_sponsors is refused", await http_status(dep(current_user=await db.get(User, uid_no), db=db)) == 403)
            yes = await db.get(User, uid_yes)
            check("saving names with manage_sponsors passes", (await dep(current_user=yes, db=db)) is yes)
        else:
            check("admin section-names routes exist", hasattr(ca, "put_section_names"))

    print("== public endpoint")
    async with Session() as db:
        pub = await clubs_router.get_club_sponsors("scarborough", request(), db)
        names = pub.get("section_names") or {}
        check("Fantasy comes back renamed with its sponsor's logo",
              (names.get("fantasy") or {}).get("name") == "Froth Fantasy Cricket"
              and ((names.get("fantasy") or {}).get("sponsor") or {}).get("logo_url") == "/images/sponsors/froth/logo", str(names.get("fantasy")))
        check("Leaderboard is renamed with no sponsor", (names.get("leaderboard") or {}).get("name") == "Big Bank Leaderboard"
              and (names.get("leaderboard") or {}).get("sponsor") is None, str(names.get("leaderboard")))
        check("Records is linked to a sponsor with no rename", (names.get("records") or {}).get("name") is None
              and ((names.get("records") or {}).get("sponsor") or {}).get("name") == "Big Bank", str(names.get("records")))
        check("Compare is not in the list (standard name)", "compare" not in names)
        # Delete the Froth sponsor: the name stays, the logo stops.
        await db.execute(text("DELETE FROM org_sponsors WHERE id=:i"), {"i": S_FROTH})
        await db.commit()
        pub = await clubs_router.get_club_sponsors("scarborough", request(), db)
        fn = (pub.get("section_names") or {}).get("fantasy") or {}
        check("a deleted sponsor stops being drawn but the rename stays",
              fn.get("name") == "Froth Fantasy Cricket" and fn.get("sponsor") is None, str(fn))
        other = await clubs_router.get_club_sponsors("otherclub", request(), db)
        check("another club's page carries none of these names", not (other.get("section_names") or {}))
        await db.execute(text("INSERT INTO org_sponsors (id, organisation_id, name, logo_url, display_order) VALUES (:i,:o,'Froth Craft','/images/sponsors/froth/logo',1)"), {"i": S_FROTH, "o": OURS})
        await db.commit()
        club = (await db.execute(select(Organisation).where(Organisation.id == OURS))).scalar_one()
        if HAVE:
            club.section_names = {**club.section_names, "fantasy": {"name": "Froth Fantasy Cricket", "sponsor_id": str(S_FROTH)}}
            await db.commit()

    print("== fantasy landing")
    async with Session() as db:
        land = await public_fantasy.landing("tok123", request(), db)
        branding = land["club"]
        check("the fantasy landing carries the club's name for the game", branding.get("fantasy_name") == "Froth Fantasy Cricket", str(branding))
        check("the fantasy landing carries the sponsor logo", (branding.get("fantasy_sponsor") or {}).get("logo_url") == "/images/sponsors/froth/logo", str(branding.get("fantasy_sponsor")))
        check("the club's own name is still there for the sub line", branding.get("name") == "Scarborough CC")

    print("== share card")
    async with Session() as db:
        route = og_preview._parse_route("/scarborough/leaderboard")
        check("the route parser keeps the section", (route or {}).get("section") == "leaderboard", str(route))
        renamed = await og_preview._club_html("scarborough", "https://x/scarborough/leaderboard", "https://x", db, "leaderboard") if HAVE else \
            await og_preview._club_html("scarborough", "https://x/scarborough/leaderboard", "https://x", db)
        check("a renamed section shares under its own name", "Big Bank Leaderboard" in renamed, "")
        plain = await og_preview._club_html("scarborough", "https://x/scarborough/compare", "https://x", db, "compare") if HAVE else \
            await og_preview._club_html("scarborough", "https://x/scarborough/compare", "https://x", db)
        check("a section that was not renamed keeps the club card (the check can fail the other way)",
              "Cricket Club Stats" in plain and "Big Bank Leaderboard" not in plain)

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
