"""BetterSelect — vote collection: eligibility, voting state and counting.

The Brownlow-style engine behind /votes (admin) and /public/votes (player
link). Everything here is DERIVED ON READ from raw ballots + the club's
current VoteSettings — no stored weekly results, no stored season points — so
changing the ballot shape, counting method or tie policy mid-season restates
the whole season consistently (same philosophy as BetterFees' derived
match-day allocation).

Eligibility is the SYNCED SCORECARD, per direct instruction: a fixture is
votable only once its game has landed in `games` (fixture.id == games.id for
playhq-sourced fixtures), and the votable/voter list is who actually played —
the union of game_appearances + per-innings stat rows, org-scoped through
players.organisation_id (never trust a shared game's rows without that scope,
see the cross-club leak notes in CLAUDE.md).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Fixture, VoteBallot, VoteFixtureOverride, VoteSettings

logger = logging.getLogger(__name__)

DEFAULT_BALLOT = [3, 2, 1]
VOTER_MODES = {"players", "captain"}
COUNTING_METHODS = {"rank", "tally"}
TIE_POLICIES = {"share", "countback"}
MAX_POSITIONS = 10

# Where the votable list comes from. 'scorecard' is the truth of who played but
# only exists after the weekly sync; the other two are available on the night.
ELIGIBILITY_SOURCES = ("scorecard", "lineup", "playhq")
SOURCE_LABELS = {
    "scorecard": "Match scorecard",
    "lineup": "BetterSelect XI",
    "playhq": "Play.Cricket team list",
}


# ─── Config ──────────────────────────────────────────────────────────────────

async def get_settings(db: AsyncSession, org_id) -> Optional[VoteSettings]:
    res = await db.execute(select(VoteSettings).where(VoteSettings.organisation_id == org_id))
    return res.scalar_one_or_none()


def clean_ballot_values(raw) -> list[int]:
    """Sanitise a configured ballot: positive ints, best-first (non-increasing),
    at most MAX_POSITIONS. Falls back to 3-2-1 when nothing usable remains."""
    vals: list[int] = []
    for v in (raw or []):
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n > 0:
            vals.append(n)
    vals = sorted(vals, reverse=True)[:MAX_POSITIONS]
    return vals or list(DEFAULT_BALLOT)


def effective_config(s: Optional[VoteSettings]) -> dict:
    """The club's voting config with defaults applied — usable whether or not a
    vote_settings row exists yet."""
    return {
        "enabled": bool(s.enabled) if s else False,
        "require_pin": bool(s.require_pin) if s else True,
        "voter_mode": (s.voter_mode if s and s.voter_mode in VOTER_MODES else "players"),
        "ballot_values": clean_ballot_values(s.ballot_values if s else None),
        "counting_method": (s.counting_method if s and s.counting_method in COUNTING_METHODS else "rank"),
        "tie_policy": (s.tie_policy if s and s.tie_policy in TIE_POLICIES else "share"),
        "allow_self_vote": bool(s.allow_self_vote) if s else False,
        "allow_non_participants": bool(s.allow_non_participants) if s else False,
        "auto_close_days": int(s.auto_close_days) if s and s.auto_close_days else 7,
        "eligibility_source": (
            s.eligibility_source
            if s and getattr(s, "eligibility_source", None) in ELIGIBILITY_SOURCES
            else "scorecard"
        ),
    }


# ─── Eligibility (who played) ────────────────────────────────────────────────

async def game_exists(db: AsyncSession, fixture_id) -> bool:
    """Has the fixture's game synced? playhq fixtures share their id with the
    eventual games row, so this is a straight PK probe."""
    res = await db.execute(text("SELECT 1 FROM games WHERE id = :gid LIMIT 1"), {"gid": fixture_id})
    return res.first() is not None


async def eligible_players(db: AsyncSession, org_id, game_id) -> list[dict]:
    """Who played in this game, from the synced scorecard: the union of
    appearances and every per-innings stat table, so a game whose sync predates
    game_appearances still resolves. Org-scoped through players so a shared
    game (both clubs synced) never leaks the opposition into our list."""
    res = await db.execute(
        text(
            """
            SELECT p.id, COALESCE(p.display_name_override, p.name) AS name,
                   BOOL_OR(src.is_captain) AS is_captain
            FROM (
                SELECT player_id, is_captain FROM game_appearances WHERE game_id = :gid
                UNION ALL SELECT player_id, false FROM batting_innings WHERE game_id = :gid
                UNION ALL SELECT player_id, false FROM bowling_spells WHERE game_id = :gid
                UNION ALL SELECT player_id, false FROM fielding_stats WHERE game_id = :gid
            ) src
            JOIN players p ON p.id = src.player_id
            WHERE p.organisation_id = :org
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ORDER BY 2
            """
        ),
        {"gid": game_id, "org": org_id},
    )
    players = [
        {"id": str(pid), "name": name, "is_captain": bool(cap)}
        for pid, name, cap in res.fetchall()
    ]
    if players and not any(p["is_captain"] for p in players):
        # Older synced games may lack the captain flag — fall back to the saved
        # BetterSelect lineup's captain for captain-only voting.
        lu = await db.execute(
            text(
                "SELECT player_id FROM fixture_lineups "
                "WHERE fixture_id = :fid AND is_captain = true"
            ),
            {"fid": game_id},
        )
        captain_ids = {str(r[0]) for r in lu.fetchall()}
        for p in players:
            if p["id"] in captain_ids:
                p["is_captain"] = True
    return players


async def lineup_players(db: AsyncSession, org_id, fixture_id) -> list[dict]:
    """The XI saved in BetterSelect selection for this fixture, in batting
    order. Org-scoped through players like every other votable list."""
    res = await db.execute(
        text(
            """
            SELECT p.id, COALESCE(p.display_name_override, p.name) AS name, fl.is_captain
            FROM fixture_lineups fl
            JOIN players p ON p.id = fl.player_id
            WHERE fl.fixture_id = :fid AND p.organisation_id = :org
            ORDER BY fl.batting_order NULLS LAST, 2
            """
        ),
        {"fid": fixture_id, "org": org_id},
    )
    return [
        {"id": str(pid), "name": name, "is_captain": bool(cap)}
        for pid, name, cap in res.fetchall()
    ]


async def eligible_from_source(db: AsyncSession, club, fixture, source: str) -> tuple[list[dict], list[str]]:
    """``(players, unmatched)`` for one source.

    ``unmatched`` only ever comes from the Play.Cricket team list — a published
    name we hold no player row for (a genuine fill-in, or a junior whose name CA
    redacts). It's surfaced rather than silently dropped so an admin can see why
    the votable list is short. Votes still can't be cast for them: a ballot pick
    is a real player FK.
    """
    if source == "lineup":
        return await lineup_players(db, club.id, fixture.id), []
    if source == "playhq":
        from app.services.lineups import our_lineup_players
        try:
            return await our_lineup_players(db, club, str(fixture.id))
        except Exception:
            # A live upstream fetch must never take the vote page down.
            logger.warning("vote eligibility: Play.Cricket lineup fetch failed for %s", fixture.id)
            return [], []
    if await game_exists(db, fixture.id):
        return await eligible_players(db, club.id, fixture.id), []
    return [], []


def effective_source(cfg: dict, override: Optional[str]) -> str:
    """The fixture's own source override, else the club default."""
    if override in ELIGIBILITY_SOURCES:
        return override
    return cfg.get("eligibility_source") or "scorecard"


