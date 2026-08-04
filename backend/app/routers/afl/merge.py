"""Merge Grades — combine grade-name variants into one competition.

Ported near-verbatim from cricket's routers/admin.py: this touches only
``grades``/``grade_merge_logs`` (a name-alias table, org-scoped) and never a
stat table, so it's 100% sport-agnostic. Merge Players (which DOES need to
walk AFL's own stat tables) is Phase 2 and deliberately not in this file yet.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MERGES, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club, get_current_user
from app.services.audit_log import log_activity

router = APIRouter(prefix="/club-admin", tags=["afl-merge"])


def _resolve_canonical_grade(chain: dict[str, str], name: str, _seen: set | None = None) -> str:
    """Follow the alias chain to its root, guarding against a cycle."""
    seen = _seen or set()
    if name in seen:
        return name
    seen.add(name)
    nxt = chain.get(name)
    if nxt is None:
        return name
    return _resolve_canonical_grade(chain, nxt, seen)


class MergeGradesRequest(BaseModel):
    alias_name: str
    canonical_name: str


@router.post("/merge-grades")
async def merge_grades(
    req: MergeGradesRequest,
    club: Organisation = Depends(get_current_club),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    db: AsyncSession = Depends(get_db),
):
    """Mark `alias_name` as a variant of `canonical_name` for this club."""
    alias = req.alias_name.strip()
    canonical = req.canonical_name.strip()
    if not alias or not canonical:
        raise HTTPException(status_code=400, detail="Both grade names are required")
    if alias == canonical:
        raise HTTPException(status_code=400, detail="Alias and canonical grade are the same")

    org_id = str(club.id)
    existing = await db.execute(text("""
        SELECT alias_name, canonical_name FROM grade_merge_logs
        WHERE org_id = :org_id AND undone_at IS NULL
    """), {"org_id": org_id})
    chain = {r["alias_name"]: r["canonical_name"] for r in existing.mappings().all()}

    resolved_canonical = _resolve_canonical_grade(chain, canonical)
    if resolved_canonical == alias:
        raise HTTPException(status_code=400, detail="That merge would create a cycle")

    await db.execute(text("""
        UPDATE grade_merge_logs SET canonical_name = :new_canonical
        WHERE org_id = :org_id AND undone_at IS NULL AND canonical_name = :alias
    """), {"org_id": org_id, "new_canonical": resolved_canonical, "alias": alias})

    await db.execute(text("""
        UPDATE grade_merge_logs SET undone_at = NOW()
        WHERE org_id = :org_id AND undone_at IS NULL AND alias_name = :alias
    """), {"org_id": org_id, "alias": alias})

    await db.execute(text("""
        INSERT INTO grade_merge_logs (org_id, alias_name, canonical_name)
        VALUES (:org_id, :alias, :canonical)
    """), {"org_id": org_id, "alias": alias, "canonical": resolved_canonical})

    await log_activity(
        db, org_id=org_id, user_id=current_user.id,
        action="merge_grades", target_type="grade", target_id=resolved_canonical,
        details={"alias_name": alias, "canonical_name": resolved_canonical},
    )
    await db.commit()
    return {"status": "merged", "alias": alias, "canonical": resolved_canonical}


@router.get("/grade-merge-history")
async def grade_merge_history(
    club: Organisation = Depends(get_current_club),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(text("""
        SELECT id, merged_at, alias_name, canonical_name, undone_at
        FROM grade_merge_logs WHERE org_id = :org_id
        ORDER BY merged_at DESC LIMIT 100
    """), {"org_id": str(club.id)})
    return [
        {
            "id": r["id"],
            "merged_at": r["merged_at"].isoformat() if r["merged_at"] else None,
            "alias_name": r["alias_name"],
            "canonical_name": r["canonical_name"],
            "undone": r["undone_at"] is not None,
        }
        for r in rows.mappings().all()
    ]


class UndoGradeMergeRequest(BaseModel):
    merge_log_id: int


@router.post("/undo-grade-merge")
async def undo_grade_merge(
    req: UndoGradeMergeRequest,
    club: Organisation = Depends(get_current_club),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        UPDATE grade_merge_logs SET undone_at = NOW()
        WHERE id = :id AND org_id = :org_id AND undone_at IS NULL
        RETURNING id
    """), {"id": req.merge_log_id, "org_id": str(club.id)})
    if result.first() is None:
        raise HTTPException(status_code=404, detail="Merge log not found or already undone")

    await log_activity(
        db, org_id=str(club.id), user_id=current_user.id,
        action="undo_merge_grades", target_type="grade_merge_log", target_id=str(req.merge_log_id),
    )
    await db.commit()
    return {"status": "undone"}


@router.get("/grade-names")
async def list_grade_names(
    club: Organisation = Depends(get_current_club),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Distinct grade names for this club, for the merge picker."""
    rows = await db.execute(text("""
        SELECT DISTINCT gr.name FROM grades gr
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org
        ORDER BY gr.name
    """), {"org": str(club.id)})
    return {"names": [r[0] for r in rows.all()]}
