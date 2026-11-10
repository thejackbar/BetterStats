"""The club block list: who BetterCricket will not register or serve.

One module owns the rules so the registration steps, the login and the session
check cannot disagree. The table is ``registration_blocks`` (migration 386, DDL
in ``registration_block_ddl``). A row is never deleted; lifting stamps
``lifted_at``.

What each kind stops:

* ``ca_org_id`` / ``club_name`` / ``email`` / ``email_domain``: the public and
  Super Admin self-serve registration (``prepare``, ``verify-email/send`` and
  ``submit`` all call ``registration_refused``), so a refused person is stopped
  at the first step they reach and never gets as far as a club row.
* ``org_id``: a registered club. Its members (anyone but a super admin or sales
  user) cannot sign in, and a session already open is refused on its next
  request (``user_is_blocked``).

The person refused is never told why: ``REFUSAL_MESSAGE`` is the only text that
leaves this module, and ``reason`` stays in the table for staff.
"""
from __future__ import annotations

import logging
import re
import time
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

KINDS = ("org_id", "ca_org_id", "club_name", "email", "email_domain")

# What a refused person reads. Deliberately says nothing about the reason, the
# other party or which of the checks fired.
REFUSAL_MESSAGE = (
    "We can't set this account up at the moment. "
    "Please email support@bettersports.com.au."
)

# Words that differ between how a club writes its own name and how Cricket
# Australia lists it, so "Subiaco-Marist CC" and "Subiaco Marist Cricket Club"
# are one name.
_FILLER = {"cricket", "club", "cc", "the", "inc", "incorporated"}
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# "C.C." and "C. C." are "CC" written with stops; left alone they would survive as
# two stray one-letter words and a differently punctuated name would miss.
_DOTTED_CC = re.compile(r"\bc\s*\.\s*c\b\.?")


def normalise_name(name: str | None) -> str:
    """A club name reduced to what identifies it: lower case, punctuation as
    spaces, the filler words above dropped. Empty when nothing is left."""
    lowered = _DOTTED_CC.sub("cc", (name or "").lower())
    words = [w for w in _NON_ALNUM.sub(" ", lowered).split() if w not in _FILLER]
    return " ".join(words)


def normalise_value(kind: str, value: str | None) -> str:
    """The stored form of a block value, so a lookup and an insert agree."""
    v = (value or "").strip()
    if kind == "club_name":
        return normalise_name(v)
    if kind == "email":
        return v.lower()
    if kind == "email_domain":
        return v.lower().lstrip("@")
    if kind in ("org_id", "ca_org_id"):
        # Ids are compared as lower-case text, so a stray capital or the braces
        # a pasted GUID sometimes carries cannot make a block miss.
        return v.lower().strip("{}")
    raise ValueError(f"unknown block kind {kind!r}")


def _email_domain(email: str | None) -> str:
    e = (email or "").strip().lower()
    return e.rsplit("@", 1)[1] if "@" in e else ""


async def registration_refused(
    db: AsyncSession,
    *,
    ca_org_id=None,
    name: str | None = None,
    email: str | None = None,
) -> bool:
    """True when a registration for this club id, club name or email address is
    on the block list. Any one match refuses. Fails OPEN on a database error
    (logged), because refusing every registration over a read failure would be
    its own outage, and the same checks run again at /submit."""
    pairs: list[tuple[str, str]] = []
    if ca_org_id:
        pairs.append(("ca_org_id", normalise_value("ca_org_id", str(ca_org_id))))
    n = normalise_name(name)
    if n:
        pairs.append(("club_name", n))
    e = (email or "").strip().lower()
    if e:
        pairs.append(("email", e))
        d = _email_domain(e)
        if d:
            pairs.append(("email_domain", d))
    if not pairs:
        return False
    kinds = [k for k, _ in pairs]
    values = [v for _, v in pairs]
    try:
        row = (await db.execute(
            text(
                "SELECT 1 FROM registration_blocks b "
                "JOIN unnest(CAST(:kinds AS text[]), CAST(:vals AS text[])) AS q(kind, val) "
                "  ON q.kind = b.kind AND q.val = b.value "
                "WHERE b.lifted_at IS NULL LIMIT 1"
            ),
            {"kinds": kinds, "vals": values},
        )).first()
    except Exception:
        logger.exception("registration block check failed; allowing this step")
        try:
            await db.rollback()
        except Exception:
            pass
        return False
    return row is not None


# ─── Signed-in side: which users are in a blocked club ───────────────────────
# One small query, cached per process for a few seconds, so the check on every
# authenticated request costs nothing measurable. A block takes effect within
# CACHE_SECONDS on each worker; `invalidate_cache()` makes it immediate in the
# process that wrote it.
CACHE_SECONDS = 10.0
_cache: dict = {"at": 0.0, "ids": frozenset()}


def invalidate_cache() -> None:
    _cache["at"] = 0.0


async def _load_blocked_user_ids() -> frozenset:
    from app.models.db import async_session_maker

    # Its own session: this is a best-effort read and a failure here must not
    # roll back (and so expire) what the request's own session has loaded.
    async with async_session_maker() as s:
        rows = (await s.execute(text(
            "SELECT m.user_id FROM club_memberships m "
            "JOIN registration_blocks b ON b.kind = 'org_id' AND b.lifted_at IS NULL "
            "  AND b.value = lower(m.club_id::text) "
            "WHERE m.role NOT IN ('super_admin', 'sales')"
        ))).all()
    return frozenset(r[0] for r in rows)


async def blocked_user_ids() -> frozenset:
    now = time.monotonic()
    if now - _cache["at"] < CACHE_SECONDS:
        return _cache["ids"]
    try:
        _cache["ids"] = await _load_blocked_user_ids()
        _cache["at"] = now
    except Exception:
        # Keep the last good set; try again on the next request rather than
        # waiting out the window.
        logger.exception("blocked-user lookup failed; using the last known set")
    return _cache["ids"]


async def user_is_blocked(user_id) -> bool:
    if user_id is None:
        return False
    ids = await blocked_user_ids()
    if not ids:
        return False
    try:
        return (user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))) in ids
    except (ValueError, TypeError):
        return False
