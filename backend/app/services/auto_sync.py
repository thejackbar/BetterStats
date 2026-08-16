"""Who the background sync runs for, and how far back it looks.

The weekly job used to be ``select(Organisation)`` with no WHERE and a full
historical pull per club. Two separate problems, both fixed here:

**Who.** A club that has been archived, switched off, or whose BetterStats
subscription has lapsed should not be costing us calls against Cricket
Australia's shared proxy every week. ``eligible_clubs`` is the one place that
decision is made, and it reuses ``auth.modules.org_core_live`` rather than
inventing a second idea of "lapsed" — that function already knows about a
cancelled or paused Core row, an expired Core trial, and the org-level master
switch, and it fails OPEN for a club whose subscription rows predate the
per-module scheme, so no long-established club is dropped by accident.

**How far back.** A club's whole history is re-pulled only when there is no
history yet (or the club has fallen far enough behind that catching up IS a
full pull). Every ordinary run asks for the fixtures played since the last
time a sync finished for that club, so the Sunday run covers the weekend and
the Monday run covers the day. ``recent_window_start`` computes that
watermark, and it reads the last SUCCESSFUL run — an interrupted or errored
run never moves it, so the next run automatically re-covers the gap instead
of leaving a hole nobody notices.

The watermark counts a manual Sync Now and a Full Rebuild too, not just the
scheduled runs. An admin who syncs on Saturday night has already pulled the
weekend, and the Sunday run should be asking "what's happened since then",
not "what's happened in the last seven days".
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.modules import org_core_live
from app.models.db import Organisation, SyncRun
from app.services import playhq_client

logger = logging.getLogger(__name__)

# The kind stamped on a scheduled incremental run. Deliberately NOT one of the
# existing kinds: 'org_full' and 'org_hard_refresh' mean "this club's whole
# history has been pulled", which several screens read as their sync-ready
# signal (the Setup Wizard's own gate, the All Clubs newly-registered filter).
# An incremental run must not be able to satisfy those.
RECENT_KIND = "org_recent"

# Kinds that bring a club up to date, and so move the watermark.
_WATERMARK_KINDS = (RECENT_KIND, "org_full", "org_hard_refresh")
# Kinds that mean the club's whole history has been pulled at least once.
_FULL_KINDS = ("org_full", "org_hard_refresh")

# How far back a run with no watermark looks. Also the effective floor for the
# Sunday run, since a week will have passed since the previous one.
DEFAULT_LOOKBACK_DAYS = 7

# Extended back past the watermark on every run. A result is often entered
# some hours after the last ball, so a window that started exactly at the
# previous run's finish would miss a fixture whose scorecard landed just after
# it. 26 hours also means the Monday run re-covers Sunday's fixtures rather
# than trusting that Sunday 03:00 saw a complete card for a game played the
# afternoon before.
OVERLAP_HOURS = 26

# A club this far behind is no longer a candidate for an incremental run —
# catching it up IS a full pull, and asking for "every fixture since" would be
# an unbounded scorecard fan-out wearing an incremental label.
MAX_LOOKBACK_DAYS = 90

# A season counts as in play for the window if it could still be running when
# the window opens. CA seasons run roughly September to March; 400 days is
# deliberately generous so a straddling season, a late final or a summer/winter
# competition can never be filtered out of a run that needed it.
SEASON_SPAN_DAYS = 400

SKIP_ARCHIVED = "archived"
SKIP_INACTIVE = "inactive"
SKIP_SUBSCRIPTION = "subscription_lapsed"


async def eligible_clubs(session: AsyncSession) -> tuple[list[Organisation], list[tuple[Organisation, str]]]:
    """Split every club into (sync these, skip these with a reason).

    Returns real ``Organisation`` rows with ``module_subscriptions`` eager
    loaded, because ``org_core_live`` needs them and a lazy load in async
    context raises. The skip list is returned rather than silently dropped so
    the caller can log what it passed over — a club quietly falling out of the
    weekly sync with no trace is how you end up debugging "why is this club's
    data three months old" from scratch.
    """
    rows = (await session.execute(
        select(Organisation).options(selectinload(Organisation.module_subscriptions))
    )).scalars().all()

    keep: list[Organisation] = []
    skip: list[tuple[Organisation, str]] = []
    for org in rows:
        reason = skip_reason(org)
        if reason:
            skip.append((org, reason))
        else:
            keep.append(org)
    return keep, skip


def skip_reason(org: Organisation, now: datetime | None = None) -> str | None:
    """Why this club is not auto-synced, or None if it is.

    Order matters only for the reason reported — a club can be several of
    these at once, and the first is the most specific thing to say about it.
    """
    if getattr(org, "archived_at", None) is not None:
        return SKIP_ARCHIVED
    if not getattr(org, "is_active", False):
        return SKIP_INACTIVE
    if not org_core_live(org, now or datetime.now(timezone.utc)):
        return SKIP_SUBSCRIPTION
    return None


async def last_sync_at(session: AsyncSession, org_id, kinds=_WATERMARK_KINDS) -> datetime | None:
    """When a sync of one of ``kinds`` last SUCCEEDED for this club.

    Success only: a run that errored, was cancelled, paused, or was cut off by
    a restart pulled some unknown fraction of its window, so treating it as a
    watermark would silently skip whatever it hadn't reached. Leaving it out
    means the next run re-covers the same ground, which is cheap and correct.
    """
    return (await session.execute(
        select(SyncRun.completed_at)
        .where(
            SyncRun.org_id == org_id,
            SyncRun.kind.in_(kinds),
            SyncRun.status == "success",
            SyncRun.completed_at.isnot(None),
        )
        .order_by(SyncRun.completed_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def plan_run(session: AsyncSession, org_id, now: datetime | None = None) -> dict:
    """Decide what kind of run this club needs, and over what window.

    Three outcomes:

    * ``full`` — the club has never had a successful whole-history pull, so
      there is nothing to be incremental against. A brand-new club, or one
      whose first sync has never got through.
    * ``full`` — the club HAS history but is more than ``MAX_LOOKBACK_DAYS``
      behind. Rebuilding the window would be a full pull anyway, and a full
      run also re-seeds seasons and grades that may have appeared meanwhile.
    * ``recent`` — the ordinary case: fixtures played since the last
      successful sync, less the overlap.

    ``since`` is a plain date because that is the granularity the fixture
    list gives us (``matchSchedule[].startDateTime``) and the granularity a
    cricket fixture actually has.
    """
    now = now or datetime.now(timezone.utc)

    ever_full = await last_sync_at(session, org_id, _FULL_KINDS)
    if ever_full is None:
        return {"mode": "full", "since": None, "reason": "no_full_sync_yet", "watermark": None}

    watermark = await last_sync_at(session, org_id)
    if watermark is None:
        # Shouldn't happen (a full sync is itself a watermark kind), but a
        # club whose runs were cleared from the log is entitled to a window
        # rather than a crash.
        return {"mode": "recent", "since": (now - timedelta(days=DEFAULT_LOOKBACK_DAYS)).date(),
                "reason": "no_watermark", "watermark": None}

    if watermark.tzinfo is None:
        watermark = watermark.replace(tzinfo=timezone.utc)

    behind = now - watermark
    if behind > timedelta(days=MAX_LOOKBACK_DAYS):
        return {"mode": "full", "since": None, "reason": "too_far_behind", "watermark": watermark}

    since = (watermark - timedelta(hours=OVERLAP_HOURS)).date()
    # A run that fires very soon after the last one still looks back a day or
    # so, never at an empty window.
    floor = (now - timedelta(days=2)).date()
    return {"mode": "recent", "since": min(since, floor), "reason": "since_last_sync",
            "watermark": watermark}


async def fixtures_in_window(org_id_str: str, since: date, now: date | None = None) -> dict:
    """Did this club play anything in the period since its last pull?

    That is the whole rule, and it is deliberately NOT a notion of "is this
    club's season over". A club has no fixtures in a period for all sorts of
    ordinary reasons — the off-season, the Christmas break, a bye, a washed-out
    round, a team between grades — and every one of them has the same right
    answer: there is nothing to pull, so do not pull. Asking the narrower
    question would mean modelling where a season starts and ends per club and
    per competition, and getting the same outcome only some of the time.

    Running the sync machinery to discover an empty period costs the shared
    Cricket Australia proxy a season-aggregate pass per club per run, so this
    asks the cheap question first.

    Returns ``{"sync": bool, "reason": str, "fixtures": int}``.

    **It errs towards syncing, and every branch that returns True is there
    for a reason a club would notice if it were missing:**

    * A CA season we do not hold yet, or hold with no grades — a new season
      has been published and there is structure to seed. Deciding "no
      fixtures" from grades we have not created yet is how a club silently
      stops syncing the day its new season opens.
    * Every grade returning an empty match list. ``get_grade_matches``
      returns ``[]`` for a transient upstream failure as well as for a
      genuinely empty grade, and those two are indistinguishable here — so a
      club whose whole card reads empty is treated as "could not tell",
      never as "nothing was played".

    The grade match lists this fetches are cached in-process by
    ``grassroots_scores_client``, so when the answer is "sync", the sync that
    follows reuses them rather than fetching them again.
    """
    from app.services import grassroots_scores_client as gr
    from app.models.db import Grade, Season, async_session_maker

    now = now or datetime.now(timezone.utc).date()
    since_str = since.isoformat()
    now_str = now.isoformat()

    ca_seasons = await playhq_client.get_seasons(org_id_str)
    in_play: list[str] = []
    for s in ca_seasons:
        raw = (s.get("startDate") or "")[:10]
        try:
            start = date.fromisoformat(raw) if raw else None
        except ValueError:
            start = None
        if season_in_window(start, since, now):
            sid = (s.get("id") or "").strip()
            if sid:
                in_play.append(sid)

    # No season could even have been running across the window, so there is
    # certainly nothing played in it. A short-circuit, not a season judgement:
    # it saves the grade round-trips below and reaches the same answer.
    if not in_play:
        return {"sync": False, "reason": "no_season_in_play", "fixtures": 0}

    async with async_session_maker() as session:
        rows = (await session.execute(
            select(Season.grassroots_id, Grade.grassroots_id, Grade.id)
            .join(Grade, Grade.season_id == Season.id, isouter=True)
            .where(Season.organisation_id == uuid.UUID(org_id_str),
                   Season.grassroots_id.in_(in_play))
        )).all()

    held_seasons = {r[0] for r in rows}
    if set(in_play) - held_seasons:
        return {"sync": True, "reason": "new_season_to_seed", "fixtures": 0}

    grade_guids = [(r[1] or str(r[2])) for r in rows if r[2] is not None]
    if not grade_guids:
        return {"sync": True, "reason": "no_grades_seeded_yet", "fixtures": 0}

    org_lower = org_id_str.lower()
    total_seen = 0
    in_window = 0
    for guid in grade_guids:
        try:
            matches = await gr.get_grade_matches(guid)
        except Exception as e:  # noqa: BLE001 — a probe must never block a sync
            logger.warning(f"Fixture probe failed for grade {guid}: {e}")
            return {"sync": True, "reason": "probe_failed", "fixtures": 0}
        total_seen += len(matches)
        for m in matches:
            sched = m.get("matchSchedule") or []
            day = ((sched[0].get("startDateTime") if sched else "") or "")[:10]
            # Played, or being played — a fixture still in the future is not a
            # result to pull, and its own run will come.
            if not day or day < since_str or day > now_str:
                continue
            teams = m.get("teams") or []
            if any(((t.get("owningOrganisation") or {}).get("id") or "").lower() == org_lower
                   for t in teams):
                in_window += 1

    if total_seen == 0:
        return {"sync": True, "reason": "no_match_data_returned", "fixtures": 0}
    if in_window == 0:
        return {"sync": False, "reason": "no_fixtures_in_window", "fixtures": 0}
    return {"sync": True, "reason": "fixtures_played", "fixtures": in_window}


def season_in_window(start_date: date | None, since: date, now: date | None = None) -> bool:
    """Could a season starting on ``start_date`` still have been running on or
    after ``since``?

    Used to cut the aggregate pass down from every season a club has ever
    played (52 for an established club, each costing three calls against CA,
    plus three more per grade) to the one or two actually in play. A season
    with no start date at all is excluded — an incremental run has no way to
    place it, and a full run covers it.
    """
    if start_date is None:
        return False
    now = now or datetime.now(timezone.utc).date()
    if start_date > now:
        return False
    return start_date + timedelta(days=SEASON_SPAN_DAYS) >= since
