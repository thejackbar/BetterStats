"""BetterScout — Overview screen ("who should I contact this week?").

Four panels, each pulling from data that already exists elsewhere in this
module: usage (scout_billing), pipeline_counts (the watchlist boards' own
columns — see the "no stage_kind" note below), form_movers and stale
(ScoutedPlayer.stats_payload + scout_player_notes), recent_clubs
(scout_club_views + scout_club_cache).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scout import (
    ScoutClubCache, ScoutClubView, ScoutOrg, ScoutPlayerNote, ScoutUser,
    ScoutWatchlist, ScoutWatchlistCard, ScoutWatchlistColumn, ScoutedPlayer,
)
from app.services import scout_billing


async def upsert_club_view(session: AsyncSession, scout_org_id: str, org_guid: str, club_name: str | None) -> None:
    res = await session.execute(
        select(ScoutClubView).where(ScoutClubView.scout_org_id == scout_org_id, ScoutClubView.club_org_guid == org_guid.lower())
    )
    row = res.scalar_one_or_none()
    if row is None:
        row = ScoutClubView(scout_org_id=scout_org_id, club_org_guid=org_guid.lower())
        session.add(row)
    row.club_name = club_name or row.club_name
    row.last_viewed_at = datetime.now(timezone.utc)
    await session.commit()


async def _pipeline_counts(session: AsyncSession, scout_org_id: str) -> dict:
    """IN PIPELINE = every distinct tracked player across every board.
    "final stage" = cards sitting in whichever column is LAST (highest
    position) on their own board — columns are free-text labels the backend
    has no opinion about (see ScoutWatchlistColumn's own docstring), so this
    counts the structural "last column" rather than guessing at a name like
    "Offer out". Labelled with that column's own name when every board's
    last column happens to share one name; otherwise a neutral label, since
    a single readout can't honestly speak for two different words."""
    total = (await session.execute(
        select(func.count(func.distinct(ScoutWatchlistCard.scouted_player_id)))
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(ScoutWatchlist.scout_org_id == scout_org_id)
    )).scalar_one() or 0

    boards = (await session.execute(
        select(ScoutWatchlist.id).where(ScoutWatchlist.scout_org_id == scout_org_id)
    )).scalars().all()

    final_count = 0
    final_labels: set[str] = set()
    for wl_id in boards:
        last_col = (await session.execute(
            select(ScoutWatchlistColumn)
            .where(ScoutWatchlistColumn.watchlist_id == wl_id)
            .order_by(ScoutWatchlistColumn.position.desc())
            .limit(1)
        )).scalar_one_or_none()
        if not last_col:
            continue
        final_labels.add(last_col.name)
        n = (await session.execute(
            select(func.count()).select_from(ScoutWatchlistCard).where(ScoutWatchlistCard.column_id == last_col.id)
        )).scalar_one() or 0
        final_count += n

    label = next(iter(final_labels)) if len(final_labels) == 1 else "Final stage"
    return {"in_pipeline": total, "final_stage_count": final_count, "final_stage_label": label}


_BATTING_HEAVY = lambda t: (t.get("wickets") or 0) <= (t.get("runs") or 0) / 20  # noqa: E731 — a simple, local heuristic


def _season_avg(season_rows: list[dict], batting: bool) -> float | None:
    if batting:
        runs = sum(s.get("runs") or 0 for s in season_rows)
        outs = sum((s.get("innings") or 0) - (s.get("not_outs") or 0) for s in season_rows)
        return round(runs / outs, 2) if outs > 0 else None
    wkts = sum(s.get("wickets") or 0 for s in season_rows)
    runs_c = sum(s.get("runs_conceded") or 0 for s in season_rows)
    return round(runs_c / wkts, 2) if wkts > 0 else None


def _form_mover(p: ScoutedPlayer) -> dict | None:
    """Latest active season vs the two before it, on the player's primary
    discipline — batting average for a batter, bowling average for a
    bowler (down is good there, so the sign is flipped for the delta before
    comparing magnitude, but the RAW delta shown to a scout is always
    "how did their own number move")."""
    payload = p.stats_payload or {}
    seasons = sorted((payload.get("seasons") or []), key=lambda s: s.get("year") or 0, reverse=True)
    active = [s for s in seasons if (s.get("matches") or 0) > 0]
    if len(active) < 2:
        return None
    totals = payload.get("totals") or {}
    batting = _BATTING_HEAVY(totals)
    latest, prior = active[0], active[1:3]
    latest_avg = _season_avg([latest], batting)
    prior_avg = _season_avg(prior, batting)
    if latest_avg is None or prior_avg is None:
        return None
    raw_delta = round(latest_avg - prior_avg, 2)
    improved = raw_delta > 0 if batting else raw_delta < 0
    magnitude = abs(raw_delta)
    if magnitude < 0.01:
        return None
    sparkline = [
        {"year": s.get("year"), "value": (s.get("runs") if batting else s.get("wickets"))}
        for s in sorted(active[:5], key=lambda s: s.get("year") or 0)
    ]
    return {
        "id": str(p.id),
        "name": p.name,
        "club_name": p.club_name,
        "grade_name": p.grade_name,
        "metric": "batting average" if batting else "bowling average",
        "delta": raw_delta,
        "improved": improved,
        "magnitude": magnitude,
        "current_value": latest_avg,
        "sparkline": sparkline,
    }


async def _form_movers(session: AsyncSession, scout_org_id: str, limit: int = 6) -> tuple[list[dict], int]:
    players = (await session.execute(
        select(ScoutedPlayer)
        .join(ScoutWatchlistCard, ScoutWatchlistCard.scouted_player_id == ScoutedPlayer.id)
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(ScoutWatchlist.scout_org_id == scout_org_id, ScoutedPlayer.stats_payload.isnot(None))
        .distinct()
    )).scalars().all()
    movers = [m for p in players if (m := _form_mover(p))]
    movers.sort(key=lambda m: m["magnitude"], reverse=True)
    return movers[:limit], len(movers)


async def _stale_players(session: AsyncSession, scout_org_id: str, stale_after_weeks: int) -> list[dict]:
    players = (await session.execute(
        select(ScoutedPlayer)
        .join(ScoutWatchlistCard, ScoutWatchlistCard.scouted_player_id == ScoutedPlayer.id)
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(ScoutWatchlist.scout_org_id == scout_org_id)
        .distinct()
    )).scalars().all()
    if not players:
        return []
    latest_notes = dict((await session.execute(
        select(ScoutPlayerNote.scouted_player_id, func.max(ScoutPlayerNote.occurred_at))
        .where(ScoutPlayerNote.scout_org_id == scout_org_id, ScoutPlayerNote.scouted_player_id.in_([p.id for p in players]))
        .group_by(ScoutPlayerNote.scouted_player_id)
    )).all())
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=stale_after_weeks)
    out = []
    for p in players:
        if p.source == "manual":
            out.append({
                "id": str(p.id), "name": p.name, "club_name": p.club_name, "manual": True,
                "note": "manual entry",
            })
            continue
        last_note = latest_notes.get(p.id)
        candidates = [d for d in [p.stats_built_at, last_note] if d is not None]
        last_activity = max(candidates) if candidates else None
        if last_activity and last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        if last_activity is not None and last_activity >= cutoff:
            continue
        weeks = None
        if last_activity is not None:
            weeks = max(1, (datetime.now(timezone.utc) - last_activity).days // 7)
        out.append({
            "id": str(p.id), "name": p.name, "club_name": p.club_name, "manual": False,
            "note": (f"stats {weeks} wks old" if p.stats_built_at and (not last_note or p.stats_built_at >= last_note)
                     else f"no note, {weeks} wks" if weeks is not None else "no activity recorded"),
        })
    return out


async def _recent_clubs(session: AsyncSession, scout_org_id: str, refresh_cadence_days: int, limit: int = 4) -> list[dict]:
    views = (await session.execute(
        select(ScoutClubView)
        .where(ScoutClubView.scout_org_id == scout_org_id)
        .order_by(ScoutClubView.last_viewed_at.desc())
        .limit(limit)
    )).scalars().all()
    if not views:
        return []
    caches = dict((await session.execute(
        select(ScoutClubCache.club_org_guid, ScoutClubCache)
        .where(ScoutClubCache.club_org_guid.in_([v.club_org_guid for v in views]))
    )).all())
    now = datetime.now(timezone.utc)
    out = []
    for v in views:
        cache = caches.get(v.club_org_guid)
        player_count = len(((cache.payload or {}).get("players") or [])) if cache else None
        built_at = cache.built_at if cache else None
        stale = False
        if built_at:
            if built_at.tzinfo is None:
                built_at = built_at.replace(tzinfo=timezone.utc)
            stale = (now - built_at).days > refresh_cadence_days
        out.append({
            "org_guid": v.club_org_guid,
            "club_name": v.club_name or (cache.club_name if cache else None),
            "player_count": player_count,
            "built_at": built_at.isoformat() if built_at else None,
            "stale": stale,
        })
    return out


_CADENCE_DAYS = {"daily": 1, "weekly": 7, "manual": 3650}


async def build_overview(session: AsyncSession, org: ScoutOrg) -> dict:
    usage = await scout_billing.usage_for(session, org)
    pipeline = await _pipeline_counts(session, org.id)
    movers, movers_total = await _form_movers(session, org.id)
    stale = await _stale_players(session, org.id, org.stale_after_weeks or 6)
    recent_clubs = await _recent_clubs(session, org.id, _CADENCE_DAYS.get(org.refresh_cadence, 7))
    return {
        "usage": usage,
        "pipeline_counts": pipeline,
        "form_movers": movers,
        "form_movers_total": movers_total,
        "stale": stale,
        "recent_clubs": recent_clubs,
    }
