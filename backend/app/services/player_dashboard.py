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

import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import MODULE_FANTASY, MODULE_FEES, MODULE_SELECT, org_has_module
from app.models.db import FeeMember, FeeMemberSeason, FeePayment, Organisation, Player, Season
from app.services import fees as fee_service
from app.services import grade_scope, player_form, session_safety
from app.services.aggregations import get_season_by_season

# key, label, one line for the admin list, and the keys on by default.
#
# Availability is not in this list: it is the point of the link, so the page
# always opens with the next games and the Available / Unavailable buttons.
CATALOGUE: list[dict] = [
    {"key": "cards", "label": "Player Cards",
     "blurb": "Their card collection: open the packs they have earned and keep the cards in a gallery. Works for every club."},
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
    {"key": "season", "label": "Season dashboard",
     "blurb": "Their season in batting, bowling and fielding, with their last few innings."},
    {"key": "fantasy", "label": "Fantasy",
     "blurb": "The next lock deadline, and their fantasy team's rank and points. Needs BetterFantasyCricket."},
    {"key": "fees", "label": "Fees owing",
     "blurb": "What they owe the club this season. Needs BetterAdmin fees and the PIN on."},
    {"key": "fines", "label": "Fines",
     "blurb": "Fines owed and how to pay into the pot. Shows only for squads that turn Fines on."},
]
KEYS = [m["key"] for m in CATALOGUE]

# What every club had before the club could choose: the original page, plus
# fines (which draws nothing unless a squad switches Fines on).
DEFAULT_MODULES = ["cards", "votes", "fantasy", "squad", "selected", "training", "fines"]

# A club without BetterSelect has no squads, selection or nets to show, so its page opens on the
# player's cards and their season instead.
NO_SELECT_DEFAULT_MODULES = ["cards", "season", "votes", "fantasy"]
SELECT_ONLY = ("squad", "selected", "training", "ladder", "fines")
# The availability side of a BetterSelect club's link: the modules that ride on its self-service switch.
# Votes are BetterSelect's, so for a club WITH it they sit here; a club without it keeps them on the
# dashboard side, where its page has always shown them.
AVAILABILITY_SIDE = SELECT_ONLY + ("votes",)


def on_availability_side(club: Organisation, key: str) -> bool:
    return key in AVAILABILITY_SIDE and org_has_module(club, MODULE_SELECT)


def availability_live(club: Organisation) -> bool:
    """The availability side of the link: the answers, votes and the BetterSelect sections (squad,
    selected, training, ladder, fines). It is the club's BetterSelect self-service switch, set in
    BetterSelect > Availability, and a club without BetterSelect never has it."""
    return org_has_module(club, MODULE_SELECT) and bool(club.availability_self_service_enabled)


def dashboard_live(club: Organisation) -> bool:
    """The dashboard side of the link: Player Cards, the season, fantasy and fees. The club's own
    switch (``player_dashboard_enabled``, BetterStats > Player Dashboard) once it has chosen. Until
    then it reads as it always did: a club with BetterSelect follows its self-service switch, and a
    club without it is on unless the page was hidden from its site. So no link changes on deploy."""
    if club.player_dashboard_enabled is not None:
        return bool(club.player_dashboard_enabled)
    if org_has_module(club, MODULE_SELECT):
        return bool(club.availability_self_service_enabled)
    return club.availability_show_on_site is not False


def link_live(club: Organisation) -> bool:
    """Whether the club's player page link opens at all (the answer for `_club_for_token`): either
    side is on. What it then shows is cut down to the sides that are on."""
    return availability_live(club) or dashboard_live(club)


def set_dashboard_live(club: Organisation, on: bool) -> None:
    """Switch the dashboard on or off from BetterStats, for any club. It never touches the BetterSelect
    availability switch. Turning it on mints the link if the club has none yet; turning it off keeps
    the token, so the same link works again when it is switched back on."""
    club.player_dashboard_enabled = bool(on)
    if on and not club.availability_link_token:
        club.availability_link_token = secrets.token_urlsafe(24)


def normalise(keys) -> list[str]:
    """Known keys only, once each, in the order given."""
    out: list[str] = []
    for k in keys or []:
        if isinstance(k, str) and k in KEYS and k not in out:
            out.append(k)
    return out


# A module that draws nothing unless something is due (or the club runs the
# thing it shows). A club's saved list is the modules it chose from the ones it
# was OFFERED, so one that arrived later is switched on for it rather than
# silently missing: a club cannot have turned off what it never saw. Saving the
# list records what was on offer.
AUTO_ON_WHEN_NEW = ("cards", "votes", "fantasy")
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
        return list(DEFAULT_MODULES if org_has_module(club, MODULE_SELECT) else NO_SELECT_DEFAULT_MODULES)
    if isinstance(raw, dict):
        on, known = normalise(raw.get("on")), normalise(raw.get("known")) or list(LEGACY_KNOWN)
    else:
        on, known = normalise(raw), list(LEGACY_KNOWN)
    at = 0
    for key in AUTO_ON_WHEN_NEW:
        if key not in known and key not in on:
            # First, in the order above: a reminder belongs near the top.
            on.insert(at, key)
            at += 1
    return on


