"""Verification: the Club Room "Honour Boards" slide can list awards from the club's own records.

Asked for by Shoalwater Bay CC: their A Grade cap numbers are Club Award rows named
"A Grade Cap Number" (number in the detail). Showing them on the TV meant making an
honour board on the website admin first. A club that does not use that page should be
able to do it from Club Room Mode: `config.kind = "awards"` with a category and an
optional exact award name.

Runs the SHIPPED `club_room.build_play_payload`, `list_honour_sources`, `list_award_names`
and `_entry_summary` on a real Postgres over the records suite's schema. Every "only the
men's caps" check is paired with one proving the rest COULD have been listed (no award
name lists the whole category), and another club's awards of the same name must not appear.

CONTROL MODE. Against the commit before the change the "awards" kind is read as the default
(a board) and nothing plays; the new route names are read through presence-safe accessors,
so the checks fail without crashing.

Run:  DATABASE_URL=postgresql+asyncpg://root@/room_awards?host=/var/run/postgresql \
      python verification/verify_club_room_award_slides.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_records_timing as vrt  # noqa: E402
from app.models.db import Organisation
from app.routers import club_room as cr

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


async def seed(db) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS player_achievements (
            id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID, player_name TEXT NOT NULL,
            season TEXT, category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL,
            detail TEXT, created_at TIMESTAMPTZ DEFAULT NOW())
    """))
    await db.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS season_end TEXT"))
    # The office-bearer lookup behind the honours picker reads the club's award
    # renames. Another raw-SQL lifespan table (main.py), copied column for column.
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS org_award_definitions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            category TEXT NOT NULL, subcategory TEXT, achievement TEXT, display_name TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0, active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())
    """))

    async def ach(org, season, name, player, detail, sub=None, category="Club Award"):
        await db.execute(text(
            "INSERT INTO player_achievements (org_id, player_name, season, category, subcategory, achievement, detail) "
            "VALUES (:o, :p, :s, :c, :sub, :a, :d)"),
            {"o": org, "p": player, "s": season, "c": category, "sub": sub, "a": name, "d": detail})

    # Out of order on purpose: season order and cap order disagree.
    await ach(vrt.ORG, "Summer 2014/15", "A Grade Cap Number", "Sample Cc", "188")
    await ach(vrt.ORG, "Summer 2013/14", "A Grade Cap Number", "Sample Aa", "186")
    await ach(vrt.ORG, "Summer 2013/14", "a grade cap number ", "Sample Bb", "187")
    await ach(vrt.ORG, "Summer 2013/14", "Women's A Grade Cap Number", "Sample Ww", "5")
    await ach(vrt.ORG, "Summer 2013/14", "Best Batter", "Sample Bat", "436 runs at 39.64", sub="1st XI")
    await ach(vrt.ORG, "Summer 2013/14", "Captain", "Sample Cap", "12")
    # Another club with an award of the very same name: must never reach this club's TV.
    await ach(vrt.EMPTY_ORG, "Summer 2013/14", "A Grade Cap Number", "Other Club Player", "999")
    await db.commit()


async def play(db, entries):
    org = await db.get(Organisation, vrt.ORG)
    await db.execute(text("DELETE FROM club_room_slides WHERE organisation_id = :o"), {"o": vrt.ORG})
    for i, (title, cfg) in enumerate(entries):
        await db.execute(text(
            "INSERT INTO club_room_slides (id, organisation_id, slide_type, title, config, position, enabled) "
            "VALUES (gen_random_uuid(), :o, 'honours', :t, CAST(:c AS jsonb), :p, true)"),
            {"o": vrt.ORG, "t": title, "c": json.dumps(cfg), "p": i})
    await db.commit()
    try:
        payload = await cr.build_play_payload(db, org)
    except Exception as exc:  # noqa: BLE001 - the control must report, not crash
        await db.rollback()
        return [], f"{type(exc).__name__}: {exc}"
    return [s for s in payload.get("slides", []) if s.get("type") == "honours"], None


def pairs(slide):
    return [(e["name"], e["detail"]) for e in (slide or {}).get("entries", [])]


async def main() -> None:
    await vrt.build_schema()
    async with vrt.Session() as s:
        await vrt.seed(s)
        await seed(s)

    async with vrt.Session() as db:
        org = await db.get(Organisation, vrt.ORG)
        caps = {"kind": "awards", "category": "Club Award", "achievement": "A Grade Cap Number"}

        print("== the men's caps")
        slides, err = await play(db, [("Men's A Grade Caps", caps)])
        check("the playlist plays", err is None, str(err))
        check("one awards slide comes back", len(slides) == 1, str(len(slides)))
        slide = slides[0] if slides else {}
        check("it carries the slide's own title", slide.get("title") == "Men's A Grade Caps", str(slide.get("title")))
        check("only the men's caps, as 'Cap N', in cap order (the women's, Best Batter and Captain are not on it)",
              pairs(slide) == [("Sample Aa", "Cap 186"), ("Sample Bb", "Cap 187"), ("Sample Cc", "Cap 188")], str(pairs(slide)))
        check("another club's award of the same name is not shown", not any("Other Club" in n for n, _ in pairs(slide)), str(pairs(slide)))

        print("== the ladies' caps, and the whole category (so the men's slide could have shown more)")
        slides, err = await play(db, [("Ladies' A Grade Caps", {**caps, "achievement": "Women's A Grade Cap Number"}),
                                      ("Every club award", {"kind": "awards", "category": "Club Award"})])
        by = {s.get("title"): s for s in slides}
        check("the ladies' list is a slide of its own", pairs(by.get("Ladies' A Grade Caps")) == [("Sample Ww", "Cap 5")], str(pairs(by.get("Ladies' A Grade Caps"))))
        every = pairs(by.get("Every club award"))
        check("with no award name the whole category is listed (6 awards, none from the other club)",
              len(every) == 6 and not any("Other Club" in n for n, _ in every), str(every))
        check("and the other awards keep their detail as typed",
              ("Sample Bat", "436 runs at 39.64") in every and ("Sample Cap", "12") in every, str(every))

        print("== a slide with no title of its own")
        slides, _ = await play(db, [(None, caps), (None, {"kind": "awards", "category": "Club Award"})])
        check("is titled by the award name, else by the category",
              [s.get("title") for s in slides] == ["A Grade Cap Number", "Club Award"], str([s.get("title") for s in slides]))

        print("== slides that cannot list anything are skipped, not fatal")
        slides, err = await play(db, [("No category", {"kind": "awards"}),
                                      ("Typo", {**caps, "achievement": "A Grade Cap Numbr"}),
                                      ("Good", caps)])
        check("the playlist still plays", err is None, str(err))
        check("only the slide that has something to list remains", [s.get("title") for s in slides] == ["Good"], str([s.get("title") for s in slides]))

        print("== the other honour kinds are unaffected")
        slides, err = await play(db, [("Premierships", {"kind": "premierships"}), ("Boards", {"kind": "boards"}), ("Caps", caps)])
        check("premierships and boards still play beside an awards slide", err is None and [s.get("title") for s in slides].count("Caps") == 1, f"{err} {[s.get('title') for s in slides]}")

        print("== the editor's pickers")
        src = getattr(cr, "list_honour_sources", None)
        got, err = None, None
        try:
            got = await src(current_user=None, club=org, db=db)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
        cats = {(c["category"], c["subcategory"]): c["count"] for c in (got or {}).get("award_categories", [])}
        check("the awards source lists this club's categories with counts, and no other club's",
              cats.get(("Club Award", None)) == 5 and cats.get(("Club Award", "1st XI")) == 1 and len(cats) == 2, f"{cats} {err}")
        names_fn = getattr(cr, "list_award_names", None)
        names, err = None, None
        try:
            names = await names_fn("Club Award", None, current_user=None, club=org, db=db)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
        d = {n["achievement"].lower(): n["count"] for n in (names or [])}
        check("the award names are listed with counts: spelling variants of one name together, the other club's row not counted",
              d.get("a grade cap number") == 3 and d.get("women's a grade cap number") == 1 and d.get("best batter") == 1
              and sum(d.values()) == 6, f"{names} {err}")

        class _E:
            def __init__(self, c): self.slide_type, self.config = "honours", c
        describe = getattr(cr, "_entry_summary", lambda e: None)
        check("a row says what it shows", describe(_E(caps)) == "Honour Boards · A Grade Cap Number"
              and describe(_E({"kind": "awards", "category": "Club Award"})) == "Honour Boards · Club Award"
              and describe(_E({"kind": "awards"})) == "Honour Boards · awards from your records",
              f"{describe(_E(caps))}")

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
