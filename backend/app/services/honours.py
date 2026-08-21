"""Premiership squads and office-bearer boards, read out of the honours a club
has already recorded against its players.

Deliberately sport-agnostic and shared by BOTH silos. ``player_achievements``
is the same table in a cricket database and a football one, with the same
columns and the same vocabulary for the two categories this reads
(``Premiership`` and ``Office Bearer``) — so a second copy per sport would be
two things to keep in step for no gain, and the day one is fixed is the day
the two start disagreeing about who won what.

Nothing here is entered twice. A club records a premiership or a committee
term once, on the player, and these two readings are that same data grouped
the two ways a club wants to read it back: the squad that won a flag, and the
list of everyone who has held a role.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PREMIERSHIP_CATEGORY = "Premiership"
OFFICE_BEARER_CATEGORY = "Office Bearer"

# ``player_achievements.season`` holds EITHER a seasons-table id (what an
# Awards screen writes) or a plain label like "2025/26" (what an import
# writes), and both are in live data — so the season is resolved through a
# guarded join rather than assumed to be one or the other. Same pattern
# routers/website.py already uses for its own honours reads.
_SEASON_JOIN = """
    LEFT JOIN seasons s ON s.id = CASE
        WHEN pa.season ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN pa.season::uuid ELSE NULL END
    LEFT JOIN seasons se ON se.id = CASE
        WHEN pa.season_end ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN pa.season_end::uuid ELSE NULL END
"""

# The order a club reads its committee in. Anything it has invented for
# itself sorts after the lot rather than being dropped.
_GROUP_ORDER = [
    "Executive Committee",
    "General Committee",
    "Committee",
    "Captains",
    "Coaches",
    "Other Roles",
]

# Within a group, the seats a club expects at the top. Everything else falls
# back to alphabetical, so a role nobody anticipated still has a stable place.
_ROLE_PRIORITY = {
    "president": 0, "chairman": 0, "chairperson": 0,
    "vice president": 1,
    "secretary": 2,
    "treasurer": 3,
    "operations": 4,
    "head coach": 5, "club coach": 5,
}

# A squad member's part in the win. Everyone recorded against the flag is in
# the squad; this only decides who is listed first and what sits under their
# name.
_SQUAD_ROLE_PRIORITY = {
    "captain": 0,
    "vice captain": 1,
    "player of the grand final": 2,
    "player of the final": 2,
    "best on ground — grand final": 2,
    "best on ground - grand final": 2,
    "coach": 3,
}
# The plain "they were in the side" award, which is not worth printing under
# somebody's name — it is what every row on the card already means.
_PLAIN_SQUAD_AWARDS = {"premiership", "premierships", "player"}


def year_of(label: Optional[str], year: Optional[int] = None) -> Optional[int]:
    """A season's start year, from the seasons row where we have one and from
    the first four-digit number in its name where we don't."""
    if year is not None:
        return year
    m = re.search(r"(\d{4})", label or "")
    return int(m.group(1)) if m else None


def _sort_name(name: Optional[str]) -> tuple:
    """Surname first, for the alphabetical order an honour board is read in.

    Not the whole string as typed: cricket renders a name as "Cole, S" for a
    club that has picked that format, so sorting on "Sam Cole" would hand that
    club a list that looks unsorted. Surname-then-rest is the same order under
    either rendering.
    """
    parts = re.sub(r"\s+", " ", (name or "").strip().lower()).split(" ")
    if not parts or parts == [""]:
        return ("", "")
    return (parts[-1], " ".join(parts[:-1]))


def _person_key(player_id: Optional[str], name: Optional[str]) -> str:
    """One person, however the row names them.

    A linked row keys on the player id; only a row with NO id at all falls
    back to the name. Same rule the player profile's own honour board keeps,
    and for the same reason: keying everything on the name would put one of
    two same-named players' honours onto the other.
    """
    if player_id:
        return "id:" + str(player_id)
    return "name:" + re.sub(r"\s+", " ", (name or "").strip().lower())


