"""Verification for StatLab's one-player filter (`context.player_id`).

Asked for as "search a particular player and then create filters around that
player". The rule under test: naming a player narrows WHICH rows a table lists
and never changes the figures on them. So a player's career row with the
filter on must be byte-for-byte the row the unfiltered table shows for them —
the filter must not tip player_career onto the live per-innings path, which
counts a career from the scorecards and reads differently.

Reuses verify_rate_coverage's schema and seed (the SHIPPED views, real
players with scorecards and CA season totals that disagree), then runs the
shipped `statlab.run_query` for every target the filter reaches.

Run:  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/bstest \
      python verification/verify_statlab_player_filter.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_rate_coverage as base  # noqa: E402  (builds the engine from DATABASE_URL)
from sqlalchemy import text  # noqa: E402

from app.services import statlab  # noqa: E402

check = base.check


async def run(session, target, context, sort_by="runs"):
    return (await statlab.run_query(
        session, org_id=str(base.ORG), target=target, sort_by=sort_by,
        sort_dir="desc", limit=200, metric_filters=None, filter_tree=None,
        context=context))["rows"]


def ids(rows, key="player_id"):
    return {str(r.get(key)) for r in rows}


async def main() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        # Lifespan-created (raw SQL), so create_all never makes it; match_list reads it.
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
    async with base.Session() as session:
        await base.seed(session)
        # One partnership each way, so the partnership target has something to
        # narrow: BAT with RECORD, and ZERO with RECORD.
        g = (await session.execute(text(
            "SELECT bi.game_id FROM batting_innings bi WHERE bi.player_id = :p LIMIT 1"),
            {"p": base.BAT})).scalar()
        g2 = (await session.execute(text(
            "SELECT bi.game_id FROM batting_innings bi WHERE bi.player_id = :p LIMIT 1"),
            {"p": base.ZERO})).scalar()
        for game, a, b, runs in ((g, base.BAT, base.RECORD, 80), (g2, base.ZERO, base.RECORD, 30)):
            await session.execute(text(
                "INSERT INTO partnerships (game_id, innings_number, wicket_number, "
                "batter1_id, batter2_id, runs, balls, batter1_runs, batter2_runs, is_club_innings) "
                "VALUES (:g, 1, 1, :a, :b, :r, 60, :r, 0, true)"),
                {"g": game, "a": a, "b": b, "r": runs})
        await session.commit()

        pid = str(base.BAT)
        one = {"player_id": pid}

        print("\n— player career: the row is the unfiltered row, alone —")
        allrows = await run(session, "player_career", {})
        mine = await run(session, "player_career", one)
        check("unfiltered lists more than one player", len(allrows) > 1, str(len(allrows)))
        check("filtered lists exactly that player", ids(mine) == {pid}, str(ids(mine)))
        full = next((r for r in allrows if str(r["player_id"]) == pid), None)
        check("every figure on the row is unchanged by the filter",
              bool(mine) and full == mine[0],
              str({k: (full or {}).get(k) for k in ("runs", "matches", "batting_strike_rate")})
              + " vs " + str({k: (mine[0] if mine else {}).get(k) for k in ("runs", "matches", "batting_strike_rate")}))
        check("career runs read every season (500 + 240 + 240 imported), not a scorecard recount",
              bool(mine) and mine[0]["runs"] == 980, str(mine and mine[0]["runs"]))

        print("\n— composes with another context filter (the live path) —")
        live_all = await run(session, "player_career", {"result": "WIN"})
        live_one = await run(session, "player_career", {"result": "WIN", **one})
        full_live = next((r for r in live_all if str(r["player_id"]) == pid), None)
        check("live path: only that player", ids(live_one) == {pid}, str(ids(live_one)))
        check("live path: same row as the unfiltered live table",
              bool(live_one) and full_live == live_one[0])

        print("\n— player season / by grade —")
        seasons = await run(session, "player_season", one)
        check("player season: rows, all his", bool(seasons) and ids(seasons) == {pid}, str(ids(seasons)))
        check("player season: his seasons are all there (3)", len(seasons) == 3, str(len(seasons)))
        grades = await run(session, "player_grade", one)
        check("player by grade: only his rows", bool(grades) and ids(grades) == {pid}, str(ids(grades)))

        print("\n— innings and spells —")
        inns = await run(session, "innings_list", one)
        check("innings list: his 10 innings and nobody else's",
              len(inns) == 10 and ids(inns) == {pid}, f"{len(inns)} {ids(inns)}")
        spells = await run(session, "spell_list", {"player_id": str(base.BOWL)}, sort_by="wickets")
        check("spell list: the bowler's 4 spells only",
              len(spells) == 4 and ids(spells) == {str(base.BOWL)}, f"{len(spells)} {ids(spells)}")

        print("\n— matches he played in —")
        matches_all = await run(session, "match_list", {}, sort_by="team_runs")
        matches_one = await run(session, "match_list", one, sort_by="team_runs")
        check("match list: fewer than the whole club's", len(matches_one) < len(matches_all),
              f"{len(matches_one)} of {len(matches_all)}")
        check("match list: his 10 matches", len(matches_one) == 10, str(len(matches_one)))

        print("\n— partnerships he was in, on either end —")
        stands = await run(session, "partnership_list", {"player_id": str(base.RECORD)})
        check("partnerships: both stands found for the batter named second",
              len(stands) == 2, str(len(stands)))
        stands_bat = await run(session, "partnership_list", one)
        check("partnerships: only the stand involving him",
              len(stands_bat) == 1 and stands_bat[0]["runs"] == 80, str(stands_bat))

        print("\n— junk and strangers —")
        junk = await run(session, "player_career", {"player_id": "not-a-uuid"})
        check("a junk id is ignored, not an error, and filters nobody out",
              len(junk) == len(allrows), f"{len(junk)} vs {len(allrows)}")
        stranger = await run(session, "player_career", {"player_id": str(uuid.uuid4())})
        check("an unknown player lists nobody", stranger == [], str(stranger))

    await base.engine.dispose()
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    if base.FAIL:
        for f in base.FAILURES:
            print("  -", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
