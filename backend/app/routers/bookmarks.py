"""Per-user admin bookmarks — quick-access favourites in the admin sidebar.

User-scoped (not club-scoped): the admin routes are the same whichever club a
super admin is acting as, so a person's favourites follow them. All endpoints
only need the logged-in user, so they depend on ``get_current_user`` alone.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from pydantic import BaseModel
from typing import Optional

from app.models.db import UserBookmark, User, get_db
from app.routers.auth import get_current_user

router = APIRouter(prefix="/club-admin", tags=["bookmarks"])

# A generous ceiling — favourites are a shortlist, not a second nav. Stops a
# runaway client (or a bored user) bloating the row.
MAX_BOOKMARKS = 50
_MAX_PATH = 512
_MAX_LABEL = 120


def _serialize(b: UserBookmark) -> dict:
    return {
        "id": str(b.id),
        "path": b.path,
        "label": b.label,
        "sort_order": b.sort_order,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


@router.get("/bookmarks")
async def list_bookmarks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(UserBookmark)
        .where(UserBookmark.user_id == current_user.id)
        .order_by(UserBookmark.sort_order, UserBookmark.created_at)
    )
    return [_serialize(b) for b in res.scalars().all()]


class BookmarkIn(BaseModel):
    path: str
    label: Optional[str] = None


@router.post("/bookmarks")
async def add_bookmark(
    payload: BookmarkIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add the current page to the user's bookmarks (idempotent by path).

    Re-posting an existing path just refreshes its label, so the star toggle and
    a rename both flow through here.
    """
    path = (payload.path or "").strip()
    if not path.startswith("/"):
        raise HTTPException(status_code=400, detail="Bookmark path must be an internal route")
    path = path[:_MAX_PATH]
    label = ((payload.label or "").strip() or path)[:_MAX_LABEL]

    existing = await db.execute(
        select(UserBookmark).where(
            UserBookmark.user_id == current_user.id,
            UserBookmark.path == path,
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        row.label = label
        await db.commit()
        await db.refresh(row)
        return _serialize(row)

    count = await db.scalar(
        select(func.count(UserBookmark.id)).where(UserBookmark.user_id == current_user.id)
    ) or 0
    if count >= MAX_BOOKMARKS:
        raise HTTPException(
            status_code=400,
            detail=f"You've reached the {MAX_BOOKMARKS} bookmark limit. Remove one to add another.",
        )

    max_order = await db.scalar(
        select(func.max(UserBookmark.sort_order)).where(UserBookmark.user_id == current_user.id)
    )
    row = UserBookmark(
        user_id=current_user.id,
        path=path,
        label=label,
        sort_order=(max_order or 0) + 1,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _serialize(row)


@router.delete("/bookmarks")
async def remove_bookmark(
    path: str = Query(..., description="The bookmarked internal route to remove"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(UserBookmark).where(
            UserBookmark.user_id == current_user.id,
            UserBookmark.path == path,
        )
    )
    await db.commit()
    return {"ok": True}
