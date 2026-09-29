"""The career figures a milestone is measured against, for many players at once.

Asked for off Shoalwater Bay's Milestones page, where four players read four
different numbers from the ones on their own profiles: S Hetel 87 short of
6,000 runs beside a profile reading 5,924, A Godfrey 3 short of 200 wickets
beside 478. The scan summed the BASE ``player_season_stats`` table while the
profile reads ``v_effective_player_season_stats`` and, under the club's grade
default, the scorecards. Two definitions of one career, and a club compares
them side by side.

So this is the ONE definition, and it is the profile's:

- **THE NUMBER IS THE ONE THE PLAYER'S PROFILE OPENS ON.** The club's default
  grade categories, widened to the categories a player has actually played
  when the default would leave them with nothing (``resolve_scope_for_player``).
  Unscoped, that is the effective view's season totals; scoped, it is the
  scorecards plus the aggregate-only residuals, exactly as ``get_career_*``
  build it. The verification asserts equality with those functions player by
  player rather than taking the mirroring on trust.
- **BATCHED, NEVER A LOOP OF PROFILE CALLS.** The dashboard asks this on every
  page load for every active player, and a sync asks it for the whole club.
  Players are grouped by the scope they resolve to (almost always one or two
  groups) and each group is one query per figure, with the player ids bound as
  an array: the form the record book's timing work measured the planner
  pushing into the views, where a subquery was a platform-wide scan.
- **JUNIOR MATCHES ARE NEVER GUESSED AWAY, THEY ARE SHOWN.** A club asked for
  a senior/junior switch on Milestones and then, better, for the page to work
  it out and show both. A player who has played junior AND open-age cricket
  carries a ``split`` with both figures: including their junior matches, and
  without them (judged on each grade's primary category, so a Girls Under 16
  grade reads as junior). No toggle; the page names whichever figure the
  headline is not.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.game_status import NOT_PLAYED_SQL_LIST
from app.services.grade_labels import GRADE_CATEGORIES, categories_for_name, org_grade_category_sets
from app.services.grade_scope import DEFAULT_CATEGORIES, GradeScope, club_default_categories, resolve_scope

STATS = ("runs", "wickets", "matches", "catches")

# The aggregate-only branches of the effective view — the ones with no
# per-innings rows behind them. Mirrors aggregations._RESIDUAL_SOURCES, which
# this module cannot import (aggregations imports milestone_scan, which imports
# this); the verification asserts the two lists agree.
RESIDUAL_SOURCES = ("manual_aggregate", "manual_career", "import")

_PIDS = "CAST(:pids AS uuid[])"
# "This game is our club's": ours, or we are one of the two sides. The same
# predicate aggregations._club_game_clause applies for one player.
_OURS = ("(g.organisation_id = CAST(:org AS uuid)"
         " OR g.home_org_id = CAST(:org AS uuid)"
         " OR g.away_org_id = CAST(:org AS uuid))")


def _empty() -> dict:
    return {s: 0 for s in STATS}


def _ids(pids: Iterable) -> list[str]:
    return sorted({str(p) for p in pids if p})


async def _unscoped(session: AsyncSession, pids: list[str]) -> dict[str, dict]:
    """The effective view's season totals — the profile's unfiltered figures."""
    rows = await session.execute(text(f"""
        SELECT pss.player_id::text AS pid,
               COALESCE(SUM(pss.runs), 0)    AS runs,
               COALESCE(SUM(pss.wickets), 0) AS wickets,
               COALESCE(SUM(pss.matches), 0) AS matches,
               COALESCE(SUM(pss.catches), 0) AS catches
        FROM v_effective_player_season_stats pss
        WHERE pss.player_id = ANY({_PIDS})
        GROUP BY pss.player_id
    """), {"pids": pids})
    return {r["pid"]: {s: int(r[s] or 0) for s in STATS} for r in rows.mappings()}


async def _scoped(session: AsyncSession, org_id, pids: list[str],
                  scope: GradeScope) -> dict[str, dict]:
    """Scorecards plus residuals, the way ``get_career_*`` build a scoped career."""
    out = {p: _empty() for p in pids}
    params: dict = {"pids": pids, "org": str(org_id)}
    scope.bind(params)
    game_scope = scope.clause("g.grade_id")

    def add(rows, stat):
        for r in rows.mappings():
            out.setdefault(r["pid"], _empty())[stat] += int(r["v"] or 0)

    add(await session.execute(text(f"""
        SELECT bi.player_id::text AS pid, SUM(bi.runs) AS v
        FROM v_effective_batting_innings bi
        JOIN v_effective_games g ON g.id = bi.game_id
        WHERE bi.player_id = ANY({_PIDS})
          AND NOT COALESCE(bi.did_not_bat, FALSE)
          AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
          AND {_OURS}{game_scope}
        GROUP BY bi.player_id
    """), params), "runs")
    add(await session.execute(text(f"""
        SELECT bs.player_id::text AS pid, SUM(bs.wickets) AS v
        FROM v_effective_bowling_spells bs
        JOIN v_effective_games g ON g.id = bs.game_id
        WHERE bs.player_id = ANY({_PIDS}) AND {_OURS}{game_scope}
        GROUP BY bs.player_id
    """), params), "wickets")
    add(await session.execute(text(f"""
        SELECT fs.player_id::text AS pid, SUM(fs.catches) AS v
        FROM v_effective_fielding_stats fs
        JOIN v_effective_games g ON g.id = fs.game_id
        WHERE fs.player_id = ANY({_PIDS}) AND {_OURS}{game_scope}
        GROUP BY fs.player_id
    """), params), "catches")
    # The four ways we know somebody was in a game, as _scoped_games_played
    # unions them, with a called-off fixture's bare team sheet left out.
    add(await session.execute(text(f"""
        WITH ap AS (
            SELECT bi.player_id, bi.game_id FROM v_effective_batting_innings bi
             WHERE bi.player_id = ANY({_PIDS})
            UNION
            SELECT bs.player_id, bs.game_id FROM v_effective_bowling_spells bs
             WHERE bs.player_id = ANY({_PIDS})
            UNION
            SELECT fs.player_id, fs.game_id FROM v_effective_fielding_stats fs
             WHERE fs.player_id = ANY({_PIDS})
            UNION
            SELECT ga.player_id, ga.game_id FROM game_appearances ga
            JOIN games ag ON ag.id = ga.game_id
             WHERE ga.player_id = ANY({_PIDS})
               AND (ag.status IS NULL OR ag.status NOT IN ({NOT_PLAYED_SQL_LIST}))
        )
        SELECT ap.player_id::text AS pid, COUNT(DISTINCT g.id) AS v
        FROM ap JOIN v_effective_games g ON g.id = ap.game_id
        WHERE {_OURS}{game_scope}
        GROUP BY ap.player_id
    """), params), "matches")

    residual = scope.clause("pss.grade_id", "aggregate", label_column="pss.grade_label")
    params["sources"] = list(RESIDUAL_SOURCES)
    rows = await session.execute(text(f"""
        SELECT pss.player_id::text AS pid,
               COALESCE(SUM(pss.runs), 0)    AS runs,
               COALESCE(SUM(pss.wickets), 0) AS wickets,
               COALESCE(SUM(pss.matches), 0) AS matches,
               COALESCE(SUM(pss.catches), 0) AS catches
        FROM v_effective_player_season_stats pss
        WHERE pss.player_id = ANY({_PIDS})
          AND pss.source = ANY(:sources){residual}
        GROUP BY pss.player_id
    """), params)
    for r in rows.mappings():
        t = out.setdefault(r["pid"], _empty())
        for s in STATS:
            t[s] += int(r[s] or 0)
    return out


async def totals_under(session: AsyncSession, org_id, pids: Iterable,
                       scope: Optional[GradeScope]) -> dict[str, dict]:
    """Every player's four figures under one scope. Missing players read zero."""
    ids = _ids(pids)
    if not ids:
        return {}
    if scope is not None and scope.active:
        got = await _scoped(session, org_id, ids, scope)
    else:
        got = await _unscoped(session, ids)
    return {p: got.get(p) or _empty() for p in ids}


