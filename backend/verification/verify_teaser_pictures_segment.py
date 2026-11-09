"""BetterComms -> Segments -> Active rules: "Club has a full set of teaser pictures".

Asked for so a campaign with the club's own dashboard in it can go to ONLY the
email contacts whose club has every teaser picture on file, so the picture
renders. The existing "Snapshot and picture ready" state reads one database column
(image_version) and cannot see the disk, so a club drawn before the dashboard
format existed counted as ready and got a broken box.

Runs the SHIPPED engine, picture route and report script (imported, nothing
retyped) against a real Postgres and a real temporary picture folder. Run it
against the previous commit and the checks fail on exactly what did not exist:
the rule is unknown there, the engine drops an unknown rule, and every contact
comes back.

    python -m verification.verify_teaser_pictures_segment
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DB_URL = os.environ.get("VERIFY_DATABASE_URL",
                        "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_teaser_pictures")
# Set BEFORE the settings module is imported: pydantic-settings reads env once.
os.environ["DATABASE_URL"] = DB_URL
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
TMP = tempfile.mkdtemp(prefix="teaser-pictures-")
os.environ["TEASER_IMAGE_DIR"] = TMP

from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, CommsContact, MarketingClub, Organisation
from app.services import club_teaser_images as ti
from app.services import comms_segments as seg
from app.services.club_teaser_ddl import STATEMENTS as TEASER_DDL

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} ({detail})")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


RULE = lambda v, op="eq": {"field": "teaser_pictures", "op": op, "value": v}  # noqa: E731
SNAP = {"schema": 2, "club": {"name": "Test CC"}, "totals": {"matches": 12}}
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 400


def put(token: str, formats, *, empty=()) -> None:
    d = Path(TMP) / token
    d.mkdir(parents=True, exist_ok=True)
    for fmt in formats:
        (d / f"{fmt}.png").write_bytes(b"" if fmt in empty else PNG)


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for stmt in TEASER_DDL:
            await conn.execute(text(stmt))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    ALL = list(ti.FORMATS)
    THREE = [f for f in ALL if f != "dashboard"]   # what a club drawn before v9.141.1 has
    tok = lambda: "tk" + uuid.uuid4().hex[:14]      # noqa: E731

    async with Session() as db:
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket", slug="bettercricket",
                                is_marketing_outreach=True)
        live_org = Organisation(id=uuid.uuid4(), name="Live Customer", slug="live-customer")
        db.add_all([outreach, live_org])
        await db.flush()

        contacts: dict[str, CommsContact] = {}
        clubs: dict[str, dict] = {}

        async def club(label, status="ok", *, image_version=1, files=ALL, empty=(), snapshot=True,
                       customer=False, schema=2, n_contacts=1):
            mc = MarketingClub(id=uuid.uuid4(), name=f"{label} CC", grassroots_guid=f"g-{label}",
                               utm_code=f"{label}-cc", state="VIC", kind="club",
                               existing_org_id=live_org.id if customer else None)
            db.add(mc)
            await db.flush()
            t = None
            if status:
                t = tok()
                snap = dict(SNAP, schema=schema) if snapshot else None
                await db.execute(text("""INSERT INTO club_teaser_snapshots
                    (marketing_club_id, org_guid, token, status, snapshot, version, image_version)
                    VALUES (CAST(:c AS uuid), 'g', :t, :s, CAST(:sn AS jsonb), 1, :iv)"""),
                    {"c": str(mc.id), "t": t, "s": status, "sn": json.dumps(snap) if snap else None,
                     "iv": image_version})
                if files:
                    put(t, files, empty=empty)
            clubs[label] = {"mc": mc, "token": t}
            for i in range(n_contacts):
                key = label if i == 0 else f"{label}{i + 1}"
                ct = CommsContact(id=uuid.uuid4(), organisation_id=outreach.id, email=f"{key}@example.com",
                                  name=f"{key} Officer", marketing_club_id=mc.id, source="directory")
                db.add(ct)
                contacts[key] = ct

        await club("full", n_contacts=2)                                   # the audience we want: two contacts
        await club("nodash", files=THREE)                                  # drawn on the old code: three of four
        await club("never", image_version=None, files=[])                  # good snapshot, never drawn
        await club("nover", image_version=None)                            # files exist, no image_version: route 404s
        await club("junior", status="junior_only", snapshot=False)         # leftover files, no usable snapshot
        await club("emptyfile", empty=("dashboard",))                      # a zero-byte dashboard
        await club("nosnapshot", status=None, files=[])                    # directory club, never crawled
        await club("errored", status="error", snapshot=False)              # last pull failed, files left over
        await club("nullsnap", snapshot=False)                             # ok but no snapshot body: route 404s
        await club("customer", customer=True, files=ALL)                   # live customer that still has files
        await club("oldschema", schema=1, image_version=None, files=[])    # waits for a re-pull
        await club("emptystatus", status="empty", snapshot=False, files=[])
        # A contact with no directory club at all (hand-added).
        loner = CommsContact(id=uuid.uuid4(), organisation_id=outreach.id, email="loner@example.com",
                             name="Loner", marketing_club_id=None, source="manual")
        db.add(loner)
        contacts["loner"] = loner
        # Folders that are not clubs must never count.
        put("crests", ALL)
        put("not a token!", ALL)
        await db.commit()

    async def emails(rules, org=None, match="all"):
        async with Session() as db:
            o = org or await db.get(Organisation, outreach.id)
            rows = await seg.resolve_contacts(db, o, {"match": match, "rules": rules})
            return {c.email for c in rows}

    async def counted(rules):
        async with Session() as db:
            return await seg.count(db, await db.get(Organisation, outreach.id), {"match": "all", "rules": rules})

    everyone = {c.email for c in contacts.values()}
    want_yes = {"full@example.com", "full2@example.com", "customer@example.com"}

    # ------------------------------------------------------------ the rule exists
    print("the rule is part of the directory field set")
    check("the engine knows the field",
          "teaser_pictures" in getattr(seg, "DIRECTORY_FIELDS", set()) and "teaser_pictures" in seg.ALL_FIELDS,
          "unknown field: the engine DROPS an unknown rule, which widens the audience to everyone")
    check("the file check exists", hasattr(ti, "scan_complete_tokens") and hasattr(ti, "complete_tokens"))

    # --------------------------------------------------------------- the files
    print("what counts as a full set on disk")
    scan = getattr(ti, "scan_complete_tokens", None)
    found = scan() if scan else None
    check("only a folder with every format as a non-empty file counts",
          found is not None and found == {clubs[k]["token"] for k in ("full", "nover", "junior", "errored",
                                                                      "nullsnap", "customer")},
          f"{sorted(found) if found is not None else None}")
    check("three of four formats (a club drawn before the dashboard format) does not count",
          found is not None and clubs["nodash"]["token"] not in found)
    check("a zero-byte file does not count",
          found is not None and clubs["emptyfile"]["token"] not in found)
    check("'crests' and a name that is not a token are never clubs",
          found is not None and "crests" not in found and "not a token!" not in found)

    # ------------------------------------------------------------- the audience
    print("Segments: club has a full set of teaser pictures = yes")
    yes = await emails([RULE("yes")])
    check("yes reaches exactly the contacts of clubs with a good snapshot AND every picture on file",
          yes == want_yes, f"got {sorted(yes)}")
    check("both contacts of a club are in it (it is a club fact, not a contact fact)",
          {"full@example.com", "full2@example.com"} <= yes)
    check("a drawn-before-the-dashboard club is NOT in it", "nodash@example.com" not in yes)
    check("a club with every file but no image_version is NOT in it (the picture route would 404)",
          "nover@example.com" not in yes)
    check("a club whose snapshot is junior-only, errored or has no body is NOT in it even with files left over",
          not ({"junior@example.com", "errored@example.com", "nullsnap@example.com"} & yes))
    check("a zero-byte picture, a never-drawn club and a never-crawled club are NOT in it",
          not ({"emptyfile@example.com", "never@example.com", "nosnapshot@example.com"} & yes))
    check("a contact with no club is NOT in it", "loner@example.com" not in yes)

    print("Segments: = no is everyone else")
    no = await emails([RULE("no")])
    check("no is every contact not in yes, with nobody in both and nobody lost",
          no == everyone - yes and not (no & yes), f"missing {sorted(everyone - yes - no)}")
    check("a contact with no directory club is in no (it would get a blank picture)", "loner@example.com" in no)
    check("count() agrees with the resolved audience",
          await counted([RULE("yes")]) == len(yes) and await counted([RULE("no")]) == len(no))

    print("the gap this closes")
    ready = await emails([{"field": "teaser_snapshot", "op": "eq", "value": ["image_ready"]}])
    check("the existing 'Snapshot and picture ready' state DOES include the drawn-before-the-dashboard club",
          "nodash@example.com" in ready, "if this fails the old state changed; re-read the guide")
    check("so the new rule is strictly the safer list of the two for an email with a picture in it",
          yes <= ready and "nodash@example.com" in ready - yes)

    # ----------------------------------------------- it renders: the picture route
    print("a club in yes really serves every picture; one outside it does not")
    from fastapi import HTTPException
    from app.routers import public_teaser as pt

    async def serves(label, fmt):
        async with Session() as db:
            try:
                r = await pt.get_teaser_image(clubs[label]["token"], fmt, db)
                return getattr(r, "status_code", 200) == 200
            except HTTPException:
                return False

    check("every format of a yes club is served by the real route",
          all([await serves("full", f) for f in ALL]))
    check("the dashboard of the drawn-before-the-dashboard club is a 404 (the broken box)",
          not await serves("nodash", "dashboard"))
    check("a club with files and no image_version is a 404", not await serves("nover", "dashboard"))
    check("a club with an ok status and no snapshot body is a 404", not await serves("nullsnap", "dashboard"))

    # ------------------------------------------------------- rules and combining
    print("it combines like any other rule")
    ok_only = await emails([RULE("yes"), {"field": "teaser_snapshot", "op": "eq", "value": ["ok"]}])
    check("AND with another teaser rule narrows", ok_only <= yes and "full@example.com" in ok_only)
    pick = await emails([RULE("yes"), {"field": "club_is", "op": "not_in", "value": [str(clubs["customer"]["mc"].id)]}])
    check("'Specific club is none of' takes a club out of it", pick == {"full@example.com", "full2@example.com"},
          f"{sorted(pick)}")
    either = await emails([RULE("yes"), dict(RULE("no"), conj="or")])
    check("yes OR no is everyone", either == everyone)

    print("fail closed")
    check("a value that is not yes or no reaches nobody",
          await emails([RULE("maybe")]) == set() and await emails([RULE("tru")]) == set())
    check("yes is case-insensitive like the other selects", await emails([RULE("YES")]) == want_yes)
    check("an unfilled rule is dropped, as for the other selects (the editor strips it before saving)",
          await emails([RULE("")]) == everyone)

    # --------------------------------------------------------------- the cache
    print("the volume is read, briefly cached, and an unmounted volume is empty")
    if not hasattr(ti, "complete_tokens"):
        check("the volume read and its cache exist", False, "club_teaser_images.complete_tokens is missing")
    else:
        full_dash = ti.image_path(clubs["full"]["token"], "dashboard")
        full_dash.unlink()
        check("a file deleted a moment ago is still counted inside the cache window (documented)",
              clubs["full"]["token"] in await ti.complete_tokens())
        fresh = await ti.complete_tokens(fresh=True)
        check("a fresh read sees it gone", clubs["full"]["token"] not in fresh)
        check("and so does the audience once the cache turns over",
              "full@example.com" not in await emails([RULE("yes")]))
        put(clubs["full"]["token"], ["dashboard"])
        await ti.complete_tokens(fresh=True)
        check("drawing it again brings the club back", "full@example.com" in await emails([RULE("yes")]))

        real_dir = ti.settings.teaser_image_dir
        ti.settings.teaser_image_dir = str(Path(TMP) / "not-mounted")
        log = io.StringIO()
        h = logging.StreamHandler(log)
        ti.logger.addHandler(h)
        try:
            none = await emails([RULE("yes")])
            everyone_no = await emails([RULE("no")])
        finally:
            ti.logger.removeHandler(h)
            ti.settings.teaser_image_dir = real_dir
            await ti.complete_tokens(fresh=True)
        check("with the volume missing, yes is nobody (fails closed) and no is everyone",
              none == set() and everyone_no == everyone)
        check("and the log says why, so an empty audience has a reason", "cannot read" in log.getvalue(), log.getvalue()[:120])

    # -------------------------------------------------------- a big set stays cheap
    print("a few thousand clubs is one bound array, not thousands of literals")
    if not hasattr(ti, "complete_tokens"):
        check("a big set is one bound array", False, "club_teaser_images.complete_tokens is missing")
    else:
        real_complete = ti.complete_tokens
        big = frozenset({clubs["full"]["token"]} | {tok() for _ in range(5000)})

        async def fake(*, fresh=False):
            return big
        ti.complete_tokens = fake
        try:
            async with Session() as db:
                q = await seg.build_query(db, await db.get(Organisation, outreach.id),
                                          {"match": "all", "rules": [RULE("yes")]})
                compiled = q.compile(dialect=postgresql.asyncpg.dialect())
                reached = {c.email for c in (await db.execute(q)).scalars().all()}
        finally:
            ti.complete_tokens = real_complete
        check("5,001 tokens become a handful of parameters", len(compiled.params) < 25, f"{len(compiled.params)} params")
        check("and the answer is still right", reached == {"full@example.com", "full2@example.com"}, f"{sorted(reached)}")

    # --------------------------------------------------------------- the scope
    print("directory only")
    jsx = (Path(__file__).resolve().parents[2] / "frontend/src/pages/admin/bettercomms/segmentFields.jsx").read_text()
    club_part, _, dir_part = jsx.partition("export const DIRECTORY_FIELD_DEFS")
    check("the picker offers it in the directory field set", "teaser_pictures:" in dir_part)
    check("and in the club field set not at all", "teaser_pictures" not in club_part)
    club_org = Organisation(id=uuid.uuid4(), name="Ordinary CC", slug="ordinary-cc")
    async with Session() as db:
        db.add(club_org)
        await db.commit()
        await db.refresh(club_org)
    check("a club build that names it gets nobody, not everybody",
          await emails([RULE("yes")], org=club_org) == set())

    # ------------------------------------------------------------ the report
    print("the coverage report")
    import app.models.db as dbmod
    dbmod.async_session_maker = Session
    from app.scripts import report_teaser_picture_coverage as rpt
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = await rpt.main([])
    body = out.getvalue()
    print("    " + body.replace("\n", "\n    "))
    num = lambda label: int(next(l for l in body.splitlines() if label in l).rsplit(":", 1)[1].split()[0])  # noqa: E731
    check("it exits 0", code == 0)
    check("it counts every club with a snapshot row (11 of the 12: one was never crawled)",
          num("Clubs with a snapshot row") == 11)
    check("junior-only, last-pull-failed and empty are the clubs with no data to build from",
          (num("junior only"), num("last pull failed"), num("empty (not placed")) == (1, 1, 1)
          and num("No data to build from") == 3)
    check("ok clubs split into full / not served / partial / customer / old data / due, adding up to the ok total",
          (num("full set of pictures on file"), num("not served"), num("partial set"), num("already a customer"),
           num("waits for a re-pull"), num("not drawn yet")) == (2, 2, 2, 0, 1, 1)
          and num("Has data (ok)") == 8,
          body)
    check("the clubs it calls full are the clubs the rule selects (2 clubs, 3 contacts)",
          num("full set of pictures on file") == 2 and len(yes) == 3)
    check("the contact counts are the Segments rule's own",
          num("= yes:") == len(yes) and num("= no: ") == len(no), body)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
