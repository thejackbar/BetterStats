"""An ordinary career import is the career as at its upload, so games synced after it add on top.

Reported by Kalamunda Cricket Club: Brian Smith and Ben Rowcroft's games stopped
going up each week while their runs and wickets kept moving, so the club added
+1 by hand after every round. Both carry an earlier ORDINARY career import (no
cut-off season). `reconcile_imported_totals` runs at the end of every sync and
works out that sheet's residual as `sheet games - whole online career`, so each
synced game took one off the residual and the total sat on the sheet's figure.
Runs moved because their online runs were already above the sheet's, so the
runs residual was 0.

The fix compares an ordinary sheet only against the online seasons the club
had started by the day it was uploaded (`seasons_after_upload`).

This suite imports a career sheet through the SHIPPED route bodies (`resolve`,
`commit`), dates the upload to 25 June 2026 (as Kalamunda's was, over winter),
then plays rounds of 2026/27 into the online season totals and runs the shipped
reconciler after each, the way the sync does. It reads the career back through
the profile's readers (`get_career_batting`, then `raise_games_to_grid_total`)
over the real `v_effective_*` views.

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_import_snapshot \\
      python -m verification.verify_import_snapshot_season

Control: run against the commit before the change. The weekly checks fail
(games stuck on the sheet's 200) and nothing crashes.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/verify_import_snapshot",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import select, text, update  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from _view_ddl import view_statements  # noqa: E402
from app.models.db import (  # noqa: E402
    Base, Game, Grade, ImportBatch, ImportEffectiveDelta, Organisation, Player, PlayerSeasonStats, Season,
)
from app.routers import imports as imp  # noqa: E402
from app.services import aggregations as agg  # noqa: E402
from app.services import import_ingest as ingest  # noqa: E402
from app.services import import_reconcile as recon  # noqa: E402

engine = create_async_engine(DB_URL, echo=False, connect_args={"server_settings": {"jit": "off"}})
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG, OPP = uuid.uuid4(), uuid.uuid4()
USER = SimpleNamespace(id=None)
SMITH, LOW, LATE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
NAMES = {SMITH: "Brian Smith", LOW: "Les Low", LATE: "Larry Late"}
SEASON = {y: uuid.uuid4() for y in (2010, 2024, 2025, 2026)}
GRADE = {y: uuid.uuid4() for y in (2024, 2025, 2026)}
WINTER_UPLOAD = datetime(2026, 6, 25, 2, 0, tzinfo=timezone.utc)
MID_SEASON_UPLOAD = datetime(2026, 11, 1, 2, 0, tzinfo=timezone.utc)

# Online (Cricket Australia) season totals: (matches, runs). 2010 is aggregate-only: no games rows.
ONLINE = {
    SMITH: {2010: (5, 100), 2024: (10, 600), 2025: (12, 700)},
    LOW: {2024: (10, 600), 2025: (12, 700)},
    LATE: {2024: (10, 600), 2025: (12, 700)},
}
# The club's sheet: games, runs. Smith and Late hold more games than online, fewer runs (the
# Kalamunda shape). Low's sheet is below online on both, so it adds nothing either way.
SHEET = {SMITH: (200, 1000), LOW: (20, 300), LATE: (200, 1000)}
ROUNDS = (date(2026, 10, 17), date(2026, 10, 24), date(2026, 11, 7), date(2026, 11, 14))
ROUND_RUNS = (20, 25, 12, 9)


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        # Lifespan DDL (main.py), not on the ORM model.
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        try:
            from app.services.import_through_ddl import STATEMENTS
            for stmt in STATEMENTS:
                await conn.execute(text(stmt))
        except ImportError:
            pass


async def seed() -> None:
    async with Session() as db:
        db.add_all([Organisation(id=ORG, name="Kalamunda Cricket Club", slug="kalamunda-s"),
                    Organisation(id=OPP, name="Opposition Cricket Club", slug="opp-s")])
        for y, sid in SEASON.items():
            db.add(Season(id=sid, organisation_id=ORG, name=f"Summer {y}/{(y + 1) % 100:02d}", year=y))
        await db.flush()
        for y, gid in GRADE.items():
            db.add(Grade(id=gid, season_id=SEASON[y], name="One Day Grade 1"))
        for pid, nm in NAMES.items():
            db.add(Player(id=pid, organisation_id=ORG, name=nm))
        await db.flush()
        # The 2026/27 draw is published before the season: fixtures dated from 17 October.
        for i, d in enumerate(ROUNDS):
            db.add(Game(id=uuid.uuid4(), grade_id=GRADE[2026], played_at=d, status="UPCOMING",
                        home_team="Kalamunda", away_team=f"Opposition {i}", home_org_id=ORG, away_org_id=OPP))
        # Games already played in 2024/25 and 2025/26.
        for y in (2024, 2025):
            db.add(Game(id=uuid.uuid4(), grade_id=GRADE[y], played_at=date(y, 10, 12), status="COMPLETED",
                        home_team="Kalamunda", away_team="Opposition", home_org_id=ORG, away_org_id=OPP))
        for pid, by_year in ONLINE.items():
            for y, (m, r) in by_year.items():
                db.add(PlayerSeasonStats(player_id=pid, season_id=SEASON[y], matches=m, batting_innings=m,
                                         runs=r, not_outs=0, source="api"))
        await db.commit()


def sheet_request(pids, **extra):
    lines = ["Name,Games Played,Total Runs"] + [f"{NAMES[p]},{SHEET[p][0]},{SHEET[p][1]}" for p in pids]
    parsed = ingest.parse_upload("career.csv", ("\n".join(lines) + "\n").encode())
    mapping = {f: v["column"] for f, v in ingest.suggest_column_mapping(parsed["headers"]).items()}
    return imp.CommitRequest(filename="career.csv", rows=parsed["rows"], mapping=mapping,
                             granularity="career", **extra)


async def import_sheet(pids, uploaded_at) -> dict:
    """Preview then commit through the shipped routes, then date the batch to the upload day."""
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        preview = await imp.resolve(sheet_request(pids), USER, club, db)
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        committed = await imp.commit(sheet_request(pids), USER, club, db)
    async with Session() as db:
        await db.execute(update(ImportBatch).where(ImportBatch.id == uuid.UUID(str(committed["batch_id"])))
                         .values(committed_at=uploaded_at, created_at=uploaded_at))
        await db.commit()
    await recon.reconcile_imported_totals(str(ORG))
    return {p["player_name"]: p for p in preview["preview"]}


async def play_round(i: int, pids) -> None:
    """A round of 2026/27 lands: the fixture is completed and CA's season totals move, then the sync's
    last pass re-runs the reconciler."""
    async with Session() as db:
        await db.execute(update(Game).where(Game.grade_id == GRADE[2026], Game.played_at == ROUNDS[i])
                         .values(status="COMPLETED"))
        for pid in pids:
            row = (await db.execute(select(PlayerSeasonStats).where(
                PlayerSeasonStats.player_id == pid, PlayerSeasonStats.season_id == SEASON[2026]))).scalars().first()
            if row is None:
                db.add(PlayerSeasonStats(player_id=pid, season_id=SEASON[2026], matches=1, batting_innings=1,
                                         runs=ROUND_RUNS[i], not_outs=0, source="api"))
            else:
                row.matches += 1
                row.batting_innings += 1
                row.runs += ROUND_RUNS[i]
        await db.commit()
    await recon.reconcile_imported_totals(str(ORG))


async def header(pid) -> dict:
    """The profile header's games and runs: career batting, raised to the by-grade grid as the route does."""
    async with Session() as db:
        bat = await agg.get_career_batting(db, str(pid)) or {}
        bowl = await agg.get_career_bowling(db, str(pid)) or {}
        field = await agg.get_career_fielding(db, str(pid)) or {}
        grid = await agg.raise_games_to_grid_total(db, str(pid), str(ORG), None, None, bat, bowl, field)
    return {"games": int(bat.get("games") or 0), "runs": int(bat.get("total_runs") or 0), "grid": grid}


