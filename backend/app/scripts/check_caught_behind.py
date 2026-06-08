"""Health-check for the caught-behind / wicketkeeper-catch feature.

Read-only. Verifies the new columns + view exist, reports backfill completeness
for batting_innings.caught_behind and bowler_wickets.caught_behind (global and
per-club), and sanity-checks the caught-behind rate against CA's authoritative
wicketkeeper-catch share (player_season_stats.catches_wk, always populated).

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.check_caught_behind
"""

import asyncio

from sqlalchemy import text as t

from app.models.db import async_session_maker


def _mark(ok: bool) -> str:
    return "OK  " if ok else "FAIL"


async def main() -> None:
    async with async_session_maker() as s:
        async def one(sql: str):
            return (await s.execute(t(sql))).mappings().first()

        print("=" * 70)
        print(" Caught-behind / wicketkeeper-catch health check")
        print("=" * 70)

        # 1. Schema — new columns + the effective view expose caught_behind.
        bi = await one("SELECT 1 AS x FROM information_schema.columns WHERE table_name='batting_innings' AND column_name='caught_behind'")
        bw = await one("SELECT 1 AS x FROM information_schema.columns WHERE table_name='bowler_wickets' AND column_name='caught_behind'")
        vw = await one("SELECT 1 AS x FROM information_schema.columns WHERE table_name='v_effective_batting_innings' AND column_name='caught_behind'")
        print("\n[schema]")
        print(f"  {_mark(bool(bi))}  batting_innings.caught_behind column (migration 075)")
        print(f"  {_mark(bool(bw))}  bowler_wickets.caught_behind column (migration 076)")
        print(f"  {_mark(bool(vw))}  v_effective_batting_innings exposes caught_behind")

        # 2. Authoritative keeper-catch share — fielding counts, always synced.
        f = await one("SELECT COALESCE(SUM(catches_wk),0) wk, COALESCE(SUM(catches),0) tot FROM player_season_stats")
        auth = (100 * f["wk"] / f["tot"]) if f["tot"] else 0.0
        print("\n[fielding wk-catch counts — authoritative, no backfill needed]")
        print(f"  catches_wk={f['wk']}  catches={f['tot']}  keeper share={auth:.1f}%")
        if not f["wk"]:
            print("  WARN: no catches_wk recorded at all — check the aggregate sync")

        # 3. Batting caught-behind.
        b = await one("""
            SELECT count(*) FILTER (WHERE dismissal_type='c') AS catches,
                   count(*) FILTER (WHERE dismissal_type='c' AND caught_behind IS NOT NULL) AS done,
                   count(*) FILTER (WHERE caught_behind IS TRUE) AS cb
            FROM batting_innings
        """)
        bdone = (100 * b["done"] / b["catches"]) if b["catches"] else 0.0
        brate = (100 * b["cb"] / b["catches"]) if b["catches"] else 0.0
        print("\n[batting_innings.caught_behind]")
        print(f"  catches={b['catches']}  backfilled={b['done']} ({bdone:.0f}%)  caught_behind={b['cb']} ({brate:.1f}% of catches)")
        if bdone < 95:
            print("  WARN: backfill incomplete — run: python -m app.scripts.backfill_caught_behind all")
        elif b["cb"] and brate < auth * 0.5:
            print(f"  NOTE: rate is well under the {auth:.0f}% keeper share — older games that don't record the keeper can't be attributed (expected, never wrong).")

        # 4. Bowling caught-behind.
        w = await one("""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE dismissal_type='caught') AS caught,
                   count(*) FILTER (WHERE dismissal_type='caught' AND caught_behind IS NOT NULL) AS done,
                   count(*) FILTER (WHERE caught_behind IS TRUE) AS cb,
                   count(*) FILTER (WHERE caught_behind IS NULL) AS legacy
            FROM bowler_wickets
        """)
        wdone = (100 * w["done"] / w["caught"]) if w["caught"] else 0.0
        wrate = (100 * w["cb"] / w["caught"]) if w["caught"] else 0.0
        print("\n[bowler_wickets.caught_behind]")
        print(f"  rows={w['total']}  caught={w['caught']}  rebuilt={w['done']} ({wdone:.0f}%)  caught_behind={w['cb']} ({wrate:.1f}% of caught)")
        if w["legacy"]:
            print(f"  WARN: {w['legacy']} rows still NULL — run (when the proxy is healthy): python -m app.scripts.rebuild_bowler_wickets all")

        # 5. Per-club batting coverage — spot clubs whose backfill hasn't run.
        rows = (await s.execute(t("""
            SELECT o.name AS name,
                   count(*) FILTER (WHERE bi.dismissal_type='c') AS catches,
                   count(*) FILTER (WHERE bi.dismissal_type='c' AND bi.caught_behind IS NOT NULL) AS done,
                   count(*) FILTER (WHERE bi.caught_behind IS TRUE) AS cb
            FROM batting_innings bi
            JOIN players p ON p.id = bi.player_id
            JOIN organisations o ON o.id = p.organisation_id
            GROUP BY o.name
            HAVING count(*) FILTER (WHERE bi.dismissal_type='c') > 0
            ORDER BY catches DESC
        """))).mappings().all()
        print("\n[per-club batting coverage]")
        print(f"  {'club':<30}{'catches':>9}{'done%':>7}{'cb':>7}{'cb%':>7}")
        incomplete = []
        for r in rows:
            done = (100 * r["done"] / r["catches"]) if r["catches"] else 0.0
            rate = (100 * r["cb"] / r["catches"]) if r["catches"] else 0.0
            flag = "  <- backfill" if done < 95 else ""
            if done < 95:
                incomplete.append(r["name"])
            print(f"  {(r['name'] or '?')[:30]:<30}{r['catches']:>9}{done:>6.0f}%{r['cb']:>7}{rate:>6.1f}%{flag}")

        print("\n" + "-" * 70)
        if not (bi and bw and vw):
            print("RESULT: schema missing — deploy + migrate before backfilling.")
        elif bdone >= 95 and not w["legacy"] and not incomplete:
            print("RESULT: all good — columns present, both backfills complete across every club.")
        else:
            print("RESULT: action needed — see WARN lines above.")
            if incomplete:
                print(f"  clubs needing batting backfill: {', '.join(incomplete[:20])}")
        print("-" * 70)


if __name__ == "__main__":
    asyncio.run(main())