async def _rows(db: AsyncSession, org_id: uuid.UUID, category: str) -> list[dict]:
    res = await db.execute(text(f"""
        SELECT pa.id,
               pa.player_id::text AS player_id,
               COALESCE(p.display_name_override, p.name, pa.player_name) AS name,
               p.photo_url,
               COALESCE(s.name, pa.season)         AS season_name,
               s.year                              AS season_year,
               COALESCE(se.name, pa.season_end)    AS season_end_name,
               se.year                             AS season_end_year,
               pa.subcategory, pa.achievement, pa.detail
        FROM player_achievements pa
        LEFT JOIN players p ON p.id = pa.player_id
        {_SEASON_JOIN}
        WHERE pa.org_id = :org AND pa.category = :cat
    """), {"org": str(org_id), "cat": category})
    return [dict(r) for r in res.mappings().all()]


async def _renames(db: AsyncSession, org_id: uuid.UUID) -> dict:
    """A club's own rename of an award, applied on read.

    Resolved in Python rather than joined, so a club holding two definitions
    under one name can't fan a single honour out into two rows — the same call
    the player profile's honour board makes.
    """
    res = await db.execute(text("""
        SELECT category, subcategory, achievement, display_name
        FROM org_award_definitions
        WHERE org_id = :org AND display_name IS NOT NULL AND display_name <> ''
    """), {"org": str(org_id)})
    return {(d["category"], d["subcategory"] or "", d["achievement"]): d["display_name"]
            for d in res.mappings().all()}


async def premiership_squads(db: AsyncSession, org_id: uuid.UUID) -> dict:
    """Every flag the club has recorded, as the squad that won it.

    A flag is one (season, team) pair — that pairing IS the premiership, so a
    club whose Seniors and Reserves both won in one year gets two cards rather
    than one squad of twice the size.

    Somebody recorded only as that side's Captain is in the squad like anyone
    else: they plainly played, and a card that lists the team but leaves out
    the person who led it is wrong in the way a reader notices immediately.
    A person recorded twice for one flag (in the squad AND as its captain) is
    ONE player carrying both, never two rows.
    """
    rows = await _rows(db, org_id, PREMIERSHIP_CATEGORY)
    renames = await _renames(db, org_id)

    groups: dict[tuple, dict] = {}
    for r in rows:
        if not r["name"]:
            continue
        season = (r["season_name"] or "").strip()
        team = (r["subcategory"] or "").strip()
        key = (season.lower(), team.lower())
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "season": season or None,
                "year": year_of(season, r["season_year"]),
                "team": team or None,
                "players": {},
            }
        # The club's own label for this award, where it has renamed one.
        label = renames.get((PREMIERSHIP_CATEGORY, team, r["achievement"])) or r["achievement"]
        pkey = _person_key(r["player_id"], r["name"])
        p = g["players"].get(pkey)
        if p is None:
            p = g["players"][pkey] = {
                "player_id": r["player_id"],
                "name": r["name"],
                "photo_url": r["photo_url"],
                "roles": [],
                "detail": None,
            }
        if label and (label or "").strip().lower() not in _PLAIN_SQUAD_AWARDS:
            if label not in p["roles"]:
                p["roles"].append(label)
        # A note the club typed against the row ("12th man", "played 3") is
        # the club's own words and outranks nothing — it just rides along.
        if r["detail"] and not p["detail"]:
            p["detail"] = r["detail"]

    out = []
    for g in groups.values():
        players = list(g["players"].values())
        players.sort(key=lambda p: (
            min((_SQUAD_ROLE_PRIORITY.get(x.lower(), 50) for x in p["roles"]), default=50),
            _sort_name(p["name"]),
        ))
        out.append({**g, "players": players, "player_count": len(players)})

    # Newest first, and a flag whose season nobody recorded sorts last rather
    # than reading as year zero at the top of the page.
    out.sort(key=lambda g: (g["year"] is None, -(g["year"] or 0),
                            (g["team"] or "").lower()))
    return {"premierships": out}