async def residual(pid) -> int:
    async with Session() as db:
        rows = (await db.execute(select(ImportEffectiveDelta).where(
            ImportEffectiveDelta.player_id == pid, ImportEffectiveDelta.scope == "career"))).scalars().all()
    return sum(int(getattr(r, "matches", None) or getattr(r, "games_played", None) or 0) for r in rows)


async def main() -> int:
    await build_schema()
    await seed()

    print("\n-- an ordinary career sheet, uploaded over winter (25 June 2026)")
    pv = await import_sheet([SMITH, LOW], WINTER_UPLOAD)
    s0, l0 = await header(SMITH), await header(LOW)
    print(f"    Smith: {s0}  residual {await residual(SMITH)}   Low: {l0}")
    check("preview Smith: sheet 200 games, online 27, final 200",
          (pv.get("Brian Smith", {}).get("club_games"), pv.get("Brian Smith", {}).get("gr_games"),
           pv.get("Brian Smith", {}).get("final_games")) == (200, 27, 200), str(pv.get("Brian Smith")))
    check("Smith after the import: 200 games (online 27 + the sheet's 173 the online record lacks)",
          s0["games"] == 200, str(s0))
    check("Smith after the import: runs are online's 1,400 (the sheet's 1,000 adds nothing)",
          s0["runs"] == 1400, str(s0))
    check("Low after the import: online 22 games, 1,300 runs (his sheet is below online)",
          (l0["games"], l0["runs"]) == (22, 1300), str(l0))

    print("\n-- the 2026/27 rounds sync in, week by week")
    for i in range(len(ROUNDS)):
        await play_round(i, [SMITH, LOW])
        s, lo = await header(SMITH), await header(LOW)
        print(f"    after {ROUNDS[i]}: Smith {s} residual {await residual(SMITH)}   Low {lo}")
        check(f"{ROUNDS[i]}: Smith's games go up to {201 + i}", s["games"] == 201 + i, str(s))
        check(f"{ROUNDS[i]}: Smith's runs go up to {1400 + sum(ROUND_RUNS[:i + 1])}",
              s["runs"] == 1400 + sum(ROUND_RUNS[:i + 1]), str(s))
        check(f"{ROUNDS[i]}: Smith's sheet residual holds at 173", await residual(SMITH) == 173,
              str(await residual(SMITH)))
        check(f"{ROUNDS[i]}: Low's games go up to {23 + i}", lo["games"] == 23 + i, str(lo))

    print("\n-- the season split, read from the data the sheet could not have held")
    split = getattr(recon, "seasons_after_upload", None)  # absent on the control commit
    if split is None:
        async def split(_db, _org, _at):
            return None
    async with Session() as db:
        after = await split(db, ORG, WINTER_UPLOAD)
        before_any = await split(db, ORG, datetime(2026, 10, 1, tzinfo=timezone.utc))
        mid = await split(db, ORG, MID_SEASON_UPLOAD)
        nothing = await split(db, ORG, None)
    check("uploaded 25 June: only 2026/27 is after the sheet", after == {SEASON[2026]}, str(after))
    check("uploaded 1 October, draw published but nothing played: 2026/27 is still after",
          before_any == {SEASON[2026]}, str(before_any))
    check("2010/11 (online totals only, no games held) counts as inside the sheet",
          after is not None and SEASON[2010] not in after, str(after))
    check("uploaded 1 November, mid-season: 2026/27 had started, so it is inside (the known limit)",
          mid == set(), str(mid))
    check("no upload date: nothing is excluded (the old comparison)", nothing == set(), str(nothing))

    print("\n-- a sheet uploaded mid-season keeps that season's later games inside it (documented limit)")
    await import_sheet([LATE], MID_SEASON_UPLOAD)
    la = await header(LATE)
    print(f"    Late after import: {la}  residual {await residual(LATE)}")
    check("Late, uploaded 1 November: total is the sheet's 200", la["games"] == 200, str(la))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    return 1 if FAIL else 0


async def _run() -> int:
    try:
        return await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