async def resolve_eligibility(
    db: AsyncSession, club, fixture, cfg: dict, override: Optional[str] = None,
    *, check_all: bool = False,
) -> dict:
    """Who can be voted for, and where that list came from.

    Uses the fixture's chosen source. When that source has nothing yet (no XI
    saved, team list not published, scorecard not synced) it falls back to the
    first other source that does, rather than leaving a club unable to vote —
    and says so via ``used``/``fell_back`` so the admin page can show which list
    is actually in play.

    ``check_all=True`` also counts the sources not in use, so the admin can see
    what switching would give them. It costs a live upstream call, so the public
    ballot page leaves it off.
    """
    requested = effective_source(cfg, override)
    order = [requested] + [s for s in ELIGIBILITY_SOURCES if s != requested]

    players: list[dict] = []
    unmatched: list[str] = []
    used: Optional[str] = None
    counts: dict[str, Optional[int]] = {}

    for src in order:
        # Without check_all we stop at the first source that yields a list, so
        # a fallback source (and its live Play.Cricket fetch) is only ever paid
        # for when the chosen one is genuinely empty.
        if players and not check_all:
            break
        found, unres = await eligible_from_source(db, club, fixture, src)
        counts[src] = len(found)
        if found and used is None:
            players, unmatched, used = found, unres, src

    return {
        "requested": requested,
        "used": used,
        "fell_back": bool(used and used != requested),
        "players": players,
        "unmatched": unmatched,
        "counts": counts,
        "labels": SOURCE_LABELS,
    }


