"""A club's trial window — the ONE definition, shared by the audience and the email.

BetterCricket's outreach needs to answer two questions about a prospect club:
is it in a trial that is about to finish, and has its trial already run out. A
segment picks the audience and a merge variable writes the number into the email
body, so the two MUST be computed from the same place: an email that says "7 days
left" inside a segment built as "at most 7 days left" is the whole point, and two
separate queries shaped the same way is how a cell and its list start disagreeing.

The window is read off ``org_module_subscriptions`` rows still marked ``trial``.
An expired trial's row is deliberately LEFT in that state (see
module_subscriptions.sweep_expired_trials — "the expired row is left as a record,
status stays trial with a past end"), so a past ``trial_ends_at`` on a ``trial``
row IS the expired state. A club that converted has no ``trial`` rows left and is
correctly neither in a trial nor expired.

A club can hold several module trials. The window is the LATEST end date across
them (``MAX(trial_ends_at)``), because that is the day the club actually stops
having anything on trial — it is still trialing while any one module is live, and
it has expired only once every one of them has run out.

**An open-ended trial (a ``trial`` row with no end date) answers NEITHER
question.** It has no countdown, so there is no number of days to report, and it
must never read as expired — that would send "your trial has finished" to a club
whose trial is still running. Silence where the data cannot answer, rather than a
confident wrong number.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import Float, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import STATUS_TRIAL
from app.models.db import OrgModuleSubscription

# The merge variables this module resolves, in display order. Deliberately NOT in
# routers/comms.py's EDITABLE_MERGE_KEYS: these are computed facts about the
# club's subscription, and letting someone hand-override "days left" would put a
# number in an email that the segment behind it disagrees with.
TRIAL_VAR_KEYS = ("trial_days_left", "trial_days_since_expiry", "trial_end_date")

_SECONDS_PER_DAY = 86400.0


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    """A stored timestamptz comes back aware; be tolerant of a naive one rather
    than raising mid-send on the subtraction."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def trial_window_subquery():
    """(org_id, ends_at, open_ended) per club with at least one trial row.

    Joined on ``marketing_clubs.existing_org_id`` by the segment builder. A
    prospect that was never onboarded has no org and so no row here — it falls
    out of the outer join as NULL, which reads as "no tracked trial".
    """
    return (
        select(
            OrgModuleSubscription.organisation_id.label("org_id"),
            func.max(OrgModuleSubscription.trial_ends_at).label("ends_at"),
            func.bool_or(OrgModuleSubscription.trial_ends_at.is_(None)).label("open_ended"),
            # ``ends_at`` is NULL both for a club with no trial at all and for one
            # whose only trial has no end date, so it cannot answer "has a trial".
            # This marker can: it is non-NULL for every row the subquery emits, and
            # NULL only where the outer join found nothing.
            literal(True).label("has_trial"),
        )
        .where(OrgModuleSubscription.status == STATUS_TRIAL)
        .group_by(OrgModuleSubscription.organisation_id)
        .subquery()
    )


def days_left_sql(ends_at_col):
    """The SQL twin of :func:`days_left`. FLOOR of the whole-day difference, which
    is what Python's ``timedelta.days`` already does in both directions (it floors,
    so half a day past the end reads -1). Expressed the same way on both sides so
    the segment matches on exactly the integer the email prints."""
    return func.floor(
        cast(func.extract("epoch", ends_at_col - func.now()), Float) / _SECONDS_PER_DAY
    )


