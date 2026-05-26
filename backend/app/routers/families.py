"""Family relationships within a club.

Lets admins group related players and surface "same surname" suggestions
similar to the merge-pairs UI. Family is also exposed as a StatLab player
filter — see PLAYER_CONTEXT_FILTERS in services/statlab.py.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_FAMILIES, require_cap
from app.models.db import Family, FamilyMember, Player, User, get_db
from app.services.audit_log import log_activity

router = APIRouter(prefix="/families", tags=["families"])


def _surname_key(name: str) -> str:
    """Lowercased surname extracted from a player name.

    Supports both stored formats: "Last, First" (canonical CA format used
    by sync) and "First Last" (occasional manual entries). Returns an
    empty string if no usable surname can be parsed.
    """
    if not name:
        return ""
    n = name.strip()
    if "," in n:
        part = n.split(",", 1)[0].strip()
    else:
        words = [w for w in re.split(r"\s+", n) if w]
        part = words[-1] if words else ""
    return part.lower()


def _player_dict(p: Player) -> dict:
    return {
        "id": str(p.id),
        "name": p.display_name,
        "playhq_id": p.playhq_id,
    }


async def _load_family_members(db: AsyncSession, family_id: uuid.UUID) -> list[dict]:
    rows = await db.execute(
        text("""
            SELECT fm.id AS fm_id, fm.relationship, fm.created_at,
                   p.id AS player_id, p.name, p.display_name_override, p.playhq_id
            FROM family_members fm
            JOIN players p ON p.id = fm.player_id
            WHERE fm.family_id = :fid
            ORDER BY p.name
        """),
        {"fid": str(family_id)},
    )
    return [
        {
            "id": str(r.fm_id),
            "player_id": str(r.player_id),
            "name": r.display_name_override or r.name,
            "playhq_id": r.playhq_id,
            "relationship": r.relationship,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows.mappings().all()
    ]


@router.get("")
async def list_families(
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        text("""
            SELECT f.id, f.name, f.notes, f.created_at, f.updated_at,
                   COUNT(fm.id) AS member_count
            FROM families f
            LEFT JOIN family_members fm ON fm.family_id = f.id
            WHERE f.organisation_id = CAST(:org_id AS UUID)
            GROUP BY f.id
            ORDER BY f.name
        """),
        {"org_id": org_id},
    )
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "notes": r.notes,
            "member_count": int(r.member_count or 0),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows.mappings().all()
    ]


@router.get("/{family_id}")
async def get_family(
    family_id: str,
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    fam = await db.get(Family, uuid.UUID(family_id))
    if not fam or str(fam.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Family not found")
    members = await _load_family_members(db, fam.id)
    return {
        "id": str(fam.id),
        "name": fam.name,
        "notes": fam.notes,
        "members": members,
    }


class FamilyCreateIn(BaseModel):
    org_id: str
    name: str = Field(..., min_length=1, max_length=120)
    notes: Optional[str] = Field(None, max_length=2000)


@router.post("")
async def create_family(
    body: FamilyCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Family name is required")
    exists = await db.execute(
        select(Family).where(
            Family.organisation_id == uuid.UUID(body.org_id),
            Family.name.ilike(name),
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A family with that name already exists")
    fam = Family(
        organisation_id=uuid.UUID(body.org_id),
        name=name,
        notes=(body.notes or None),
    )
    db.add(fam)
    await db.flush()
    await log_activity(
        db, org_id=uuid.UUID(body.org_id), user_id=current_user.id,
        action="create_family", target_type="family", target_id=str(fam.id),
        details={"name": name},
    )
    await db.commit()
    return {"id": str(fam.id), "name": fam.name, "notes": fam.notes, "members": []}


class FamilyUpdateIn(BaseModel):
    org_id: str
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    notes: Optional[str] = Field(None, max_length=2000)


@router.patch("/{family_id}")
async def update_family(
    family_id: str,
    body: FamilyUpdateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    fam = await db.get(Family, uuid.UUID(family_id))
    if not fam or str(fam.organisation_id) != body.org_id:
        raise HTTPException(status_code=404, detail="Family not found")
    if body.name is not None:
        new_name = body.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Family name cannot be empty")
        if new_name.lower() != fam.name.lower():
            clash = await db.execute(
                select(Family).where(
                    Family.organisation_id == fam.organisation_id,
                    Family.name.ilike(new_name),
                    Family.id != fam.id,
                )
            )
            if clash.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="A family with that name already exists")
        fam.name = new_name
    if body.notes is not None:
        fam.notes = body.notes or None
    await db.execute(
        text("UPDATE families SET updated_at = NOW() WHERE id = :fid"),
        {"fid": str(fam.id)},
    )
    await log_activity(
        db, org_id=fam.organisation_id, user_id=current_user.id,
        action="update_family", target_type="family", target_id=str(fam.id),
        details={"name": fam.name},
    )
    await db.commit()
    return {"id": str(fam.id), "name": fam.name, "notes": fam.notes}


@router.delete("/{family_id}")
async def delete_family(
    family_id: str,
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    fam = await db.get(Family, uuid.UUID(family_id))
    if not fam or str(fam.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Family not found")
    fam_name = fam.name
    await db.delete(fam)
    await log_activity(
        db, org_id=fam.organisation_id, user_id=current_user.id,
        action="delete_family", target_type="family", target_id=str(family_id),
        details={"name": fam_name},
    )
    await db.commit()
    return {"status": "deleted"}


class MemberIn(BaseModel):
    org_id: str
    player_id: str
    relationship: Optional[str] = Field(None, max_length=80)


@router.post("/{family_id}/members")
async def add_member(
    family_id: str,
    body: MemberIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    fam = await db.get(Family, uuid.UUID(family_id))
    if not fam or str(fam.organisation_id) != body.org_id:
        raise HTTPException(status_code=404, detail="Family not found")
    player = await db.get(Player, uuid.UUID(body.player_id))
    if not player or str(player.organisation_id) != body.org_id:
        raise HTTPException(status_code=404, detail="Player not found in this organisation")
    dupe = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == fam.id,
            FamilyMember.player_id == player.id,
        )
    )
    if dupe.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Player is already in this family")
    rel = (body.relationship or "").strip() or None
    fm = FamilyMember(family_id=fam.id, player_id=player.id, relationship_label=rel)
    db.add(fm)
    await db.execute(
        text("UPDATE families SET updated_at = NOW() WHERE id = :fid"),
        {"fid": str(fam.id)},
    )
    await log_activity(
        db, org_id=fam.organisation_id, user_id=current_user.id,
        action="add_family_member", target_type="family", target_id=str(fam.id),
        details={"family": fam.name, "player": player.display_name, "relationship": rel},
    )
    await db.commit()
    members = await _load_family_members(db, fam.id)
    return {"members": members}


class MemberPatchIn(BaseModel):
    org_id: str
    relationship: Optional[str] = Field(None, max_length=80)


@router.patch("/{family_id}/members/{player_id}")
async def update_member(
    family_id: str,
    player_id: str,
    body: MemberPatchIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    fam = await db.get(Family, uuid.UUID(family_id))
    if not fam or str(fam.organisation_id) != body.org_id:
        raise HTTPException(status_code=404, detail="Family not found")
    row = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == fam.id,
            FamilyMember.player_id == uuid.UUID(player_id),
        )
    )
    fm = row.scalar_one_or_none()
    if not fm:
        raise HTTPException(status_code=404, detail="Member not found")
    fm.relationship_label = (body.relationship or "").strip() or None
    await db.execute(
        text("UPDATE families SET updated_at = NOW() WHERE id = :fid"),
        {"fid": str(fam.id)},
    )
    await db.commit()
    return {"status": "ok"}


@router.delete("/{family_id}/members/{player_id}")
async def remove_member(
    family_id: str,
    player_id: str,
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    fam = await db.get(Family, uuid.UUID(family_id))
    if not fam or str(fam.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Family not found")
    row = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == fam.id,
            FamilyMember.player_id == uuid.UUID(player_id),
        )
    )
    fm = row.scalar_one_or_none()
    if not fm:
        raise HTTPException(status_code=404, detail="Member not found")
    await db.delete(fm)
    await db.execute(
        text("UPDATE families SET updated_at = NOW() WHERE id = :fid"),
        {"fid": str(fam.id)},
    )
    await log_activity(
        db, org_id=fam.organisation_id, user_id=current_user.id,
        action="remove_family_member", target_type="family", target_id=str(fam.id),
        details={"family": fam.name, "player_id": player_id},
    )
    await db.commit()
    return {"status": "removed"}


@router.get("/suggestions/list")
async def family_suggestions(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    """Group org players by exact-lowercased surname.

    Excludes players already assigned to a family, single-player groups,
    and surnames the admin has previously dismissed.
    """
    org_uuid = uuid.UUID(org_id)

    res = await db.execute(
        select(Player).where(Player.organisation_id == org_uuid)
    )
    players = res.scalars().all()

    assigned = await db.execute(
        text("""
            SELECT fm.player_id, f.id AS family_id, f.name AS family_name
            FROM family_members fm
            JOIN families f ON f.id = fm.family_id
            WHERE f.organisation_id = CAST(:org_id AS UUID)
        """),
        {"org_id": org_id},
    )
    assigned_map = {
        str(r.player_id): {"family_id": str(r.family_id), "family_name": r.family_name}
        for r in assigned.mappings().all()
    }

    dismissed_res = await db.execute(
        text("SELECT surname_key FROM family_suggestions_dismissed WHERE organisation_id = CAST(:org_id AS UUID)"),
        {"org_id": org_id},
    )
    dismissed = {r.surname_key for r in dismissed_res.mappings().all()}

    groups: dict[str, list[Player]] = {}
    for p in players:
        if str(p.id) in assigned_map:
            continue
        key = _surname_key(p.name)
        if not key or key in dismissed:
            continue
        groups.setdefault(key, []).append(p)

    suggestions = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        suggestions.append({
            "surname_key": key,
            "surname_display": key.title(),
            "players": [_player_dict(p) for p in sorted(members, key=lambda x: (x.name or "").lower())],
        })
    suggestions.sort(key=lambda g: (-len(g["players"]), g["surname_key"]))
    return suggestions


class DismissIn(BaseModel):
    org_id: str
    surname_key: str = Field(..., min_length=1, max_length=120)


@router.post("/suggestions/dismiss")
async def dismiss_suggestion(
    body: DismissIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    key = body.surname_key.strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="surname_key required")
    await db.execute(
        text("""
            INSERT INTO family_suggestions_dismissed (organisation_id, surname_key, dismissed_by_user_id)
            VALUES (CAST(:org_id AS UUID), :k, :uid)
            ON CONFLICT (organisation_id, surname_key) DO NOTHING
        """),
        {"org_id": body.org_id, "k": key, "uid": str(current_user.id)},
    )
    await db.commit()
    return {"status": "dismissed"}


@router.delete("/suggestions/dismissed/{surname_key}")
async def restore_suggestion(
    surname_key: str,
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    await db.execute(
        text(
            "DELETE FROM family_suggestions_dismissed "
            "WHERE organisation_id = CAST(:org_id AS UUID) AND surname_key = :k"
        ),
        {"org_id": org_id, "k": surname_key.strip().lower()},
    )
    await db.commit()
    return {"status": "restored"}
