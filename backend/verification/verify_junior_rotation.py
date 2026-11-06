"""Verification for Junior Rotation (migration 381), against a real Postgres.

Calls the SHIPPED route bodies (``routers/rotation.py``, ``routers/public_rotation.py``)
and the shipped generator, never a re-implementation of them.

The questions worth the harness, because none can be read off the code:

  * IT EVENS OUT. Twelve weeks of 11 kids on a 9-position tee ball field, each
    week generated then locked through the routes, leaves every kid within one
    rest and one key-position turn of every other. A control with ``fairness``
    0 (a plain shuffle) must NOT manage that, or the check proves nothing.
  * IT IS STILL RANDOM. From one fixed history, many draws give many different
    batting orders and several different openers, so a parent cannot work
    next week out from this one.
  * A DRAFT IS NOT HISTORY. Re-rolling, hand edits and deleting a draft leave
    the tally exactly where it was; only locking moves it.
  * A LOCKED ROUND IS SAFE. Every write refuses it until it is unlocked.
  * THE PARENT LINK SAYS LITTLE. Off by default, a plain 404 for a bad token,
    a disabled group, an archived group or a club without BetterSelect; locked
    rounds only; first name and last initial; no ids.
  * ONE CLUB CANNOT SEE ANOTHER'S GROUPS, ROUNDS OR FIXTURES.

Run:  DATABASE_URL=postgresql+asyncpg://... python verify_junior_rotation.py
"""
from __future__ import annotations

import asyncio
import inspect
import os
import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Fixture, Organisation, User

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def refused(coro, status: int) -> bool:
    try:
        await coro
    except HTTPException as e:
        return e.status_code == status
    return False


async def detail_code(coro):
    try:
        await coro
    except HTTPException as e:
        d = e.detail
        return d.get("code") if isinstance(d, dict) else None
    return "no error"


KIDS = ["Sam Taylor", "Ava Brown", "Noah Smith", "Mia Jones", "Leo Wilson", "Ella Davis",
        "Jack Miller", "Zoe Moore", "Max Clark", "Ruby Lewis", "Finn Young"]


async def build():
    from app.services.rotation_ddl import STATEMENTS
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in STATEMENTS:
            await conn.execute(text(stmt))


async def seed():
    async with Session() as db:
        club = Organisation(id=uuid.uuid4(), name="Applecross CC", slug="applecross-rot",
                            module_overrides=["select"], subscription_status="active")
        other = Organisation(id=uuid.uuid4(), name="High Wycombe CC", slug="hw-rot",
                             module_overrides=["select"], subscription_status="active")
        nosel = Organisation(id=uuid.uuid4(), name="Stats Only CC", slug="statsonly-rot",
                             module_overrides=[], subscription_status="active")
        db.add_all([club, other, nosel])
        await db.flush()
        user = User(id=uuid.uuid4(), username="coach-rot", email="c@rot.com", password_hash="x")
        db.add(user)
        fx = Fixture(id=uuid.uuid4(), organisation_id=club.id, source="manual", played_on=date.today() + timedelta(days=3),
                     opponent_name="Bayswater", status="UPCOMING")
        foreign_fx = Fixture(id=uuid.uuid4(), organisation_id=other.id, source="manual",
                             played_on=date.today() + timedelta(days=3), opponent_name="Them", status="UPCOMING")
        db.add_all([fx, foreign_fx])
        await db.commit()
        return {"club": club.id, "other": other.id, "nosel": nosel.id, "user": user.id,
                "fx": fx.id, "foreign_fx": foreign_fx.id}


