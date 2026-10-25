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

A round stays open to this pass from its first day until the day before the next round starts (a
few days after its last day when it is the final round), not just while its own window lasts: its last
day's games finish and get entered after the window has closed, and the gap between two rounds is
exactly when a finished round is waiting to be confirmed. Once its window is over a round is looked at
only ``ENDED_ROUND_HOURS`` (four times a day), so a quiet fortnight costs next to nothing.

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
from app.services import auto_sync, fantasy_engine, fantasy_realign

logger = logging.getLogger(__name__)

LIVE_SYNC_RULE = "live_sync"
# Club-local hours the scheduled pass looks at games. Late T20s finish after dark, and the 01:00
# results sync and the 05:00 settle cover everything outside them.
PLAY_FROM_HOUR = 7
PLAY_UNTIL_HOUR = 22
# Club-local hours at which the scheduled pass looks at a round whose window is over but which is still
# open (no later round has started). The first pass in the hour does it (the job runs every 10 minutes).
ENDED_ROUND_HOURS = (8, 12, 16, 20)
# After the LAST round of a season there is no next round to close it: stay open this many days.
FINAL_ROUND_GRACE_DAYS = 3
# An admin pressing Sync scores twice in a row gets the first answer.
MANUAL_COOLDOWN_SECONDS = 60
PAUSE_BETWEEN_CLUBS_SECONDS = 2.0

_org_locks: dict[str, asyncio.Lock] = {}

# What an admin is told when a pass did not run. The scheduled pass logs the key instead.
REASON_TEXT = {
    "no_running_round": "No round is open to sync right now. A round stays open until the next one starts.",
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


def round_states(rounds: list, today: date) -> dict:
    """``{round id: (playing, open)}`` for one season's rounds on a club-local ``today``.

    ``playing``: today is inside the round's own window. ``open``: the round has started and the next
    round has not (the day before it starts is the last open day; for the final round, a few days
    after its last day), or it is being played. A round an admin took out of settlement is neither."""
    ordered = sorted(rounds, key=lambda r: r.round_number)
    out: dict = {}
    for i, r in enumerate(ordered):
        if r.status == fantasy_engine.ROUND_UNSETTLED or not r.start_date or not r.end_date:
            out[r.id] = (False, False)
            continue
        nxt = next((n.start_date for n in ordered[i + 1:] if n.start_date), None)
        until = (nxt - timedelta(days=1)) if nxt else r.end_date + timedelta(days=FINAL_ROUND_GRACE_DAYS)
        playing = r.start_date <= today <= r.end_date
        out[r.id] = (playing, playing or (r.start_date <= today <= max(until, r.end_date)))
    return out


async def season_rounds(session: AsyncSession, fs) -> list[FantasyRound]:
    return list((await session.execute(
        select(FantasyRound).where(FantasyRound.fantasy_season_id == fs.id).order_by(FantasyRound.round_number)
    )).scalars().all())


async def running_rounds(session: AsyncSession, fs, today) -> list[FantasyRound]:
    """The season's rounds that are open to the live pass today (see ``round_states``). A round already
    marked scored is included: one that settled on its last morning is still being played, and one whose
    last games were entered after it settled still moves."""
    rounds = await season_rounds(session, fs)
    states = round_states(rounds, today)
    return [r for r in rounds if states[r.id][1]]


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
    all_rounds = await season_rounds(session, fs)
    states = round_states(all_rounds, today)
    rounds = [r for r in all_rounds if states[r.id][1]]
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
        if not any(playing for playing, _ in states.values()) and not (
                local_now.hour in ENDED_ROUND_HOURS and local_now.minute < 10):
            out["reason"] = "waiting_for_next_check"   # only finished rounds are open: four looks a day
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

        # A team stamped as joining in the round after one a realignment re-opened is skipped for it.
        try:
            rejoined = await fantasy_realign.repair_joined_rounds(session, fs)
        except Exception:
            logger.exception("Fantasy live: re-stamping joined rounds failed for season %s", fs.id)
            rejoined = 0
        out["teams_rejoined"] = rejoined

        moved: set[str] = set()
        for rnd in rounds:
            drift = await fantasy_engine.round_drift(session, fs, rnd)
            moved.update(d["player_id"] for d in drift)
            if rnd.status == "scored":
                # Settled on its last morning, played since: same lineup, no second free transfer.
                if drift:
                    await fantasy_engine.settle_round(session, fs, rnd)
                    out["rounds"].append({"number": rnd.round_number, "action": "settled_again"})
            elif drift or manual or rejoined:
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


async def seasons_to_check(session_maker, today: date) -> list:
    """Seasons with a round open to the live pass on ``today`` or the day either side of it (the clubs
    are in different timezones; ``live_pass`` decides on the club's own date). Every round of such a
    season is read, because the next round's start is what closes a round."""
    near = select(FantasyRound.fantasy_season_id).where(
        FantasyRound.start_date <= today + timedelta(days=1),
        FantasyRound.end_date >= today - timedelta(days=60))
    async with session_maker() as session:
        rows = (await session.execute(
            select(FantasyRound).where(FantasyRound.fantasy_season_id.in_(near))
        )).scalars().all()
    by_season: dict = {}
    for r in rows:
        by_season.setdefault(r.fantasy_season_id, []).append(r)
    return [sid for sid, rs in by_season.items()
            if any(o for d in (-1, 0, 1) for _, o in round_states(rs, today + timedelta(days=d)).values())]


async def run_all(session_maker) -> list[dict]:
    """The scheduled pass: every season with a round that could be in play, one at a time, each in
    its own session so one club's failure cannot stop the rest."""
    season_ids = await seasons_to_check(session_maker, datetime.now(timezone.utc).date())
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
