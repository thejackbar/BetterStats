"""A fixture CA called off but left COMPLETED must not count for a player who only turned up on the sheet.

Reported off Leederville CC, 2020/21: about twenty players read one match over PlayCricket, all from the
one date 14 Nov 2020. Six games across six grades, each "Match drawn" with status COMPLETED, where both
teams' `matchSummary.teams[].resultType` is ABANDONED. CA leaves a named-only player out of those. Nothing
on our row said so: `result` is NULL (sync maps ABANDONED to no result), `status` reads COMPLETED and the
opposition scored 19 to 22 overs, so neither the status rule nor the empty-scorecard rule fired. The season
table read CA's total (right); the profile header is raised to the by-grade grid, which counted the
games we hold, and read one over.

`games.ca_called_off` carries the call, read from the scorecard (`game_status.card_called_off`), written by
the sync and by `app.scripts.backfill_ca_called_off`. This suite reads every figure through the shipped
route bodies with the production views, against a real Postgres, first with the column unread (NULL: the
control, which must show the reported numbers) and then once the backfill has read the games.

  BISSETT   5 real games and a named-only call-off game; CA's total left it out (5)    -> 5, was 6 on the header
  CACOUNT   the same, but CA's total counted it (6)                                      -> 5, once
  HASROW    batted in the call-off game: they played                                     -> keeps it (4)
  DRAWN     named-only in a genuine draw (resultType DREW): CA counts it                  -> keeps it (4)
  NOCARD    named-only in a game CA returns no card for: nothing can be said              -> unchanged (4)

Run against the previous commit this file is the control: the column is added by hand so the data is the
same, the old code ignores it, and the figures stay at the reported ones.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \\
  python verification/verify_called_off_games.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from verify_board_games_match_profile import build_schema
from app.routers.leaderboard import batting_leaderboard
from app.routers.players import get_player_stats
from app.services import grassroots_scores_client as gr
from app.services import game_status, superseded_ddl
from app.services.aggregations import get_player_team_breakdown, get_season_by_season

# Presence-safe: against the previous commit these do not exist, and a control that crashes is not one.
try:
    from app.scripts import backfill_ca_called_off as backfill
except ImportError:
    backfill = None
card_called_off = getattr(game_status, "card_called_off", None)
appearance_counts_as_match = game_status.appearance_counts_as_match

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


ORG, OPP = uuid.uuid4(), uuid.uuid4()
SEASON, GRADE = uuid.uuid4(), uuid.uuid4()
P = {k: uuid.uuid4() for k in ("BISSETT", "CACOUNT", "HASROW", "DRAWN", "NOCARD")}
NAMES = {"BISSETT": "Bissett, Wilbur", "CACOUNT": "Counted, Carl", "HASROW": "Hasrow, Hugh",
         "DRAWN": "Drawn, Dan", "NOCARD": "Nocard, Ned"}
CARDS: dict[uuid.UUID, dict | None] = {}
FETCHES: list[str] = []
G: dict[str, uuid.UUID] = {}
_day = 0


async def _stub(match_id: str, *, force: bool = False):
    FETCHES.append(match_id)
    return CARDS.get(uuid.UUID(match_id))


gr.get_match_scorecard = _stub


def summary_card(types: list[str], status: str = "COMPLETED") -> dict:
    return {"status": status, "matchSummary": {"teams": [{"id": str(uuid.uuid4()), "resultType": t} for t in types]}}


async def seed() -> None:
    global _day
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug in ((ORG, "Called Off Club", "calledoff"), (OPP, "Opposition CC", "opp")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2020/21', 2020)", i=SEASON, o=ORG)
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, 'D Grade', :g, 'senior', ARRAY['senior'])", i=GRADE, s=SEASON, g=str(GRADE))
        for k, pid in P.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=pid, o=ORG, n=NAMES[k], g=str(pid))

        async def game(result="WIN") -> uuid.UUID:
            global _day
            _day += 7
            gid = uuid.uuid4()
            # The opposition scored: play happened, so the empty-scorecard rule cannot call this unplayed.
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status, innings_totals) "
                     "VALUES (:i, :g, :d, :r, :o, :x, 'One Day', 'COMPLETED', "
                     " jsonb_build_array(jsonb_build_object('runs_scored', 120, 'wickets', 6)))",
                     i=gid, g=GRADE, d=date(2020, 10, 3) + timedelta(days=_day), r=result, o=ORG, x=OPP)
            return gid

        async def real(key, n):
            for _ in range(n):
                gid = await game()
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=P[key])
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, not_out, "
                         " dismissal_type, did_not_bat) VALUES (:g, :p, 1, 20, 25, 1, 0, false, 'caught', false)", g=gid, p=P[key])

        async def named(gid, key):
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=P[key])

        async def ca(key, season_total):
            await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, wickets, "
                     " catches, source) VALUES (:p, :s, :m, 0, 0, 0, 0, 0, 'api')", p=P[key], s=SEASON, m=season_total)
            await ex("INSERT INTO player_season_grade_stats (player_id, season_id, grade_id, matches) VALUES (:p, :s, :g, :m)",
                     p=P[key], s=SEASON, g=GRADE, m=season_total)

        # The call-off game: COMPLETED, "Match drawn", no result, both teams ABANDONED on the card.
        G["CO"] = await game(result=None)
        CARDS[G["CO"]] = summary_card(["ABANDONED", "ABANDONED"])
        # A genuine draw: both teams DREW. CA counts a named-only player here.
        G["DR"] = await game(result="DRAW")
        CARDS[G["DR"]] = summary_card(["DREW", "DREW"])
        # A game CA returns no card for.
        G["NC"] = await game()
        CARDS[G["NC"]] = None

        await real("BISSETT", 5)
        await named(G["CO"], "BISSETT")
        await ca("BISSETT", 5)                       # CA's total left the call-off game out
        await real("CACOUNT", 5)
        await named(G["CO"], "CACOUNT")
        await ca("CACOUNT", 6)                       # CA's total counted it
        await real("HASROW", 3)
        await named(G["CO"], "HASROW")
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, not_out, "
                 " dismissal_type, did_not_bat) VALUES (:g, :p, 1, 7, 12, 0, 0, false, 'bowled', false)", g=G["CO"], p=P["HASROW"])
        await ca("HASROW", 4)
        await real("DRAWN", 3)
        await named(G["DR"], "DRAWN")
        await ca("DRAWN", 4)
        await real("NOCARD", 3)
        await named(G["NC"], "NOCARD")
        await ca("NOCARD", 4)
        await s.commit()


async def header(key) -> int | None:
    async with Session() as s:
        d = await get_player_stats(player_id=str(P[key]), db=s, season_id=None, grade_id=None, last_n_games=None,
                                   start_date=None, end_date=None, categories=None, formats=None, competitions=None, grades=None)
    return (d["career_batting"] or {}).get("games")


async def season_row(key) -> int | None:
    async with Session() as s:
        rows = await get_season_by_season(s, str(P[key]), include_prior=True)
    return next((r["matches"] for r in rows if str(r.get("season_id")) == str(SEASON)), None)


async def grid(key) -> dict:
    async with Session() as s:
        return await get_player_team_breakdown(s, str(P[key]), str(ORG), None)


async def board(key) -> int | None:
    async with Session() as s:
        rows = await batting_leaderboard(db=s, viewer=None, org_id=str(ORG), season_id=None, grade_id=None, grade_name=None,
                                         limit=50, finals_only=None, captain_only=None, gender=None, overseas=None,
                                         categories=None, formats=None, competitions=None, sort_by="total_runs",
                                         min_runs=0, min_rate_innings=0)
    row = next((r for r in rows if str(r["player_id"]) == str(P[key])), None)
    return None if row is None else row.get("games")


async def counts_as_match(key, gid) -> bool:
    async with Session() as s:
        return bool((await s.execute(text(
            f"SELECT {appearance_counts_as_match('ga')} FROM game_appearances ga WHERE ga.game_id = :g AND ga.player_id = :p"),
            {"g": gid, "p": P[key]})).scalar())


async def figures() -> dict:
    return {k: (await header(k), await season_row(k), (await grid(k))["grid_matches"], await board(k)) for k in P}


async def main() -> None:
    await build_schema()
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS ca_called_off BOOLEAN"))   # the control's data
        for stmt in superseded_ddl.STATEMENTS:     # the lifespan re-applies these: production reads THESE views
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL, user_id UUID,
                action TEXT NOT NULL, target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}')"""))
    await seed()

    print("\n-- CONTROL: NOTHING READ YET (ca_called_off NULL), AND THE APP READS WHAT IT READ BEFORE --")
    f0 = await figures()
    check("Bissett: the season table reads CA's 5, the header and the grid read the 6 games held (the reported +1)",
          f0["BISSETT"][1] == 5 and f0["BISSETT"][0] == 6 and f0["BISSETT"][2] == 6, str(f0["BISSETT"]))

    print("\n-- THE RULE, FROM CA'S OWN CARD SHAPES --")
    if card_called_off is None:
        check("game_status.card_called_off exists", False, "absent: this is the previous commit")
    else:
        check("both teams ABANDONED on a COMPLETED card: called off", card_called_off(summary_card(["ABANDONED", "ABANDONED"])) is True)
        check("both teams DREW: not called off (CA counts a genuine draw)", card_called_off(summary_card(["DREW", "DREW"])) is False)
        check("one team ABANDONED and one LOST: not called off", card_called_off(summary_card(["ABANDONED", "LOST"])) is False)
        check("WON and LOST: not called off", card_called_off(summary_card(["WON_OUTRIGHT", "LOST_OUTRIGHT"])) is False)
        check("a card CA has not called COMPLETED is not judged", card_called_off(summary_card(["ABANDONED", "ABANDONED"], status="LIVE")) is None)
        check("a card with no summary is not judged", card_called_off({"status": "COMPLETED"}) is None
              and card_called_off({"status": "COMPLETED", "matchSummary": {"teams": []}}) is None)
        check("no card is not judged", card_called_off(None) is None)
        check("a status of ABANDONED is already called off by status, so it is not stamped twice",
              card_called_off(summary_card(["ABANDONED", "ABANDONED"], status="ABANDONED")) is None)

    print("\n-- THE BACKFILL (dry run, apply, undo) --")
    if backfill is None:
        check("app.scripts.backfill_ca_called_off exists", False, "absent: this is the previous commit")
        async with Session() as s:     # the same data, written by hand so the figures below are the control
            await s.execute(text("UPDATE games SET ca_called_off = (id = :co) WHERE id IN (:co, :dr)"), {"co": G["CO"], "dr": G["DR"]})
            await s.commit()
    else:
        args = Namespace(year=None, pace=0.0, timeout=120, list=40, max_games=500)
        FETCHES.clear()
        rows, left = await backfill.plan(str(ORG), args, [500])
        by_game = {r["game_id"]: r["called_off"] for r in rows}
        check("the plan marks the call-off game TRUE and the draw FALSE",
              by_game == {str(G["CO"]): True, str(G["DR"]): False}, str(by_game))
        check("a game CA has no card for is left NULL, not guessed", any("no card" in k for k in left), str(dict(left)))
        check("only games with a named-only player are read: not one of the 19 games every player has a row in",
              set(FETCHES) == {str(G["CO"]), str(G["DR"]), str(G["NC"])}, f"{len(FETCHES)} fetched")
        async with Session() as s:
            n_set = (await s.execute(text("SELECT COUNT(*) FROM games WHERE ca_called_off IS NOT NULL"))).scalar()
        check("the dry run writes nothing", n_set == 0, str(n_set))
        for expect, by, label in ((len(rows) + 1, "Test Admin", "a wrong --expect"), (len(rows), None, "a missing --by")):
            try:
                await backfill.apply(str(ORG), rows, expect, by)
                check(f"{label} is refused", False, "it applied")
            except SystemExit:
                check(f"{label} is refused", True)
        await backfill.apply(str(ORG), rows, len(rows), "Test Admin")
        async with Session() as s:
            audit = (await s.execute(text("SELECT id, details FROM audit_logs WHERE action = 'backfill_ca_called_off'"))).mappings().all()
            flags = {str(r[0]): r[1] for r in (await s.execute(text(
                "SELECT id, ca_called_off FROM games WHERE ca_called_off IS NOT NULL"))).all()}
        check("the flags are written", flags == {str(G["CO"]): True, str(G["DR"]): False}, str(flags))
        check("one audit entry holds every row written", len(audit) == 1 and len(audit[0]["details"]["changes"]) == len(rows))
        FETCHES.clear()
        rows2, _ = await backfill.plan(str(ORG), args, [500])
        check("a second run reads only the game CA has no card for", rows2 == [] and FETCHES == [str(G["NC"])], str(FETCHES))

    print("\n-- AFTER: THE CALL-OFF GAME NO LONGER COUNTS FOR A PLAYER WHO ONLY WAS NAMED --")
    f1 = await figures()
    check("Bissett: header, season table, grid and batting board all read CA's 5",
          f1["BISSETT"] == (5, 5, 5, 5), str(f1["BISSETT"]))
    check("CA counted the game for Carl (6): it comes off once, every figure reads 5",
          f1["CACOUNT"] == (5, 5, 5, 5), str(f1["CACOUNT"]))
    check("Hugh batted in it: he played, 4 everywhere", f1["HASROW"] == (4, 4, 4, 4), str(f1["HASROW"]))
    check("Dan was named in a genuine draw, which CA counts: 4 everywhere", f1["DRAWN"] == (4, 4, 4, 4), str(f1["DRAWN"]))
    check("Ned's game has no card, so nothing can be said: 4 everywhere", f1["NOCARD"] == (4, 4, 4, 4), str(f1["NOCARD"]))
    g = await grid("BISSETT")
    check("no grade cell is drawn for the game", g["season_rows"][0]["grades"] == {"D Grade": 5}, str(g["season_rows"][0]["grades"]))

    print("\n-- FEES AND STATLAB USE THE SAME PREDICATE --")
    check("a named-only player in the call-off game is not enrolled for a match day", not await counts_as_match("BISSETT", G["CO"]))
    check("a player with a batting row in it is", await counts_as_match("HASROW", G["CO"]))
    check("a named-only player in a genuine draw is", await counts_as_match("DRAWN", G["DR"]))

    print("\n-- THE SYNC WRITES IT --")
    src = (Path(__file__).resolve().parent.parent / "app/services/sync.py").read_text()
    check("a new game row is created with the card's reading", "ca_called_off=card_called_off(scorecard)" in src)
    check("an already-stored game is updated before the appearances gate, so a finished game is not skipped",
          re.search(r"_called_off = card_called_off\(scorecard\).*?our_appearances_done = True", src, re.S) is not None)

    if backfill is not None:
        await backfill.restore(audit[0]["id"], "Test Admin")
        async with Session() as s:
            n_set = (await s.execute(text("SELECT COUNT(*) FROM games WHERE ca_called_off IS NOT NULL"))).scalar()
        check("--restore puts every game back to NULL", n_set == 0, str(n_set))
        check("and the app reads the old figure again (Bissett's header 6): nothing was lost", await header("BISSETT") == 6)
        try:
            await backfill.restore(audit[0]["id"], "Test Admin")
            check("an entry restores once", False, "restored twice")
        except SystemExit:
            check("an entry restores once", True)

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
