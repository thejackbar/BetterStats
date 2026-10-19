"""Verification: an honour board can list one award by name, and a cap reads "Cap 186".

Reported by Shoalwater Bay CC: their A Grade cap numbers were imported as Club Award
rows named "A Grade Cap Number" with the number in the detail and no subcategory.
An auto honour board could only pick a category (+ subcategory), so a board on
"Club Award" would list EVERY club award, men's and ladies' caps together, and a cap
showed as a bare "186" (or none at all on the profile).

Runs the SHIPPED route bodies (`website._auto_entries`, `_auto_count`,
`admin_create_board` / `admin_update_board`, `club_room._expand_honour_boards`) on a
real Postgres, over the records suite's schema. Every "only the caps are listed"
check is paired with one proving the other awards COULD have been listed (a board
with no filter lists them all), and "Captain"/"436 runs at 39.64" must keep their
detail exactly as typed.

CONTROL MODE. Against the commit before the change the filter does not exist, so the
named-award checks fail without crashing (every call is wrapped, new names are read
through presence-safe accessors).

Run:  DATABASE_URL=postgresql+asyncpg://root@/honour_caps?host=/var/run/postgresql \
      python verification/verify_honour_board_caps.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_records_timing as vrt  # noqa: E402
from app.models.db import ClubHonourBoard, Organisation
from app.routers import club_room as cr
from app.routers import website as web

try:
    from app.services import cap_awards
except Exception:  # noqa: BLE001 - the control has no such module
    cap_awards = None
try:
    from app.services.honour_board_achievement_ddl import STATEMENTS as ACH_DDL
except Exception:  # noqa: BLE001
    ACH_DDL = None

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


async def S(make):
    """Run `make()` and await it. The call is built INSIDE the try, so a keyword the
    previous commit does not know raises here and is reported as a failed check."""
    try:
        return await make(), None
    except Exception as exc:  # noqa: BLE001 - the control raises; report it, do not crash
        return None, f"{type(exc).__name__}: {exc}"


async def seed(db) -> None:
    # A raw-SQL lifespan table (main.py), so `create_all` cannot know it. Copied
    # column for column, including the later ALTER.
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS player_achievements (
            id SERIAL PRIMARY KEY,
            org_id UUID NOT NULL,
            player_id UUID,
            player_name TEXT NOT NULL,
            season TEXT,
            category TEXT NOT NULL,
            subcategory TEXT,
            achievement TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    await db.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS season_end TEXT"))
    async def ach(season, sub, name, player, detail, category="Club Award"):
        await db.execute(text(
            "INSERT INTO player_achievements (org_id, player_name, season, category, subcategory, achievement, detail) "
            "VALUES (:o, :p, :s, :c, :sub, :a, :d)"),
            {"o": vrt.ORG, "p": player, "s": season, "c": category, "sub": sub, "a": name, "d": detail})

    # Out of order on purpose: season order and cap order disagree.
    await ach("Summer 2014/15", None, "A Grade Cap Number", "Sample Cc", "188")
    await ach("Summer 2013/14", None, "A Grade Cap Number", "Sample Aa", "186")
    await ach("Summer 2013/14", None, "a grade cap number ", "Sample Bb", "#187")  # case, spaces and a hash
    await ach("Summer 2013/14", None, "Women's A Grade Cap Number", "Sample Ww", "5")
    await ach("Summer 2013/14", "1st XI", "Best Batter", "Sample Bat", "436 runs at 39.64")
    await ach("Summer 2013/14", None, "Captain", "Sample Cap", "12")
    await ach("Summer 2013/14", None, "A Grade Cap Number", "Sample Dd", "no number yet")
    await db.commit()


async def board(db, **kw):
    b = ClubHonourBoard(organisation_id=vrt.ORG, title=kw.pop("title"), columns=1, **kw)
    db.add(b)
    await db.commit()
    return b.id


async def entries(db, **kw):
    res, err = await S(lambda: web._auto_entries(vrt.ORG, "Club Award", None, db, **kw))
    return res, err


def names(rows):
    return [r["name"] for r in (rows or [])]


async def main() -> None:
    await vrt.build_schema()
    async with vrt.Session() as s:
        await vrt.seed(s)
        await seed(s)

    async with vrt.Session() as db:
        print("== the cap rule")
        if cap_awards is None:
            check("cap_awards module exists", False, "not present")
        else:
            ok = cap_awards.is_cap_award
            check("'A Grade Cap Number', '1st XI Cap' and 'Club Cap' are caps",
                  ok("Club Award", None, "A Grade Cap Number") and ok("Club Award", "1st XI", "1st XI Cap") and ok("Club Award", None, "Club Cap"))
            check("Milestone > Cap Number 'Player Number' is a cap", ok("Milestone", "Cap Number", "Player Number"))
            check("'Captain', 'Best Batter', '100 Game Number' are not caps (so the rule can say no)",
                  not ok("Club Award", None, "Captain") and not ok("Club Award", None, "Best Batter")
                  and not ok("Milestone", "Cap Number", "100 Game Number") and not ok("Premiership", None, "Captain's Award"))
            check("'#186' and ' 186 ' read as 186; '186a' and '' do not",
                  cap_awards.cap_number("#186") == 186 and cap_awards.cap_number(" 186 ") == 186
                  and cap_awards.cap_number("186a") is None and cap_awards.cap_number("") is None
                  and cap_awards.cap_label("186") == "Cap 186" and cap_awards.cap_label("none") is None)

        print("== a board on 'Club Award' with no filter (what the club had)")
        rows, err = await entries(db)
        check("it lists every award in the category, caps and the rest together", err is None and len(rows or []) == 7, f"{len(rows or [])} {err}")

        print("== only 'A Grade Cap Number'")
        rows, err = await entries(db, achievement="A Grade Cap Number")
        check("the call is accepted", err is None, str(err))
        got = names(rows)
        check("only the men's caps are listed (the women's, Best Batter and Captain are not)",
              sorted(got) == ["Sample Aa", "Sample Bb", "Sample Cc", "Sample Dd"], str(got))
        details = {r["name"]: r["detail"] for r in (rows or [])}
        check("each cap reads 'Cap N'", details.get("Sample Aa") == "Cap 186" and details.get("Sample Bb") == "Cap 187"
              and details.get("Sample Cc") == "Cap 188", str(details))
        check("a cap with no number keeps its detail as typed", details.get("Sample Dd") == "no number yet", str(details))
        check("the name match ignores case and spaces ('a grade cap number ' was matched)", "Sample Bb" in got, str(got))

        print("== a board that is all numbered caps reads in cap order")
        rows, err = await entries(db, achievement="Women's A Grade Cap Number")
        check("the ladies' caps are a board of their own", names(rows) == ["Sample Ww"] and (rows or [{}])[0].get("detail") == "Cap 5", str(rows))
        rows_all, _ = await S(lambda: web._auto_entries(vrt.ORG, "Club Award", None, db, "A Grade Cap Number"))
        check("a board that includes an un-numbered cap falls back to newest season first",
              (names(rows_all) or [None])[0] == "Sample Cc", str(names(rows_all)))
        await db.execute(text("DELETE FROM player_achievements WHERE detail = 'no number yet'"))
        await db.commit()
        rows, _ = await entries(db, achievement="A Grade Cap Number")
        check("with every cap numbered, the board is in cap order, not season order",
              names(rows) == ["Sample Aa", "Sample Bb", "Sample Cc"], str(names(rows)))

        print("== other awards keep their detail exactly as typed")
        rows, _ = await entries(db)
        d = {r["name"]: r["detail"] for r in (rows or [])}
        check("'436 runs at 39.64' and a Captain's '12' are untouched",
              d.get("Sample Bat") == "436 runs at 39.64" and d.get("Sample Cap") == "12", str(d))

        print("== the count beside the board")
        res, err = await S(lambda: web._auto_count(vrt.ORG, "Club Award", None, db, "A Grade Cap Number"))
        check("auto_count counts only that award", err is None and res == 3, f"{res} {err}")
        res, err = await S(lambda: web._auto_count(vrt.ORG, "Club Award", None, db))
        check("and counts the whole category without a filter", err is None and res == 6, f"{res} {err}")

        print("== saving a board: create, edit, leave alone, clear")
        org = await db.get(Organisation, vrt.ORG)
        body, err = await S(lambda: asyncio.sleep(0, web.BoardBody(
            title="Men's A Grade Caps", source_category="Club Award", source_achievement=" A Grade Cap Number ")))
        made, err = await S(lambda: web.admin_create_board(body, _=None, club=org, db=db))
        check("a board is created with the award name (trimmed)", err is None and (made or {}).get("source_achievement") == "A Grade Cap Number" and (made or {}).get("auto_count") == 3, f"{made} {err}")
        bid = (made or {}).get("id")
        upd, err = await S(lambda: web.admin_update_board(bid, web.BoardBody(title="Men's A Grade Caps", source_category="Club Award", description="x"), _=None, club=org, db=db))
        check("an edit that does not send the field leaves it alone", err is None and (upd or {}).get("source_achievement") == "A Grade Cap Number", f"{upd} {err}")
        upd, err = await S(lambda: web.admin_update_board(bid, web.BoardBody(title="Men's A Grade Caps", source_category="Club Award", source_achievement=None), _=None, club=org, db=db))
        check("an explicit null clears it", err is None and (upd or {}).get("source_achievement") is None and (upd or {}).get("auto_count") == 6, f"{upd} {err}")
        await S(lambda: web.admin_update_board(bid, web.BoardBody(title="Men's A Grade Caps", source_category="Club Award", source_achievement="A Grade Cap Number"), _=None, club=org, db=db))
        await S(lambda: web.admin_create_board(web.BoardBody(title="Ladies' A Grade Caps", source_category="Club Award", source_achievement="Women's A Grade Cap Number"), _=None, club=org, db=db))
        await S(lambda: web.admin_create_board(web.BoardBody(title="Every club award", source_category="Club Award"), _=None, club=org, db=db))
        opts, err = await S(lambda: web.admin_honour_achievements("Club Award", None, _=None, club=org, db=db))
        check("the picker lists the award names in the category with counts",
              err is None and {o["achievement"]: o["count"] for o in (opts or [])}.get("A Grade Cap Number") == 3, f"{opts} {err}")

        print("== the same boards on the Club Room TV and the public site")
        slides, err = await S(lambda: cr._expand_honour_boards(db, org, {}))
        by_title = {s["title"]: s for s in (slides or [])}
        men = by_title.get("Men's A Grade Caps", {})
        check("the TV board lists only the men's caps, as 'Cap N', in cap order",
              err is None and [(e["name"], e["detail"]) for e in men.get("entries", [])]
              == [("Sample Aa", "Cap 186"), ("Sample Bb", "Cap 187"), ("Sample Cc", "Cap 188")], f"{men} {err}")
        check("the ladies' board is separate", [e["name"] for e in by_title.get("Ladies' A Grade Caps", {}).get("entries", [])] == ["Sample Ww"], str(by_title.get("Ladies' A Grade Caps")))
        check("a board with no filter still lists the whole category (an existing board is unchanged)",
              len(by_title.get("Every club award", {}).get("entries", [])) == 6, str(len(by_title.get("Every club award", {}).get("entries", []))))

        print("== the migration's DDL")
        if ACH_DDL is None:
            check("the shared DDL list exists", False, "not present")
        else:
            await db.rollback()  # an open read transaction on the table would block the ALTER below
            async with vrt.engine.begin() as conn:
                for _ in range(2):  # the lifespan re-runs it on every boot
                    for stmt in ACH_DDL:
                        await conn.execute(text(stmt))
            col = (await db.execute(text(
                "SELECT 1 FROM information_schema.columns WHERE table_name='club_honour_boards' AND column_name='source_achievement'"))).first()
            check("source_achievement exists and the statements re-run cleanly", col is not None)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
