"""Verification for the boundary-count guard, against a real Postgres.

Reported off the record boards: "most sixes in an innings" was topped by a 2006
Under 12 innings of **8 runs off 0 balls with 1 four and 30 sixes**. Verified
against Cricket Australia's own live feed rather than assumed — it sends
`foursScored: 1, sixesScored: 30` for that innings — while the CricketStatz
import reads the same match's card correctly (8 runs, 1 four, 0 sixes).

Runs the SHIPPED rule and the SHIPPED backfill. The suite's whole point is that
the SQL mirror and the Python rule agree row by row: two copies of the same
arithmetic is how a repaired row and a freshly synced one start disagreeing.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/bettercricket?host=/tmp&port=5599 \
      python verification/verify_boundary_counts.py
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import Base  # noqa: E402

try:
    from app.services import boundary_counts  # noqa: E402
except ImportError:  # pragma: no cover - control runs only
    boundary_counts = None

PASS = FAIL = 0
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILED.append(name)
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def verify_rule() -> None:
    print("\nWhat a boundary count can be")
    if boundary_counts is None:
        check("services/boundary_counts.py is present", False,
              "the rule is absent — every check below is reported, not run")
        return
    clean = boundary_counts.clean

    # THE REPORTED INNINGS, as Cricket Australia sends it.
    check("the reported innings loses only the count that cannot fit",
          clean(8, 1, 30) == (1, None), str(clean(8, 1, 30)))
    check("an ordinary innings is left exactly as it is",
          clean(100, 10, 5) == (10, 5))
    check("a genuine none is kept as a none, never turned into unknown",
          clean(0, 0, 0) == (0, 0))
    # SIX RUNS PER SIX IS THE BOUND, so the boundary case is a real innings.
    check("six off one ball is possible and stands", clean(6, 0, 1) == (0, 1))
    check("a six in a five-run innings is not", clean(5, 0, 1) == (0, None))
    check("four off one ball stands", clean(4, 1, 0) == (1, 0))
    check("a four in a three-run innings does not", clean(3, 1, 0) == (None, 0))
    # EACH ON ITS OWN FIRST, THEN THE PAIR.
    check("each is possible alone but not together, so neither can be read",
          clean(24, 6, 1) == (None, None), str(clean(24, 6, 1)))
    check("and the same pair inside a bigger innings is fine",
          clean(30, 6, 1) == (6, 1))
    # NOTHING TO CHECK AGAINST IS NOT A REASON TO THROW A FIGURE AWAY.
    check("with no runs recorded the counts are left alone",
          clean(None, 1, 30) == (1, 30))
    check("a negative count cannot be read", clean(10, -1, 0) == (None, 0))
    # A CHECK THAT READS THE RETURN VALUE'S REPR CANNOT FAIL. The rule hands
    # back the two boundary counts and nothing else, so the runs are safe by
    # construction — the check that means something is on the stored row, in
    # `verify_backfill` below.
    check("the rule hands back the two boundary counts and nothing else",
          len(clean(8, 1, 30)) == 2)


async def verify_backfill(engine, session_maker) -> None:
    print("\nRepairing what is already stored")
    if boundary_counts is None:
        check("the backfill is present", False, "the rule is absent")
        return
    from app.scripts import backfill_boundary_counts as script

    org, other = uuid.uuid4(), uuid.uuid4()
    player, foreign = uuid.uuid4(), uuid.uuid4()
    season, grade, game = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_maker() as db:
        for oid, slug in ((org, "boundary-cc"), (other, "other-cc")):
            await db.execute(text("""
                INSERT INTO organisations (id, name, slug, is_active)
                VALUES (:o, :n, :s, true)
            """), {"o": str(oid), "n": slug, "s": slug})
        for pid, oid in ((player, org), (foreign, other)):
            await db.execute(text("""
                INSERT INTO players (id, organisation_id, name)
                VALUES (:p, :o, 'A Batter')
            """), {"p": str(pid), "o": str(oid)})
        await db.execute(text("""
            INSERT INTO seasons (id, organisation_id, name, year)
            VALUES (:s, :o, 'Summer 2006/07', 2006)
        """), {"s": str(season), "o": str(org)})
        await db.execute(text(
            "INSERT INTO grades (id, season_id, name) VALUES (:g, :s, 'U12')"),
            {"g": str(grade), "s": str(season)})
        await db.execute(text("""
            INSERT INTO games (id, grade_id, played_at, home_team, away_team)
            VALUES (:i, :g, CAST('2006-11-17' AS date), 'Boundary CC', 'Cameron')
        """), {"i": str(game), "g": str(grade)})
        # The reported row, one that is fine, and one belonging to another club.
        for inn, (pid, runs, fours, sixes) in enumerate(
                ((player, 8, 1, 30), (player, 100, 10, 5), (foreign, 8, 1, 30)), 1):
            await db.execute(text("""
                INSERT INTO batting_innings
                    (game_id, player_id, innings_number, runs, fours, sixes,
                     not_out, did_not_bat)
                VALUES (:g, :p, :i, :r, :f, :x, false, false)
            """), {"g": str(game), "p": str(pid), "i": inn, "r": runs,
                   "f": fours, "x": sixes})
        await db.execute(text("""
            INSERT INTO player_season_stats
                (player_id, season_id, source, matches, runs, fours, sixes)
            VALUES (:p, :s, 'api', 1, 8, 1, 30)
        """), {"p": str(player), "s": str(season)})
        await db.commit()

    dry = await script.repair("boundary-cc", apply=False)
    async with session_maker() as db:
        untouched = (await db.execute(text("""
            SELECT sixes FROM batting_innings
             WHERE player_id = :p AND runs = 8
        """), {"p": str(player)})).scalar()
    check("the dry run reports what it would repair",
          dry.get("batting_innings") == 1 and dry.get("player_season_stats") == 1,
          str(dry))
    check("and writes nothing", untouched == 30, str(untouched))

    applied = await script.repair("boundary-cc", apply=True)
    check("applying repairs the same rows the dry run named", applied == dry,
          f"{applied} vs {dry}")

    async with session_maker() as db:
        row = (await db.execute(text("""
            SELECT fours, sixes FROM batting_innings
             WHERE player_id = :p AND runs = 8
        """), {"p": str(player)})).first()
        ok_row = (await db.execute(text("""
            SELECT fours, sixes FROM batting_innings
             WHERE player_id = :p AND runs = 100
        """), {"p": str(player)})).first()
        theirs = (await db.execute(text("""
            SELECT sixes FROM batting_innings WHERE player_id = :p
        """), {"p": str(foreign)})).scalar()
        agg = (await db.execute(text("""
            SELECT fours, sixes FROM player_season_stats WHERE player_id = :p
        """), {"p": str(player)})).first()
    async with session_maker() as db:
        runs_after = (await db.execute(text("""
            SELECT runs FROM batting_innings
             WHERE player_id = :p AND innings_number = 1
        """), {"p": str(player)})).scalar()
    check("the runs are never touched — they are what everything else is "
          "reconciled against", runs_after == 8, str(runs_after))
    check("the impossible count reads as not recorded, not as zero",
          tuple(row) == (1, None), str(tuple(row)))
    check("the four beside it is kept — it fits the runs perfectly well",
          row[0] == 1, str(row[0]))
    check("an ordinary innings is untouched", tuple(ok_row) == (10, 5), str(tuple(ok_row)))
    check("a season total is repaired the same way", tuple(agg) == (1, None), str(tuple(agg)))
    check("another club's rows are not this club's to repair", theirs == 30, str(theirs))

    again = await script.repair("boundary-cc", apply=True)
    check("a second run repairs nothing", sum(again.values()) == 0, str(again))

    # THE SQL MIRROR AND THE PYTHON RULE MUST AGREE ROW BY ROW. Two copies of
    # the same arithmetic is how a repaired row and a freshly synced one start
    # disagreeing about the same innings.
    random.seed(5)
    cases = [(random.randrange(0, 200),
              random.choice([None, 0, 1, 3, 7, 12, 30]),
              random.choice([None, 0, 1, 2, 9, 30])) for _ in range(300)]
    async with session_maker() as db:
        for n, (runs, fours, sixes) in enumerate(cases, 10):
            await db.execute(text("""
                INSERT INTO batting_innings
                    (game_id, player_id, innings_number, runs, fours, sixes,
                     not_out, did_not_bat)
                VALUES (:g, :p, :i, :r, :f, :x, false, false)
            """), {"g": str(game), "p": str(player), "i": n, "r": runs,
                   "f": fours, "x": sixes})
        await db.commit()
    await script.repair("boundary-cc", apply=True)
    async with session_maker() as db:
        stored = (await db.execute(text("""
            SELECT runs, fours, sixes FROM batting_innings
             WHERE player_id = :p AND innings_number >= 10
             ORDER BY innings_number
        """), {"p": str(player)})).all()
    disagree = [
        (case, tuple(got)[1:])
        for case, got in zip(cases, stored)
        if boundary_counts.clean(case[0], case[1], case[2]) != tuple(got)[1:]
    ]
    check(f"the SQL and the Python rule agree on all {len(cases)} rows",
          not disagree, str(disagree[:3]))


def verify_writers() -> None:
    print("\nEvery writer applies it")
    root = Path(__file__).resolve().parent.parent / "app"
    sync = (root / "services" / "sync.py").read_text()
    check("the per-innings sync applies it", "_bounds(row.get(\"runsScored\")" in sync)
    check("and so does the season aggregate the career reads",
          "_bounds(bat.get(\"battingAggregate\")" in sync)
    check("no writer stores a raw boundary count any more",
          'fours=row.get("foursScored") or 0' not in sync
          and 'fours=bat.get("battingFours") or 0' not in sync,
          "a raw boundary write is still in sync.py")
    imp = (root / "services" / "cricketstatz_import.py").read_text()
    check("the CricketStatz import applies it too",
          "boundary_counts.clean(" in imp)


async def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set"); return 2
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    verify_rule()
    await verify_backfill(engine, session_maker)
    verify_writers()

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