async def played_grade_names(session: AsyncSession, org_id, pids: Iterable) -> dict[str, set]:
    """The grade names each player has a record in — ``player_categories``, batched."""
    ids = _ids(pids)
    if not ids:
        return {}
    rows = await session.execute(text(f"""
        WITH player_games AS (
            SELECT bi.player_id, bi.game_id FROM v_effective_batting_innings bi
             WHERE bi.player_id = ANY({_PIDS})
            UNION
            SELECT bs.player_id, bs.game_id FROM v_effective_bowling_spells bs
             WHERE bs.player_id = ANY({_PIDS})
            UNION
            SELECT fs.player_id, fs.game_id FROM v_effective_fielding_stats fs
             WHERE fs.player_id = ANY({_PIDS})
            UNION
            SELECT ga.player_id, ga.game_id FROM game_appearances ga
             WHERE ga.player_id = ANY({_PIDS})
        ),
        played AS (
            SELECT pg.player_id, g.grade_id
            FROM v_effective_games g JOIN player_games pg ON pg.game_id = g.id
            WHERE g.grade_id IS NOT NULL
            UNION
            SELECT pss.player_id, pss.grade_id
            FROM v_effective_player_season_stats pss
            WHERE pss.player_id = ANY({_PIDS}) AND pss.grade_id IS NOT NULL
        )
        SELECT DISTINCT pl.player_id::text AS pid, gr.name
        FROM played pl
        JOIN grades gr ON gr.id = pl.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = CAST(:org AS uuid)
    """), {"pids": ids, "org": str(org_id)})
    out: dict[str, set] = {}
    for r in rows.mappings():
        out.setdefault(r["pid"], set()).add(r["name"])
    return out