def _merge_spans(years: list[tuple[int, Optional[int]]]) -> list[tuple[int, Optional[int]]]:
    """Consecutive seasons in one role become one span; a genuine gap stays two.

    Somebody who was President 2010-2012, stepped away, and came back in 2018
    held the role twice, and printing that as "2010–2019" would be a claim the
    club never made. Only touching or overlapping spans are joined.
    """
    spans = sorted(((a, b if b is not None else a) for a, b in years))
    merged: list[list] = []
    for start, end in spans:
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def _span_label(spans: list[tuple[int, Optional[int]]], open_ended: bool) -> str:
    parts = []
    for i, (a, b) in enumerate(spans):
        last = i == len(spans) - 1
        if last and open_ended:
            parts.append(f"{a}–present")
        elif b > a:
            parts.append(f"{a}–{b}")
        else:
            parts.append(str(a))
    return ", ".join(parts)


async def office_bearer_boards(db: AsyncSession, org_id: uuid.UUID) -> dict:
    """One board per role the club has recorded somebody in — President,
    Secretary, Club Coach and the rest — each listing who held it and when.

    The years come from the seasons the club filed each term under, folded
    into spans, so twelve yearly rows for one long-serving secretary read as
    the one line a reader expects rather than twelve.
    """
    rows = await _rows(db, org_id, OFFICE_BEARER_CATEGORY)
    renames = await _renames(db, org_id)

    boards: dict[tuple, dict] = {}
    for r in rows:
        if not r["name"] or not r["achievement"]:
            continue
        sub = (r["subcategory"] or "").strip()
        role = renames.get((OFFICE_BEARER_CATEGORY, sub, r["achievement"])) or r["achievement"]
        bkey = (sub.lower(), role.lower())
        b = boards.get(bkey)
        if b is None:
            b = boards[bkey] = {"group": sub or "Other Roles", "role": role, "holders": {}}
        pkey = _person_key(r["player_id"], r["name"])
        h = b["holders"].get(pkey)
        if h is None:
            h = b["holders"][pkey] = {
                "player_id": r["player_id"], "name": r["name"],
                "photo_url": r["photo_url"], "_years": [], "_open": False,
            }
        start = year_of(r["season_name"], r["season_year"])
        if start is None:
            # No year to place them by. Kept, because they DID hold the role
            # and dropping them would quietly shorten the club's own history;
            # they sort to the bottom of the board with no years shown.
            continue
        end = year_of(r["season_end_name"], r["season_end_year"])
        # An end that isn't a year at all ("Present", "Current") is the club
        # saying the term is still running, not a season we failed to parse.
        if r["season_end_name"] and end is None:
            h["_open"] = True
        h["_years"].append((start, end))

    out = []
    for b in boards.values():
        holders = []
        for h in b["holders"].values():
            spans = _merge_spans(h["_years"]) if h["_years"] else []
            holders.append({
                "player_id": h["player_id"],
                "name": h["name"],
                "photo_url": h["photo_url"],
                "from_year": spans[0][0] if spans else None,
                "to_year": (None if h["_open"] else spans[-1][1]) if spans else None,
                # The spans themselves, not only the sentence built from them.
                # A screen laying the years out in aligned columns needs the
                # two numbers apart; handing it one string would leave it
                # splitting on a dash it did not write.
                "spans": [
                    {"from": a,
                     "to": None if (h["_open"] and i == len(spans) - 1) else (b if b > a else None),
                     "open": h["_open"] and i == len(spans) - 1}
                    for i, (a, b) in enumerate(spans)
                ],
                "years": _span_label(spans, h["_open"]) if spans else None,
                "seasons": len(h["_years"]),
            })
        # Most recent term first; a holder with no year at all sorts last.
        holders.sort(key=lambda h: (h["from_year"] is None,
                                    -((h["to_year"] or h["from_year"]) or 0),
                                    _sort_name(h["name"])))
        out.append({"group": b["group"], "role": b["role"],
                    "holders": holders, "holder_count": len(holders)})

    def group_rank(name: str) -> int:
        try:
            return _GROUP_ORDER.index(name)
        except ValueError:
            return len(_GROUP_ORDER)

    out.sort(key=lambda b: (group_rank(b["group"]), b["group"].lower(),
                            _ROLE_PRIORITY.get(b["role"].lower(), 50),
                            b["role"].lower()))

    groups: list[dict] = []
    for b in out:
        if not groups or groups[-1]["group"] != b["group"]:
            groups.append({"group": b["group"], "boards": []})
        groups[-1]["boards"].append(b)
    return {"groups": groups}
