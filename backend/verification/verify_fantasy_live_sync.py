"""Running scores for a Fantasy round that is still being played, against a real Postgres.

Reported (Applecross, Oct 2026): in the middle of a two day round nothing moved. The only way to get a
score was Settle, which also marks the round final. Scores should update as the games are played, with
Settle left to confirm the final figures.

Why nothing moved. Sync stores a game's rows the first time it reads the card and, from then on, only
replaces a figure once CA calls the card COMPLETED. Provisional Fantasy points were only rebuilt by the
05:00 job or the Settle due rounds button, from those frozen rows.

Drives the SHIPPED code with the Cricket Australia client stubbed: `sync_grassroots_game_level_data`,
`services/fantasy_live.live_pass` and `fantasy_engine` (refresh_live_round, settle_round), plus the
`routers/fantasy` route bodies and the member `live` view.

CONTROL: the "before" behaviour is the shipped sync called without `live`; it is asserted inline. The
whole script can also be run against the commit before this change (git worktree): everything it needs
from the new code is read through presence-safe accessors, so absence is reported as failed checks and
not as a crash.

Run, on its own database:
  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_live_sync.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.config.settings import settings
from app.models.db import (
    Base, FantasyLeague, FantasyManager, FantasyPoolPlayer, FantasyRound, FantasySeason, FantasySquad,
    FantasySquadPlayer,
)
from app.services import fantasy_engine, grassroots_scores_client as gr
from app.services.sync import sync_grassroots_game_level_data

try:
    from app.services import fantasy_live
except ImportError:  # pragma: no cover - control run only
    fantasy_live = None

try:
    from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS
except ImportError:  # pragma: no cover
    COMP_STATEMENTS = []
try:
    from app.services.fantasy_live_ddl import STATEMENTS as LIVE_DDL
except ImportError:  # pragma: no cover - control run only
    LIVE_DDL = []

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
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


TZ = ZoneInfo("Australia/Perth")
NOW_UTC = datetime.now(timezone.utc)
TODAY = NOW_UTC.astimezone(TZ).date()
AFTERNOON = datetime.combine(TODAY, datetime.min.time(), tzinfo=TZ).replace(hour=14)
NIGHT = AFTERNOON.replace(hour=23, minute=30)
D1 = TODAY - timedelta(days=1)            # first day of a two day game; the second is a week on

ORG, OPP_ORG = uuid.uuid4(), uuid.uuid4()
SEASON, GRADE_GUID = uuid.uuid4(), str(uuid.uuid4())
GRADE = uuid.UUID(GRADE_GUID)
SUSH, SHUB, MATE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
G1, G2 = uuid.uuid4(), uuid.uuid4()       # G1: the two day game. G2: a one dayer, today
FS_ID, RND, MGR, SQ = (uuid.uuid4() for _ in range(4))


def card(match_id, first_day, status, *, runs, balls, fours, sixes, dt_id, dt, wkts, played=(SUSH, SHUB, MATE),
         days=1):
    ours, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    sched = [{"startDateTime": f"{first_day + timedelta(days=7 * i)}T10:00:00"} for i in range(days)]
    return {
        "id": str(match_id), "status": status, "matchSchedule": sched,
        "venue": {"name": "Oval"}, "grade": {"id": GRADE_GUID, "name": "1st Grade"},
        "teams": [
            {"id": ours, "displayName": "APX 1st", "owningOrganisation": {"id": str(ORG)},
             "players": [{"participantId": str(p), "roles": []} for p in played]},
            {"id": theirs, "displayName": "Them 1st", "owningOrganisation": {"id": str(OPP_ORG)}, "players": []},
        ],
        "matchSummary": {"resultText": "", "teams": [{"id": ours, "displayName": "APX 1st", "isHome": True},
                                                      {"id": theirs, "displayName": "Them 1st", "isHome": False}]},
        "innings": [
            {"inningsOrder": 1, "battingTeamId": ours, "runsScored": runs + 10, "numberOfWicketsFallen": 2,
             "totalExtras": 10, "fallOfWickets": [],
             "batting": [{"participantId": str(SUSH), "dismissalTypeId": dt_id, "dismissalType": dt,
                          "runsScored": runs, "ballsFaced": balls, "foursScored": fours, "sixesScored": sixes,
                          "batOrder": 3}],
             "bowling": [], "fielding": []},
            {"inningsOrder": 2, "battingTeamId": theirs, "runsScored": 40, "numberOfWicketsFallen": wkts,
             "totalExtras": 2, "batting": [],
             "bowling": [{"participantId": str(SHUB), "oversBowled": 4.0, "maidensBowled": 0, "runsConceded": 22,
                          "wicketsTaken": wkts, "wideBalls": 0, "noBalls": 0, "economy": 5.5}],
             "fielding": [],
             "fallOfWickets": [{"order": 1, "runs": 20, "participantId": str(uuid.uuid4()),
                                "playerShortName": "T Opp"}]},
        ],
    }


def entry(mid, first_day, status, days=1):
    return {"id": str(mid), "status": status, "matchType": "Two Day", "round": {"name": "Round 3"},
            "matchSchedule": [{"startDateTime": f"{first_day + timedelta(days=7 * i)}T10:00:00"} for i in range(days)],
            "teams": [{"id": str(uuid.uuid4()), "owningOrganisation": {"id": str(ORG)}},
                      {"id": str(uuid.uuid4()), "owningOrganisation": {"id": str(OPP_ORG), "name": "Them"}}]}


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons "
                                "BOOLEAN NOT NULL DEFAULT false"))
        for stmt in COMP_STATEMENTS:
            await conn.execute(text(stmt))
        for stmt in LIVE_DDL:   # the column is mapped on the ORM model, so the table has it already
            await conn.execute(text(stmt))
        for (tbl,) in (await conn.execute(text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
                "AND column_name='id' AND table_name LIKE 'fantasy\\_%' AND data_type='uuid'"))).all():
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN id SET DEFAULT gen_random_uuid()'))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID,
                keep_player_id UUID, keep_player_name TEXT, removed_player_id UUID,
                removed_player_name TEXT, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID, user_id UUID,
                action TEXT, target_type TEXT, target_id TEXT, details JSONB)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marketing_clubs (
                id SERIAL PRIMARY KEY, existing_org_id UUID, state TEXT)"""))
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for oid, nm, slug, state in ((ORG, "Applecross", "apx", "WA"), (OPP_ORG, "Them CC", "them", "WA")):
            await ex("INSERT INTO organisations (id, name, slug, is_active, state) VALUES (:i, :n, :s, true, :st)",
                     i=oid, n=nm, s=slug, st=state)
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) "
                 "VALUES (:i, :o, 'Summer', :y, :g)", i=SEASON, o=ORG, y=TODAY.year, g=str(SEASON))
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, '1st Grade', :g, 'senior', ARRAY['senior'])", i=GRADE, s=SEASON, g=GRADE_GUID)
        for pid, nm in ((SUSH, "Menon, Sushruth"), (SHUB, "Shubham"), (MATE, "Mate, Mick")):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))
        await s.commit()
    async with Session() as s:
        s.add(FantasySeason(id=FS_ID, organisation_id=ORG, season_year=TODAY.year, name="Fantasy",
                            status="active", scoring={}, rules={"lock_timezone": "Australia/Perth"}))
        await s.flush()
        s.add(FantasyRound(id=RND, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=1, name="Round 1",
                           start_date=D1, end_date=TODAY + timedelta(days=6)))
        s.add_all([FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=p, role="batter",
                                     base_price=5, current_price=5) for p in (SUSH, SHUB, MATE)])
        s.add(FantasyManager(id=MGR, organisation_id=ORG, display_name="Xavier"))
        await s.flush()
        lg = FantasyLeague(id=uuid.uuid4(), fantasy_season_id=FS_ID, organisation_id=ORG,
                           kind="global_salary_cap", name="Club ladder")
        s.add(lg)
        await s.flush()
        s.add(FantasySquad(id=SQ, fantasy_season_id=FS_ID, league_id=lg.id, manager_id=MGR, organisation_id=ORG,
                           team_name="X Team", free_transfers=1))
        await s.flush()
        s.add_all([FantasySquadPlayer(squad_id=SQ, player_id=SUSH, role="batter", is_captain=False),
                   FantasySquadPlayer(squad_id=SQ, player_id=SHUB, role="batter", is_vice_captain=True),
                   FantasySquadPlayer(squad_id=SQ, player_id=MATE, role="batter")])
        await s.commit()


