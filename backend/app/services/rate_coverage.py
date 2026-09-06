"""One definition of "this rate can be worked out from what we hold".

A batting strike rate and a bowling economy are both a RATIO, and a ratio is
only meaningful when its numerator and its denominator come from the same
innings. Every rate in this app used to be ``SUM(runs) / SUM(balls)`` across a
whole season or career, which quietly mixes two different populations:

    500 runs across 10 innings, of which only 3 carry a ball count (150 balls)
    -> SUM(runs) / SUM(balls) = 333.33

The runs from the seven un-balled innings land in the numerator and nothing
lands in the denominator behind them. The right answer is 100, worked out from
the three innings that can actually answer the question, with a note saying so.

This is the rule ``sync._derive_partnerships_grassroots`` already applies to
stands: when the inputs do not reconcile, refuse to derive a figure from them
rather than publishing a wrong one.

What counts as covered
----------------------
An innings is covered when it carries a ball count that could actually carry
its runs:

* ``balls`` recorded and greater than zero -> covered.
* ``balls`` recorded as zero with zero runs -> covered. A batter run out at the
  non-striker's end without facing is a real innings and contributes 0 to both
  halves, so counting it keeps the coverage fraction honest.
* ``balls`` recorded as zero with runs on the board -> NOT covered. The source
  dropped the count; the runs are real and the zero is not.
* ``balls`` NULL -> not covered. This is what an Upload Scorecard with the
  "balls faced" column untracked writes (v8.80.1).

That third case is load-bearing and is not defensive coding. ``sync.py``'s
Grassroots scorecard reader writes ``balls=row.get("ballsFaced") or 0``, so a
missing ball count from CA has always landed in the database as a zero rather
than a NULL. Testing ``balls IS NOT NULL`` alone would therefore read every one
of those innings as covered and reproduce the very bug this module exists to
fix, one level down. The sync now preserves NULL going forward; the zero-with-
runs test is what covers the history already stored.

Bowling is the same shape with overs in place of balls. It is the milder case,
because a scorer who writes nothing else still writes the overs, so most clubs
will find their economy fully covered and no note drawn.

Coverage is reported, never silently applied
--------------------------------------------
Every reader emits ``(counted, of)`` alongside the figure so a screen can say
"worked out from 3 of 10 innings". A rate covering everything draws no note, or
the note becomes noise on every figure in the app and stops being read.
"""

from __future__ import annotations

from typing import Optional


# ─── SQL ──────────────────────────────────────────────────────────────────────

def batting_covered_sql(alias: str = "bi") -> str:
    """Is this batting innings' ball count able to carry its runs?"""
    return (
        f"({alias}.balls IS NOT NULL "
        f"AND ({alias}.balls > 0 OR COALESCE({alias}.runs, 0) = 0))"
    )


def bowling_covered_sql(alias: str = "bs") -> str:
    """Is this spell's overs figure able to carry the runs conceded?"""
    return (
        f"({alias}.overs IS NOT NULL "
        f"AND ({alias}.overs > 0 OR COALESCE({alias}.runs, 0) = 0))"
    )


def overs_to_balls_sql(col: str) -> str:
    """Cricket notation to balls: 10.2 overs is 10 overs and 2 balls, not 10.2."""
    return f"(FLOOR({col}) * 6 + ROUND(({col} - FLOOR({col})) * 10))"


def batting_rate_columns(alias: str = "bi", prefix: str = "", extra: str = "") -> str:
    """Select-list fragment: the covered halves of a batting strike rate.

    Emitted as raw sums rather than a finished rate so a caller blending these
    with another source can add them up first and divide once, which is the
    same rule the averages here already follow.

    ``extra`` is ANDed into the filter for a query whose rows are wider than the
    innings the rate is about — a select that keeps did-not-bat rows for their
    counts has to leave them out of the coverage, or a 0 off 0 nobody batted in
    reads as an innings that answered the question.
    """
    cov = batting_covered_sql(alias)
    if extra:
        cov = f"({cov} AND ({extra}))"
    return (
        f"COALESCE(SUM({alias}.runs) FILTER (WHERE {cov}), 0) AS {prefix}covered_runs,\n"
        f"COALESCE(SUM({alias}.balls) FILTER (WHERE {cov}), 0) AS {prefix}covered_balls,\n"
        f"COUNT(*) FILTER (WHERE {cov}) AS {prefix}covered_innings"
    )


def bowling_rate_columns(alias: str = "bs", prefix: str = "", extra: str = "") -> str:
    """Select-list fragment: the covered halves of a bowling economy."""
    cov = bowling_covered_sql(alias)
    if extra:
        cov = f"({cov} AND ({extra}))"
    balls = overs_to_balls_sql(f"{alias}.overs")
    return (
        f"COALESCE(SUM({alias}.runs) FILTER (WHERE {cov}), 0) AS {prefix}covered_conceded,\n"
        f"COALESCE(SUM({balls}) FILTER (WHERE {cov}), 0) AS {prefix}covered_bowl_balls,\n"
        f"COALESCE(SUM({alias}.wickets) FILTER (WHERE {cov}), 0) AS {prefix}covered_wickets,\n"
        f"COUNT(*) FILTER (WHERE {cov}) AS {prefix}covered_spells"
    )


def batting_covered_count_sql(alias: str = "bi") -> str:
    """How many of these innings could answer a strike rate."""
    return f"COUNT(*) FILTER (WHERE {batting_covered_sql(alias)})"


def bowling_covered_count_sql(alias: str = "bs") -> str:
    """How many of these spells could answer an economy."""
    return f"COUNT(*) FILTER (WHERE {bowling_covered_sql(alias)})"


