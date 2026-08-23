"""Public club routes: slug-based lookup, inactive-club gating, and the
password-protected "Draft" page gate (see app/services/club_lock.py)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.db import ClubUnpauseRequest, Organisation, Season, Sponsor, get_db
from app.routers.organisations import _season_sort_key
from app.auth.modules import org_core_live
from app.services import club_lock, email_service, rate_limit
from app.services import fonts as font_service
from app.config.settings import settings

router = APIRouter(prefix="/clubs", tags=["clubs"])

INACTIVE_DETAIL = "This club page is currently not available. Contact your club executives to get access."

# Super Admin's notification address for unpause requests — deliberately this
# specific address (not the general support/reply-to address) per direct
# instruction, so this is the "sales conversion" inbox, not customer support.
UNPAUSE_NOTIFY_EMAIL = "cricket@bettersports.com.au"

# PIN lockout: 5 wrong attempts inside 15 minutes (per org + IP) → cooldown.
PIN_MAX_FAILURES = 5
PIN_LOCKOUT_SECONDS = 15 * 60
VERIFY_IP_LIMIT = 40
VERIFY_IP_WINDOW = 60
REQUEST_IP_LIMIT = 10
REQUEST_IP_WINDOW = 60 * 60


def _public_blocked(org) -> bool:
    """A club's public surfaces are hidden when it's manually inactive OR its
    BetterStats (Core) module isn't live (cancelled / expired trial / master switch
    off). org must be loaded with module_subscriptions for the Core check."""
    return (not org.is_active) or (not org_core_live(org))


def _client_ip(request: Request) -> str:
    """Best-effort real client IP for rate-limit keying (Cloudflare-aware)."""
    for header in ("cf-connecting-ip", "x-real-ip"):
        v = request.headers.get(header)
        if v:
            return v.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _org_by_slug(db: AsyncSession, slug: str) -> Organisation | None:
    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug.lower())
        .options(selectinload(Organisation.module_subscriptions))
    )
    return result.scalar_one_or_none()


@router.get("/{slug}")
async def get_club_by_slug(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    org = await _org_by_slug(db, slug)
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    if club_lock.is_locked_for_request(org, request):
        raise HTTPException(status_code=423, detail=club_lock.lock_detail(org))
    if _public_blocked(org):
        raise HTTPException(status_code=403, detail=INACTIVE_DETAIL)
    return {
        "id": str(org.id),
        "slug": org.slug,
        "name": org.name,
        "short_name": org.short_name,
        "is_active": org.is_active,
        "primary_color": org.primary_color,
        "accent_color": org.accent_color,
        "logo_url": org.logo_url,
        "hero_image_url": org.hero_image_url,
        "theme_mode": org.theme_mode,
        "theme_config": org.theme_config or {},
        **font_service.public_font_fields(org),
        "contact_email": org.contact_email,
        "player_name_format": org.player_name_format or "last_first",
        "website_enabled": bool(org.website_enabled),
        "public_header_logo": bool(org.public_header_logo),
    }


class UnlockBody(BaseModel):
    pin: str = ""


@router.post("/{slug}/unlock")
async def unlock_club(slug: str, body: UnlockBody, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Verify the 4-digit PIN and issue the bs_lock cookie. Rate-limited per IP
    and locked out after repeated wrong guesses (same shape as BetterSelect's
    self-service availability PIN, see public_availability.py)."""
    org = await _org_by_slug(db, slug)
    if not org or not org.password_protected:
        raise HTTPException(status_code=404, detail="Club not found")

    ip = _client_ip(request)
    rate_limit.enforce(
        f"club-unlock-ip:{org.id}:{ip}", VERIFY_IP_LIMIT, VERIFY_IP_WINDOW,
        detail="Too many attempts, slow down and try again shortly.",
    )
    lock_key = f"club-unlock:{org.id}:{ip}"
    rate_limit.assert_not_locked(
        lock_key, PIN_MAX_FAILURES, PIN_LOCKOUT_SECONDS,
        detail="Too many incorrect attempts. Please wait a few minutes and try again.",
    )

    pin = (body.pin or "").strip()
    if not club_lock.verify_pin(pin, org.access_pin_hash):
        rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
        raise HTTPException(status_code=401, detail="That PIN didn't match. Try again.")

    rate_limit.clear_failures(lock_key)
    club_lock.issue_lock_cookie(response, org.id)
    return {"status": "ok"}


