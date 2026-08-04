"""AFL Users — club-scoped member management + platform-wide Better HQ user
management. Ported near-verbatim from cricket's club_admin.py: this is
already 100% sport-agnostic (User/ClubMembership/capabilities), and reuses
the already-shared invite-accept flow in routers/auth.py untouched.
"""
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import (
    ALL_CAPABILITIES, MANAGE_USERS, effective_capabilities, require_cap,
)
from app.config.settings import settings
from app.models.db import ClubMembership, Organisation, User, get_db
from app.routers.auth import _hash_password, get_current_club, get_current_user, require_super_admin
from app.services.audit_log import log_activity
from app.services.password_policy import password_errors
from app.services.user_invite import send_invite_email, send_password_reset_email

router = APIRouter(tags=["afl-users"])

_INVITE_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MOBILE_STRIP_RE = re.compile(r"[\s\-()]")
_MOBILE_DIGITS_RE = re.compile(r"^\+?\d{7,15}$")
_INVITE_TOKEN_TTL_DAYS = 7
_PASSWORD_RESET_TOKEN_TTL_HOURS = 24


def _clean_mobile(raw: Optional[str]) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None
    if not _MOBILE_DIGITS_RE.match(_MOBILE_STRIP_RE.sub("", value)):
        raise HTTPException(400, "That doesn't look like a valid mobile number")
    return value


# ─── Club-scoped user management ─────────────────────────────────────────────