def strike_rate_sql(alias: str = "bi") -> str:
    """A batting strike rate over the covered innings only."""
    cov = batting_covered_sql(alias)
    return (
        f"ROUND(SUM({alias}.runs) FILTER (WHERE {cov})::numeric "
        f"/ NULLIF(SUM({alias}.balls) FILTER (WHERE {cov}), 0) * 100, 2)"
    )


def economy_sql(alias: str = "bs") -> str:
    """A bowling economy over the covered spells only."""
    cov = bowling_covered_sql(alias)
    balls = overs_to_balls_sql(f"{alias}.overs")
    return (
        f"ROUND(SUM({alias}.runs) FILTER (WHERE {cov})::numeric * 6 "
        f"/ NULLIF(SUM({balls}) FILTER (WHERE {cov}), 0), 2)"
    )


def innings_strike_rate_sql(alias: str = "bi", stored: str = "strike_rate") -> str:
    """ONE innings' own strike rate, derived rather than read off the column.

    ``batting_innings.strike_rate`` has a writer for a hand-entered manual
    innings and none at all for a synced one — CA's ``battingStrikeRate`` is
    only ever stamped onto the season aggregate — so the column is NULL for
    essentially every innings in the platform and the screens reading it drew a
    dash on every row.

    There is no population to mix at one innings: the runs and the balls are
    the same innings by construction. So the only question is whether the
    innings can answer at all, and ``NULLIF(balls, 0)`` answers it exactly the
    way :func:`batting_covered_sql` does — a NULL ball count, a count flattened
    to zero with runs on it, and a genuine 0 off 0 (a real innings, but not a
    rate) all come out NULL rather than as a figure nobody can stand behind.

    A stored figure is the FALLBACK, not the answer: where balls were recorded
    it must not contradict the two columns printed beside it, and where they
    were not it is the only thing we hold.
    """
    return (
        f"COALESCE(ROUND({alias}.runs::numeric / NULLIF({alias}.balls, 0) * 100, 2), "
        f"{alias}.{stored})"
    )


def bowling_strike_rate_sql(alias: str = "bs") -> str:
    """Balls per wicket, over the covered spells only."""
    cov = bowling_covered_sql(alias)
    balls = overs_to_balls_sql(f"{alias}.overs")
    return (
        f"ROUND(SUM({balls}) FILTER (WHERE {cov})::numeric "
        f"/ NULLIF(SUM({alias}.wickets) FILTER (WHERE {cov}), 0), 2)"
    )


# ─── Python ───────────────────────────────────────────────────────────────────

def is_batting_covered(runs, balls) -> bool:
    """Python mirror of :func:`batting_covered_sql`.

    The two are asserted against each other row by row in the verification
    suite rather than assumed to agree.
    """
    if balls is None:
        return False
    return int(balls) > 0 or int(runs or 0) == 0


def is_bowling_covered(runs, overs) -> bool:
    """Python mirror of :func:`bowling_covered_sql`."""
    if overs is None:
        return False
    return float(overs) > 0 or int(runs or 0) == 0


def overs_to_balls(overs) -> int:
    """Cricket notation to balls. 10.2 -> 62."""
    if overs is None:
        return 0
    whole = int(float(overs))
    part = round((float(overs) - whole) * 10)
    return whole * 6 + int(part)


def innings_strike_rate(runs, balls, stored=None, digits: int = 2) -> Optional[float]:
    """Python mirror of :func:`innings_strike_rate_sql`.

    The two are asserted against each other row by row in the verification
    suite rather than assumed to agree.
    """
    if balls:
        return round(float(runs or 0) * 100 / float(balls), digits)
    return round(float(stored), digits) if stored is not None else None


def strike_rate(runs, balls, digits: int = 2) -> Optional[float]:
    if not balls:
        return None
    return round(float(runs or 0) * 100 / float(balls), digits)


def economy(runs, balls, digits: int = 2) -> Optional[float]:
    if not balls:
        return None
    return round(float(runs or 0) * 6 / float(balls), digits)


def coverage(counted, of) -> dict:
    """The pair every rate rides with.

    ``of`` is the innings or spells in scope; ``counted`` is how many of them
    could answer the question. ``complete`` is what a screen tests before
    drawing a note: a fully covered figure says nothing extra.
    """
    counted = int(counted or 0)
    of = int(of or 0)
    return {
        "counted": counted,
        "of": of,
        "complete": of > 0 and counted >= of,
        "none": counted == 0,
    }


def qualifies(counted, minimum) -> bool:
    """Does a player clear a leaderboard's minimum?

    Counted on COVERED innings or spells, never on innings in scope. A player
    with ten innings and three ball counts has a three-innings strike rate, and
    letting them clear a ten-innings bar is exactly what the bar is there to
    stop.
    """
    return int(counted or 0) >= int(minimum or 0)


def with_coverage(row: dict) -> dict:
    """Turn the raw ``sr_``/``econ_`` counts on a row into the pair every rate rides with.

    ``basis`` is what a screen uses to word the note: a rate re-derived from
    scorecards can name the innings behind it, while one that could only come
    from a season total has nothing to count and says so instead.

    Presence-aware, so a query that never asked for coverage keeps its exact
    payload shape and no screen grows a key it does not use.
    """
    if "sr_counted" in row:
        counted = int(row.pop("sr_counted", 0) or 0)
        of = int(row.pop("sr_of", 0) or 0)
        row["strike_rate_coverage"] = {
            **coverage(counted, max(of, counted)),
            "basis": "innings" if counted else "aggregate",
        }
    if "econ_counted" in row:
        counted = int(row.pop("econ_counted", 0) or 0)
        of = int(row.pop("econ_of", 0) or 0)
        row["economy_coverage"] = {
            **coverage(counted, max(of, counted)),
            "basis": "innings" if counted else "aggregate",
        }
    return row
