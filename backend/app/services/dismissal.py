"""What counts as a dismissal, in one place.

A batting average is ``runs / (innings - not outs)``. Everything that surfaces
an average in this app agrees on that formula; what it has NOT always agreed on
is which innings are the not outs. This module is that one definition.

THE TWO RETIREMENTS ARE NOT THE SAME THING, and conflating them is the whole
reason this module exists. MCC Law 25.4 splits them:

  * **25.4.2 - "Retired - not out".** The batter retired through illness, injury
    or another unavoidable cause and did not resume. It is NOT a dismissal. No
    bowler is credited, and it does not go in the average's denominator.
  * **25.4.3 - "Retired - out".** The batter retired for any other reason
    without the opposing captain's consent. It IS a dismissal, credited to no
    bowler, and it counts against the average.

Cricket Australia's Grassroots feed carries both, as separate
``dismissalTypeId`` values, and treats them exactly the way the Law does.
Verified live against the feed rather than assumed (see the ids below).

**NEVER match these with ``LIKE 'retired%'``.** That single word is the
difference between "not a dismissal" and "a dismissal": it would sweep CA's
plain ``Retired`` (a genuine wicket under 25.4.3) in with the two not-out
retirements and start crediting batters with an average they have not earned -
the same bug this module fixes, pointed the other way. Match the whole phrase.
"""
from __future__ import annotations

# Cricket Australia ``dismissalTypeId`` values, enumerated from 260 real
# scorecards across 33 grades on the Grassroots feed:
#   0 Did Not Bat   1 Not Out   2 Caught   3 LBW   4 Bowled   5 Stumped
#   6 Run Out       8 Retired Hurt        13 Retired        14 Retired Not Out
#   15 Absent
#
# The three that are NOT dismissals. Confirmed against CA's own season
# aggregates, which is the authority we reconcile to:
#   * 1  - trivially.
#   * 14 - Lily Thompson (Payneham CC, SGCL Metro U18, 2025/26): 8 innings,
#          77 runs, two plain not outs and one Retired Not Out. CA reports
#          ``battingNotOuts: 3`` and ``battingAverage: 15.4`` = 77 / (8 - 3).
#   * 8  - Retired Hurt. Law 25.4.2 names injury explicitly, CA's own naming
#          says so, and ``sync._NON_WICKET_DT`` has always treated it as a
#          non-wicket for fall-of-wickets. A CA aggregate carrying one has not
#          been reconciled directly, so this one rests on the Law rather than
#          on a measurement.
#
# 13 ("Retired") is deliberately absent. That is Law 25.4.3's retired-out, and
# CA counts it as a dismissal: N Raux (Murrumbidgee, 2025/26) retired for 0 and
# CA reported it among his ``batting0s`` with ``battingNotOuts: 1`` for his one
# genuine not out - a duck and a wicket, not a reprieve.
NOT_OUT_DISMISSAL_IDS: frozenset[int] = frozenset({1, 8, 14})

# The same three by name, lowercased. Stored rows carry the name and not the
# id, and a manual or uploaded scorecard never had an id at all, so the name is
# what every read and every backfill matches on.
NOT_OUT_DISMISSAL_NAMES: frozenset[str] = frozenset({
    "not out",
    "retired not out",
    "retired hurt",
})

# A genuine dismissal that credits no bowler (Law 25.4.3). Kept as its own name
# so the record book can still list it among the unusual ways of getting out.
RETIRED_OUT_NAMES: frozenset[str] = frozenset({"retired", "retired out"})


def normalise_dismissal(name: str | None) -> str:
    """Lowercase and collapse whitespace so 'Retired  Not Out' and
    'retired not out' compare equal."""
    return " ".join((name or "").split()).lower()


def is_not_out(dismissal_type_id: int | None = None, dismissal_type: str | None = None) -> bool:
    """True when this innings ended without the batter being dismissed.

    Takes the id, the name, or both - a Grassroots scorecard has both, a
    hand-typed or photo-read card has only the name. Either one saying not out
    is enough; neither is ever ambiguous, since CA's ids and names agree.
    """
    if dismissal_type_id is not None and dismissal_type_id in NOT_OUT_DISMISSAL_IDS:
        return True
    return normalise_dismissal(dismissal_type) in NOT_OUT_DISMISSAL_NAMES


def not_out_sql(col: str) -> str:
    """SQL predicate matching the same three names on a stored column.

    The Python and SQL forms are asserted to agree row by row in
    ``backend/verification/verify_retired_not_out.py`` - two spellings of one
    rule is how the reader and the backfill start disagreeing about a career.
    """
    names = ", ".join(f"'{n}'" for n in sorted(NOT_OUT_DISMISSAL_NAMES))
    return f"LOWER(BTRIM(REGEXP_REPLACE({col}, '\\s+', ' ', 'g'))) IN ({names})"