@router.get("/club-admin/users")
async def list_club_users(
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(text("""
        SELECT u.id, u.username, u.display_name, u.email, u.mobile_number, u.last_login_at,
               cm.role, cm.capabilities
        FROM club_memberships cm JOIN users u ON u.id = cm.user_id
        WHERE cm.club_id = :org
        ORDER BY cm.role, COALESCE(u.display_name, u.username)
    """), {"org": str(club.id)})
    out = []
    for r in rows.mappings().all():
        out.append({
            "id": str(r["id"]), "username": r["username"], "display_name": r["display_name"],
            "email": r["email"], "mobile_number": r["mobile_number"],
            "last_login_at": r["last_login_at"].isoformat() if r["last_login_at"] else None,
            "role": r["role"], "capabilities": r["capabilities"] or [],
            "effective_capabilities": effective_capabilities(r["role"], r["capabilities"]),
        })
    return out


@router.get("/club-admin/users/capabilities")
async def list_capabilities(_user: User = Depends(require_cap(MANAGE_USERS))):
    return {"capabilities": list(ALL_CAPABILITIES)}


class ClubUserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None
    email: str
    mobile_number: Optional[str] = None


@router.post("/club-admin/users")
async def create_club_user(
    data: ClubUserCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Invite a colleague as a full club admin — no password is set here; the
    account is created with password_hash NULL plus an invite token, and an
    email links to /login?invite=<token> where they set their own password."""
    username = (data.username or "").strip().lower()
    email = (data.email or "").strip().lower()
    if not username:
        raise HTTPException(400, "Username is required")
    if not email or not _INVITE_EMAIL_RE.match(email):
        raise HTTPException(400, "A valid email address is required to invite the new admin")

    existing = await db.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username})
    if existing.first():
        raise HTTPException(409, "Username already in use")

    new_user_id = uuid.uuid4()
    invite_token = secrets.token_urlsafe(32)
    invite_expires = datetime.now(timezone.utc) + timedelta(days=_INVITE_TOKEN_TTL_DAYS)
    mobile_number = _clean_mobile(data.mobile_number)
    await db.execute(text(
        "INSERT INTO users (id, username, display_name, email, mobile_number, "
        "password_hash, invite_token, invite_token_expires_at) "
        "VALUES (:id, :u, :d, :e, :m, NULL, :tok, :exp)"
    ), {"id": str(new_user_id), "u": username, "d": data.display_name, "e": email,
        "m": mobile_number, "tok": invite_token, "exp": invite_expires})
    await db.execute(text(
        "INSERT INTO club_memberships (id, club_id, user_id, role, capabilities) "
        "VALUES (:id, :club, :uid, 'club_admin', CAST('[]' AS JSONB))"
    ), {"id": str(uuid.uuid4()), "club": str(club.id), "uid": str(new_user_id)})

    await log_activity(db, org_id=club.id, user_id=current_user.id,
                       action="create_club_user", target_type="user", target_id=str(new_user_id),
                       details={"username": username, "email": email})
    await db.commit()

    invite_link = f"{settings.public_base_url}/login?invite={invite_token}"
    background_tasks.add_task(send_invite_email, email=email, display_name=data.display_name or username,
                              club_name=club.name, link=invite_link)
    return {"id": str(new_user_id), "username": username, "role": "club_admin", "invited": True}


class ClubUserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    mobile_number: Optional[str] = None
    password: Optional[str] = None
    confirm_password: Optional[str] = None


@router.patch("/club-admin/users/{user_id}")
async def update_club_user(
    user_id: str,
    data: ClubUserUpdate,
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    row = await db.execute(text(
        "SELECT u.id FROM club_memberships cm JOIN users u ON u.id = cm.user_id "
        "WHERE u.id = :uid AND cm.club_id = :club"
    ), {"uid": user_id, "club": str(club.id)})
    if not row.first():
        raise HTTPException(404, "User not found in this club")

    changes = {}
    if data.display_name is not None:
        await db.execute(text("UPDATE users SET display_name = :d WHERE id = :id"), {"d": data.display_name, "id": user_id})
        changes["display_name"] = True
    if data.email is not None:
        email = (data.email or "").strip().lower()
        if not email or not _INVITE_EMAIL_RE.match(email):
            raise HTTPException(400, "A valid email address is required")
        await db.execute(text("UPDATE users SET email = :e WHERE id = :id"), {"e": email, "id": user_id})
        changes["email"] = True
    if data.mobile_number is not None:
        mobile_number = _clean_mobile(data.mobile_number)
        await db.execute(text("UPDATE users SET mobile_number = :m WHERE id = :id"), {"m": mobile_number, "id": user_id})
        changes["mobile_number"] = True
    if data.password is not None:
        errors = password_errors(data.password, data.confirm_password or "")
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        await db.execute(text("UPDATE users SET password_hash = :h WHERE id = :id"),
                         {"h": _hash_password(data.password), "id": user_id})
        changes["password"] = True

    await log_activity(db, org_id=club.id, user_id=current_user.id,
                       action="update_club_user", target_type="user", target_id=user_id,
                       details={"changes": list(changes.keys())})
    await db.commit()
    return {"status": "ok", **changes}


@router.post("/club-admin/users/{user_id}/send-password-reset")
async def send_password_reset_link(
    user_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    row = await db.execute(text(
        "SELECT u.id, u.email, u.display_name, u.username FROM club_memberships cm "
        "JOIN users u ON u.id = cm.user_id WHERE u.id = :uid AND cm.club_id = :club"
    ), {"uid": user_id, "club": str(club.id)})
    target = row.mappings().first()
    if not target:
        raise HTTPException(404, "User not found in this club")
    if not target["email"]:
        raise HTTPException(400, "This user has no email address on file to send a reset link to")

    reset_token = secrets.token_urlsafe(32)
    reset_expires = datetime.now(timezone.utc) + timedelta(hours=_PASSWORD_RESET_TOKEN_TTL_HOURS)
    await db.execute(text(
        "UPDATE users SET password_reset_token = :tok, password_reset_token_expires_at = :exp WHERE id = :id"
    ), {"tok": reset_token, "exp": reset_expires, "id": user_id})
    await log_activity(db, org_id=club.id, user_id=current_user.id,
                       action="send_password_reset_link", target_type="user", target_id=user_id)
    await db.commit()

    reset_link = f"{settings.public_base_url}/login?reset={reset_token}"
    background_tasks.add_task(send_password_reset_email, email=target["email"],
                              display_name=target["display_name"] or target["username"],
                              club_name=club.name, link=reset_link)
    return {"status": "sent"}


@router.delete("/club-admin/users/{user_id}")
async def remove_club_user(
    user_id: str,
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if str(current_user.id) == user_id:
        raise HTTPException(400, "Can't remove yourself")

    row = await db.execute(text(
        "DELETE FROM club_memberships WHERE user_id = :uid AND club_id = :club RETURNING id"
    ), {"uid": user_id, "club": str(club.id)})
    if not row.first():
        raise HTTPException(404, "User not found in this club")

    # Free the now-orphaned account's username/credentials for reuse, same
    # reasoning as cricket: club_memberships.uq_membership_one_per_user means
    # nothing else can ever attach a new membership to this row.
    await db.execute(text(
        "UPDATE users SET username = NULL, password_hash = NULL, "
        "invite_token = NULL, invite_token_expires_at = NULL, "
        "password_reset_token = NULL, password_reset_token_expires_at = NULL WHERE id = :uid"
    ), {"uid": user_id})

    await log_activity(db, org_id=club.id, user_id=current_user.id,
                       action="remove_club_user", target_type="user", target_id=user_id)
    await db.commit()
    return {"status": "removed"}


# ─── Platform-wide (Better HQ) user management ───────────────────────────────

@router.get("/club-admin/super/users")
async def list_users(_: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User, ClubMembership, Organisation)
        .join(ClubMembership, ClubMembership.user_id == User.id, isouter=True)
        .join(Organisation, Organisation.id == ClubMembership.club_id, isouter=True)
        .order_by(User.username)
    )
    return [
        {
            "id": str(r.User.id), "username": r.User.username, "display_name": r.User.display_name,
            "email": r.User.email, "mobile_number": r.User.mobile_number,
            "role": r.ClubMembership.role if r.ClubMembership else None,
            "club_name": r.Organisation.name if r.Organisation else None,
            "club_id": str(r.ClubMembership.club_id) if r.ClubMembership else None,
            "is_primary_admin": bool(r.ClubMembership.is_primary_admin) if r.ClubMembership else False,
            "last_login_at": r.User.last_login_at.isoformat() if r.User.last_login_at else None,
            "locked": r.User.locked_until is not None,
        }
        for r in result.all()
    ]


async def _super_admin_count(db: AsyncSession) -> int:
    res = await db.execute(select(func.count()).select_from(ClubMembership).where(ClubMembership.role == "super_admin"))
    return res.scalar() or 0


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    club_id: str
    role: str = "club_admin"


@router.post("/club-admin/super/users", status_code=201)
async def create_user(
    data: UserCreate, _: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db),
):
    """Create a Better HQ account directly (username + password set here and
    handed to the person, not an email invite — mirrors cricket's own
    super-admin create-user flow) and assign it a club + role in one step."""
    username = data.username.lower().strip()
    if not username or len(username) < 3 or len(username) > 32:
        raise HTTPException(422, "Username must be 3-32 characters")
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Username already taken")
    if len(data.password) < 10:
        raise HTTPException(422, "Password must be at least 10 characters")
    club = await db.get(Organisation, uuid.UUID(data.club_id))
    if not club:
        raise HTTPException(404, "Club not found")

    user = User(username=username, password_hash=_hash_password(data.password), display_name=data.display_name)
    db.add(user)
    await db.flush()

    membership = ClubMembership(
        club_id=club.id, user_id=user.id,
        role=data.role if data.role in ("super_admin", "club_admin") else "club_admin",
    )
    db.add(membership)
    await db.flush()
    if membership.role == "club_admin":
        from app.services.memberships import ensure_primary_admin
        await ensure_primary_admin(db, club.id)

    await db.commit()
    return {"id": str(user.id), "username": user.username, "club_id": data.club_id, "role": membership.role}


class UserUpdate(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    mobile_number: Optional[str] = None
    role: Optional[str] = None
    club_id: Optional[str] = None


@router.patch("/club-admin/super/users/{user_id}")
async def patch_user(
    user_id: str, data: UserUpdate,
    current_user: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    fields = data.model_dump(exclude_unset=True)
    if "username" in fields:
        username = (fields["username"] or "").lower().strip()
        if len(username) < 3 or len(username) > 32:
            raise HTTPException(status_code=422, detail="Username must be 3-32 characters")
        clash = await db.execute(select(User).where(User.username == username, User.id != user.id))
        if clash.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Username already taken")
        user.username = username
    if "display_name" in fields:
        user.display_name = (fields["display_name"] or "").strip() or None
    if "email" in fields:
        email = (fields["email"] or "").strip().lower()
        if email and not _INVITE_EMAIL_RE.match(email):
            raise HTTPException(status_code=422, detail="That doesn't look like a valid email address")
        user.email = email or None
    if "mobile_number" in fields:
        user.mobile_number = _clean_mobile(fields["mobile_number"])

    membership_res = await db.execute(select(ClubMembership).where(ClubMembership.user_id == user.id))
    membership = membership_res.scalar_one_or_none()

    new_role = fields.get("role")
    if new_role is not None and new_role not in ("super_admin", "club_admin"):
        raise HTTPException(status_code=422, detail="Role must be super_admin or club_admin")
    if (new_role == "club_admin" and membership and membership.role == "super_admin"
            and await _super_admin_count(db) <= 1):
        raise HTTPException(status_code=400, detail="Cannot demote the last super admin")

    if "club_id" in fields:
        club = await db.get(Organisation, uuid.UUID(fields["club_id"]))
        if not club:
            raise HTTPException(status_code=404, detail="Club not found")
        if membership:
            membership.club_id = club.id
        else:
            membership = ClubMembership(club_id=club.id, user_id=user.id, role=new_role or "club_admin")
            db.add(membership)

    if new_role is not None and membership:
        membership.role = new_role

    await db.commit()
    return {
        "id": str(user.id), "username": user.username, "display_name": user.display_name,
        "email": user.email, "mobile_number": user.mobile_number,
        "role": membership.role if membership else None,
        "club_id": str(membership.club_id) if membership else None,
    }


@router.delete("/club-admin/super/users/{user_id}")
async def delete_user(user_id: str, current_user: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    membership_res = await db.execute(select(ClubMembership).where(ClubMembership.user_id == user.id))
    membership = membership_res.scalar_one_or_none()
    if membership and membership.role == "super_admin" and await _super_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last super admin")

    await db.delete(user)
    await db.commit()
    return {"status": "deleted", "id": user_id}


class PasswordReset(BaseModel):
    new_password: str


@router.post("/club-admin/super/users/{user_id}/reset-password")
async def reset_password(
    user_id: str, data: PasswordReset,
    _: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db),
):
    if len(data.new_password) < 10:
        raise HTTPException(status_code=422, detail="Password must be at least 10 characters")
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = _hash_password(data.new_password)
    user.failed_login_count = 0
    user.locked_until = None
    await db.commit()
    return {"status": "password_reset"}
