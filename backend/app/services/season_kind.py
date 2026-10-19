"""Which half of the year a season row is: winter, spring, autumn, or the main summer season.

Cricket Australia names a club's seasons "Summer 2026/27" and "Winter 2026", and
both rows carry `year = 2026`. Anything that treated the year as the season's
identity folded the two into one, so the public season filter drew "2026/27"
twice and a player's 2026/27 line swallowed their winter games.

The kind is read from the NAME, because that is the only place CA says it.
Summer and a name with no qualifier at all ("2025/26", "Season 2025") are the
same kind (''), so a club whose own row is called "2025/26" still folds a
neighbouring club's "Summer 2025/26" onto it, as it always has.

A club that wants winter and summer counted as one season per year sets
`organisations.amalgamate_seasons`; every caller then treats the kind as '' for
every row, which is the year-only rule this module replaced. See
`aggregations._SEASON_FOLD_CTE` and `season_aliases.resolve_season_filter`.
"""
from __future__ import annotations

import re
from typing import Optional

# Order matters only if a name holds two words ("Winter/Spring 2026"): first hit wins.
_KINDS = (("winter", "winter"), ("spring", "spring"), ("autumn", "autumn"))
_KIND_RE = re.compile(r"\b(winter|spring|autumn)\b", re.I)

# Integer code per kind, so a (year, kind) pair can ride in one integer column
# where a query compares years today (`summary_only_seasons`).
_CODES = {"": 0, "winter": 1, "spring": 2, "autumn": 3}


def season_kind(name: Optional[str]) -> str:
    """'winter', 'spring', 'autumn', or '' for summer and for an unlabelled name."""
    m = _KIND_RE.search(name or "")
    return m.group(1).lower() if m else ""


def season_kind_sql(name_col: str) -> str:
    """The same rule as `season_kind`, as a SQL expression over `name_col`."""
    return (
        f"(CASE WHEN {name_col} ~* '\\ywinter\\y' THEN 'winter' "
        f"WHEN {name_col} ~* '\\yspring\\y' THEN 'spring' "
        f"WHEN {name_col} ~* '\\yautumn\\y' THEN 'autumn' ELSE '' END)"
    )


def season_key_sql(year_col: str, name_col: str) -> str:
    """`year * 10 + kind code`: one integer per (year, kind). NULL when the year is NULL."""
    return (
        f"({year_col} * 10 + (CASE WHEN {name_col} ~* '\\ywinter\\y' THEN 1 "
        f"WHEN {name_col} ~* '\\yspring\\y' THEN 2 "
        f"WHEN {name_col} ~* '\\yautumn\\y' THEN 3 ELSE 0 END))"
    )
