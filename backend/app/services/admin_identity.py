"""Primary Club Admin identity rules — one set, shared by every flow that
creates a club's first admin account.

Two flows create that account today and they must agree on what a valid one
looks like, or a club registered one way ends up with an account the other way
would have rejected:

  * self-serve trial registration (routers/self_serve_trial.py, and its public
    mirror routers/public_self_serve.py) — the club's own admin fills this in;
  * Super Admin → All Clubs → New Club (routers/club_admin.py::create_club) —
    a staff member fills it in on the club's behalf.

The rules themselves are unchanged from the self-serve originals (which in turn
reused POST /super/users' username rules): lowercase 3-32 char unique username,
a format-checked email that isn't already a BetterCricket account, and an AU or
international mobile. The one difference between callers is whether the mobile
is mandatory — the club's own admin is asked for one, a super admin creating a
club on someone's behalf often doesn't have it yet — hence ``require_mobile``.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# AU mobile: 04xxxxxxxx, +614xxxxxxxx or 614xxxxxxxx, spaces/dashes ignored.
AU_MOBILE_RE = re.compile(r"^(\+?61|0)4\d{8}$")
# Generic international fallback: a leading + and 8-15 digits — the codebase
# has no phone-validation library anywhere (Player.phone is stored as free text,
# see routers/availability.py's phone_last4), so this is a light sanity check,
# not a claim of full E.164 validation.
INTL_MOBILE_RE = re.compile(r"^\+\d{8,15}$")

EMAIL_TAKEN_MESSAGE = (
    "This email already belongs to a BetterCricket account. Registration "
    "doesn't yet support adding an existing admin to a second club — email "
    "support@bettersports.com.au for help."
)


def mobile_valid(raw: str) -> bool:
    compact = re.sub(r"[\s-]", "", raw or "")
    return bool(AU_MOBILE_RE.match(compact) or INTL_MOBILE_RE.match(compact))


async def validate_admin_fields(
    db: AsyncSession,
    *,
    first_name: str = "",
    last_name: str = "",
    display_name: str = "",
    username: str = "",
    email: str = "",
    mobile_number: str = "",
    require_mobile: bool = True,
) -> dict:
    """Field-name → error message for the primary admin's details. An empty
    dict means every field passed.

    Email is format-checked, then checked against existing users and BLOCKED if
    already taken (see docs/self-serve-trial-onboarding-plan.md Decision 14).
    The source document wanted this to link an existing admin to a second club
    instead — but club_memberships.uq_membership_one_per_user (a user can have
    at most one membership, ever) and the global uniqueness of users.email make
    that a schema change, not a form feature. This blocks rather than silently
    allowing a broken multi-club state, and does not reveal which club(s) the
    existing account holds."""
    errors: dict[str, str] = {}

    if not (first_name or "").strip():
        errors["first_name"] = "First name is required"
    if not (last_name or "").strip():
        errors["last_name"] = "Last name is required"
    if not (display_name or "").strip():
        errors["display_name"] = "Preferred display name is required"

    uname = (username or "").strip().lower()
    if not uname or len(uname) < 3 or len(uname) > 32:
        errors["username"] = "Username must be 3-32 characters"
    else:
        existing = await db.execute(select(User).where(User.username == uname))
        if existing.scalars().first():
            errors["username"] = "Username already taken"

    mail = (email or "").strip().lower()
    if not mail or not EMAIL_RE.match(mail):
        errors["email"] = "Enter a valid email address"
    else:
        # users.email is no longer DB-unique (migration 145 — club-user emails
        # are format-validated only), so this can't assume at most one match.
        existing_user = await db.execute(select(User).where(User.email == mail))
        if existing_user.scalars().first():
            errors["email"] = EMAIL_TAKEN_MESSAGE

    mobile = (mobile_number or "").strip()
    if not mobile:
        if require_mobile:
            errors["mobile_number"] = (
                "Enter a valid Australian mobile number, or an international "
                "number starting with +"
            )
    elif not mobile_valid(mobile):
        errors["mobile_number"] = (
            "Enter a valid Australian mobile number, or an international "
            "number starting with +"
        )

    return errors
