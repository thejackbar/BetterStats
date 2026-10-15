"""The one rule for how many players a side's XI holds (0 = no limit).

Kept free of imports so any router can use it. Women's and junior sides often
name 7 or 9, so there is no short list of allowed numbers: a club may save 0 or
any whole number from 1 to MAX_SIDE_SIZE.
"""

MAX_SIDE_SIZE = 30


def valid_side_size(n) -> bool:
    return isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= MAX_SIDE_SIZE
