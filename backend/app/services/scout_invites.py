"""BetterScout — pending teammate invites (Settings → People).

No mailer of BetterScout's own yet, so create_invite hands back the raw
token/link for the inviter to copy and send by hand — same "the record
exists, sending is the next increment" posture the club product's earliest
invite work took (see CLAUDE.md's "Super Admin New Club" note on
invite-not-password accounts) rather than blocking this on wiring email.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scout import ScoutInvite, ScoutUser
from app.services import scout_auth

INVITE_TTL_DAYS = 14
ROLES = {"owner", "viewer"}


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


async def list_people(session: AsyncSession, scout_org_id: str) -> dict:
    users = (await session.execute(
        select(ScoutUser).where(ScoutUser.scout_org_id == scout_org_id).order_by(ScoutUser.created_at)
    )).scalars().all()
    invites = (await session.execute(
        select(ScoutInvite)
        .where(ScoutInvite.scout_org_id == scout_org_id, ScoutInvite.accepted_at.is_(None))
        .order_by(ScoutInvite.created_at)
    )).scalars().all()
    now = datetime.now(timezone.utc)
    return {
        "users": [
            {"id": str(u.id), "display_name": u.display_name, "username": u.username, "email": u.email, "role": u.role}
            for u in users
        ],
        "invites": [
            {
                "id": str(i.id), "email": i.email, "role": i.role,
                "invited_at": i.created_at.isoformat(),
                "expired": _aware(i.expires_at) < now,
            }
            for i in invites
        ],
    }


async def create_invite(
    session: AsyncSession, scout_org_id: str, email: str, role: str, invited_by_user_id: str,
) -> dict:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("A valid email is required.")
    if role not in ROLES:
        raise ValueError("Unknown role.")
    existing_user = (await session.execute(
        select(ScoutUser).where(ScoutUser.email == email, ScoutUser.scout_org_id == scout_org_id)
    )).scalar_one_or_none()
    if existing_user:
        raise ValueError("Already a member of this org.")

    invite = (await session.execute(
        select(ScoutInvite).where(
            ScoutInvite.scout_org_id == scout_org_id, ScoutInvite.email == email, ScoutInvite.accepted_at.is_(None),
        )
    )).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if invite is None:
        invite = ScoutInvite(
            scout_org_id=scout_org_id, email=email, role=role, invited_by=invited_by_user_id,
            token=secrets.token_urlsafe(24), expires_at=now + timedelta(days=INVITE_TTL_DAYS),
        )
        session.add(invite)
    else:
        # Re-inviting the same pending address resends: fresh token +
        # expiry, same row — the unique partial index on
        # (org, email) WHERE accepted_at IS NULL is what makes "invite" and
        # "resend" the same call from the caller's side.
        invite.role = role
        invite.token = secrets.token_urlsafe(24)
        invite.expires_at = now + timedelta(days=INVITE_TTL_DAYS)
    await session.commit()
    return {"id": str(invite.id), "token": invite.token, "email": invite.email, "role": invite.role}


async def revoke_invite(session: AsyncSession, scout_org_id: str, invite_id: str) -> None:
    invite = await session.get(ScoutInvite, invite_id)
    if not invite or str(invite.scout_org_id) != str(scout_org_id):
        raise ValueError("Invite not found.")
    await session.delete(invite)
    await session.commit()


async def accept_invite(
    session: AsyncSession, token: str, username: str, password: str, display_name: str | None = None,
) -> dict:
    invite = (await session.execute(select(ScoutInvite).where(ScoutInvite.token == token))).scalar_one_or_none()
    if not invite:
        raise ValueError("Invite not found.")
    if invite.accepted_at is not None:
        raise ValueError("This invite has already been used.")
    if _aware(invite.expires_at) < datetime.now(timezone.utc):
        raise ValueError("This invite has expired — ask for a new one.")
    username = (username or "").strip().lower()
    if not username:
        raise ValueError("Username is required.")
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    taken = (await session.execute(select(ScoutUser).where(ScoutUser.username == username))).scalar_one_or_none()
    if taken:
        raise ValueError("That username is already taken.")
    user = ScoutUser(
        scout_org_id=invite.scout_org_id, username=username, email=invite.email,
        password_hash=scout_auth.hash_password(password), display_name=display_name or invite.email,
        role=invite.role,
    )
    session.add(user)
    invite.accepted_at = datetime.now(timezone.utc)
    await session.commit()
    return {"id": str(user.id), "username": user.username}
