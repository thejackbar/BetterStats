"""Shared SQL fragments for the BetterIQ global Season + Team filter.

The filter sends ONE representative season-row id, but a single real cricket
season ("2024/25") is frequently stored as several ``seasons`` rows: the
MyCricket and PlayHQ feeds give the same year different season ids, and separate
competitions get their own rows. Scoping on one row shows only a slice of the
year, so we expand a picked season to every row in the same org that shares its
year (falling back to the one row when the year is unknown, so an undated row is
never widened to the whole table). Grades are matched by NAME because the
per-club / per-season grade ids all collapse to one competition grade.

Both builders read the already-bound parameter ``:season`` (a season-row id) and,
for the grade variant, ``:grade`` (a grade NAME — or several names joined with
``||``, the multi-grade filter's wire format; a name never contains ``||``, so a
single name and a multi-select read through the same parameter). Callers bind
these today.
"""
from __future__ import annotations

# Every sibling row of :season for the same org/year (or just :season when the
# year is NULL). s0 is the picked row; s2 ranges over the org's season rows.
_SEASON_YEAR_SET = (
    "(SELECT s2.id FROM seasons s2 "
    "JOIN seasons s0 ON s0.id = CAST(:season AS UUID) "
    "WHERE s2.organisation_id = s0.organisation_id "
    "AND (s2.year = s0.year OR (s0.year IS NULL AND s2.id = s0.id)))"
)


def season_member_clause(column: str, season_id) -> str:
    """``AND <column> IN (<rows of :season's year>)`` — or '' when no season set.

    For a non-grade season column, e.g. ``pss.season_id``."""
    return f"AND {column} IN {_SEASON_YEAR_SET}" if season_id else ""


# The year set PLUS every OTHER club's sibling row of the same CA season —
# per-club season rows minted for a cross-club collision share `grassroots_id`
# (the raw CA season GUID), so this is how a shared game the OPPONENT synced
# first (whose `season_id` resolves to THEIR season row, migration 167's note)
# still matches OUR season filter. Mirrors aggregations._club_results.
_SEASON_YEAR_SET_CROSS = (
    "(SELECT s5.id FROM seasons s5 "
    f"WHERE s5.id IN {_SEASON_YEAR_SET} "
    "OR (s5.grassroots_id IS NOT NULL AND s5.grassroots_id IN "
    f"(SELECT s6.grassroots_id FROM seasons s6 WHERE s6.id IN {_SEASON_YEAR_SET} "
    "AND s6.grassroots_id IS NOT NULL)))"
)


def season_member_clause_cross_club(column: str, season_id) -> str:
    """``season_member_clause`` for a GAME's season column: also matches another
    club's sibling row of the same CA season, so an opponent-first-synced shared
    game isn't dropped by our season filter."""
    return f"AND {column} IN {_SEASON_YEAR_SET_CROSS}" if season_id else ""


def season_ids_cross_club(in_list: str, column: str = "g.season_id") -> str:
    """Compare-mode variant: ``column`` matches an explicit inlined id list OR a
    cross-club sibling (shared ``grassroots_id``) of any id in it."""
    return (
        f"AND ({column} IN ({in_list}) OR {column} IN "
        f"(SELECT s5.id FROM seasons s5 WHERE s5.grassroots_id IS NOT NULL "
        f"AND s5.grassroots_id IN (SELECT s6.grassroots_id FROM seasons s6 "
        f"WHERE s6.id IN ({in_list}) AND s6.grassroots_id IS NOT NULL)))"
    )


def grade_base(col: str) -> str:
    """SQL expression: a grade name with a trailing sponsor parenthetical
    stripped, so "B Grade (DXC Technology)" and "B Grade" read as the SAME
    competition grade (CA decorates the grade name with the season's sponsor, so
    the same grade gets a different name year to year).

    Only a parenthetical with NO digit is stripped — sponsors are alphabetic
    ("(Solo Energy)", "(Raikot Group)"), whereas a genuine sub-grade usually
    carries a number ("(Div 1)", "(Section 2)"), so numbered grades stay
    distinct. The filter both lists and matches grades on this base, so picking
    "B Grade" scopes every sponsor variant of it."""
    return f"regexp_replace({col}, '\\s*\\([^)0-9]*\\)\\s*$', '')"


def grade_match_clause(col_expr: str) -> str:
    """``<base name> = ANY(...)`` against the ``:grade`` parameter, which may be a
    single grade name or several joined with ``||`` (multi-select). For a single
    name ``string_to_array`` yields a one-element array, so behaviour is
    identical to the old ``= :grade`` equality."""
    return f"{col_expr} = ANY(string_to_array(:grade, '||'))"


def grade_canonical_label(alias: str = "gr", org_param: str = "org") -> str:
    """SQL expression: a grade row's merge- and sponsor-aware grouping label.

    An admin can merge two genuinely different-looking raw grade names (e.g.
    "PSWL South" and "PSWL: South") into one competition via the merge-grades
    admin screen (``grade_merge_logs``: org-scoped active rows ``alias_name ->
    canonical_name``, at most one active row per alias, mirrored idempotently at
    startup in ``main.py``) — ``aggregations._GRADE_MATCH`` already honours this
    for leaderboards. BetterIQ's grade filter didn't, so a club with a merged
    grade saw both raw names as separate options that each only matched their
    own literal games. Resolves an active alias to its canonical raw name
    (single-hop, matching ``_GRADE_MATCH`` — merges are re-targeted onto the
    final root at merge time, not chased through a chain here), then strips the
    trailing sponsor parenthetical (``grade_base``) from whichever name applies,
    so team_grades()'s listing and season_grade_clause's matching agree."""
    own = grade_base(f"COALESCE({alias}.display_name_override, {alias}.name)")
    return (
        f"COALESCE("
        f"(SELECT {grade_base('gml.canonical_name')} FROM grade_merge_logs gml"
        f" WHERE gml.org_id = CAST(:{org_param} AS UUID)"
        f" AND gml.alias_name = {alias}.name AND gml.undone_at IS NULL LIMIT 1), "
        f"{own})"
    )


def season_grade_clause(season_id, grade_id, *, grade_alias: str = "gr", org_param: str = "org") -> str:
    """Combined season (year-expanded) + grade (by merged, sponsor-stripped
    name) filter for the per-game IQ queries, where the grades table is
    aliased ``gr`` by default. ``org_param`` is the already-bound org-id
    parameter name the caller's query uses (``org`` everywhere except iq.py's
    ``org_id`` — see ``grade_canonical_label``)."""
    parts = []
    if season_id:
        parts.append(season_member_clause(f"{grade_alias}.season_id", season_id))
    if grade_id:
        parts.append(f"AND {grade_match_clause(grade_canonical_label(grade_alias, org_param))}")
    return " ".join(p for p in parts if p)