# ─── Voting state ────────────────────────────────────────────────────────────

def fixture_close_date(fixture: Fixture, cfg: dict) -> Optional[date]:
    """Last day votes are accepted (inclusive): match end + auto_close_days."""
    end = fixture.end_on or fixture.played_on
    if not end:
        return None
    return end + timedelta(days=int(cfg["auto_close_days"]))


def fixture_vote_state(fixture: Fixture, cfg: dict, override: Optional[str], ready: bool,
                       today: Optional[date] = None) -> str:
    """One of: 'upcoming' (not played yet), 'awaiting_team' (played, but no
    votable list from the club's chosen source yet — an unsynced scorecard, an
    unsaved XI, an unpublished team list), 'open', 'closed' (auto-close passed),
    'locked' (admin lock). A manual lock/reopen always wins over the auto
    window."""
    today = today or date.today()
    start = fixture.played_on
    if start and start > today:
        return "upcoming"
    if not ready:
        return "awaiting_team"
    if override == "locked":
        return "locked"
    if override == "reopened":
        return "open"
    close = fixture_close_date(fixture, cfg)
    if close and today > close:
        return "closed"
    return "open"


async def get_override(db: AsyncSession, fixture_id) -> Optional[VoteFixtureOverride]:
    """The fixture's override row (lock/reopen status and/or an eligibility
    source), or None. Callers read ``.status`` / ``.eligibility_source``."""
    res = await db.execute(
        select(VoteFixtureOverride).where(VoteFixtureOverride.fixture_id == fixture_id)
    )
    return res.scalar_one_or_none()


# ─── Counting ────────────────────────────────────────────────────────────────

def tally_ballots(ballots: list[VoteBallot], values: list[int]) -> dict[str, dict]:
    """Raw weekly totals per votable player.

    Returns {player_id: {"raw": int, "counts": [n at values[0], n at values[1], …]}}.
    A pick's value comes from its POSITION against the current config; picks at
    positions beyond the configured ballot (config shrank after votes came in)
    score nothing.
    """
    totals: dict[str, dict] = {}
    for b in ballots:
        for pick in b.picks:
            idx = (pick.position or 0) - 1
            if idx < 0 or idx >= len(values):
                continue
            pid = str(pick.player_id)
            t = totals.setdefault(pid, {"raw": 0, "counts": [0] * len(values)})
            t["raw"] += values[idx]
            t["counts"][idx] += 1
    return totals