def blocked_reason(club: Organisation, key: str) -> Optional[str]:
    """Why a module cannot be shown to this club's players, or None."""
    if key in SELECT_ONLY and not org_has_module(club, MODULE_SELECT):
        return "Needs the BetterSelect module."
    if on_availability_side(club, key):
        if not availability_live(club):
            return "Turn on the availability link in BetterSelect first."
    elif not dashboard_live(club):
        return "Turn the Player Dashboard on in BetterStats settings first."
    if key == "fees":
        if not org_has_module(club, MODULE_FEES):
            return "Needs the BetterAdmin fees module."
        if not club.availability_require_pin:
            return "Turn the PIN on first. With no PIN anyone with the link could open a player's fees."
    if key == "ladder" and not club.availability_show_squad:
        return "Turn Show squad on first."
    if key == "fantasy":
        if not org_has_module(club, MODULE_FANTASY):
            return "Needs the BetterFantasyCricket module."
        if not club.fantasy_link_token:
            return "Create the fantasy link first."
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


def _rate(row: dict, key: str, cover_key: str) -> tuple[Optional[float], bool]:
    """A rate and whether it rests on only some of the innings or spells. The server
    owns the rate (services/rate_coverage.py); a short one is marked, never hidden."""
    val = _num(row.get(key))
    cov = row.get(cover_key) or {}
    return val, bool(val is not None and cov.get("counted") and not cov.get("complete"))


async def _latest_season(db: AsyncSession, club: Organisation, player: Player):
    """``(season row, scope, auto_shown)`` for the player's most recent season under
    the grade scope their public profile uses (so the figures match it). The row is
    None when they have no recorded games."""
    scope, auto_shown = await grade_scope.resolve_scope_for_player(
        db, club.id, str(player.id), None,
        auto_widen=bool(club.stats_auto_show_played_grades),
    )
    rows = await get_season_by_season(db, str(player.id), include_prior=False, scope=scope)
    if not rows:
        return None, scope, auto_shown
    r = rows[0]
    if not (r.get("matches") or r.get("total_runs") or r.get("total_wickets") or r.get("total_catches")):
        return None, scope, auto_shown
    return r, scope, auto_shown


async def season_overview(db: AsyncSession, club: Organisation, player: Player) -> Optional[dict]:
    """The player's most recent season as a small dashboard, under the same grade
    scope their public profile uses (so the figures match it). None when they
    have no recorded games.

    The first block of keys is what the page always had and stays as it was, so
    a page bundle left open across a deploy still renders; the rest feed the
    batting, bowling and fielding panels. A rate missing its balls is marked
    partial (the page puts a dagger on it), never guessed."""
    r, scope, auto_shown = await _latest_season(db, club, player)
    if r is None:
        return None
    strike_rate, sr_partial = _rate(r, "strike_rate", "strike_rate_coverage")
    economy, econ_partial = _rate(r, "economy", "economy_coverage")
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
        "batting": {
            "innings": _num(r.get("batting_innings")) or 0,
            "not_outs": _num(r.get("not_outs")) or 0,
            "strike_rate": strike_rate,
            "strike_rate_partial": sr_partial,
            "fifties": _num(r.get("fifties")) or 0,
            "hundreds": _num(r.get("hundreds")) or 0,
            "ducks": _num(r.get("ducks")) or 0,
            "fours": _num(r.get("total_fours")) or 0,
            "sixes": _num(r.get("total_sixes")) or 0,
        },
        "bowling": {
            "overs": _num(r.get("total_overs")) or 0,
            "maidens": _num(r.get("total_maidens")) or 0,
            "runs_conceded": _num(r.get("bowling_runs_conceded")) or 0,
            "average": _num(r.get("bowling_average")),
            "economy": economy,
            "economy_partial": econ_partial,
            "five_fors": _num(r.get("five_fors")) or 0,
        },
        "fielding": {
            "catches": _num(r.get("total_catches")) or 0,
            "run_outs": _num(r.get("total_run_outs")) or 0,
            "stumpings": _num(r.get("total_stumpings")) or 0,
        },
    }


async def recent_form(db: AsyncSession, club: Organisation, player: Player) -> dict:
    """Their last five innings and last five spells for the club, newest first.
    The same rows the admin profile's snapshot reads (did-not-bat is not an
    innings, a hand-typed game counts, a game for another club does not), across
    every grade, so the page says so. Game ids are left out: nothing links to a
    scorecard from here."""
    bat = await player_form.recent_batting(db, str(player.id), club.id)
    bowl = await player_form.recent_bowling(db, str(player.id), club.id)
    return {
        "batting": [{"runs": b["runs"], "not_out": b["not_out"], "balls": b["balls"], "date": b["date"]} for b in bat],
        "bowling": [{"wickets": w["wickets"], "runs": w["runs"], "overs": w["overs"], "date": w["date"]} for w in bowl],
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
        return {"on_record": False, "payments": []}
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
        "payments": await fees_paid(db, club, member),
    }


