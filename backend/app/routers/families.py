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
from app.models.db import Family, FamilyMember, FeeMember, FeeMemberSeason, FeeSchedule, Player, Season, User, get_db
from app.routers.fees import _days_by_member_season, _financials, _paid_by_member_season, _waived_days_by_member_season
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
    """Every member of a family — players AND non-playing members (parents,
    guardians — anyone who's a fee_members row but not themselves a Player;
    migration 175). ``kind`` tells the two apart on the frontend."""
    rows = await db.execute(
        text("""
            SELECT fm.id AS fm_id, fm.relationship, fm.created_at, fm.is_guardian, fm.receives_family_comms,
                   p.id AS player_id, p.name, p.display_name_override, p.playhq_id
            FROM family_members fm
            JOIN players p ON p.id = fm.player_id
            WHERE fm.family_id = :fid
            ORDER BY p.name
        """),
        {"fid": str(family_id)},
    )
    out = [
        {
            "id": str(r.fm_id),
            "kind": "player",
            "player_id": str(r.player_id),
            "fee_member_id": None,
            "name": r.display_name_override or r.name,
            "playhq_id": r.playhq_id,
            "relationship": r.relationship,
            "is_guardian": r.is_guardian,
            "receives_family_comms": r.receives_family_comms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows.mappings().all()
    ]
    rows2 = await db.execute(
        text("""
            SELECT fm.id AS fm_id, fm.relationship, fm.created_at, fm.is_guardian, fm.receives_family_comms,
                   m.id AS fee_member_id, m.full_name, m.email, m.mobile
            FROM family_members fm
            JOIN fee_members m ON m.id = fm.fee_member_id
            WHERE fm.family_id = :fid
            ORDER BY m.full_name
        """),
        {"fid": str(family_id)},
    )
    out += [
        {
            "id": str(r.fm_id),
            "kind": "fee_member",
            "player_id": None,
            "fee_member_id": str(r.fee_member_id),
            "name": r.full_name,
            "email": r.email,
            "mobile": r.mobile,
            "relationship": r.relationship,
            "is_guardian": r.is_guardian,
            "receives_family_comms": r.receives_family_comms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows2.mappings().all()
    ]
    return out


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


class FeeMemberIn(BaseModel):
    org_id: str
    fee_member_id: str
    relationship: Optional[str] = Field(None, max_length=80)
    is_guardian: bool = False


@router.post("/{family_id}/members/fee-member")
async def add_fee_member(
    family_id: str,
    body: FeeMemberIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    """Add a non-playing member (typically a parent/guardian) to a family —
    the fee_member-based counterpart to add_member above (which is
    player-only). See routers/fees.py — a "manual member" with player_id NULL
    already covers parents; this just links their existing FeeMember row into
    the family structure."""
    fam = await db.get(Family, uuid.UUID(family_id))
    if not fam or str(fam.organisation_id) != body.org_id:
        raise HTTPException(status_code=404, detail="Family not found")
    fmember = await db.get(FeeMember, uuid.UUID(body.fee_member_id))
    if not fmember or str(fmember.organisation_id) != body.org_id:
        raise HTTPException(status_code=404, detail="Member not found in this organisation")
    dupe = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == fam.id, FamilyMember.fee_member_id == fmember.id,
        )
    )
    if dupe.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This member is already in this family")
    rel = (body.relationship or "").strip() or None
    fm_row = FamilyMember(family_id=fam.id, fee_member_id=fmember.id, relationship_label=rel, is_guardian=body.is_guardian)
    db.add(fm_row)
    await db.execute(text("UPDATE families SET updated_at = NOW() WHERE id = :fid"), {"fid": str(fam.id)})
    await log_activity(
        db, org_id=fam.organisation_id, user_id=current_user.id,
        action="add_family_member", target_type="family", target_id=str(fam.id),
        details={"family": fam.name, "member": fmember.full_name, "relationship": rel},
    )
    await db.commit()
    members = await _load_family_members(db, fam.id)
    return {"members": members}


class FeeMemberPatchIn(BaseModel):
    org_id: str
    relationship: Optional[str] = Field(None, max_length=80)
    is_guardian: Optional[bool] = None
    receives_family_comms: Optional[bool] = None


@router.patch("/{family_id}/members/fee-member/{fee_member_id}")
async def update_fee_member(
    family_id: str,
    fee_member_id: str,
    body: FeeMemberPatchIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    fam = await db.get(Family, uuid.UUID(family_id))
    if not fam or str(fam.organisation_id) != body.org_id:
        raise HTTPException(status_code=404, detail="Family not found")
    row = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == fam.id, FamilyMember.fee_member_id == uuid.UUID(fee_member_id),
        )
    )
    frow = row.scalar_one_or_none()
    if not frow:
        raise HTTPException(status_code=404, detail="Member not found")
    if body.relationship is not None:
        frow.relationship_label = body.relationship.strip() or None
    if body.is_guardian is not None:
        frow.is_guardian = body.is_guardian
    if body.receives_family_comms is not None:
        frow.receives_family_comms = body.receives_family_comms
    await db.execute(text("UPDATE families SET updated_at = NOW() WHERE id = :fid"), {"fid": str(fam.id)})
    await db.commit()
    return {"status": "ok"}


