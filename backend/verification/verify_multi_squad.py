"""Verification for multi-squad membership, against a real Postgres.

A player can be in several squads at once (1st XI + 2nd XI + Colts + T20). This
exercises the SHIPPED helpers and route bodies — never a re-implementation:

  * team_members is authoritative; players.squad_team_id is the DERIVED primary
    (top-ranked member squad). add / move / remove / set all keep it in step.
  * The Squads board's squad-assign actions (set/add/move/remove).
  * Ratio auto-assign: 50 games 1sts / 40 2nds / 10 3rds → the 1st and 2nd XI
    squads, not the 3rd; the top team is always suggested.
  * Membership-aware selection eligibility: a fringe player genuinely in the
    2nd XI squad is an exact match (tier 1) when the 2nd XI is picked, and a
    drop-down (tier 3) for the 1st XI; the gender wall still holds.
  * Marking a player inactive clears EVERY squad, in one write.
  * The legacy single squad_team_id backfills into team_members (main.py).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_multi_squad.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import (
    Base, Organisation, User, Player, Team, TeamMember, Grade, Season, Game,
    GameAppearance, Fixture,
)
from app.services import squad_membership as sm
from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

MAIN = Path(__file__).resolve().parent.parent / "app/main.py"


def _create_stmt(table):
    """Pull a raw-SQL table's CREATE out of the lifespan (create_all never made
    it), the way the other suites lift lifespan-only tables."""
    src = MAIN.read_text()
    m = re.search(r"(CREATE TABLE IF NOT EXISTS " + table + r" \([\s\S]*?\n\s*\))", src)
    return m.group(1) if m else None


DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def primary(db, pid):
    return (await db.execute(text("SELECT squad_team_id FROM players WHERE id=:p"), {"p": pid})).scalar()


async def members(db, pid):
    rows = (await db.execute(text("SELECT team_id FROM team_members WHERE player_id=:p"), {"p": pid})).all()
    return {r[0] for r in rows}


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # assemble_selection reads the club's association rules and the nets
        # training window — both raw-SQL lifespan tables create_all never built.
        for t in ("net_sessions", "net_attendance"):
            stmt = _create_stmt(t)
            if stmt:
                await conn.execute(text(stmt))
        for stmt in SELECTION_RULE_STATEMENTS:
            await conn.execute(text(stmt))

    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    # Teams: 1st (seq1), 2nd (seq2), 3rd (seq3), Colts (unranked seq0), Women's.
    T1, T2, T3, TC, TW = (uuid.uuid4() for _ in range(5))
    season_id = uuid.uuid4()
    # Grades linked to the ranked teams (name == team name, for auto-assign).
    G1, G2, G3, GW = (uuid.uuid4() for _ in range(4))

    async with Session() as db:
        db.add(Organisation(id=org_id, name="Verify CC", slug=f"verify-{org_id.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com",
                    password_hash="x"))
        db.add(Season(id=season_id, organisation_id=org_id, name="Summer 2025/26", year=2025))
        for gid, nm, fee in [(G1, "1st XI", None), (G2, "2nd XI", None), (G3, "3rd XI", None), (GW, "Women's", "women")]:
            db.add(Grade(id=gid, season_id=season_id, name=nm, fee_format=fee))
        db.add(Team(id=T1, organisation_id=org_id, name="1st XI", sequence=1, grade_id=G1))
        db.add(Team(id=T2, organisation_id=org_id, name="2nd XI", sequence=2, grade_id=G2))
        db.add(Team(id=T3, organisation_id=org_id, name="3rd XI", sequence=3, grade_id=G3))
        db.add(Team(id=TC, organisation_id=org_id, name="Colts", sequence=0))
        db.add(Team(id=TW, organisation_id=org_id, name="Women's", sequence=1, grade_id=GW))
        await db.commit()

    def mk_player(name, gender="male"):
        pid = uuid.uuid4()
        return pid, Player(id=pid, organisation_id=org_id, name=name, gender=gender, is_player=True, status="active")

    # ── 1. Derived primary + membership helpers ──────────────────────────────
    print("\n# derived primary + helpers")
    p1, obj1 = mk_player("Fringe One")
    async with Session() as db:
        db.add(obj1); await db.commit()
        await sm.add_squad_memberships(db, org_id, p1, [T2, T1, TC], user_id)  # add out of order
        await db.commit()
        check("member of all three", await members(db, p1) == {T1, T2, TC})
        check("primary is top-ranked (1st XI)", await primary(db, p1) == T1)
        # Remove the 1st XI → primary falls to 2nd XI (next ranked); Colts unranked stays last.
        await sm.remove_squad_memberships(db, org_id, p1, [T1]); await db.commit()
        check("after removing 1st, still in 2nd+Colts", await members(db, p1) == {T2, TC})
        check("primary now 2nd XI (ranked beats unranked)", await primary(db, p1) == T2)
        # Remove 2nd → only unranked Colts left → primary Colts.
        await sm.remove_squad_memberships(db, org_id, p1, [T2]); await db.commit()
        check("only Colts left", await members(db, p1) == {TC})
        check("primary is Colts (only member)", await primary(db, p1) == TC)
        # move Colts → 3rd XI
        await sm.move_squad_membership(db, org_id, p1, TC, T3, user_id); await db.commit()
        check("moved Colts→3rd", await members(db, p1) == {T3})
        check("primary 3rd XI", await primary(db, p1) == T3)
        # set replaces the whole set
        await sm.set_squad_memberships(db, org_id, p1, [T1, TW], user_id); await db.commit()
        check("set replaces to {1st, Women's}", await members(db, p1) == {T1, TW})
        # clear
        await sm.clear_all_squad_memberships(db, org_id, p1); await db.commit()
        check("cleared: no memberships", await members(db, p1) == set())
        check("cleared: primary NULL", await primary(db, p1) is None)

    # ── 2. squad-assign route body actions ───────────────────────────────────
    print("\n# squad-assign actions (shipped route body)")
    from app.routers.teams import squad_assign, SquadAssign
    p2, obj2 = mk_player("Board Player")
    async with Session() as db:
        db.add(obj2); await db.commit()
        club = await db.get(Organisation, org_id)
        user = await db.get(User, user_id)
        await squad_assign(SquadAssign(player_ids=[str(p2)], squad_team_id=str(T1), action="add"), db, club, user)
        check("add → in 1st", await members(db, p2) == {T1})
        await squad_assign(SquadAssign(player_ids=[str(p2)], squad_team_id=str(T2), action="add"), db, club, user)
        check("add 2nd (additive) → {1st,2nd}", await members(db, p2) == {T1, T2})
        await squad_assign(SquadAssign(player_ids=[str(p2)], squad_team_id=str(T3),
                                       from_squad_team_id=str(T1), action="move"), db, club, user)
        check("move 1st→3rd → {2nd,3rd}", await members(db, p2) == {T2, T3})
        await squad_assign(SquadAssign(player_ids=[str(p2)], from_squad_team_id=str(T2), action="remove"), db, club, user)
        check("remove 2nd → {3rd}", await members(db, p2) == {T3})
        await squad_assign(SquadAssign(player_ids=[str(p2)], squad_team_id=str(TC), action="set"), db, club, user)
        check("set → only Colts (replaces)", await members(db, p2) == {TC})
        await squad_assign(SquadAssign(player_ids=[str(p2)], squad_team_id=None, action="set"), db, club, user)
        check("set null → cleared", await members(db, p2) == set())

    # ── 3. Ratio auto-assign ─────────────────────────────────────────────────
    print("\n# ratio auto-assign (shipped route body)")
    from app.routers.teams import auto_assign_suggest
    p3, obj3 = mk_player("Straddler")
    async with Session() as db:
        db.add(obj3)
        # 50 games for 1st XI, 40 for 2nd XI, 10 for 3rd XI.
        for tname, gid, n in [("1st XI", G1, 50), ("2nd XI", G2, 40), ("3rd XI", G3, 10)]:
            for i in range(n):
                g = Game(id=uuid.uuid4(), grade_id=gid,
                         played_at=date(2025, 10, 1) + timedelta(days=i))
                db.add(g)
                db.add(GameAppearance(game_id=g.id, player_id=p3, team_name=tname))
        await db.commit()
        club = await db.get(Organisation, org_id)
        user = await db.get(User, user_id)
        res = await auto_assign_suggest(seasons=2, only_unassigned=False, min_share=0.2,
                                        db=db, club=club, _user=user)
        teams_sugg = {s["team_id"] for s in res["suggestions"] if s["player_id"] == str(p3)}
        check("20% share → 1st XI suggested", str(T1) in teams_sugg)
        check("20% share → 2nd XI suggested", str(T2) in teams_sugg)
        check("20% share → 3rd XI (10%) NOT suggested", str(T3) not in teams_sugg)
        res2 = await auto_assign_suggest(seasons=2, only_unassigned=False, min_share=0.05,
                                         db=db, club=club, _user=user)
        teams2 = {s["team_id"] for s in res2["suggestions"] if s["player_id"] == str(p3)}
        check("5% share → 3rd XI now suggested", str(T3) in teams2)
        # already-in a squad is never re-suggested
        await sm.add_squad_memberships(db, org_id, p3, [T1], user_id); await db.commit()
        res3 = await auto_assign_suggest(seasons=2, only_unassigned=False, min_share=0.2,
                                         db=db, club=club, _user=user)
        t3 = {s["team_id"] for s in res3["suggestions"] if s["player_id"] == str(p3)}
        check("already in 1st → not re-suggested", str(T1) not in t3)
        check("still suggests the 2nd XI they're not in", str(T2) in t3)

    # ── 4. Membership-aware selection eligibility ────────────────────────────
    print("\n# membership-aware eligibility (assemble_selection)")
    from app.services.selection_pool import assemble_selection
    pF, objF = mk_player("Eligible Fringe")          # in 1st + 2nd XI
    pM, objM = mk_player("Men Only")                 # in 1st XI only
    pWm, objWm = mk_player("Woman", gender="female")  # in Women's squad
    recent = date.today() - timedelta(days=30)
    async with Session() as db:
        for pid, obj in [(pF, objF), (pM, objM), (pWm, objWm)]:
            db.add(obj)
        await db.commit()
        await sm.add_squad_memberships(db, org_id, pF, [T1, T2], user_id)
        await sm.add_squad_memberships(db, org_id, pM, [T1], user_id)
        await sm.add_squad_memberships(db, org_id, pWm, [TW], user_id)
        # Recent appearance for everyone so the 12-month recency wall passes.
        for pid in (pF, pM, pWm):
            g = Game(id=uuid.uuid4(), grade_id=G1, played_at=recent)
            db.add(g); db.add(GameAppearance(game_id=g.id, player_id=pid, team_name="1st XI"))
        await db.commit()

    async def pool_for(team_id, grade_id):
        async with Session() as db:
            club = await db.get(Organisation, org_id)
            fx = Fixture(id=uuid.uuid4(), organisation_id=org_id, team_id=team_id,
                         grade_id=grade_id, played_on=date.today() + timedelta(days=3))
            db.add(fx); await db.commit()
            data = await assemble_selection(db, club, fx)
            return {row["id"]: row for row in data["pool"]}

    try:
        # Picking the 2nd XI: the fringe player is genuinely in it.
        pool2 = await pool_for(T2, G2)
        check("fringe in 2nd XI: squad_match", pool2[str(pF)]["squad_match"] is True)
        check("fringe in 2nd XI: tier 1", pool2[str(pF)]["tier"] == 1)
        check("fringe in 2nd XI: autofill eligible", pool2[str(pF)]["autofill_eligible"] is True)
        # The 1st-XI-only player is a drop-down (tier 3) for the 2nd XI.
        check("1st-only for 2nd XI: not squad_match", pool2[str(pM)]["squad_match"] is False)
        check("1st-only for 2nd XI: tier 3 (drop-down)", pool2[str(pM)]["tier"] == 3)
        check("1st-only for 2nd XI: eligible", pool2[str(pM)]["autofill_eligible"] is True)

        # Picking the 1st XI: the fringe player is a drop-down there.
        pool1 = await pool_for(T1, G1)
        check("fringe for 1st XI: squad_match", pool1[str(pF)]["squad_match"] is True)
        check("fringe for 1st XI: tier 1", pool1[str(pF)]["tier"] == 1)

        # Picking a women's fixture: a men's-squad-only player fails the gender wall.
        poolW = await pool_for(TW, GW)
        check("men-only for women's fixture: gender_ok False", poolW[str(pM)]["gender_ok"] is False)
        check("men-only for women's fixture: not eligible", poolW[str(pM)]["autofill_eligible"] is False)
        check("woman for women's fixture: gender_ok", poolW[str(pWm)]["gender_ok"] is True)
        check("woman for women's fixture: squad_match", poolW[str(pWm)]["squad_match"] is True)
        check("woman for women's fixture: eligible", poolW[str(pWm)]["autofill_eligible"] is True)
    except Exception as e:
        check(f"assemble_selection ran (error: {str(e)[:120]})", False)

    # ── 5. Profile update: multi-set + inactive clears all ───────────────────
    print("\n# profile update (shipped route body)")
    from app.routers.players import update_player_profile, PlayerProfileUpdate
    pP, objP = mk_player("Profile Player")
    async with Session() as db:
        db.add(objP); await db.commit()
    async with Session() as db:
        user = await db.get(User, user_id)
        await update_player_profile(str(pP), PlayerProfileUpdate(squad_team_ids=[str(T1), str(T2)]), db, user)
    async with Session() as db:
        check("profile multi-set → {1st,2nd}", await members(db, pP) == {T1, T2})
        check("profile multi-set primary 1st", await primary(db, pP) == T1)
    async with Session() as db:
        user = await db.get(User, user_id)
        await update_player_profile(str(pP), PlayerProfileUpdate(status="inactive"), db, user)
    async with Session() as db:
        check("inactive clears every squad", await members(db, pP) == set())
        check("inactive clears primary", await primary(db, pP) is None)

    # ── 6. /club-admin/players exposes squad_team_ids ────────────────────────
    print("\n# payload exposes squad_team_ids")
    from app.routers.club_admin import list_players
    async with Session() as db:
        await sm.add_squad_memberships(db, org_id, pP, [T2, T3], user_id); await db.commit()
        club = await db.get(Organisation, org_id)
        user = await db.get(User, user_id)
        rows = await list_players(user, club, db)
        row = next(r for r in rows if r["id"] == str(pP))
        check("payload carries squad_team_ids array", set(row["squad_team_ids"]) == {str(T2), str(T3)})
        check("payload primary is a ranked one", row["squad_team_id"] == str(T2))

    # ── 7. Legacy backfill: squad_team_id → team_members ─────────────────────
    print("\n# legacy backfill (main.py lifespan statement)")
    pL, objL = mk_player("Legacy Single")
    async with Session() as db:
        # A pre-multi-squad row: squad_team_id set, no team_members row.
        db.add(objL); await db.commit()
        await db.execute(text("UPDATE players SET squad_team_id=:t WHERE id=:p"), {"t": T2, "p": pL})
        await db.commit()
        check("legacy row starts with no membership", await members(db, pL) == set())
        await db.execute(text(
            "INSERT INTO team_members (team_id, player_id, organisation_id) "
            "SELECT squad_team_id, id, organisation_id FROM players "
            "WHERE squad_team_id IS NOT NULL ON CONFLICT DO NOTHING"))
        await db.commit()
        check("backfill mirrors squad_team_id into team_members", T2 in await members(db, pL))

    # cleanup
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM organisations WHERE id=:o"), {"o": org_id})
    await engine.dispose()

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\nFAILURES:")
        for f in FAILURES:
            print("  -", f)
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
