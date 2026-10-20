"""A player's own page: which modules a club shows, and the data behind the new ones.

The page is the "My page" tab of the self-service link (``/avail/:token``), behind
the player's PIN cookie. The club picks which modules appear and in what order
(``organisations.player_dashboard_modules``); every player sees the same set, and
a module with nothing to say for a player (no fees record, a squad with no
Fines) simply drops out for them.

Every figure here is that one player's own. Two modules are held back when the
page cannot be trusted with them:

* ``fees`` needs the club's fees module AND the PIN switched on. The PIN is the
  last four digits of a mobile, which teammates often know, and with the PIN off
  anyone holding the link could open anybody's page, so with it off the fees
  module is never served. Fail closed.
* ``ladder`` names the player's squad, so it follows the same Show squad switch
  as the rest of the page. (``votes`` and ``fines`` draw nothing unless something is due or on; ``squad`` itself stays served with the switch off: it
  then says so, which is what the page always did.)
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import MODULE_FEES, org_has_module
from app.models.db import FeeMember, Organisation, Player, Season
from app.services import fees as fee_service
from app.services import grade_scope
from app.services.aggregations import get_season_by_season

# key, label, one line for the admin list, and the keys on by default.
CATALOGUE: list[dict] = [
    {"key": "availability", "label": "Your availability",
     "blurb": "Their answers for the next few games."},
    {"key": "votes", "label": "Votes",
     "blurb": "Reminds them to vote on games they played that are still open. Shows only when a vote is due."},
    {"key": "squad", "label": "Your squad",
     "blurb": "The squads they are in. While Show squad is off it says the club hasn't turned squad names on."},
    {"key": "selected", "label": "Selected",
     "blurb": "Sides they are picked in, once the selectors lock them."},
    {"key": "training", "label": "Training",
     "blurb": "Upcoming nets and how often they have turned up lately."},
    {"key": "ladder", "label": "Ladder",
     "blurb": "Where their team sits on the competition ladder. Needs Show squad on."},
    {"key": "season", "label": "Season overview",
     "blurb": "Their matches, runs, wickets and catches this season."},
    {"key": "fees", "label": "Fees owing",
     "blurb": "What they owe the club this season. Needs BetterAdmin fees and the PIN on."},
    {"key": "fines", "label": "Fines",
     "blurb": "Fines owed and how to pay into the pot. Shows only for squads that turn Fines on."},
]
KEYS = [m["key"] for m in CATALOGUE]

# What every club had before the club could choose: the original page, plus
# fines (which draws nothing unless a squad switches Fines on).
DEFAULT_MODULES = ["availability", "votes", "squad", "selected", "training", "fines"]


def normalise(keys) -> list[str]:
    """Known keys only, once each, in the order given."""
    out: list[str] = []
    for k in keys or []:
        if isinstance(k, str) and k in KEYS and k not in out:
            out.append(k)
    return out


# A module that draws nothing unless something is due. A club's saved list is
# the modules it chose from the ones it was OFFERED, so one that arrived later
# is switched on for it rather than silently missing: a club cannot have turned
# off what it never saw. Saving the list records what was on offer.
AUTO_ON_WHEN_NEW = ("votes",)
# What a list saved before `known` was recorded had been offered.
LEGACY_KNOWN = [k for k in KEYS if k not in AUTO_ON_WHEN_NEW]


def store(keys) -> dict:
    """The value to save for a club's chosen modules: the ordered list that is on,
    and every module that was on offer when it was chosen."""
    return {"on": normalise(keys), "known": list(KEYS)}


def enabled_modules(club: Organisation) -> list[str]:
    """The club's chosen modules, or the old page if it never chose. An explicit
    empty list is a choice (everything off), so test None and not falsiness. The
    stored value is a bare list (saved before `known` existed) or `store()`'s dict."""
    raw = club.player_dashboard_modules
    if raw is None:
        return list(DEFAULT_MODULES)
    if isinstance(raw, dict):
        on, known = normalise(raw.get("on")), normalise(raw.get("known")) or list(LEGACY_KNOWN)
    else:
        on, known = normalise(raw), list(LEGACY_KNOWN)
    for key in AUTO_ON_WHEN_NEW:
        if key not in known and key not in on:
            # Beside Availability when it is on, else first: a reminder belongs near the top.
            on.insert(on.index("availability") + 1 if "availability" in on else 0, key)
    return on


