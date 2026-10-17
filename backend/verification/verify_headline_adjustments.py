"""A profile headline carries the club's season-less adjustment, and only where it belongs.

Reported by Kalamunda: a player Cricket Australia plus the club's own history
upload credits with 302 matches read 289, and read 42 under Juniors and 47 under
Masters although he never played a junior match.

Two faults, one player:
  1. The headline is raised to the Analysis grid's total (`raise_games_to_grid_total`),
     but the grid crashed for any player holding a season-less adjustment (an
     import's career line) and the crash was swallowed, so the headline stayed
     where the scorecards left it. And once it ran, the grid total left the
     adjustment out, so the headline could never reach the combined figure.
  2. An adjustment with no grade at all was kept under EVERY category pick, so
     the Juniors headline counted a senior book.

Runs the SHIPPED `get_player_stats` route body against a real Postgres over the
real views, on the match-coverage suite's seeded club, with a season-less career
adjustment of 5 matches added to GAPPY (senior seasons plus junior games).

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_headline \\
      python -m verification.verify_headline_adjustments

Run against the commit before the change the headline checks report; nothing crashes.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/verify_headline")

import verify_match_coverage as m  # noqa: E402
from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


async def head(session, player, **kw) -> int:
    try:
        out = await m.stats(session, player, **kw)
        return int((out.get("career_batting") or {}).get("games") or 0)
    except Exception as exc:  # control run: report, do not crash
        return -1


async def grid(session, player, **kw):
    try:
        return await m.grid(session, player, **kw)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {str(exc)[:80]}"}


PICKS = (("the club default", {}, 5), ("Men's", {"categories": "senior"}, 5), ("every grade type", {"categories": "all"}, 5),
         ("Juniors", {"categories": "junior"}, 0), ("Masters", {"categories": "masters"}, 0),
         ("Women's", {"categories": "womens"}, 0),
         ("Men's + One Day", {"categories": "senior", "formats": "one_day"}, 0))


async def main() -> int:
    await m.build_schema()
    async with m.Session() as s:
        await m.seed(s)
        await s.commit()
    async with m.Session() as s:
        before = {label: await head(s, m.GAPPY, **kw) for label, kw, _ in PICKS}
        before_short = await head(s, m.SHORT)
        before_plain = await head(s, m.PLAIN)
        print("    headline before the adjustment:", before)
        # The club's own career-level line: no season, no grade, no label.
        await s.execute(text(
            "INSERT INTO import_effective_deltas (organisation_id, player_id, scope, season_id, grade_id,"
            " grade_label, matches, batting_innings, runs) VALUES (:o, :p, 'career', NULL, NULL, NULL, 5, 5, 100)"),
            {"o": m.ORG, "p": m.GAPPY})
        await s.commit()
    async with m.Session() as s:
        print("\n-- the Team grid loads for a player holding a season-less adjustment (it used to 500)")
        g = await grid(s, m.GAPPY)
        check("the grid answers", "error" not in g, str(g.get("error")))
        check("and reports the 5 among the matches without a grade", g.get("unattributed", 0) >= 5, str(g.get("unattributed")))

        print("\n-- the headline moves by the 5 where the adjustment belongs and by nothing where it does not")
        for label, kw, gain in PICKS:
            h = await head(s, m.GAPPY, **kw)
            check(f"{label}: +{gain}", h == before[label] + gain, f"{before[label]} -> {h}")
        h = await head(s, m.GAPPY)
        check("the club default reads 12: scorecards plus CA's gap-fill (4 + 3) plus the 5", h == 12, str(h))
        h = await head(s, m.GAPPY, categories="all")
        check("every grade type reads 16: CA's 11 plus the 5", h == 16, str(h))

        print("\n-- a player with no adjustment is unchanged")
        check("SHORT is unchanged", await head(s, m.SHORT) == before_short, str(await head(s, m.SHORT)))
        check("PLAIN is unchanged", await head(s, m.PLAIN) == before_plain, str(await head(s, m.PLAIN)))

    print(f"\n{PASS} passed, {FAIL} failed")
    await m.engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