def award_weekly_points(totals: dict[str, dict], cfg: dict) -> dict[str, int]:
    """Turn a fixture's raw totals into season points under the club's config.

    'tally'  — season points ARE the raw vote total (10 voters all giving a
               player their 3 = 30 points).
    'rank'   — Brownlow conversion: the week's top vote-getter earns
               ballot_values[0], second earns ballot_values[1], and so on.
               Ties under 'share' all take the value of the best position they
               tie for (standard competition ranking — the next value(s) are
               consumed). Under 'countback' a tie is broken by who received
               more of the highest ballot value, then the next value, etc.;
               only a dead heat after every countback still shares.
    """
    values = cfg["ballot_values"]
    if cfg["counting_method"] == "tally":
        return {pid: t["raw"] for pid, t in totals.items() if t["raw"] > 0}

    contenders = [(pid, t) for pid, t in totals.items() if t["raw"] > 0]
    if cfg["tie_policy"] == "countback":
        def key(item):
            return (item[1]["raw"], *item[1]["counts"])
    else:
        def key(item):
            return (item[1]["raw"],)

    contenders.sort(key=key, reverse=True)
    awarded: dict[str, int] = {}
    consumed = 0
    i = 0
    while i < len(contenders) and consumed < len(values):
        group = [contenders[i]]
        while i + len(group) < len(contenders) and key(contenders[i + len(group)]) == key(contenders[i]):
            group.append(contenders[i + len(group)])
        value = values[consumed]
        for pid, _t in group:
            awarded[pid] = value
        consumed += len(group)
        i += len(group)
    return awarded


# ─── Season / rounds ─────────────────────────────────────────────────────────

def season_year_for(d: Optional[date]) -> Optional[int]:
    """AU season year: Jul→Jun. October 2025 and February 2026 are both season
    2025 ("Summer 2025/26")."""
    if not d:
        return None
    return d.year if d.month >= 7 else d.year - 1


def season_window(year: int) -> tuple[date, date]:
    return date(year, 7, 1), date(year + 1, 6, 30)


def round_key_for(fixture: Fixture) -> str:
    r = (fixture.round or "").strip()
    if r:
        return r.lower()
    if fixture.played_on:
        return fixture.played_on.isoformat()
    return "unscheduled"


def round_label_for(fixture: Fixture) -> str:
    r = (fixture.round or "").strip()
    if r:
        # Fixture rounds sync as bare numbers or "Round N" — display uniformly.
        return r if not r.isdigit() else f"Round {r}"
    if fixture.played_on:
        return fixture.played_on.strftime("%d %b %Y")
    return "Unscheduled"


async def load_ballots_by_fixture(db: AsyncSession, org_id, fixture_ids: list) -> dict:
    """All ballots (picks eager-loaded) for a set of fixtures, grouped by
    fixture id (string keys)."""
    if not fixture_ids:
        return {}
    res = await db.execute(
        select(VoteBallot).where(
            VoteBallot.organisation_id == org_id,
            VoteBallot.fixture_id.in_(fixture_ids),
        )
    )
    grouped: dict[str, list[VoteBallot]] = {}
    for b in res.scalars().all():
        grouped.setdefault(str(b.fixture_id), []).append(b)
    return grouped


async def player_names(db: AsyncSession, org_id, player_ids: set[str]) -> dict[str, str]:
    if not player_ids:
        return {}
    ids = [uuid.UUID(p) for p in player_ids]
    res = await db.execute(
        text(
            "SELECT id, COALESCE(display_name_override, name) FROM players "
            "WHERE organisation_id = :org AND id = ANY(:ids)"
        ),
        {"org": org_id, "ids": ids},
    )
    return {str(pid): name for pid, name in res.fetchall()}


