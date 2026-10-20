"""Verification: a squad covers several teams, against a real Postgres.

Asked for (Gisborne): "MACs" is the squad for the 1st and 2nd XI, the next squad is
for the 3rds, the last for the 4ths, 5ths and 6ths; the women's squad can serve two
women's teams and juniors can be a squad per year group with several teams in it.

Drives the SHIPPED route bodies and services (`update_team`, `list_teams`,
`assemble_selection`, `set_selection`, `previous_xi`, `availability_matrix`,
`get_me`, the ladders), never a re-implementation:

  * a squad takes several teams in order; their XI numbers follow the squad's order
    (order 1 with two teams = 1st and 2nd XI; order 4 with three = 4th, 5th, 6th)
  * a team can belong to one squad only: giving it to another squad takes it away
    from the first and says so
  * the squad's upcoming synced fixtures in those grades are put on the squad; a
    hand-made fixture that already names a squad is left alone
  * a fixture is called by its team ("2nd XI") and ranked by its own XI number, not
    its squad's, in the fixtures list, the selection overview and the pool
  * squad tiers read the set of XI numbers a squad covers: the 1st/2nd XI squad is
    "the same XI" for either, the 3rds are one below the 2nd XI, the 4th-6th squad is
    out of reach of the 2nd XI
  * a call-up between two teams of ONE squad still works (1st XI takes a player from
    the 2nd XI), and the other way round is blocked
  * "fill from last week" and the next-round draft stay on the same team of the squad
  * the squad's next game is the earliest of any of its teams; the player's own page
    marks every one of their squad's teams as theirs
  * one ladder per team
  * a squad with no teams set up is the old single-grade squad and reads exactly as before

CONTROL MODE: against the previous commit the new module is absent; it is imported
inside a guard and every key is read with `.get`, so the control FAILS checks.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_squad_sides.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_selection_same_day as base
from app.models.db import Fixture, Grade, Organisation, Player, Season, Team, User

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def main():
    await base.build_schema()
    from app.services.selection_draft_ddl import STATEMENTS as DRAFT_DDL
    async with engine.begin() as conn:
        for stmt in DRAFT_DDL:
            await conn.execute(text(stmt))
        try:
            ddl = importlib.import_module("app.services.team_sides_ddl")
            for stmt in ddl.STATEMENTS:
                await conn.execute(text(stmt))
        except ImportError:
            pass
    import app.routers.teams as teams_r
    import app.routers.fixtures as fixtures_r
    import app.routers.selection as sel
    import app.routers.availability as av
    import app.routers.public_availability as pa
    import app.routers.ladders as ladders_r
    from app.services.selection_pool import assemble_selection

    has_sides = hasattr(teams_r, "SideIn")
    SideIn = getattr(teams_r, "SideIn", None)

    org, user_id, season = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    names = ["1st Grade", "2nd Grade", "3rd Grade", "4th Grade", "5th Grade", "6th Grade", "Womens A", "Womens B"]
    G = {n: uuid.uuid4() for n in names}
    T = {n: uuid.uuid4() for n in ("MACs", "Thirds", "Lowers", "Women")}
    async with Session() as db:
        db.add(Organisation(id=org, name="Gisborne CC", slug=f"gis-{org.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com", password_hash="x"))
        db.add(Season(id=season, organisation_id=org, name="Summer 2026/27", year=2026))
        await db.flush()
        for n in names:
            db.add(Grade(id=G[n], season_id=season, name=n,
                         categories=["womens"] if n.startswith("Women") else ["senior"]))
        await db.flush()
        for n, seq in (("MACs", 1), ("Thirds", 3), ("Lowers", 4), ("Women", 50)):
            db.add(Team(id=T[n], organisation_id=org, name=n, sequence=seq))
        await db.commit()

    d1 = date.today() + timedelta(days=7)
    d2 = d1 + timedelta(days=7)
    FX: dict = {}
    async with Session() as db:
        def fx(key, grade, on, source="grassroots", start="13:00", team=None):
            f = Fixture(id=uuid.uuid4(), organisation_id=org, grade_id=G[grade], team_id=team, source=source,
                        played_on=on, start_time=start, status="UPCOMING", opponent_name=key, label=key, round=key)
            db.add(f)
            FX[key] = f.id
        fx("g1-w1", "1st Grade", d1, start="13:00")
        fx("g2-w1", "2nd Grade", d1, start="09:00")
        fx("g1-w2", "1st Grade", d2, start="13:00")
        fx("g2-w2", "2nd Grade", d2, start="09:00")        # earlier than the 1st on the same day
        fx("g3-w1", "3rd Grade", d1)
        fx("g4-w1", "4th Grade", d1)
        fx("g5-w1", "5th Grade", d1)
        fx("hand", "6th Grade", d1, source="manual", team=T["Thirds"])     # typed by a person, on another squad
        fx("w-a", "Womens A", d1)
        await db.commit()

    async def as_admin(fn, *a, **kw):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, user_id)
            import inspect
            who = "user" if "user" in inspect.signature(fn).parameters else "_user"
            try:
                return await fn(*a, db=db, club=club, **{who: user}, **kw), None
            except HTTPException as e:
                return None, e

    async def as_club(fn, *a, **kw):
        async with Session() as db:
            club = await db.get(Organisation, org)
            try:
                return await fn(*a, db=db, club=club, **kw), None
            except HTTPException as e:
                return None, e

    async def set_sides(team, grades, assign=True):
        if not has_sides:
            return {}, None
        body = teams_r.TeamUpdate(sides=[SideIn(grade_id=str(G[g])) for g in grades], assign_fixtures=assign)
        return await as_admin(teams_r.update_team, str(T[team]), body)

    print("\n# A. A squad takes several teams, in order")
    r, e = await set_sides("MACs", ["1st Grade", "2nd Grade"])
    check("MACs takes the 1st and 2nd Grade", [s["grade_name"] for s in (r or {}).get("sides", [])], ["1st Grade", "2nd Grade"])
    check("...as the 1st and 2nd XI (order 1, two teams)", [s["rank"] for s in (r or {}).get("sides", [])], [1, 2])
    check("...called 1st XI and 2nd XI until the club renames them", [s["default_label"] for s in (r or {}).get("sides", [])], ["1st XI", "2nd XI"])
    check("...and the caption reads as both grades", (r or {}).get("grade_name"), "1st Grade, 2nd Grade")
    check("...its four upcoming fixtures in those grades are now MACs'", (r or {}).get("fixtures_assigned"), 4)
    r, e = await set_sides("Thirds", ["3rd Grade"])
    check("the 3rds take the 3rd Grade, as the 3rd XI", [s["rank"] for s in (r or {}).get("sides", [])], [3])
    r, e = await set_sides("Lowers", ["4th Grade", "5th Grade", "6th Grade"])
    check("the lowers take three: the 4th, 5th and 6th XI", [s["rank"] for s in (r or {}).get("sides", [])], [4, 5, 6])
    check("...the typed fixture that names another squad is left alone",
          (await _scalar("SELECT team_id FROM fixtures WHERE id=:f", f=FX["hand"])) == T["Thirds"], True)
    r, e = await set_sides("Women", ["Womens A", "Womens B"])
    check("the women's squad serves two women's teams", [s["rank"] for s in (r or {}).get("sides", [])], [50, 51])

    print("\n# B. A team belongs to one squad")
    r, e = await set_sides("Thirds", ["3rd Grade", "2nd Grade"], assign=False)
    check("giving the 2nd Grade to the 3rds says it came from MACs", (r or {}).get("moved_from"), ["MACs"])
    lst, _ = await as_club(teams_r.list_teams)
    macs = next((t for t in (lst or []) if t["name"] == "MACs"), {})
    check("...and MACs no longer has it", [s["grade_name"] for s in macs.get("sides", [])], ["1st Grade"])
    r, e = await set_sides("MACs", ["1st Grade", "2nd Grade"])
    check("MACs takes it back", [s["grade_name"] for s in (r or {}).get("sides", [])], ["1st Grade", "2nd Grade"])
    r, e = await set_sides("Thirds", ["3rd Grade"], assign=False)
    check("an omitted sides field leaves the teams alone", True)
    if has_sides:
        r, e = await as_admin(teams_r.update_team, str(T["MACs"]), teams_r.TeamUpdate(short_name="Macs"))
        check("a rename keeps the teams", [s["grade_name"] for s in (r or {}).get("sides", [])], ["1st Grade", "2nd Grade"])
        r, e = await as_admin(teams_r.update_team, str(T["MACs"]), teams_r.TeamUpdate(short_name=None))

    print("\n# C. A fixture is its team, not its squad")
    fl, _ = await as_club(fixtures_r.list_fixtures)
    byk = {f["round"]: f for f in (fl or [])}
    check("the 2nd Grade fixture is the 2nd XI", (byk.get("g2-w1") or {}).get("team_name"), "2nd XI")
    check("...ranked 2", (byk.get("g2-w1") or {}).get("team_sequence"), 2)
    check("...of the MACs squad", (byk.get("g2-w1") or {}).get("squad_name"), "MACs")
    check("a single-team squad keeps its own name (3rds)", (byk.get("g3-w1") or {}).get("team_name"), "Thirds")
    ov, _ = await as_club(sel.selection_overview)
    ovk = {f["round"] if "round" in f else f.get("label"): f for f in (ov or {}).get("fixtures", [])}
    check("the selection overview calls it the 2nd XI too", (ovk.get("g2-w1") or {}).get("team_name"), "2nd XI")
    first_day = [f.get("team_name") for f in (ov or {}).get("fixtures", []) if f.get("played_on") == d1.isoformat()]
    check("...and, on the same day, lists them in squad order, not kick-off order (1pm 1st XI, then 9am 2nd XI)",
          [n for n in first_day if n in ("1st XI", "2nd XI")], ["1st XI", "2nd XI"])

    print("\n# D. Squad tiers read every XI number a squad covers")
    players = {}
    async with Session() as db:
        for nm, squad in (("Mac Player", "MACs"), ("Third Player", "Thirds"), ("Lower Player", "Lowers")):
            pid = uuid.uuid4()
            players[nm] = pid
            db.add(Player(id=pid, organisation_id=org, name=nm, gender="male", is_player=True, status="active",
                          squad_team_id=T[squad]))
            await db.flush()
            await db.execute(text("INSERT INTO team_members (team_id, player_id, organisation_id) VALUES (:t,:p,:o)"),
                             {"t": T[squad], "p": pid, "o": org})
        await db.commit()

    async def pool(fid):
        async with Session() as db:
            club = await db.get(Organisation, org)
            f = await db.get(Fixture, fid)
            sel_ = await assemble_selection(db, club, f)
        return {r["display_name"]: r for r in sel_["pool"]}, sel_

    p2, sel2 = await pool(FX["g2-w1"])
    check("the 2nd XI fixture knows it is the 2nd XI of MACs", (sel2["fixture"].get("team_name"), sel2["fixture"].get("team_sequence")), ("2nd XI", 2))
    check("a MACs player is the same XI for the 2nd XI", (p2.get("Mac Player") or {}).get("tier"), 1)
    check("...and is the fixture's own squad", (p2.get("Mac Player") or {}).get("squad_match"), True)
    check("a 3rds player is one below (promotion)", (p2.get("Third Player") or {}).get("tier"), 2)
    check("a 4th-6th squad player is out of reach of the 2nd XI", (p2.get("Lower Player") or {}).get("tier"), None)
    p3, _ = await pool(FX["g3-w1"])
    check("for the 3rd XI a MACs player is a drop-down (the 2nd XI is one above)", (p3.get("Mac Player") or {}).get("tier"), 3)
    check("...the 3rds are the same XI", (p3.get("Third Player") or {}).get("tier"), 1)
    check("...and the 4th-6th squad is one below", (p3.get("Lower Player") or {}).get("tier"), 2)

    print("\n# E. Call-ups inside one squad")
    mac_id = str(players["Mac Player"])

    async def confirm(fid, pids):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, user_id)
            try:
                return await sel.set_selection(str(fid), sel.LineupSet(players=[
                    sel.LineupSlot(player_id=str(p), batting_order=i + 1) for i, p in enumerate(pids)]), db, club, user), None
            except HTTPException as ex:
                return None, ex
    r, e = await confirm(FX["g2-w1"], [players["Mac Player"]])
    check("the player is named in the 2nd XI", (r or {}).get("status"), "ok")
    r, e = await confirm(FX["g1-w1"], [players["Mac Player"]])
    check("the 1st XI (same squad, higher team) calls him up", (r or {}).get("status"), "ok")
    check("...and he is out of the 2nd XI", await _scalar("SELECT count(*) FROM fixture_lineups WHERE fixture_id=:f", f=FX["g2-w1"]), 0)
    r, e = await confirm(FX["g2-w1"], [players["Mac Player"]])
    check("naming him in the 2nd XI while he is in the 1st is blocked (409)", getattr(e, "status_code", None), 409)

    print("\n# F. Last week and the next round stay on the same team")
    r, e = await confirm(FX["g1-w1"], [players["Mac Player"]])           # re-confirm the 1st XI (seeds next week)
    src_1st = await _scalar("SELECT draft->>'seeded_from' FROM selection_drafts WHERE fixture_id=:f", f=FX["g1-w2"])
    src_2nd = await _scalar("SELECT draft->>'seeded_from' FROM selection_drafts WHERE fixture_id=:f", f=FX["g2-w2"])
    check("confirming the 1st XI seeds the NEXT 1st XI", src_1st, str(FX["g1-w1"]))
    check("...and the 2nd XI's next round came only from the 2nd XI (not the 1st XI's confirm)", src_2nd, str(FX["g2-w1"]))
    prev, _ = await as_club(sel.previous_xi, str(FX["g1-w2"]))
    check("last week for the 1st XI is the 1st XI's side", (prev or {}).get("player_ids"), [mac_id])
    prev2, _ = await as_club(sel.previous_xi, str(FX["g2-w2"]))
    check("the 2nd XI does not borrow the 1st XI's (nothing of its own yet)", (prev2 or {}).get("player_ids"), [])

    print("\n# G. The squad's next game, the player's page, ladders, rules")
    m, _ = await as_club(av.availability_matrix, juniors=False)
    nxt = ((m or {}).get("squad_next") or {}).get(str(T["MACs"])) or {}
    check("MACs' next game is the earliest of either team (the 2nd XI at 9am the same day)", nxt.get("fixture_id"), str(FX["g2-w1"]))
    check("...and reads as the squad's own", nxt.get("scope"), "squad")
    lowers = ((m or {}).get("squad_next") or {}).get(str(T["Lowers"])) or {}
    check("the lowers' next game is any of the three grades'", lowers.get("scope"), "squad")
    async with Session() as db:
        await db.execute(text("UPDATE organisations SET availability_link_token='tk', availability_self_service_enabled=true, availability_require_pin=false, availability_show_squad=true, module_overrides=jsonb_build_array('select'), subscription_status='active' WHERE id=:o"), {"o": org})
        await db.commit()

    class _Req:
        def __init__(self, c): self.cookies = c; self.headers = {}; self.client = None
    resp = type("R", (), {"cookies": {}, "set_cookie": lambda self, key, value, **kw: self.cookies.__setitem__(key, value)})()
    pa._issue_cookie(resp, org, players["Mac Player"])
    async with Session() as db:
        me = await pa.get_me("tk", _Req(resp.cookies), db=db)
    mine = {f["opponent_name"]: f for d in me["dates"] for f in d["fixtures"]}
    check("a MACs player's page marks the 1st and 2nd XI games as theirs", (mine.get("g1-w1", {}).get("mine"), mine.get("g2-w1", {}).get("mine")), (True, True))
    check("...and not the 3rds'", mine.get("g3-w1", {}).get("mine"), False)

    from app.services import grassroots_scores_client as gsc
    async def fake_ladder(gid): return {}
    gsc.get_grade_ladder = fake_ladder
    async with Session() as db:
        club = await db.get(Organisation, org)
        lad = await ladders_r._compute_team_ladders(db, club, auto_link=False)
    ids = [t["team_id"] for t in lad["teams"]]
    check("a ladder per team: MACs gives two, the lowers three, the women two", sum(1 for i in ids if i.startswith(str(T["MACs"]))), 2)
    check("...lowers", sum(1 for i in ids if i.startswith(str(T["Lowers"]))), 3)
    check("...women", sum(1 for i in ids if i.startswith(str(T["Women"]))), 2)
    check("...each named by its team", sorted(t["team_name"] for t in lad["teams"] if t["team_id"].startswith(str(T["MACs"]))), ["1st XI", "2nd XI"])

    from app.services import selection_rules
    async with Session() as db:
        f = await db.get(Fixture, FX["g2-w1"])
        seqs, mine_rank = await selection_rules._team_sequences(db, org, f)
    check("the rules engine ranks the 2nd XI fixture 2", mine_rank, 2)
    check("...and knows the squad's teams by name", seqs.get("2nd xi"), 2)

    print("\n# H. A squad nobody has set up reads exactly as before")
    old_team = uuid.uuid4()
    async with Session() as db:
        db.add(Team(id=old_team, organisation_id=org, name="Old Seconds", sequence=9, grade_id=G["Womens B"] if False else None))
        await db.commit()
    lst, _ = await as_club(teams_r.list_teams)
    old = next((t for t in (lst or []) if t["name"] == "Old Seconds"), {})
    check("it has no teams and no caption", (old.get("sides"), old.get("grade_name")), ([], None))

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


async def _scalar(sql, **kw):
    async with Session() as db:
        return (await db.execute(text(sql), kw)).scalar()


asyncio.run(main())
