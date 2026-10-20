"""Verification: Fantasy scores a club's players in a fixture the OTHER club synced
first. Real Postgres.

A fixture between two clubs that both sync is ONE `games` row whose grade and season
point at whichever club synced it first. The Fantasy engine read games by the season's
owner (`seasons.organisation_id`), so a club's own match vanished from its Fantasy the
moment the opposition's sync got there first, and the grade filter compared the club's
own grade ids against the other club's grade row. It also returned the opposition's
players from the same rows.

Runs the SHIPPED `fantasy_engine._round_player_scores`.

CONTROL (`--control`): the engine as it was before this change (`CONTROL_REV`). It must
score nobody from the shared fixture, read through presence-safe accessors.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_shared_fixture.py [--control]
"""
from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text

import verify_fantasy_unsettle as base
from app.models.db import (
    Player, Season, Grade, Game, BattingInnings, GameAppearance, FantasySeason, FantasyRound,
)
from app.services import fantasy_engine

Session, check = base.Session, base.check
ORG, ORG_B, FS_ID, R2, TODAY = base.ORG, base.ORG_B, base.FS_ID, base.R2, base.TODAY
SAM, RAY = uuid.uuid4(), uuid.uuid4()             # our player, and the opposition's
SEASON_B, GRADE_B, GAME = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
REPO = Path(__file__).resolve().parent.parent.parent
CONTROL_REV = "bae2507"                           # the engine before the shared-fixture fix


async def seed_shared() -> uuid.UUID:
    """The opposition (ORG_B) synced the fixture first: its season and grade own the row."""
    async with Session() as s:
        s.add_all([Player(id=SAM, name="Shared Sam", organisation_id=ORG, grassroots_id="sam-ca"),
                   Player(id=RAY, name="Rival Ray", organisation_id=ORG_B, grassroots_id="ray-ca")])
        s.add(Season(id=SEASON_B, organisation_id=ORG_B, name="Summer", year=TODAY.year, grassroots_id="sb"))
        await s.flush()
        s.add(Grade(id=GRADE_B, season_id=SEASON_B, name="Firsts", grassroots_id="gb"))
        await s.flush()
        s.add(Game(id=GAME, grade_id=GRADE_B, played_at=TODAY - timedelta(days=2), home_team="Bravo", away_team="Alpha",
                   home_org_id=ORG_B, away_org_id=ORG, status="COMPLETED"))
        await s.flush()
        # The view's organisation_id is the season owner's (ORG_B here): the fixture hangs off the other club.
        for pid, runs in ((SAM, 44), (RAY, 60)):
            s.add(GameAppearance(game_id=GAME, player_id=pid, team_name="x"))
            s.add(BattingInnings(game_id=GAME, player_id=pid, innings_number=1, runs=runs, balls=runs, fours=0, sixes=0,
                                 dismissal_type="bowled", not_out=False))
        s.add(base.FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=SAM, role="batter", base_price=5, current_price=5))
        await s.commit()
        own_grade = (await s.execute(text("SELECT id FROM grades WHERE name='Firsts' AND season_id IN (SELECT id FROM seasons WHERE organisation_id=:o)"), {"o": ORG})).scalar()
    return own_grade


async def scores(engine_mod, grade_ids=None) -> dict:
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        fs.included_grade_ids = grade_ids
        rnd = await s.get(FantasyRound, R2)
        out = await engine_mod._round_player_scores(s, fs, rnd)
        await s.rollback()
        return out


async def checks(engine_mod, control=False) -> None:
    own = await seed_shared()
    tag = "(control) " if control else ""
    async with Session() as s:
        n = (await s.execute(text("SELECT COUNT(*) FROM batting_innings WHERE game_id = :g AND player_id = :p"), {"g": GAME, "p": RAY})).scalar()
    check(f"{tag}the opposition's innings really is in the shared game (so 'not scored' means something)", n == 1, str(n))
    r = await scores(engine_mod)
    sam = r.get(str(SAM), {}).get("total")
    check(f"{tag}our player in a fixture the other club owns is scored", sam is not None and sam > 0, repr(r.get(str(SAM), "<absent>")))
    check(f"{tag}and the opposition's player from the same rows is not", str(RAY) not in r, "opposition scored: " + repr(r.get(str(RAY), "<absent>")))
    if control:
        return
    check("a player in a fixture the club owns itself still scores (nothing lost)", r.get(str(base.A), {}).get("total", 0) > 0, repr(list(r)))
    r2 = await scores(engine_mod, grade_ids=[str(own)])
    check("a grade filter on the club's own grade still finds the fixture sitting under the other club's same-named grade",
          r2.get(str(SAM), {}).get("total", 0) > 0, repr(list(r2)))
    other = uuid.uuid4()
    async with Session() as s:
        sid = (await s.execute(text("SELECT season_id FROM grades WHERE id=:g"), {"g": own})).scalar()
        s.add(Grade(id=other, season_id=sid, name="Seconds", grassroots_id="g2"))
        await s.commit()
    r3 = await scores(engine_mod, grade_ids=[str(other)])
    check("and a filter on a different grade still leaves it out (the filter still filters)", str(SAM) not in r3, repr(list(r3)))
    # The rounds calendar sees the shared fixture's date too.
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        fs.included_grade_ids = None
        dates = {r[0] for r in (await s.execute(text(f"""
            SELECT g.played_at FROM v_effective_games g JOIN grades gr ON gr.id = g.grade_id JOIN seasons s ON s.id = gr.season_id
            WHERE {fantasy_engine.club_game_sql("g", "org")} AND s.year = :y"""), {"org": str(ORG), "y": TODAY.year})).all()}
        await s.rollback()
    check("the round calendar's read of games includes the fixture's date", (TODAY - timedelta(days=2)) in dates, repr(dates))


async def main() -> int:
    await base.build_schema()
    async with base.engine.begin() as conn:       # lifespan table the grade lookup reads (main.py), copied column for column
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
    await base.seed()
    if "--control" in sys.argv:
        src = subprocess.check_output(["git", "show", f"{CONTROL_REV}:backend/app/services/fantasy_engine.py"], cwd=REPO, text=True)
        tmp = Path(__file__).resolve().parent / "_fantasy_engine_control2.py"
        tmp.write_text(src)
        try:
            spec = importlib.util.spec_from_file_location("fantasy_engine_control2", tmp)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            await checks(mod, control=True)
        finally:
            tmp.unlink(missing_ok=True)
    else:
        await checks(fantasy_engine)
    return base.FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    sys.exit(1 if failed else 0)
