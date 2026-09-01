"""How many clubs an audience reaches, beside how many people it reaches.

Asked for on BetterCricket's internal BetterComms: the live readout under a
List and under a Segment says "79 contacts match · 79 reachable by email" —
add the number of distinct clubs those contacts belong to.

Runs the SHIPPED route body and figure builder against a real Postgres, and
checks the Python rule against the JavaScript one the Lists screen computes
from its own membership rows.

    python -m verification.verify_audience_clubs
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_audience",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import (  # noqa: E402
    Base, CommsContact, CommsList, CommsListMember, MarketingClub, Organisation, User,
)
from app.routers.comms import (  # noqa: E402
    SegmentIn, audience_figures, list_members, resolve_segment,
)

PASS: list[str] = []
FAIL: list[str] = []
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


class Stub:
    """The two fields audience_figures reads, for the cap and agreement checks."""
    def __init__(self, email, mc):
        self.email = email
        self.marketing_club_id = mc


def js_club_count(rows: list) -> int:
    """Run the FRONTEND's own clubCount over the same rows, by lifting the real
    function out of crudShell.jsx and evaluating it in node with a stand-in
    reachability. A structural "does the source mention these two conditions"
    check would pass on a rule that behaved differently."""
    src = open(os.path.join(
        REPO, "frontend/src/pages/admin/clubhouse/crudShell.jsx")).read()
    if "export function clubCount" not in src:
        return None   # the rule isn't there at all — reported, not a crash
    start = src.index("export function clubCount")
    end = src.index("\n}", start) + 2
    code = src[start:end].replace("export function", "function", 1)
    script = (
        "const reachability = (c) => ({ key: c.email ? 'email' : 'none' });\n"
        + code + "\n"
        "const rows = JSON.parse(process.argv[2]);\n"
        "process.stdout.write(String(clubCount(rows)));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as fh:
        fh.write(script)
        path = fh.name
    try:
        out = subprocess.run(["node", path, json.dumps(rows)],
                             capture_output=True, text=True, check=True)
        return int(out.stdout.strip())
    finally:
        os.unlink(path)


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # fee_members.member_category is added by a raw-SQL migration, not by the
        # ORM model, so create_all does not produce it — and the shipped route
        # body runs reconcile_contacts_from_directory, which selects it. The
        # lifespan-only-column trap this repo's notes already document.
        # ...and member_membership_types is a lifespan-created table with no ORM
        # model at all, so create_all does not make it either.
        for stmt in (
            "ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS member_category TEXT",
            """CREATE TABLE IF NOT EXISTS member_membership_types (
                   organisation_id UUID NOT NULL,
                   member_id UUID NOT NULL,
                   membership_type_id UUID NOT NULL,
                   PRIMARY KEY (member_id, membership_type_id))""",
            """CREATE TABLE IF NOT EXISTS player_achievements (
                   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                   org_id UUID, player_id UUID, category TEXT, achievement TEXT)""",
        ):
            await conn.execute(text(stmt))

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket", slug="bettercricket",
                                is_marketing_outreach=True)
        own = Organisation(id=uuid.uuid4(), name="Applecross CC", slug="applecross-cc")
        db.add_all([outreach, own])
        await db.flush()
        staff = User(id=uuid.uuid4(), username="staff", email="staff@example.com")
        db.add(staff)
        await db.flush()

        # Three prospect clubs, and contacts spread unevenly across them: one
        # club with three officers, one with one, one with none of its own.
        mcs = {}
        for label in ("alpha", "beta", "gamma"):
            mc = MarketingClub(id=uuid.uuid4(), name=f"{label} CC",
                               grassroots_guid=f"guid-{label}", utm_code=f"{label}-cc",
                               state="WA")
            db.add(mc)
            await db.flush()
            mcs[label] = mc

        def contact(email, mc=None, org=None, source="directory"):
            db.add(CommsContact(id=uuid.uuid4(), organisation_id=(org or outreach).id,
                                email=email, source=source,
                                marketing_club_id=(mc.id if mc else None)))

        for i in range(3):
            contact(f"alpha{i}@example.com", mcs["alpha"])
        contact("beta0@example.com", mcs["beta"])
        # Hand-added: a real contact belonging to no club at all.
        contact("loose@example.com", None)
        # An address that cannot be emailed. comms_contacts.email is NOT NULL,
        # but a blank one is still storable and is not a reachable person.
        contact("", mcs["gamma"])
        # A club's own member: no directory club, which is why the figure is 0
        # in a club's context and the readout does not draw it.
        contact("member@example.com", None, org=own, source="player")
        await db.commit()

        print("\n── The figure itself ──────────────────────────────────────────")
        res = await resolve_segment(SegmentIn(name="all", definition={}), staff, outreach, db)
        check("every contact in the org matches an empty definition",
              res["count"] == 6, res["count"])
        check("the blank address counts as matching but NOT as reachable",
              res["reachable"] == 5 and res["count"] == 6,
              f"{res['reachable']}/{res['count']}")
        check("three officers at one club count as one club, and the club with "
              "no reachable contact is not counted", res["clubs"] == 2, res["clubs"])
        check("a contact belonging to no club does not invent one",
              res["clubs"] == 2 and any(c["email"] == "loose@example.com"
                                        for c in res["contacts"]), res["clubs"])
        check("another org's contacts are not in this audience",
              not any(c["email"] == "member@example.com" for c in res["contacts"]))

        own_res = await resolve_segment(SegmentIn(name="all", definition={}), staff, own, db)
        check("a club's own audience reports 0 clubs, so the readout hides it",
              own_res["clubs"] == 0 and own_res["count"] >= 1, own_res["clubs"])

        print("\n── Exact over the whole audience, never the capped slice ──────")
        big = ([Stub(f"p{i}@example.com", uuid.uuid4()) for i in range(6000)]
               + [Stub("dup@example.com", None)])
        figs = audience_figures(big)
        check("6001 contacts across 6000 clubs are all counted",
              figs["clubs"] == 6000 and figs["reachable"] == 6001, figs)
        src = open(os.path.join(REPO, "backend/app/routers/comms.py")).read()
        body = src.split("async def resolve_segment")[1].split("@router.get")[0]
        check("resolve passes the FULL audience to the figures, not the capped rows",
              "audience_figures(contacts)" in body and "audience_figures(rows)" not in body)
        check("...and still caps the contact list it ships",
              "contacts[:5000]" in body)

        print("\n── The Lists screen counts the same way ───────────────────────")
        lst = CommsList(organisation_id=outreach.id, name="Prospects", source="manual")
        db.add(lst)
        await db.flush()
        rows = (await db.execute(select(CommsContact).where(
            CommsContact.organisation_id == outreach.id))).scalars().all()
        for c in rows:
            db.add(CommsListMember(list_id=lst.id, contact_id=c.id))
        await db.commit()
        members = await list_members(str(lst.id), staff, outreach, db)
        check("the list endpoint returns every member, uncapped",
              len(members) == len(rows), f"{len(members)}/{len(rows)}")
        check("each member carries the club link the count needs",
              all("marketing_club_id" in m for m in members))
        js = js_club_count([{"email": m["email"],
                             "marketing_club_id": m["marketing_club_id"]} for m in members])
        py = audience_figures(rows)["clubs"]
        check("the frontend's clubCount and the server's figure agree on the same rows",
              js == py == 2, f"js={js} py={py}")
        # An audience that would fool a rule counting rows instead of clubs, or
        # one forgetting to exclude the unreachable.
        tricky = [{"email": "a@x.com", "marketing_club_id": "c1"},
                  {"email": "b@x.com", "marketing_club_id": "c1"},
                  {"email": "", "marketing_club_id": "c2"},
                  {"email": "d@x.com", "marketing_club_id": None}]
        js2 = js_club_count(tricky)
        py2 = audience_figures([Stub(t["email"], t["marketing_club_id"]) for t in tricky])["clubs"]
        check("...and on the awkward cases too (a repeat, a blank address, no club)",
              js2 == py2 == 1, f"js={js2} py={py2}")

        print("\n── Where it is drawn ──────────────────────────────────────────")
        shell = open(os.path.join(
            REPO, "frontend/src/pages/admin/clubhouse/crudShell.jsx")).read()
        check("the readout draws the figure only when there are clubs to report",
              "clubs > 0 &&" in shell)
        check("and says club / clubs correctly",
              "clubs === 1 ? 'club' : 'clubs'" in shell)
        internal = open(os.path.join(
            REPO, "frontend/src/pages/admin/clubhouse/InternalSegments.jsx")).read()
        check("the internal Segments screen passes it", "clubs={s.clubs}" in internal)
        lists = open(os.path.join(
            REPO, "frontend/src/pages/admin/bettercomms/CommsLists.jsx")).read()
        check("the Lists screen computes and draws it",
              "clubCount(members)" in lists and "clubs === 1 ? 'club' : 'clubs'" in lists)
        engine_src = open(os.path.join(
            REPO, "frontend/src/pages/admin/clubhouse/segmentEngine.jsx")).read()
        check("a segment prefers the server's exact figures over the capped slice",
              "resolved?.clubs ?? clubCount(contacts)" in engine_src
              and "resolved?.reachable ??" in engine_src)
        club_scope = open(os.path.join(
            REPO, "frontend/src/pages/admin/clubhouse/ClubhouseSegments.jsx")).read()
        check("a club's own Segments screen is left alone", "clubs=" not in club_scope)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
