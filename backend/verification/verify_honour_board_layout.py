"""Verification for a club's own Honour Board order (migration 324), against a
real Postgres.

Runs the SHIPPED ``services/honours.office_bearer_boards``, ``services/honour_layout``
and ``services/honour_layout_ddl`` and the shipped route bodies: the public
``/honours/{org}/office-bearers`` read and the club-admin ``/honour-board-layout``
GET and PUT.

The club under test is built from the Shoalwater Bay request: Life Members first,
Allan Godfrey first among them although he was recorded in 1985 and another
life member in 1978, two life members awarded in the one year, the Executive
Committee read President, Treasurer, Secretary, and the General Committee read
Director of Cricket before Club Manager. A second club with no layout proves the
standard order is untouched.

Every "X is not reordered" check is paired with a check that a reordered thing IS
reordered, so a check cannot pass by changing nothing (rule 21).

CONTROL MODE. Run against the commit BEFORE this change ``office_bearer_boards``
has no ``layout`` argument and the layout service and DDL do not exist; they are
found through find_spec / inspect and new keys read through presence-safe
accessors, so the control reports the missing behaviour as failed checks and
does not crash.

Run:  DATABASE_URL=postgresql+asyncpg://root@/honours_test?host=/var/run/postgresql \
      python verification/verify_honour_board_layout.py
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
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, ClubMembership, Organisation, Player, User
from app.routers import club_admin as ca
from app.routers import honours as honours_router
from app.services import honours

HAVE_LAYOUT_SVC = importlib.util.find_spec("app.services.honour_layout") is not None
HAVE_ARG = "layout" in inspect.signature(honours.office_bearer_boards).parameters
HAVE_ADMIN = hasattr(ca, "put_honour_board_layout")
if HAVE_LAYOUT_SVC:
    from app.services import honour_layout as hl
else:
    hl = None
if importlib.util.find_spec("app.services.honour_layout_ddl"):
    from app.services.honour_layout_ddl import STATEMENTS as DDL
else:
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
GODFREY = uuid.uuid4()
EXTRA = uuid.uuid4()


async def http_status(coro):
    try:
        await coro
    except HTTPException as e:
        return e.status_code
    return None


# (category, subcategory, achievement, player id or None, name, season label)
ROWS = [
    # Life Members. Godfrey recorded 1985; B was awarded earlier, in 1978.
    ("Life Membership", "Club", "Life Membership", GODFREY, "Allan Godfrey", "1985/86"),
    ("Life Membership", "Club", "Life Membership", None, "Beryl Brown", "1978/79"),
    ("Life Membership", "Club", "Life Membership", None, "Colin Cole", "1991/92"),
    ("Life Membership", "Club", "Life Membership", None, "Dana Dunn", "2003/04"),
    ("Life Membership", "Club", "Life Membership", None, "Eddie East", "2003/04"),
    ("Life Membership", "Club", "Life Membership", None, "Fay Ford", "2014/15"),
    ("Life Membership", "Club", "Life Membership", None, "Gus Gray", "2022/23"),
    # Executive Committee
    ("Office Bearer", "Executive Committee", "President", None, "Pat Price", "2010/11"),
    ("Office Bearer", "Executive Committee", "President", None, "Quinn Quill", "2012/13"),
    ("Office Bearer", "Executive Committee", "President", None, "Rob Reed", "2018/19"),
    ("Office Bearer", "Executive Committee", "Secretary", None, "Sam Shaw", "2015/16"),
    ("Office Bearer", "Executive Committee", "Treasurer", None, "Tess Tate", "2016/17"),
    # General Committee
    ("Office Bearer", "General Committee", "Club Manager", None, "Una Underhill", "2019/20"),
    ("Office Bearer", "General Committee", "Director of Cricket", None, "Vic Vance", "2020/21"),
    # Captains (never placed by the layout under test)
    ("Office Bearer", "Captains", "1st XI Captain", None, "Wes West", "2021/22"),
]
# A person with a role and no season at all.
NO_YEAR = ("Life Membership", "Club", "Life Membership", None, "Hana Hill", None)

OTHER_ROWS = [
    ("Office Bearer", "Executive Committee", "Secretary", None, "Ola Other", "2011/12"),
    ("Office Bearer", "Executive Committee", "President", None, "Ned Other", "2012/13"),
    ("Life Membership", "Club", "Life Membership", None, "Ivy Other", "1999/00"),
    ("Life Membership", "Club", "Life Membership", None, "Jed Other", "2005/06"),
]


def names(board: dict) -> list[str]:
    return [h["name"] for h in board["holders"]]


def find(groups: list[dict], group: str, role: str) -> dict:
    for g in groups:
        if g["group"] == group:
            for b in g["boards"]:
                if b["role"] == role:
                    return b
    return {"holders": [], "role": role}


def group_names(groups: list[dict]) -> list[str]:
    return [g["group"] for g in groups]


def role_names(groups: list[dict], group: str) -> list[str]:
    for g in groups:
        if g["group"] == group:
            return [b["role"] for b in g["boards"]]
    return []


def key_of(board: dict, name: str):
    for h in board["holders"]:
        if h["name"] == name:
            return h.get("key")
    return None


async def boards(db, org, layout=None):
    if HAVE_ARG:
        return (await honours.office_bearer_boards(db, org, include_life_members=True, layout=layout))["groups"]
    return (await honours.office_bearer_boards(db, org, include_life_members=True))["groups"]


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # The lifespan's own player_achievements DDL, column for column (rule 24).
        await conn.execute(text("""
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
            )"""))
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

    print("== migration DDL")
    if DDL:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE organisations DROP COLUMN honour_board_layout"))
            for stmt in DDL:
                await conn.execute(text(stmt))
            for stmt in DDL:
                await conn.execute(text(stmt))
            col = (await conn.execute(text(
                "SELECT count(*) FROM information_schema.columns WHERE table_name='organisations' "
                "AND column_name='honour_board_layout'"))).scalar()
            check("the column is added, and the DDL list is idempotent", col == 1)
    else:
        check("the DDL module exists", False)

    async with engine.begin() as conn:
        for oid, name, slug in ((OURS, "Shoalwater Bay CC", "shoalwater"), (OTHER, "Other CC", "otherclub")):
            await conn.execute(text(
                "INSERT INTO organisations (id, name, slug, is_active) VALUES (:i,:n,:s,true)"),
                {"i": oid, "n": name, "s": slug})
        await conn.execute(text(
            "INSERT INTO players (id, name, organisation_id) VALUES (:i, 'Allan Godfrey', :o)"),
            {"i": GODFREY, "o": OURS})
        for org, rows in ((OURS, ROWS + [NO_YEAR]), (OTHER, OTHER_ROWS)):
            for cat, sub, ach, pid, name, season in rows:
                await conn.execute(text(
                    "INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory, achievement) "
                    "VALUES (:o, :p, :n, :s, :c, :sub, :a)"),
                    {"o": org, "p": pid, "n": name, "s": season, "c": cat, "sub": sub, "a": ach})

    print("== the standard order (no layout) is exactly what it was")
    async with Session() as db:
        std = await boards(db, OURS)
        check("groups are Executive, General, Captains, then Life Members last",
              group_names(std) == ["Executive Committee", "General Committee", "Captains", "Life Members"], str(group_names(std)))
        check("Executive roles are President, Secretary, Treasurer (standard seat order)",
              role_names(std, "Executive Committee") == ["President", "Secretary", "Treasurer"], str(role_names(std, "Executive Committee")))
        check("General roles fall back to alphabetical", role_names(std, "General Committee") == ["Club Manager", "Director of Cricket"])
        check("presidents are most recent first",
              names(find(std, "Executive Committee", "President")) == ["Rob Reed", "Quinn Quill", "Pat Price"])
        life = find(std, "Life Members", "Life Membership")
        check("life members are most recent first, no-year person last",
              names(life) == ["Gus Gray", "Fay Ford", "Dana Dunn", "Eddie East", "Colin Cole", "Allan Godfrey", "Beryl Brown", "Hana Hill"],
              str(names(life)))
        check("every holder carries a key (a linked player is id:, an unlinked one name:)",
              key_of(life, "Allan Godfrey") == f"id:{GODFREY}" and key_of(life, "Gus Gray") == "name:gus gray")
        other_std = await boards(db, OTHER)
        check("the other club is also in the standard order",
              group_names(other_std) == ["Executive Committee", "Life Members"]
              and role_names(other_std, "Executive Committee") == ["President", "Secretary"])
        check("the football-style call (no flag, no layout) has no Life Members group and the same order",
              group_names((await honours.office_bearer_boards(db, OURS))["groups"]) == ["Executive Committee", "General Committee", "Captains"])
        godfrey_key = f"id:{GODFREY}"
        east_key, dunn_key = key_of(life, "Eddie East"), key_of(life, "Dana Dunn")

    print("== service: clean_layout")
    if HAVE_LAYOUT_SVC:
        check("not a dict is no layout", hl.clean_layout(None) is None and hl.clean_layout("x") is None and hl.clean_layout([1]) is None)
        check("empty things clean to None (standard order)", hl.clean_layout({"groups": [], "roles": {}, "holders": {}}) is None)
        got = hl.clean_layout({"groups": ["  Life   Members ", "life members", "", 5, None, "Executive Committee"]})
        check("names are tidied, duplicates folded (case-insensitive), junk dropped",
              got == {"groups": ["Life Members", "Executive Committee"]}, str(got))
        got = hl.clean_layout({"holders": {"Life Members": {"Life Membership": {"sort": "sideways", "order": []}}}})
        check("an unknown sort word falls back to newest, and nothing else is left so nothing is stored", got is None, str(got))
        got = hl.clean_layout({"holders": {"Life Members": {"Life Membership": {"sort": "oldest", "order": ["id:1", "id:1", "name:a b"]}}}})
        check("a person key is kept once, in order",
              got == {"holders": {"Life Members": {"Life Membership": {"sort": "oldest", "order": ["id:1", "name:a b"]}}}}, str(got))
        got = hl.clean_layout({"holders": {"Life Members": {"Life Membership": {"sort": "newest", "order": ["id:1"]}}}})
        check("newest with a tie-break order is kept (it only breaks ties)", got is not None and got["holders"]["Life Members"]["Life Membership"]["order"] == ["id:1"])
        once = hl.clean_layout({"groups": ["B", "A"], "roles": {"B": ["x", "y"]},
                                "holders": {"B": {"x": {"sort": "manual", "order": ["name:q"]}}}})
        check("cleaning is idempotent", hl.clean_layout(once) == once)
        check("a huge list is capped", len(hl.clean_layout({"groups": [f"g{i}" for i in range(5000)]})["groups"]) == hl.MAX_NAMES)
        check("control characters are flattened", hl.clean_layout({"groups": ["A\nB\x00C"]}) == {"groups": ["A B C"]})
    else:
        check("the honour_layout service exists", False)

    print("== service: the layout applied (Shoalwater's request)")
    layout = {
        "groups": ["Life Members", "Executive Committee", "General Committee"],
        "roles": {"Executive Committee": ["President", "Treasurer", "Secretary"],
                  "General Committee": ["Director of Cricket", "Club Manager"]},
        "holders": {"Life Members": {"Life Membership": {"sort": "manual", "order": [godfrey_key]}}},
    }
    cleaned = hl.clean_layout(layout) if HAVE_LAYOUT_SVC else None
    async with Session() as db:
        lay = await boards(db, OURS, cleaned)
        check("Life Members is the first group, then Executive, then General, then the unplaced Captains",
              group_names(lay) == ["Life Members", "Executive Committee", "General Committee", "Captains"], str(group_names(lay)))
        check("Executive reads President, Treasurer, Secretary",
              role_names(lay, "Executive Committee") == ["President", "Treasurer", "Secretary"], str(role_names(lay, "Executive Committee")))
        check("General reads Director of Cricket before Club Manager",
              role_names(lay, "General Committee") == ["Director of Cricket", "Club Manager"], str(role_names(lay, "General Committee")))
        life = find(lay, "Life Members", "Life Membership")
        check("manual: Allan Godfrey is the first name, everyone the club did not place follows newest first",
              names(life)[:1] == ["Allan Godfrey"] and names(life)[1:] == ["Gus Gray", "Fay Ford", "Dana Dunn", "Eddie East", "Colin Cole", "Beryl Brown", "Hana Hill"],
              str(names(life)))
        check("a board reports its sort mode", life.get("sort") == "manual" and find(lay, "Executive Committee", "President").get("sort") == "newest")
        check("presidents are untouched by a layout that never mentions them (still newest first)",
              names(find(lay, "Executive Committee", "President")) == ["Rob Reed", "Quinn Quill", "Pat Price"])

        # Oldest first, with the two 2003 awards placed by the club.
        oldest = {"holders": {"Life Members": {"Life Membership": {"sort": "oldest", "order": [east_key, dunn_key]}}}}
        life = find(await boards(db, OURS, hl.clean_layout(oldest) if HAVE_LAYOUT_SVC else None), "Life Members", "Life Membership")
        check("oldest first: 1978 first, Godfrey 1985 second, the no-year person last",
              names(life) == ["Beryl Brown", "Allan Godfrey", "Colin Cole", "Eddie East", "Dana Dunn", "Fay Ford", "Gus Gray", "Hana Hill"],
              str(names(life)))
        check("oldest first: the club's own order settles the two 2003 awards (East before Dunn)",
              names(life).index("Eddie East") < names(life).index("Dana Dunn"))
        flipped = {"holders": {"Life Members": {"Life Membership": {"sort": "oldest", "order": [dunn_key, east_key]}}}}
        life = find(await boards(db, OURS, hl.clean_layout(flipped) if HAVE_LAYOUT_SVC else None), "Life Members", "Life Membership")
        check("flipping the order flips only that pair",
              names(life).index("Dana Dunn") < names(life).index("Eddie East") and names(life)[0] == "Beryl Brown")
        # Newest first with a tie-break.
        newest = {"holders": {"Life Members": {"Life Membership": {"sort": "newest", "order": [east_key]}}}}
        life = find(await boards(db, OURS, hl.clean_layout(newest) if HAVE_LAYOUT_SVC else None), "Life Members", "Life Membership")
        check("newest first: the club's order settles the 2003 tie (East before Dunn) and the rest is standard",
              names(life) == ["Gus Gray", "Fay Ford", "Eddie East", "Dana Dunn", "Colin Cole", "Allan Godfrey", "Beryl Brown", "Hana Hill"], str(names(life)))

        # Things the layout names that do not exist, and a role recorded later.
        stale = {"groups": ["Nonexistent Group", "Executive Committee"],
                 "roles": {"Executive Committee": ["Vice President", "Treasurer"]},
                 "holders": {"Life Members": {"Life Membership": {"sort": "manual", "order": ["id:ghost", godfrey_key]}}}}
        lay = await boards(db, OURS, hl.clean_layout(stale) if HAVE_LAYOUT_SVC else None)
        check("a group that is not there is ignored and the placed one still leads",
              group_names(lay)[0] == "Executive Committee" and "Nonexistent Group" not in group_names(lay), str(group_names(lay)))
        check("a role not there is ignored; Treasurer leads, the rest keep standard order after it",
              role_names(lay, "Executive Committee") == ["Treasurer", "President", "Secretary"], str(role_names(lay, "Executive Committee")))
        life = find(lay, "Life Members", "Life Membership")
        check("a person key that is not there is ignored; Godfrey (placed) still leads", names(life)[0] == "Allan Godfrey")

        # Matching is case-insensitive.
        shout = {"groups": ["LIFE MEMBERS"], "roles": {"executive committee": ["TREASURER"]}}
        lay = await boards(db, OURS, hl.clean_layout(shout) if HAVE_LAYOUT_SVC else None)
        check("group and role names match without regard to case",
              group_names(lay)[0] == "Life Members" and role_names(lay, "Executive Committee")[0] == "Treasurer")

        # A layout is per club.
        other = await boards(db, OTHER, cleaned)
        check("a layout names groups by name only; the other club has no Captains/General so just reorders what it has",
              group_names(other) == ["Life Members", "Executive Committee"], str(group_names(other)))

    print("== admin routes")
    async with Session() as db:
        club = (await db.execute(select(Organisation).where(Organisation.id == OURS))).scalar_one()
        other_club = (await db.execute(select(Organisation).where(Organisation.id == OTHER))).scalar_one()
        if HAVE_ADMIN:
            view = await ca.get_honour_board_layout(current_user=None, club=club, db=db)
            check("before any save: not customised and the standard order is shown",
                  view["customised"] is False and view["layout"] == {} and group_names(view["groups"])[0] == "Executive Committee")
            body = ca.HonourBoardLayoutPut(
                groups=layout["groups"], roles=layout["roles"],
                holders={"Life Members": {"Life Membership": ca.HonourHolderLayout(sort="manual", order=[godfrey_key])}})
            view = await ca.put_honour_board_layout(data=body, current_user=None, club=club, db=db)
            check("a save is customised and comes back in the club's order",
                  view["customised"] is True and group_names(view["groups"])[:3] == ["Life Members", "Executive Committee", "General Committee"])
            check("the saved layout is returned as stored", view["layout"].get("groups") == layout["groups"])
            life = find(view["groups"], "Life Members", "Life Membership")
            check("the admin view lists each person with a key and a year",
                  names(life)[0] == "Allan Godfrey" and all("key" in h and "from_year" in h for h in life["holders"]))

            pub = await honours_router.get_office_bearers(OURS, db)
            check("the public page reads the saved layout (Life Members first, Godfrey first)",
                  group_names(pub["groups"])[0] == "Life Members"
                  and names(find(pub["groups"], "Life Members", "Life Membership"))[0] == "Allan Godfrey")
            pub_other = await honours_router.get_office_bearers(OTHER, db)
            check("the public page of a club with no layout is the standard order",
                  group_names(pub_other["groups"]) == ["Executive Committee", "Life Members"]
                  and role_names(pub_other["groups"], "Executive Committee") == ["President", "Secretary"])
            check("saving one club's layout wrote nothing to the other",
                  (await db.execute(text("SELECT honour_board_layout IS NULL FROM organisations WHERE id=:i"), {"i": OTHER})).scalar() is True)

            # A person recorded after the layout was saved is not lost.
            await db.execute(text(
                "INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory, achievement) "
                "VALUES (:o, NULL, 'Zed Zane', '2024/25', 'Life Membership', 'Club', 'Life Membership')"), {"o": OURS})
            await db.execute(text(
                "INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory, achievement) "
                "VALUES (:o, NULL, 'Kit Kane', '2024/25', 'Office Bearer', 'Social Committee', 'Social Convenor')"), {"o": OURS})
            await db.commit()
            pub = await honours_router.get_office_bearers(OURS, db)
            life = find(pub["groups"], "Life Members", "Life Membership")
            check("a life member recorded after the save appears (not hidden by the layout)",
                  "Zed Zane" in names(life) and names(life)[0] == "Allan Godfrey")
            check("a group recorded after the save appears, after the placed ones",
                  "Social Committee" in group_names(pub["groups"])
                  and group_names(pub["groups"]).index("Social Committee") > group_names(pub["groups"]).index("General Committee"))

            # PUT with nothing resets.
            view = await ca.put_honour_board_layout(data=ca.HonourBoardLayoutPut(), current_user=None, club=club, db=db)
            check("saving nothing resets to the standard order (customised false)",
                  view["customised"] is False and group_names(view["groups"])[0] == "Executive Committee")
            check("a reset stores NULL, not an empty object",
                  (await db.execute(text("SELECT honour_board_layout IS NULL FROM organisations WHERE id=:i"), {"i": OURS})).scalar() is True)
            # a bad sort word is dropped, not stored
            view = await ca.put_honour_board_layout(data=ca.HonourBoardLayoutPut(
                holders={"Life Members": {"Life Membership": ca.HonourHolderLayout(sort="sideways", order=[])}}),
                current_user=None, club=club, db=db)
            check("an unknown sort word stores nothing", view["customised"] is False)

            dep_put = inspect.signature(ca.put_honour_board_layout).parameters["current_user"].default.dependency
            dep_get = inspect.signature(ca.get_honour_board_layout).parameters["current_user"].default.dependency
            uid_no, uid_yes = uuid.uuid4(), uuid.uuid4()
            db.add(User(id=uid_no, username="nocap", email="a@b.co", password_hash="x"))
            db.add(User(id=uid_yes, username="hascap", email="c@d.co", password_hash="x"))
            await db.flush()
            db.add(ClubMembership(club_id=OURS, user_id=uid_no, role="club_member", capabilities=["manage_sponsors"]))
            db.add(ClubMembership(club_id=OURS, user_id=uid_yes, role="club_member", capabilities=["manage_awards"]))
            await db.commit()
            check("saving the order without manage_awards is refused", await http_status(dep_put(current_user=await db.get(User, uid_no), db=db)) == 403)
            check("reading the order without manage_awards is refused", await http_status(dep_get(current_user=await db.get(User, uid_no), db=db)) == 403)
            yes = await db.get(User, uid_yes)
            check("saving the order with manage_awards passes", (await dep_put(current_user=yes, db=db)) is yes)
        else:
            check("admin honour-board-layout routes exist", False)
            check("the public route reads a layout", "layout" in inspect.getsource(honours_router))

    print()
    print(f"{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:")
        for f in FAILURES:
            print("  -", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
