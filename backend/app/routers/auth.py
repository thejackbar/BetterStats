from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
import bcrypt as _bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
import uuid

from app.models.db import User, ClubMembership, Organisation, get_db
from app.config.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def _hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

COOKIE_NAME = "bs_session"
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def create_session_token(user_id: str) -> str:
    """Mint a session JWT for a user id — no password check, so callers must
    already have established the right to log this user in (a verified
    password, or an equivalently-authorized flow like self-serve trial
    registration, routers/self_serve_trial.py). Not module-private: this is
    the one real "establish a session" primitive, reused wherever a user
    needs logging in without going through the login form."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.secret_key, algorithm=settings.algorithm)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def get_optional_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    """Like get_current_user, but returns None instead of 401 when there's no
    valid session. For public endpoints that show more to a signed-in club admin
    (e.g. hidden grades stay visible in their own admin-side views)."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        if not user_id:
            return None
    except JWTError:
        return None
    try:
        return await db.get(User, uuid.UUID(user_id))
    except (ValueError, TypeError):
        return None


async def user_can_view_org_private(db: AsyncSession, user: User | None, org_id) -> bool:
    """True if this user may see a club's non-public data (its own admins + Better
    staff). Used to decide whether to filter hidden grades from a public surface."""
    if user is None:
        return False
    res = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == user.id)
    )
    membership = res.scalar_one_or_none()
    if not membership:
        return False
    if membership.role == "super_admin":
        return True
    eff = _effective_club_id(membership, user)
    return eff is not None and str(eff) == str(org_id)


