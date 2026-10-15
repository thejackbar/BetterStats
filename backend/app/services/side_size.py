"""The one rule for how many players a side's XI holds (0 = no limit).

Kept free of imports so any router can use it. Women's and junior sides often
name 7 or 9, so there is no short list of allowed numbers: a club may save 0 or
any whole number from 1 to MAX_SIDE_SIZE.
"""

MAX_SIDE_SIZE = 30


def valid_side_size(n) -> bool:
    return isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= MAX_SIDE_SIZE


def valid_min_size(min_size, size) -> bool:
    """A minimum a team may save, given the size it is saved with: a whole number
    from 1 to MAX_SIDE_SIZE that sits BELOW the size (a minimum equal to the size
    is just a full side). With no limit (size 0) any number in range will do."""
    if not isinstance(min_size, int) or isinstance(min_size, bool):
        return False
    if not 1 <= min_size <= MAX_SIDE_SIZE:
        return False
    return not size or min_size < size


def effective_min(min_size, size):
    """The minimum that counts for a team, or None. A stored minimum that no
    longer sits below the size (the size was lowered later) is no minimum, so a
    stale number can never make a full side read as short."""
    return min_size if min_size is not None and valid_min_size(min_size, size) else None