async def val(sql: str, **p):
    async with Session() as s:
        return (await s.execute(text(sql), p)).first()


async def runs_of(game, player):
    r = await val("SELECT runs FROM batting_innings WHERE game_id=:g AND player_id=:p", g=game, p=player)
    return r[0] if r else None


async def wickets_of(game, player):
    r = await val("SELECT wickets FROM bowling_spells WHERE game_id=:g AND player_id=:p", g=game, p=player)
    return r[0] if r else None


async def player_points(player):
    r = await val("SELECT total_points FROM fantasy_player_round_scores WHERE round_id=:r AND player_id=:p",
                  r=RND, p=player)
    return float(r[0]) if r else None


async def squad_points():
    r = await val("SELECT points FROM fantasy_squad_round_scores WHERE round_id=:r AND squad_id=:s", r=RND, s=SQ)
    return float(r[0]) if r else None


async def has_stamp_column() -> bool:
    return bool(await val("SELECT 1 FROM information_schema.columns WHERE table_name = 'fantasy_rounds' "
                          "AND column_name = 'live_checked_at'"))


async def round_row():
    """(status, live_checked_at, scored_at); the stamp reads None where the column does not exist (control run)."""
    if await has_stamp_column():
        return await val("SELECT status, live_checked_at, scored_at FROM fantasy_rounds WHERE id=:r", r=RND)
    r = await val("SELECT status, scored_at FROM fantasy_rounds WHERE id=:r", r=RND)
    return (r[0], None, r[1]) if r else None