def blocked_reason(club: Organisation, key: str) -> Optional[str]:
    """Why a module cannot be shown to this club's players, or None."""
    if key == "fees":
        if not org_has_module(club, MODULE_FEES):
            return "Needs the BetterAdmin fees module."
        if not club.availability_require_pin:
            return "Turn the PIN on first. With no PIN anyone with the link could open a player's fees."
    if key == "ladder" and not club.availability_show_squad:
        return "Turn Show squad on first."
    return None


def catalogue_for(club: Organisation) -> list[dict]:
    """Every module for the admin list: the club's chosen ones first, in the
    club's order, then the rest in catalogue order. `blocked` says why a module
    cannot be shown to this club's players yet (the page then leaves it out)."""
    on = enabled_modules(club)
    by_key = {m["key"]: m for m in CATALOGUE}
    ordered = [by_key[k] for k in on] + [m for m in CATALOGUE if m["key"] not in on]
    return [
        {**m, "enabled": m["key"] in on, "blocked": blocked_reason(club, m["key"])}
        for m in ordered
    ]


def served_modules(club: Organisation) -> list[str]:
    """The enabled modules, in order, minus any this club may not show."""
    return [k for k in enabled_modules(club) if blocked_reason(club, k) is None]


def _num(v):
    if v is None:
        return None
    f = float(v)
    return int(f) if f.is_integer() else round(f, 2)


async def season_overview(db: AsyncSession, club: Organisation, player: Player) -> Optional[dict]:
    """The player's most recent season in one small block, under the same grade
    scope their public profile uses (so the figures match it). None when they
    have no recorded games."""
    scope, auto_shown = await grade_scope.resolve_scope_for_player(
        db, club.id, str(player.id), None,
        auto_widen=bool(club.stats_auto_show_played_grades),
    )
    rows = await get_season_by_season(db, str(player.id), include_prior=False, scope=scope)
    if not rows:
        return None
    r = rows[0]
    if not (r.get("matches") or r.get("total_runs") or r.get("total_wickets") or r.get("total_catches")):
        return None
    return {
        "season": r.get("season_name"),
        "matches": _num(r.get("matches")) or 0,
        "runs": _num(r.get("total_runs")) or 0,
        "high_score": _num(r.get("high_score")),
        "batting_average": _num(r.get("batting_average")),
        "wickets": _num(r.get("total_wickets")) or 0,
        "best_bowling": r.get("best_bowling_figures") or None,
        "catches": _num(r.get("total_catches")) or 0,
        "auto_shown": bool(auto_shown),
    }


async def fees_owing(db: AsyncSession, club: Organisation, player: Player) -> dict:
    """The player's fee position this season, from the same snapshot the member
    portal reads. ``None`` fields never mean zero: a player with no fee record
    gets ``on_record: False`` so the page says so instead of showing $0."""
    member = (await db.execute(
        select(FeeMember).where(
            FeeMember.organisation_id == club.id, FeeMember.player_id == player.id)
    )).scalar_one_or_none()
    snap = await fee_service.member_financial_snapshot(db, club.id, member.id) if member else None
    if snap is None:
        return {"on_record": False}
    fin = snap["financials"]
    season = await db.get(Season, snap["season_id"])
    return {
        "on_record": True,
        "season": season.name if season else None,
        "status": fin.get("status"),
        "membership_outstanding": fin.get("membership_outstanding", 0.0),
        "match_fee_outstanding": fin.get("match_fee_outstanding", 0.0),
        "total_outstanding": fin.get("total_outstanding", 0.0),
        "total_paid": fin.get("total_paid", 0.0),
        "credit": fin.get("credit", 0.0),
    }