class RequestUnpauseBody(BaseModel):
    email: str
    message: str = ""


@router.post("/{slug}/request-unpause")
async def request_unpause(slug: str, body: RequestUnpauseBody, request: Request, db: AsyncSession = Depends(get_db)):
    """The "email me for access" form shown only on a trial_ended-gated page —
    the sales-conversion trigger. Creates a queue row Super Admin reviews at
    /admin/super/unpause-requests, plus a best-effort notification email."""
    org = await _org_by_slug(db, slug)
    if not org or not org.password_protected or org.password_protect_reason != "trial_ended":
        raise HTTPException(status_code=400, detail="This club isn't accepting unpause requests")

    ip = _client_ip(request)
    rate_limit.enforce(
        f"club-unpause-ip:{ip}", REQUEST_IP_LIMIT, REQUEST_IP_WINDOW,
        detail="Too many requests, please try again later.",
    )

    email = (body.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    message = (body.message or "").strip()[:2000] or None

    # Dedupe: don't pile up duplicate pending rows for the same club + email.
    existing = await db.execute(
        select(ClubUnpauseRequest).where(
            ClubUnpauseRequest.organisation_id == org.id,
            ClubUnpauseRequest.email == email,
            ClubUnpauseRequest.status == "pending",
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "ok"}

    db.add(ClubUnpauseRequest(
        id=uuid.uuid4(), organisation_id=org.id, email=email, message=message,
    ))
    await db.commit()

    try:
        msg = email_service.EmailMessage(
            to_email=UNPAUSE_NOTIFY_EMAIL,
            subject=f"Unpause request: {org.name}",
            html=(
                f"<p><strong>{org.name}</strong> ({org.slug}) has a new unpause request.</p>"
                f"<p>From: {email}</p>"
                + (f"<p>{message}</p>" if message else "")
            ),
            text=f"{org.name} ({org.slug}) has a new unpause request.\nFrom: {email}\n{message or ''}",
            from_email=settings.email_from_address, from_name=settings.email_from_name,
            reply_to=email,
        )
        await email_service.get_email_provider().send(msg)
    except Exception:
        pass  # best-effort — the queue row is the source of truth either way

    return {"status": "ok"}


@router.get("/{slug}/sponsors")
async def get_club_sponsors(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    org = await _org_by_slug(db, slug)
    if not org or _public_blocked(org) or club_lock.is_locked_for_request(org, request):
        raise HTTPException(status_code=404, detail="Club not found")

    sponsors_result = await db.execute(
        select(Sponsor)
        .where(Sponsor.organisation_id == org.id)
        .order_by(Sponsor.display_order, Sponsor.created_at)
    )
    sponsors = sponsors_result.scalars().all()

    # Determine the current (most recent) season name
    seasons_result = await db.execute(
        select(Season).where(Season.organisation_id == org.id)
    )
    all_seasons = seasons_result.scalars().all()
    current_season = None
    if all_seasons:
        sorted_seasons = sorted(all_seasons, key=_season_sort_key)
        current_season = sorted_seasons[0].name if sorted_seasons else None

    return {
        "club_name": org.short_name or org.name,
        "current_season": current_season,
        "sponsors": [
            {
                "id": str(s.id),
                "name": s.name,
                "website_url": s.website_url,
                "logo_url": s.logo_url,
            }
            for s in sponsors
            if s.logo_url  # only show sponsors that have a logo
        ],
    }
