"""Verification for the sponsor a club picks for its player cards (migration 367),
against a real Postgres.

Runs the SHIPPED `services/card_sponsors.py`, `services/card_sponsors_ddl.py`, the
shipped route bodies in `routers/club_admin.py` (`get_card_sponsors`,
`put_card_sponsors`) and the public `routers/clubs.get_club_sponsors`.

The club has a Major and a Gold with logos, a Major with NO logo and a Silver. A
second club's sponsor guards against a leak. Every "X is refused / not shown" check
is paired with a check that X works elsewhere, so a check cannot pass by doing
nothing (rule 21).

CONTROL MODE. Run against the commit BEFORE this change the service does not exist;
it is read through find_spec and new keys through presence-safe accessors, so the
control reports the missing behaviour as failed checks.

Run:  DATABASE_URL=postgresql+asyncpg://root@/cardsp?host=/tmp \
      python verification/verify_card_sponsors.py
"""
from __future__ import annotations

import asyncio
import importlib.util
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

from app.models.db import Base, Organisation, Sponsor
from app.routers import club_admin as ca
from app.routers import clubs as clubs_router

HAVE = importlib.util.find_spec("app.services.card_sponsors") is not None
if HAVE:
    from app.services import card_sponsors as cs
    from app.services.card_sponsors_ddl import STATEMENTS as DDL
else:
    cs = None
    DDL = []

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
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
ID = {k: uuid.uuid4() for k in ("major", "gold", "major_nologo", "silver", "other")}
LOGO = "/images/sponsors/x/logo"


def sid(k: str) -> str:
    return str(ID[k])


async def status_of(coro):
    try:
        await coro
    except HTTPException as e:
        return e.status_code
    return None


