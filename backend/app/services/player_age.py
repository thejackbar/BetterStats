"""How old a player is, and who is allowed to be told.

One vocabulary, shared by the profile, the club roster payload and
BetterSelect's selection pool. Two copies of "can this screen show an age"
is how a club that restricted ages to juniors ends up with an adult's
birthday on one screen and not another.

Nothing here stores an age. ``players.date_of_birth`` is the record and the
age is worked out on every read (migration 268) — a stored age is wrong from
the day after it was written.
"""
from __future__ import annotations

from datetime import date

# A date of birth outside this is a typo (a mis-keyed year, a date pasted
# from the wrong column), not a person. Rejected on write and treated as
# unknown on read, so one bad row shows nothing rather than "age 1,026".
MAX_AGE_YEARS = 120

# The ages a club can restrict BetterSelect's display to. Bounded so the
# settings screen and the API agree on what is a sane answer; NULL/None is
# the separate "every player" case and is not in this list.
MIN_AGE_LIMIT = 5
MAX_AGE_LIMIT = 99


def age_on(dob: date | None, as_of: date | None = None) -> int | None:
    """Whole years old on ``as_of`` (today by default), or None.

    None for no date of birth, for a date in the future, and for anything
    past ``MAX_AGE_YEARS`` — all three mean "we cannot say", which is what a
    screen should render as nothing rather than as a number.

    The month/day tuple comparison is what makes a birthday land on the
    right day, leap years included: someone born 29 Feb turns a year older
    on 1 March in a non-leap year, because (3, 1) is not less than (2, 29).
    """
    if not dob:
        return None
    as_of = as_of or date.today()
    years = as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))
    if years < 0 or years > MAX_AGE_YEARS:
        return None
    return years


def dob_error(dob: date | None, as_of: date | None = None) -> str | None:
    """Why this date of birth can't be stored, or None if it's fine.

    Returned as a message rather than raised so the caller decides the
    status code; clearing the field (None) is always allowed.
    """
    if dob is None:
        return None
    as_of = as_of or date.today()
    if dob > as_of:
        return "Date of birth can't be in the future"
    if age_on(dob, as_of) is None:
        return f"Date of birth can't be more than {MAX_AGE_YEARS} years ago"
    return None


def clean_age_limit(value) -> int | None:
    """A club's "only show ages under X" setting, or None for every player.

    Anything outside the sane range — including 0, which a browser sends for
    an empty number input — clears back to None rather than saving, so the
    setting can never mean "show nobody" while reading as switched on.
    """
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None
    if not MIN_AGE_LIMIT <= limit <= MAX_AGE_LIMIT:
        return None
    return limit


def age_is_visible(age: int | None, org) -> bool:
    """Whether ``org``'s BetterSelect settings allow showing this age."""
    if age is None or org is None:
        return False
    if not getattr(org, "select_show_age", False):
        return False
    limit = clean_age_limit(getattr(org, "select_show_age_under", None))
    return limit is None or age < limit


def visible_age(dob: date | None, org, as_of: date | None = None) -> int | None:
    """The age BetterSelect may show for this player, or None.

    Call this — never ``age_on`` — anywhere the answer leaves the server for
    a selection or roster screen. A club showing ages for under-16s only
    should not be sending its adults' ages to a browser that has simply been
    told not to draw them.
    """
    age = age_on(dob, as_of)
    return age if age_is_visible(age, org) else None
