"""A player typed into a BetterPosts lineup (v9.106.37), against a real Postgres.

Runs the SHIPPED `services/similar_players.find_similar` and the shipped
`club_admin` route bodies (`create_player`, `similar_players`,
`upload_player_photo`) over a club with a roster, a person who asked to be
removed, and a second club with a same-named player.

  * a typed name that is already on the roster is offered back (exact, short
    form "Steve" / "Steven", "Surname Initial"), best first;
  * a name nobody holds comes back empty, and the pairing check is a contrast:
    the same call DOES return a player for a name the club holds;
  * a person who asked to be removed is never offered, and another club's
    player is never offered;
  * `create_player` keeps a role and derives the skill code, refuses an unknown
    role, and leaves a roleless player as before;
  * the photo route stores a headshot on the new player.

CONTROL MODE: run against the commit before this change. `similar_players` does
not exist there and `PlayerCreate` has no role, so the checks report as failed
rather than crashing (everything new is read through getattr / find_spec).

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/mp_test?host=/var/run/postgresql \
      python verification/verify_social_manual_player.py
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException, UploadFile
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Organisation, Player
import app.models.scout  # noqa: F401
from app.routers import club_admin as ca

HAVE = importlib.util.find_spec("app.services.similar_players") is not None
find_similar = importlib.import_module("app.services.similar_players").find_similar if HAVE else None

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1; print(f"  ok   {label}")
    else:
        FAIL += 1; print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


async def similar(db, org, name):
    if find_similar is None:
        return None
    return await find_similar(db, org, name)


def names(rows):
    return [r["name"] for r in rows] if rows is not None else None


async def main():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    OURS, OTHER = uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add_all([Organisation(id=OURS, name="Ours CC", slug="ours"), Organisation(id=OTHER, name="Other CC", slug="other")])
        await db.flush()
        mk = lambda n, org=OURS, **kw: Player(id=uuid.uuid4(), name=n, organisation_id=org, **kw)
        hidden = mk("Trent, Hidden")
        hidden.privacy_hidden_at = datetime.now(timezone.utc)
        db.add_all([
            mk("Smith, Steven", player_role="All Rounder", photo_url="/api/images/players/x/photo"),
            mk("North, Ash", player_role="All Rounder"),
            mk("Abbey, Jayden"), mk("Abbey, Nate"),
            mk("Camarda, Frank"),
            hidden,
            mk("Elsewhere, Gus", org=OTHER),
        ])
        await db.commit()

    club = SimpleNamespace(id=OURS)
    user = SimpleNamespace(id=uuid.uuid4())
    print("similar players")
    async with Session() as db:
        r = await similar(db, OURS, "Ash North")
        check("an exact name is offered, at full confidence", r is not None and names(r)[:1] == ["North, Ash"] and r[0]["confidence"] >= 1.0, str(r))
        check("the offer carries role and photo for the picker", r is not None and r[0]["player_role"] == "All Rounder" and "photo_url" in r[0], str(r))
        r = await similar(db, OURS, "Steve Smith")
        check("a short form (Steve for Steven) is offered", r is not None and "Smith, Steven" in names(r), str(r))
        r = await similar(db, OURS, "F Camarda")
        check("'Initial Surname' is offered for the one Frank", r is not None and names(r)[:1] == ["Camarda, Frank"], str(r))
        r = await similar(db, OURS, "Nate Abbey")
        check("two Abbeys: the right one leads", r is not None and names(r)[:1] == ["Abbey, Nate"], str(r))
        r = await similar(db, OURS, "Zed Nobody")
        check("a name nobody holds comes back empty", r == [], str(r))
        r = await similar(db, OURS, "Hidden Trent")
        check("a person who asked to be removed is never offered", r == [], str(r))
        r = await similar(db, OURS, "Gus Elsewhere")
        check("another club's player is never offered", r == [], str(r))
        r = await similar(db, OURS, "   ")
        check("a blank name offers nothing", r == [] , str(r))

    print("create_player")
    async with Session() as db:
        PC = ca.PlayerCreate
        has_role_field = "player_role" in getattr(PC, "model_fields", {})
        check("PlayerCreate accepts a role", has_role_field)
        body = PC(first_name="Rhys", last_name="Newman", **({"player_role": "All Rounder"} if has_role_field else {}))
        made = await ca.create_player(body, current_user=user, club=club, db=db)
        row = (await db.execute(select(Player).where(Player.id == uuid.UUID(made["id"])))).scalar_one()
        check("stored as 'Last, First' in the club", row.name == "Newman, Rhys" and row.organisation_id == OURS)
        check("the role is kept", row.player_role == "All Rounder", str(row.player_role))
        check("the skill code is derived from the role", list(row.skill_positions or []) == ["ALL"], str(row.skill_positions))
        check("the reply is roster-shaped (role, photo keys, id)", all(k in made for k in ("id", "player_role", "photo_url", "display_name")), str(sorted(made)))
        plain = await ca.create_player(PC(first_name="No", last_name="Role"), current_user=user, club=club, db=db)
        prow = (await db.execute(select(Player).where(Player.id == uuid.UUID(plain["id"])))).scalar_one()
        check("a roleless player is created as before", prow.player_role is None and list(prow.skill_positions or []) == [])
        if has_role_field:
            try:
                await ca.create_player(PC(first_name="Bad", last_name="Role", player_role="Opener"), current_user=user, club=club, db=db)
                check("an unknown role is refused", False)
            except HTTPException as e:
                check("an unknown role is refused", e.status_code == 422)
        else:
            check("an unknown role is refused", False, "no role field")

        print("after it is created, it is found")
        r = await similar(db, OURS, "Rhys Newman")
        check("the new player is offered next time (no second record)", r is not None and "Newman, Rhys" in names(r), str(r))

        print("photo")
        up = UploadFile(filename="face.png", file=__import__("io").BytesIO(b"\x89PNG\r\n\x1a\nfake"))
        out = await ca.upload_player_photo(made["id"], file=up, current_user=user, club=club, db=db)
        row = (await db.execute(select(Player).where(Player.id == uuid.UUID(made["id"])))).scalar_one()
        check("the photo is stored on the new player", row.photo_data is not None and out.get("photo_url", "").startswith("/api/images/players/"), str(out))

        print("route")
        fn = getattr(ca, "similar_players", None)
        if fn is None:
            check("the similar-players route answers", False, "route missing")
        else:
            res = await fn(ca.PlayerSimilarQuery(name="Ash North"), current_user=user, club=club, db=db)
            check("the similar-players route answers with candidates", res["candidates"][:1] and res["candidates"][0]["name"] == "North, Ash", str(res))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
