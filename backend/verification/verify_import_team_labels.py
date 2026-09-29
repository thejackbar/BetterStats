"""A sheet broken down by the club's own TEAMS is reconciled against the whole record.

Reported off The Basin: Leigh Cook's sheet says 240 matches over 2003/04 to
2025/26, labelled 1XI / 2XI / 3XI / 4XI / 20/20, and matches the online data
season for season. The import read 355 and the profile went to 433. Each team
label was mapped to ONE Cricket Australia grade name and compared against that
grade alone, but CA files the same side under a different grade name most
seasons, so every season spent under another name read as missing online and
was added on top.

Runs the SHIPPED `reconcile_imported_totals` against a real Postgres, plus the
pure helpers the preview shares with it.

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_import_team_labels \\
      python -m verification.verify_import_team_labels
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/verify_import_team_labels",
)
# app.models.db builds its engine from settings at import time.
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import select, text  # noqa: E402

from app.models.db import (  # noqa: E402
    Base, ImportBatch, ImportedStat, ImportEffectiveDelta, Organisation, Player, PlayerSeasonStats,
    Season, async_session_maker, engine,
)
from app.services import import_reconcile as recon  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


# Leigh Cook, as the sheet has him: (season start year, team, matches, runs).
SHEET = [
    (2003, "1XI", 10, 265), (2004, "1XI", 9, 197), (2005, "2XI", 2, 48),
    (2006, "1XI", 6, 82), (2006, "2XI", 1, 25), (2006, "3XI", 1, 79),
    (2007, "2XI", 8, 215), (2008, "2XI", 2, 24), (2008, "3XI", 2, 123),
    (2010, "1XI", 4, 122), (2010, "2XI", 3, 66), (2010, "3XI", 2, 238), (2010, "4XI", 1, 49),
    (2011, "1XI", 6, 69), (2011, "2XI", 3, 167),
    (2012, "1XI", 6, 26), (2012, "20/20", 4, 122), (2012, "2XI", 8, 237),
    (2013, "2XI", 14, 345), (2014, "2XI", 14, 339),
    (2015, "2XI", 9, 109), (2015, "3XI", 2, 89),
    (2016, "2XI", 9, 215), (2016, "3XI", 1, 29),
    (2017, "2XI", 11, 348), (2017, "3XI", 1, 41),
    (2018, "2XI", 14, 447), (2019, "2XI", 12, 282),
    (2020, "2XI", 9, 214), (2020, "3XI", 4, 61),
    (2021, "1XI", 4, 8), (2021, "2XI", 8, 192),
    (2022, "2XI", 11, 160), (2023, "2XI", 12, 366), (2024, "2XI", 12, 221),
    (2025, "2XI", 4, 72), (2025, "3XI", 11, 190),
]
# What the online (CA) season totals hold for him, per season.
ONLINE = {2025: 15, 2024: 12, 2023: 12, 2022: 12, 2021: 13, 2020: 14, 2019: 13,
          2018: 14, 2017: 12, 2016: 10, 2015: 12, 2014: 14, 2013: 14, 2012: 18,
          2011: 9, 2010: 10, 2009: 11, 2008: 4, 2007: 8, 2006: 8, 2005: 2,
          2004: 9, 2003: 10}


async def deltas(db, org_id, pid):
    return (await db.execute(select(ImportEffectiveDelta).where(
        ImportEffectiveDelta.organisation_id == org_id,
        ImportEffectiveDelta.player_id == pid))).scalars().all()


def total(rows, key="matches"):
    return sum(getattr(r, key) or 0 for r in rows)


async def main() -> int:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    print("\n── the pure helpers")
    check("one grade label is not a team-labelled sheet",
          not recon.is_team_labelled(["1st Grade", "1st Grade", None]))
    check("several are", recon.is_team_labelled(["1XI", "2XI"]))
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    check("a covered season widens to its year's other row",
          recon.covered_by_year({a}, {a: 2015, b: 2015, c: 2016}) == {a, b})
    check("and to nothing else", c not in recon.covered_by_year({a}, {a: 2015, b: 2015, c: 2016}))

    async with async_session_maker() as db:
        org = Organisation(id=uuid.uuid4(), name="The Basin Cricket Club", slug="the-basin-v")
        other = Organisation(id=uuid.uuid4(), name="Elsewhere", slug="elsewhere-v")
        db.add_all([org, other])
        leigh = Player(id=uuid.uuid4(), organisation_id=org.id, name="Cook, Leigh")
        older = Player(id=uuid.uuid4(), organisation_id=org.id, name="Old, Timer")
        db.add_all([leigh, older])
        seasons = {}
        for y in sorted(ONLINE):
            seasons[y] = Season(id=uuid.uuid4(), organisation_id=org.id,
                                name=f"Summer {y}/{(y + 1) % 100:02d}", year=y)
        # A hand-made second row for 2015 — the sheet's 2015 is matched to it.
        hand_2015 = Season(id=uuid.uuid4(), organisation_id=org.id, name="2015/16", year=None)
        # A season the online data never reached.
        pre = Season(id=uuid.uuid4(), organisation_id=org.id, name="1998/99", year=1998)
        db.add_all(list(seasons.values()) + [hand_2015, pre])
        batch = ImportBatch(id=uuid.uuid4(), organisation_id=org.id, status="committed")
        db.add(batch)
        await db.flush()
        for y, n in ONLINE.items():
            db.add(PlayerSeasonStats(player_id=leigh.id, season_id=seasons[y].id,
                                     matches=n, source="api"))
        for y, team, m, runs in SHEET:
            db.add(ImportedStat(organisation_id=org.id, import_batch_id=batch.id, player_id=leigh.id, scope="season",
                                season_id=hand_2015.id if y == 2015 else seasons[y].id,
                                season_label=f"{y}/{(y + 1) % 100:02d}", grade_label=team,
                                games_played=m, batting_runs=runs, is_prior_bucket=False))
        # A player whose sheet reaches before the online data and past it.
        db.add(PlayerSeasonStats(player_id=older.id, season_id=seasons[2003].id, matches=5, source="api"))
        db.add(ImportedStat(organisation_id=org.id, import_batch_id=batch.id, player_id=older.id, scope="season",
                            season_id=pre.id, season_label="1998/99", grade_label="2XI",
                            games_played=7, batting_runs=100, is_prior_bucket=False))
        db.add(ImportedStat(organisation_id=org.id, import_batch_id=batch.id, player_id=older.id, scope="season",
                            season_id=seasons[2003].id, season_label="2003/04", grade_label="1XI",
                            games_played=9, batting_runs=200, is_prior_bucket=False))
        await db.commit()
        org_id, leigh_id, older_id = org.id, leigh.id, older.id

    print("\n── the reported player")
    written = await recon.reconcile_imported_totals(str(org_id))
    async with async_session_maker() as db:
        rows = await deltas(db, org_id, leigh_id)
        online = sum(ONLINE.values())
        sheet = sum(m for _y, _t, m, _r in SHEET)
        check("the sheet is 240", sheet == 240, str(sheet))
        check("no season he played online is added again",
              not [r for r in rows if r.scope == "season"], str([(r.season_id, r.matches) for r in rows]))
        check("the hand-made 2015 row counts as covered",
              not [r for r in rows if r.scope == "season" and r.season_id == hand_2015.id])
        check("online already holds more than the sheet, so nothing is added",
              total(rows) == 0, f"added {total(rows)}")
        check("his career reads the online figure, never the two added together",
              online + total(rows) == 256, str(online + total(rows)))

        print("\n── a player the online data does not fully cover")
        rows = await deltas(db, org_id, older_id)
        pre_rows = [r for r in rows if r.scope == "season" and r.season_id == pre.id]
        check("the season before the online data is added", total(pre_rows) == 7, str(total(pre_rows)))
        check("and keeps the team its own row named", [r.grade_label for r in pre_rows] == ["2XI"])
        career = [r for r in rows if r.scope == "career"]
        check("the covered season's shortfall rides as one residual (9 - 5)",
              total(career) == 4, str(total(career)))
        check("the residual carries no grade it cannot vouch for",
              all(r.grade_label is None for r in career))
        check("his career is exactly the sheet's 16", 5 + total(rows) == 16, str(5 + total(rows)))

    print("\n── idempotent")
    again = await recon.reconcile_imported_totals(str(org_id))
    check("a second pass writes the same rows", again == written, f"{written} then {again}")

    print("\n── a single-competition sheet keeps the grade-scoped path")
    async with async_session_maker() as db:
        labels = [g for (g,) in (await db.execute(text(
            "SELECT DISTINCT grade_label FROM imported_stats WHERE organisation_id = :o"),
            {"o": org_id})).all()]
        check("this club's sheet reads as team-labelled", recon.is_team_labelled(labels))
        check("a club that uploaded only '1st Grade' would not", not recon.is_team_labelled(["1st Grade"]))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
