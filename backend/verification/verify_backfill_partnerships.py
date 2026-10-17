"""Verification for `app.scripts.backfill_partnerships`, against a real Postgres.

Reported by Shoalwater Bay: a 204 and a 153 stand from 2017/18 never reach the
records page. Their games hold fall of wickets but no partnership rows, because
sync only started writing stands later and never revisits a finished game for
them. The control is the state production is in: the SHIPPED records route does
not list the 204 until the script has run.

Seeded games:

  fixable   fall of wickets stored, no stands, scorecard fits  -> stands added
  mismatch  fall of wickets stored, no stands, card's fall of wickets
            disagrees with its dismissals                     -> refused, no stands
  has       already holds stands                              -> never selected
  no_fow    no fall of wickets stored                         -> never selected
  gone      fall of wickets stored, Cricket Australia 204s    -> counted, not written
  foreign   card names no team owned by this club             -> no stand, reason says so

Run:  DATABASE_URL=postgresql+asyncpg://root@/backfillpart?host=/var/run/postgresql \
      python verification/verify_backfill_partnerships.py
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_club_records as base   # its engine, schema and views; main() is guarded
from app.scripts import backfill_partnerships as bf
from app.routers.records import get_records

Session = base.Session
engine = base.engine
OURS, THEIRS = base.OURS, base.THEIRS
check = base.check

S = uuid.uuid4(); G = uuid.uuid4()
T_US, T_OPP = uuid.uuid4(), uuid.uuid4()
GUIDS = {k: uuid.uuid4() for k in "ABCD"}
PIDS = {k: uuid.uuid4() for k in "ABCD"}
GAMES = {k: uuid.uuid4() for k in ("fixable", "mismatch", "has", "no_fow", "gone", "foreign")}


def card(fow_rows: list[tuple]) -> dict:
    """A scorecard whose 3rd wicket stand is C and D for 204 (224 less 20)."""
    def bat(k, order, runs, dt_id, dt):
        return {"participantId": str(GUIDS[k]), "batOrder": order, "runsScored": runs,
                "dismissalTypeId": dt_id, "dismissalType": dt, "playerShortName": f"Player {k}"}
    return {
        "teams": [
            {"id": str(T_US), "owningOrganisation": {"id": str(OURS)},
             "players": [{"participantId": str(g)} for g in GUIDS.values()]},
            {"id": str(T_OPP), "owningOrganisation": {"id": str(THEIRS)}, "players": []},
        ],
        "innings": [{
            "inningsOrder": 1, "battingTeamId": str(T_US),
            "batting": [bat("A", 1, 10, 2, "Bowled"), bat("B", 2, 10, 2, "Bowled"),
                        bat("C", 3, 130, 2, "Bowled"), bat("D", 4, 90, 1, "Not Out")],
            "fallOfWickets": [{"order": o, "runs": r, "participantId": str(GUIDS[k]),
                               "playerShortName": f"Player {k}"} for o, r, k in fow_rows],
        }],
    }


GOOD = card([(1, 10, "A"), (2, 20, "B"), (3, 224, "C")])
BAD = card([(1, 10, "A"), (2, 20, "B")])            # 2 fall of wicket rows, 3 dismissals
FOREIGN = card([(1, 10, "A"), (2, 20, "B"), (3, 224, "C")])
FOREIGN["teams"][0]["owningOrganisation"] = {"id": str(THEIRS)}   # no team on the card is this club's


async def merge_logs_table() -> None:
    """`merge_logs` is a lifespan table (main.py), so create_all does not make it.
    Copied column for column from the lifespan, later ALTERs included."""
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merge_logs (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID,
                keep_player_id UUID,
                keep_player_name TEXT,
                removed_player_id UUID,
                removed_player_name TEXT,
                removed_player_playhq_id TEXT,
                keep_original_playhq_id TEXT,
                moved_season_stat_ids JSONB DEFAULT '[]',
                batting_innings_ids JSONB DEFAULT '[]',
                bowling_spell_ids JSONB DEFAULT '[]',
                fielding_stat_ids JSONB DEFAULT '[]',
                fall_of_wicket_ids JSONB DEFAULT '[]',
                batter1_partnership_ids JSONB DEFAULT '[]',
                batter2_partnership_ids JSONB DEFAULT '[]',
                milestone_ids JSONB DEFAULT '[]',
                bowler_wicket_ids JSONB DEFAULT '[]',
                fielder_wicket_ids JSONB DEFAULT '[]',
                grade_stat_ids JSONB DEFAULT '[]',
                appearance_game_ids JSONB DEFAULT '[]',
                undone_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text(
            "ALTER TABLE merge_logs ADD COLUMN IF NOT EXISTS imported_stat_ids JSONB DEFAULT '[]'"))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        await ex("INSERT INTO organisations (id, name, is_active, slug) VALUES (:i, 'Our Club', true, 'our-club')", i=OURS)
        await ex("INSERT INTO organisations (id, name, is_active) VALUES (:i, 'Their Club', true)", i=THEIRS)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2017/18', 2017)", i=S, o=OURS)
        await ex("INSERT INTO grades (id, season_id, name, category) VALUES (:i, :s, 'Grade D', 'senior')", i=G, s=S)
        for k in "ABCD":
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:i, :o, :n, :g)",
                     i=PIDS[k], o=OURS, n=f"Player {k}", g=str(GUIDS[k]))
        for n, gid in GAMES.items():
            await ex(
                "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_club, away_club, "
                " opp_club_name, result, home_org_id, away_org_id, venue, match_format, is_final) "
                "VALUES (:i, :g, :d, 'Our Club', 'Opp', 'Our Club', 'Opp', 'Opp', 'WIN', :ho, NULL, 'Oval', "
                " 'One Day', false)", i=gid, g=G, d=date(2017, 12, 16), ho=OURS)
            if n != "no_fow":
                for o, r, k in ((1, 10, "A"), (2, 20, "B"), (3, 224, "C")):
                    await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, player_id) "
                             "VALUES (:g, 1, :o, :r, :p)", g=gid, o=o, r=r, p=PIDS[k])
        await ex("INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, batter2_id, runs, is_club_innings) "
                 "VALUES (:g, 1, 1, :a, :b, 10, true)", g=GAMES["has"], a=PIDS["A"], b=PIDS["B"])
        await s.commit()


async def stands(game: str) -> list[int]:
    async with Session() as s:
        return [r[0] for r in (await s.execute(text(
            "SELECT runs FROM partnerships WHERE game_id = :g ORDER BY wicket_number"), {"g": GAMES[game]})).all()]


async def board() -> set:
    async with Session() as s:
        p = await get_records(
            str(OURS), season_id=None, grade_id=None, grade_name=None, finals_only=False,
            captain_only=False, gender=None, categories="all", formats=None, competitions=None,
            debug_timing=False, db=s, viewer=None)
    return {r["runs"] for r in p["partnerships"]["top_partnerships"]}


async def main() -> None:
    await base.build_schema()
    await merge_logs_table()
    await seed()
    bf.async_session_maker = Session

    asked: list[str] = []
    by_id = {str(GAMES["fixable"]): GOOD, str(GAMES["mismatch"]): BAD, str(GAMES["gone"]): None,
             str(GAMES["foreign"]): FOREIGN}

    async def fetch(match_id: str):
        asked.append(match_id)
        return by_id.get(match_id)

    # Control: the state production is in.
    check("before: the shipped records route does not list the 204", 204 not in await board(), str(await board()))
    check("before: the game holds no stands", await stands("fixable") == [])

    # Dry run reads and reports but writes nothing.
    t = await bf.run("our-club", pause=0, apply=False, fetch=fetch)
    check("dry run: reports the stands it would add", t["stands_added"] == 3, str(t))
    check("dry run: writes nothing", await stands("fixable") == [])
    check("dry run: the board is unchanged", 204 not in await board())
    check("only games with fall of wickets and no stands were asked for",
          set(asked) == {str(GAMES[k]) for k in ("fixable", "mismatch", "gone", "foreign")}, str(asked))

    asked.clear()
    buf = io.StringIO()
    with redirect_stdout(buf):
        t = await bf.run("our-club", pause=0, apply=True, fetch=fetch, explain=True)
    out = buf.getvalue()
    check("apply: three stands written for the fixable game", await stands("fixable") == [10, 10, 204], str(await stands("fixable")))
    check("apply: the shipped records route now lists the 204", 204 in await board(), str(await board()))
    check("apply: the mismatched card is refused and writes no stand", await stands("mismatch") == [])
    check("apply: the two games that got no stand are counted", t["refused"] == 2, str(t))
    check("reason: names the fall of wickets v dismissals mismatch",
          "2 fall of wickets v 3 dismissals on the card" in out, out)
    check("reason: names a card with no team owned by the club",
          "no team on the card is owned by this club" in out, out)
    check("--explain dumps the rows the derivation read", "fow   2" in out and "bat   3" in out, out)
    check("a game that did get stands is not reported as refused",
          f"{GAMES['fixable']}: no stand" not in out, out)
    check("apply: a game Cricket Australia cannot answer for is counted, not written",
          t["no_data"] == 1 and await stands("gone") == [], str(t))
    check("apply: a game that already held stands is untouched", await stands("has") == [10])
    check("apply: no fall of wickets rows were duplicated", t["fow_added"] == 0, str(t))

    # Idempotent: the fixable game now holds stands and drops out of the selection.
    asked.clear()
    t2 = await bf.run("our-club", pause=0, apply=True, fetch=fetch)
    check("re-run adds nothing", t2["stands_added"] == 0, str(t2))
    check("re-run does not ask Cricket Australia for the finished game", str(GAMES["fixable"]) not in asked, str(asked))
    check("re-run leaves the stands as they were", await stands("fixable") == [10, 10, 204])

    # The cap and date window bound the traffic.
    asked.clear()
    t3 = await bf.run("our-club", pause=0, apply=False, fetch=fetch, limit=1)
    check("--limit caps the games asked for", len(asked) == 1, str(asked))
    asked.clear()
    await bf.run("our-club", pause=0, apply=False, fetch=fetch, d_from=date(2018, 1, 1))
    check("--from outside the games' date selects none", asked == [], str(asked))

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    for f in base.FAILURES:
        print(f"  - {f}")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
