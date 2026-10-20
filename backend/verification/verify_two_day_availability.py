"""Verification: a two-day game is answered, shown and selected on BOTH of its
days, against a real Postgres.

Reported (Applecross, Oct 2026): a two-day 1st XI game on 24 and 31 Oct showed
only "Sat 24 Oct" on the selection board, and a player who had said UNAVAILABLE
for week 2 was offered as available, because

  * the fixtures sync read only `matchSchedule[0]` and never wrote `end_on`
    (Cricket Australia sends one entry per day, a week apart, in no reliable
    order), so a synced two-day game had one date; and
  * the pool, the overview and the next-round carry read availability on
    `played_on` alone.

Drives the SHIPPED code: `grassroots_scores_client.get_grade_fixtures`, the
`POST /fixtures/sync` route body, `upcoming_fixtures_by_date`,
`assemble_selection`, `selection_overview`, the two-weekend clash rules and
the public `GET/POST /public/availability/{token}/me`.

CONTROL MODE: against the commit before this change every "both days" check
FAILS (new keys are read with `.get`, new modules are imported guarded) rather
than crashing. Each "absent" check is paired with one that proves it could be
present (a one-day game stays one day; a fully available player stays available).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_two_day_availability.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import re
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, Organisation, User, Player, Team, Grade, Season, Fixture, PlayerAvailability,
)
from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

MAIN = Path(__file__).resolve().parent.parent / "app/main.py"
DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
LAST_DETAIL: list = [None]
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


def _create_stmt(table):
    m = re.search(r"(CREATE TABLE IF NOT EXISTS " + table + r" \([\s\S]*?\n\s*\))", MAIN.read_text())
    return m.group(1) if m else None


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Harness tables the confirm path reads (copied from the lifespan, as in
        # verify_selection_same_day.py).
        for ddl in (
            """CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS import_effective_deltas (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id uuid, player_id uuid, season_id uuid,
                scope text, grade_label text, matches int, batting_innings int, runs int,
                not_outs int, balls_faced int, fifties int, hundreds int,
                ducks int, high_score int, is_hs_not_out boolean,
                fours int, sixes int, batting_minutes int,
                bowling_innings int, wickets int, overs numeric,
                bowling_balls int, runs_conceded int, maidens int,
                best_bowling_wickets int, best_bowling_figures text,
                five_wicket_innings int, wides int, no_balls int,
                catches int, catches_wk int, catches_non_wk int,
                run_outs int, assisted_run_outs int, unassisted_run_outs int,
                stumpings int)""",
        ):
            await conn.execute(text(ddl))
        from app.services.competition_ddl import STATEMENTS as COMP_DDL
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        try:
            from app.services.junior_hiding_ddl import STATEMENTS as JUNIOR_DDL
            for stmt in JUNIOR_DDL:
                await conn.execute(text(stmt))
        except ImportError:
            pass
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for t in ("net_sessions", "net_attendance"):
            stmt = _create_stmt(t)
            if stmt:
                await conn.execute(text(stmt))
        for stmt in SELECTION_RULE_STATEMENTS:
            await conn.execute(text(stmt))
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))
        try:
            ddl = importlib.import_module("app.services.selection_draft_ddl")
            for stmt in ddl.STATEMENTS:
                await conn.execute(text(stmt))
        except ImportError:
            pass
        try:
            ddl = importlib.import_module("app.services.selection_lock_ddl")
            for stmt in ddl.STATEMENTS:
                await conn.execute(text(stmt))
        except ImportError:
            pass
        try:
            ddl = importlib.import_module("app.services.audit_ddl")
            for stmt in ddl.STATEMENTS:
                await conn.execute(text(stmt))
        except (ImportError, AttributeError):
            pass
        try:
            ddl = importlib.import_module("app.services.team_sides_ddl")
            for stmt in ddl.STATEMENTS:
                await conn.execute(text(stmt))
        except ImportError:
            pass




async def main():
    await build_schema()
    import app.routers.selection as sel
    import app.routers.availability as av
    import app.routers.fixtures as fxr
    import app.routers.public_availability as pa
    import app.services.grassroots_scores_client as gr
    from app.services.selection_pool import assemble_selection

    org, season, g1, t1, user_id = (uuid.uuid4() for _ in range(5))
    g2, t2 = uuid.uuid4(), uuid.uuid4()
    TD, OD, FB, OW2, TDP, ODP = (uuid.uuid4() for _ in range(6))
    jack, ann, bob, cal = (uuid.uuid4() for _ in range(4))
    wk1 = date.today() + timedelta(days=10)
    wk2 = wk1 + timedelta(days=7)
    wk3 = wk1 + timedelta(days=14)
    token = "tok-" + uuid.uuid4().hex

    async with Session() as db:
        db.add(Organisation(id=org, name="TwoDay CC", slug=f"td-{org.hex[:8]}", module_overrides=["select"],
                            availability_link_token=token, availability_self_service_enabled=True))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:6]}@x.com", password_hash="x"))
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g1, season_id=season, name="1st Grade"))
        await db.flush()
        db.add(Grade(id=g2, season_id=season, name="2nd Grade"))
        await db.flush()
        db.add(Team(id=t1, organisation_id=org, name="1st XI", sequence=1, grade_id=g1))
        db.add(Team(id=t2, organisation_id=org, name="2nd XI", sequence=2, grade_id=g2))
        await db.flush()
        for pid, nm in ((jack, "Jack"), (ann, "Ann"), (bob, "Bob"), (cal, "Cal")):
            db.add(Player(id=pid, organisation_id=org, name=nm, gender="male", is_player=True, status="active"))
        await db.flush()
        db.add(Fixture(id=TD, organisation_id=org, grade_id=g1, team_id=t1, source="manual", status="UPCOMING",
                       played_on=wk1, end_on=wk2, start_time="12:30", opponent_name="Kalamunda", label="Round 3"))
        # A one-day 2nd XI game on the two-day game's SECOND weekend.
        db.add(Fixture(id=OW2, organisation_id=org, grade_id=g2, team_id=t2, source="manual", status="UPCOMING",
                       played_on=wk2, start_time="12:30", opponent_name="Joondalup", label="Round 4"))
        # A two-day game already under way (week 1 gone, week 2 tomorrow) and a past one-day game.
        db.add(Fixture(id=TDP, organisation_id=org, grade_id=g1, team_id=t1, source="manual", status="UPCOMING",
                       played_on=date.today() - timedelta(days=6), end_on=date.today() + timedelta(days=1),
                       start_time="12:30", opponent_name="Swan Districts", label="Round 2"))
        db.add(Fixture(id=ODP, organisation_id=org, grade_id=g2, team_id=t2, source="manual", status="UPCOMING",
                       played_on=date.today() - timedelta(days=1), start_time="12:30", opponent_name="Past", label="Round 1"))
        db.add(Fixture(id=OD, organisation_id=org, grade_id=g1, team_id=t1, source="manual", status="UPCOMING",
                       played_on=wk3, start_time="12:30", opponent_name="Wanneroo", label="Round 5"))
        # Jack: free week 1, away week 2. Ann: free both. Bob: free week 1, no answer week 2.
        # Cal: maybe week 2 only.
        for pid, d, st in ((jack, wk1, "AVAILABLE"), (jack, wk2, "UNAVAILABLE"),
                           (ann, wk1, "AVAILABLE"), (ann, wk2, "AVAILABLE"),
                           (bob, wk1, "AVAILABLE"), (cal, wk2, "MAYBE")):
            db.add(PlayerAvailability(organisation_id=org, player_id=pid, avail_date=d, status=st))
        await db.commit()

    print("\n# A. The date builder offers both weeks, labelled")
    async with Session() as db:
        by = await av.upcoming_fixtures_by_date(db, org)
    f1 = [f for f in by.get(wk1.isoformat(), []) if f["id"] == str(TD)]
    f2 = [f for f in by.get(wk2.isoformat(), []) if f["id"] == str(TD)]
    check("week 1 date lists the game as day 1", [f.get("role") for f in f1], ["day1"])
    check("week 2 date lists the game as day 2", [f.get("role") for f in f2], ["day2"])
    check("each entry names both days", (f1 and f1[0].get("day1"), f1 and f1[0].get("day2")), (wk1.isoformat(), wk2.isoformat()))
    one = [f for f in by.get(wk3.isoformat(), []) if f["id"] == str(OD)]
    check("control: a one-day game stays a single date", [f.get("role") for f in one], ["single"])
    check("control: a one-day game carries no day1/day2", (one[0].get("day1"), one[0].get("day2")), (None, None))

    print("\n# B. Week 1 under way: week 2 is still on offer")
    start = datetime.combine(wk1, datetime.min.time()).replace(hour=14)   # after the 12:30 start
    async with Session() as db:
        by = await av.upcoming_fixtures_by_date(db, org, now_local=start)
    check("week 1 has started, so it leaves", wk1.isoformat() in by, False)
    check("week 2 is still answerable", wk2.isoformat() in by, True)
    mid = datetime.combine(wk2, datetime.min.time()).replace(hour=9)      # morning of week 2, before the start
    async with Session() as db:
        by = await av.upcoming_fixtures_by_date(db, org, now_local=mid)
    check("the morning of week 2 it is still offered", wk2.isoformat() in by, True)
    late = datetime.combine(wk2, datetime.min.time()).replace(hour=15)
    async with Session() as db:
        by = await av.upcoming_fixtures_by_date(db, org, now_local=late)
    check("once week 2 has started it leaves", wk2.isoformat() in by, False)

    print("\n# C. The selection pool reads both days")
    async with Session() as db:
        club = await db.get(Organisation, org)
        two = await assemble_selection(db, club, await db.get(Fixture, TD))
        odn = await assemble_selection(db, club, await db.get(Fixture, OD))
    pool = {p["display_name"]: p for p in two["pool"]}
    check("Jack (free wk 1, away wk 2) is UNAVAILABLE for the game", pool["Jack"]["availability"], "UNAVAILABLE")
    check("Jack's two weeks are listed", [d.get("status") for d in (pool["Jack"].get("availability_days") or [])],
          ["AVAILABLE", "UNAVAILABLE"])
    check("...against the right dates", [d.get("date") for d in (pool["Jack"].get("availability_days") or [])],
          [wk1.isoformat(), wk2.isoformat()])
    check("control: Ann (free both weeks) is AVAILABLE", pool["Ann"]["availability"], "AVAILABLE")
    check("Bob (free wk 1, nothing for wk 2) is not offered as available", pool["Bob"]["availability"], "NO_RESPONSE")
    check("Cal (maybe wk 2, nothing wk 1) reads NO_RESPONSE, the less favourable of the two", pool["Cal"]["availability"], "NO_RESPONSE")
    check("a player with no answers at all has both weeks listed", len(pool["Jack"].get("availability_days") or []), 2)
    pool1 = {p["display_name"]: p for p in odn["pool"]}
    check("control: the one-day game reads its own date only (nobody answered wk 3)", pool1["Ann"]["availability"], "NO_RESPONSE")
    check("control: a one-day game has no per-week list", pool1["Ann"].get("availability_days"), None)

    print("\n# D. The overview and the board header")
    async with Session() as db:
        club = await db.get(Organisation, org)
        user = await db.get(User, user_id)
        await sel.set_selection(str(TD), sel.LineupSet(players=[
            sel.LineupSlot(player_id=str(p), batting_order=i + 1, is_captain=False, is_wicket_keeper=False)
            for i, p in enumerate((jack, ann))]), db, club, user)
    async with Session() as db:
        club = await db.get(Organisation, org)
        ov = await sel.selection_overview(db=db, club=club)
    row = next(f for f in ov["fixtures"] if f["id"] == str(TD))
    check("overview names the second day", row.get("end_on"), wk2.isoformat())
    avail = {p["display_name"]: p["availability"] for p in row["lineup"]}
    check("overview shows Jack as UNAVAILABLE (week 2)", avail.get("Jack"), "UNAVAILABLE")
    check("control: overview shows Ann as AVAILABLE", avail.get("Ann"), "AVAILABLE")
    row1 = next(f for f in ov["fixtures"] if f["id"] == str(OD))
    check("control: a one-day game has no end_on", row1.get("end_on"), None)

    print("\n# E. The two weekends are linked: a two-day pick is busy for one-day sides in week 2")
    async with Session() as db:
        club = await db.get(Organisation, org)
        ow2 = await assemble_selection(db, club, await db.get(Fixture, OW2))
        od3 = await assemble_selection(db, club, await db.get(Fixture, OD))
    p2 = {p["display_name"]: p for p in ow2["pool"]}
    check("Ann (in the two-day 1st XI) shows as picked elsewhere on week 2's one-day side", p2["Ann"].get("clash"), ["1st XI"])
    check("...and the lower side cannot take her", p2["Ann"].get("clash_blocks"), True)
    check("control: Bob (picked nowhere) has no clash", p2["Bob"].get("clash"), [])
    check("control: a one-day side on a third weekend is not affected", {p["display_name"]: p for p in od3["pool"]}["Ann"].get("clash"), [])
    try:
        async with Session() as db:
            club = await db.get(Organisation, org); user = await db.get(User, user_id)
            await sel.set_selection(str(OW2), sel.LineupSet(players=[
                sel.LineupSlot(player_id=str(ann), batting_order=1, is_captain=False, is_wicket_keeper=False)]), db, club, user)
        refused = None
    except HTTPException as e:
        refused = e.status_code
    check("saving her into the week 2 one-day side is refused (409)", refused, 409)
    async with Session() as db:
        club = await db.get(Organisation, org); user = await db.get(User, user_id)
        await sel.set_selection(str(OW2), sel.LineupSet(players=[
            sel.LineupSlot(player_id=str(bob), batting_order=1, is_captain=False, is_wicket_keeper=False)]), db, club, user)
        td = await assemble_selection(db, club, await db.get(Fixture, TD))
    pt = {p["display_name"]: p for p in td["pool"]}
    check("the other way round: the two-day pool shows Bob as picked in the week 2 side", pt["Bob"].get("clash"), ["2nd XI"])
    check("...as a call-up (the higher side may take him)", pt["Bob"].get("clash_blocks"), False)
    async with Session() as db:
        club = await db.get(Organisation, org); user = await db.get(User, user_id)
        await sel.set_selection(str(TD), sel.LineupSet(players=[
            sel.LineupSlot(player_id=str(p), batting_order=i + 1, is_captain=False, is_wicket_keeper=False)
            for i, p in enumerate((jack, ann, bob))]), db, club, user)
    left = await _rows("SELECT count(*) FROM fixture_lineups WHERE fixture_id=:f AND player_id=:p", f=OW2, p=bob)
    check("calling Bob up to the two-day side takes him out of the week 2 side", left[0][0], 0)
    # An unconfirmed draft for the two-day game is flagged on the week 2 side, never blocking.
    async with Session() as db:
        club = await db.get(Organisation, org); user = await db.get(User, user_id)
        try:
            await sel.save_draft(str(TD), sel.DraftSet(slots=[str(cal)], base_version=0), db=db, club=club, user=user)
        except Exception:
            pass
        ow2 = await assemble_selection(db, club, await db.get(Fixture, OW2))
    check("a player in the two-day draft is flagged on the week 2 side", {p["display_name"]: p for p in ow2["pool"]}["Cal"].get("in_draft_of"), ["1st XI"])

    print("\n# E2. A two-day game under way stays on the board until week 2 is over")
    async with Session() as db:
        club = await db.get(Organisation, org)
        ov = await sel.selection_overview(db=db, club=club)
    ids_on_board = {f["id"] for f in ov["fixtures"]}
    check("the game with week 1 gone and week 2 tomorrow is still listed", str(TDP) in ids_on_board, True)
    check("control: a one-day game that has been played is not", str(ODP) in ids_on_board, False)

    print("\n# E3. Nobody is taken out of a carried draft for being unavailable")
    import app.services.selection_seed as seed2
    check("the removal helpers are gone", (hasattr(seed2, "without_unavailable"), hasattr(seed2, "unavailable_ids")), (False, False))

    print("\n# F. The public page and a player's own answer for week 2")
    from jose import jwt as jose_jwt
    from starlette.requests import Request
    from app.config.settings import settings

    def req_for(pid):
        c = jose_jwt.encode({"club": str(org), "pid": str(pid), "typ": "avail",
                             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                            settings.secret_key, algorithm=settings.algorithm)
        return Request({"type": "http", "headers": [(b"cookie", f"{pa.COOKIE_NAME}={c}".encode())]})

    async with Session() as db:
        me = await pa.get_me(token, req_for(jack), None, db)
    dates = {d["date"]: d for d in me["dates"]}
    check("self-service lists both weeks", wk1.isoformat() in dates and wk2.isoformat() in dates, True)
    fx2 = (dates.get(wk2.isoformat()) or {"fixtures": [{}]})["fixtures"][0]
    check("week 2 is tagged day 2 and names day 1", (fx2.get("role"), fx2.get("day1")), ("day2", wk1.isoformat()))
    check("Jack's answers come back per date",
          (me["availability"].get(wk1.isoformat()) or {}).get("status"), "AVAILABLE")
    check("...and week 2", (me["availability"].get(wk2.isoformat()) or {}).get("status"), "UNAVAILABLE")
    check("no internal ids leak to the page", all("team_id" not in f and "grade_id" not in f
                                                 for d in me["dates"] for f in d["fixtures"]), True)
    async with Session() as db:
        r = await pa.set_me(token, pa.SetBody(date=wk2, status="AVAILABLE"), req_for(bob), db)
    check("a player can answer week 2", r.get("status"), "ok")
    async with Session() as db:
        st = (await db.execute(text("SELECT status, source FROM player_availability WHERE player_id=:p AND avail_date=:d"),
                               {"p": bob, "d": wk2})).first()
    check("...and it is stored against week 2, as a self answer", tuple(st) if st else None, ("AVAILABLE", "self"))
    async with Session() as db:
        club = await db.get(Organisation, org)
        two = await assemble_selection(db, club, await db.get(Fixture, TD))
    check("Bob is now AVAILABLE for the game (both weeks answered)",
          {p["display_name"]: p["availability"] for p in two["pool"]}["Bob"], "AVAILABLE")

    print("\n# G. Cricket Australia's feed: both days, in any order")
    def match(mid, entries):
        return {"id": mid, "statusId": 0, "matchSchedule": entries,
                "teams": [{"isHome": True, "displayName": "TwoDay CC 1st"}, {"isHome": False, "displayName": "Kalamunda"}],
                "round": {"name": "Round 3"}, "venue": {"name": "Bert Jeffrey Park"}}
    d1, d2 = wk1.isoformat(), wk2.isoformat()
    feed = [
        match("m-two", [{"startDateTime": f"{d2}T12:30:00"}, {"startDateTime": f"{d1}T12:30:00"}]),   # day 2 listed first
        match("m-one", [{"startDateTime": f"{wk3.isoformat()}T12:30:00"}]),
        match("m-bye", []),
    ]
    async def fake_matches(grade_id, force=False):
        return feed
    orig = gr.get_grade_matches
    gr.get_grade_matches = fake_matches
    try:
        got = await gr.get_grade_fixtures("g")
    finally:
        gr.get_grade_matches = orig
    by_id = {f["id"]: f for f in got}
    check("a two-day game is filed under its FIRST day, whatever order the feed lists them", (by_id.get("m-two") or {}).get("played_at"), d1)
    check("...and carries its last day", (by_id.get("m-two") or {}).get("end_at"), d2)
    check("control: a one-day game has no end day", ("m-one" in by_id, (by_id.get("m-one") or {}).get("end_at", "absent")), (True, None))
    check("a bye (no schedule) is left out", "m-bye" in by_id, False)
    # A game whose first day has passed but whose second has not is still upcoming.
    y = (date.today() - timedelta(days=3)).isoformat()
    t = (date.today() + timedelta(days=4)).isoformat()
    feed[:] = [match("m-mid", [{"startDateTime": f"{y}T12:30:00"}, {"startDateTime": f"{t}T12:30:00"}]),
               match("m-gone", [{"startDateTime": f"{y}T12:30:00"}])]
    gr.get_grade_matches = fake_matches
    try:
        got = await gr.get_grade_fixtures("g")
    finally:
        gr.get_grade_matches = orig
    ids = {f["id"] for f in got}
    check("a game between its two days is still listed", "m-mid" in ids, True)
    check("control: a one-day game in the past is not", "m-gone" in ids, False)

    print("\n# H. The sync writes the second day")
    async def fake_checked(db, club, hidden=(), *, force=False, discover_live=False):
        games = [
            {"id": "sync-two", "played_at": d1, "end_at": d2, "time": "12:30", "status": "UPCOMING",
             "home_team": "TwoDay CC 1st", "away_team": "Kalamunda", "round": "Round 3", "venue": "Park",
             "db_grade_id": str(g1), "grade_name": "1st Grade"},
            {"id": "sync-one", "played_at": wk3.isoformat(), "time": "12:30", "status": "UPCOMING",
             "home_team": "TwoDay CC 1st", "away_team": "Wanneroo", "round": "Round 5", "venue": "Park",
             "db_grade_id": str(g1), "grade_name": "1st Grade"},
        ]
        return games, {"grades": {}, "failed": 0, "others": set()}
    orig_chk = fxr.org_grassroots_fixtures_checked
    fxr.org_grassroots_fixtures_checked = fake_checked
    try:
        async with Session() as db:
            club = await db.get(Organisation, org)
            res = await fxr.sync_fixtures(db=db, club=club, _user=None)
    finally:
        fxr.org_grassroots_fixtures_checked = orig_chk
    check("sync ran", bool(res.get("synced")), True)
    rows = {r[0]: r for r in (await _rows("SELECT playhq_id, played_on, end_on FROM fixtures WHERE playhq_id IN ('sync-two','sync-one')"))}
    check("synced two-day game has both dates", (rows.get("sync-two") or (0, None, None))[1:], (wk1, wk2))
    check("control: synced one-day game has no end date", (rows.get("sync-one") or (0, None, "absent"))[2], None)
    # An end date a person typed on a synced one-day entry survives the next sync.
    await _exec("UPDATE fixtures SET end_on = :e WHERE playhq_id = 'sync-one'", e=wk3 + timedelta(days=7))
    fxr.org_grassroots_fixtures_checked = fake_checked
    try:
        async with Session() as db:
            club = await db.get(Organisation, org)
            await fxr.sync_fixtures(db=db, club=club, _user=None)
    finally:
        fxr.org_grassroots_fixtures_checked = orig_chk
    rows = {r[0]: r for r in (await _rows("SELECT playhq_id, played_on, end_on FROM fixtures WHERE playhq_id IN ('sync-two','sync-one')"))}
    check("a hand-typed end date is not wiped by the next sync", (rows.get("sync-one") or (0, 0, None))[2], wk3 + timedelta(days=7))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAIL:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


async def _rows(sql, **kw):
    async with Session() as db:
        return (await db.execute(text(sql), kw)).all()


async def _exec(sql, **kw):
    async with Session() as db:
        await db.execute(text(sql), kw)
        await db.commit()


asyncio.run(main())