async def _auto_widen(session: AsyncSession, org_id) -> bool:
    row = (await session.execute(text(
        "SELECT stats_auto_show_played_grades FROM organisations WHERE id = CAST(:o AS uuid)"
    ), {"o": str(org_id)})).first()
    return bool(row[0]) if row and row[0] is not None else True


async def profile_totals(session: AsyncSession, org_id, pids: Iterable, *,
                         with_split: bool = True) -> dict[str, dict]:
    """``{pid: {"totals": {...}, "split": {...} | None, "counts": str | None}}``.

    ``totals`` is what the player's profile opens on. ``split`` is present only
    for a player with both junior and open-age records, carrying
    ``with_junior`` and ``without_junior`` figures; ``counts`` then names which
    of the two ``totals`` equals, or ``"club_default"`` when a club's own default
    matches neither.
    """
    ids = _ids(pids)
    if not ids:
        return {}
    default = await resolve_scope(session, org_id)
    widen = default.category_active and await _auto_widen(session, org_id)
    need_played = widen or with_split
    played_names = await played_grade_names(session, org_id, ids) if need_played else {}
    name_cats = await org_grade_category_sets(session, org_id) if need_played else {}

    def cats_of(pid) -> list[frozenset]:
        return [categories_for_name(name_cats, n) for n in played_names.get(pid, ())]

    groups: dict[tuple, list[str]] = {}
    for pid in ids:
        key = ()
        if widen:
            played = set().union(*cats_of(pid)) if played_names.get(pid) else set()
            if played and not (played & set(default.categories)):
                key = tuple(sorted(set(default.categories) | played))
        groups.setdefault(key, []).append(pid)

    primary: dict[str, dict] = {}
    for key, members in groups.items():
        scope = default if not key else await resolve_scope(session, org_id, list(key))
        primary.update(await totals_under(session, org_id, members, scope))

    out = {pid: {"totals": primary.get(pid) or _empty(), "split": None, "counts": None}
           for pid in ids}
    if not with_split:
        return out

    split_ids = []
    for pid in ids:
        cs = cats_of(pid)
        if any("junior" in c for c in cs) and any("junior" not in c for c in cs):
            split_ids.append(pid)
    if not split_ids:
        return out
    with_junior = await totals_under(
        session, org_id, split_ids,
        await resolve_scope(session, org_id, list(GRADE_CATEGORIES)))
    without_junior = await totals_under(
        session, org_id, split_ids,
        await resolve_scope(session, org_id, list(DEFAULT_CATEGORIES), judge_primary=True))
    for pid in split_ids:
        w, s, p = with_junior[pid], without_junior[pid], out[pid]["totals"]
        if w == s:
            continue  # nothing junior actually counts towards a figure here
        out[pid]["split"] = {"with_junior": w, "without_junior": s}
        out[pid]["counts"] = ("with_junior" if p == w
                              else "without_junior" if p == s
                              else "club_default")
    return out


__all__ = [
    "STATS", "RESIDUAL_SOURCES", "totals_under", "played_grade_names",
    "profile_totals", "club_default_categories",
]
