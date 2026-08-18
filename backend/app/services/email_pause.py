"""Pause switch for BetterCricket's own reminder and nudge emails.

Every email BetterCricket sends leaves through one door
(``email_service.get_email_provider().send``), so the switch lives there
rather than being sprinkled across the places that compose a message. What
decides whether a send is allowed is the message's own ``category``:

  ``automated``      a scheduled scan sent it, and nobody asked for it: the
                     six trial-lifecycle nudges, the two member-portal
                     reminders and the Club Diary task reminder. Marketing
                     and housekeeping — a club not receiving one loses
                     nothing it needs. **This is the only pausable
                     category.**

  ``transactional``  one person's action produced exactly one email, and
                     that email is how the action completes: an invite, both
                     password resets, the signup verification code, the
                     member-portal sign-in link, a vote nudge, an unpause
                     request. **Never pausable.** These carry system
                     operations — without them nobody can accept an invite,
                     recover a password, finish a self-serve signup or sign
                     in to a member portal. There is deliberately no setting,
                     no flag and no code path that holds one back.

  ``campaign``       a person composed it and pressed Send: a BetterComms
                     campaign (and its test send) or a sales rep's outreach.
                     **Never pausable.** A club sending its own newsletter
                     has nothing to do with BetterCricket's reminders, and
                     BetterComms has its own suspension, quota and
                     unsubscribe controls.

The rule is enforced by construction, not by remembering to check: only
``automated`` appears in ``PAUSABLE_CATEGORIES``, ``is_paused`` returns False
for everything else before it so much as looks at a setting, and there is no
platform setting for any other category. Adding one would mean editing this
module deliberately.

Two consequences of that shape worth knowing:

  * ``EmailMessage.category`` defaults to ``transactional``, so a send that
    somehow never names a category goes out rather than being held. That is
    the safe direction here: the cost of a nudge escaping the pause is a club
    getting one reminder it needn't have, while the cost of holding an
    untagged transactional email is somebody locked out of their account.
    The verification asserts that every EmailMessage in the tree names its
    category explicitly, so the default is a backstop, not the norm.

  * A settings row that can't be read leaves the nudges paused, because the
    only thing that read can affect is whether nudges go out.
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

# The only category a super admin can hold back. Everything else is
# unpausable BY CONSTRUCTION — see the module docstring. Do not add to this
# tuple without a deliberate decision: transactional email carries system
# operations (invites, password recovery, signup, portal sign-in) and must
# never be disabled.
PAUSABLE_CATEGORIES = (CATEGORY_AUTOMATED,)

# Named so the guarantee is greppable and testable, not just prose.
NEVER_PAUSABLE_CATEGORIES = (CATEGORY_TRANSACTIONAL, CATEGORY_CAMPAIGN)

# platform_settings key per pausable category.
SETTING_KEYS = {
    CATEGORY_AUTOMATED: "automated_emails_paused",
}

# Nudges are paused unless the settings row says otherwise, so the pause
# takes effect on deploy with no switch to find first.
DEFAULT_PAUSED = True

# The flag is read on the send path, which has no session of its own, so the
# lookup opens one and the answer is cached. Short enough that unpausing
# takes effect within half a minute without a restart; long enough that a
# campaign blasting a few thousand recipients doesn't hit the DB per message
# (though a campaign never reaches the lookup at all — see is_paused).
CACHE_TTL_SECONDS = 30

_cache: dict[str, bool] | None = None
_cache_at: float = 0.0
_lock = asyncio.Lock()


def invalidate_cache() -> None:
    """Drop the cached flag so the next send re-reads it. Called right after a
    super admin saves General Settings, so a pause or an unpause is visible
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

    A failure to read the flag leaves the nudges paused rather than raising.
    Nothing that carries a system operation depends on this call.
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
            logger.exception("email pause: could not read the flag, nudges stay paused")
            loaded = {c: DEFAULT_PAUSED for c in PAUSABLE_CATEGORIES}
        _cache = loaded
        _cache_at = time.monotonic()
        return loaded


async def is_paused(category: str | None) -> bool:
    """Whether a send in this category is currently held.

    Anything that is not ``automated`` returns False here immediately —
    before any setting is read, so no configuration, no missing settings row
    and no database failure can hold back a transactional or campaign send.
    """
    if category not in PAUSABLE_CATEGORIES:
        return False
    return (await paused_state()).get(category, DEFAULT_PAUSED)
