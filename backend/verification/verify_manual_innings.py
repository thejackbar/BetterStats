"""A hand-entered manual game can say which side batted, record its extras,
and record the opposition innings' own total (migration 310).

The reported case: a club typed our batting AND our bowling both under innings
1, so the scorecard drew our own bowlers as the attack against our own batters
and their wides/no-balls polluted our batting extras. The hand-entry form had
no innings selector, no byes/leg-byes/total-extras field, and no way to record
an opposition total (their batters can't be itemised — a manual batting row FKs
to our own players).

This runs the SHIPPED write path (`_replace_game_children`) and read paths
(`get_manual_game`, `get_scorecard`) against a real Postgres, over a hand-entered
game. It NEVER touches `extracted_payload`, so the photo-upload path is untested
here by design — the two are disjoint.

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_manual_innings \
        python -m verification.verify_manual_innings

Control run: check out the previous commit and run it again — the import guard
below reports the feature absent (the ManualInnings model / manual_innings_ddl
don't exist there) rather than crashing, and the merge/round-trip checks fail.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import (
    Base,
    Grade,
    ManualBattingInnings,
    ManualBowlingSpell,
    ManualGame,
    Organisation,
    Player,
    Season,
)

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/verify_manual_innings",
)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


# The two views get_scorecard's fall-of-wickets / partnerships reads touch,
# pulled out of migrations 092 / 147 rather than retyped (a manual game with no
# such rows still reads them).
VIEWS = [
    """
    CREATE OR REPLACE VIEW v_effective_fall_of_wickets AS
    SELECT id, game_id, innings_number, wicket_number,
           score_at_fall, overs_at_fall, player_id, batter_name, 'api'::text AS source
    FROM fall_of_wickets
    UNION ALL
    SELECT id, manual_game_id AS game_id, innings_number, wicket_number,
           score_at_fall, overs_at_fall, player_id, batter_name, 'manual'::text AS source
    FROM manual_fall_of_wickets
    """,
    """
    CREATE OR REPLACE VIEW v_effective_partnerships AS
    SELECT id, game_id, innings_number, wicket_number,
           batter1_id, batter2_id, runs, balls, batter1_runs, batter2_runs,
           is_club_innings, 'api'::text AS source, batter1_name, batter2_name
    FROM partnerships
    UNION ALL
    SELECT id, manual_game_id AS game_id, innings_number, wicket_number,
           batter1_id, batter2_id, runs, balls, batter1_runs, batter2_runs,
           is_club_innings, 'manual'::text AS source, batter1_name, batter2_name
    FROM manual_partnerships
    """,
]

OUR_TEAM = "Hamilton Veterans"
OPP_TEAM = "Camperdown"


async def seed_bare_game(session):
    org = Organisation(id=uuid.uuid4(), name=OUR_TEAM, slug=f"hv-{uuid.uuid4().hex[:6]}")
    season = Season(id=uuid.uuid4(), organisation_id=org.id, name="Summer 2025/26", year=2025)
    grade = Grade(id=uuid.uuid4(), season_id=season.id, name="A Grade")
    players = [
        Player(id=uuid.uuid4(), organisation_id=org.id, name=f"Player {i}") for i in range(4)
    ]
    session.add_all([org, season, grade, *players])
    await session.flush()

    game = ManualGame(
        id=uuid.uuid4(), organisation_id=org.id, season_id=season.id, grade_id=grade.id,
        played_at=dt.date(2026, 1, 10), home_team=OUR_TEAM, away_team=OPP_TEAM,
        opposition=OPP_TEAM,
    )
    session.add(game)
    await session.flush()
    return org, season, grade, players, game


async def main() -> int:
    # Import guard so the control run (previous commit, no ManualInnings /
    # manual_innings_ddl) reports the feature absent rather than crashing.
    try:
        from app.services.manual_innings_ddl import STATEMENTS as INNINGS_DDL
        from app.models.db import ManualInnings  # noqa: F401
        from app.routers.manual_entries import (
            ManualGameIn, ManualBattingIn, ManualBowlingIn, ManualInningsIn,
            _replace_game_children, get_manual_game,
        )
        from app.routers.games import get_scorecard
        HAVE_FEATURE = True
    except Exception as exc:  # noqa: BLE001
        print(f"\nFEATURE ABSENT — {type(exc).__name__}: {exc}")
        print("This is the control run against a build without migration 310.")
        HAVE_FEATURE = False

    if not HAVE_FEATURE:
        for n in [
            "manual_innings table exists",
            "innings side / extras / opposition total stored",
            "get_manual_game returns the innings rows",
            "the scorecard labels each innings' batting side",
            "extras are read from the recorded innings, not only the bowlers",
            "the opposition total renders as bat-only + extras",
            "re-saving replaces the innings rows (no duplicate-key error)",
        ]:
            check(n, False, "feature not present in this build")
        print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
        return 1

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in INNINGS_DDL:
            await conn.execute(text(stmt))
        for stmt in VIEWS:
            await conn.execute(text(stmt))

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        org, season, grade, players, game = await seed_bare_game(session)

        # Hand-entered game: our batting in innings 1, our bowling in innings 2
        # (the opposition's batting innings — the reported fix). Innings meta
        # declares each side, our innings-1 extras (itemised), and the
        # opposition innings-2 total + a single extras total.
        data = ManualGameIn(
            season_id=str(season.id), grade_id=str(grade.id),
            opposition=OPP_TEAM,
            batting_innings=[
                ManualBattingIn(player_id=str(players[0].id), innings_number=1, batting_position=1, runs=54, dismissal_type="b Smith"),
                ManualBattingIn(player_id=str(players[1].id), innings_number=1, batting_position=2, runs=30, dismissal_type="lbw b Smith"),
            ],
            bowling_spells=[
                ManualBowlingIn(player_id=str(players[2].id), innings_number=2, overs=8.0, runs=40, wickets=3, wides=4, no_balls=2),
            ],
            fielding_stats=[],
            innings=[
                ManualInningsIn(innings_number=1, batting_side="us", byes=2, leg_byes=3, wides=1, no_balls=0, penalty=0),
                ManualInningsIn(innings_number=2, batting_side="opposition", total_runs=141, total_wickets=6, overs=35.0, extras_total=9),
            ],
        )
        await _replace_game_children(session, game.id, data, org.id)
        await session.commit()

        print("\nThe innings rows are stored")
        cnt = (await session.execute(
            text("SELECT COUNT(*) FROM manual_innings WHERE manual_game_id = :g"), {"g": game.id}
        )).scalar()
        check("manual_innings table exists", True)
        check("innings side / extras / opposition total stored", cnt == 2, f"got {cnt}")

        print("\nget_manual_game returns the innings rows for the edit form")
        full = await get_manual_game(str(game.id), current_user=None, club=org, db=session)
        inns = full.get("innings") or []
        by_n = {r["innings_number"]: r for r in inns}
        check("get_manual_game returns the innings rows", len(inns) == 2, f"got {len(inns)}")
        check("innings 1 is ours with its itemised byes",
              by_n.get(1, {}).get("batting_side") == "us" and by_n.get(1, {}).get("byes") == 2,
              str(by_n.get(1)))
        check("innings 2 is the opposition with its total",
              by_n.get(2, {}).get("batting_side") == "opposition"
              and by_n.get(2, {}).get("total_runs") == 141
              and by_n.get(2, {}).get("total_wickets") == 6,
              str(by_n.get(2)))

        print("\nThe scorecard merges the innings meta")
        card = await get_scorecard(str(game.id), session)
        totals = card["innings_totals"]
        check("both innings have a total", set(totals) == {1, 2}, str(sorted(totals)))
        check("the scorecard labels each innings' batting side",
              totals[1].get("batting_team") == OUR_TEAM and totals[2].get("batting_team") == OPP_TEAM,
              str({k: v.get("batting_team") for k, v in totals.items()}))

        # Our innings 1: batters sum to 84, extras itemised = 2+3+1+0+0 = 6.
        # Frontend renders runs + extras = 84 + 6 = 90.
        check("our innings runs stay the batters' sum (bat-only)",
              totals[1]["runs"] == 84, str(totals[1]))
        check("extras are read from the recorded innings, not only the bowlers",
              totals[1]["extras"] == 6, str(totals[1]))
        check("the itemised breakdown carries through",
              (totals[1].get("extras_breakdown") or {}).get("byes") == 2,
              str(totals[1].get("extras_breakdown")))

        # Opposition innings 2: total 141 full, extras_total 9 → bat-only 132,
        # so the frontend renders 132 + 9 = 141. NOT the bowler-derived 6.
        check("the opposition total renders as bat-only + extras (no double count)",
              totals[2]["runs"] == 132, str(totals[2]))
        check("the opposition extras use the recorded total, not the bowler sum",
              totals[2]["extras"] == 9, str(totals[2]))
        check("the opposition wickets come from the recorded total",
              totals[2]["wickets"] == 6, str(totals[2]))
        check("the opposition overs are carried",
              totals[2].get("overs") == 35.0, str(totals[2].get("overs")))
        check("our own bowling still sits in the opposition's innings",
              any(r["innings_number"] == 2 and r["wickets"] == 3 for r in card["bowling"]),
              str([(r["innings_number"], r["wickets"]) for r in card["bowling"]]))

        print("\nRe-saving replaces rather than duplicating")
        data2 = ManualGameIn(
            season_id=str(season.id), grade_id=str(grade.id), opposition=OPP_TEAM,
            batting_innings=data.batting_innings, bowling_spells=data.bowling_spells,
            innings=[
                # A duplicate innings_number in one payload must not hit the
                # unique key — last one wins.
                ManualInningsIn(innings_number=2, batting_side="opposition", total_runs=99),
                ManualInningsIn(innings_number=2, batting_side="opposition", total_runs=150, total_wickets=8),
            ],
        )
        await _replace_game_children(session, game.id, data2, org.id)
        await session.commit()
        cnt2 = (await session.execute(
            text("SELECT COUNT(*) FROM manual_innings WHERE manual_game_id = :g"), {"g": game.id}
        )).scalar()
        row2 = (await session.execute(
            text("SELECT total_runs, total_wickets FROM manual_innings WHERE manual_game_id = :g"), {"g": game.id}
        )).first()
        check("re-saving replaces the innings rows (no duplicate-key error)", cnt2 == 1, f"got {cnt2}")
        check("a duplicate innings_number in one payload keeps the last",
              row2 is not None and row2[0] == 150 and row2[1] == 8, str(tuple(row2) if row2 else None))

        print("\nA game with no innings rows renders exactly as before")
        game_b = ManualGame(
            id=uuid.uuid4(), organisation_id=org.id, season_id=season.id, grade_id=grade.id,
            played_at=dt.date(2026, 2, 1), opposition=OPP_TEAM,
        )
        session.add(game_b)
        await session.flush()
        plain = ManualGameIn(
            season_id=str(season.id), grade_id=str(grade.id),
            batting_innings=[ManualBattingIn(player_id=str(players[0].id), innings_number=1, runs=25, dismissal_type="b X")],
        )
        await _replace_game_children(session, game_b.id, plain, org.id)
        await session.commit()
        card_b = await get_scorecard(str(game_b.id), session)
        check("a game with no innings rows still totals from its batters",
              card_b["innings_totals"].get(1, {}).get("runs") == 25,
              str(card_b["innings_totals"]))
        check("a game with no innings rows carries no batting_team label",
              card_b["innings_totals"].get(1, {}).get("batting_team") in (None, ""),
              str(card_b["innings_totals"].get(1)))

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