def days_left(ends_at: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    """Whole days until the trial ends. SIGNED and NOT clamped — negative means it
    has already finished, which is the entire distinction between the two
    scenarios. Do not clamp this to 0 in a new caller: that is the exact bug
    ``crm.trial_days_remaining_by_club`` documents, where every already-expired
    trial read identically to one expiring today."""
    if ends_at is None:
        return None
    return (_aware(ends_at) - _now(now)).days


def days_since_sql(ends_at_col):
    """The SQL twin of :func:`days_since`."""
    return func.floor(
        cast(func.extract("epoch", func.now() - ends_at_col), Float) / _SECONDS_PER_DAY
    )


def days_since(ends_at: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    """Whole days since the trial ended — its OWN floor, not the negation of
    :func:`days_left`.

    Both count whole days elapsed, so each floors towards its own end of the
    window: a trial that finished 3.2 days ago has been over for 3 whole days,
    and negating ``days_left`` (which floors to -4) would report 4. That
    off-by-one is visible in the email, so the two are computed separately and
    the verification asserts the printed figure against the segment boundary.
    """
    if ends_at is None:
        return None
    return (_now(now) - _aware(ends_at)).days


class TrialWindow:
    """One club's resolved trial state."""

    __slots__ = ("ends_at", "open_ended", "has_trial", "_now", "_days")

    def __init__(self, ends_at: Optional[datetime], open_ended: bool = False,
                 now: Optional[datetime] = None, has_trial: bool = True):
        self.ends_at = _aware(ends_at) if ends_at is not None else None
        self.open_ended = bool(open_ended)
        # A club can hold a trial with no end date at all, so "has a trial" is a
        # separate fact from "has an end date".
        self.has_trial = bool(has_trial)
        self._now = _now(now)
        self._days = days_left(self.ends_at, self._now)

    @property
    def in_trial(self) -> bool:
        """Open-ended counts as in a trial — it just has no countdown."""
        return self.has_trial and (
            self.open_ended or (self._days is not None and self._days >= 0))

    @property
    def expired(self) -> bool:
        return (self.has_trial and not self.open_ended
                and self._days is not None and self._days < 0)

    @property
    def days_remaining(self) -> Optional[int]:
        """Days until expiry, or None when there is no live dated trial to count."""
        return self._days if (self._days is not None and self._days >= 0 and not self.open_ended) else None

    @property
    def days_since_expiry(self) -> Optional[int]:
        return days_since(self.ends_at, self._now) if self.expired else None

    def merge_vars(self) -> dict:
        """The three ``{{…}}`` values for this club. A figure that does not apply
        renders BLANK, never ``0`` — "0 days left" in an email to a club that is
        not on a trial is a lie, and a blank is what every other directory
        variable already does when it has nothing to say."""
        left = self.days_remaining
        since = self.days_since_expiry
        return {
            "trial_days_left": str(left) if left is not None else "",
            "trial_days_since_expiry": str(since) if since is not None else "",
            # The date reads correctly whenever the email is opened, where a
            # countdown written at send time is wrong by the next morning.
            "trial_end_date": self.ends_at.strftime("%-d %B %Y") if self.ends_at else "",
        }


#: What the three variables resolve to for a contact with no club trial at all.
BLANK_TRIAL_VARS = {k: "" for k in TRIAL_VAR_KEYS}


async def windows_for_orgs(session: AsyncSession, org_ids: Iterable,
                           *, now: Optional[datetime] = None) -> dict:
    """organisation_id -> TrialWindow, batched (no N+1). Absent when the club has
    no ``trial`` subscription row at all."""
    ids = [i for i in set(org_ids or ()) if i]
    if not ids:
        return {}
    w = trial_window_subquery()
    rows = (await session.execute(
        select(w.c.org_id, w.c.ends_at, w.c.open_ended).where(w.c.org_id.in_(ids))
    )).all()
    return {org_id: TrialWindow(ends_at, open_ended, now)
            for org_id, ends_at, open_ended in rows}


async def vars_by_marketing_club(session: AsyncSession, clubs: Iterable,
                                 *, now: Optional[datetime] = None) -> dict:
    """marketing_club_id -> the three merge variables, batched for a send.

    Every listed club gets an entry, so a directory club that has never been
    onboarded (or has no trial) resolves the variables to blank rather than
    leaving a raw ``{{trial_days_left}}`` in the email.
    """
    clubs = [c for c in (clubs or ()) if c is not None]
    if not clubs:
        return {}
    windows = await windows_for_orgs(
        session, (getattr(c, "existing_org_id", None) for c in clubs), now=now)
    out = {}
    for club in clubs:
        window = windows.get(getattr(club, "existing_org_id", None))
        out[club.id] = window.merge_vars() if window else dict(BLANK_TRIAL_VARS)
    return out


async def vars_for_marketing_club(session: AsyncSession, club,
                                  *, now: Optional[datetime] = None) -> dict:
    """The single-contact form of :func:`vars_by_marketing_club` (preview, test
    send, the contact detail view)."""
    if club is None:
        return dict(BLANK_TRIAL_VARS)
    return (await vars_by_marketing_club(session, [club], now=now)).get(
        club.id, dict(BLANK_TRIAL_VARS))
