"""The club's own rows, copied out of the effective views once per StatLab request.

Why this exists. Every `v_effective_*` view plans at millions of rows, and a
StatLab player report joins one to `players` to reach a single club. Postgres
scans every innings on the platform before it throws away everybody else's.
Measured on a platform of 36,000 games and 800,000 innings, one club:

    player_career (default)   25s   (two grid chunks at ~10s each, covered rates 4.8s)
    player_grade              13s
    player_season              6s
    player_career + a filter   6s

`routers/records.py` solved the same thing for the record book by copying the
club's rows into temp tables once and reading the copies (`_club_bi` and
friends). This is that, for StatLab's three player reports and the grid lookup
behind their `matches` column.

The copies hold exactly what the views return for the club's players, and every
query rewritten to read them already joined `players` on
`organisation_id = :org_id`, so no figure changes: only where the rows are read
from. `rewrite` swaps the view names for the copy names and nothing else.

Temp tables are per connection. `ON COMMIT DROP` and a `DROP TABLE IF EXISTS`
first cover a pooled connection that kept one.
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# view -> copy. Order matters only for readability.
COPIES = {
    "v_effective_batting_innings": "_sl_bi",
    "v_effective_bowling_spells": "_sl_bs",
    "v_effective_fielding_stats": "_sl_fs",
    "v_game_roles": "_sl_roles",
    "v_effective_player_season_stats": "_sl_pss",
}

# What `aggregations.grid_matches_for_players(rels=)` reads. The grid wants a
# games relation and game_appearances too; the games copy holds every game one
# of the club's rows is in, and the appearances copy is the club's own rows.
GRID_RELS = {
    "bi": "_sl_bi", "bs": "_sl_bs", "fs": "_sl_fs", "ga": "_sl_ga",
    "games": "_sl_games", "pss": "_sl_pss",
}

_PATTERN = re.compile(r"\b(" + "|".join(re.escape(v) for v in COPIES) + r")\b")


def rewrite(sql: str) -> str:
    """The same SQL reading the club's copies instead of the platform-wide views."""
    return _PATTERN.sub(lambda m: COPIES[m.group(1)], sql)


async def ensure_club_rows(session: AsyncSession, org_id: str) -> dict:
    """Create the copies for this club in the current transaction (once) and return the grid's `rels`.

    Idempotent within a transaction: a second call for the same club finds the
    tables and does nothing. A call for a different club rebuilds them.
    """
    marker = session.info.get("_statlab_rows_org")
    present = (await session.execute(text("SELECT to_regclass('pg_temp._sl_games') IS NOT NULL"))).scalar()
    if present and marker == str(org_id):
        return dict(GRID_RELS)

    for t in (*COPIES.values(), "_sl_ga", "_sl_games"):
        await session.execute(text(f"DROP TABLE IF EXISTS {t}"))
    ids = (await session.execute(
        text("SELECT array_agg(id) FROM players WHERE organisation_id = CAST(:o AS UUID)"),
        {"o": str(org_id)})).scalar() or []
    bind = {"ids": ids}
    for view, table in COPIES.items():
        await session.execute(text(
            f"CREATE TEMP TABLE {table} ON COMMIT DROP AS SELECT * FROM {view} x "
            "WHERE x.player_id = ANY(CAST(:ids AS uuid[]))"), bind)
    await session.execute(text(
        "CREATE TEMP TABLE _sl_ga ON COMMIT DROP AS SELECT * FROM game_appearances x "
        "WHERE x.player_id = ANY(CAST(:ids AS uuid[]))"), bind)
    # An array built from the copies, not `IN (SELECT ...)`: a semi-join against
    # the games view scans every game on the platform.
    await session.execute(text(
        "CREATE TEMP TABLE _sl_games ON COMMIT DROP AS SELECT * FROM v_effective_games g "
        "WHERE g.id = ANY(ARRAY("
        " SELECT game_id FROM _sl_bi UNION SELECT game_id FROM _sl_bs"
        " UNION SELECT game_id FROM _sl_fs UNION SELECT game_id FROM _sl_ga"
        " UNION SELECT game_id FROM _sl_roles))"))
    await session.execute(text("ANALYZE _sl_bi, _sl_bs, _sl_fs, _sl_ga, _sl_roles, _sl_pss, _sl_games"))
    session.info["_statlab_rows_org"] = str(org_id)
    return dict(GRID_RELS)


async def materialize_universe(session: AsyncSession, universe_sql: str, params: dict) -> None:
    """Create a temp table called `game_universe` from the CTE text `statlab._game_universe_sql` builds.

    The CTE is read four or five times by a player report and its row estimate is
    wrong by a factor of six (934 against 6,000 games), which is what sent Postgres
    into a 600 x 6,000 Cartesian product of `players` and the universe (8s). As a
    table, analysed, it is counted. A table and a CTE of the same name coexist in
    the statement that creates it: the CTE shadows the table.
    """
    await session.execute(text("DROP TABLE IF EXISTS game_universe"))
    await session.execute(text(
        f"CREATE TEMP TABLE game_universe ON COMMIT DROP AS WITH {universe_sql} SELECT * FROM game_universe"),
        params)
    await session.execute(text("ANALYZE game_universe"))


async def run_on_copies(session: AsyncSession, org_id: str, sql: str, params: dict,
                        universe: str | None = None):
    """Run `sql` against the club's copies, without nested loops.

    The copies are small and every join they meet is a hash join in a good plan;
    the planner's estimate for the games filter is what turns it into a nested
    loop (records.py measured 6.6s for one board). Set around the one statement,
    not the request.
    """
    await ensure_club_rows(session, org_id)
    if universe is not None:
        await materialize_universe(session, universe, params)
    await session.execute(text("SET LOCAL enable_nestloop = off"))
    try:
        return await session.execute(text(rewrite(sql)), params)
    finally:
        # Not reached with a usable connection after a failed statement; the
        # caller's rollback then discards the SET LOCAL with the transaction.
        try:
            await session.execute(text("SET LOCAL enable_nestloop = on"))
        except Exception:
            pass