async def set_stamp(expr: str) -> None:
    """UPDATE fantasy_rounds SET live_checked_at = <expr>; nothing where the column does not exist."""
    if await has_stamp_column():
        async with Session() as s:
            await s.execute(text(f"UPDATE fantasy_rounds SET live_checked_at = {expr}"))
            await s.commit()


async def free_transfers():
    return (await val("SELECT free_transfers FROM fantasy_squads WHERE id=:s", s=SQ))[0]


async def run_live(*, manual=False, now=AFTERNOON) -> dict:
    """The shipped live pass in its own session, committed as the scheduler / route does."""
    if fantasy_live is None:
        return {"ran": False, "reason": "module missing", "error": True}
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        try:
            res = await fantasy_live.live_pass(s, fs, manual=manual, now=now)
            await s.commit()
            return res
        except Exception as e:  # noqa: BLE001
            await s.rollback()
            return {"ran": False, "reason": f"error: {e}", "error": True}


async def main() -> None:
    await build_schema()
    await seed()

    cards: dict[str, dict] = {}
    statuses: dict[str, str] = {}
    first_day = {str(G1): D1, str(G2): TODAY}
    two_day = {str(G1): 2, str(G2): 1}
    fetched: list[tuple[str, bool]] = []

    async def fake_matches(grade_guid, *a, **k):
        return [entry(m, first_day[m], statuses[m], two_day[m]) for m in statuses]

    async def fake_card(match_id, *a, **k):
        fetched.append((str(match_id), bool(k.get("force"))))
        return cards.get(str(match_id))

    gr.get_grade_matches = fake_matches
    gr.get_match_scorecard = fake_card

    def live1(**k):   # Sushruth at the crease on 23*, Shubham two wickets
        base = dict(runs=23, balls=30, fours=3, sixes=0, dt_id=1, dt="Not Out", wkts=2)
        base.update(k)
        return card(G1, D1, "LIVE", days=2, **base)

    print("\n-- 1. The game is first read in play (Sushruth 1 not out, no wickets yet) --")
    cards[str(G1)] = card(G1, D1, "LIVE", days=2, runs=1, balls=3, fours=0, sixes=0, dt_id=1, dt="Not Out", wkts=0)
    statuses[str(G1)] = "LIVE"
    res = await run_live()
    if fantasy_live is None:   # control run: the old code's only way to store the game is the ordinary sync
        await sync_grassroots_game_level_data(str(ORG), since=D1)
    check("the pass ran", res.get("ran") is True, str(res))
    check("one game read", res.get("games_checked") == 1, str(res))
    check("the new game is stored from the running card: Sushruth 1", await runs_of(G1, SUSH) == 1)
    check("Fantasy shows him on 5 (1 run and 4 for playing) before any settlement", await player_points(SUSH) == 5.0,
          str(await player_points(SUSH)))
    check("his squad has running points", (await squad_points() or 0) > 0, str(await squad_points()))
    st = await round_row()
    check("the round is NOT scored", st is not None and st[0] == "upcoming" and st[2] is None, str(st))
    check("and the pass stamped when it looked", st is not None and st[1] is not None, str(st))
    check("no free transfer was granted", await free_transfers() == 1, str(await free_transfers()))
    check("the scorecard was read fresh, not from the cache", fetched and all(f for _, f in fetched), str(fetched))

    print("\n-- 2. CONTROL: what production did before. The ordinary sync reads the game again --")
    cards[str(G1)] = live1()
    await sync_grassroots_game_level_data(str(ORG), since=D1)
    check("Sushruth is still on 1 although CA now has 23*", await runs_of(G1, SUSH) == 1, str(await runs_of(G1, SUSH)))
    check("and Fantasy still shows 5", await player_points(SUSH) == 5.0)

    print("\n-- 3. The live pass picks up the running score --")
    fetched.clear()
    res = await run_live()
    check("Sushruth is on 23", await runs_of(G1, SUSH) == 23, str(await runs_of(G1, SUSH)))
    check("Shubham has his two wickets", await wickets_of(G1, SHUB) == 2, str(await wickets_of(G1, SHUB)))
    check("Fantasy: 23 runs + 3 fours + 4 for playing = 30", await player_points(SUSH) == 30.0,
          str(await player_points(SUSH)))
    sq1 = await squad_points()
    check("the squad's running total moved with it", sq1 is not None and sq1 > 5, str(sq1))
    check("the pass says what moved", res.get("players_moved", 0) >= 2 and res.get("figures_changed", 0) >= 2
          and any(r.get("action") == "refreshed" for r in res.get("rounds", [])), str(res))
    tot = await val("SELECT innings_totals FROM games WHERE id=:g", g=G1)
    check("the game's stored innings totals follow the card too", tot is not None and tot[0] is not None)

    print("\n-- 4. Nothing changed on CA: the pass looks, writes no scores, and says it looked --")
    before = await val("SELECT MAX(computed_at) FROM fantasy_player_round_scores WHERE round_id=:r", r=RND)
    stamp_before = (await round_row() or (None, None))[1]
    await asyncio.sleep(0.05)
    res = await run_live()
    after = await val("SELECT MAX(computed_at) FROM fantasy_player_round_scores WHERE round_id=:r", r=RND)
    check("it ran and found no change", res.get("ran") is True and res.get("players_moved") == 0
          and not res.get("rounds"), str(res))
    check("no score row was rewritten", before[0] == after[0])
    check("the looked-at stamp moved on", (await round_row())[1] is not None and stamp_before is not None
          and (await round_row())[1] > stamp_before)

    print("\n-- 5. Limits on the scheduled pass --")
    fetched.clear()
    res = await run_live(now=NIGHT)
    check("outside the club's playing hours it reads nothing", res.get("reason") == "outside_play_hours"
          and not fetched, f"{res} {fetched}")
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_seasons SET rules = rules || '{\"live_sync\": false}'::jsonb "
                             "WHERE id=:i"), {"i": FS_ID})
        await s.commit()
    res = await run_live()
    check("a season switched off is not read", res.get("reason") == "switched_off" and not fetched, f"{res} {fetched}")
    res = await run_live(manual=True)
    check("but an admin pressing Sync scores still can (cooldown applies: just checked)",
          res.get("reason") == "just_checked" and not fetched, str(res))
    await set_stamp("NOW() - INTERVAL '5 minutes'")
    res = await run_live(manual=True)
    check("after the cooldown it runs, ignores the playing hours, and rewrites the rows",
          res.get("ran") is True and any(r.get("action") == "refreshed" for r in res.get("rounds", [])), str(res))
    res = await run_live(manual=True, now=NIGHT)
    check("a second press inside a minute gets the first answer", res.get("reason") == "just_checked", str(res))
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_seasons SET rules = rules - 'live_sync' WHERE id=:i"), {"i": FS_ID})
        await s.commit()
    await set_stamp("NULL")
    if hasattr(settings, "fantasy_live_sync_enabled"):
        settings.fantasy_live_sync_enabled = False
        res = await run_live()
        check("the platform switch stops it everywhere", res.get("reason") == "switched_off_platform", str(res))
        settings.fantasy_live_sync_enabled = True
    else:
        check("the platform switch exists", False, "setting missing")
    from app.routers.organisations import _org_sync_running
    _org_sync_running.add(str(ORG))
    fetched.clear()
    res = await run_live()
    check("a club with its own sync running is left alone", res.get("reason") == "sync_running" and not fetched,
          f"{res} {fetched}")
    _org_sync_running.discard(str(ORG))
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_rounds SET start_date = :a, end_date = :b WHERE id=:r"),
                        {"a": TODAY - timedelta(days=30), "b": TODAY - timedelta(days=20), "r": RND})
        await s.commit()
    res = await run_live()
    check("a round whose window is not today is not read", res.get("reason") == "no_running_round", str(res))
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_rounds SET start_date = :a, end_date = :b WHERE id=:r"),
                        {"a": D1, "b": TODAY + timedelta(days=6), "r": RND})
        await s.commit()

    print("\n-- 6. CA calls the game COMPLETED: the final figures land and the game is then left alone --")
    cards[str(G1)] = card(G1, D1, "COMPLETED", days=2, runs=43, balls=40, fours=5, sixes=1, dt_id=2, dt="Caught", wkts=4)
    statuses[str(G1)] = "COMPLETED"
    await run_live()
    check("Sushruth 43 and out", await runs_of(G1, SUSH) == 43)
    check("Fantasy 54 (43 + 5 fours + 2 for the six + 4)", await player_points(SUSH) == 54.0,
          str(await player_points(SUSH)))
    fetched.clear()
    await run_live()
    check("a COMPLETED game we hold as COMPLETED is not read again", not fetched, str(fetched))
    check("the round is still not scored", (await round_row())[0] == "upcoming")

    print("\n-- 7. Settle confirms: same points, and only now the free transfer --")
    live_sq = await squad_points()
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        rnd = await s.get(FantasyRound, RND)
        await fantasy_engine.settle_round(s, fs, rnd)
        await s.commit()
    check("the round is scored", (await round_row())[0] == "scored")
    check("the squad's confirmed points equal the running ones", await squad_points() == live_sq,
          f"{live_sq} vs {await squad_points()}")
    check("the free transfer is banked by Settle (1 -> 2)", await free_transfers() == 2, str(await free_transfers()))

    print("\n-- 8. Settled on its last morning, then a game is played that day --")
    statuses[str(G2)] = "LIVE"
    cards[str(G2)] = card(G2, TODAY, "LIVE", runs=17, balls=20, fours=2, sixes=0, dt_id=1, dt="Not Out", wkts=0,
                          played=(SUSH, SHUB, MATE))
    # G2 has Sushruth on 17* too; G1 is finished and untouched.
    fetched.clear()
    res = await run_live()
    check("the scored round is still looked at (its window includes today)", res.get("ran") is True, str(res))
    check("it was settled again from its stored lineup", any(r.get("action") == "settled_again" for r in res.get("rounds", [])),
          str(res))
    check("Sushruth now has both games: 54 + 17 + 2 + 4 = 77", await player_points(SUSH) == 77.0,
          str(await player_points(SUSH)))
    check("no second free transfer was banked", await free_transfers() == 2, str(await free_transfers()))
    check("the round is still scored", (await round_row())[0] == "scored")

    print("\n-- 9. The admin routes --")
    from app.routers import fantasy as fantasy_router
    async with Session() as s:
        org = await s.get(fantasy_router.Organisation, ORG) if hasattr(fantasy_router, "Organisation") else None
    if org is None:
        from app.models.db import Organisation
        async with Session() as s:
            org = await s.get(Organisation, ORG)
    has_route = hasattr(fantasy_router, "sync_scores")
    check("POST sync-scores exists", has_route)
    if has_route:
        await set_stamp("NULL")
        async with Session() as s:
            out = await fantasy_router.sync_scores(str(FS_ID), club=org, db=s, _=None)
        check("it returns what happened, with a message only when nothing ran", out.get("ran") is True
              and out.get("message") is None, str(out))
        async with Session() as s:
            out = await fantasy_router.sync_scores(str(FS_ID), club=org, db=s, _=None)
        check("and a plain-language message when it did not", out.get("ran") is False and bool(out.get("message")),
              str(out))
        async with Session() as s:
            listed = await fantasy_router.list_rounds(str(FS_ID), club=org, db=s, _=None)
        r0 = listed["rounds"][0]
        check("the rounds list says the round is being played and when it was last looked at",
              r0.get("playing") is True and r0.get("live_checked_at") and listed.get("live_sync") is True, str(r0))
        async with Session() as s:
            body = fantasy_router.RulesUpdate(live_sync=False)
            rules = await fantasy_router.update_rules(str(FS_ID), body, club=org, db=s, _=None)
        check("the season switch is saved by the rules route", rules["rules"].get("live_sync") is False)
        async with Session() as s:
            rules = await fantasy_router.update_rules(str(FS_ID), fantasy_router.RulesUpdate(budget=100), club=org, db=s, _=None)
        check("and an update that does not send it leaves it alone", rules["rules"].get("live_sync") is False)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
