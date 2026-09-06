"""A manually uploaded scorecard has to open.

Reported off a live club: a 1974 game uploaded from a PDF appeared in the
Games list and returned `Error: Internal Server Error` the moment anybody
clicked it. Every manual game did — `manual_batting_innings` has no
`caught_behind` column (only the synced `batting_innings` does, migration
075), and `get_scorecard` read `bi.caught_behind` unconditionally on the
shared code path, so the row build raised `AttributeError` before the
response was ever assembled.

This runs the SHIPPED route body (extracted from the router, nothing
retyped) against a real Postgres, over a manual game seeded the way the AI
scorecard upload writes one. Run it with the fix reverted and check 1 fails
with the reported error — a check that cannot fail is not a check.

    DATABASE_URL=postgresql+asyncpg://... python -m verification.verify_manual_scorecard
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db import (
    Base,
    Grade,
    ManualBattingInnings,
    ManualBowlingSpell,
    ManualFieldingStat,
    ManualGame,
    Organisation,
    Player,
    Season,
)
from app.routers.games import get_scorecard

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@localhost:55432/verify_manual_scorecard",
)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


# The two views get_game_fall_of_wickets / get_game_partnerships read, pulled
# straight out of migrations 092 and 147 rather than retyped.
VIEWS = [
    """
    CREATE OR REPLACE VIEW v_effective_fall_of_wickets AS
    SELECT id, game_id, innings_number, wicket_number,
           score_at_fall, overs_at_fall, player_id, batter_name,
           'api'::text AS source
    FROM fall_of_wickets
    UNION ALL
    SELECT id, manual_game_id AS game_id, innings_number, wicket_number,
           score_at_fall, overs_at_fall, player_id, batter_name,
           'manual'::text AS source
    FROM manual_fall_of_wickets
    """,
    """
    CREATE OR REPLACE VIEW v_effective_partnerships AS
    SELECT id, game_id, innings_number, wicket_number,
           batter1_id, batter2_id, runs, balls,
           batter1_runs, batter2_runs, is_club_innings,
           'api'::text AS source,
           batter1_name, batter2_name
    FROM partnerships
    UNION ALL
    SELECT id, manual_game_id AS game_id, innings_number, wicket_number,
           batter1_id, batter2_id, runs, balls,
           batter1_runs, batter2_runs, is_club_innings,
           'manual'::text AS source,
           batter1_name, batter2_name
    FROM manual_partnerships
    """,
]

OUR_TEAM = "Collegians 2nd XI"
OPP_TEAM = "Newry"


def extracted_payload() -> dict:
    """What the AI scorecard reader stores for a two-team card."""
    return {
        "match": {"date": "1974-11-30", "home_team": OPP_TEAM, "away_team": OUR_TEAM},
        "innings": [
            {
                "innings_number": 1,
                "batting_team": OPP_TEAM,
                "is_our_team": False,
                "total_runs": 118,
                "total_wickets": 10,
                "extras": {"total": 9},
                "batting": [
                    {"name": "R Kelly", "runs": 41, "balls": None, "position": 1,
                     "dismissal_text": "b: J Smith"},
                    {"name": "P Dwyer", "runs": 12, "position": 2, "dismissal_text": "lbw b: J Smith"},
                ],
                "bowling": [{"name": "J Smith", "overs": 14.0, "maidens": 3, "runs": 38, "wickets": 5}],
            },
            {
                "innings_number": 2,
                "batting_team": OUR_TEAM,
                "is_our_team": True,
                "total_runs": 140,
                "total_wickets": 6,
                "extras": {"total": 7},
                "bowling": [
                    {"name": "G Nolan", "overs": 16.0, "maidens": 2, "runs": 52, "wickets": 3},
                ],
            },
        ],
    }


async def seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    org = Organisation(id=uuid.uuid4(), name="Collegians Cricket Club", slug="collegians-verify")
    session.add(org)
    await session.flush()

    season = Season(id=uuid.uuid4(), organisation_id=org.id, name="Summer 1974/75", year=1974)
    session.add(season)
    await session.flush()

    grade = Grade(id=uuid.uuid4(), season_id=season.id, name="2nd Grade")
    session.add(grade)
    await session.flush()

    players = []
    for name in ("Smith, John", "Doe, Peter", "Brown, Alan"):
        p = Player(id=uuid.uuid4(), organisation_id=org.id, name=name)
        session.add(p)
        players.append(p)
    await session.flush()

    game = ManualGame(
        id=uuid.uuid4(),
        organisation_id=org.id,
        season_id=season.id,
        grade_id=grade.id,
        played_at=dt.date(1974, 11, 30),
        home_team=OPP_TEAM,
        away_team=OUR_TEAM,
        opposition=OPP_TEAM,
        result="WIN",
        winning_team=OUR_TEAM,
        extracted_payload=extracted_payload(),
    )
    session.add(game)
    await session.flush()

    # Our own half of the card, exactly as the upload commit writes it —
    # note nothing here carries a caught_behind value, because the column
    # does not exist on the manual table.
    session.add_all([
        ManualBattingInnings(manual_game_id=game.id, player_id=players[0].id, innings_number=2,
                             batting_position=1, runs=64, balls=98, fours=7, sixes=0,
                             dismissal_type="c: R Kelly b: G Nolan", not_out=False, did_not_bat=False),
        ManualBattingInnings(manual_game_id=game.id, player_id=players[1].id, innings_number=2,
                             batting_position=2, runs=31, balls=None, fours=None, sixes=None,
                             dismissal_type="not out", not_out=True, did_not_bat=False),
        ManualBattingInnings(manual_game_id=game.id, player_id=players[2].id, innings_number=2,
                             batting_position=3, runs=0, did_not_bat=True, not_out=False),
        ManualBowlingSpell(manual_game_id=game.id, player_id=players[0].id, innings_number=1,
                           overs=14.0, maidens=3, runs=38, wickets=5, wides=None, no_balls=None),
        ManualFieldingStat(manual_game_id=game.id, player_id=players[2].id,
                           catches=2, catches_wk=0, run_outs=1, stumpings=0),
    ])
    await session.flush()

    # A column the card didn't track is NULL, not 0 (migration 184). Setting
    # the attribute to None does NOT produce that — SQLAlchemy reads it as
    # "unset" and lets the server default 0 apply — so force it in SQL, or
    # the check below would be measuring the harness's own insert.
    await session.execute(
        text("UPDATE manual_batting_innings SET fours = NULL, sixes = NULL "
             "WHERE manual_game_id = :g AND runs = 31"),
        {"g": game.id},
    )
    return game.id, org.id


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in VIEWS:
            await conn.execute(text(stmt))

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        game_id, org_id = await seed(session)
        await session.commit()

        print("\nA manual game opens at all")
        try:
            card = await get_scorecard(str(game_id), session)
            crashed = None
        except Exception as exc:  # noqa: BLE001 — the reported failure
            card, crashed = None, f"{type(exc).__name__}: {exc}"

        check("the scorecard endpoint returns instead of raising", crashed is None, crashed or "")
        if card is None:
            print("\nEverything below depends on the card being built.")
            return 1

        print("\nThe response carries what the page needs")
        check("the game is identified", card["id"] == str(game_id))
        check("both team names are present",
              card["home_team"] == OPP_TEAM and card["away_team"] == OUR_TEAM)
        check("the owning club resolves (themes the page)", card["organisation_id"] == str(org_id))
        check("the date survives", card["played_at"] == "1974-11-30")
        check("the grade and season resolve",
              (card["grade"] or {}).get("raw_name") == "2nd Grade"
              and (card["season"] or {}).get("name") == "Summer 1974/75")

        print("\nOur own half of the card")
        batting = card["batting"]
        check("all three of our batting rows are returned", len(batting) == 3, f"got {len(batting)}")
        top = next((r for r in batting if r["runs"] == 64), None)
        check("the top score is there with its dismissal",
              top is not None and top["dismissal_type"] == "c: R Kelly b: G Nolan")
        check("caught_behind is reported as unknown, not invented",
              all(r["caught_behind"] is None for r in batting),
              str([r["caught_behind"] for r in batting]))
        check("a not-out row reads not out",
              any(r["not_out"] and r["runs"] == 31 for r in batting))
        check("a did-not-bat row is flagged rather than dropped",
              any(r["did_not_bat"] for r in batting))
        check("an untracked boundary count stays NULL rather than reading 0",
              any(r["runs"] == 31 and r["fours"] is None for r in batting))
        check("our bowling figures are returned",
              len(card["bowling"]) == 1 and card["bowling"][0]["wickets"] == 5)
        check("our fielding is returned",
              len(card["fielding"]) == 1 and card["fielding"][0]["catches"] == 2)

        print("\nThe opposition half, from the stored payload")
        opp_bat = card["opp_batting"]
        check("the opposition batters are drawn", len(opp_bat) == 2, f"got {len(opp_bat)}")
        check("an opposition batter keeps their name and score",
              any(r["player_name"] == "R Kelly" and r["runs"] == 41 for r in opp_bat))
        check("an opposition batter is never linked to one of our players",
              all(r["player_id"] is None for r in opp_bat))
        check("the opposition's bowling figures are drawn",
              len(card["opp_bowling"]) == 1 and card["opp_bowling"][0]["player_name"] == "G Nolan")

        print("\nBoth innings' totals")
        totals = card["innings_totals"]
        check("both innings have a total", set(totals) == {1, 2}, str(sorted(totals)))
        check("each innings names the side that batted",
              totals[1].get("batting_team") == OPP_TEAM and totals[2].get("batting_team") == OUR_TEAM,
              str({k: v.get("batting_team") for k, v in totals.items()}))
        check("the opposition total comes from the card, not from summing our rows",
              totals[1]["runs"] == 118 and totals[1]["wickets"] == 10,
              str(totals[1]))
        check("our own total sums our batters", totals[2]["runs"] == 95, str(totals[2]))
        check("extras are carried per innings",
              totals[1]["extras"] == 9 and totals[2]["extras"] == 7,
              str({k: v.get("extras") for k, v in totals.items()}))

        print("\nThe session is still usable afterwards")
        ok = (await session.execute(text("SELECT 1"))).scalar() == 1
        check("a plain query still runs", ok)

    await engine.dispose()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
