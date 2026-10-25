"""Running scores for a Fantasy round while it is being played.

Settling a round confirms its final scores. This is the other half: while games are in play, read
them again every few minutes and bring the round's provisional points (``refresh_live_round``) in
line, so a two day round shows its running scores instead of nothing until the end.

One pass for one season (``live_pass``):

1. Pull the fixtures CA has not finished with, through the club's ordinary game sync run narrowly
   (``sync_grassroots_game_level_data(live=True)``), so a game stored while it was in play has its
   figures put right from the running card.
2. For each round still being played, score it read only (``round_drift``) and only when its stored
   points differ (or an admin pressed Sync scores) write the provisional player, squad and ladder
   rows. A round that was settled early on its last day, before its last games were played, is
   settled again from its stored lineup when it has drifted, which banks no second free transfer.
3. Stamp ``fantasy_rounds.live_checked_at``, so "nothing moved" can be told from "nothing was looked
   at".

Never granted, filled or marked here: the free transfer rollover, head-to-head results, a round's
``scored`` status, prices. Those wait for the round to be settled.

Outbound traffic to Cricket Australia is bounded: only clubs running a Fantasy season with a round
whose window includes today, only inside the club's playing hours, one match list per grade (cached
by the CA client for 30 minutes) and one scorecard per unfinished game, at most ``LIVE_MAX_GAMES``
per pass, one game at a time, and never while that club has a sync of its own in flight. It can be
stopped per season (``rules.live_sync`` false) or for the whole platform (``FANTASY_LIVE_SYNC_ENABLED``).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import settings
from app.models.db import FantasyRound, FantasySeason, Organisation
from app.services import auto_sync, fantasy_engine

logger = logging.getLogger(__name__)

LIVE_SYNC_RULE = "live_sync"
# Club-local hours the scheduled pass looks at games. Late T20s finish after dark, and the 01:00
# results sync and the 05:00 settle cover everything outside them.
PLAY_FROM_HOUR = 7
PLAY_UNTIL_HOUR = 22
# An admin pressing Sync scores twice in a row gets the first answer.
MANUAL_COOLDOWN_SECONDS = 60
PAUSE_BETWEEN_CLUBS_SECONDS = 2.0

_org_locks: dict[str, asyncio.Lock] = {}

# What an admin is told when a pass did not run. The scheduled pass logs the key instead.
REASON_TEXT = {
    "no_running_round": "No round is being played today. A finished round is confirmed with Confirm final scores.",
    "sync_running": "The club has a sync running. The scores follow it when it finishes.",
    "already_running": "Scores are already being synced. Give it a minute.",
    "just_checked": "The scores were checked a moment ago.",
    "no_club_season": "The club has no season for this year to read games from.",
    "club_archived": "This club is archived.",
    "club_inactive": "This club is not active.",
    "club_subscription": "This club's subscription is not live.",
    "no_club": "Club not found.",
}


def live_sync_on(rules: dict | None) -> bool:
    """The season's own switch. Absent means on; only an explicit false stops the scheduled pass."""
    return (rules or {}).get(LIVE_SYNC_RULE) is not False


async def club_today(session: AsyncSession, fs, now: datetime | None = None) -> tuple[datetime, date]:
    """The club's local time now and its local date (the round windows are club dates)."""
    state = await fantasy_engine.club_state(session, fs.organisation_id)
    tz = ZoneInfo(fantasy_engine.lock_timezone_name(fs.rules, state))
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    return local, local.date()


async def running_rounds(session: AsyncSession, fs, today) -> list[FantasyRound]:
    """Rounds whose window includes ``today`` and that no admin has taken out of settlement. A round
    already marked scored is included: one that settled on its last morning is still being played."""
    return list((await session.execute(
        select(FantasyRound).where(
            FantasyRound.fantasy_season_id == fs.id,
            FantasyRound.status != fantasy_engine.ROUND_UNSETTLED,
            FantasyRound.start_date <= today,
            FantasyRound.end_date >= today,
        ).order_by(FantasyRound.round_number)
    )).scalars().all())


def _in_flight(org_id: str) -> bool:
    """The club has a sync of its own running: leave it to finish rather than race it."""
    from app.routers.organisations import _org_sync_running
    from app.routers.club_admin import _hard_refresh_running
    return org_id in _org_sync_running or org_id in _hard_refresh_running