@router.delete("/{family_id}/members/fee-member/{fee_member_id}")
async def remove_fee_member(
    family_id: str,
    fee_member_id: str,
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    fam = await db.get(Family, uuid.UUID(family_id))
    if not fam or str(fam.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Family not found")
    row = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == fam.id, FamilyMember.fee_member_id == uuid.UUID(fee_member_id),
        )
    )
    frow = row.scalar_one_or_none()
    if not frow:
        raise HTTPException(status_code=404, detail="Member not found")
    await db.delete(frow)
    await db.execute(text("UPDATE families SET updated_at = NOW() WHERE id = :fid"), {"fid": str(fam.id)})
    await log_activity(
        db, org_id=fam.organisation_id, user_id=current_user.id,
        action="remove_family_member", target_type="family", target_id=str(fam.id),
        details={"family": fam.name, "fee_member_id": fee_member_id},
    )
    await db.commit()
    return {"status": "removed"}


@router.get("/{family_id}/financials")
async def family_financials(
    family_id: str,
    org_id: str,
    season_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_cap(MANAGE_FAMILIES)),
):
    """A read-only rollup of what this family owes for one season — sums each
    member's own individual BetterFees record. This is "one view for one
    payment conversation with the family", NOT a new combined-invoicing
    engine (billing still happens per member underneath) — that's real,
    separate follow-on work, not built here."""
    fam = await db.get(Family, uuid.UUID(family_id))
    if not fam or str(fam.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Family not found")
    season = await db.get(Season, uuid.UUID(season_id))
    if not season or str(season.organisation_id) != uuid.UUID(org_id):
        raise HTTPException(status_code=404, detail="Season not found")

    fam_members = (await db.execute(
        select(FamilyMember).where(FamilyMember.family_id == fam.id)
    )).scalars().all()
    member_ids: set = set()
    for frow in fam_members:
        if frow.fee_member_id:
            member_ids.add(frow.fee_member_id)
        elif frow.player_id:
            m = (await db.execute(
                select(FeeMember).where(FeeMember.organisation_id == uuid.UUID(org_id), FeeMember.player_id == frow.player_id)
            )).scalars().first()
            if m:
                member_ids.add(m.id)

    days_map = await _days_by_member_season(db, season.id)
    paid_map = await _paid_by_member_season(db, season.id)
    waived_map = await _waived_days_by_member_season(db, season.id)

    members_out = []
    totals = {"total_payable": 0.0, "total_paid": 0.0, "total_outstanding": 0.0}
    for mid in member_ids:
        m = await db.get(FeeMember, mid)
        ms = (await db.execute(
            select(FeeMemberSeason).where(FeeMemberSeason.member_id == mid, FeeMemberSeason.season_id == season.id)
        )).scalars().first()
        if ms is None or m is None:
            continue
        schedule = await db.get(FeeSchedule, ms.fee_schedule_id) if ms.fee_schedule_id else None
        fin = _financials(schedule, days_map.get(ms.id, 0.0), paid_map.get(ms.id), waived_map.get(ms.id, 0.0))
        members_out.append({"member_id": str(mid), "full_name": m.full_name, "status": ms.status, **fin})
        totals["total_payable"] += fin["total_payable"]
        totals["total_paid"] += fin["total_paid"]
        totals["total_outstanding"] += fin["total_outstanding"]
    totals = {k: round(v, 2) for k, v in totals.items()}

    return {"family": {"id": str(fam.id), "name": fam.name}, "members": members_out, "totals": totals}


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
