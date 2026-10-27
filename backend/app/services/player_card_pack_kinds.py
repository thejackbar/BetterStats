"""Player Cards: the kinds of pack, what is in each, and the calendar of packs that arrive on a day.

A pack is five cards. What differs between kinds is the odds (`weights`, by tier), how many of the five are guaranteed
Rare or better (`rare_plus`) and the chance a card is a special card. Standard packs (starter, weekly, earned by runs, wickets
and dismissals, duck) are unchanged. Packs for something the player did (a century, a five-for, a hat-trick, a half
century, a milestone) are stacked with Rare and better cards. Packs for a day (Match Day, a holiday, a birthday, a
surprise drop, a Test match the club schedules) sit between the two.

Pure: nothing here touches the database, so the odds and the calendar can be checked directly.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Optional

STANDARD = {"common": 60, "rare": 28, "epic": 10, "legendary": 2}
DAY = {"common": 45, "rare": 35, "epic": 16, "legendary": 4}
EVENT = {"common": 40, "rare": 35, "epic": 20, "legendary": 5}
FIFTY = {"common": 20, "rare": 45, "epic": 28, "legendary": 7}
MILESTONE = {"common": 12, "rare": 43, "epic": 33, "legendary": 12}
FIVE_FOR = {"common": 8, "rare": 37, "epic": 38, "legendary": 17}
CENTURY = {"common": 5, "rare": 35, "epic": 40, "legendary": 20}


@dataclass(frozen=True)
class Kind:
    label: str
    line: str
    weights: dict
    rare_plus: int = 1          # how many of the five are Rare or better, at least
    special: float = 0.05       # the chance a card is a special card


def _std(label: str, line: str) -> Kind:
    return Kind(label, line, STANDARD, 1, 0.05)


KINDS: dict[str, Kind] = {
    "starter": _std("Starter pack", "Welcome to the club"),
    "weekly": _std("Weekly pack", "Fresh this week"),
    "runs": _std("Runs pack", "Earned with the bat"),
    "wickets": _std("Wickets pack", "Earned with the ball"),
    "dismissals": _std("Dismissals pack", "Earned in the field"),
    "duck": _std("Duck pack", "Better luck next time"),
    # For a day
    "match_day": Kind("Match Day pack", "You are playing today", DAY, 2, 0.08),
    "birthday": Kind("Birthday pack", "Many happy returns", EVENT, 2, 0.10),
    "mystery": Kind("Surprise pack", "A random drop", EVENT, 2, 0.10),
    "halloween": Kind("Halloween pack", "Trick or treat", EVENT, 2, 0.10),
    "melbourne_cup": Kind("Melbourne Cup pack", "The race that stops a nation", EVENT, 2, 0.10),
    "christmas": Kind("Christmas pack", "Merry Christmas", EVENT, 2, 0.10),
    "boxing_day": Kind("Boxing Day pack", "Test cricket day", EVENT, 2, 0.10),
    "new_year": Kind("New Year pack", "A fresh start", EVENT, 2, 0.10),
    "australia_day": Kind("Australia Day pack", "Good on ya", EVENT, 2, 0.10),
    "anzac_day": Kind("Anzac Day pack", "Lest we forget", EVENT, 2, 0.10),
    "event": Kind("Event pack", "Today only", EVENT, 2, 0.10),   # a day the club has scheduled (a Test match, a club day)
    # For something the player did
    "century": Kind("Century pack", "A hundred. Take a bow", CENTURY, 4, 0.15),
    "five_for": Kind("Five-for pack", "Five wickets or more", FIVE_FOR, 4, 0.15),
    "hat_trick": Kind("Hat-trick pack", "Three in three", FIVE_FOR, 4, 0.15),
    "fifty": Kind("Fifty pack", "Fifty up", FIFTY, 3, 0.10),
    "milestone": Kind("Milestone pack", "A landmark reached", MILESTONE, 3, 0.12),
}
DEFAULT_KIND = KINDS["weekly"]

# Special card kinds that earn a pack the day the card is made for a recent event, and the pack each earns.
ACHIEVEMENT_PACKS = {
    "century": "century", "five_for": "five_for", "hat_trick": "hat_trick", "fifty": "fifty",
    "games": "milestone", "runs_milestone": "milestone", "wickets_milestone": "milestone", "dismissals_milestone": "milestone",
}

# How often a surprise pack drops: one day in this many, the same day for everyone in a club.
MYSTERY_ONE_IN = 12

# Packs that need a person to be there on the day. They are granted when the player opens their page that day and are theirs to
# keep until opened (a missed day is a missed pack).
DAY_SOURCES = ("match_day", "birthday", "mystery", "halloween", "melbourne_cup", "christmas", "boxing_day", "new_year",
               "australia_day", "anzac_day", "event")


def kind_for(source: Optional[str]) -> Kind:
    return KINDS.get(source or "", DEFAULT_KIND)


def label_for(source: Optional[str]) -> str:
    return kind_for(source).label if source in KINDS else "Pack"


def annual_events(d: date) -> list[tuple[str, str]]:
    """The holiday packs for a day: `[(source, ref_key)]`, the ref carrying the year so each comes once a year."""
    out: list[str] = []
    if (d.month, d.day) == (10, 31):
        out.append("halloween")
    if d.month == 11 and d.weekday() == 1 and d.day <= 7:   # the first Tuesday of November
        out.append("melbourne_cup")
    for md, source in (((12, 25), "christmas"), ((12, 26), "boxing_day"), ((1, 1), "new_year"), ((1, 26), "australia_day"), ((4, 25), "anzac_day")):
        if (d.month, d.day) == md:
            out.append(source)
    return [(s, f"{s}:{d.year}") for s in out]


def is_mystery_day(org_id, d: date, one_in: int = MYSTERY_ONE_IN) -> bool:
    """A surprise pack day: decided by the club and the date alone, so everyone sees the same days and nothing is stored."""
    digest = hashlib.sha256(f"mystery:{org_id}:{d.isoformat()}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % one_in == 0


def is_birthday(dob: Optional[date], d: date) -> bool:
    if dob is None:
        return False
    if (dob.month, dob.day) == (2, 29) and not _leap(d.year):
        return (d.month, d.day) == (2, 28)
    return (dob.month, dob.day) == (d.month, d.day)


def _leap(y: int) -> bool:
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