async def _live_pass(session: AsyncSession, fs, *, manual: bool = False, now: datetime | None = None) -> dict:
    """One live pass for one season. ``manual`` is an admin pressing Sync scores: it ignores the
    playing hours and the season switch, always rewrites the provisional rows, and is rate limited
    instead. The caller commits (and rolls back on an error)."""
    out = {"ran": False, "reason": None, "games_checked": 0, "new_games": 0, "figures_changed": 0,
           "rows_added": 0, "players_moved": 0, "rounds": [], "checked_at": None}
    org = (await session.execute(
        select(Organisation).options(selectinload(Organisation.module_subscriptions))
        .where(Organisation.id == fs.organisation_id)
    )).scalar_one_or_none()
    if org is None:
        out["reason"] = "no_club"
        return out
    skip = auto_sync.skip_reason(org)
    if skip:
        out["reason"] = f"club_{skip}"
        return out

    local_now, today = await club_today(session, fs, now)
    rounds = await running_rounds(session, fs, today)
    if not rounds:
        out["reason"] = "no_running_round"
        return out
    if manual:
        last = max((r.live_checked_at for r in rounds if r.live_checked_at), default=None)
        if last and (datetime.now(timezone.utc) - last).total_seconds() < MANUAL_COOLDOWN_SECONDS:
            out["reason"] = "just_checked"
            out["checked_at"] = last.isoformat()
            return out
    else:
        if not settings.fantasy_live_sync_enabled:
            out["reason"] = "switched_off_platform"
            return out
        if not live_sync_on(fs.rules):
            out["reason"] = "switched_off"
            return out
        if not (PLAY_FROM_HOUR <= local_now.hour < PLAY_UNTIL_HOUR):
            out["reason"] = "outside_play_hours"
            return out

    org_id = str(org.id)
    if _in_flight(org_id):
        out["reason"] = "sync_running"
        return out
    lock = _org_locks.setdefault(org_id, asyncio.Lock())
    if lock.locked():
        out["reason"] = "already_running"
        return out

    async with lock:
        season_ids = list((await session.execute(
            text("SELECT id FROM seasons WHERE organisation_id = CAST(:o AS UUID) AND year = :y"),
            {"o": org_id, "y": fs.season_year},
        )).scalars().all())
        if not season_ids:
            out["reason"] = "no_club_season"
            return out
        from app.services import sync
        stats = await sync.sync_grassroots_game_level_data(
            org_id, None, since=min(r.start_date for r in rounds), season_ids=season_ids,
            live=True, live_today=today)
        out["games_checked"] = int(stats.get("gr_live_candidates", 0))
        out["new_games"] = int(stats.get("gr_games_new", 0))
        out["figures_changed"] = int(stats.get("gr_figures_refreshed", 0))
        out["rows_added"] = int(stats.get("gr_rows_repaired", 0))
        if stats.get("gr_games_failed"):
            out["games_failed"] = int(stats["gr_games_failed"])

        moved: set[str] = set()
        for rnd in rounds:
            drift = await fantasy_engine.round_drift(session, fs, rnd)
            moved.update(d["player_id"] for d in drift)
            if rnd.status == "scored":
                # Settled on its last morning, played since: same lineup, no second free transfer.
                if drift:
                    await fantasy_engine.settle_round(session, fs, rnd)
                    out["rounds"].append({"number": rnd.round_number, "action": "settled_again"})
            elif drift or manual:
                await fantasy_engine.refresh_live_round(session, fs, rnd)
                out["rounds"].append({"number": rnd.round_number, "action": "refreshed"})
        out["players_moved"] = len(moved)

        checked = datetime.now(timezone.utc)
        await session.execute(
            text("UPDATE fantasy_rounds SET live_checked_at = :t WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"t": checked, "ids": [str(r.id) for r in rounds]},
        )
        out["ran"] = True
        out["checked_at"] = checked.isoformat()
    return out


async def live_pass(session: AsyncSession, fs, *, manual: bool = False, now: datetime | None = None) -> dict:
    """See ``_live_pass``. Adds ``message``: the reason in words when nothing ran."""
    out = await _live_pass(session, fs, manual=manual, now=now)
    out["message"] = None if out["ran"] else REASON_TEXT.get(out["reason"] or "", out["reason"])
    return out


async def run_all(session_maker) -> list[dict]:
    """The scheduled pass: every season with a round that could be in play, one at a time, each in
    its own session so one club's failure cannot stop the rest."""
    today = datetime.now(timezone.utc).date()
    async with session_maker() as session:
        season_ids = list((await session.execute(
            text("""SELECT DISTINCT fantasy_season_id FROM fantasy_rounds
                    WHERE status <> :unsettled AND start_date <= :hi AND end_date >= :lo"""),
            {"unsettled": fantasy_engine.ROUND_UNSETTLED, "hi": today + timedelta(days=1),
             "lo": today - timedelta(days=1)},
        )).scalars().all())
    results: list[dict] = []
    for sid in season_ids:
        async with session_maker() as session:
            try:
                fs = await session.get(FantasySeason, sid)
                res = await live_pass(session, fs)
                await session.commit()
                res["season_id"] = str(sid)
                results.append(res)
                if res["ran"]:
                    logger.info("Fantasy live: season %s checked %d game(s), %d player(s) moved",
                                sid, res["games_checked"], res["players_moved"])
            except Exception as e:
                await session.rollback()
                logger.error("Fantasy live pass failed for season %s: %s", sid, e)
        await asyncio.sleep(PAUSE_BETWEEN_CLUBS_SECONDS)
    return results
