"""Which awards are a playing cap, and how a cap number reads.

A club records its cap numbers as awards: the achievement is the cap's name
("A Grade Cap Number", "1st XI Cap", "Club Cap") and the detail is the number.
Only an award KNOWN to be a cap is shown as "Cap 186", because the same detail
column holds "436 runs at 39.64" on a Best Batter and "captain" on a premiership.

The rule is the achievement's name: it ends in "Cap" or "Cap Number" as a whole
word (so "Captain" is not one). The Milestone > Cap Number "Player Number" award
is a cap too. ``frontend/src/lib/capAward.js`` is the same rule for the profile
badge; change them together.
"""
from __future__ import annotations

import re

_CAP_NAME = re.compile(r"\bcap(?:\s+number)?\s*$", re.I)
_NUMBER = re.compile(r"^\s*#?\s*(\d+)\s*$")


def is_cap_award(category, subcategory, achievement) -> bool:
    name = (achievement or "").strip()
    if (category or "") == "Milestone" and (subcategory or "") == "Cap Number" and name.lower() == "player number":
        return True
    return bool(_CAP_NAME.search(name))


def cap_number(detail) -> int | None:
    m = _NUMBER.match(str(detail)) if detail is not None else None
    return int(m.group(1)) if m else None


def cap_label(detail) -> str | None:
    """"Cap 186" for a detail that is a number, else None (show the detail as typed)."""
    n = cap_number(detail)
    return f"Cap {n}" if n is not None else None
