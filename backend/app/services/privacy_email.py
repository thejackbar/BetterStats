"""No email to a person who asked to be removed (migration 316).

A removal request is not only about the public site: the club's emails (BetterComms
campaigns, fee notices, availability and selection mail, votes, notifications)
must not reach the person either. This is the one place that knows which
addresses those are.

THE ADDRESSES
-------------
Derived on read from the person's records, never from a stored copy, so an
address added later (a new email on their fee record, a contact re-created from
the Directory) is covered without anyone re-running a script:

  * the email on every ``players`` row marked ``privacy_hidden_at``;
  * the email on a ``fee_members`` row linked to one of those players;
  * a ``comms_contacts`` row linked to one of those players or members;
  * the sign-in email of a claimed account (``players.user_id``);
  * every address on the global suppression list recorded by a removal
    (``email_suppressions.source = 'privacy_request'``), which also covers an
    address that has since been edited off the record.

Family and guardian addresses are other people's and are NOT included.

WHERE IT BITES (three layers, so one missed caller is not a leak)
-----------------------------------------------------------------
  1. ``email_service.get_email_provider()`` returns a provider that refuses the
     recipient. Every send in the app goes through it, whatever the module.
  2. ``email_suppression.deliverable()``, the gate the per-club senders ask first.
  3. ``comms_segments.sendable_where``, so an audience, a count and a "reachable"
     figure never include them.

Cached for 30 seconds per process. A failed lookup keeps the last answer; if there
has never been one it lets the send through and logs, because refusing every
email on a transient database error is a worse failure than the one it prevents.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from sqlalchemy import text

log = logging.getLogger(__name__)

CACHE_SECONDS = 30
SOURCE = "privacy_request"

_cache: dict = {"at": 0.0, "addresses": None}


def _norm(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def forget() -> None:
    _cache.update(at=0.0, addresses=None)


_ADDRESS_SQL = """
SELECT LOWER(TRIM(e)) FROM (
    SELECT p.email AS e FROM players p WHERE p.privacy_hidden_at IS NOT NULL
    UNION ALL
    SELECT fm.email FROM fee_members fm
      JOIN players p ON p.id = fm.player_id
     WHERE p.privacy_hidden_at IS NOT NULL
    UNION ALL
    SELECT cc.email FROM comms_contacts cc
      JOIN players p ON p.id = cc.player_id
     WHERE p.privacy_hidden_at IS NOT NULL
    UNION ALL
    SELECT cc.email FROM comms_contacts cc
      JOIN fee_members fm ON fm.id = cc.member_id
      JOIN players p ON p.id = fm.player_id
     WHERE p.privacy_hidden_at IS NOT NULL
    UNION ALL
    SELECT u.email FROM users u
      JOIN players p ON p.user_id = u.id
     WHERE p.privacy_hidden_at IS NOT NULL
    UNION ALL
    SELECT s.email FROM email_suppressions s WHERE s.source = 'privacy_request'
) t WHERE e IS NOT NULL AND TRIM(e) <> ''
"""


async def addresses_for_players(session, player_ids) -> set[str]:
    """Every address on record for these players (used when a removal is recorded)."""
    ids = [str(p) for p in player_ids]
    if not ids:
        return set()
    rows = (await session.execute(text("""
        SELECT LOWER(TRIM(e)) FROM (
            SELECT p.email AS e FROM players p WHERE p.id::text = ANY(:ids)
            UNION ALL
            SELECT fm.email FROM fee_members fm WHERE fm.player_id::text = ANY(:ids)
            UNION ALL
            SELECT cc.email FROM comms_contacts cc WHERE cc.player_id::text = ANY(:ids)
            UNION ALL
            SELECT cc.email FROM comms_contacts cc
              JOIN fee_members fm ON fm.id = cc.member_id
             WHERE fm.player_id::text = ANY(:ids)
            UNION ALL
            SELECT u.email FROM users u JOIN players p ON p.user_id = u.id WHERE p.id::text = ANY(:ids)
        ) t WHERE e IS NOT NULL AND TRIM(e) <> ''
    """), {"ids": ids})).fetchall()
    return {r[0] for r in rows}


async def removed_addresses(session=None) -> set[str]:
    """All addresses that must not be emailed. Never raises."""
    now = time.monotonic()
    if _cache["addresses"] is not None and now - _cache["at"] < CACHE_SECONDS:
        return _cache["addresses"]
    try:
        if session is not None:
            rows = (await session.execute(text(_ADDRESS_SQL))).fetchall()
        else:
            from app.models.db import async_session_maker
            async with async_session_maker() as s:
                rows = (await s.execute(text(_ADDRESS_SQL))).fetchall()
        _cache.update(at=now, addresses={r[0] for r in rows})
    except Exception:
        log.exception("privacy email: could not load the removed-people addresses")
        _cache["at"] = now
        if _cache["addresses"] is None:
            _cache["addresses"] = set()
    return _cache["addresses"]


async def is_removed_address(email: Optional[str], session=None) -> bool:
    e = _norm(email)
    return bool(e) and e in await removed_addresses(session)
