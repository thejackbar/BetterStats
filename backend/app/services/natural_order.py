"""One ordering for names that carry a number: squads, teams and grades.

Read digits as numbers, so "1st XI" comes before "2nd XI" and both before
"10th XI" (a plain alphabetical sort puts "10th" between "1st" and "2nd").
Everything that sorts a squad, team or grade name for display goes through
`natural_key`, so no list can disagree with another. Frontend twin:
`frontend/src/lib/naturalSort.js`; keep the two in step.

A name without a number sorts after the plain club name and the numbered sides
that share its start ("Applecross", then "Applecross 1st XI" ... "Applecross 10th XI",
then "Applecross A", "Applecross Colts"), because a digit run is read as a number
and compares as less than any letter at that spot.
"""
from __future__ import annotations

import re

_DIGITS = re.compile(r"(\d+)")


def natural_key(name: str | None) -> list:
    """Sort key: text and numbers alternate (text first, always), so two keys
    always compare without mixing a string with an integer."""
    return [int(p) if i % 2 else p for i, p in enumerate(_DIGITS.split((name or "").casefold()))]
