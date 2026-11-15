"""The compare page's bowling tab needs wides, no-balls and balls bowled.

Asked for by Jack at Applecross (Nov 2026): the Compare page was missing overs,
the actual best figures (5/28, not a bare "5"), extras (wides and no-balls) and
more. Best figures, overs and runs conceded were already in the career-bowling
payload the page reads; wides and no-balls were not in it at all, and the
career `total_overs` is a SUM of cricket-notation figures (10.4 + 10.4 reads as
20.8 where the true total is 21.2).

What the three career readers must now return, additively:

  * `total_wides`, `total_no_balls`: summed from the same rows as everything
    else on that path. NULL (None), never 0, when the only rows are hand-typed
    spells the scorer did not count them on (a NULL there is "not tracked").
  * `total_balls`: balls bowled, converted row by row from overs notation.

Runs the SHIPPED `get_career_bowling` (unscoped, scoped) and
`get_career_bowling_from_spells` (the last-N and date-window path) over the
effective views, with `held_topup` in play for one player.

THE CONTROL RUN is this file against the previous commit: every new key is read
through `.get`, so the old code fails the checks and does not crash.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:pw@127.0.0.1:5432/bstest \
  python verification/verify_compare_bowling_fields.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_rate_coverage as base
from app.services import aggregations as agg
from app.services.grade_scope import resolve_scope

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label + (f" -- {detail}" if detail else ""))
        print(f"  FAIL {label}" + (f" -- {detail}" if detail else ""))


AGG_ONLY = uuid.UUID("b1000000-0000-0000-0000-000000000001")   # two CA season rows, no scorecards
SPELLS = uuid.UUID("b1000000-0000-0000-0000-000000000002")     # three synced spells, no CA row
TOPPED = uuid.UUID("b1000000-0000-0000-0000-000000000003")     # a thin CA row, three held spells
UNTRACKED = uuid.UUID("b1000000-0000-0000-0000-000000000004")  # hand-typed spells with no extras counted
TYPED = uuid.UUID("b1000000-0000-0000-0000-000000000005")      # hand-typed spells WITH extras counted


async def seed_extra(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for pid, nm in ((AGG_ONLY, "Aggregate, Anna"), (SPELLS, "Spells, Sam"),
                    (TOPPED, "Topped, Tia"), (UNTRACKED, "Untracked, Una"), (TYPED, "Typed, Ty")):
        await ex("INSERT INTO players (id, organisation_id, name) VALUES (:i, :o, :n)",
                 i=pid, o=base.ORG, n=nm)

    # ── CA aggregate only: 10.4 overs in each of two seasons ────────────────
    # Cricket notation, so the true total is 128 balls = 21.2 overs. The legacy
    # `SUM(overs)` says 20.8, which is the figure the compare page must not print.
    for sid, wd, nb in ((base.SEASON, 4, 1), (base.SEASON_OLD, 3, 2)):
        await ex("INSERT INTO player_season_stats (player_id, season_id, matches, bowling_innings, "
                 " wickets, overs, bowling_balls, runs_conceded, maidens, wides, no_balls) "
                 "VALUES (:p, :s, 5, 5, 8, 10.4, 64, 60, 1, :w, :n)",
                 p=AGG_ONLY, s=sid, w=wd, n=nb)

    async def game(d: date) -> uuid.UUID:
        g = uuid.uuid4()
        await ex("INSERT INTO games (id, grade_id, played_at, venue, result, match_format) "
                 "VALUES (:i, :g, :d, 'Home Oval', 'WIN', 'One Day')", i=g, g=base.GRADE, d=d)
        return g

    # ── three synced spells: wides 4+2+1, no-balls 1+0+3, balls 64+64+30 ─────
    spells = ((10.4, 2, 40, 4, 1), (10.4, 3, 35, 2, 0), (5.0, 0, 30, 1, 3))
    for pid in (SPELLS, TOPPED):
        for n, (ov, wk, rn, wd, nb) in enumerate(spells):
            g = await game(date(2025, 11, 1 + n + (10 if pid == TOPPED else 0)))
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=g, p=pid)
            await ex("INSERT INTO bowling_spells (game_id, player_id, overs, maidens, runs, wickets, wides, no_balls) "
                     "VALUES (:g, :p, :o, 0, :r, :w, :wd, :nb)", g=g, p=pid, o=ov, r=rn, w=wk, wd=wd, nb=nb)

    # TOPPED's CA row for the same season is thinner than the scorecards held
    # (1 innings against 3), which is what lets `held_topup` raise it.
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, bowling_innings, "
             " wickets, overs, bowling_balls, runs_conceded, maidens, wides, no_balls) "
             "VALUES (:p, :s, 1, 1, 2, 10.4, 64, 40, 0, 4, 1)", p=TOPPED, s=base.SEASON)
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, bowling_innings, "
             " wickets, overs, bowling_balls, runs_conceded, maidens, wides, no_balls) "
             "VALUES (:p, :s, 4, 4, 6, 10.4, 64, 55, 0, 3, 2)", p=TOPPED, s=base.SEASON_OLD)

    # ── hand-typed spells where the scorer never counted wides or no-balls ───
    mg = uuid.uuid4()
    await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, "
             " result, match_format) VALUES (:i, :o, :s, :g, DATE '2025-12-01', 'WIN', 'One Day')",
             i=mg, o=base.ORG, s=base.SEASON, g=base.GRADE)
    # The column defaults to 0 when omitted, so "not tracked" has to be an explicit
    # NULL, which is what a blank cell in a CSV import writes (`_parse_int`).
    await ex("INSERT INTO manual_bowling_spells (manual_game_id, player_id, innings_number, "
             " overs, maidens, runs, wickets, wides, no_balls) "
             "VALUES (:g, :p, 1, 8.0, 0, 30, 2, NULL, NULL)", g=mg, p=UNTRACKED)
    await ex("INSERT INTO manual_bowling_spells (manual_game_id, player_id, innings_number, "
             " overs, maidens, runs, wickets, wides, no_balls) "
             "VALUES (:g, :p, 1, 8.0, 0, 30, 2, 2, 1)", g=mg, p=TYPED)


async def main() -> None:
    await base.build_schema()
    async with base.Session() as session:
        await base.seed(session)
        await seed_extra(session)
        await session.commit()

    async with base.Session() as session:
        print("\n-- last-N and date windows (get_career_bowling_from_spells) --")
        for label, kw in (("last 3 games", dict(last_n_games=3)),
                          ("a date window", dict(start_date="2025-10-01", end_date="2025-11-30"))):
            r = await agg.get_career_bowling_from_spells(session, str(SPELLS), **kw) or {}
            check(f"{label}: wides add across spells (4+2+1)", r.get("total_wides") == 7, repr(r.get("total_wides")))
            check(f"{label}: no-balls add across spells (1+0+3)", r.get("total_no_balls") == 4,
                  repr(r.get("total_no_balls")))
            check(f"{label}: balls bowled are 158 (64+64+30)", r.get("total_balls") == 158, repr(r.get("total_balls")))
        un = await agg.get_career_bowling_from_spells(session, str(UNTRACKED), start_date="2025-10-01") or {}
        check("hand-typed spells with no extras counted give None, not 0",
              "total_wides" in un and un.get("total_wides") is None and un.get("total_no_balls") is None,
              f"{un.get('total_wides', 'ABSENT')!r} / {un.get('total_no_balls', 'ABSENT')!r}")
        check("and the same player still has their wickets (the read found the spell)",
              un.get("total_wickets") == 2, repr(un.get("total_wickets")))
        ty = await agg.get_career_bowling_from_spells(session, str(TYPED), start_date="2025-10-01") or {}
        check("pair: hand-typed spells WITH extras counted do show them (2 and 1)",
              (ty.get("total_wides"), ty.get("total_no_balls")) == (2, 1),
              f"{ty.get('total_wides', 'ABSENT')!r} / {ty.get('total_no_balls', 'ABSENT')!r}")

        print("\n-- unscoped career (CA season rows) --")
        a = await agg.get_career_bowling(session, str(AGG_ONLY)) or {}
        check("wides are summed across seasons (4+3)", a.get("total_wides") == 7, repr(a.get("total_wides")))
        check("no-balls are summed across seasons (1+2)", a.get("total_no_balls") == 3, repr(a.get("total_no_balls")))
        check("balls bowled convert row by row: 128", a.get("total_balls") == 128, repr(a.get("total_balls")))
        check("and the legacy overs sum is the decimal one it always was (control for the check above)",
              float(a.get("total_overs") or 0) == 20.8, repr(a.get("total_overs")))

        print("\n-- unscoped career raised to the scorecards we hold (held_topup) --")
        t = await agg.get_career_bowling(session, str(TOPPED)) or {}
        check("the held scorecards raised the CA row (topped_up is present)", bool(t.get("topped_up")),
              repr(t.get("topped_up", "ABSENT")))
        check("wides follow the raise: CA 3 + held 7 = 10", t.get("total_wides") == 10, repr(t.get("total_wides")))
        check("no-balls follow it: CA 2 + held 4 = 6", t.get("total_no_balls") == 6, repr(t.get("total_no_balls")))
        check("balls follow it: CA 64 + held 158 = 222", t.get("total_balls") == 222, repr(t.get("total_balls")))

        print("\n-- the club's default grade scope (scorecards, not CA rows) --")
        scope = await resolve_scope(session, str(base.ORG))
        check("the club's default scope is active", bool(getattr(scope, "active", False)), repr(scope))
        s = await agg.get_career_bowling(session, str(SPELLS), scope=scope) or {}
        check("scoped wides: 7", s.get("total_wides") == 7, repr(s.get("total_wides")))
        check("scoped no-balls: 4", s.get("total_no_balls") == 4, repr(s.get("total_no_balls")))
        check("scoped balls: 158", s.get("total_balls") == 158, repr(s.get("total_balls")))
        su = await agg.get_career_bowling(session, str(UNTRACKED), scope=scope) or {}
        check("scoped, untracked extras stay None", "total_wides" in su and su.get("total_wides") is None,
              repr(su.get("total_wides", "ABSENT")))
        check("scoped, the same player still has their wickets", su.get("total_wickets") == 2,
              repr(su.get("total_wickets")))
        st = await agg.get_career_bowling(session, str(TYPED), scope=scope) or {}
        check("pair: scoped, counted hand-typed extras show (2 and 1)",
              (st.get("total_wides"), st.get("total_no_balls")) == (2, 1),
              f"{st.get('total_wides', 'ABSENT')!r} / {st.get('total_no_balls', 'ABSENT')!r}")

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await base.engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
