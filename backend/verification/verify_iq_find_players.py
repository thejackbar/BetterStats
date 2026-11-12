"""Ask IQ's find_players must not read the whole roster to look one player up.

Reported: Ask IQ questions sat for minutes and then died. Production logged
`iq_ask: tool find_players took 110.9s` while every model call took 2 to 6s. The tool
loaded EVERY player the club has ever had (`iq_players.list_all_players`), raised each
to the by-grade grid total (the costly part, it reads the heavy views per id), and only
then filtered by name in Python and kept 40.

The fix filters by name in SQL and raises only the rows that are returned. This checks,
against a real Postgres through the shipped tool and resolver:
  - the rows a lookup returns are the rows the old whole-roster path returned, in the
    same order, with the same figures (including the grid-raised games);
  - the grid loader is asked about the handful of rows shown, not the roster;
  - an exact name is still found when many longer names contain it;
  - a name with `_` or `%` matches itself and not everyone;
  - the Players page's own call (no filter) is unchanged.

The "ids the grid loader was asked about" count stands in for the production seconds:
a toy database cannot show 110s, it can show what the work scales with.

Run (reuses the schema and seed of verify_board_games_match_profile.py):
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_iq_find_players.py

Control: run it against the previous iq_players.py and iq_ask.py. It reports what is
missing rather than crashing.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_board_games_match_profile as base  # noqa: E402  (schema + seed; its main() is not run)

from sqlalchemy import text  # noqa: E402

from app.services import aggregations, iq_ask, iq_players  # noqa: E402

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG = base.ORG
FILLER = 600
DAN = uuid.uuid4()
UNDERSCORE = uuid.uuid4()
PERCENT = uuid.uuid4()

# Ids the grid loader is asked about, per call. Patched in, read back, restored.
asked: list[int] = []
_real_inputs = aggregations._grid_inputs


async def _counting_inputs(session, ids, *a, **kw):
    asked.append(len(ids))
    return await _real_inputs(session, ids, *a, **kw)


def slim(rows):
    return [(r["player_id"], r["name"], r["matches"], r["runs"], r["wickets"], r["last_year"], r["squad"]) for r in rows]


async def old_way_find(s, query):
    """What the tool returned before: the whole roster, filtered in Python, 40 kept."""
    rows = await iq_players.list_all_players(s, str(ORG))
    q = query.strip().lower()
    rows = [p for p in rows if q in (p["name"] or "").lower()] if q else rows
    return rows[:40]


async def main() -> None:
    await base.build_schema()
    await base.seed()
    async with base.Session() as s:
        await s.execute(text("UPDATE players SET is_player = TRUE WHERE organisation_id = :o"), {"o": ORG})
        # A roster big enough that a whole-roster raise is visibly the wrong amount of work,
        # and big enough to be roster-sized for the grid loader's own cache (100+ ids).
        for i in range(FILLER):
            await s.execute(text(
                "INSERT INTO players (id, organisation_id, name, grassroots_id, status, is_player) "
                "VALUES (:i, :o, :n, :g, 'active', TRUE)"),
                {"i": uuid.uuid4(), "o": ORG, "n": f"Filler, Number {i}", "g": str(uuid.uuid4())})
        # An exact name that sorts behind many longer names containing it.
        await s.execute(text(
            "INSERT INTO players (id, organisation_id, name, grassroots_id, status, is_player) "
            "VALUES (:i, :o, 'Dan', :g, 'active', TRUE)"), {"i": DAN, "o": ORG, "g": str(DAN)})
        for i in range(60):
            await s.execute(text(
                "INSERT INTO players (id, organisation_id, name, grassroots_id, status, is_player) "
                "VALUES (:i, :o, :n, :g, 'active', TRUE)"),
                {"i": uuid.uuid4(), "o": ORG, "n": f"Dan Longname {i}", "g": str(uuid.uuid4())})
        for pid, nm in ((UNDERSCORE, "Mc_Donald, Rory"), (PERCENT, "Fifty%, Percy")):
            await s.execute(text(
                "INSERT INTO players (id, organisation_id, name, grassroots_id, status, is_player) "
                "VALUES (:i, :o, :n, :g, 'active', TRUE)"), {"i": pid, "o": ORG, "n": nm, "g": str(pid)})
        await s.commit()

    aggregations._grid_inputs = _counting_inputs
    # The grid loader remembers a roster-sized answer for two minutes; clear it between
    # steps so each step measures its own work, not the last one's.
    def fresh():
        aggregations._GRID_CACHE.clear()
        asked.clear()

    try:
        print("\n-- A NAME LOOKUP RETURNS WHAT THE WHOLE-ROSTER PATH RETURNED --")
        for q in ("short", "Exact", "Held", "mixed"):
            fresh()
            async with base.Session() as s:
                want = slim(await old_way_find(s, q))
            fresh()
            async with base.Session() as s:
                got = await iq_ask._tool_find_players(s, str(ORG), query=q)
            gotrows = [(r["player_id"], r["name"], r["matches"], r["runs"], r["wickets"], r["last_year"], r["squad"])
                       for r in got["players"]]
            check(f"find_players({q!r}): same rows, order and figures as before ({len(want)})",
                  gotrows == want and len(want) > 0, f"{gotrows[:2]} vs {want[:2]}")

        print("\n-- AND THE GRADE-RAISED GAMES ARE STILL RAISED --")
        fresh()
        async with base.Session() as s:
            got = await iq_ask._tool_find_players(s, str(ORG), query="Short, Exact")
        row = (got["players"] or [{}])[0]
        check("Short, Exact reads 7 games (5 held, the grade row says 7)", row.get("matches") == 7, str(row.get("matches")))

        print("\n-- THE GRID LOADER IS ASKED ABOUT THE ROWS SHOWN, NOT THE ROSTER --")
        fresh()
        async with base.Session() as s:
            await iq_ask._tool_find_players(s, str(ORG), query="short")
        new_ids = sum(asked)
        fresh()
        async with base.Session() as s:
            await old_way_find(s, "short")
        old_ids = sum(asked)
        check(f"a name lookup asks about 2 players (the old way asked about {old_ids})",
              new_ids == 2, f"asked about {new_ids}")
        check("and the old way really did ask about the whole roster", old_ids >= FILLER, str(old_ids))
        fresh()
        async with base.Session() as s:
            await iq_ask._tool_find_players(s, str(ORG), query="Filler")
        check("a lookup matching 600 players raises only the 40 it returns", sum(asked) == 40, str(sum(asked)))

        print("\n-- AN EXACT NAME IS FOUND AMONG MANY LONGER ONES --")
        fresh()
        async with base.Session() as s:
            pid = await iq_ask._resolve_pid(s, str(ORG), "Dan")
        check("'Dan' resolves to the exact player, not an ambiguity", pid == str(DAN), str(pid))
        fresh()
        async with base.Session() as s:
            pid = await iq_ask._resolve_pid(s, str(ORG), "Dan Longname")
        check("'Dan Longname' is ambiguous, with at most 8 shown",
              isinstance(pid, dict) and 1 < len(pid["ambiguous"]) <= 8, str(pid)[:120])
        check("and raised only the 8 it shows", sum(asked) <= 8, str(sum(asked)))
        async with base.Session() as s:
            pid = await iq_ask._resolve_pid(s, str(ORG), "Held, More")
        check("a unique name resolves to its id", pid == str(base.HELD_MORE), str(pid))
        async with base.Session() as s:
            pid = await iq_ask._resolve_pid(s, str(ORG), "Nobody Atall")
        check("a name nobody has resolves to nothing", pid is None, str(pid))

        print("\n-- LIKE'S OWN WILDCARDS MATCH THEMSELVES --")
        async with base.Session() as s:
            u = await iq_ask._tool_find_players(s, str(ORG), query="_")
            p = await iq_ask._tool_find_players(s, str(ORG), query="%")
            u2 = await iq_ask._tool_find_players(s, str(ORG), query="mc_d")
        check("'_' finds only the name that has an underscore", [r["name"] for r in u["players"]] == ["Mc_Donald, Rory"],
              str([r["name"] for r in u["players"]][:3]))
        check("'%' finds only the name that has a percent sign", [r["name"] for r in p["players"]] == ["Fifty%, Percy"],
              str([r["name"] for r in p["players"]][:3]))
        check("'mc_d' finds Mc_Donald", [r["name"] for r in u2["players"]] == ["Mc_Donald, Rory"])

        print("\n-- THE PLAYERS PAGE'S OWN CALL IS UNCHANGED --")
        fresh()
        async with base.Session() as s:
            roster = await iq_players.list_all_players(s, str(ORG))
        check("no filter returns the whole roster", len(roster) >= FILLER + 5, str(len(roster)))
        check("and raises all of it, as it always did", sum(asked) >= FILLER, str(sum(asked)))
        by = {r["player_id"]: r for r in roster}
        check("Short, Exact is raised to 7 there too", by[str(base.SHORT_EXACT)]["matches"] == 7)
    finally:
        aggregations._grid_inputs = _real_inputs

    print(f"\n{PASS} passed, {FAIL} failed")
    await base.engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
