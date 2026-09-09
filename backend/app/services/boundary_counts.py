"""What a batter's boundary counts CAN be, given the runs beside them.

Reported off the record boards: "most sixes in an innings" was topped by a
2006 Under 12 innings of **8 runs off 0 balls with 1 four and 30 sixes**.
Verified against Cricket Australia's own live feed rather than assumed — it
sends `foursScored: 1, sixesScored: 30` for that innings, so a scorer twenty
years ago typed something else into the sixes box and CA has carried it ever
since. The CricketStatz import reads the same match's card correctly (8 runs,
1 four, 0 sixes), which is how the two were told apart.

**SIX RUNS PER SIX IS ARITHMETIC, NOT A JUDGEMENT.** A batter cannot have hit
more in boundaries than they scored, so `fours * 4 + sixes * 6 <= runs` is a
hard bound that holds for every innings ever played. A count that breaks it is
not a boundary count at all, and publishing it puts an impossible innings at
the top of a record board.

**IT READS AS NOT RECORDED, NOT AS ZERO**, which is the same call
`sync.py` already makes for a missing ball count: a 0 says the batter hit no
boundaries, and that is a different claim from "this column cannot be read".
NULL keeps it out of a total without asserting anything.

**EACH COLUMN IS JUDGED ON ITS OWN FIRST.** In the reported innings the fours
are perfectly possible and only the sixes are not, so nulling both would throw
away a figure that is fine. Only when the pair still cannot fit the runs
together does the other one go too.

Deliberately NOT applied to runs: the runs are what every other figure is
reconciled against, and a bad boundary count is no reason to doubt them.
"""
from __future__ import annotations

from typing import Optional


def clean(runs: Optional[int], fours: Optional[int],
          sixes: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    """The boundary counts as they can be read, or None where they cannot."""
    if runs is None or runs < 0:
        # Nothing to check against. Whatever is here is what we were given.
        return fours, sixes

    if fours is not None and (fours < 0 or fours * 4 > runs):
        fours = None
    if sixes is not None and (sixes < 0 or sixes * 6 > runs):
        sixes = None
    if (fours or 0) * 4 + (sixes or 0) * 6 > runs:
        # Each is possible alone and the two together are not, so there is no
        # telling which is wrong.
        return None, None
    return fours, sixes


def is_impossible(runs: Optional[int], fours: Optional[int],
                  sixes: Optional[int]) -> bool:
    """Would `clean` change this row? What the backfill counts."""
    return clean(runs, fours, sixes) != (fours, sixes)