async def build_leaderboard(
    db: AsyncSession,
    org_id,
    cfg: dict,
    year: int,
    grade_id: Optional[str] = None,
    through_round: Optional[str] = None,
) -> dict:
    """The Brownlow board: every round (a distinct fixture.round label, or the
    match date when no round is set) in chronological order, each fixture's
    weekly result, and cumulative standings THROUGH a chosen round — so in week
    8 you can replay what the count looked like after week 3.

    grade_id filters both the rounds' fixtures and the standings to one grade;
    without it the board is club-wide across every grade.
    """
    start, end = season_window(year)
    q = (
        select(Fixture)
        .where(
            Fixture.organisation_id == org_id,
            Fixture.played_on.is_not(None),
            Fixture.played_on >= start,
            Fixture.played_on <= end,
        )
        .order_by(Fixture.played_on.asc())
    )
    if grade_id:
        q = q.where(Fixture.grade_id == uuid.UUID(str(grade_id)))
    fixtures = (await db.execute(q)).scalars().all()

    ballots_by_fx = await load_ballots_by_fixture(db, org_id, [f.id for f in fixtures])
    # Only fixtures that actually collected votes appear on the board.
    voted = [f for f in fixtures if ballots_by_fx.get(str(f.id))]

    # Grade names for the fixture chips.
    grade_ids = {f.grade_id for f in voted if f.grade_id}
    grade_names: dict[str, str] = {}
    if grade_ids:
        res = await db.execute(
            text("SELECT id, name FROM grades WHERE id = ANY(:ids)"),
            {"ids": list(grade_ids)},
        )
        grade_names = {str(gid): name for gid, name in res.fetchall()}

    # Group into rounds, ordered by each round's earliest date.
    rounds: list[dict] = []
    by_key: dict[str, dict] = {}
    for f in voted:
        key = round_key_for(f)
        rd = by_key.get(key)
        if not rd:
            rd = {"key": key, "label": round_label_for(f), "date": f.played_on, "fixtures": []}
            by_key[key] = rd
            rounds.append(rd)
        rd["date"] = min(rd["date"], f.played_on)
        rd["fixtures"].append(f)
    rounds.sort(key=lambda r: (r["date"], r["key"]))

    values = cfg["ballot_values"]
    cumulative: dict[str, dict] = {}
    all_pids: set[str] = set()
    out_rounds: list[dict] = []
    cutoff_hit = False
    for rd in rounds:
        fixtures_out = []
        for f in rd["fixtures"]:
            totals = tally_ballots(ballots_by_fx.get(str(f.id), []), values)
            awarded = award_weekly_points(totals, cfg)
            results = []
            for pid, t in totals.items():
                results.append({
                    "player_id": pid,
                    "raw": t["raw"],
                    "counts": t["counts"],
                    "points": awarded.get(pid, 0),
                })
                all_pids.add(pid)
            results.sort(key=lambda r: (-r["points"], -r["raw"]))
            fixtures_out.append({
                "id": str(f.id),
                "opponent": f.opponent_name or f.label,
                "grade_id": str(f.grade_id) if f.grade_id else None,
                "grade": grade_names.get(str(f.grade_id)) if f.grade_id else None,
                "date": f.played_on.isoformat() if f.played_on else None,
                "ballots": len(ballots_by_fx.get(str(f.id), [])),
                "results": results,
            })
            if not cutoff_hit:
                for r in results:
                    c = cumulative.setdefault(r["player_id"], {
                        "points": 0, "raw": 0, "counts": [0] * len(values), "rounds": 0,
                    })
                    c["points"] += r["points"]
                    c["raw"] += r["raw"]
                    for i2, n in enumerate(r["counts"]):
                        if i2 < len(c["counts"]):
                            c["counts"][i2] += n
                    if r["points"] > 0 or r["raw"] > 0:
                        c["rounds"] += 1
        out_rounds.append({
            "key": rd["key"],
            "label": rd["label"],
            "date": rd["date"].isoformat(),
            "fixtures": fixtures_out,
            "counted": not cutoff_hit,
        })
        if through_round is not None and rd["key"] == through_round:
            cutoff_hit = True

    names = await player_names(db, org_id, all_pids)
    standings = [
        {
            "player_id": pid,
            "name": names.get(pid, "Unknown"),
            "points": c["points"],
            "raw": c["raw"],
            "counts": c["counts"],
            "rounds": c["rounds"],
        }
        for pid, c in cumulative.items()
    ]
    standings.sort(key=lambda s: (-s["points"], -s["raw"], s["name"]))

    return {
        "year": year,
        "ballot_values": values,
        "counting_method": cfg["counting_method"],
        "tie_policy": cfg["tie_policy"],
        "rounds": out_rounds,
        "standings": standings,
        "through_round": through_round if cutoff_hit else None,
    }
