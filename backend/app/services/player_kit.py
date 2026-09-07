"""The club's kit record — one definition of what a shirt number and a kit size
are, shared by every writer.

Three writers exist and they must agree: the player profile (Core, which owns
the NUMBER), the BetterAdmin Directory (which owns the two SIZES), and the bulk
profile importer. Two copies of "what counts as a shirt number" is how a
spreadsheet upload starts storing something the profile form would refuse.

NOTHING HERE NORMALISES A SIZE TO A VOCABULARY, and that is deliberate. A club
buys from whichever supplier it buys from: "Youth 12", "2XL", "34" and "Small"
are all real answers, and a controlled list would mean a club whose supplier
sizes in centimetres has nowhere to put the truth. The only rules are trim,
collapse the inner whitespace, and cap the length so a pasted paragraph can't
land in a column a team sheet prints.

A number is TEXT for the same reason ``afl_player_game_lines.jumper_number``
is: a club that issues "07" or "00" means it.
"""
from __future__ import annotations

import re

# Long enough for "100" and for the "00" a club really does issue; short enough
# that the column can only ever hold something a shirt could carry.
SHIRT_NUMBER_MAX = 4
# Long enough for "Youth 12 (152cm)"; short enough to stay a size.
KIT_SIZE_MAX = 24

_WS = re.compile(r"\s+")


def _clean(v, cap: int):
    if v is None:
        return None
    s = _WS.sub(" ", str(v)).strip()
    return s[:cap] if s else None


def clean_shirt_number(v):
    """The number as the club writes it, or None. An empty string clears it —
    the PATCH readers all use ``exclude_unset``, so a present blank IS the
    intent to clear, and only an ABSENT key leaves the stored value alone."""
    return _clean(v, SHIRT_NUMBER_MAX)


def clean_kit_size(v):
    """A shirt or pants size as the club writes it, or None. Same clear rule."""
    return _clean(v, KIT_SIZE_MAX)
