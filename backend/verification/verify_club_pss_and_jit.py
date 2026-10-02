"""The record book reads the season totals once, and every connection has JIT off.

Three causes of a slow public stats site, found by timing a real database at the
production's size:

1. **JIT was on for everything but the record book.** The `v_effective_*`
   views plan at a cost of millions, so Postgres compiled a plan before every
   read: one read of `v_effective_player_season_stats` was 7.2s with JIT on and
   0.66s with it off. Milestones, the leaderboard, the dashboard and the player
   page all pay it. The fix is a startup parameter on the app's engine.
2. **`GET /records/{org}` read that view fourteen times.** Each read rebuilds
   the whole view, so the unfiltered record book was a flat ~12s. The club's
   rows are now copied out once into a temp table and the boards read the copy.
3. **Under an active scope every board scanned the platform's innings.** The
   per-innings boards read three views and the games view, each scanning every
   innings row on the platform before joining to the club's players: 0.5 to 1.5s
   a board, 20 boards, 12s. The club's own rows are copied out once
   (`_club_bi`, `_club_bs`, `_club_fs`, `_club_ga`, `_club_games`) and the boards
   read those, with nested loops off for the statements that do.

This runs the SHIPPED route body over the real view DDL (`superseded_ddl`, which
the lifespan re-applies on every boot), not the older migration definitions, and
asserts on what the database was actually asked.

THE CONTROL RUN is the same file against the previous commit. It must FAIL on
exactly the two reported behaviours (JIT reads `on`; the view is read many times)
and must not crash: every new name is read through a presence-safe accessor.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_pss_and_jit.py [--write-golden F | --golden F]

`--write-golden` is for the CONTROL checkout: it records what that commit's
record book returned, so the commit under test can be compared to it.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import event, text

import verify_records_timing as base
from app.services import superseded_ddl

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


def arg(flag: str):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else None


# Requests that between them reach every board: nothing filtered (the season
# totals path), a format filter (an active scope, the per-innings path), one
# season, a grade picked by name, and finals only.
VARIANTS = {
    "unfiltered": {},
    "format scope": {"formats": "one_day"},
    "one season": {"season_id": str(base.SEASON)},
    "grade by name": {"grade_name": "1st Grade"},
    "grade by name + format": {"grade_name": "1st Grade", "formats": "one_day"},
    "finals only": {"finals_only": True},
    "captain only": {"captain_only": True},
    "one season + format": {"season_id": str(base.SEASON), "formats": "one_day"},
}

# A board reading a per-innings view directly names it with the board's alias.
# The copy's own creation reads it as `x`, and the match-played test probes it as
# `_cb`, so neither is counted: this is "a board that did not use the copy".
BOARD_VIEW_READ = re.compile(
    r"\bv_effective_(?:batting_innings\s+bi|bowling_spells\s+bs|fielding_stats\s+fs)\b", re.I)
INNINGS_COPY_READ = re.compile(r"\b_club_(?:bi|bs|fs|ga|games)\b", re.I)
VIEW_READ = re.compile(r"\b(?:FROM|JOIN)\s+v_effective_player_season_stats\b", re.I)
COPY_READ = re.compile(r"\b(?:FROM|JOIN)\s+_club_pss\b", re.I)


async def extra_seed(session) -> None:
    """What the base seed lacks: a hand-entered game, so the view's manual branch
    has something to roll up and the copy has to carry it."""
    mg = uuid.UUID("aaaaaaaa-0000-0000-0000-00000000000a")
    await session.execute(text(
        "INSERT INTO manual_games (id, organisation_id, season_id, grade_id, "
        " played_at, result, match_format) "
        "VALUES (:i, :o, :s, :g, DATE '2025-02-01', 'WIN', 'One Day')"),
        {"i": mg, "o": base.ORG, "s": base.SEASON, "g": base.GRADE})
    await session.execute(text(
        "INSERT INTO manual_batting_innings (manual_game_id, player_id, "
        " innings_number, batting_position, runs, balls, not_out, did_not_bat, "
        " dismissal_type) VALUES (:g, :p, 1, 1, 77, 60, false, false, 'bowled')"),
        {"g": mg, "p": base.PLAYER})
    ids = {k: uuid.UUID(f"bbbbbbbb-0000-0000-0000-0000000000{n:02d}") for k, n in (
        ("shared", 1), ("called_off", 2), ("roster_only", 3), ("fielding_only", 4),
        ("rival_grade", 5), ("paired_manual", 6))}
    synced = [r[0] for r in (await session.execute(text(
        "SELECT id FROM games WHERE grade_id = :g ORDER BY played_at"), {"g": base.GRADE})).all()]
    rival_season = (await session.execute(text(
        "SELECT id FROM seasons WHERE organisation_id = :o"), {"o": base.OPPONENT})).scalar()
    # A SHARED FIXTURE: the other club synced it first, so it sits in THEIR
    # season and grade, and ours is the away side. Ours by home/away, never by
    # the season's owner. Our PLAYER batted; their RIVAL_PLAYER batted too and
    # must not appear on any board of ours.
    await session.execute(text(
        "INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
        "VALUES (:g, :s, '2nd Grade', :gid, 'senior', ARRAY['senior'])"),
        {"g": ids["rival_grade"], "s": rival_season, "gid": str(ids["rival_grade"])})
    for key, status, when in (("shared", "COMPLETED", date(2025, 1, 20)),
                              ("called_off", "ABANDONED", date(2025, 1, 21)),
                              ("roster_only", "COMPLETED", date(2025, 1, 22)),
                              ("fielding_only", "COMPLETED", date(2025, 1, 23))):
        grade = ids["rival_grade"] if key == "shared" else base.GRADE
        home, away = (base.OPPONENT, base.ORG) if key == "shared" else (base.ORG, base.OPPONENT)
        await session.execute(text(
            "INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
            " match_format, status) VALUES (:i, :g, :d, 'WIN', :h, :a, 'One Day', :st)"),
            {"i": ids[key], "g": grade, "d": when, "h": home, "a": away, "st": status})
    # The roster-only game needs a real batting line from SOMEONE ELSE: a
    # COMPLETED game with an empty scorecard is not a match played at all.
    for gid, pid in ((ids["shared"], base.PLAYER), (ids["shared"], base.RIVAL_PLAYER),
                     (ids["roster_only"], base.PLAYER)):
        await session.execute(text(
            "INSERT INTO batting_innings (game_id, player_id, runs, balls, fours, sixes, "
            " not_out, dismissal_type, did_not_bat, batting_position) "
            "VALUES (:g, :p, :r, 40, 3, 1, false, 'caught', false, 4)"),
            {"g": gid, "p": pid,
             "r": 99 if pid == base.RIVAL_PLAYER else (41 if gid == ids["shared"] else 12)})
    # A named player who recorded nothing: a match played in a completed game,
    # NOT in one that was called off. And a player with only a catch.
    for gid in (ids["called_off"], ids["roster_only"]):
        await session.execute(text(
            "INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)"),
            {"g": gid, "p": base.MATE})
    await session.execute(text(
        "INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, stumpings, run_outs) "
        "VALUES (:g, :p, 2, 0, 0, 0)"), {"g": ids["fielding_only"], "p": base.MATE})
    # A hand-entered match that IS one of the synced games, preferred over it
    # (the paired import holds the scorecard): the synced rows must step aside.
    await session.execute(text(
        "INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, "
        " result, match_format, superseded_by_game_id, pair_prefers_import) "
        "VALUES (:i, :o, :s, :g, DATE '2025-01-07', 'WIN', 'One Day', :twin, true)"),
        {"i": ids["paired_manual"], "o": base.ORG, "s": base.SEASON, "g": base.GRADE,
         "twin": synced[1]})
    await session.execute(text(
        "INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, "
        " batting_position, runs, balls, not_out, did_not_bat, dismissal_type) "
        "VALUES (:g, :p, 1, 2, 58, 44, false, false, 'lbw')"),
        {"g": ids["paired_manual"], "p": base.PLAYER})
    # One of the seeded games is a final, so the finals-only request has boards.
    await session.execute(text(
        "UPDATE games SET is_final = true WHERE played_at = DATE '2025-01-07'"))
    await session.commit()


def canonical(payload: dict):
    """A payload with every board's row order made irrelevant.

    The copy and the view can break a tie between equal figures differently, and
    this check is about WHICH figures come back, not about how ties are ordered.
    """
    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items() if k != "_query_timings"}
        if isinstance(v, list):
            return sorted((walk(x) for x in v),
                          key=lambda x: json.dumps(x, sort_keys=True, default=str))
        return v
    return json.dumps(walk(payload), sort_keys=True, default=str)


async def run_variant(**kw):
    """One request on a fresh session, and every statement it sent."""
    sent: list[str] = []

    def grab(conn, cursor, statement, parameters, context, executemany):
        sent.append(statement)

    event.listen(base.engine.sync_engine, "before_cursor_execute", grab)
    try:
        async with base.Session() as session:
            payload = await base.records(session, **kw)
    finally:
        event.remove(base.engine.sync_engine, "before_cursor_execute", grab)
    return payload, sent


async def main() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        # The app's own view definitions, as the lifespan applies them.
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))
    async with base.Session() as session:
        await base.seed(session)
        await extra_seed(session)

    print("\n-- every connection the app opens has JIT off --")
    from app.models import db as app_db
    async with app_db.engine.connect() as conn:
        jit = (await conn.execute(text("SHOW jit"))).scalar()
    check("the app's engine opens connections with jit = off", jit == "off",
          f"SHOW jit read {jit!r}")

    print("\n-- the season totals are read once, not once per board --")
    results: dict[str, tuple[dict, list[str]]] = {}
    for name, kw in VARIANTS.items():
        results[name] = await run_variant(**kw)

    _, sent = results["unfiltered"]
    view_reads = sum(1 for s in sent if VIEW_READ.search(s))
    copy_reads = sum(1 for s in sent if COPY_READ.search(s))
    check("an unfiltered request reads the view exactly once", view_reads == 1,
          f"{view_reads} reads of v_effective_player_season_stats")
    check("and the season-total boards read the copy instead", copy_reads >= 10,
          f"{copy_reads} statements read _club_pss")
    # The pairing that makes the two checks above able to fail: the very same
    # statements, counted the same way, on the previous commit.
    check("the count is measuring real boards (a view read or a copy read exists)",
          view_reads + copy_reads >= 10, f"view {view_reads} + copy {copy_reads}")

    _, sent = results["format scope"]
    scoped_view = sum(1 for s in sent if VIEW_READ.search(s))
    check("a filtered request that skips those boards copies nothing it does not read",
          scoped_view <= 1, f"{scoped_view} reads")

    print("\n-- the per-innings boards read the club's own copies --")
    for name in ("format scope", "grade by name + format", "captain only"):
        _, sent = results[name]
        direct = sum(1 for st in sent if BOARD_VIEW_READ.search(st))
        copied = sum(1 for st in sent if INNINGS_COPY_READ.search(st))
        check(f"{name}: no board reads a per-innings view directly", direct == 0,
              f"{direct} statements read a view with a board alias")
        check(f"{name}: the boards read the copies", copied >= 6,
              f"{copied} statements read a _club_ copy")
    _, sent = results["format scope"]
    built = [st for st in sent if re.search(r"CREATE TEMP TABLE _club_(bi|bs|fs|ga|games)\b", st)]
    check("the five copies are each built once", len(built) == 5, f"{len(built)} built")
    nested_off = sum(1 for st in sent if "enable_nestloop = off" in st)
    nested_on = sum(1 for st in sent if "enable_nestloop = on" in st)
    check("nested loops are switched off around copy-reading statements and back on after",
          nested_off >= 6 and nested_off == nested_on, f"off {nested_off}, on {nested_on}")

    print("\n-- the copy answers exactly what the view answered --")
    golden_out = arg("--write-golden")
    golden_in = arg("--golden")
    got = {name: canonical(payload) for name, (payload, _) in results.items()}
    for name, payload_json in got.items():
        check(f"{name}: the boards are not empty", len(payload_json) > 2000,
              f"{len(payload_json)} bytes")
    if golden_out:
        Path(golden_out).write_text(json.dumps(got, sort_keys=True))
        print(f"  wrote golden for {len(got)} requests to {golden_out}")
    if golden_in:
        want = json.loads(Path(golden_in).read_text())
        for name in VARIANTS:
            check(f"{name}: identical to what the previous commit returned",
                  got.get(name) == want.get(name))
    else:
        print("  (no --golden given: payload comparison skipped)")

    unfiltered = got["unfiltered"]
    check("a rival club's bigger scorer is on no board of ours",
          "Bradman" not in unfiltered and "6996" not in unfiltered)
    check("the hand-entered game is in a season total (the copy carries the manual branch)",
          re.search(r'"runs": 162\b', unfiltered) is not None,
          "PLAYER's 85 api runs plus the 77 hand-entered should read 162 somewhere")

    print("\n-- what the richer seed must and must not show --")
    scoped = got["format scope"]
    check("the shared fixture counts for us (we are the away side)",
          '"runs": 41' in scoped or "41" in scoped)
    check("the other club's batter in that fixture is on no board", "Bradman" not in scoped
          and not re.search(r'"runs": 99\b', scoped))
    async with base.Session() as session:
        scoped_payload = await base.records(session, formats="one_day")
    played = {r["name"]: r["matches"] for r in scoped_payload["team"]["most_matches"]}
    # Baker (MATE): batted in two seeded games (the third was paired to a
    # hand-entered match that did not include him, so his synced rows step
    # aside), was named in a played game and recorded nothing, took catches in
    # another, and was named in a game that was CALLED OFF, which is no match.
    check("a player named in a completed game with nothing recorded has it as a match, "
          "and one named in a called-off game does not",
          played.get("Baker, Ken") == 4, f"Baker played {played.get('Baker, Ken')}")
    # Barker (PLAYER): two synced games, the hand-entered game that replaced the
    # third, the shared fixture, the roster-only game (he batted, Baker did not),
    # and the first extra hand-entered game.
    check("a shared fixture, a paired import and a hand-entered game all count once",
          played.get("Barker, Geoffrey") == 6, f"Barker played {played.get('Barker, Geoffrey')}")

    print("\n-- the copy does not outlive the request --")
    async with base.Session() as session:
        first = await base.records(session)
        left = (await session.execute(
            text("SELECT to_regclass('pg_temp._club_pss')"))).scalar()
        check("the temp table is dropped when the request ends", left is None,
              f"to_regclass returned {left!r}")
        second = await base.records(session)
        check("a second request on the same connection works and agrees",
              canonical(first) == canonical(second))
        await session.execute(text(
            "CREATE TEMP TABLE _club_pss AS SELECT 1 AS stale"))
        third = await base.records(session)
        check("a leftover from a committed request is replaced, not tripped over",
              canonical(third) == canonical(first))
        await session.execute(text("CREATE TEMP TABLE _club_bi AS SELECT 1 AS stale"))
        fourth = await base.records(session, formats="one_day")
        await base.records(session, formats="one_day")
        gone = [t for t in ("_club_bi", "_club_bs", "_club_fs", "_club_ga", "_club_games")
                if (await session.execute(text("SELECT to_regclass(:n)"),
                                          {"n": "pg_temp." + t})).scalar() is not None]
        check("a stale innings copy is replaced and none of the five outlives the request",
              not gone and fourth["batting"]["top_career_runs"] is not None, str(gone))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await base.engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
