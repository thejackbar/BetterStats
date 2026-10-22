"""Verification for `app.scripts.backfill_partnerships`, against a real Postgres.

Reported by Shoalwater Bay: a 204 and a 153 stand from 2017/18 never reach the
records page. Their games hold fall of wickets but no partnership rows, because
sync only started writing stands later and never revisits a finished game for
them. The control is the state production is in: the SHIPPED records route does
not list the 204 until the script has run.

Seeded games:

  fixable   fall of wickets stored, no stands, scorecard fits  -> stands added
  short     fall of wickets stored, no stands, card holds 2 of its 3
            wickets (a scorer who recorded some)             -> the stands those settle
  mismatch  fall of wickets stored, no stands, card holds MORE fall of
            wickets than dismissals                           -> refused, no stands
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
GAMES = {k: uuid.uuid4() for k in ("fixable", "short", "mismatch", "has", "no_fow", "gone", "foreign", "shared")}
TGUIDS = {k: uuid.uuid4() for k in "XYZ"}     # THEIRS' players: they bat in innings 2 of the shared fixture
TPIDS = {k: uuid.uuid4() for k in "XYZ"}


def shared_card() -> dict:
    """Ours bat first (A, B, C, D), theirs second (X, Y, Z): each side's innings gives its own stands."""
    c = card([(1, 10, "A"), (2, 20, "B"), (3, 224, "C")])
    c["teams"][1]["players"] = [{"participantId": str(g)} for g in TGUIDS.values()]

    def tbat(k, order, runs, dt_id, dt):
        return {"participantId": str(TGUIDS[k]), "batOrder": order, "runsScored": runs,
                "dismissalTypeId": dt_id, "dismissalType": dt, "playerShortName": f"Player {k}"}
    c["innings"].append({
        "inningsOrder": 2, "battingTeamId": str(T_OPP),
        "batting": [tbat("X", 1, 20, 2, "Bowled"), tbat("Y", 2, 25, 2, "Bowled"), tbat("Z", 3, 30, 1, "Not Out")],
        "fallOfWickets": [{"order": 1, "runs": 30, "participantId": str(TGUIDS["X"]), "playerShortName": "Player X"},
                          {"order": 2, "runs": 50, "participantId": str(TGUIDS["Y"]), "playerShortName": "Player Y"}],
    })
    return c


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
SHORT = card([(1, 10, "A"), (2, 20, "B")])          # 2 fall of wicket rows, 3 dismissals: a short card
BAD = card([(1, 10, "A"), (2, 20, "B"), (3, 224, "C"), (4, 230, "D")])   # 4 rows, 3 dismissals: refused
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
            if n == "shared":
                continue   # seeded later by seed_shared(), after the single-club checks
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


async def seed_shared() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        # A fixture between two synced clubs: ONE game row, home OURS, away THEIRS. Ours bat first
        # (A, B, C, D), theirs second (X, Y, Z). Fall of wickets for both innings are stored.
        for k in "XYZ":
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:i, :o, :n, :g)",
                     i=TPIDS[k], o=THEIRS, n=f"Player {k}", g=str(TGUIDS[k]))
        await ex(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_club, away_club, "
            " opp_club_name, result, home_org_id, away_org_id, venue, match_format, is_final) "
            "VALUES (:i, :g, :d, 'Our Club', 'Their Club', 'Our Club', 'Their Club', 'Their Club', 'WIN', :ho, :ao, "
            " 'Oval', 'One Day', false)", i=GAMES["shared"], g=G, d=date(2017, 12, 9), ho=OURS, ao=THEIRS)
        for inn, rows_ in ((1, ((1, 10, "A"), (2, 20, "B"), (3, 224, "C"))),):
            for o, r, k in rows_:
                await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, player_id) "
                         "VALUES (:g, :n, :o, :r, :p)", g=GAMES["shared"], n=inn, o=o, r=r, p=PIDS[k])
        for o, r, k in ((1, 30, "X"), (2, 50, "Y")):
            await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, player_id) "
                     "VALUES (:g, 2, :o, :r, :p)", g=GAMES["shared"], o=o, r=r, p=TPIDS[k])
        await s.commit()


async def stands(game: str) -> list[int]:
    async with Session() as s:
        return [r[0] for r in (await s.execute(text(
            "SELECT runs FROM partnerships WHERE game_id = :g ORDER BY wicket_number"), {"g": GAMES[game]})).all()]


async def stand_rows(game_key: str, innings: int) -> list[int]:
    async with Session() as s:
        return [r[0] for r in (await s.execute(text(
            "SELECT runs FROM partnerships WHERE game_id = :g AND innings_number = :i ORDER BY wicket_number"),
            {"g": GAMES[game_key], "i": innings})).all()]


async def board() -> set:
    async with Session() as s:
        p = await get_records(
            str(OURS), season_id=None, grade_id=None, grade_name=None, finals_only=False,
            captain_only=False, gender=None, categories="all", formats=None, competitions=None,
            debug_timing=False, db=s, viewer=None)
    return {r["runs"] for r in p["partnerships"]["top_partnerships"]}


async def _refused(coro) -> bool:
    try:
        await coro
    except SystemExit:
        return True
    return False


