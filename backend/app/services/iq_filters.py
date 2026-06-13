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
for the grade variant, ``:grade`` (a grade NAME). Callers bind these today.
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


def season_grade_clause(season_id, grade_id, *, grade_alias: str = "gr") -> str:
    """Combined season (year-expanded) + grade (by name) filter for the per-game
    IQ queries, where the grades table is aliased ``gr`` by default."""
    parts = []
    if season_id:
        parts.append(season_member_clause(f"{grade_alias}.season_id", season_id))
    if grade_id:
        parts.append(f"AND {grade_alias}.name = :grade")
    return " ".join(p for p in parts if p)
