"""BetterScout — Settings screen routes: org profile/plan/refresh/sharing/
digest settings, people + invites, share-link management. Every write here
requires the 'owner' role (require_scout_owner) — see routers/scout/auth.py
for why org-wide actions get an extra layer on top of the per-record
ownership check every other write endpoint already has."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.scout import ScoutOrg, ScoutUser
from app.routers.scout.auth import get_current_scout_user, require_scout_owner
from app.services import scout_billing, scout_invites, scout_settings, scout_watchlist

router = APIRouter(prefix="/scout", tags=["scout-settings"])


@router.get("/settings")
async def get_settings(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
):
    _, org = current
    return scout_settings.settings_out(org)


class UpdateSettingsRequest(BaseModel):
    org_type: str | None = None
    home_region: str | None = None
    refresh_cadence: str | None = None
    stale_after_weeks: int | None = None
    default_window: str | None = None
    share_include_notes: bool | None = None
    share_include_tags: bool | None = None
    share_expiry_days: int | None = None
    digest_enabled: bool | None = None
    alert_scope: str | None = None


@router.patch("/settings")
async def update_settings(
    data: UpdateSettingsRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    try:
        return await scout_settings.update_settings(db, org, **data.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/settings/billing")
async def get_billing(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    usage = await scout_billing.usage_for(db, org)
    return {
        **usage,
        "tiers": [
            {"key": k, "label": scout_billing.TIER_LABELS[k], "cap": v}
            for k, v in scout_billing.TIER_LIMITS.items()
        ],
    }


# ─── people + invites ───────────────────────────────────────────────────────

@router.get("/people")
async def list_people(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    return await scout_invites.list_people(db, org.id)


class InviteRequest(BaseModel):
    email: str
    role: str = "viewer"


@router.post("/people/invite")
async def invite_person(
    data: InviteRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    try:
        return await scout_invites.create_invite(db, org.id, data.email, data.role, user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/people/invites/{invite_id}")
async def revoke_invite(
    invite_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    try:
        await scout_invites.revoke_invite(db, org.id, invite_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok"}


# ─── share-link management ──────────────────────────────────────────────────

@router.get("/settings/share-links")
async def list_share_links(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    return await scout_watchlist.list_share_links(db, org.id)


@router.post("/settings/share-links/revoke-all")
async def revoke_all_share_links(
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    n = await scout_watchlist.revoke_all_share_links(db, org.id)
    return {"revoked": n}


# ─── danger zone ─────────────────────────────────────────────────────────────

@router.post("/settings/close-org")
async def close_org(
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    """A genuine, irreversible delete — the confirm copy on the design says
    so ("Deletes watchlists, notes and share links") and it would be a false
    promise to only flip is_active. Every scout_org_id-scoped table
    (scout_users, scout_watchlists -> columns -> cards) cascades on
    ondelete=CASCADE, so deleting the org row is the whole operation.
    ScoutedPlayer/ScoutClubCache rows are untouched — they carry no FK to
    scout_orgs at all (platform-wide, shared by every org, see
    models/scout.py), which is exactly "cached club rosters stay, they
    aren't yours"."""
    _, org = current
    await db.delete(org)
    await db.commit()
    return {"status": "closed"}
