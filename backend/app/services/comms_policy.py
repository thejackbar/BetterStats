"""BetterComms message categories + the suppression policy.

Every send has a category, and the category decides what is allowed to suppress
it. This is how transactional mail stays separate from campaigns without a second
send path (see docs/bettercomms-architecture.md).

  transactional — password reset / invite / verify / 2FA / receipt. Only a hard
                  bounce stops it (the mailbox is undeliverable). Must keep flowing.
  operational   — selection / availability / fee reminders. Club ops to members.
                  Stopped by hard bounce + complaint; respects a per-club opt-out.
  news          — newsletters / announcements. Stopped by everything.
  marketing     — promotional + BetterCricket Clubs Directory outreach. Stopped by
                  everything.

Campaigns are ``news`` or ``marketing``.
"""
from __future__ import annotations

TRANSACTIONAL = "transactional"
OPERATIONAL = "operational"
NEWS = "news"
MARKETING = "marketing"

CATEGORIES = (TRANSACTIONAL, OPERATIONAL, NEWS, MARKETING)


def normalise_category(category: str | None) -> str:
    c = (category or "").strip().lower()
    return c if c in CATEGORIES else NEWS


# A hard bounce means the mailbox is dead — it blocks every category.
def blocks_hard_bounce(category: str) -> bool:
    return True


# A complaint blocks everything except essential transactional mail.
def blocks_on_complaint(category: str) -> bool:
    return normalise_category(category) != TRANSACTIONAL


# A per-club unsubscribe / per-person preference opt-out blocks anything that
# isn't transactional. Operational respects an explicit opt-out too, by design.
def blocks_on_optout(category: str) -> bool:
    return normalise_category(category) != TRANSACTIONAL


def preference_allows(preferences: dict | None, category: str) -> bool:
    """A per-person preference map (category → bool). Absent key ⇒ opted in;
    transactional is never gated."""
    cat = normalise_category(category)
    if cat == TRANSACTIONAL:
        return True
    if not isinstance(preferences, dict):
        return True
    val = preferences.get(cat)
    return True if val is None else bool(val)
