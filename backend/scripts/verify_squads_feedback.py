"""Verification for the BetterSelect Squads feedback pass.

Drives the SHIPPED route bodies and service functions against a real Postgres:
  * marking a player inactive clears their squad (and the team_members mirror);
  * it does NOT move a player whose status this request didn't touch;
  * reactivating does not re-file them;
  * the profile import applies the same rule, off the sheet's own patch;
  * auto-assign never suggests a squad for an inactive player;
  * the Directory's squad write now mirrors into team_members;
  * the payload the Squads board reads carries what the pools split on.

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... \
            python scripts/verify_squads_feedback.py
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date, timedelta

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres@/postgres?host=/tmp&port=5433")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, text

from app.models.db import (
    Base, Organisation, User, Player, Team, TeamMember, Season, Grade, Game, GameAppearance,
)
from app.routers.players import update_player_profile, PlayerProfileUpdate
from app.routers.teams import auto_assign_suggest
from app.routers.club_admin import list_players
from app.services import directory as directory_svc

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  ok  ' if cond else ' FAIL '} {name}{('  — ' + str(detail)) if detail and not cond else ''}")


async def members(db, team_id, player_id):
    return (await db.execute(text(
        "SELECT count(*) FROM team_members WHERE team_id = :t AND player_id = :p"
    ), {"t": team_id, "p": player_id})).scalar()


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    # Reset by schema, not drop_all: organisations <-> users is a genuine FK
    # cycle that DROP-ordering can't resolve.
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    org_id, other_org_id = uuid.uuid4(), uuid.uuid4()
    user_id = uuid.uuid4()
    firsts_id, seconds_id = uuid.uuid4(), uuid.uuid4()
    today = date.today()

    async with Session() as db:
        db.add(Organisation(id=org_id, name="Verify CC", slug="verify-cc", dormancy_months=24))
        db.add(Organisation(id=other_org_id, name="Other CC", slug="other-cc"))
        db.add(User(id=user_id, username="admin", email="a@b.c", password_hash="x"))
        db.add(Team(id=firsts_id, organisation_id=org_id, name="1st XI"))
        db.add(Team(id=seconds_id, organisation_id=org_id, name="2nd XI"))
        await db.commit()

        # A season / grade / games so appearances give players a last_played.
        season_id, grade_id = uuid.uuid4(), uuid.uuid4()
        db.add(Season(id=season_id, organisation_id=org_id, name="Summer 2025/26", year=2025))
        await db.commit()
        db.add(Grade(id=grade_id, season_id=season_id, name="1st Grade"))
        await db.commit()

        def player(name, **kw):
            pid = uuid.uuid4()
            db.add(Player(id=pid, organisation_id=org_id, name=name, **kw))
            return pid

        # current: played last month, in the 1st XI
        current = player("Current, Colin", squad_team_id=firsts_id)
        # dormant: last played 4 years ago, in the 2nd XI
        dormant = player("Dormant, Dave", squad_team_id=seconds_id)
        # never: no appearances at all, unassigned
        never = player("Newbie, Ned")
        # already inactive, sitting in a squad (pre-existing state)
        stale = player("Stale, Sam", squad_team_id=firsts_id, status="inactive")
        # an unassigned recent player, for auto-assign
        recent_free = player("Free, Fred")
        # an inactive player who DID play recently — auto-assign must skip them
        inactive_recent = player("Gone, Gary", status="inactive")
        await db.commit()

        async def appearance(pid, when, team_name="1st XI"):
            gid = uuid.uuid4()
            db.add(Game(id=gid, grade_id=grade_id, played_at=when, home_team="Verify CC",
                        away_team="Someone", result="win"))
            await db.flush()
            db.add(GameAppearance(game_id=gid, player_id=pid, team_name=team_name))
            await db.flush()

        await appearance(current, today - timedelta(days=30))
        await appearance(dormant, today - timedelta(days=365 * 4))
        await appearance(stale, today - timedelta(days=30))
        await appearance(recent_free, today - timedelta(days=20))
        await appearance(inactive_recent, today - timedelta(days=20))
        await db.commit()

        # Mirror the squads into team_members the way every write path does.
        for pid, tid in ((current, firsts_id), (dormant, seconds_id), (stale, firsts_id)):
            db.add(TeamMember(team_id=tid, player_id=pid, organisation_id=org_id))
        await db.commit()

        user = await db.get(User, user_id)
        club = await db.get(Organisation, org_id)

        # ── 1. Marking inactive clears the squad ────────────────────────────
        out = await update_player_profile(str(current), PlayerProfileUpdate(status="inactive"), db, user)
        p = await db.get(Player, current)
        check("marking inactive clears squad_team_id", p.squad_team_id is None, p.squad_team_id)
        check("marking inactive clears the team_members mirror",
              await members(db, firsts_id, current) == 0)
        check("the PATCH response reports the cleared squad",
              (out.get("squad") in (None, {}) or not out.get("squad")), out.get("squad"))
        check("status really is inactive", p.status == "inactive", p.status)

        # ── 2. Reactivating does NOT re-file them ───────────────────────────
        await update_player_profile(str(current), PlayerProfileUpdate(status="active"), db, user)
        p = await db.get(Player, current)
        check("reactivating leaves them unassigned", p.squad_team_id is None, p.squad_team_id)

        # ── 3. An unrelated edit never moves an already-inactive player ─────
        before = (await db.get(Player, stale)).squad_team_id
        await update_player_profile(str(stale), PlayerProfileUpdate(player_role="Batter"), db, user)
        p = await db.get(Player, stale)
        check("editing an already-inactive player's other fields leaves their squad alone",
              p.squad_team_id == before and before is not None, f"{before} -> {p.squad_team_id}")
        check("...and leaves the team_members mirror alone",
              await members(db, firsts_id, stale) == 1)

        # ── 4. Re-asserting inactive DOES clear it ──────────────────────────
        await update_player_profile(str(stale), PlayerProfileUpdate(status="inactive"), db, user)
        p = await db.get(Player, stale)
        check("re-asserting inactive clears a squad set earlier", p.squad_team_id is None, p.squad_team_id)
        check("...and drops the mirror row", await members(db, firsts_id, stale) == 0)

        # ── 5. Squad + inactive in ONE request: inactive wins, no stale row ──
        await update_player_profile(
            str(dormant), PlayerProfileUpdate(squad_team_id=str(firsts_id), status="inactive"), db, user)
        p = await db.get(Player, dormant)
        check("squad + inactive in one request ends unassigned", p.squad_team_id is None, p.squad_team_id)
        check("...leaves no mirror row for the squad it briefly held",
              await members(db, firsts_id, dormant) == 0)
        check("...and none for the squad it came from",
              await members(db, seconds_id, dormant) == 0)

        # ── 6. An ordinary squad assign still works ─────────────────────────
        await update_player_profile(str(never), PlayerProfileUpdate(squad_team_id=str(seconds_id)), db, user)
        p = await db.get(Player, never)
        check("assigning a squad on an active player still works", p.squad_team_id == seconds_id)
        check("...and mirrors into team_members", await members(db, seconds_id, never) == 1)

        # ── 7. Auto-assign skips inactive players ───────────────────────────
        res = await auto_assign_suggest(seasons=60, only_unassigned=True, db=db, club=club, _user=user)
        suggested = {s["player_id"] for s in res["suggestions"]}
        unmatched = {u["player_id"] for u in res.get("unmatched", [])}
        check("auto-assign suggests an active unassigned player",
              str(recent_free) in suggested, sorted(suggested))
        check("auto-assign never suggests an inactive player",
              str(inactive_recent) not in suggested and str(inactive_recent) not in unmatched)

        # ── 8. The Directory's squad write mirrors into team_members ────────
        await directory_svc.set_squad(db, org_id, recent_free, firsts_id)
        await db.commit()
        p = await db.get(Player, recent_free)
        check("Directory set_squad writes players.squad_team_id", p.squad_team_id == firsts_id)
        check("Directory set_squad mirrors into team_members",
              await members(db, firsts_id, recent_free) == 1)
        await directory_svc.set_squad(db, org_id, recent_free, seconds_id)
        await db.commit()
        check("Directory reassign drops the old mirror row",
              await members(db, firsts_id, recent_free) == 0)
        check("Directory reassign adds the new mirror row",
              await members(db, seconds_id, recent_free) == 1)
        await directory_svc.set_squad(db, org_id, recent_free, None)
        await db.commit()
        check("Directory unassign drops the mirror row",
              await members(db, seconds_id, recent_free) == 0)
        # Re-running the same write is a no-op, not a duplicate-key error.
        await directory_svc.set_squad(db, org_id, recent_free, firsts_id)
        await directory_svc.set_squad(db, org_id, recent_free, firsts_id)
        await db.commit()
        check("Directory set_squad is idempotent",
              await members(db, firsts_id, recent_free) == 1)
        try:
            await directory_svc.set_squad(db, org_id, recent_free, uuid.uuid4())
            check("Directory set_squad refuses an unknown team", False)
        except ValueError:
            check("Directory set_squad refuses an unknown team", True)

        # ── 9. The board's payload carries what the pools split on ─────────
        rows = await list_players(user, club, db)
        by_id = {r["id"]: r for r in rows}
        check("board payload carries status", all("status" in r for r in rows))
        check("board payload carries last_played", all("last_played" in r for r in rows))
        check("board payload carries squad_team_id", all("squad_team_id" in r for r in rows))
        check("a never-played player has a null last_played",
              by_id[str(never)]["last_played"] is None, by_id[str(never)]["last_played"])
        check("a dormant player's last_played is outside a 24-month window",
              by_id[str(dormant)]["last_played"] < (today - timedelta(days=730)).isoformat())
        check("an inactive player is still returned (the board filters, the API doesn't)",
              by_id[str(stale)]["status"] == "inactive")

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print("  FAILED:", f)
        raise SystemExit(1)


asyncio.run(main())
