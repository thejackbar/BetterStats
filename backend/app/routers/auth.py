from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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


def _create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.secret_key, algorithm=settings.algorithm)


def _set_session_cookie(response: Response, token: str) -> None:
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
    club = await db.get(Organisation, membership.club_id)
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
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username.lower()))
    user = result.scalar_one_or_none()

    # Generic error — do not leak which field was wrong
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    now = datetime.now(timezone.utc)

    # Check lockout
    if user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
        raise HTTPException(status_code=429, detail="Account temporarily locked. Try again later.")

    if not _verify_password(data.password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Check user has an active club membership (super_admin bypasses the is_active check)
    membership_res = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == user.id)
    )
    membership = membership_res.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=403, detail="No club membership found")

    if membership.role != "super_admin":
        club = await db.get(Organisation, membership.club_id)
        if not club or not club.is_active:
            raise HTTPException(status_code=403, detail="Club is not active")

    # Success — reset counters, update last login
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    await db.commit()

    token = _create_token(str(user.id))
    _set_session_cookie(response, token)

    role = membership.role if membership else None
    return {"id": str(user.id), "username": user.username, "display_name": user.display_name, "role": role}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "logged_out"}


@router.get("/me")
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    membership_res = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )
    membership = membership_res.scalar_one_or_none()
    role = membership.role if membership else None
    club_id = str(membership.club_id) if membership else None

    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "display_name": current_user.display_name,
        "role": role,
        "club_id": club_id,
    }
