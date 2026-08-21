"""When the daily backup is due — the one place Perth time is resolved.

The schedule a super admin sets (Backup settings page) is a PERTH wall-clock
time; see ``platform_settings.get_backup_schedule``. Three things need to
agree about what that means, so all three come through here:

- ``app/scripts/backup_task.py should-run`` — what the host timer's every-15-
  minutes tick asks before doing any real work.
- ``routers/backup_admin.py`` — the "next run" line on the settings screen.
- the retention window, which counts Perth days rather than 24-hour blocks
  from whenever the last run happened to start.

**A missed run catches up rather than being skipped.** The rule is "the
scheduled time has passed today (Perth) and today has no completed backup
yet", not "the clock currently reads exactly 03:00" — a box that was down at
03:00, or a tick pattern that steps over the configured minute, would
otherwise silently cost a club a whole day's backup with nothing to see. It
is still at most one automatic backup per Perth day: the completed-today
check is what makes the frequent tick idempotent.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

PERTH = ZoneInfo("Australia/Perth")


def perth_now() -> datetime:
    return datetime.now(PERTH)


def scheduled_at(day: date, schedule: dict) -> datetime:
    """The Perth-local moment the backup is due on ``day``."""
    return datetime(
        day.year, day.month, day.day,
        int(schedule["hour"]), int(schedule["minute"]), tzinfo=PERTH,
    )


def next_run_at(schedule: dict, now: datetime | None = None,
                last_completed: datetime | None = None) -> datetime:
    """When the next automatic backup will run, as an aware Perth datetime.

    Today's slot if it hasn't come round yet, or if it has passed and today
    still has no completed backup (the catch-up above — the next tick takes
    it), otherwise tomorrow's.
    """
    now = now or perth_now()
    today_slot = scheduled_at(now.date(), schedule)
    if now < today_slot:
        return today_slot
    if not completed_on(now.date(), last_completed):
        return today_slot
    return scheduled_at(now.date() + timedelta(days=1), schedule)


def completed_on(day: date, last_completed: datetime | None) -> bool:
    """Did a backup complete on this Perth day? ``last_completed`` may be any
    aware datetime (it comes from a TIMESTAMPTZ column)."""
    if last_completed is None:
        return False
    if last_completed.tzinfo is None:  # a naive value can only be UTC here
        last_completed = last_completed.replace(tzinfo=ZoneInfo("UTC"))
    return last_completed.astimezone(PERTH).date() == day


def is_due(schedule: dict, last_completed: datetime | None,
           now: datetime | None = None) -> tuple[bool, str]:
    """``(due, reason)`` — the reason is what the host script logs when it
    decides to skip, so a quiet tick is explainable without guesswork."""
    now = now or perth_now()
    slot = scheduled_at(now.date(), schedule)
    stamp = f"{int(schedule['hour']):02d}:{int(schedule['minute']):02d} Perth"
    if completed_on(now.date(), last_completed):
        return False, "a backup has already completed today"
    if now < slot:
        return False, f"not due yet (scheduled {stamp}, now {now:%H:%M} Perth)"
    return True, f"due (scheduled {stamp}, now {now:%H:%M} Perth)"
