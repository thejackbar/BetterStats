"""A player's third photograph (the action shot) and the pick of which shot fills the hero position (migration 375).

Runs the SHIPPED upload, delete and serve routes, the profile PATCH, the club and public player lists, the Player Cards
snapshot and the DDL against a real Postgres. Nothing here replays their logic.

Every "X is stored" check is paired with a check that X can be absent (rule 21), and the suite reads new keys through
presence-safe accessors so the control run (the commit before this change) reports failures instead of crashing:

    createdb -h /tmp -p 5599 -U postgres actionphoto
    DATABASE_URL=postgresql+asyncpg://postgres@/actionphoto?host=/tmp&port=5599 \\
        python verification/verify_player_action_photo.py
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Organisation, Player
from app.routers import club_admin as club_admin_router
from app.routers import images as images_router
from app.routers import players as players_router

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail and not ok else ""))


MISSING = object()


def get(obj, key):
    """Presence-safe read: the control run's old code has no such key."""
    if isinstance(obj, dict):
        return obj.get(key, MISSING)
    return getattr(obj, key, MISSING)


async def attempt(coro):
    """Run a coroutine; return (result, None) or (None, exception)."""
    try:
        return await coro, None
    except Exception as e:  # noqa: BLE001
        return None, e


OURS, OTHER = uuid.uuid4(), uuid.uuid4()
P_HERO, P_ACTION, P_NONE, P_FOREIGN, P_HIDDEN = (uuid.uuid4() for _ in range(5))
HERO = b"\x89PNG-hero"
ACTION = b"\x89PNG-action-shot"
ACTION2 = b"\x89PNG-action-shot-replacement"


class FakeUser:
    id = uuid.uuid4()
    username = "verifier"


def upload(data: bytes, name: str = "a.png") -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(data))


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    async with Session() as db:
        db.add(Organisation(id=OURS, name="Applecross", slug="applecross-ap", is_active=True))
        db.add(Organisation(id=OTHER, name="Rival", slug="rival-ap", is_active=True))
        await db.flush()
        db.add(Player(id=P_HERO, name="Hero, Has", organisation_id=OURS, hero_photo_data=HERO, hero_photo_mime="image/png",
                      hero_photo_url=f"/api/images/players/{P_HERO}/hero-photo?v=1"))
        db.add(Player(id=P_ACTION, name="Action, Has", organisation_id=OURS))
        db.add(Player(id=P_NONE, name="Neither, Has", organisation_id=OURS))
        db.add(Player(id=P_FOREIGN, name="Foreign, Player", organisation_id=OTHER))
        await db.commit()


