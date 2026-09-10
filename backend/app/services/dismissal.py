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


# ---------------------------------------------------------------------------
# Absence
# ---------------------------------------------------------------------------
# A BATTER WHO NEVER CAME IN IS SCORED DIFFERENTLY BY DIFFERENT COMPETITIONS,
# and the difference lands in the average. Shoalwater Bay Cricket Club settled
# it for their own archive (Sep 2026): "If you are named and absent, it gets
# recorded as 'absent out'. That is different from did not bat. This would make
# a difference to someone's average."
#
#   * "absent out"   IS a dismissal. It adds an innings AND a wicket, credited
#                    to no bowler, and the batter wears the duck - the same
#                    shape as Law 25.4.3's retired out.
#   * "absent hurt"  is NOT a dismissal, and not an innings either. Illness or
#                    injury, the same reasoning as Law 25.4.2's retirement.
#   * a bare "absent" IS AMBIGUOUS and only the club can settle it. Cricket
#                    Australia reads it as no innings at all (dismissalTypeId
#                    15, which `sync.py` stores as `did_not_bat=True` with
#                    `runs=None`), so that is the default here - but a
#                    competition using it as shorthand for absent out means the
#                    opposite, and an importer must ASK rather than assume.
#
# **NEVER match these with ``LIKE 'absent%'``**, which is the same trap this
# module already documents for ``LIKE 'retired%'``: one word is the difference
# between an innings that counts and one that does not, so a prefix sweeps
# "absent out" in with "absent hurt" and silently drops a real dismissal.
ABSENT_OUT_NAMES: frozenset[str] = frozenset({
    "absent out",
    "absent, out",
})

# Absent for a stated reason that is not a dismissal. No innings, no wicket.
ABSENT_NO_INNINGS_NAMES: frozenset[str] = frozenset({
    "absent hurt",
    "absent ill",
    "absent injured",
    "absent sick",
})

# The bare word, which says nothing about which of the two it means.
ABSENT_UNSTATED_NAMES: frozenset[str] = frozenset({"absent"})


def absent_reading(
    dismissal_type: str | None, *, bare_absent_is_out: bool = False
) -> str | None:
    """How an absence should be stored, or None when this is not an absence.

    Returns ``'out'`` for an innings that counts as a dismissal, or
    ``'no_innings'`` for one that counts as neither an innings nor a wicket.

    ``bare_absent_is_out`` is the CLUB's answer for the ambiguous bare word and
    nothing else - an explicit "absent out" or "absent hurt" already says which
    it is, and is read as written whatever the flag says. Defaulting it to
    False keeps Cricket Australia's reading, so a caller that never asks
    behaves exactly as this app always has.
    """
    name = normalise_dismissal(dismissal_type)
    if not name:
        return None
    if name in ABSENT_OUT_NAMES:
        return "out"
    if name in ABSENT_NO_INNINGS_NAMES:
        return "no_innings"
    if name in ABSENT_UNSTATED_NAMES:
        return "out" if bare_absent_is_out else "no_innings"
    return None