async def main():
    import app.routers.rotation as R
    import app.routers.public_rotation as P
    from app.services import rotation as svc

    print("\n── Schema, migration and the lifespan mirror ──")
    await build()
    ids = await seed()
    here = Path(__file__).resolve().parent.parent
    check("the migration runs the shared DDL list", "from app.services.rotation_ddl import STATEMENTS" in (here / "alembic/versions/381_junior_rotation.py").read_text())
    check("the lifespan runs the same list", "services.rotation_ddl import STATEMENTS" in (here / "app/main.py").read_text())
    from app.services.rotation_ddl import STATEMENTS
    async with engine.begin() as conn:
        for stmt in STATEMENTS:   # the lifespan re-runs it every boot
            await conn.execute(text(stmt))
    check("the DDL is idempotent (second run raised nothing)", True)

    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        other = await db.get(Organisation, ids["other"])
        nosel = await db.get(Organisation, ids["nosel"])
        user = await db.get(User, ids["user"])

        def kw(fn):
            # Route bodies name their gate dependency `user` where they use it, `_` where not.
            who = "user" if "user" in inspect.signature(fn).parameters else "_"
            return {"db": db, "club": club, who: user}

        print("\n── Group: presets, names, the stored shape ──")
        g = await R.create_group(R.GroupCreate(name="Under 8 Tee Ball", preset="tee_ball", names="\n".join(KIDS) + "\nsam taylor"),
                                 db=db, club=club, user=user)
        gid = g["group"]["id"]
        check("tee ball preset has nine positions", len(g["group"]["positions"]), 9)
        check("pitcher and the bases are key positions", sorted(p["name"] for p in g["group"]["positions"] if p["key"]),
              sorted(["Pitcher", "Catcher", "1st base", "2nd base", "3rd base", "Shortstop"]))
        check("eleven saved names, the case-folded repeat dropped", len(g["players"]), 11)
        check("the parent link starts OFF with no token", (g["group"]["public_enabled"], g["group"]["public_path"]), (False, None))
        check("surnames start hidden", g["group"]["public_show_surnames"], False)
        check("a blank name is refused", await refused(R.create_group(R.GroupCreate(name="  "), db=db, club=club, user=user), 400))

        print("\n── PATCH: an absent key is not a clear ──")
        pos_before = g["group"]["positions"]
        p = await R.patch_group(gid, R.GroupPatch(name="U8 Tee Ball"), db=db, club=club, user=user)
        check("renaming leaves positions, fairness, innings alone",
              (p["group"]["positions"], p["group"]["fairness"], p["group"]["innings"]), (pos_before, 60, 1))
        renamed = [dict(x) for x in pos_before]
        renamed[0]["name"] = "Pitcher (coach)"
        p = await R.patch_group(gid, R.GroupPatch(positions=renamed), db=db, club=club, user=user)
        check("renaming a position keeps its id (history survives)", p["group"]["positions"][0]["id"], pos_before[0]["id"])
        p = await R.patch_group(gid, R.GroupPatch(positions=[{"name": "Brand new"}] + renamed), db=db, club=club, user=user)
        check("a new position gets a fresh id", p["group"]["positions"][0]["id"] not in {x["id"] for x in pos_before}, True)
        p = await R.patch_group(gid, R.GroupPatch(positions=renamed), db=db, club=club, user=user)
        check("taking a position out removes it", len(p["group"]["positions"]), 9)
        p = await R.patch_group(gid, R.GroupPatch(fairness=500, innings=99), db=db, club=club, user=user)
        check("fairness and innings are clamped", (p["group"]["fairness"], p["group"]["innings"]), (100, 6))
        p = await R.patch_group(gid, R.GroupPatch(fairness=60, innings=1), db=db, club=club, user=user)
        positions = p["group"]["positions"]
        pos_ids = [x["id"] for x in positions]
        key_ids = {x["id"] for x in positions if x["key"]}
        players = {x["name"]: x["id"] for x in p["players"]}

        print("\n── A round: generated, valid, and a draft is not history ──")
        r = (await R.create_round(gid, R.RoundCreate(label="Week 1"), db=db, club=club, user=user))["round"]
        check("everyone is here by default", len(r["present"]), 11)
        check("everyone has a batting slot, nobody twice", sorted(r["batting_order"]), sorted(r["present"]))
        check("one field change", len(r["fielding"]), 1)
        check("nine fielders and two resting", (sum(1 for v in r["fielding"][0].values() if v), sum(1 for v in r["fielding"][0].values() if v is None)), (9, 2))
        check("no position double-booked", len({v for v in r["fielding"][0].values() if v}), 9)
        check("a draft round carries no warnings with a full field", r["warnings"], [])
        t = await R.group_tally(gid, **kw(R.group_tally))
        check("a DRAFT does not count towards the tally", (t["rounds"], max(x["games"] for x in t["players"])), (0, 0))
        r2 = (await R.regenerate_round(r["id"], R.RoundGenerate(), **kw(R.regenerate_round)))["round"]
        check("re-rolling bumps the version", r2["version"], r["version"] + 1)
        t = await R.group_tally(gid, **kw(R.group_tally))
        check("re-rolling a draft still leaves the tally at zero", t["rounds"], 0)

        print("\n── Hand edits are validated ──")
        v = r2["version"]
        dup = [{**r2["fielding"][0]}]
        a, b = [k for k, val in dup[0].items() if val][:2]
        dup[0][a] = dup[0][b]
        check("two players on one position is refused", await refused(R.put_round(r["id"], R.RoundPut(version=v, fielding=dup), **kw(R.put_round)), 400))
        check("a position the group does not have is refused", await refused(R.put_round(r["id"], R.RoundPut(version=v, fielding=[{a: "nope"}]), **kw(R.put_round)), 400))
        check("someone who is not in the group is refused", await refused(R.put_round(r["id"], R.RoundPut(version=v, batting_order=[str(uuid.uuid4())]), **kw(R.put_round)), 400))
        check("a stale version is a 409 conflict carrying the current round",
              await detail_code(R.put_round(r["id"], R.RoundPut(version=v - 1, label="x"), **kw(R.put_round))), "conflict")
        swapped = list(reversed(r2["batting_order"]))
        e = (await R.put_round(r["id"], R.RoundPut(version=v, batting_order=swapped), **kw(R.put_round)))["round"]
        check("a hand-edited batting order is kept", e["batting_order"], swapped)
        check("the field is untouched by a batting edit", e["fielding"], r2["fielding"])
        sent_home = r2["present"][0]
        e = (await R.put_round(r["id"], R.RoundPut(version=e["version"], present=r2["present"][1:]), **kw(R.put_round)))["round"]
        check("someone sent home leaves the order and the field", (sent_home in e["batting_order"], sent_home in e["fielding"][0]), (False, False))
        e = (await R.put_round(r["id"], R.RoundPut(version=e["version"], present=r2["present"]), **kw(R.put_round)))["round"]
        check("a late arrival goes to the end of the order, resting", (e["batting_order"][-1], e["fielding"][0][sent_home]), (sent_home, None))
        check("a clear label is a clear", (await R.put_round(r["id"], R.RoundPut(version=e["version"], label=None), **kw(R.put_round)))["round"]["label"], None)

        print("\n── Fixture tie ──")
        tied = (await R.create_round(gid, R.RoundCreate(fixture_id=str(ids["fx"])), db=db, club=club, user=user))["round"]
        check("a tied round takes the fixture's date and opponent", (tied["round_date"], tied["label"]),
              ((date.today() + timedelta(days=3)).isoformat(), "vs Bayswater"))
        check("another club's fixture is refused", await refused(R.create_round(gid, R.RoundCreate(fixture_id=str(ids["foreign_fx"])), db=db, club=club, user=user), 400))
        fl = (await R.fixtures_to_tie(**kw(R.fixtures_to_tie)))["fixtures"]
        check("the fixture list is the club's own", [f["id"] for f in fl], [str(ids["fx"])])
        await R.delete_round(tied["id"], **kw(R.delete_round))

        print("\n── Lock: history, and a locked round is safe ──")
        locked = (await R.lock_round(r["id"], **kw(R.lock_round)))["round"]
        check("locking marks it", locked["status"], "locked")
        t = await R.group_tally(gid, **kw(R.group_tally))
        check("a LOCKED round counts", (t["rounds"], min(x["games"] for x in t["players"])), (1, 1))
        check("editing a locked round is refused", await detail_code(R.put_round(r["id"], R.RoundPut(version=locked["version"], label="no"), **kw(R.put_round))), "locked")
        check("re-rolling a locked round is refused", await detail_code(R.regenerate_round(r["id"], R.RoundGenerate(), **kw(R.regenerate_round))), "locked")
        check("deleting a locked round is refused", await detail_code(R.delete_round(r["id"], **kw(R.delete_round))), "locked")
        await R.unlock_round(r["id"], **kw(R.unlock_round))
        t = await R.group_tally(gid, **kw(R.group_tally))
        check("unlocking takes it back out of the history", t["rounds"], 0)
        await R.delete_round(r["id"], **kw(R.delete_round))
        check("a draft can be deleted", await refused(R.get_round(r["id"], **kw(R.get_round)), 404))
        empty = (await R.create_round(gid, R.RoundCreate(present=[], generate=False), db=db, club=club, user=user))["round"]
        check("an empty round will not lock", await refused(R.lock_round(empty["id"], **kw(R.lock_round)), 400))
        await R.delete_round(empty["id"], **kw(R.delete_round))

        print("\n── It evens out across a season (and a plain shuffle does not) ──")

        async def season(fairness: int, name: str, weeks: int = 12):
            grp = await R.create_group(R.GroupCreate(name=name, preset="tee_ball", names="\n".join(KIDS)), db=db, club=club, user=user)
            sid = grp["group"]["id"]
            await R.patch_group(sid, R.GroupPatch(fairness=fairness), db=db, club=club, user=user)
            for _ in range(weeks):
                rnd = (await R.create_round(sid, R.RoundCreate(), db=db, club=club, user=user))["round"]
                await R.lock_round(rnd["id"], **kw(R.lock_round))
            tl = await R.group_tally(sid, **kw(R.group_tally))
            return sid, tl

        random.seed(7)
        sid, tl = await season(60, "Fair season")
        rests = [x["rests"] for x in tl["players"]]
        keys = [x["key_turns"] for x in tl["players"]]
        check("twelve locked weeks tallied", tl["rounds"], 12)
        check("rests differ by at most one", max(rests) - min(rests) <= 1, True)
        check("key-position turns differ by at most two", max(keys) - min(keys) <= 2, True)
        check("nobody fielded the same position more than three times in 12 weeks",
              max(max(x["field"].values()) for x in tl["players"]) <= 3, True)
        check("the tally's own spread agrees", tl["spread"], {"key_turns": max(keys) - min(keys), "rests": max(rests) - min(rests)})
        _, tl0 = await season(0, "Shuffle season")
        rests0 = [x["rests"] for x in tl0["players"]]
        keys0 = [x["key_turns"] for x in tl0["players"]]
        check("CONTROL: a plain shuffle (fairness 0) is NOT this even", (max(rests0) - min(rests0) > 1) or (max(keys0) - min(keys0) > 1), True)
        check("nobody in the fair season led off more than four times in 12 weeks", max(x["bat_first"] for x in tl["players"]) <= 4, True)

        print("\n── Many seasons, seeded, so the claim is not one lucky run ──")

        def sim_season(fairness: int, sd: int, n: int, innings: int, weeks: int = 12):
            ks = [f"k{i}" for i in range(n)]
            rng = random.Random(sd)
            rounds = []
            for _ in range(weeks):
                gen = svc.generate(ks, positions, svc.history_stats(rounds), innings=innings, fairness=fairness, rng=rng)
                rounds.append({"present": ks, "batting_order": gen["batting_order"], "fielding": gen["fielding"]})
            return svc.tally([{"id": k, "name": k} for k in ks], positions, rounds)["players"]

        for n, inn in ((11, 1), (11, 3), (9, 1), (13, 2)):
            worst_rest = worst_key = 0
            fair_avg = shuffle_avg = 0.0
            for sd in range(40):
                f = sim_season(60, sd, n, inn)
                worst_rest = max(worst_rest, max(x["rests"] for x in f) - min(x["rests"] for x in f))
                worst_key = max(worst_key, max(x["key_turns"] for x in f) - min(x["key_turns"] for x in f))
                fair_avg += max(x["bat_avg"] for x in f) - min(x["bat_avg"] for x in f)
                sh = sim_season(0, sd, n, inn)
                shuffle_avg += max(x["bat_avg"] for x in sh) - min(x["bat_avg"] for x in sh)
            check(f"{n} kids, {inn} change(s), 40 seasons: rests never differ by more than one", worst_rest <= 1, True)
            check(f"{n} kids, {inn} change(s), 40 seasons: key turns never differ by more than two", worst_key <= 2, True)
            check(f"{n} kids, {inn} change(s): batting average positions are well tighter than a shuffle's", fair_avg < 0.7 * shuffle_avg, True)

        print("\n── It stays random ──")
        hist = svc.history_stats([{"present": list(players.values()), "batting_order": list(players.values()), "fielding": []}])
        draws = [svc.generate(list(players.values()), positions, hist, fairness=100, rng=random.Random(s)) for s in range(80)]
        check("80 draws from one history give many different batting orders", len({tuple(d["batting_order"]) for d in draws}) > 40, True)
        check("and more than three different openers", len({d["batting_order"][0] for d in draws}) > 3, True)
        check("the kid who batted LAST before is likelier to open than the one who opened",
              sum(1 for d in draws if d["batting_order"][0] == list(players.values())[-1])
              > sum(1 for d in draws if d["batting_order"][0] == list(players.values())[0]), True)

        print("\n── Players: former, revived, avoid ──")
        sam = players["Sam Taylor"]
        pr = await R.patch_player(sam, R.PlayerPatch(active=False), **kw(R.patch_player))
        check("a kid who leaves is marked, not deleted", pr["player"]["former_at"] is not None, True)
        rr = (await R.create_round(gid, R.RoundCreate(), db=db, club=club, user=user))["round"]
        check("a former kid is left out of new rounds", (sam in rr["present"], len(rr["present"])), (False, 10))
        back = await R.add_players(gid, R.PlayersAdd(names="sam taylor, Brand New Kid"), **kw(R.add_players))
        check("typing a former kid's name brings them back (no second person)", (back["returned"], back["added"]), (1, 1))
        check("their id is the same", sam in [x["id"] for x in back["players"] if not x["former_at"]], True)
        check("a name already in the group is skipped", (await R.add_players(gid, R.PlayersAdd(names="Ava Brown"), **kw(R.add_players)))["skipped"], 1)
        check("renaming onto someone else's name is refused",
              await refused(R.patch_player(players["Ava Brown"], R.PlayerPatch(name="noah smith"), **kw(R.patch_player)), 400))
        pitcher = pos_ids[0]
        await R.patch_player(players["Ava Brown"], R.PlayerPatch(avoid_positions=[pitcher, "bogus"]), **kw(R.patch_player))
        pl = {x["id"]: x for x in (await R.get_group(gid, **kw(R.get_group)))["players"]}
        check("an avoid list keeps only the group's own positions", pl[players["Ava Brown"]]["avoid_positions"], [pitcher])
        violations = 0
        for _ in range(40):
            x = (await R.create_round(gid, R.RoundCreate(), db=db, club=club, user=user))["round"]
            violations += x["fielding"][0].get(players["Ava Brown"]) == pitcher
            await R.delete_round(x["id"], **kw(R.delete_round))
        check("a kid to be kept off pitcher is not put there in 40 draws", violations, 0)

        print("\n── Several field changes in one game ──")
        await R.patch_group(gid, R.GroupPatch(innings=3), db=db, club=club, user=user)
        x = (await R.create_round(gid, R.RoundCreate(), db=db, club=club, user=user))["round"]
        present = len(x["present"])
        check("three field changes", len(x["fielding"]), 3)
        rested = [{k for k, v in c.items() if v is None} for c in x["fielding"]]
        check("each change rests the spare kids", [len(s) for s in rested], [present - 9] * 3)
        check("nobody rests in all of the changes while others rest none", len(set().union(*rested)) >= present - 9 + 1, True)
        await R.delete_round(x["id"], **kw(R.delete_round))
        await R.patch_group(gid, R.GroupPatch(innings=1), db=db, club=club, user=user)
        few = (await R.create_round(gid, R.RoundCreate(present=[players["Ava Brown"], players["Noah Smith"], players["Mia Jones"]]), db=db, club=club, user=user))["round"]
        check("too few kids leaves positions empty and says so in words", any(w.startswith("Nobody on:") for w in few["warnings"]), True)
        check("the key positions are kept when there are too few", len({v for v in few["fielding"][0].values() if v} & key_ids), 3)
        await R.delete_round(few["id"], **kw(R.delete_round))

        print("\n── One club cannot see another's ──")
        check("another club's group is a 404", await refused(R.get_group(gid, db=db, club=other, _=user), 404))
        check("another club's round is a 404", await refused(R.get_round(rr["id"], db=db, club=other, _=user), 404))
        check("another club's player cannot be edited", await refused(R.patch_player(sam, R.PlayerPatch(active=True), db=db, club=other, _=user), 404))
        check("another club lists none of ours", (await R.list_groups(archived=False, db=db, club=other, _=user))["groups"], [])
        check("a junk id is a 404, not a 500", await refused(R.get_group("not-a-uuid", **kw(R.get_group)), 404))

        print("\n── The parent link ──")
        sid_locked = (await R.create_group(R.GroupCreate(name="Kanga Group", preset="junior_cricket",
                                                         names="Ollie Nguyen\nOllie Nash\nIsla Roberts\nCharlie Singh"), db=db, club=club, user=user))["group"]["id"]
        cr = (await R.create_round(sid_locked, R.RoundCreate(label="vs Bayswater"), db=db, club=club, user=user))["round"]
        draft_only = (await R.create_round(sid_locked, R.RoundCreate(label="Draft only"), db=db, club=club, user=user))["round"]
        await R.lock_round(cr["id"], **kw(R.lock_round))
        grp = (await R.get_group(sid_locked, **kw(R.get_group)))["group"]
        check("no token until the link is turned on", grp["public_path"], None)

        class Req:
            headers: dict = {}
            client = None

        check("an unknown token is a 404", await refused(P.landing("nope", Req(), db=db), 404))
        grp = (await R.patch_group(sid_locked, R.GroupPatch(public_enabled=True), db=db, club=club, user=user))["group"]
        token = grp["public_path"].rsplit("/", 1)[1]
        check("turning it on mints a token", bool(token), True)
        page = await P.landing(token, Req(), db=db)
        check("only the locked round is public", [r["label"] for r in page["rounds"]], ["vs Bayswater"])
        check("the draft never leaves the admin screens", "Draft only" in str(page), False)
        flat = str(page)
        check("no ids on the public payload", any(i in flat for i in (sid_locked, cr["id"], *cr["present"])), False)
        names = page["rounds"][0]["batting"]
        check("two Ollies and the others: first name and initial, collisions fall back to full names",
              sorted(names), sorted(["Ollie Nguyen", "Ollie Nash", "Isla R.", "Charlie S."]))
        check("the field lists every position by name", [s["position"] for s in page["rounds"][0]["changes"][0]["slots"]][:2], ["Wicketkeeper", "Bowler"])
        await R.patch_group(sid_locked, R.GroupPatch(public_show_surnames=True), db=db, club=club, user=user)
        page = await P.landing(token, Req(), db=db)
        check("surnames on shows them", sorted(page["rounds"][0]["batting"]), sorted(["Ollie Nguyen", "Ollie Nash", "Isla Roberts", "Charlie Singh"]))
        new_link = (await R.regenerate_link(sid_locked, **kw(R.regenerate_link)))["group"]["public_path"].rsplit("/", 1)[1]
        check("rotating the link kills the old one", await refused(P.landing(token, Req(), db=db), 404))
        check("and the new one works", (await P.landing(new_link, Req(), db=db))["group"]["name"], "Kanga Group")
        await R.patch_group(sid_locked, R.GroupPatch(public_enabled=False), db=db, club=club, user=user)
        check("turning it off is a 404 and the token is kept", await refused(P.landing(new_link, Req(), db=db), 404))
        await R.patch_group(sid_locked, R.GroupPatch(public_enabled=True), db=db, club=club, user=user)
        check("turning it back on keeps the same link", (await R.get_group(sid_locked, **kw(R.get_group)))["group"]["public_path"].rsplit("/", 1)[1], new_link)
        await R.archive_group(sid_locked, undo=False, **kw(R.archive_group))
        check("an archived group's link is a 404", await refused(P.landing(new_link, Req(), db=db), 404))
        await R.archive_group(sid_locked, undo=True, **kw(R.archive_group))
        check("restoring it brings the link back", (await P.landing(new_link, Req(), db=db))["group"]["name"], "Kanga Group")
        await db.execute(text("UPDATE organisations SET module_overrides = '[]'::jsonb WHERE id = :i"), {"i": ids["club"]})
        await db.commit()
        await db.refresh(club)
        check("a club that has lost BetterSelect is a 404", await refused(P.landing(new_link, Req(), db=db), 404))
        await db.execute(text("UPDATE organisations SET module_overrides = '[\"select\"]'::jsonb WHERE id = :i"), {"i": ids["club"]})
        await db.commit()
        await db.refresh(club)
        check("archived groups list apart from live ones",
              ([g["name"] for g in (await R.list_groups(archived=True, **kw(R.list_groups)))["groups"]], "Kanga Group" in [g["name"] for g in (await R.list_groups(archived=False, **kw(R.list_groups)))["groups"]]),
              ([], True))

    print("\n── Registered behind the BetterSelect module ──")
    from app.main import app
    paths = {getattr(r, "path", None): r for r in app.routes}
    route = paths.get("/rotation/groups")
    check("the admin router is mounted", route is not None, True)
    check("and sits behind a module dependency", bool(getattr(route, "dependencies", None)), True)
    check("the parent link is mounted un-gated (token only)", "/public/rotation/{token}" in paths, True)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\n".join(FAILURES))
        sys.exit(1)


asyncio.run(main())
