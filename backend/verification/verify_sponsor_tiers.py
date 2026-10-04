"""Verification for sponsor tiers and placements (migration 318), against a real
Postgres.

Runs the SHIPPED `services/sponsor_tiers.py`, `services/sponsor_tiers_ddl.py`
and the shipped route bodies: the public `GET /clubs/{slug}/sponsors` and the
club admin sponsor routes (list, create, patch, settings, delete).

The club under test seeds one sponsor per case: a major with a logo, a major
whose dashboard spot was switched off by hand, a gold, a silver whose bar spot
was switched off, a legacy-shaped silver, and a supporter with no logo. A second
club's sponsor guards against a leak.

Every "X is absent" check is paired with a check that X shows elsewhere or
before the change, so a check cannot pass by hiding everything (rule 21).

CONTROL MODE. Run against the commit BEFORE this change, `sponsor_tiers` does
not exist. It is read through find_spec and the new keys are read through
presence-safe accessors, so the control reports the reported behaviour (no tiers,
no placements, logo-less sponsors dropped) as failed checks rather than crashing.

Run:  DATABASE_URL=postgresql+asyncpg://root@/sponsors_test?host=/var/run/postgresql \
      python verification/verify_sponsor_tiers.py
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

HAVE = importlib.util.find_spec("app.services.sponsor_tiers") is not None
if HAVE:
    from app.services import sponsor_tiers as st
    from app.services.sponsor_tiers_ddl import STATEMENTS as TIER_DDL
else:
    st = None
    TIER_DDL = []

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
IDS = {k: uuid.uuid4() for k in ("major", "major_nodash", "gold", "silver_nobar", "legacy", "supporter", "other")}
LOGO = "/images/sponsors/x/logo"


def request() -> Request:
    return Request({"type": "http", "headers": [], "query_string": b""})


async def public(db) -> dict:
    return await clubs_router.get_club_sponsors("ourclub", request(), db)


def by_name(payload: dict) -> dict:
    return {s["name"]: s for s in payload["sponsors"]}


def spot_names(payload: dict, spot: str) -> list[str]:
    """What the page draws in a spot: placed there, and (dashboard/bar) with a logo."""
    out = []
    for s in payload["sponsors"]:
        if spot in (s.get("placements") or []) and (spot == "footer" or s.get("logo_url")):
            out.append(s["name"])
    return out


async def admin_call(fn, db, club, **kw):
    kw.setdefault("current_user", None)
    return await fn(club=club, db=db, **kw)


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        for oid, name, slug in ((OURS, "Our Club", "ourclub"), (OTHER, "Other Club", "otherclub")):
            await conn.execute(text(
                "INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)"),
                {"i": oid, "n": name, "s": slug})
        await conn.execute(text(
            "INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2026/27', 2026)"),
            {"i": uuid.uuid4(), "o": OURS})

    async with Session() as db:
        rows = [
            ("major", "Big Major", OURS, 1, "major", None, LOGO),
            ("major_nodash", "Quiet Major", OURS, 2, "major", {"dashboard": False}, LOGO),
            ("gold", "Gold Co", OURS, 3, "gold", None, LOGO),
            ("silver_nobar", "Silver NoBar", OURS, 4, "silver", {"bar": False}, LOGO),
            ("legacy", "Legacy Silver", OURS, 5, "silver", None, LOGO),
            ("supporter", "Small Supporter", OURS, 6, "supporter", None, None),
            ("other", "Other Club Sponsor", OTHER, 1, "major", None, LOGO),
        ]
        for key, name, org, order, tier, placements, logo in rows:
            kw = dict(id=IDS[key], organisation_id=org, name=name, display_order=order, logo_url=logo)
            if HAVE:
                kw.update(tier=tier, placements=placements)
            db.add(Sponsor(**kw))
        await db.commit()


async def main() -> None:
    print("== migration DDL")
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    if HAVE:
        async with engine.begin() as conn:
            org_id = uuid.uuid4()
            await conn.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i,'Legacy','legacy',true)"), {"i": org_id})
            # A legacy-shaped table: drop the new columns, insert an old row, then run the DDL.
            await conn.execute(text("ALTER TABLE org_sponsors DROP COLUMN tier"))
            await conn.execute(text("ALTER TABLE org_sponsors DROP COLUMN placements"))
            await conn.execute(text("ALTER TABLE organisations DROP COLUMN sponsor_tier_labels"))
            await conn.execute(text("INSERT INTO org_sponsors (id, organisation_id, name, display_order) VALUES (:i,:o,'Old Sponsor',1)"),
                               {"i": uuid.uuid4(), "o": org_id})
            for stmt in TIER_DDL:
                await conn.execute(text(stmt))
            row = (await conn.execute(text("SELECT tier, placements FROM org_sponsors WHERE name='Old Sponsor'"))).one()
            check("an existing sponsor lands on silver with no overrides", row[0] == "silver" and row[1] is None, str(row))
            for stmt in TIER_DDL:  # the lifespan re-runs every statement each boot
                await conn.execute(text(stmt))
            check("the DDL list is idempotent (second run raises nothing)", True)
    else:
        check("the DDL module exists", False, "sponsor_tiers_ddl missing")

    await seed()

    print("== tier service")
    if HAVE:
        check("four tiers in rank order", st.TIERS == ("major", "gold", "silver", "supporter"))
        check("major shows in all three spots", st.resolve_placements("major", None) == ["dashboard", "bar", "footer", "posts"])
        check("gold shows in bar and list", st.resolve_placements("gold", None) == ["bar", "footer", "posts"])
        check("supporter shows in the list only", st.resolve_placements("supporter", None) == ["footer"])
        check("an override switches a spot off", st.resolve_placements("major", {"dashboard": False}) == ["bar", "footer", "posts"])
        check("an override switches a spot on", st.resolve_placements("supporter", {"dashboard": True}) == ["dashboard", "footer"])
        check("an unknown spot in an override is ignored, never widened",
              st.resolve_placements("supporter", {"everywhere": True, "bar": "yes"}) == ["footer"])
        check("an unknown tier shows nowhere (fails closed)", st.resolve_placements("platinum", None) == [])
        check("a bad tier is refused on write", _raises(lambda: st.clean_tier("platinum")))
        check("a good tier is accepted case-insensitively", st.clean_tier(" Gold ") == "gold")
        check("blank labels fall back to the stock names", st.resolve_labels({"major": "  "})["major"] == "Major Partners")
        check("a custom label is used and clipped to 40",
              st.resolve_labels({"major": "x" * 80})["major"] == "x" * 40)
        check("labels equal to the stock name are not stored", st.clean_labels({"major": "Major Partners"}) is None)
        check("an override set empty reads NULL", st.clean_overrides({"bar": "x", "zzz": True}) is None)
    else:
        check("sponsor_tiers service exists", False)

    print("== public endpoint")
    async with Session() as db:
        club = (await db.execute(select(Organisation).where(Organisation.id == OURS))).scalar_one()
        if HAVE:
            club.sponsor_tier_labels = {"major": "Naming Partner"}
            await db.commit()
        pub = await public(db)
        names = [s["name"] for s in pub["sponsors"]]
        check("a sponsor with no logo is still returned (named in the list)", "Small Supporter" in names, str(names))
        check("the other club's sponsor is not returned", "Other Club Sponsor" not in names)
        check("sponsors come tier first, then the club's order",
              names == ["Big Major", "Quiet Major", "Gold Co", "Silver NoBar", "Legacy Silver", "Small Supporter"], str(names))
        check("dashboard slot: only the major with the spot on", spot_names(pub, "dashboard") == ["Big Major"], str(spot_names(pub, "dashboard")))
        check("dashboard slot is not empty for this club (the check can pass the other way)", len(spot_names(pub, "dashboard")) > 0)
        check("bar: tiers in order, hand-off spot left out, no-logo left out",
              spot_names(pub, "bar") == ["Big Major", "Quiet Major", "Gold Co", "Legacy Silver"], str(spot_names(pub, "bar")))
        check("sponsor list names every sponsor of the club",
              spot_names(pub, "footer") == ["Big Major", "Quiet Major", "Gold Co", "Silver NoBar", "Legacy Silver", "Small Supporter"],
              str(spot_names(pub, "footer")))
        check("the club's own tier name is returned", (pub.get("tier_labels") or {}).get("major") == "Naming Partner", str(pub.get("tier_labels")))
        legacy = by_name(pub)["Legacy Silver"]
        check("a legacy silver sponsor shows in the bar and the list, not the dashboard (unchanged from before)",
              legacy.get("placements") == ["bar", "footer"], str(legacy.get("placements")))

    print("== admin routes")
    async with Session() as db:
        club = (await db.execute(select(Organisation).where(Organisation.id == OURS))).scalar_one()
        listed = await admin_call(ca.list_sponsors, db, club)
        row = {s["name"]: s for s in listed}["Quiet Major"]
        check("admin list carries tier, overrides and the resolved spots",
              row.get("tier") == "major" and row.get("placement_overrides") == {"dashboard": False}
              and row.get("placements") == ["bar", "footer", "posts"], str(row))

        if HAVE:
            made = await admin_call(ca.create_sponsor, db, club, data=ca.SponsorCreate(name="New One", tier="gold"))
            check("create takes a tier", made["tier"] == "gold" and made["placements"] == ["bar", "footer", "posts"], str(made))
            plain = await admin_call(ca.create_sponsor, db, club, data=ca.SponsorCreate(name="No Tier Sent"))
            check("create with no tier defaults to silver", plain["tier"] == "silver", str(plain))
            check("create with a bad tier is a 422", await _http_status(
                admin_call(ca.create_sponsor, db, club, data=ca.SponsorCreate(name="Bad", tier="platinum"))) == 422)

            sid = str(IDS["gold"])
            out = await admin_call(ca.patch_sponsor, db, club, sponsor_id=sid, data=ca.SponsorPatch(tier="major"))
            check("patch moves a sponsor to major and it follows the tier's spots",
                  out["tier"] == "major" and out["placements"] == ["dashboard", "bar", "footer", "posts"], str(out))

            out = await admin_call(ca.patch_sponsor, db, club, sponsor_id=sid, data=ca.SponsorPatch(name="Gold Co Renamed"))
            check("a patch that sends no tier leaves the tier alone (absent is not a clear)", out["tier"] == "major", str(out))

            out = await admin_call(ca.patch_sponsor, db, club, sponsor_id=sid, data=ca.SponsorPatch(placements={"bar": False}))
            check("patch switches one spot off by hand", out["placements"] == ["dashboard", "footer", "posts"]
                  and out["placement_overrides"] == {"bar": False}, str(out))
            out = await admin_call(ca.patch_sponsor, db, club, sponsor_id=sid, data=ca.SponsorPatch(placements={"footer": False}))
            check("a second switch merges with the first", out["placement_overrides"] == {"bar": False, "footer": False}, str(out))
            out = await admin_call(ca.patch_sponsor, db, club, sponsor_id=sid, data=ca.SponsorPatch(placements={"bar": None}))
            check("a null on one spot drops just that switch", out["placement_overrides"] == {"footer": False}, str(out))
            out = await admin_call(ca.patch_sponsor, db, club, sponsor_id=sid, data=ca.SponsorPatch(placements=None))
            check("placements sent as null clears every switch", out["placement_overrides"] == {}
                  and out["placements"] == ["dashboard", "bar", "footer", "posts"], str(out))
            out = await admin_call(ca.patch_sponsor, db, club, sponsor_id=sid, data=ca.SponsorPatch(placements={"footer": False}))
            out = await admin_call(ca.patch_sponsor, db, club, sponsor_id=sid, data=ca.SponsorPatch(tier="gold"))
            check("changing tier keeps the hand-set switches", out["placement_overrides"] == {"footer": False}, str(out))
            check("an unknown spot is a 422", await _http_status(
                admin_call(ca.patch_sponsor, db, club, sponsor_id=sid, data=ca.SponsorPatch(placements={"homepage": True}))) == 422)
            check("an unknown tier on patch is a 422", await _http_status(
                admin_call(ca.patch_sponsor, db, club, sponsor_id=sid, data=ca.SponsorPatch(tier="platinum"))) == 422)
            check("another club's sponsor cannot be patched", await _http_status(
                admin_call(ca.patch_sponsor, db, club, sponsor_id=str(IDS["other"]), data=ca.SponsorPatch(tier="gold"))) == 404)

            # settings
            sett = await ca.get_sponsor_settings(current_user=None, club=club)
            check("settings return the tier names in use", sett["tier_labels"]["major"] == "Naming Partner", str(sett["tier_labels"]))
            check("settings describe every tier's default spots",
                  {t["key"]: t["default_placements"] for t in sett["tiers"]}["supporter"] == ["footer"])
            out = await ca.put_sponsor_settings(data=ca.SponsorSettingsPut(), current_user=None, club=club, db=db)
            check("a settings save that sends no names leaves them alone", out["tier_labels"]["major"] == "Naming Partner", str(out["tier_labels"]))
            out = await ca.put_sponsor_settings(data=ca.SponsorSettingsPut(tier_labels={"gold": "Principal Partner", "major": ""}),
                                                current_user=None, club=club, db=db)
            check("a saved name shows and a blank one falls back to the stock name",
                  out["tier_labels"]["gold"] == "Principal Partner" and out["tier_labels"]["major"] == "Major Partners", str(out["tier_labels"]))

        # capability gate on every write
        if HAVE:
            gated = {}
            for fn in (ca.create_sponsor, ca.patch_sponsor, ca.put_sponsor_settings, ca.upload_sponsor_logo,
                       ca.delete_sponsor_logo, ca.delete_sponsor, ca.reorder_sponsors):
                dep = inspect.signature(fn).parameters["current_user"].default.dependency
                gated[fn.__name__] = dep
            uid_no, uid_yes = uuid.uuid4(), uuid.uuid4()
            db.add(User(id=uid_no, username="nocap", email="a@b.co", password_hash="x"))
            db.add(User(id=uid_yes, username="hascap", email="c@d.co", password_hash="x"))
            await db.flush()
            db.add(ClubMembership(club_id=OURS, user_id=uid_no, role="club_member", capabilities=[]))
            db.add(ClubMembership(club_id=OURS, user_id=uid_yes, role="club_member", capabilities=["manage_sponsors"]))
            await db.commit()
            u_no = await db.get(User, uid_no)
            u_yes = await db.get(User, uid_yes)
            for name, dep in gated.items():
                check(f"{name}: a member without manage_sponsors is refused",
                      await _http_status(dep(current_user=u_no, db=db)) == 403)
                ok = await dep(current_user=u_yes, db=db)
                check(f"{name}: a member with manage_sponsors passes", ok is u_yes)

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


async def _http_status(coro) -> int | None:
    try:
        await coro
    except HTTPException as e:
        return e.status_code
    return None


if __name__ == "__main__":
    asyncio.run(main())
