"""Kill switch for the platform's own outbound email.

Every email BetterCricket sends leaves through one door
(``email_service.get_email_provider().send``), so the pause lives there rather
than being sprinkled across the ten places that compose a message. What
decides whether a given send is allowed is the message's own ``category``:

  ``automated``      a scheduled scan sent it; nobody pressed send. The six
                     trial-lifecycle nudges, the two member-portal reminders
                     and the Club Diary task reminder.
  ``transactional``  one person's action produced exactly one email —
                     invites, both password resets, the signup verification
                     code, the member-portal sign-in link, a vote nudge, an
                     unpause request.
  ``campaign``       a person composed it and clicked send: a BetterComms
                     campaign (and its test send) or a sales rep's outreach.
                     NEVER pausable here — a club sending its own newsletter
                     has nothing to do with the platform's background email,
                     and BetterComms has its own suspension controls.

**Both pausable categories default to PAUSED.** That is the point: the pause
takes effect the moment this deploys, with nobody needing to find a switch
first, and staying paused is the state you fall back into if the settings row
is missing or unreadable. Turning either group back on is the deliberate act,
from All Clubs -> General Settings.

``category`` itself defaults to ``transactional`` on ``EmailMessage``, so a
send that never names a category is paused rather than slipping out. Only the
three person-sent paths opt into ``campaign``, and they do it explicitly.

Read this way round it is fail-safe in both directions: a new email added
later is paused until somebody thinks about which category it belongs to, and
a DB hiccup pauses rather than floods.
"""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

CATEGORY_AUTOMATED = "automated"
CATEGORY_TRANSACTIONAL = "transactional"
CATEGORY_CAMPAIGN = "campaign"

CATEGORIES = (CATEGORY_AUTOMATED, CATEGORY_TRANSACTIONAL, CATEGORY_CAMPAIGN)

# The two a super admin can pause. 'campaign' is deliberately absent.
PAUSABLE_CATEGORIES = (CATEGORY_AUTOMATED, CATEGORY_TRANSACTIONAL)

# platform_settings key per pausable category.
SETTING_KEYS = {
    CATEGORY_AUTOMATED: "automated_emails_paused",
    CATEGORY_TRANSACTIONAL: "transactional_emails_paused",
}

# Paused unless the settings row says otherwise — see the module docstring.
DEFAULT_PAUSED = True

# The flags are read on the send path, which has no session of its own, so the
# lookup opens one and the answer is cached. Short enough that unpausing takes
# effect within half a minute without a restart; long enough that a campaign
# blasting a few thousand recipients doesn't hit the DB per message.
CACHE_TTL_SECONDS = 30

_cache: dict[str, bool] | None = None
_cache_at: float = 0.0
_lock = asyncio.Lock()


def invalidate_cache() -> None:
    """Drop the cached flags so the next send re-reads them. Called right after
    a super admin saves General Settings, so a pause or an unpause is visible
    immediately rather than up to CACHE_TTL_SECONDS later."""
    global _cache, _cache_at
    _cache = None
    _cache_at = 0.0


async def _load() -> dict[str, bool]:
    from app.models.db import async_session_maker
    from app.services import platform_settings as ps

    async with async_session_maker() as session:
        blob = await ps.get_settings(session)
    out = {}
    for category, key in SETTING_KEYS.items():
        value = blob.get(key)
        out[category] = DEFAULT_PAUSED if value is None else bool(value)
    return out


async def paused_state() -> dict[str, bool]:
    """{category: is_paused} for the pausable categories, cached.

    A failure to read the flags returns the paused defaults rather than
    raising — a database that can't answer must not become a licence to send.
    """
    global _cache, _cache_at
    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < CACHE_TTL_SECONDS:
        return _cache
    async with _lock:
        # Another waiter may have refreshed while this one queued.
        if _cache is not None and (time.monotonic() - _cache_at) < CACHE_TTL_SECONDS:
            return _cache
        try:
            loaded = await _load()
        except Exception:  # noqa: BLE001
            logger.exception("email pause: could not read the flags, staying paused")
            loaded = {c: DEFAULT_PAUSED for c in PAUSABLE_CATEGORIES}
        _cache = loaded
        _cache_at = time.monotonic()
        return loaded


async def is_paused(category: str | None) -> bool:
    """Whether a send in this category is currently held.

    An unrecognised category is treated as ``transactional`` — the same
    fail-safe reason ``EmailMessage.category`` defaults to it.
    """
    if category == CATEGORY_CAMPAIGN:
        return False
    if category not in PAUSABLE_CATEGORIES:
        category = CATEGORY_TRANSACTIONAL
    return (await paused_state()).get(category, DEFAULT_PAUSED)
