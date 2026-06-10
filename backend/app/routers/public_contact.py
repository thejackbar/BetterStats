"""Public Contact-form intake (unauthenticated).

The marketing Contact form (betterat.cricket/contact) posts here on submit so
every prospective-club enquiry is stored in BetterStats, alongside the Formspree
email the form still sends. Unauthenticated by design: the sender is a prospect
with no club and no login, so this is NOT wrapped in require_module / auth.
Stored rows are read back in the super-admin area
(GET /club-admin/super/onboarding-requests).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ClubOnboardingRequest, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/contact", tags=["public-contact"])


class ContactIn(BaseModel):
    name: str = ""
    club: str = ""
    email: str = ""
    phone: Optional[str] = None
    association: Optional[str] = None
    grades: Optional[str] = None
    storage: Optional[str] = None
    timeline: Optional[str] = None
    clubUrl: Optional[str] = None
    message: Optional[str] = None


def _clip(value: Optional[str], limit: int) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value[:limit] if value else None


@router.post("")
async def submit_contact(
    payload: ContactIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Store one club onboarding enquiry.

    The required fields are validated client-side too; we re-check the three that
    make a row meaningful (name, club, email) and clip every field so a bad or
    oversized post can't bloat the table. Formspree is the primary delivery, so
    the frontend treats a non-200 here as non-fatal.
    """
    name = (payload.name or "").strip()
    club = (payload.club or "").strip()
    email = (payload.email or "").strip().lower()
    if not name or not club or not email:
        raise HTTPException(status_code=422, detail="Name, club and email are required.")

    row = ClubOnboardingRequest(
        name=name[:200],
        club=club[:200],
        email=email[:320],
        phone=_clip(payload.phone, 50),
        association=_clip(payload.association, 200),
        grades=_clip(payload.grades, 50),
        storage=_clip(payload.storage, 100),
        timeline=_clip(payload.timeline, 100),
        club_url=_clip(payload.clubUrl, 500),
        message=_clip(payload.message, 4000),
        source="contact_form",
        user_agent=_clip(request.headers.get("user-agent"), 500),
    )
    db.add(row)
    await db.commit()
    return {"ok": True}
