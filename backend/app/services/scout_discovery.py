"""BetterScout — player discovery.

Reuses BetterIQ's "scout any club" engine (services.iq_scout) wholesale for
the actual Cricket Australia data-fetching — that module's whole reason to
exist is scouting a club we've never played, using nothing but its public
Grassroots org GUID, which is exactly BetterScout's situation for every club.
The only thing it doesn't give us is somewhere to cache into: its own
caching (iq_opponent's opposition_dossiers table) has a NOT NULL FK to
organisations, which is precisely the club-data relationship BetterScout
must never have. So this module borrows the fetch logic and gives it a new,
platform-wide cache (scout_club_cache — see models/scout.py), then layers
two more concepts BetterIQ has no equivalent of: a durable per-person record
that survives past one search (ScoutedPlayer) and a per-tenant "this Scout
Org has added this player" fact (ScoutTrackedPlayer).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Player, async_session_maker
from app.models.scout import (
    ScoutClubCache, ScoutMilestoneSeen, ScoutPlayerNote, ScoutPlayerSearchView,
    ScoutWatchlist, ScoutWatchlistCard, ScoutedPlayer, ScoutedPlayerClub,
)
from app.services import iq_scout, scout_feed, scout_internal_link, scout_live_search, scout_watchlist
from app.services.iq_opponent import BUILD_STALE_AFTER, TTL, _BUILD_TASKS  # noqa: F401 — shared build-task bookkeeping

logger = logging.getLogger(__name__)

# Tracks the fire-and-forget "does this player play anywhere else?" scans
# (services._run_other_club_scan) the same way _BUILD_TASKS tracks roster
# builds — a bare asyncio.create_task with nothing holding a reference can be
# garbage-collected mid-flight, so this set (with add_done_callback(discard))
# is what keeps it alive until it actually finishes.
_MATCH_TASKS: set[asyncio.Task] = set()

# This module's OWN roster-payload contract version — independent of
# iq_scout.CAREER_VERSION and scout_internal_link.INTERNAL_SCHEMA_VERSION.
# Two different builders (iq_scout._build_career's public-API path,
# scout_internal_link.build_internal_career's internal path) can produce this
# payload; freshness has to track the SHAPE this module's own consumers read
# (Discover/Profile/Overview), not either builder's own version number.
# _run_club_build stamps every payload with this value before storing it.
# Bump whenever either builder's output shape changes in a way that matters
# here. Bumped 1 → 2 when the fetch window itself changed (see
# SCOUT_CAREER_YEARS below) — a stale schema_v==1 cache holds a 10-year
# payload built before the 5-year recruiting-search cap existed, and must be
# rebuilt rather than served as fresh.
ROSTER_SCHEMA_VERSION = 2

# BetterScout's own recruiting-search window — deliberately narrower than
# BetterIQ's iq_scout.CAREER_YEARS (10). A recruiter searching a club wants
# who's playing NOW, not a decade of history that surfaces long-retired
# names and slows every build; passed explicitly to both builders below so
# BetterIQ's own callers (which pass no `years` arg) are untouched.
SCOUT_CAREER_YEARS = 5


# ─── club roster cache (platform-wide, no org scoping) ───────────────────────

async def _load_club_row(session: AsyncSession, org_guid: str) -> ScoutClubCache | None:
    res = await session.execute(
        select(ScoutClubCache).where(ScoutClubCache.club_org_guid == org_guid.lower())
    )
    return res.scalar_one_or_none()


async def _upsert_club_row(session: AsyncSession, org_guid: str, **fields) -> None:
    row = await _load_club_row(session, org_guid)
    if row is None:
        row = ScoutClubCache(club_org_guid=org_guid.lower())
        session.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()


async def _run_club_build(org_guid: str, club_name: str | None) -> None:
    async with async_session_maker() as session:
        try:
            # If this club is already onboarded on BetterCricket, our own
            # per-game tables are richer than the public aggregate API (exact
            # figures, real grade-per-season, dateable matches) and free to
            # read — see services/scout_internal_link.py. Falls through to
            # the existing public-API build for every other club.
            internal_org = await scout_internal_link.resolve_internal_org(session, org_guid)
            if internal_org:
                payload = await scout_internal_link.build_internal_career(internal_org, session, years=SCOUT_CAREER_YEARS)
            else:
                payload = await iq_scout._build_career(org_guid, club_name, years=SCOUT_CAREER_YEARS)
            payload["schema_v"] = ROSTER_SCHEMA_VERSION
            await _upsert_club_row(
                session, org_guid,
                club_name=(payload.get("org") or {}).get("name") or club_name,
                status="ready", payload=payload,
                built_at=datetime.now(timezone.utc), error=None,
            )
            logger.info(
                f"BetterScout: club roster built for {org_guid} "
                f"(source={payload.get('source', 'external')})"
            )
        except Exception as e:  # never leave the row wedged at 'building'
            logger.exception(f"BetterScout: club roster build failed for {org_guid}: {e}")
            try:
                await _upsert_club_row(session, org_guid, status="error", error=str(e)[:500])
            except Exception:
                pass


async def refresh_club_and_apply(org_guid: str, club_name: str | None, scouted_player_ids: list[str]) -> int:
    """The scheduled-refresh job's one entry point (jobs/scheduler.py's
    refresh_scout_players): rebuild a club ONCE, then stamp every one of the
    given ScoutedPlayer rows from that single build. Deliberately NOT N
    calls to refresh_player() — that function's own force=True kicks off a
    fresh background rebuild every time it's called, so ten tracked players
    (across however many orgs) at one club would otherwise trigger ten
    redundant rebuilds hitting the same rate-limited CA proxy. This awaits
    _run_club_build directly (a plain async function, not the fire-and-poll
    task _run_club_build's own caller normally launches) since a scheduled
    job can afford to wait, unlike a live HTTP request."""
    await _run_club_build(org_guid, club_name)
    async with async_session_maker() as session:
        row = await _load_club_row(session, org_guid)
        if not row or row.status != "ready":
            return 0
        n = 0
        for pid in scouted_player_ids:
            club_row = (await session.execute(
                select(ScoutedPlayerClub).where(
                    ScoutedPlayerClub.scouted_player_id == pid,
                    ScoutedPlayerClub.club_org_guid == org_guid.lower(),
                )
            )).scalar_one_or_none()
            if not club_row or not club_row.grassroots_participant_id:
                continue
            sliced = _slice_player(row.payload or {}, club_row.grassroots_participant_id)
            if not sliced:
                continue
            club_row.stats_payload = sliced
            club_row.stats_built_at = datetime.now(timezone.utc)
            if club_row.is_primary:
                player = await session.get(ScoutedPlayer, pid)
                if player:
                    player.club_org_guid = org_guid.lower()
                    player.club_name = club_row.club_name
                    player.stats_payload = sliced
                    player.stats_built_at = club_row.stats_built_at
                    _stamp_internal_link(player, sliced, org_guid)
            n += 1
        if n:
            await session.commit()
        return n


async def get_or_start_club_roster(
    session: AsyncSession, org_guid: str, *, club_name: str | None = None, force: bool = False,
) -> dict:
    """Same build/poll contract as BetterIQ's get_or_start_dossier: a fresh
    ready cache returns the roster; otherwise mark building, launch the
    detached task, and report {status: 'building'} for the frontend to poll."""
    row = await _load_club_row(session, org_guid)
    now = datetime.now(timezone.utc)
    fresh = (
        row and row.status == "ready" and row.built_at and (now - row.built_at) < TTL
        and (row.payload or {}).get("schema_v") == ROSTER_SCHEMA_VERSION
    )
    if fresh and not force:
        return {"status": "ready", "cached": True, **(row.payload or {})}
    building = row and row.status == "building" and row.updated_at and (now - row.updated_at) < BUILD_STALE_AFTER
    if building and not force:
        return {"status": "building"}
    await _upsert_club_row(session, org_guid, club_name=club_name, status="building", error=None)
    task = asyncio.create_task(_run_club_build(org_guid, club_name))
    _BUILD_TASKS.add(task)
    task.add_done_callback(_BUILD_TASKS.discard)
    return {"status": "building"}


# ─── scouted players (durable, platform-wide) ─────────────────────────────────

def _slice_player(roster_payload: dict, player_id: str) -> dict | None:
    pid = (player_id or "").lower()
    return next(
        (p for p in roster_payload.get("players") or [] if (p.get("player_id") or "").lower() == pid),
        None,
    )


async def annotate_tracking(session: AsyncSession, scout_org_id: str, roster: dict) -> dict:
    """Overlays this ORG's own tracking state onto a roster payload — never
    baked into the cache itself (ScoutClubCache is platform-wide, shared by
    every Scout Org, so which players THIS org has already added is private
    per-request state, not part of the cached build). Adds `tracked` and
    `watchlist_count` to every player row that resolves to an existing
    ScoutedPlayer; untouched players get `watchlist_count: 0`."""
    if roster.get("status") != "ready" or not roster.get("players"):
        return roster
    ext_ids = [p["player_id"] for p in roster["players"] if p.get("player_id")]
    if not ext_ids:
        return roster
    rows = (await session.execute(
        select(ScoutedPlayer.id, ScoutedPlayer.grassroots_participant_id)
        .where(ScoutedPlayer.grassroots_participant_id.in_(ext_ids))
    )).all()
    scouted_id_by_ext = {ext: str(sid) for sid, ext in rows}
    count_by_sid: dict[str, int] = {}
    if scouted_id_by_ext:
        counts = (await session.execute(
            select(ScoutWatchlistCard.scouted_player_id, func.count())
            .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
            .where(
                ScoutWatchlist.scout_org_id == scout_org_id,
                ScoutWatchlistCard.scouted_player_id.in_(scouted_id_by_ext.values()),
            )
            .group_by(ScoutWatchlistCard.scouted_player_id)
        )).all()
        count_by_sid = {str(sid): n for sid, n in counts}
    for p in roster["players"]:
        sid = scouted_id_by_ext.get(p.get("player_id"))
        p["scouted_player_id"] = sid
        p["watchlist_count"] = count_by_sid.get(sid, 0) if sid else 0
    return roster


def _stamp_internal_link(player: ScoutedPlayer, sliced: dict, org_guid: str) -> None:
    """Record which real BetterCricket org/player this scouted player
    resolved to, when the roster that sliced them was built via
    scout_internal_link (see that module's docstring on why these two
    columns carry no ForeignKey). Cleared back to None when a later refresh
    no longer resolves internally (e.g. the club was archived) — a stale
    link is worse than none, since the next refresh would silently trust it."""
    internal_pid = sliced.get("internal_player_id")
    player.internal_org_id = org_guid if internal_pid else None
    player.internal_player_id = internal_pid


def _parse_best(best: str | None) -> tuple[int, int] | None:
    if not best or "/" not in best:
        return None
    try:
        w, r = best.split("/", 1)
        return int(w), int(r)
    except ValueError:
        return None


def _combine_season_totals(seasons: list[dict]) -> dict:
    """The backend twin of frontend/src/scout/lib/seasonRollup.js's
    rollupSeasons — same rule (plain counts sum, rate stats are re-derived
    from the summed raw counts, never averaged from per-season rates).
    Used to combine season rows across MULTIPLE CLUBS into one career total
    (player_out's `stats.totals`), where the frontend's own rollup only ever
    combines seasons within a single already-fetched club payload."""
    if not seasons:
        return {
            "matches": 0, "innings": 0, "runs": 0, "not_outs": 0, "balls_faced": 0,
            "average": None, "strike_rate": None, "high_score": None,
            "fifties": 0, "hundreds": 0, "ducks": 0,
            "wickets": 0, "bowling_balls": 0, "runs_conceded": 0, "maidens": 0, "five_fors": 0,
            "bowling_average": None, "economy": None, "best": None,
            "catches": 0, "catches_wk": 0, "stumpings": 0, "run_outs": 0,
        }

    def s(key: str) -> int:
        return sum((season.get(key) or 0) for season in seasons)

    matches, innings, runs, not_outs, balls_faced = s("matches"), s("innings"), s("runs"), s("not_outs"), s("balls_faced")
    wickets, bowling_balls, runs_conceded = s("wickets"), s("bowling_balls"), s("runs_conceded")
    outs = max(innings - not_outs, 0)

    best = None
    for season in seasons:
        bp = _parse_best(season.get("best"))
        if bp and (best is None or bp[0] > best[0] or (bp[0] == best[0] and bp[1] < best[1])):
            best = bp

    high_score = None  # (value, not_out)
    for season in seasons:
        hs = season.get("high_score")
        if hs is None:
            continue
        not_out = str(hs).endswith("*")
        try:
            value = int(str(hs).rstrip("*"))
        except ValueError:
            continue
        if high_score is None or value > high_score[0]:
            high_score = (value, not_out)

    return {
        "matches": matches, "innings": innings, "runs": runs, "not_outs": not_outs, "balls_faced": balls_faced,
        "average": round(runs / outs, 2) if outs else None,
        "strike_rate": round(100 * runs / balls_faced, 2) if balls_faced else None,
        "high_score": (f"{high_score[0]}{'*' if high_score[1] else ''}" if high_score else None),
        "fifties": s("fifties"), "hundreds": s("hundreds"), "ducks": s("ducks"),
        "wickets": wickets, "bowling_balls": bowling_balls, "runs_conceded": runs_conceded,
        "maidens": s("maidens"), "five_fors": s("five_fors"),
        "bowling_average": round(runs_conceded / wickets, 2) if wickets else None,
        "economy": round(runs_conceded / (bowling_balls / 6), 2) if bowling_balls else None,
        "best": f"{best[0]}/{best[1]}" if best else None,
        "catches": s("catches"), "catches_wk": s("catches_wk"),
        "stumpings": s("stumpings"), "run_outs": s("run_outs"),
    }


async def _upsert_player_club(
    session: AsyncSession, scouted_player_id: str, org_guid: str, club_name: str | None, sliced: dict, *,
    participant_id: str | None, is_primary: bool, linked_via: str,
) -> ScoutedPlayerClub:
    """Upsert one club stint for a player, keyed on (scouted_player_id,
    club_org_guid). When is_primary is set, demotes any other existing
    primary row for the same player first — uq_scouted_player_clubs_primary
    only allows one at a time, and doing the demotion here (rather than
    relying on the caller) is what keeps every call site honest."""
    org_guid = org_guid.lower()
    row = (await session.execute(
        select(ScoutedPlayerClub).where(
            ScoutedPlayerClub.scouted_player_id == scouted_player_id,
            ScoutedPlayerClub.club_org_guid == org_guid,
        )
    )).scalar_one_or_none()
    if is_primary:
        others = (await session.execute(
            select(ScoutedPlayerClub).where(
                ScoutedPlayerClub.scouted_player_id == scouted_player_id,
                ScoutedPlayerClub.club_org_guid != org_guid,
                ScoutedPlayerClub.is_primary.is_(True),
            )
        )).scalars().all()
        for o in others:
            o.is_primary = False
    if row is None:
        row = ScoutedPlayerClub(scouted_player_id=scouted_player_id, club_org_guid=org_guid, linked_via=linked_via)
        session.add(row)
    row.club_name = club_name or row.club_name
    row.grassroots_participant_id = participant_id
    row.stats_payload = sliced
    row.stats_built_at = datetime.now(timezone.utc)
    row.is_primary = is_primary
    await session.flush()
    return row


async def add_player(
    session: AsyncSession, scout_org_id: str, org_guid: str, player_id: str, club_name: str | None = None,
    watchlist_id: str | None = None,
) -> dict:
    """Adds a real AU player found via club search. Requires the club roster
    cache to already be ready (the frontend only offers "Add" once a roster
    has loaded, so this is a real precondition, not a race to paper over).

    Adding the SAME participant GUID from a second club used to silently
    overwrite the first club's stats (ScoutedPlayer only ever held one
    club) — fixed here: a second club for an already-known player becomes a
    second, non-primary ScoutedPlayerClub row (see _upsert_player_club)
    rather than replacing the first. Only the FIRST club a player is ever
    added from fires the "find them at other clubs" background scan — a
    player already linked to N clubs doesn't need it re-triggered on every
    subsequent add."""
    club_row = await _load_club_row(session, org_guid)
    if not club_row or club_row.status != "ready":
        raise ValueError("Club roster isn't ready yet — fetch the roster before adding a player.")
    sliced = _slice_player(club_row.payload or {}, player_id)
    if not sliced:
        raise ValueError("That player wasn't found in this club's roster.")
    resolved_club_name = club_name or (club_row.payload or {}).get("org", {}).get("name")

    res = await session.execute(
        select(ScoutedPlayer).where(ScoutedPlayer.grassroots_participant_id == player_id)
    )
    player = res.scalar_one_or_none()
    is_new_player = player is None
    if player is None:
        player = ScoutedPlayer(
            source="au_grassroots",
            grassroots_participant_id=player_id,
            name=sliced.get("name") or "Unknown",
        )
        session.add(player)
        await session.flush()

    existing_clubs = (await session.execute(
        select(func.count()).select_from(ScoutedPlayerClub).where(ScoutedPlayerClub.scouted_player_id == player.id)
    )).scalar_one()
    is_primary = existing_clubs == 0
    club_row_obj = await _upsert_player_club(
        session, player.id, org_guid, resolved_club_name, sliced,
        participant_id=player_id, is_primary=is_primary, linked_via="add",
    )
    if is_primary:
        player.club_org_guid = org_guid.lower()
        player.club_name = resolved_club_name
        player.stats_payload = sliced
        player.stats_built_at = club_row_obj.stats_built_at
        _stamp_internal_link(player, sliced, org_guid)
    await session.flush()

    await scout_watchlist.ensure_card_on_watchlist(session, scout_org_id, player.id, watchlist_id)
    await session.commit()

    if is_new_player:
        task = asyncio.create_task(_run_other_club_scan(str(player.id)))
        _MATCH_TASKS.add(task)
        task.add_done_callback(_MATCH_TASKS.discard)

    return await player_out(session, player)


async def add_player_from_search(
    session: AsyncSession, scout_org_id: str, org_guid: str, player_name: str,
    club_name: str | None = None, canonical_participant_id: str | None = None,
    watchlist_id: str | None = None,
) -> dict:
    """The global search bar's own "add and track" action for an UNTRACKED
    result. The identity there comes from the national playCommunity search
    (services.scout_live_search), which knows a name and a club but not that
    club's own locally-scoped roster id — unlike add_player, which is only
    ever called from Discover with a player_id already sliced out of an
    already-fetched club roster.

    Resolves the same way link_player_club's auto-resolve does: build the
    named club's roster (reporting {"status": "building"} for the caller to
    poll, same contract as everywhere else in this module), try an exact
    match on canonical_participant_id, then fall back to a name match scoped
    to that one club. Once resolved, delegates to add_player itself — so a
    clicked search result and a click on Discover's own roster end up
    creating byte-for-byte the same kind of row, not a second code path."""
    roster = await get_or_start_club_roster(session, org_guid, club_name=club_name)
    if roster.get("status") != "ready":
        return {"status": roster.get("status")}
    club_row = await _load_club_row(session, org_guid)
    resolved_club_name = club_name or ((club_row.payload or {}).get("org", {}).get("name") if club_row else None)

    player_id = None
    sliced = _slice_player(club_row.payload or {}, canonical_participant_id) if canonical_participant_id else None
    if sliced:
        player_id = canonical_participant_id
    else:
        matches = await scout_feed.find_name_matches(session, player_name, only_club_guid=org_guid, threshold=0.85)
        if matches:
            player_id = matches[0]["player_id"]
    if not player_id:
        raise ValueError("Could not find this player in that club's current roster.")

    return {
        "status": "ready",
        **(await add_player(session, scout_org_id, org_guid, player_id, resolved_club_name, watchlist_id)),
    }


async def add_manual_player(
    session: AsyncSession, scout_org_id: str, name: str, club_name: str | None = None, notes: str | None = None,
    watchlist_id: str | None = None,
) -> dict:
    """A hand-entered player (UK/international, or anyone outside the AU
    Grassroots feed) — clearly marked source='manual', no automated stats."""
    player = ScoutedPlayer(source="manual", name=name, club_name=club_name, notes=notes)
    session.add(player)
    await session.flush()
    await scout_watchlist.ensure_card_on_watchlist(session, scout_org_id, player.id, watchlist_id)
    await session.commit()
    return await player_out(session, player)


async def refresh_player(session: AsyncSession, scouted_player_id: str) -> dict:
    """Force-refreshes EVERY club a player is linked to (not just the one
    club previously stored on ScoutedPlayer) — a player tracked at two
    clubs needs both kept current, or the second club's stint would go
    stale forever once linked."""
    player = await session.get(ScoutedPlayer, scouted_player_id)
    if not player:
        raise ValueError("Player not found.")
    if player.source != "au_grassroots":
        raise ValueError("This player has no automated data source to refresh from.")
    club_rows = (await session.execute(
        select(ScoutedPlayerClub).where(ScoutedPlayerClub.scouted_player_id == player.id)
    )).scalars().all()
    if not club_rows:
        raise ValueError("This player has no automated data source to refresh from.")

    statuses = []
    for club_row in club_rows:
        if not club_row.grassroots_participant_id:
            continue
        roster = await get_or_start_club_roster(
            session, club_row.club_org_guid, club_name=club_row.club_name, force=True,
        )
        statuses.append(roster.get("status"))
        if roster.get("status") != "ready":
            continue
        sliced = _slice_player(roster, club_row.grassroots_participant_id)
        if not sliced:
            continue
        club_row.stats_payload = sliced
        club_row.stats_built_at = datetime.now(timezone.utc)
        if club_row.is_primary:
            player.club_org_guid = club_row.club_org_guid
            player.club_name = club_row.club_name
            player.stats_payload = sliced
            player.stats_built_at = club_row.stats_built_at
            _stamp_internal_link(player, sliced, club_row.club_org_guid)
    await session.commit()

    refresh_status = "ready" if statuses and all(s == "ready" for s in statuses) else (
        "building" if any(s == "building" for s in statuses) else "partial"
    )
    return await player_out(session, player) | {"refresh_status": refresh_status}


async def list_tracked_players(session: AsyncSession, scout_org_id: str) -> list[dict]:
    """Every distinct player with at least one card on any of this org's
    watchlists — the flat "My players" directory, now derived from the real
    watchlist model instead of the phase-2 bookmark table."""
    res = await session.execute(
        select(ScoutedPlayer)
        .join(ScoutWatchlistCard, ScoutWatchlistCard.scouted_player_id == ScoutedPlayer.id)
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(ScoutWatchlist.scout_org_id == scout_org_id)
        .distinct()
        .order_by(ScoutedPlayer.name)
    )
    return [await player_out(session, p) for p in res.scalars().all()]


async def player_out(session: AsyncSession, p: ScoutedPlayer) -> dict:
    photo_url = None
    if p.internal_player_id:
        # A player already on BetterCricket via their own club: their real
        # uploaded photo (if any) wins over a scout-uploaded one — it's the
        # canonical image, not a stand-in. See services/scout_internal_link.py.
        linked = await session.get(Player, p.internal_player_id)
        photo_url = linked.photo_url if linked else None
    if not photo_url and p.photo_data:
        photo_url = f"/api/images/scouted-players/{p.id}/photo"

    club_rows = (await session.execute(
        select(ScoutedPlayerClub)
        .where(ScoutedPlayerClub.scouted_player_id == p.id)
        .order_by(ScoutedPlayerClub.is_primary.desc(), ScoutedPlayerClub.linked_at)
    )).scalars().all()

    clubs = [{
        "id": str(c.id),
        "club_org_guid": c.club_org_guid,
        "club_name": c.club_name,
        "grade_name": c.grade_name,
        "is_primary": c.is_primary,
        "totals": (c.stats_payload or {}).get("totals"),
        "seasons": (c.stats_payload or {}).get("seasons") or [],
        "stats_built_at": c.stats_built_at.isoformat() if c.stats_built_at else None,
        "linked_at": c.linked_at.isoformat() if c.linked_at else None,
        "linked_via": c.linked_via,
    } for c in club_rows]

    if clubs:
        # A season across several clubs — tag each with which club it came
        # from (a season row alone doesn't say), then combine into one
        # career total the same way the frontend combines seasons WITHIN
        # one club (see _combine_season_totals's own docstring).
        all_seasons = []
        for c in clubs:
            for season in c["seasons"]:
                all_seasons.append({**season, "club_name": c["club_name"], "club_org_guid": c["club_org_guid"]})
        stats = {"seasons": all_seasons, "totals": _combine_season_totals(all_seasons)}
    else:
        # A manual player, or one added before this feature existed and not
        # yet re-added — fall back to the legacy single-club snapshot.
        stats = p.stats_payload

    return {
        "id": str(p.id),
        "source": p.source,
        "name": p.name,
        "club_name": p.club_name,
        "grade_name": p.grade_name,
        "notes": p.notes,
        "photo_url": photo_url,
        "stats": stats,
        "stats_built_at": p.stats_built_at.isoformat() if p.stats_built_at else None,
        # True once this player resolved to a real BetterCricket club/player
        # (see scout_internal_link) — the stats above are exact per-game
        # figures rather than CA's public season aggregates, and Milestones
        # can date a crossing to a real match instead of only a season.
        "internal_link": p.internal_player_id is not None,
        "clubs": clubs,
        "other_club_candidates": p.other_club_candidates or [],
        "other_club_candidates_checked_at": (
            p.other_club_candidates_checked_at.isoformat() if p.other_club_candidates_checked_at else None
        ),
    }


# ─── cross-club linking (Spencer Green plays for several clubs) ──────────────

async def suggest_other_clubs(session: AsyncSession, scouted_player_id: str) -> dict:
    """Asks PlayHQ's own canonical player index (services.scout_live_search)
    which clubs this player is REALLY registered at — not a name-similarity
    guess. Spencer Green's own identity there lists all 12 real clubs/rep
    sides he plays for, keyed on the same id his play.cricket.com.au profile
    URL uses.

    Matching this ScoutedPlayer to the right live-search identity: prefer an
    EXACT id match against any participant id we already know for this
    player (their original grassroots_participant_id, or any linked club's
    own — see ScoutedPlayerClub); a raw CA aggregate id and this canonical
    id often do coincide. When no id matches, fall back to every identity
    whose name FUZZY-matches ours (scout_feed._score_name, the same
    NAME_MATCH_THRESHOLD find_name_matches already uses) — NOT an exact
    string match, and NOT just a lone unambiguous hit. Two things independently
    silently returned zero candidates for a real, scoutable player before this:
    (1) requiring uniqueness — PlayHQ's own index genuinely holds two-plus
    distinct people under one common name (confirmed live: "Benji Floros"
    alone resolves to two separate canonical ids); (2) requiring an exact
    string match — the aggregate feed a roster was built from and this live
    canonical index are different PlayHQ services (see scout_live_search's own
    docstring) and don't always agree on spelling out a nickname/middle name
    ("Benji" vs "Benjamin") or word order. Every candidate still needs a
    scout's confirm click in link_player_club before anything is linked, so
    surfacing an extra club that turns out to belong to a same-named or
    similarly-spelled stranger costs one Dismiss, not a wrong link. A
    genuinely zero-result search still returns no candidates — the scout
    still has "Find at other clubs" for a manual, scout-picked search.

    Writes the result onto ScoutedPlayer as a cache (other_club_candidates),
    same "recompute wholesale, never partial-edit" rule stats_payload
    already follows, and returns it."""
    player = await session.get(ScoutedPlayer, scouted_player_id)
    if not player:
        raise ValueError("Player not found.")
    if player.source != "au_grassroots":
        return {"candidates": [], "checked_at": None}

    club_rows = (await session.execute(
        select(ScoutedPlayerClub).where(ScoutedPlayerClub.scouted_player_id == player.id)
    )).scalars().all()
    linked_guids = {c.club_org_guid for c in club_rows}
    known_ids = {player.grassroots_participant_id} | {c.grassroots_participant_id for c in club_rows}
    known_ids.discard(None)

    result = await scout_live_search.search_playcommunity(player.name, types=("PLAYCOMM_PLAYER",))
    identity = next((p for p in result["players"] if p["id"] in known_ids), None)
    identities = [identity] if identity else []
    if identity is None:
        # No id we already hold matched anything live. Take EVERY identity
        # that fuzzy-matches our stored name at or above the same threshold
        # find_name_matches uses — not an exact string match (a nickname or
        # a different word order between the aggregate feed and this live
        # canonical index is enough to break equality) and not just a lone
        # unambiguous hit (PlayHQ's own index genuinely holds two-plus
        # distinct people under one common name). A candidate is never
        # auto-linked — link_player_club always needs a scout's confirm
        # click — so an extra, wrongly-matched club costs one Dismiss click,
        # while silently showing nothing costs the whole feature.
        identities = [
            p for p in result["players"]
            if scout_feed._score_name(player.name, p["name"]) >= scout_feed.NAME_MATCH_THRESHOLD
        ]
        if not identities:
            # A full "First Last" search term can come back with ZERO
            # results even when the person is right there in the index —
            # confirmed live: searching the literal term "Benjamin Floros"
            # returns nothing at all, while "Benji Floros" is one of 14 hits
            # for the bare surname "Floros". PlayHQ's own search appears to
            # match the WHOLE term, not an OR of its words, so a first-name
            # mismatch between the aggregate feed this player's name came
            # from and this live canonical index (a nickname, a middle name,
            # a typo) starves our fuzzy filter above of anything to even
            # look at. Retry once on the surname alone — reliably the widest
            # net PlayHQ's search will give us for one person — then apply
            # the same fuzzy filter over that wider result.
            surname = (player.name or "").strip().split()[-1] if (player.name or "").strip() else None
            if surname and surname.lower() != (player.name or "").strip().lower():
                wider = await scout_live_search.search_playcommunity(surname, types=("PLAYCOMM_PLAYER",))
                identities = [
                    p for p in wider["players"]
                    if scout_feed._score_name(player.name, p["name"]) >= scout_feed.NAME_MATCH_THRESHOLD
                ]

    candidates = []
    seen_guids = set()
    for ident in identities:
        for org in ident["organisations"]:
            if org["id"] in linked_guids or org["id"] in seen_guids:
                continue
            seen_guids.add(org["id"])
            candidates.append({"club_org_guid": org["id"], "club_name": org["name"], "canonical_participant_id": ident["id"]})

    player.other_club_candidates = candidates
    player.other_club_candidates_checked_at = datetime.now(timezone.utc)
    await session.commit()
    return {"candidates": candidates, "checked_at": player.other_club_candidates_checked_at.isoformat()}


async def _run_other_club_scan(scouted_player_id: str) -> None:
    """Detached-task wrapper for the automatic post-add scan (see add_player)
    — fire-and-forget, its own session, exceptions logged and swallowed so a
    slow/failed background scan never surfaces as an error to the scout who
    just added the player."""
    async with async_session_maker() as session:
        try:
            await suggest_other_clubs(session, scouted_player_id)
        except Exception as e:
            logger.exception(f"BetterScout: other-clubs scan failed for {scouted_player_id}: {e}")


async def search_other_club(session: AsyncSession, scouted_player_id: str, org_guid: str, club_name: str | None = None) -> dict:
    """On-demand: the scout names a SPECIFIC club they suspect this player
    also turns out for (the manual counterpart to suggest_other_clubs' live-
    search-driven automatic scan — for a club that search doesn't surface,
    e.g. one PlayHQ's index doesn't cover yet). Same build/poll contract as
    Discover's own roster fetch — a not-yet-cached club reports
    {"status": "building"} for the frontend to keep polling, same as
    get_or_start_club_roster already returns everywhere else."""
    player = await session.get(ScoutedPlayer, scouted_player_id)
    if not player:
        raise ValueError("Player not found.")
    roster = await get_or_start_club_roster(session, org_guid, club_name=club_name)
    if roster.get("status") != "ready":
        return {"status": roster.get("status"), "candidates": player.other_club_candidates or []}
    matches = await scout_feed.find_name_matches(session, player.name, only_club_guid=org_guid)
    existing = player.other_club_candidates or []
    merged = {(c["club_org_guid"], c.get("player_id")): c for c in existing}
    for m in matches:
        merged[(m["club_org_guid"], m["player_id"])] = {
            "club_org_guid": m["club_org_guid"], "club_name": m["club_name"], "player_id": m["player_id"],
            "name": m["name"], "confidence": m["confidence"],
        }
    player.other_club_candidates = list(merged.values())
    player.other_club_candidates_checked_at = datetime.now(timezone.utc)
    await session.commit()
    return {"status": "ready", "candidates": player.other_club_candidates}


async def link_player_club(
    session: AsyncSession, scouted_player_id: str, org_guid: str, player_id: str | None = None, *,
    is_primary: bool = False, canonical_participant_id: str | None = None,
) -> dict:
    """The scout confirmed a candidate really is the same person — links
    that club stint onto this ScoutedPlayer. Never called automatically; a
    suggestion in other_club_candidates only becomes a real
    ScoutedPlayerClub row via this explicit confirm.

    `player_id` — this club's OWN locally-scoped participant id — is
    required for the manual "Find at other clubs" flow (the scout picked a
    specific roster row) but optional for a live-search-driven candidate
    from suggest_other_clubs, which only knows the target club's name, not
    its own internal id for this player. When omitted, this resolves it
    itself: build the club's roster if needed (reporting {"status":
    "building"} for the caller to poll, exactly like search_other_club),
    then try an exact match on `canonical_participant_id` (cheap and precise
    when this club's own CA aggregate feed happens to use the same id),
    falling back to a name match scoped to this one club."""
    player = await session.get(ScoutedPlayer, scouted_player_id)
    if not player:
        raise ValueError("Player not found.")
    roster = await get_or_start_club_roster(session, org_guid)
    if roster.get("status") != "ready":
        return {"status": roster.get("status")}
    club_row = await _load_club_row(session, org_guid)
    resolved_club_name = (club_row.payload or {}).get("org", {}).get("name") if club_row else None

    if player_id is None:
        sliced = _slice_player(club_row.payload or {}, canonical_participant_id) if canonical_participant_id else None
        if sliced:
            player_id = canonical_participant_id
        else:
            matches = await scout_feed.find_name_matches(session, player.name, only_club_guid=org_guid, threshold=0.85)
            if not matches:
                raise ValueError("Could not find this player in that club's roster.")
            player_id = matches[0]["player_id"]
            sliced = _slice_player(club_row.payload or {}, player_id)
    else:
        sliced = _slice_player(club_row.payload or {}, player_id)
    if not sliced:
        raise ValueError("That player wasn't found in this club's roster.")

    club_row_obj = await _upsert_player_club(
        session, player.id, org_guid, resolved_club_name, sliced,
        participant_id=player_id, is_primary=is_primary, linked_via="match_confirmed",
    )
    if is_primary:
        player.club_org_guid = org_guid.lower()
        player.club_name = resolved_club_name
        player.stats_payload = sliced
        player.stats_built_at = club_row_obj.stats_built_at
        _stamp_internal_link(player, sliced, org_guid)

    # Drop the now-confirmed candidate out of the suggestion list.
    player.other_club_candidates = [
        c for c in (player.other_club_candidates or []) if c.get("club_org_guid") != org_guid.lower()
    ]
    await session.commit()
    return {"status": "ready", **(await player_out(session, player))}


async def unlink_player_club(session: AsyncSession, scouted_player_id: str, scouted_player_club_id: str) -> dict:
    """Removes one club stint. If it was the primary, promotes the most-
    recently-linked remaining stint (or clears ScoutedPlayer's singular
    columns back to None if this was the player's last club)."""
    player = await session.get(ScoutedPlayer, scouted_player_id)
    if not player:
        raise ValueError("Player not found.")
    club_row = await session.get(ScoutedPlayerClub, scouted_player_club_id)
    if not club_row or str(club_row.scouted_player_id) != str(player.id):
        raise ValueError("That club link wasn't found for this player.")
    was_primary = club_row.is_primary
    await session.delete(club_row)
    await session.flush()

    if was_primary:
        remaining = (await session.execute(
            select(ScoutedPlayerClub)
            .where(ScoutedPlayerClub.scouted_player_id == player.id)
            .order_by(ScoutedPlayerClub.linked_at.desc())
        )).scalars().first()
        if remaining:
            remaining.is_primary = True
            player.club_org_guid = remaining.club_org_guid
            player.club_name = remaining.club_name
            player.stats_payload = remaining.stats_payload
            player.stats_built_at = remaining.stats_built_at
            if remaining.grassroots_participant_id:
                _stamp_internal_link(player, remaining.stats_payload or {}, remaining.club_org_guid)
        else:
            player.club_org_guid = None
            player.club_name = None
            player.stats_payload = None
            player.stats_built_at = None
            player.internal_org_id = None
            player.internal_player_id = None
    await session.commit()
    return await player_out(session, player)


# ─── merging two profiles that turn out to be one real person ────────────────

async def merge_scouted_players(session: AsyncSession, keep_id: str, remove_id: str) -> dict:
    """Combines two ScoutedPlayer profiles that turned out to be the same
    real person — the BetterStats admin.merge_players precedent, scaled
    down to BetterScout's simpler model. Reported live: a player had two
    separate tracked profiles because he was added from two clubs whose own
    CA aggregate feeds happened to mint different participant ids for him
    (the well-documented "one real person, several CA GUIDs" class of
    issue) — his scouting notes on one profile were invisible from the
    other, and neither watchlist knew about the other's tracking.

    `keep_id` survives; `remove_id`'s real data folds in (never clobbering a
    value `keep` already has — same rule every other merge/fill-gap
    operation in this codebase follows) and its row is deleted once its
    children have all been moved or de-duplicated away. Platform-wide, not
    org-scoped, unlike remove_player_everywhere: a merge here affects every
    org tracking either profile, which is the point — it fixes a genuinely
    wrong split, not one org's private opinion."""
    if keep_id == remove_id:
        raise ValueError("Can't merge a profile with itself.")
    keep = await session.get(ScoutedPlayer, keep_id)
    remove = await session.get(ScoutedPlayer, remove_id)
    if not keep or not remove:
        raise ValueError("Player not found.")

    # ScoutedPlayerClub — skip a club `keep` already has (its own row wins),
    # re-point the rest. At most one row may carry is_primary; only promote
    # a moved-over row when `keep` currently has none.
    keep_club_guids = {
        row[0] for row in (await session.execute(
            select(ScoutedPlayerClub.club_org_guid).where(ScoutedPlayerClub.scouted_player_id == keep.id)
        )).all()
    }
    keep_has_primary = bool((await session.execute(
        select(ScoutedPlayerClub.id).where(
            ScoutedPlayerClub.scouted_player_id == keep.id, ScoutedPlayerClub.is_primary.is_(True),
        )
    )).first())
    for c in (await session.execute(
        select(ScoutedPlayerClub).where(ScoutedPlayerClub.scouted_player_id == remove.id)
    )).scalars().all():
        if c.club_org_guid in keep_club_guids:
            await session.delete(c)
            continue
        c.scouted_player_id = keep.id
        c.is_primary = not keep_has_primary
        keep_has_primary = True
        keep_club_guids.add(c.club_org_guid)

    # ScoutWatchlistCard — one card per (watchlist, player); a watchlist
    # both profiles happened to be on collides on that constraint. `keep`'s
    # own card wins there (it's already tracked on that board), the
    # duplicate is dropped rather than erroring.
    keep_watchlist_ids = {
        row[0] for row in (await session.execute(
            select(ScoutWatchlistCard.watchlist_id).where(ScoutWatchlistCard.scouted_player_id == keep.id)
        )).all()
    }
    for card in (await session.execute(
        select(ScoutWatchlistCard).where(ScoutWatchlistCard.scouted_player_id == remove.id)
    )).scalars().all():
        if card.watchlist_id in keep_watchlist_ids:
            await session.delete(card)
        else:
            card.scouted_player_id = keep.id
            keep_watchlist_ids.add(card.watchlist_id)

    # ScoutPlayerNote — org-scoped, no unique constraint to collide with.
    # This is the actual data-loss fix: every note recorded against the
    # OTHER profile was invisible from this one.
    await session.execute(
        update(ScoutPlayerNote).where(ScoutPlayerNote.scouted_player_id == remove.id).values(scouted_player_id=keep.id)
    )

    # ScoutMilestoneSeen — unique per (org, player, type, value); skip a
    # duplicate dismissal, re-point the rest.
    keep_milestones = {
        (row[0], row[1], row[2]) for row in (await session.execute(
            select(ScoutMilestoneSeen.scout_org_id, ScoutMilestoneSeen.milestone_type, ScoutMilestoneSeen.milestone_value)
            .where(ScoutMilestoneSeen.scouted_player_id == keep.id)
        )).all()
    }
    for m in (await session.execute(
        select(ScoutMilestoneSeen).where(ScoutMilestoneSeen.scouted_player_id == remove.id)
    )).scalars().all():
        key = (m.scout_org_id, m.milestone_type, m.milestone_value)
        if key in keep_milestones:
            await session.delete(m)
        else:
            m.scouted_player_id = keep.id
            keep_milestones.add(key)

    # ScoutPlayerSearchView — unique per (org, player); skip a duplicate,
    # keeping keep's own row.
    keep_search_orgs = {
        row[0] for row in (await session.execute(
            select(ScoutPlayerSearchView.scout_org_id).where(ScoutPlayerSearchView.scouted_player_id == keep.id)
        )).all()
    }
    for v in (await session.execute(
        select(ScoutPlayerSearchView).where(ScoutPlayerSearchView.scouted_player_id == remove.id)
    )).scalars().all():
        if v.scout_org_id in keep_search_orgs:
            await session.delete(v)
        else:
            v.scouted_player_id = keep.id
            keep_search_orgs.add(v.scout_org_id)

    # Fill gaps on keep from remove — never clobber a value keep already has.
    if not keep.notes and remove.notes:
        keep.notes = remove.notes
    if not keep.grade_name and remove.grade_name:
        keep.grade_name = remove.grade_name
    if not keep.photo_url and not keep.photo_data and (remove.photo_url or remove.photo_data):
        keep.photo_url, keep.photo_data, keep.photo_mime = remove.photo_url, remove.photo_data, remove.photo_mime
    if not keep.internal_player_id and remove.internal_player_id:
        keep.internal_org_id, keep.internal_player_id = remove.internal_org_id, remove.internal_player_id

    await session.flush()
    await session.delete(remove)
    await session.commit()
    return await player_out(session, keep)