async def main() -> None:
    await base.build_schema()
    await merge_logs_table()
    await seed()
    bf.async_session_maker = Session

    asked: list[str] = []
    by_id = {str(GAMES["fixable"]): GOOD, str(GAMES["short"]): SHORT, str(GAMES["mismatch"]): BAD, str(GAMES["gone"]): None,
             str(GAMES["foreign"]): FOREIGN}

    async def fetch(match_id: str):
        asked.append(match_id)
        return by_id.get(match_id)

    # Control: the state production is in.
    check("before: the shipped records route does not list the 204", 204 not in await board(), str(await board()))
    check("before: the game holds no stands", await stands("fixable") == [])

    # Dry run reads and reports but writes nothing.
    t = await bf.run("our-club", pause=0, apply=False, fetch=fetch)
    check("dry run: reports the stands it would add", t["stands_added"] == 5, str(t))
    check("dry run: writes nothing", await stands("fixable") == [])
    check("dry run: the board is unchanged", 204 not in await board())
    check("only games with fall of wickets and no stands were asked for",
          set(asked) == {str(GAMES[k]) for k in ("fixable", "short", "mismatch", "gone", "foreign")}, str(asked))

    asked.clear()
    buf = io.StringIO()
    with redirect_stdout(buf):
        t = await bf.run("our-club", pause=0, apply=True, fetch=fetch, explain=True)
    out = buf.getvalue()
    check("apply: three stands written for the fixable game", await stands("fixable") == [10, 10, 204], str(await stands("fixable")))
    check("apply: the shipped records route now lists the 204", 204 in await board(), str(await board()))
    check("apply: a card short of wickets gets the stands its figures settle (1st and 2nd)",
          await stands("short") == [10, 10], str(await stands("short")))
    check("apply: a card with more fall of wickets than dismissals is refused and writes no stand",
          await stands("mismatch") == [])
    check("apply: the two games that got no stand are counted", t["refused"] == 2, str(t))
    check("reason: names the fall of wickets v dismissals mismatch",
          "4 fall of wickets v 3 dismissals on the card" in out, out)
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


    # ── Walking on without asking twice, and every club at once ─────────────────
    print("--resume and `all`")
    await seed_shared()
    by_id[str(GAMES["shared"])] = shared_card()

    # Refused games stay selected, so a walk that always restarted at the top would ask for the same
    # ones for ever. With --limit 2 and --resume the walk must move on and ask for each game once.
    asked.clear()
    t = await bf.run("our-club", pause=0, apply=False, fetch=fetch, limit=2)
    first = list(asked)
    check("a run that stops at its limit hands back a resume token", bool(t["resume"]), str(t))
    walked = list(first)
    token, guard = t["resume"], 0
    while token and guard < 20:
        asked.clear()
        t = await bf.run("our-club", pause=0, apply=False, fetch=fetch, limit=2, resume=token)
        check("a resumed run does not ask for a game it already asked for", not set(asked) & set(walked), str(asked))
        walked += asked
        token, guard = t["resume"], guard + 1
    check("the walk ends (it does not loop on refused games)", token is None and guard < 20, str(token))
    cands = {str(GAMES[k]) for k in ("mismatch", "gone", "foreign", "shared")}   # "short" got its stands in the apply run above
    check("and it reached every candidate game exactly once",
          sorted(walked) == sorted(cands) and len(walked) == len(set(walked)), str(sorted(walked)))
    check("a malformed token is refused, not guessed at",
          await _refused(bf.run("our-club", pause=0, fetch=fetch, resume="not-a-token")))

    # The shared fixture: one game row, two synced clubs. OURS goes first and writes its own stands.
    # The game must still be offered to THEIRS, whose innings has no stand yet.
    asked.clear()
    t = await bf.run("our-club", pause=0, apply=True, fetch=fetch, limit=100)
    check("our club's innings of the shared fixture gets its stands",
          await stand_rows("shared", 1) == [10, 10, 204], str(await stand_rows("shared", 1)))
    check("theirs does not yet (ours was written first)", await stand_rows("shared", 2) == [])
    asked.clear()
    t = await bf.run("all", pause=0, apply=True, fetch=fetch, limit=100)
    check("`all` walks more than one club", t["clubs"] >= 2, str(t))
    check("the other club's innings of the same game is then written too (30 and 20)",
          await stand_rows("shared", 2) == [30, 20], str(await stand_rows("shared", 2)))
    check("and our club's stands were not touched or doubled", await stand_rows("shared", 1) == [10, 10, 204])

    # One limit for the whole run, however many clubs.
    async with Session() as s:
        await s.execute(text("DELETE FROM partnerships WHERE game_id = :g AND innings_number = 2"),
                        {"g": GAMES["shared"]})
        await s.commit()
    asked.clear()
    t = await bf.run("all", pause=0, apply=False, fetch=fetch, limit=1)
    check("`all` honours one limit across every club", len(asked) == 1 and t["asked"] == 1, str(asked))
    check("and says where to carry on", bool(t["resume"]), str(t))
    walked, token, guard = list(asked), t["resume"], 0
    while token and guard < 30:
        asked.clear()
        t = await bf.run("all", pause=0, apply=False, fetch=fetch, limit=1, resume=token)
        walked += asked
        token, guard = t["resume"], guard + 1
    check("walking `all` one game at a time ends, and asks nothing twice",
          token is None and len(walked) == len(set(walked)), f"{len(walked)} asked, {len(set(walked))} distinct")
    check("it reaches THEIRS' game (offered to the second club)",
          str(GAMES["shared"]) in walked)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    for f in base.FAILURES:
        print(f"  - {f}")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