async def require_super_admin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    result = await db.execute(
        select(ClubMembership).where(
            ClubMembership.user_id == current_user.id,
            ClubMembership.role == "super_admin",
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return current_user


async def require_self_serve_registration_enabled(db: AsyncSession = Depends(get_db)) -> None:
    """Route dependency for the internal self-serve club trial registration flow
    (see docs/self-serve-trial-onboarding-plan.md). 404s, not 403s, when the
    ``self_serve_registration_enabled`` platform flag is off, so a disabled feature
    reads as "doesn't exist" rather than revealing a gated feature. This is a
    feature-flag check, not an authorization check — every route it guards must
    also depend on ``require_super_admin`` (or, once this flow goes public, whatever
    the public-facing auth model turns out to be)."""
    from app.services import platform_settings as ps
    if not await ps.get_self_serve_registration_enabled(db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


async def require_onboarding_wizard_enabled(db: AsyncSession = Depends(get_db)) -> None:
    """Route dependency for the club onboarding wizard. 404s when the
    ``onboarding_wizard_enabled`` platform flag is off. See
    ``require_self_serve_registration_enabled`` for the rationale."""
    from app.services import platform_settings as ps
    if not await ps.get_onboarding_wizard_enabled(db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


def _effective_club_id(membership: ClubMembership | None, user: User) -> uuid.UUID | None:
    """The club a request is scoped to.

    Super admins are Better staff who manage every club, so they can "act as"
    any club via ``User.active_club_id`` (set through ``POST /auth/switch-club``).
    Everyone else is pinned to the single club on their membership — the override
    is ignored for non-super roles, so it can never widen a club admin's reach.
    """
    if membership is None:
        return None
    if membership.role == "super_admin" and getattr(user, "active_club_id", None):
        return user.active_club_id
    return membership.club_id


async def get_current_club(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organisation:
    result = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No club membership found")
    eff_id = _effective_club_id(membership, current_user)
    # Eager-load per-module subscriptions so the entitlement gate enforces
    # read-time trial expiry exactly (see app/auth/modules.py).
    _opts = [selectinload(Organisation.module_subscriptions)]
    club = await db.get(Organisation, eff_id, options=_opts) if eff_id else None
    # A dangling active_club_id (e.g. the acted-as club was deleted) falls back
    # to the staff member's home membership club rather than 403-ing them out.
    if club is None and eff_id != membership.club_id:
        club = await db.get(Organisation, membership.club_id, options=_opts)
    if not club:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Club not found")
    return club


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    username: str | None
    display_name: str | None
    role: str | None = None

    class Config:
        from_attributes = True


@router.post("/login")
async def login(data: LoginRequest, response: Response, request: Request, db: AsyncSession = Depends(get_db)):
    from app.services import login_audit

    username = (data.username or "").lower()
    ip = login_audit.client_ip(request)
    user_agent = request.headers.get("user-agent")
    country = request.headers.get("cf-ipcountry")

    async def _log(success: bool, reason: str | None = None,
                   user_id=None, org_id=None) -> None:
        await login_audit.record_login_attempt(
            username=username, success=success, failure_reason=reason,
            user_id=user_id, org_id=org_id, ip=ip, user_agent=user_agent,
            country=country,
        )

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    # Generic error — do not leak which field was wrong
    if not user or not user.password_hash:
        await _log(False, login_audit.REASON_UNKNOWN_USER)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    now = datetime.now(timezone.utc)

    # Check lockout
    if user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
        await _log(False, login_audit.REASON_LOCKED, user_id=user.id)
        raise HTTPException(status_code=429, detail="Account temporarily locked. Try again later.")

    if not _verify_password(data.password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        await db.commit()
        await _log(False, login_audit.REASON_BAD_PASSWORD, user_id=user.id)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Check user has an active club membership (super_admin bypasses the is_active check)
    membership_res = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == user.id)
    )
    membership = membership_res.scalar_one_or_none()
    if not membership:
        await _log(False, login_audit.REASON_NO_MEMBERSHIP, user_id=user.id)
        raise HTTPException(status_code=403, detail="No club membership found")

    club = await db.get(Organisation, membership.club_id)
    if membership.role != "super_admin":
        if not club or not club.is_active:
            await _log(False, login_audit.REASON_CLUB_INACTIVE,
                       user_id=user.id, org_id=membership.club_id)
            raise HTTPException(status_code=403, detail="Club is not active")

    # Success — reset counters, update last login
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    await db.commit()
    await _log(True, user_id=user.id, org_id=membership.club_id)

    token = create_session_token(str(user.id))
    set_session_cookie(response, token)

    return await _build_me(user, db)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "logged_out"}


class InviteAcceptRequest(BaseModel):
    password: str
    confirm_password: str


@router.get("/invite/{token}")
async def get_invite(token: str, db: AsyncSession = Depends(get_db)):
    """Public: resolve a club-user invite token (routers/club_admin.py's
    "Invite admin" — create_club_user) to the invited person's basic
    identity, so the accept-invite step on the login page can greet them by
    name before asking for a password. Generic "invalid or expired" on any
    failure — doesn't leak whether a token ever existed."""
    result = await db.execute(select(User).where(User.invite_token == token))
    user = result.scalar_one_or_none()
    if user is None or user.password_hash is not None:
        raise HTTPException(status_code=404, detail="This invite link is invalid or has already been used")
    expires = user.invite_token_expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            raise HTTPException(
                status_code=410,
                detail="This invite link has expired — ask an admin at your club to invite you again",
            )

    membership_res = await db.execute(select(ClubMembership).where(ClubMembership.user_id == user.id))
    membership = membership_res.scalar_one_or_none()
    club = await db.get(Organisation, membership.club_id) if membership else None
    return {
        "username": user.username,
        "display_name": user.display_name,
        "club_name": club.name if club else None,
    }


@router.post("/invite/{token}/accept")
async def accept_invite(token: str, data: InviteAcceptRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Set the invited user's own password (the "first login must set a
    password" step) and log them in immediately — same session-minting
    primitive login() itself uses. Same password rule as self-serve trial
    registration (services/password_policy.py), so the two flows can never
    silently diverge."""
    from app.services import password_policy

    result = await db.execute(select(User).where(User.invite_token == token))
    user = result.scalar_one_or_none()
    if user is None or user.password_hash is not None:
        raise HTTPException(status_code=404, detail="This invite link is invalid or has already been used")
    expires = user.invite_token_expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            raise HTTPException(
                status_code=410,
                detail="This invite link has expired — ask an admin at your club to invite you again",
            )

    errors = password_policy.password_errors(data.password, data.confirm_password)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    user.password_hash = _hash_password(data.password)
    user.invite_token = None
    user.invite_token_expires_at = None
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    token_value = create_session_token(str(user.id))
    set_session_cookie(response, token_value)
    return await _build_me(user, db)


class ResetPasswordAcceptRequest(BaseModel):
    password: str
    confirm_password: str


@router.get("/reset-password/{token}")
async def get_password_reset(token: str, db: AsyncSession = Depends(get_db)):
    """Public: resolve a club-admin "reset your password" token
    (routers/club_admin.py::send_password_reset_link) to the account's basic
    identity, so the reset step on the login page can greet them by name.
    Generic "invalid or expired" on any failure — doesn't leak whether a
    token ever existed. Unlike get_invite, doesn't care about password_hash —
    this is for an account that already has one."""
    result = await db.execute(select(User).where(User.password_reset_token == token))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="This reset link is invalid or has already been used")
    expires = user.password_reset_token_expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            raise HTTPException(
                status_code=410,
                detail="This reset link has expired — ask an admin at your club to send a new one",
            )

    membership_res = await db.execute(select(ClubMembership).where(ClubMembership.user_id == user.id))
    membership = membership_res.scalar_one_or_none()
    club = await db.get(Organisation, membership.club_id) if membership else None
    return {
        "username": user.username,
        "display_name": user.display_name,
        "club_name": club.name if club else None,
    }


@router.post("/reset-password/{token}/accept")
async def accept_password_reset(token: str, data: ResetPasswordAcceptRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Set an existing club-admin's password from an admin-triggered reset
    link and log them in — same session-minting primitive login() and
    accept_invite() use. Same shared password rule as every other
    self-set-password flow (services/password_policy.py)."""
    from app.services import password_policy

    result = await db.execute(select(User).where(User.password_reset_token == token))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="This reset link is invalid or has already been used")
    expires = user.password_reset_token_expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            raise HTTPException(
                status_code=410,
                detail="This reset link has expired — ask an admin at your club to send a new one",
            )

    errors = password_policy.password_errors(data.password, data.confirm_password)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    user.password_hash = _hash_password(data.password)
    user.password_reset_token = None
    user.password_reset_token_expires_at = None
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    token_value = create_session_token(str(user.id))
    set_session_cookie(response, token_value)
    return await _build_me(user, db)


async def _build_me(current_user: User, db: AsyncSession) -> dict:
    """The shared identity payload returned by /login, /me and /switch-club.

    For a super admin this resolves to whichever club they're currently acting
    as (``active_club_id``), and also carries the home-club + acting flags the
    frontend club switcher needs.
    """
    from app.auth.capabilities import effective_capabilities
    from app.auth.modules import entitlement_summary
    from app.services.marketing_org import org_is_outreach

    membership_res = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )
    membership = membership_res.scalar_one_or_none()
    role = membership.role if membership else None
    caps = effective_capabilities(role, membership.capabilities if membership else None) if role else []

    home_club = await db.get(Organisation, membership.club_id) if membership else None
    eff_id = _effective_club_id(membership, current_user)
    # Eager-load per-module subscriptions so entitlement_summary can return each
    # module's status / renewal / trial end (and apply read-time trial expiry).
    club = await db.get(
        Organisation, eff_id,
        options=[selectinload(Organisation.module_subscriptions)],
    ) if eff_id else None
    # active_club_id may dangle (acted-as club deleted) — fall back to home.
    if club is None and membership is not None:
        club = home_club
        eff_id = membership.club_id

    is_super = role == "super_admin"
    acting = bool(is_super and home_club and club and club.id != home_club.id)

    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "display_name": current_user.display_name,
        "role": role,
        "club_id": str(eff_id) if eff_id else None,
        "club_slug": club.slug if club else None,
        "club_name": club.name if club else None,
        # True when acting as the BetterCricket marketing-outreach org (not a real
        # club), so the public club navbar can suppress its club links.
        "is_marketing_org": org_is_outreach(club),
        "capabilities": caps,
        "entitlements": entitlement_summary(club, role),
        # Super-admin club-switch context. can_switch_clubs gates the UI switcher;
        # acting_as_club is true only while scoped to a club other than home.
        "can_switch_clubs": is_super,
        "home_club_id": str(membership.club_id) if membership else None,
        "home_club_name": home_club.name if home_club else None,
        "acting_as_club": acting,
        # The club's primary/owner admin gate: only the primary may request a paid
        # module subscription (any club_admin may request a trial). True for a super
        # admin so the UI never blocks them.
        "is_primary_admin": bool(is_super or (membership and getattr(membership, "is_primary_admin", False))),
    }


@router.get("/me")
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _build_me(current_user, db)


class SwitchClubRequest(BaseModel):
    # None / omitted resets the super admin back to their home club.
    club_id: str | None = None


@router.post("/switch-club")
async def switch_club(
    data: SwitchClubRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Super-admin-only: re-scope the whole admin app to another club.

    Persists the choice on the user row so every subsequent club-scoped request
    (and a page reload) resolves to the acted-as club until they switch again.
    """
    result = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()
    if not membership or membership.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admins can switch clubs")

    if not data.club_id:
        current_user.active_club_id = None
    else:
        try:
            target_id = uuid.UUID(data.club_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid club id")
        target = await db.get(Organisation, target_id)
        if not target:
            raise HTTPException(status_code=404, detail="Club not found")
        # Acting as the home club is just the cleared state — keep it NULL so
        # acting_as_club reads false.
        current_user.active_club_id = None if target_id == membership.club_id else target_id

    await db.commit()
    await db.refresh(current_user)
    return await _build_me(current_user, db)
