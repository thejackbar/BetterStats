"""Verification for the Club Room "Honour Boards" slide, against a real Postgres.

Shoalwater Bay asked to put their honour boards on the club room TV and found
no such slide type. This runs the SHIPPED ``club_room.build_play_payload`` (the
one place a saved playlist becomes rendered slides, shared by the admin preview
and the public /room/{token} link) and the shipped ``list_honour_sources`` route
body, over a club with:

  - two hand-built honour boards (one with a no-year entry, one that also pulls
    from an award category) and one empty board,
  - a premiership flag with a named competition, one with the bare word, and a
    captain recorded as their own award row,
  - office bearers and life members.

A second club with its own board proves nothing crosses over.

Every "X is absent" check is paired with a check that X could be present (rule
21).

CONTROL MODE. Run against the commit BEFORE this change, an "honours" playlist
entry is silently skipped, so every slide check fails and nothing crashes: the
payload is read through presence-safe accessors.

Run:  DATABASE_URL=postgresql+asyncpg://root@/honours_room?host=/var/run/postgresql \
      python verification/verify_club_room_honours.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Organisation
from app.routers import club_room as cr

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


OURS, OTHER = uuid.uuid4(), uuid.uuid4()
B_ROLL, B_HOF, B_EMPTY, B_OTHER = (uuid.uuid4() for _ in range(4))

# (category, subcategory, achievement, name, season, detail)
ACH = [
    ("Premiership", "1st XI", "A Grade Premiership", "Wes West", "2019/20", None),
    ("Premiership", "1st XI", "A Grade Premiership", "Xavi Xu", "2019/20", "Player of the Match"),
    ("Premiership", "1st XI", "A Grade Premiership", "Yan Yu", "2019/20", None),
    ("Premiership", "1st XI", "Captain", "Wes West", "2019/20", None),
    ("Premiership", "2nd XI", "Premiership", "Zed Zhou", "2015/16", None),
    ("Office Bearer", "Executive Committee", "President", "Pat Price", "2010/11", None),
    ("Office Bearer", "Executive Committee", "President", "Rob Reed", "2018/19", None),
    ("Office Bearer", "Executive Committee", "Secretary", "Sam Shaw", "2015/16", None),
    ("Life Membership", "Club", "Life Membership", "Allan Godfrey", "1985/86", None),
    ("Life Membership", "Club", "Life Membership", "Beryl Brown", "1978/79", None),
    ("Hall of Fame", None, "Inducted", "Hana Hill", "2021/22", "Inducted for services to the club"),
]


async def play(db, org, entries: list[tuple[str, dict]]) -> list[dict]:
    """Save a playlist for the club and read back what the TV would show."""
    await db.execute(text("DELETE FROM club_room_slides WHERE organisation_id = :o"), {"o": org.id})
    for i, (stype, cfg) in enumerate(entries):
        await db.execute(text(
            "INSERT INTO club_room_slides (id, organisation_id, slide_type, config, position, enabled) "
            "VALUES (gen_random_uuid(), :o, :t, CAST(:c AS jsonb), :p, true)"),
            {"o": org.id, "t": stype, "c": __import__("json").dumps(cfg), "p": i})
    await db.commit()
    payload = await cr.build_play_payload(db, org)
    return [s for s in payload.get("slides", []) if s.get("type") == "honours"]


def by_title(slides: list[dict], title: str) -> dict:
    return next((s for s in slides if s.get("title") == title), {})


def names(slide: dict) -> list[str]:
    return [e.get("name") for e in slide.get("entries", [])]


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # The lifespan's own player_achievements / award-definition DDL, column for column (rule 24).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID, player_name TEXT NOT NULL,
                season TEXT, category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL,
                detail TEXT, created_at TIMESTAMPTZ DEFAULT NOW())"""))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS season_end TEXT"))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS import_batch_id UUID"))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS club_role_id UUID"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_award_definitions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                category TEXT NOT NULL, subcategory TEXT, achievement TEXT, display_name TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0, active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))

        for oid, name, slug in ((OURS, "Shoalwater Bay CC", "shoalwater"), (OTHER, "Other CC", "otherclub")):
            await conn.execute(text(
                "INSERT INTO organisations (id, name, slug, is_active) VALUES (:i,:n,:s,true)"),
                {"i": oid, "n": name, "s": slug})
        for cat, sub, ach, name, season, detail in ACH:
            await conn.execute(text(
                "INSERT INTO player_achievements (org_id, player_name, season, category, subcategory, achievement, detail) "
                "VALUES (:o, :n, :s, :c, :sub, :a, :d)"),
                {"o": OURS, "n": name, "s": season, "c": cat, "sub": sub, "a": ach, "d": detail})

        boards = [
            (B_ROLL, OURS, "Batting Honour Roll", "Centuries for the club", None, 2, 0),
            (B_HOF, OURS, "Hall of Fame", None, "Hall of Fame", 1, 1),
            (B_EMPTY, OURS, "Not Filled In Yet", None, None, 1, 2),
            (B_OTHER, OTHER, "Somebody Else's Board", None, None, 1, 0),
        ]
        for bid, org, title, desc, src, cols, order in boards:
            await conn.execute(text(
                "INSERT INTO club_honour_boards (id, organisation_id, title, description, source_category, columns, display_order) "
                "VALUES (:i,:o,:t,:d,:s,:c,:ord)"),
                {"i": bid, "o": org, "t": title, "d": desc, "s": src, "c": cols, "ord": order})
        entries = [
            (B_ROLL, 2019, "Sam Shaw", "142 v Rivals", 0),
            (B_ROLL, 2015, "Pat Price", None, 1),
            (B_ROLL, None, "Old Timer", "year not recorded", 2),
            (B_OTHER, 2001, "Not Ours", None, 0),
        ]
        for bid, year, name, detail, order in entries:
            await conn.execute(text(
                "INSERT INTO club_honour_entries (id, board_id, year, name, detail, display_order) "
                "VALUES (gen_random_uuid(), :b, :y, :n, :d, :o)"),
                {"b": bid, "y": year, "n": name, "d": detail, "o": order})

    async with Session() as db:
        ours = await db.get(Organisation, OURS)
        other = await db.get(Organisation, OTHER)

        print("== our honour boards")
        s = await play(db, ours, [("honours", {"kind": "boards"})])
        check("one slide per non-empty board (the empty board is skipped)",
              [x.get("title") for x in s] == ["Batting Honour Roll", "Hall of Fame"],
              str([x.get("title") for x in s]))
        roll = by_title(s, "Batting Honour Roll")
        check("the club's own order and entries come through, no-year entry kept",
              names(roll) == ["Sam Shaw", "Pat Price", "Old Timer"], str(names(roll)))
        check("year is the label, a missing year is no label",
              [e.get("label") for e in roll.get("entries", [])] == ["2019", "2015", None])
        check("detail, description and the board's own column count come through",
              roll.get("entries", [{}])[0].get("detail") == "142 v Rivals"
              and roll.get("subtitle") == "Centuries for the club" and roll.get("columns") == 2)
        hof = by_title(s, "Hall of Fame")
        check("a board that pulls from an award category shows those players",
              names(hof) == ["Hana Hill"] and hof["entries"][0].get("label") == "2021"
              and hof["entries"][0].get("detail") == "Inducted for services to the club", str(hof))
        check("another club's board is not shown to us", not by_title(s, "Somebody Else's Board"))
        s_other = await play(db, other, [("honours", {"kind": "boards"})])
        check("and it IS shown to the club that owns it (the absence above is a real check)",
              [x.get("title") for x in s_other] == ["Somebody Else's Board"])
        check("our boards are not shown to them", not by_title(s_other, "Batting Honour Roll"))

        print("== one board, picked")
        s = await play(db, ours, [("honours", {"kind": "boards", "board_id": str(B_HOF)})])
        check("picking a board shows only that board", [x.get("title") for x in s] == ["Hall of Fame"])
        s = await play(db, ours, [("honours", {"kind": "boards", "board_id": str(B_OTHER)})])
        check("picking another club's board id shows nothing", s == [])
        s = await play(db, ours, [("honours", {"kind": "boards", "board_id": "not-a-uuid"})])
        check("a junk board id shows nothing instead of failing the whole show", s == [])
        s = await play(db, ours, [("honours", {"kind": "sideways"})])
        check("an unknown kind falls back to the club's own boards", len(s) == 2)
        s = await play(db, ours, [("honours", {})])
        check("a bare config is the club's own boards", len(s) == 2)

        print("== premiership squads")
        s = await play(db, ours, [("honours", {"kind": "premierships"})])
        check("one slide per flag, newest first",
              [x.get("title") for x in s] == ["2019/20 · 1st XI", "2015/16 · 2nd XI"], str([x.get("title") for x in s]))
        flag = s[0] if s else {}
        check("the competition is the subtitle", flag.get("subtitle") == "A Grade Premiership")
        check("the squad is all three players, the captain row joins the one flag",
              sorted(names(flag)) == ["Wes West", "Xavi Xu", "Yan Yu"], str(names(flag)))
        details = {e["name"]: e.get("detail") for e in flag.get("entries", [])}
        check("a part in the win sits beside the name", details.get("Wes West") == "Captain"
              and details.get("Xavi Xu") == "Player of the Match" and details.get("Yan Yu") is None, str(details))
        check("a bare 'Premiership' names no competition (no subtitle repeating the page's subject)",
              (s[1] if len(s) > 1 else {}).get("subtitle") is None)

        print("== office bearers and life members")
        s = await play(db, ours, [("honours", {"kind": "office_bearers"})])
        titles = [(x.get("eyebrow"), x.get("title")) for x in s]
        check("a slide per role, groups in the standard order, life members last",
              titles == [("Executive Committee", "President"), ("Executive Committee", "Secretary"),
                         ("Life Members", "Life Membership")], str(titles))
        pres = by_title(s, "President")
        check("holders newest first, with their years as the label",
              [(e["name"], e["label"]) for e in pres.get("entries", [])] == [("Rob Reed", "2018"), ("Pat Price", "2010")],
              str(pres.get("entries")))
        s = await play(db, ours, [("honours", {"kind": "office_bearers", "group": "Life Members"})])
        check("narrowing to a group shows only that group",
              [x.get("title") for x in s] == ["Life Membership"]
              and names(s[0]) == ["Allan Godfrey", "Beryl Brown"],
              str([names(x) for x in s]))
        s = await play(db, ours, [("honours", {"kind": "office_bearers", "group": "Nobody Has This Group"})])
        check("a group nobody has shows nothing", s == [])

        print("== the playlist")
        s = await play(db, ours, [("honours", {"kind": "premierships"}), ("honours", {"kind": "boards"})])
        ids = [x.get("id") for x in s]
        check("two honours entries in one playlist give distinct slide ids", len(ids) == len(set(ids)) == 4, str(ids))

        print("== the picker route")
        route = getattr(cr, "list_honour_sources", None)  # presence-safe: the control has no such route
        src = await route(current_user=None, club=ours, db=db) if route else {}
        check("lists our boards in the club's order and none of the other club's",
              [b["title"] for b in src.get("boards", [])] == ["Batting Honour Roll", "Hall of Fame", "Not Filled In Yet"],
              str(src))
        check("lists the office-bearer groups", src.get("groups") == ["Executive Committee", "Life Members"], str(src.get("groups")))
        src_o = await route(current_user=None, club=other, db=db) if route else {}
        check("the other club sees only its own", [b["title"] for b in src_o.get("boards", [])] == ["Somebody Else's Board"])

        print("== the type is accepted")
        check("'honours' is a slide type the create route accepts", "honours" in cr.SLIDE_TYPES)

        # The browser check (frontend/verification/verify_club_room_honours_browser.mjs)
        # reads this file, so the screens are driven with the shipped payload shape.
        fixture = os.environ.get("CLUB_ROOM_FIXTURE")
        if fixture and route:
            import json
            slides = await play(db, ours, [
                ("honours", {"kind": "boards"}), ("honours", {"kind": "premierships"}),
                ("honours", {"kind": "office_bearers"}),
            ])
            payload = await cr.build_play_payload(db, ours)
            payload["slides"] = slides
            Path(fixture).write_text(json.dumps(
                {"play": payload, "sources": await route(current_user=None, club=ours, db=db)}, indent=2))

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