PAYMENTS_SHOWN = 30
PAYMENT_KINDS = {"membership": "Membership", "match_day": "Match fees"}


async def fees_paid(db: AsyncSession, club: Organisation, member: FeeMember) -> list[dict]:
    """Every fee payment the club has recorded for this person, newest first, across
    seasons. Date, amount, what it was for, how it was paid and the season: nothing
    from the notes or bank reference columns, which are the treasurer's own. A zero
    row is not a payment. Read through the member's own seasons, so another club's
    or another person's payment cannot appear."""
    rows = (await db.execute(
        select(FeePayment, Season.name)
        .join(FeeMemberSeason, FeeMemberSeason.id == FeePayment.member_season_id)
        .join(Season, Season.id == FeeMemberSeason.season_id)
        .where(FeeMemberSeason.member_id == member.id, FeePayment.organisation_id == club.id, FeePayment.amount > 0)
        .order_by(FeePayment.paid_at.desc().nullslast(), FeePayment.created_at.desc())
        .limit(PAYMENTS_SHOWN)
    )).all()
    return [
        {
            "date": p.paid_at.isoformat() if p.paid_at else None,
            "amount": float(p.amount),
            "kind": PAYMENT_KINDS.get(p.kind, "Fees"),
            "method": p.method or None,
            "season": season_name,
        }
        for p, season_name in rows
    ]


# ── Where they rank in the club this season ──────────────────────────────────
# Runs, wickets and catches, as a position among the club's players for the season
# the dashboard is showing, under the same grade scope as the figures beside it. It
# is read from the club's own leaderboards (the same functions the public boards
# use), so a rank here and the board cannot disagree, and it is derived on read,
# never stored. A leaderboard is a heavy read, so the page asks for this only when
# the Stats section is opened, and a club's three boards are kept for two minutes.
RANK_KINDS = (
    ("runs", "total_runs"),
    ("wickets", "total_wickets"),
    ("catches", "total_catches"),
)
RANK_LIMIT = 2000
RANK_TTL = 120.0
RANK_MAX_KEYS = 40
_RANK_CACHE: dict = {}


async def _season_boards(db: AsyncSession, club: Organisation, season_id: str, scope) -> dict:
    """``{metric: {player_id: value}}`` for the club's season. A board that fails is
    left out, not guessed, and the others still draw."""
    import logging
    import time
    from app.services import aggregations as agg

    key = (str(club.id), season_id, agg._scope_cache_key(scope))
    hit = _RANK_CACHE.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < RANK_TTL:
        return hit[1]
    fetch = {
        "runs": lambda: agg.get_batting_leaderboard_extended(
            db, str(club.id), season_id=season_id, sort_by="total_runs", limit=RANK_LIMIT, scope=scope),
        "wickets": lambda: agg.get_bowling_leaderboard_extended(
            db, str(club.id), season_id=season_id, sort_by="total_wickets", limit=RANK_LIMIT, scope=scope),
        "catches": lambda: agg.get_fielding_leaderboard(
            db, str(club.id), season_id=season_id, sort_by="total_catches", limit=RANK_LIMIT, scope=scope),
    }
    boards: dict = {}
    for metric, field in RANK_KINDS:
        try:
            rows = await fetch[metric]()
        except Exception:  # noqa: BLE001 - one board failing must not take the others down
            logging.getLogger(__name__).exception("player page: %s board failed", metric)
            await session_safety.rollback_keeping(db, club)
            continue
        boards[metric] = {str(r["player_id"]): float(r.get(field) or 0) for r in rows if r.get("player_id") is not None}
    if len(boards) == len(RANK_KINDS):
        if len(_RANK_CACHE) >= RANK_MAX_KEYS:
            _RANK_CACHE.clear()
        _RANK_CACHE[key] = (now, boards)
    return boards


def rank_in(board: dict, player_id: str) -> Optional[dict]:
    """``{rank, of, value}`` for a player on a board, or None when they have nothing
    on it. Ties share the better place (two on 400 are both 2nd, the next is 4th);
    `of` counts the players with something on the board, not the whole roster."""
    mine = board.get(str(player_id)) or 0
    if mine <= 0:
        return None
    ahead = sum(1 for v in board.values() if v > mine)
    return {"rank": ahead + 1, "of": sum(1 for v in board.values() if v > 0), "value": _num(mine)}


async def season_ranks(db: AsyncSession, club: Organisation, player: Player) -> Optional[dict]:
    """The player's club rank for runs, wickets and catches in the season shown on
    their dashboard. None when they have no season; a metric they have nothing on,
    or whose board could not be read, is absent from ``ranks``."""
    r, scope, _auto = await _latest_season(db, club, player)
    if r is None or r.get("season_id") is None:
        return None
    boards = await _season_boards(db, club, str(r["season_id"]), scope)
    ranks = {m: rank_in(b, str(player.id)) for m, b in boards.items()}
    return {"season": r.get("season_name"), "ranks": {m: v for m, v in ranks.items() if v}}
