"""An innings CA scored as a total and nothing else, against a real Postgres.

Reported off https://betterat.cricket/games/1df207e1-… — a two-day match
Applecross won by 221 runs. The page showed Murdoch University as having
scored **8**.

Ground truth, fetched from Grassroots before anything was changed
(`/scores/matches/1df207e1-…?responseModifier=includeScorecard`): Murdoch's
innings carries `runsScored: 102`, `numberOfWicketsFallen: 10`,
`totalExtras: 8` — and **zero batting rows**. Nobody ever entered the
individual scores.

`get_scorecard` builds an innings' `runs` as the sum of its batting rows,
deliberately: `runs` means the BATTERS' runs and the frontend adds extras on
top, so substituting GR's own `runsScored` (which already includes them)
would double-count. With no rows to sum, that gave 0 — and the page then
rendered the innings as its extras alone.

The fix keeps that contract exactly. `runs` is still the batters' runs; it
is simply recovered as `runsScored - totalExtras`, which is what
`runsScored` is made of by definition, and only for an innings with no
contributing rows at all.

Runs the SHIPPED `get_scorecard` with the Grassroots client stubbed to the
reported match's real figures.

Run:  DATABASE_URL=postgresql+asyncpg://root@/scard_test?host=/var/run/postgresql \
      python verification/verify_scorecard_innings_total.py
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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.services import grassroots_scores_client as grc
from app.routers.games import get_scorecard

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
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
        print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


ORG = uuid.uuid4()
SEASON = uuid.uuid4()
GRADE = uuid.uuid4()
GAME = uuid.uuid4()
OUR_TID = "aaaa1111"
OPP_TID = "bbbb2222"
OUR_PIDS = [str(uuid.uuid4()) for _ in range(11)]
OPP_PIDS = [str(uuid.uuid4()) for _ in range(11)]


def _bat_rows(pids, bat_total, n_out):
    """Individual scores, the way an innings CA DID score reaches us.

    Distributed so they SUM to the innings' batters' runs — a fixture whose
    own rows don't reconcile with its declared total proves nothing.
    """
    per = bat_total // 10
    extra_on_first = bat_total - per * 10
    return [{
        "participantId": pids[i], "playerShortName": f"Player {i + 1}",
        "batOrder": i + 1, "runsScored": per + (extra_on_first if i == 0 else 0),
        "ballsFaced": 30,
        "fours": 1, "sixes": 0,
        "dismissalTypeId": 2 if i < n_out else 1,
        "dismissalType": "Caught" if i < n_out else "Not Out",
        "dismissalText": "c A b B" if i < n_out else "",
    } for i in range(10)]


def _bowl_rows(pids, runs_each):
    return [{
        "participantId": pids[i], "playerShortName": f"Player {i + 1}",
        "oversBowled": "8.0", "maidens": 0,
        "runsConceded": runs_each, "wickets": 2,
    } for i in range(5)]


# The reported match's real figures. Innings 2 is the one that matters: a
# real total, real extras, and NO batting rows.
GR_PAYLOAD = {
    "id": str(GAME),
    "status": "Final", "matchType": "Two Day",
    "matchSummary": {"resultText": "Our Club won by 221 runs", "teams": [
        {"id": OUR_TID, "isHome": True, "scoreText": "8-323 & 8-158"},
        {"id": OPP_TID, "isHome": False, "scoreText": "102"},
    ]},
    "teams": [
        {"id": OUR_TID, "name": "1st XI",
         "owningOrganisation": {"name": "Our Club"},
         "players": [{"participantId": p, "playerShortName": f"Player {i+1}"}
                     for i, p in enumerate(OUR_PIDS)]},
        {"id": OPP_TID, "name": "1st Grade",
         "owningOrganisation": {"name": "Murdoch University Cricket Club"},
         "players": [{"participantId": p, "playerShortName": f"Opp {i+1}"}
                     for i, p in enumerate(OPP_PIDS)]},
    ],
    "innings": [
        {"inningsOrder": 1, "inningsNumber": 1, "battingTeamId": OUR_TID,
         "runsScored": 323, "numberOfWicketsFallen": 8, "totalExtras": 17,
         "batting": _bat_rows(OUR_PIDS, 306, 8),
         "bowling": _bowl_rows(OPP_PIDS, 60), "fielding": [], "fallOfWickets": []},
        # THE REPORTED INNINGS: a total, and nothing else.
        {"inningsOrder": 2, "inningsNumber": 1, "battingTeamId": OPP_TID,
         "runsScored": 102, "numberOfWicketsFallen": 10, "totalExtras": 8,
         "batting": [], "bowling": _bowl_rows(OUR_PIDS, 18),
         "fielding": [], "fallOfWickets": []},
        {"inningsOrder": 3, "inningsNumber": 2, "battingTeamId": OUR_TID,
         "runsScored": 158, "numberOfWicketsFallen": 8, "totalExtras": 10,
         "batting": _bat_rows(OUR_PIDS, 148, 8),
         "bowling": _bowl_rows(OPP_PIDS, 28), "fielding": [], "fallOfWickets": []},
    ],
    "venue": {"name": "Home Ground"},
    "matchSchedule": [{"startDateTime": "2025-02-01T00:00:00"}],
    "grade": {"id": str(GRADE), "name": "Men's First Grade"},
}


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        for _ in range(2):
            for name, sql in view_statements():
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    await ex("INSERT INTO organisations (id, name, is_active) "
             "VALUES (:i, 'Our Club', true)", i=ORG)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 2024/25', 2024)", i=SEASON, o=ORG)
    await ex("INSERT INTO grades (id, season_id, name, category) "
             "VALUES (:i, :s, 'Men''s First Grade', 'senior')", i=GRADE, s=SEASON)
    for i, pid in enumerate(OUR_PIDS):
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id) "
                 "VALUES (:i, :o, :n, :g)",
                 i=uuid.UUID(pid), o=ORG, n=f"Player {i+1}", g=pid)
    await ex(
        "INSERT INTO games (id, grade_id, played_at, home_team, away_team, "
        " home_club, away_club, opp_club_name, result, winning_team, "
        " home_org_id, venue, match_format, is_final) "
        "VALUES (:i, :g, :d, 'Our Club', 'Murdoch University Cricket Club', "
        " 'Our Club', 'Murdoch University Cricket Club', "
        " 'Murdoch University Cricket Club', 'WIN', 'Our Club', :o, "
        " 'Home Ground', 'Two Day', false)",
        i=GAME, g=GRADE, d=date(2025, 2, 1), o=ORG)
    # Our own two innings ARE stored — only the opposition's was never
    # scored individually, which is the whole point of the case.
    for inn, per in ((1, 30), (3, 14)):  # DB copy; the live GR merge replaces it
        for idx in range(10):
            await ex(
                "INSERT INTO batting_innings (game_id, player_id, innings_number, "
                " batting_position, runs, balls, not_out, dismissal_type, did_not_bat) "
                "VALUES (:g, :p, :inn, :pos, :r, 30, :no, :dt, false)",
                g=GAME, p=uuid.UUID(OUR_PIDS[idx]), inn=inn, pos=idx + 1,
                r=per, no=idx >= 8, dt="caught" if idx < 8 else None)
    for idx in range(5):
        await ex(
            "INSERT INTO bowling_spells (game_id, player_id, innings_number, "
            " overs, maidens, runs, wickets) VALUES (:g, :p, 2, 8, 0, 18, 2)",
            g=GAME, p=uuid.UUID(OUR_PIDS[idx]))
    await session.commit()


async def run_checks() -> None:
    async def _stub(_gid, force=False):
        return GR_PAYLOAD
    grc.get_match_scorecard = _stub

    async with Session() as s:
        card = await get_scorecard(str(GAME), s)

    tot = {int(k): v for k, v in (card.get("innings_totals") or {}).items()}
    print("\n── the reported innings ──")
    opp = tot.get(2)
    check("the opposition's innings is on the card at all", opp is not None)
    if opp:
        # `runs` is the BATTERS' runs and the frontend adds extras on top, so
        # the figure a reader sees is runs + extras. That is what has to come
        # to 102 — asserting `runs == 102` would be asserting the double-count
        # this fix exists to avoid.
        check("the innings reads 102, not its 8 extras",
              (opp["runs"] or 0) + (opp["extras"] or 0) == 102,
              f"runs {opp['runs']} + extras {opp['extras']}")
        check("its batters' runs are recovered as total minus extras",
              opp["runs"] == 94, f"got {opp['runs']}")
        check("the extras are still reported separately, not folded in",
              opp["extras"] == 8, f"got {opp['extras']}")
        check("GR's own wicket count is kept", opp["wickets"] == 10,
              f"got {opp['wickets']}")
        check("it is filed under the opposition", 
              (opp.get("batting_team") or "").lower().startswith("murdoch")
              or "1st grade" in (opp.get("batting_team") or "").lower(),
              str(opp.get("batting_team")))

    print("\n── the innings we DID score are untouched ──")
    for n, total, extras in ((1, 323, 17), (3, 158, 10)):
        t = tot.get(n)
        check(f"innings {n} still reads {total}",
              t is not None and (t["runs"] or 0) + (t["extras"] or 0) == total,
              f"runs {t['runs'] if t else None} + extras {t['extras'] if t else None}")
        check(f"innings {n}'s runs are its own batting rows, not a derived figure",
              t is not None and t["runs"] == total - extras,
              f"got {t['runs'] if t else None}")

    print("\n── nothing else moved ──")
    check("our batting card still carries both our innings",
          len({r["innings_number"] for r in (card.get("batting") or [])}) == 2,
          str(sorted({r["innings_number"] for r in (card.get("batting") or [])})))
    # The opposition's 11 are their named side rendered as did-not-bat, which
    # is what a roster with no scorecard should read as. The thing that must
    # never happen is a batter carrying RUNS nobody ever recorded, invented to
    # make the innings add up.
    opp_bat = card.get("opp_batting") or []
    check("no opposition batter is invented with runs to justify the total",
          all((r.get("runs") or 0) == 0 for r in opp_bat),
          str([(r.get("player_name"), r.get("runs")) for r in opp_bat if r.get("runs")][:3]))
    check("their named side still shows, as did-not-bat",
          all(r.get("did_not_bat") for r in opp_bat) if opp_bat else True,
          f"{sum(1 for r in opp_bat if not r.get('did_not_bat'))} with a real innings")
    check("our bowlers' figures for that innings are still there",
          any(r["innings_number"] == 2 for r in (card.get("bowling") or [])))


async def run_control_checks() -> None:
    """An innings with NO total and no rows must stay silent, not invent one."""
    payload = {**GR_PAYLOAD, "innings": [
        {**GR_PAYLOAD["innings"][1], "runsScored": None, "totalExtras": None},
    ]}

    async def _stub(_gid, force=False):
        return payload
    grc.get_match_scorecard = _stub

    async with Session() as s:
        card = await get_scorecard(str(GAME), s)
    tot = {int(k): v for k, v in (card.get("innings_totals") or {}).items()}
    print("\n── an innings with nothing recorded at all ──")
    t = tot.get(2)
    check("an innings with no rows AND no total reports 0, never a guess",
          t is None or (t["runs"] or 0) == 0, f"got {t['runs'] if t else None}")


async def main() -> None:
    await build_schema()
    async with Session() as s:
        await seed(s)
    await run_checks()
    await run_control_checks()
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print(f"  - {f}")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