async def main() -> None:
    await seed()
    ours = None
    async with Session() as db:
        ours = await db.get(Organisation, OURS)
    other_club = None
    async with Session() as db:
        other_club = await db.get(Organisation, OTHER)

    print("the DDL")
    import importlib
    try:
        ddl = importlib.import_module("app.services.player_action_photo_ddl")
    except ImportError:
        ddl = None  # the control run: the module does not exist yet
    check("the shared DDL list exists", ddl is not None)
    if ddl is not None:
        async with engine.begin() as conn:
            for c in ("action_photo_data", "action_photo_mime", "action_photo_url", "hero_source"):
                await conn.execute(text(f"ALTER TABLE players DROP COLUMN IF EXISTS {c}"))
            for _ in range(2):  # twice: the lifespan re-runs every statement on every boot
                for stmt in ddl.STATEMENTS:
                    await conn.execute(text(stmt))
            cols = {r[0] for r in (await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='players'"))).all()}
        check("the DDL adds the four columns and is idempotent", {"action_photo_data", "action_photo_mime", "action_photo_url", "hero_source"} <= cols)
        check("hero_photo_* from migration 274 are untouched by it", {"hero_photo_data", "hero_photo_url", "hero_photo_mime"} <= cols)

    print("uploading and serving the action shot")
    up_fn = getattr(club_admin_router, "upload_player_action_photo", None)
    del_fn = getattr(club_admin_router, "delete_player_action_photo", None)
    check("the upload and delete routes exist", callable(up_fn) and callable(del_fn))
    if callable(up_fn):
        async with Session() as db:
            res, err = await attempt(up_fn(str(P_ACTION), upload(ACTION), FakeUser(), ours, db))
        url = get(res, "action_photo_url") if res else MISSING
        check("an upload answers with its address", isinstance(url, str) and f"/players/{P_ACTION}/action-photo" in url, f"{res} {err}")
        async with Session() as db:
            resp, err = await attempt(images_router.get_player_action_photo(str(P_ACTION), db))
        check("the shipped image route serves the same bytes", resp is not None and bytes(resp.body) == ACTION and resp.media_type == "image/png", str(err))
        async with Session() as db:
            row = (await db.execute(text("SELECT photo_data, hero_photo_data FROM players WHERE id=:i"), {"i": P_ACTION})).first()
        check("the headshot and hero photo columns are not touched by it", row[0] is None and row[1] is None)
        async with Session() as db:
            res2, _ = await attempt(up_fn(str(P_ACTION), upload(ACTION2), FakeUser(), ours, db))
        check("a replacement gets a new cache-busting address", bool(res2) and get(res2, "action_photo_url") != url)
        async with Session() as db:
            resp, _ = await attempt(images_router.get_player_action_photo(str(P_ACTION), db))
        check("and serves the replacement", resp is not None and bytes(resp.body) == ACTION2)
        async with Session() as db:
            _, err = await attempt(up_fn(str(P_FOREIGN), upload(ACTION), FakeUser(), ours, db))
        check("another club's player is a 404", isinstance(err, HTTPException) and err.status_code == 404, str(err))
        async with Session() as db:
            _, err = await attempt(up_fn(str(P_NONE), upload(b"x", "a.exe"), FakeUser(), ours, db))
        check("a non-image file is refused with 400", isinstance(err, HTTPException) and err.status_code == 400, str(err))
        async with Session() as db:
            _, err = await attempt(images_router.get_player_action_photo(str(P_NONE), db))
        check("a player with no action shot serves a 404 (absence is reportable)", isinstance(err, HTTPException) and err.status_code == 404)
        async with Session() as db:
            res, err = await attempt(del_fn(str(P_ACTION), FakeUser(), ours, db))
        async with Session() as db:
            row = (await db.execute(text("SELECT action_photo_data, action_photo_url FROM players WHERE id=:i"), {"i": P_ACTION})).first()
        check("delete clears the bytes and the address", row[0] is None and row[1] is None, str(err))
        # put it back for the listings below
        async with Session() as db:
            await attempt(up_fn(str(P_ACTION), upload(ACTION), FakeUser(), ours, db))

    print("hero_source on the profile PATCH")
    Update = players_router.PlayerProfileUpdate
    async def patch(pid, **kw):
        async with Session() as db:
            org = await db.get(Organisation, OURS)
            return await attempt(players_router.update_player_profile(str(pid), Update(**kw), db, FakeUser(), org))
    async def stored(pid):
        async with Session() as db:
            try:
                return (await db.execute(text("SELECT hero_source FROM players WHERE id=:i"), {"i": pid})).scalar()
            except Exception:
                return MISSING
    from app.services import player_cards
    player_cards._SNAP[str(OURS)] = (0, {"stale": True})  # a cached club snapshot, as a card page would have left
    res, err = await patch(P_ACTION, hero_source="action")
    check("changing the pick drops the cached card snapshot so the card updates now", str(OURS) not in player_cards._SNAP)
    check("pinning the action shot is stored", await stored(P_ACTION) == "action", str(err))
    check("and comes back on the profile payload", get(res, "hero_source") == "action" if res else False)
    res, err = await patch(P_ACTION, shirt_number="9")
    check("a PATCH that does not mention it leaves the pin alone", await stored(P_ACTION) == "action", str(err))
    res, err = await patch(P_ACTION, hero_source="bogus")
    check("an unknown value is a 422 and is not stored", isinstance(err, HTTPException) and err.status_code == 422 and await stored(P_ACTION) == "action", str(err))
    res, err = await patch(P_ACTION, hero_source=None)
    check("an explicit null goes back to automatic", await stored(P_ACTION) is None, str(err))
    res, err = await patch(P_ACTION, hero_source="auto")
    check("'auto' also means automatic (stored as null)", await stored(P_ACTION) is None, str(err))
    await patch(P_ACTION, hero_source="hero")
    check("'hero' can be pinned too", await stored(P_ACTION) == "hero")
    await patch(P_ACTION, hero_source=None)

    print("the lists the editor, the cards and the share card read")
    async with Session() as db:
        rows, err = await attempt(club_admin_router.list_players(FakeUser(), ours, db))
    byid = {r["id"]: r for r in (rows or [])}
    check("the club list carries the action shot address", bool(get(byid.get(str(P_ACTION), {}), "action_photo_url") not in (MISSING, None)), str(err))
    check("a player with none shows null, not a missing key", get(byid.get(str(P_NONE), {}), "action_photo_url") is None)
    check("the club list carries hero_source", get(byid.get(str(P_ACTION), {}), "hero_source") is None and "hero_source" in byid.get(str(P_ACTION), {}))
    async with Session() as db:
        pub, err = await attempt(players_router.list_players(str(OURS), False, db, None))
    pbyid = {r["id"]: r for r in (pub or [])}
    check("the public list carries it for the share card", get(pbyid.get(str(P_ACTION), {}), "action_photo_url") not in (MISSING, None), str(err))

    # The Player Cards payload (needs the cards views and tables) is checked in verify_player_cards.py.

    print("merging carries it")
    from app.services import merge_profile
    async with Session() as db:
        keep = await db.get(Player, P_NONE)
        rem = await db.get(Player, P_ACTION)
        filled = merge_profile.carry_profile(keep, rem) if hasattr(Player, "action_photo_data") else []
        await db.flush()
        check("the keeper with no action shot receives the other's bytes", "action_photo_url" in filled and bytes(getattr(keep, "action_photo_data", b"") or b"") == ACTION, str(filled))
        check("the address is rebuilt for the keeper, not left on the removed player",
              merge_profile.image_url_owner(getattr(keep, "action_photo_url", None)) == str(P_NONE))
        await db.rollback()

    print("smaller copies of a photo (?w=)")
    from PIL import Image
    from app.services import image_sizes

    def jpeg(size, orientation=None):
        im = Image.new("RGB", size, (200, 30, 30))
        im.paste((30, 30, 200), (0, 0, size[0] // 2, size[1] // 2))
        buf = io.BytesIO()
        exif = Image.Exif()
        if orientation:
            exif[274] = orientation
        im.save(buf, format="JPEG", quality=95, exif=exif.tobytes() if orientation else b"")
        return buf.getvalue()

    def png_alpha(size):
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        im.paste((255, 0, 0, 255), (0, 0, size[0] // 2, size[1]))
        buf = io.BytesIO(); im.save(buf, format="PNG"); return buf.getvalue()

    P_BIG, P_ROT, P_ALPHA, P_SMALL, P_TWO = (uuid.uuid4() for _ in range(5))
    big, rot, alpha, small = jpeg((3200, 2400)), jpeg((2400, 1600), orientation=6), png_alpha((2000, 3000)), jpeg((300, 200))
    async with Session() as db:
        for pid, data, mime in ((P_BIG, big, "image/jpeg"), (P_ROT, rot, "image/jpeg"), (P_ALPHA, alpha, "image/png"), (P_SMALL, small, "image/jpeg")):
            db.add(Player(id=pid, name=f"Size {str(pid)[:4]}", organisation_id=OURS, hero_photo_data=data, hero_photo_mime=mime, photo_data=small, photo_mime="image/jpeg"))
        await db.commit()
    image_sizes.clear()

    async def fetch(pid, kind="hero", **kw):
        fn = {"hero": images_router.get_player_hero_photo, "photo": images_router.get_player_photo, "action": images_router.get_player_action_photo}[kind]
        async with Session() as db:
            return await attempt(fn(str(pid), db, **kw))

    def dims(resp):
        with Image.open(io.BytesIO(bytes(resp.body))) as im:
            return im.size, im.format
    r, e = await fetch(P_BIG)
    check("with no size the original bytes are served, as before", r is not None and bytes(r.body) == big, str(e))
    r, e = await fetch(P_BIG, w=700, v="a1")
    check("a 700 wide request is served at the next size up (800 wide), as a JPEG", r is not None and dims(r) == ((800, 600), "JPEG") and r.media_type == "image/jpeg", str(e))
    check("...and is far smaller than the upload", r is not None and len(r.body) < len(big) / 5, f"{len(r.body) if r else 0} vs {len(big)}")
    r2, _ = await fetch(P_BIG, w=790, v="a1")
    check("two widths in the same size share one copy", r2 is not None and bytes(r2.body) == bytes(r.body) and len(image_sizes._cache) == 1, str(len(image_sizes._cache)))
    r3, _ = await fetch(P_BIG, w=100000, v="a1")
    check("a huge width is held to the largest size (1200), and the cache stays small", r3 is not None and dims(r3)[0][0] == 1200 and len(image_sizes._cache) == 2)
    r, e = await fetch(P_ROT, w=800, v="b1")
    check("a phone photo with EXIF rotation is turned upright in its copy", r is not None and dims(r)[0] == (800, 1200), str(dims(r) if r else e))
    r, e = await fetch(P_ALPHA, w=480, v="c1")
    check("a photo with transparency stays a PNG, with its transparency", r is not None and dims(r) == ((480, 720), "PNG") and Image.open(io.BytesIO(bytes(r.body))).convert("RGBA").getpixel((400, 10))[3] == 0, str(e))
    r, e = await fetch(P_SMALL, w=800, v="d1")
    check("a photo already smaller than the size is served untouched", r is not None and bytes(r.body) == small, str(e))
    r, e = await fetch(P_HERO, w=800, v="e1")
    check("bytes that are not an image are served as uploaded, not a 500", r is not None and bytes(r.body) == HERO, str(e))
    r, e = await fetch(P_NONE, w=800)
    check("a player with no hero photo is still a 404", r is None and isinstance(e, HTTPException) and e.status_code == 404)
    r, e = await fetch(P_BIG, kind="photo", w=240, v="f1")
    check("the headshot route takes a size too", r is not None and dims(r)[0] == (240, 160), str(e))
    check("the cache headers are unchanged", r is not None and "max-age=604800" in r.headers.get("cache-control", ""))
    async with Session() as db:
        await db.execute(text("UPDATE players SET hero_photo_data = :d WHERE id = :i"), {"d": jpeg((3200, 2400)), "i": P_BIG}); await db.commit()
    r4, _ = await fetch(P_BIG, w=700, v="a1")
    check("a photo that changes under the same version is not served from a stale copy", r4 is not None and bytes(r4.body) != bytes(r.body))
    from sqlalchemy import event
    statements = []
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _log(conn, cursor, stmt, params, ctx, many): statements.append(stmt)
    await fetch(P_BIG, w=800, v="a1")
    event.remove(engine.sync_engine, "before_cursor_execute", _log)
    photo_reads = [x for x in statements if "players" in x.lower()]
    check("an image request reads only the column it serves", photo_reads and all("hero_photo_data" in x and "action_photo_data" not in x and " photo_data" not in x.replace("hero_photo_data", "") for x in photo_reads), str(photo_reads)[:300])

    print("the control: it can be absent")
    async with Session() as db:
        n = (await db.execute(text("SELECT count(*) FROM players WHERE action_photo_data IS NULL"))).scalar()
    check("players without an action shot stay without one (the suite can see absence)", n >= 2)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", *FAIL, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