async def put(db, club, **fields):
    body = ca.CardSponsorsPut(**fields)
    return await ca.put_card_sponsors(data=body, current_user=None, club=club, db=db)


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    print("== migration DDL")
    if HAVE:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE organisations DROP COLUMN card_sponsors"))
            for _ in range(2):
                for stmt in DDL:
                    await conn.execute(text(stmt))
            n = (await conn.execute(text(
                "SELECT count(*) FROM information_schema.columns WHERE table_name='organisations' AND column_name='card_sponsors'"))).scalar()
            check("the column is added and the DDL list is idempotent", n == 1)
    else:
        check("the DDL module exists", False)

    async with engine.begin() as conn:
        for oid, name, slug in ((OURS, "Our Club", "ourclub"), (OTHER, "Other Club", "other")):
            await conn.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i,:n,:s,true)"),
                               {"i": oid, "n": name, "s": slug})
        for key, org, name, order, tier, logo in (
            ("major", OURS, "Big Major", 1, "major", LOGO),
            ("gold", OURS, "Gold Co", 2, "gold", LOGO),
            ("major_nologo", OURS, "Logoless Major", 3, "major", None),
            ("silver", OURS, "Silver Co", 4, "silver", LOGO),
            ("other", OTHER, "Other Sponsor", 1, "major", LOGO),
        ):
            await conn.execute(text(
                "INSERT INTO org_sponsors (id, organisation_id, name, display_order, logo_url, tier) VALUES (:i,:o,:n,:d,:l,:t)"),
                {"i": ID[key], "o": org, "n": name, "d": order, "l": logo, "t": tier})

    print("== service")
    async with Session() as db:
        rows = list((await db.execute(select(Sponsor).where(Sponsor.organisation_id == OURS).order_by(Sponsor.display_order))).scalars().all())
        if HAVE:
            check("surfaces are the share card and the Player Cards", cs.SURFACES == ("share_card", "player_cards"))
            ok = cs.clean({"share_card": sid("gold"), "player_cards": sid("silver")}, rows)
            check("clean keeps a valid pick for each surface", ok == {"share_card": sid("gold"), "player_cards": sid("silver")}, str(ok))
            check("clean drops another club's sponsor", cs.clean({"share_card": sid("other")}, rows) is None)
            check("clean drops a sponsor with no logo", cs.clean({"share_card": sid("major_nologo")}, rows) is None)
            check("clean drops an unknown id", cs.clean({"share_card": str(uuid.uuid4())}, rows) is None)
            check("clean drops a null pick but keeps the other surface",
                  cs.clean({"share_card": None, "player_cards": sid("gold")}, rows) == {"player_cards": sid("gold")})
            try:
                cs.clean({"posters": sid("gold")}, rows)
                refused = False
            except ValueError:
                refused = True
            check("clean refuses a surface that does not exist", refused)
            check("view: nothing stored is no pick on either surface", cs.view(None, rows) == {"share_card": None, "player_cards": None})
            check("view: a stored pick is returned", cs.view({"share_card": sid("gold")}, rows) == {"share_card": sid("gold"), "player_cards": None})
            check("view: a pick whose sponsor is gone reads as not picked", cs.view({"share_card": str(uuid.uuid4())}, rows)["share_card"] is None)
            check("view: a pick whose sponsor lost its logo reads as not picked", cs.view({"share_card": sid("major_nologo")}, rows)["share_card"] is None)
        else:
            check("the card_sponsors service exists", False)

    print("== admin routes")
    async with Session() as db:
        club = (await db.execute(select(Organisation).where(Organisation.id == OURS))).scalar_one()
        if HAVE:
            view = await ca.get_card_sponsors(current_user=None, club=club, db=db)
            check("nothing is picked to start with", view["picks"] == {"share_card": None, "player_cards": None}, str(view))
            check("both surfaces are listed with a label", [s["key"] for s in view["surfaces"]] == ["share_card", "player_cards"]
                  and all(s["label"] for s in view["surfaces"]), str(view["surfaces"]))

            view = await put(db, club, share_card=sid("gold"))
            check("picking the share card sponsor saves it", view["picks"] == {"share_card": sid("gold"), "player_cards": None}, str(view))
            view = await put(db, club, player_cards=sid("silver"))
            check("picking the other surface leaves the first pick alone (absent is not a clear)",
                  view["picks"] == {"share_card": sid("gold"), "player_cards": sid("silver")}, str(view))
            check("the pick is stored on the club", club.card_sponsors == {"share_card": sid("gold"), "player_cards": sid("silver")}, str(club.card_sponsors))

            for label, sponsor in (("another club's sponsor", sid("other")), ("a sponsor with no logo", sid("major_nologo")), ("an unknown id", str(uuid.uuid4()))):
                code = await status_of(put(db, club, share_card=sponsor))
                check(f"{label} is refused with 422", code == 422, str(code))
            check("a refused pick changes nothing", club.card_sponsors == {"share_card": sid("gold"), "player_cards": sid("silver")}, str(club.card_sponsors))

            view = await put(db, club, share_card=None)
            check("an explicit null clears one surface only", view["picks"] == {"share_card": None, "player_cards": sid("silver")}, str(view))
            view = await put(db, club, player_cards=None)
            check("clearing the last pick stores NULL", club.card_sponsors is None and view["picks"] == {"share_card": None, "player_cards": None}, str(club.card_sponsors))
            view = await put(db, club)
            check("an empty body changes nothing", club.card_sponsors is None)

            await put(db, club, share_card=sid("gold"))
        else:
            check("the card-sponsors routes exist", False)

    print("== public sponsor list")
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"", "client": ("127.0.0.1", 1)}
    async with Session() as db:
        res = await clubs_router.get_club_sponsors("ourclub", Request(scope), db)
        picks = res.get("card_sponsors") if isinstance(res, dict) else None
        check("the public list carries the club's picks",
              picks == {"share_card": sid("gold"), "player_cards": None} if HAVE else False, str(picks))
        check("the public list still returns every sponsor, logo or not", len(res["sponsors"]) == 4, str(len(res["sponsors"])))
        other = await clubs_router.get_club_sponsors("other", Request(scope), db)
        check("another club's list does not see our pick",
              (other.get("card_sponsors") or {}).get("share_card") is None and all(s["id"] != sid("gold") for s in other["sponsors"]), str(other.get("card_sponsors")))

        # A sponsor deleted after being picked: the list reads it as not picked.
        await db.execute(text("DELETE FROM org_sponsors WHERE id = :i"), {"i": ID["gold"]})
        await db.commit()
        res = await clubs_router.get_club_sponsors("ourclub", Request(scope), db)
        check("a deleted sponsor no longer shows as the pick",
              (res.get("card_sponsors") or {}).get("share_card") is None and HAVE, str(res.get("card_sponsors")))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
