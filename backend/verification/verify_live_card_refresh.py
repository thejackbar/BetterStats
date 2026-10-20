"""A game stored while Cricket Australia still had it LIVE keeps its mid-game figures, and Fantasy scores them.

Reported off Leederville CC (Oct 2026): after the weekend one player who scored 40 odd read 1 Fantasy
point and one who took 4 wickets read 24, while the club's own scorecard on PlayCricket had the right
figures. The aggregate (season totals) feed is right, so the profile and milestones agree with
PlayCricket; Fantasy reads the stored per-innings rows, and those were written from a card read in play.

Why they stay short. `sync_grassroots_game_level_data` stores a game's batting, bowling and fielding rows
when it first reads the card, whatever CA's status. A later read of the same game takes the
`our_appearances_done` branch, and `participant_relink.reread_stored_game` only ADDS a row that is not
there: a figure that was 1* in play is never replaced by the 43 it finished on. A two-day game (played
over two Saturdays, dated on the first) is read by Sunday 01:00 while still in play, is inside Monday's
window, and is outside every window after that.

Drives the real sync (`sync_grassroots_game_level_data`) with the Cricket Australia client stubbed, then
the shipped Fantasy scorer (`fantasy_engine._round_player_scores`) over the same database.

Run, on its own database:
  DATABASE_URL=postgresql+asyncpg://postgres:pw@localhost:5432/verify_live_card python verification/verify_live_card_refresh.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.services import fantasy_engine, grassroots_scores_client as gr
from app.services.sync import sync_grassroots_game_level_data

try:
    from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS
except ImportError:  # pragma: no cover
    COMP_STATEMENTS = []

# Presence-safe: the control run (the commit before the fix) has no such module and must still run.
try:
    from app.services import card_figures_refresh
except ImportError:  # pragma: no cover - control run only
    card_figures_refresh = None

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


TODAY = date.today()
ORG, OPP_ORG = uuid.uuid4(), uuid.uuid4()
SEASON, GRADE_GUID = uuid.uuid4(), str(uuid.uuid4())
GRADE = uuid.UUID(GRADE_GUID)
SUSH, SHUB, MATE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
G_IN = uuid.uuid4()        # played 2 days ago: inside every window
G_OUT = uuid.uuid4()       # played 8 days ago (a two-day game's first day): outside the next windows
G_DONE = uuid.uuid4()      # stored COMPLETED with figures that already match the card
G_OLD = uuid.uuid4()       # stored short, but 40 days old: not touched
DAYS = {G_IN: 2, G_OUT: 8, G_DONE: 3, G_OLD: 40}


def card(match_id, days_ago, status, *, sush, shub_bat, shub_bowl, mate_catches):
    """A scorecard. `sush` = (runs, balls, fours, sixes, dismissalTypeId, dismissalType)."""
    iso = (TODAY - timedelta(days=days_ago)).isoformat() + "T10:00:00Z"
    ours, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    s_runs, s_balls, s_4, s_6, s_id, s_dt = sush
    batting = [{"participantId": str(SUSH), "dismissalTypeId": s_id, "dismissalType": s_dt,
                "runsScored": s_runs, "ballsFaced": s_balls, "foursScored": s_4, "sixesScored": s_6, "batOrder": 3}]
    if shub_bat is not None:
        batting.append({"participantId": str(SHUB), "dismissalTypeId": 3, "dismissalType": "Caught",
                        "runsScored": shub_bat, "ballsFaced": 14, "foursScored": 1, "sixesScored": 0, "batOrder": 9})
    overs, maidens, runs, wkts = shub_bowl
    bowling = [{"participantId": str(SHUB), "oversBowled": overs, "maidensBowled": maidens,
                "runsConceded": runs, "wicketsTaken": wkts, "wideBalls": 0, "noBalls": 0, "economy": 4.0}]
    fielding = [{"participantId": str(MATE), "playerShortName": "M Mate", "totalCatches": mate_catches,
                 "wicketKeeperCatches": 0, "runOuts": 0, "stumpings": 0}] if mate_catches else []
    return {
        "id": str(match_id), "status": status,
        "matchSchedule": [{"startDateTime": iso}],
        "venue": {"name": "Oval"},
        "grade": {"id": GRADE_GUID, "name": "1st Grade"},
        "teams": [
            {"id": ours, "displayName": "LCC 1st", "owningOrganisation": {"id": str(ORG)},
             "players": [{"participantId": str(p), "roles": []} for p in (SUSH, SHUB, MATE)]},
            {"id": theirs, "displayName": "Them 1st", "owningOrganisation": {"id": str(OPP_ORG)}, "players": []},
        ],
        "matchSummary": {"resultText": "LCC won",
                         "teams": [{"id": ours, "displayName": "LCC 1st", "isHome": True},
                                   {"id": theirs, "displayName": "Them 1st", "isHome": False}]},
        "innings": [
            {"inningsOrder": 1, "battingTeamId": ours, "batting": batting, "bowling": [], "fielding": [],
             "fallOfWickets": []},
            {"inningsOrder": 2, "battingTeamId": theirs, "batting": [], "bowling": bowling, "fielding": fielding,
             # A fall of wickets row, as every real card has one: otherwise `recent_games_without_detail`
             # picks the game up for having none, which would hide the very gap under test.
             "fallOfWickets": [{"order": 1, "runs": 20, "participantId": str(uuid.uuid4()),
                                "playerShortName": "T Opp"}]},
        ],
    }


def live_card(mid, days):    # in play: Sushruth 1 not out, Shubham 2 overs for 1, one catch
    return card(mid, days, "LIVE", sush=(1, 3, 0, 0, 1, "Not Out"), shub_bat=None,
                shub_bowl=(2.0, 0, 9, 1), mate_catches=1)


def final_card(mid, days):   # finished: Sushruth 43, Shubham 12 and 4 wickets, three catches
    return card(mid, days, "COMPLETED", sush=(43, 40, 5, 1, 2, "Bowled"), shub_bat=12,
                shub_bowl=(8.0, 1, 31, 4), mate_catches=3)


def entry(mid, days, status):
    iso = (TODAY - timedelta(days=days)).isoformat() + "T10:00:00Z"
    return {"id": str(mid), "matchSchedule": [{"startDateTime": iso}], "status": status,
            "matchType": "Two Day", "round": {"name": "Round 3"},
            "teams": [{"id": str(uuid.uuid4()), "owningOrganisation": {"id": str(ORG)}},
                      {"id": str(uuid.uuid4()), "owningOrganisation": {"id": str(OPP_ORG), "name": "Them"}}]}


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons BOOLEAN NOT NULL DEFAULT false"))
        for stmt in COMP_STATEMENTS:
            await conn.execute(text(stmt))
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
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for oid, nm, slug in ((ORG, "Leederville", "lcc"), (OPP_ORG, "Them CC", "them")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)",
                     i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) "
                 "VALUES (:i, :o, 'Summer', :y, :g)", i=SEASON, o=ORG, y=TODAY.year, g=str(SEASON))
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, '1st Grade', :g, 'senior', ARRAY['senior'])", i=GRADE, s=SEASON, g=GRADE_GUID)
        for pid, nm in ((SUSH, "Menon, Sushruth"), (SHUB, "Shubham"), (MATE, "Mate, Mick")):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))

        # G_DONE: stored from a finished card and already right (the common case).
        # G_OLD: stored short but 40 days old (outside the 14 day window).
        for mid, days in ((G_DONE, 3), (G_OLD, 40)):
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, status, venue, match_format) "
                     "VALUES (:i, :g, :d, 'WIN', :o, 'COMPLETED', 'Oval', 'Two Day')",
                     i=mid, g=GRADE, d=TODAY - timedelta(days=days), o=ORG)
            for p in (SUSH, SHUB, MATE):
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=mid, p=p)
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, "
                 " not_out, dismissal_type, did_not_bat, batting_position) "
                 "VALUES (:g, :p, 1, 43, 40, 5, 1, false, 'bowled', false, 3)", g=G_DONE, p=SUSH)
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, "
                 " not_out, dismissal_type, did_not_bat, batting_position) "
                 "VALUES (:g, :p, 1, 1, 3, 0, 0, true, 'not out', false, 3)", g=G_OLD, p=SUSH)
        await s.commit()


async def runs_of(game_id, player, innings=1):
    async with Session() as s:
        return (await s.execute(text(
            "SELECT runs FROM batting_innings WHERE game_id = :g AND player_id = :p AND innings_number = :i"),
            {"g": game_id, "p": player, "i": innings})).scalar()


async def batting_row(game_id, player, innings=1):
    async with Session() as s:
        return (await s.execute(text(
            "SELECT id, runs, balls, fours, sixes, not_out, dismissal_type FROM batting_innings "
            "WHERE game_id = :g AND player_id = :p AND innings_number = :i"),
            {"g": game_id, "p": player, "i": innings})).mappings().first()


async def wickets_of(game_id, player):
    async with Session() as s:
        return (await s.execute(text(
            "SELECT wickets, maidens, runs FROM bowling_spells WHERE game_id = :g AND player_id = :p"),
            {"g": game_id, "p": player})).first()


async def catches_of(game_id, player):
    async with Session() as s:
        return (await s.execute(text(
            "SELECT COALESCE(SUM(catches), 0), COUNT(*) FROM fielding_stats WHERE game_id = :g AND player_id = :p"),
            {"g": game_id, "p": player})).first()


async def fantasy_points(start, end):
    """The shipped Fantasy scorer over this database, for a round spanning start..end."""
    fs = SimpleNamespace(id=uuid.uuid4(), organisation_id=ORG, season_year=TODAY.year, included_grade_ids=None,
                         rules={}, scoring=None)
    rnd = SimpleNamespace(start_date=start, end_date=end)
    async with Session() as s:
        got = await fantasy_engine._round_player_scores(s, fs, rnd)
    return {k: v["total"] for k, v in got.items()}


async def main() -> None:
    await build_schema()
    await seed()

    cards: dict[str, dict] = {}
    statuses: dict[str, str] = {}
    fetched: list[str] = []

    async def fake_matches(grade_guid, *a, **k):
        return [entry(m, DAYS_ALL[m], statuses[str(m)]) for m in DAYS_ALL if str(m) in statuses]

    async def fake_card(match_id, *a, **k):
        fetched.append(str(match_id))
        return cards.get(str(match_id))

    gr.get_grade_matches = fake_matches
    gr.get_match_scorecard = fake_card
    DAYS_ALL = dict(DAYS)

    print("\n-- RUN 1: both games are read while CA has them LIVE (the Sunday 01:00 sync) --")
    for m in (G_IN, G_OUT):
        cards[str(m)] = live_card(m, DAYS[m])
        statuses[str(m)] = "LIVE"
    # The two seeded games are in the list too, already finished.
    for m in (G_DONE, G_OLD):
        cards[str(m)] = final_card(m, DAYS[m])
        statuses[str(m)] = "COMPLETED"
    await sync_grassroots_game_level_data(str(ORG), since=TODAY - timedelta(days=10))
    check("the game is stored from the card read in play: Sushruth 1", await runs_of(G_IN, SUSH) == 1,
          str(await runs_of(G_IN, SUSH)))
    check("and Shubham 1 wicket", (await wickets_of(G_IN, SHUB) or (None,))[0] == 1)
    pts = await fantasy_points(TODAY - timedelta(days=2), TODAY - timedelta(days=2))
    check("Fantasy scores what was stored: Sushruth on 5 (1 run and the 4 for playing)",
          abs(pts.get(str(SUSH), -1) - 5) < 1e-6, str(pts.get(str(SUSH))))

    print("\n-- RUN 2: CA now calls both COMPLETED. G_IN is inside the window; G_OUT (8 days old) is not --")
    for m in (G_IN, G_OUT):
        cards[str(m)] = final_card(m, DAYS[m])
        statuses[str(m)] = "COMPLETED"
    fetched.clear()
    await sync_grassroots_game_level_data(str(ORG), since=TODAY - timedelta(days=3))
    check("the in-window game was read", str(G_IN) in fetched, str(fetched))
    check("Sushruth's 43 replaces the 1* (in-window game)", await runs_of(G_IN, SUSH) == 43,
          str(await runs_of(G_IN, SUSH)))
    check("and he is no longer 'not out'", (await batting_row(G_IN, SUSH) or {}).get("not_out") is False)
    check("Shubham's 4 wickets replace the 1", (await wickets_of(G_IN, SHUB) or (None,))[0] == 4,
          str(await wickets_of(G_IN, SHUB)))
    check("Mate's third catch is there (one row per innings fielded, summed)",
          (await catches_of(G_IN, MATE))[0] == 3, str(await catches_of(G_IN, MATE)))
    check("the out-of-window game was read as well (stored while LIVE, so it is asked about again)",
          str(G_OUT) in fetched, str(fetched))
    check("and its Sushruth is 43", await runs_of(G_OUT, SUSH) == 43, str(await runs_of(G_OUT, SUSH)))
    check("and its Shubham 4 wickets", (await wickets_of(G_OUT, SHUB) or (None,))[0] == 4,
          str(await wickets_of(G_OUT, SHUB)))

    print("\n-- FANTASY now scores the finished card --")
    pts = await fantasy_points(TODAY - timedelta(days=2), TODAY - timedelta(days=2))
    # Sushruth: 43 runs + 5 fours + 2 for the six + 4 for playing = 54.
    check("Sushruth 54", abs(pts.get(str(SUSH), -1) - 54) < 1e-6, str(pts.get(str(SUSH))))
    # Shubham (batter by default, so bowling is off-role x1.5): bat 12 + 1 four = 13; bowl 4x25 + 8 + 8 maiden = 116 x1.5 = 174; +4.
    check("Shubham 191", abs(pts.get(str(SHUB), -1) - 191) < 1e-6, str(pts.get(str(SHUB))))

    print("\n-- NOTHING ELSE MOVES --")
    done = await batting_row(G_DONE, SUSH)
    check("a game whose figures already match keeps its row (same id, not rewritten)",
          done is not None and done["runs"] == 43)
    check("a 40 day old game is left as it was", await runs_of(G_OLD, SUSH) == 1)

    print("\n-- A SECOND RUN CHANGES NOTHING --")
    before = {m: await batting_row(m, SUSH) for m in (G_IN, G_OUT)}
    await sync_grassroots_game_level_data(str(ORG), since=TODAY - timedelta(days=3))
    after = {m: await batting_row(m, SUSH) for m in (G_IN, G_OUT)}
    check("same rows, same ids", before == after)
    check("one row per innings, not duplicated", (await catches_of(G_IN, MATE))[1] == 1, str(await catches_of(G_IN, MATE)))

    print("\n-- A CARD CA STILL CALLS LIVE NEVER OVERWRITES A FINISHED FIGURE --")
    cards[str(G_IN)] = live_card(G_IN, DAYS[G_IN])
    statuses[str(G_IN)] = "LIVE"
    await sync_grassroots_game_level_data(str(ORG), since=TODAY - timedelta(days=3))
    check("Sushruth stays on 43", await runs_of(G_IN, SUSH) == 43, str(await runs_of(G_IN, SUSH)))

    print("\n-- A GAME ALREADY STORED SHORT AND MARKED COMPLETED (the state production is in): the repair --")
    async with Session() as s:
        await s.execute(text("UPDATE batting_innings SET runs = 1, balls = 3, fours = 0, sixes = 0, not_out = true, "
                             "dismissal_type = 'not out' WHERE game_id = :g AND player_id = :p"),
                        {"g": G_IN, "p": SUSH})
        await s.execute(text("UPDATE bowling_spells SET wickets = 1 WHERE game_id = :g AND player_id = :p"),
                        {"g": G_IN, "p": SHUB})
        await s.commit()
    cards[str(G_IN)] = final_card(G_IN, DAYS[G_IN])
    statuses[str(G_IN)] = "COMPLETED"
    if card_figures_refresh is None:
        check("the repair exists (services/card_figures_refresh.py)", False, "module missing")
    else:
        async with Session() as s:
            changes = await card_figures_refresh.plan_game(s, ORG, G_IN, cards[str(G_IN)], lambda g: uuid.UUID(g))
        kinds = {(c["table"], c["field"]) for c in changes}
        check("a dry run lists the stale figures", ("batting_innings", "runs") in kinds
              and ("bowling_spells", "wickets") in kinds, str(sorted(kinds)))
        check("and writes nothing", await runs_of(G_IN, SUSH) == 1)
        async with Session() as s:
            n = await card_figures_refresh.refresh_stored_figures(s, ORG, G_IN, cards[str(G_IN)], lambda g: uuid.UUID(g))
        check("applying puts them right", await runs_of(G_IN, SUSH) == 43
              and (await wickets_of(G_IN, SHUB) or (None,))[0] == 4, str(n))
        async with Session() as s:
            again = await card_figures_refresh.plan_game(s, ORG, G_IN, cards[str(G_IN)], lambda g: uuid.UUID(g))
        check("and a second dry run finds nothing", not again, str(again))
        cards["live"] = live_card(G_IN, DAYS[G_IN])
        async with Session() as s:
            live_changes = await card_figures_refresh.plan_game(s, ORG, G_IN, cards["live"], lambda g: uuid.UUID(g))
        check("a card CA does not call COMPLETED plans nothing", not live_changes, str(live_changes))

    print("\n-- THE REPAIR SCRIPT (app.scripts.refresh_card_figures), end to end --")
    from app.scripts import refresh_card_figures as script
    # Put G_IN back to its in-play figures, and give the card a second innings of fielding for Mate
    # (a two-day game is fielded twice, one row each).
    async with Session() as s:
        await s.execute(text("UPDATE batting_innings SET runs = 1, balls = 3, fours = 0, sixes = 0, not_out = true, "
                             "dismissal_type = 'not out' WHERE game_id = :g AND player_id = :p"), {"g": G_IN, "p": SUSH})
        await s.execute(text("UPDATE bowling_spells SET wickets = 1, overs = 2.0, maidens = 0, runs = 9 "
                             "WHERE game_id = :g AND player_id = :p"), {"g": G_IN, "p": SHUB})
        await s.execute(text("UPDATE fielding_stats SET catches = 1 WHERE game_id = :g AND player_id = :p"),
                        {"g": G_IN, "p": MATE})
        await s.commit()
    two_day = final_card(G_IN, DAYS[G_IN])
    two_day["innings"].append({"inningsOrder": 4, "battingTeamId": "x", "batting": [], "bowling": [], "fallOfWickets": [],
                               "fielding": [{"participantId": str(MATE), "totalCatches": 2, "wicketKeeperCatches": 0,
                                             "runOuts": 0, "stumpings": 0}]})
    cards[str(G_IN)] = two_day
    for m in (G_OUT, G_DONE, G_OLD):
        cards[str(m)] = final_card(m, DAYS[m])
    # CA's cards for the other games are already what is stored, or stale only in G_OUT (fixed above).
    args = SimpleNamespace(days=14, pace=0, max_games=50, list=100)
    async def audited():
        async with Session() as s:
            return (await s.execute(text("SELECT COUNT(*) FROM audit_logs WHERE action = 'refresh_card_figures'"))).scalar()

    changes, seen = await script.plan(str(ORG), args, [50])
    fields = {(c["table"], c["field"], c["op"]) for c in changes}
    check("the plan lists the batting, bowling and fielding figures",
          {("batting_innings", "runs", "update"), ("bowling_spells", "wickets", "update"),
           ("fielding_stats", "catches", "update"), ("fielding_stats", "row", "insert")} <= fields, str(sorted(fields)))
    check("it read the 14 day games only (the 40 day old one was not asked for)", seen["read"] == 3, str(seen))
    check("a dry run writes nothing", await runs_of(G_IN, SUSH) == 1 and await audited() == 0)
    try:
        await script.apply(str(ORG), changes, len(changes) + 1, "tester")
        refused = False
    except SystemExit:
        refused = True
    check("--apply with the wrong --expect is refused and writes nothing", refused and await runs_of(G_IN, SUSH) == 1)
    try:
        await script.apply(str(ORG), changes, len(changes), None)
        refused = False
    except SystemExit:
        refused = True
    check("--apply without --by is refused", refused and await runs_of(G_IN, SUSH) == 1)
    await script.apply(str(ORG), changes, len(changes), "tester")
    check("applied: Sushruth 43, Shubham 4 wickets, Mate 5 catches over two rows",
          await runs_of(G_IN, SUSH) == 43 and (await wickets_of(G_IN, SHUB) or (None,))[0] == 4
          and tuple(await catches_of(G_IN, MATE)) == (5, 2), str(await catches_of(G_IN, MATE)))
    check("one audit entry holds every change", await audited() == 1)
    changes2, _ = await script.plan(str(ORG), args, [50])
    check("a second dry run finds nothing", not changes2, str(changes2))
    async with Session() as s:
        audit_id = (await s.execute(text("SELECT id FROM audit_logs WHERE action = 'refresh_card_figures'"))).scalar()
    await script.restore(audit_id, "tester")
    check("--restore puts the in-play figures back and takes out the row it added",
          await runs_of(G_IN, SUSH) == 1 and (await wickets_of(G_IN, SHUB) or (None,))[0] == 1
          and tuple(await catches_of(G_IN, MATE)) == (1, 1), str(await catches_of(G_IN, MATE)))
    try:
        await script.restore(audit_id, "tester")
        twice = False
    except SystemExit:
        twice = True
    check("an entry restores once", twice)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
