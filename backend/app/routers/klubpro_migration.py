"""KlubPro → BetterStats migration tooling (super-admin onboarding only).

An operator-facing wizard, integrated into the admin app, that reviews staged
KlubPro data (held in the external KlubPro Postgres' ``klubpro_migration`` schema)
and imports player profile fields + sponsors into BetterStats — with a dry-run
preview, per-row backup, and one-click rollback.

Gated by ``require_super_admin`` (cross-club platform tooling, not a per-club
capability) and by KlubPro being configured (`KLUBPRO_DATABASE_URL`). Reads two
databases: ``get_db`` (BetterStats, read+write) and ``get_klubpro_db`` (KlubPro,
read + operator-decision writes only).
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    KlubproMigrationBackup, KlubproMigrationBatch, Organisation, User, get_db,
)
from app.routers.auth import require_super_admin
from app.services import klubpro_migration as svc
from app.services.klubpro_db import get_klubpro_db, klubpro_configured

router = APIRouter(prefix="/club-admin/klubpro", tags=["klubpro-migration"])


def _require_configured():
    if not klubpro_configured():
        raise HTTPException(
            status_code=400,
            detail="KlubPro migration is not configured on this server "
                   "(KLUBPRO_DATABASE_URL is unset).",
        )


def _parse_uuid(value: str, what: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid {what}")


async def _resolve_club(kp: AsyncSession, bs: AsyncSession, club_mapping_id: str) -> tuple[dict, uuid.UUID]:
    """Load the club mapping + validate its BetterStats org exists. Returns (mapping, org_id)."""
    cm = await svc.fetch_club_mapping(kp, _parse_uuid(club_mapping_id, "club_mapping_id"))
    if not cm:
        raise HTTPException(status_code=404, detail="Club mapping not found")
    org_id_str = cm.get("betterstats_organisation_id")
    if not org_id_str:
        raise HTTPException(status_code=400, detail="Club mapping has no BetterStats organisation")
    org_id = _parse_uuid(org_id_str, "organisation_id")
    org = await bs.get(Organisation, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Mapped BetterStats organisation not found")
    return cm, org_id


# ── status + dashboard ───────────────────────────────────────────────────────

@router.get("/status")
async def status(current_user: User = Depends(require_super_admin)):
    return {"configured": klubpro_configured()}


@router.get("/dashboard")
async def dashboard(
    current_user: User = Depends(require_super_admin),
    kp: AsyncSession = Depends(get_klubpro_db),
):
    _require_configured()
    return {
        "summary": await svc.fetch_dashboard(kp),
        "club_mappings": await svc.fetch_club_mappings(kp),
    }


@router.get("/organisations")
async def organisations(
    current_user: User = Depends(require_super_admin),
    bs: AsyncSession = Depends(get_db),
):
    """Every BetterStats organisation — populates the per-row mapping dropdown."""
    return {"organisations": await svc.fetch_all_orgs(bs)}


class ClubMappingBody(BaseModel):
    klubpro_club_id: str
    betterstats_organisation_id: str
    force: bool = False  # overwrite even if the org is mapped to another KlubPro club


@router.patch("/club-mapping")
async def upsert_club_mapping(
    body: ClubMappingBody,
    current_user: User = Depends(require_super_admin),
    bs: AsyncSession = Depends(get_db),
    kp: AsyncSession = Depends(get_klubpro_db),
):
    """Map (or remap) a staged KlubPro club to a BetterStats organisation.

    Returns {status:'conflict', ...} (HTTP 200) when the chosen org is already
    mapped to a different KlubPro club and `force` is not set — the UI confirms,
    then retries with force=true. Repeatable / update-safe.
    """
    _require_configured()
    org = await bs.get(Organisation, _parse_uuid(body.betterstats_organisation_id, "betterstats_organisation_id"))
    if not org:
        raise HTTPException(status_code=404, detail="BetterStats organisation not found")
    target = await svc.fetch_target_club(kp, body.klubpro_club_id)
    if not target:
        raise HTTPException(status_code=404, detail="KlubPro target club not found")

    if not body.force:
        other = await svc.org_mapped_elsewhere(kp, body.betterstats_organisation_id, body.klubpro_club_id)
        if other:
            return {
                "status": "conflict",
                "other_klubpro_club_name": other["klubpro_club_name"],
                "message": (
                    f"{org.name} is already mapped to KlubPro club "
                    f"\"{other['klubpro_club_name']}\". Map it to "
                    f"\"{target['klubpro_club_name']}\" as well?"
                ),
            }

    mapping = await svc.upsert_club_mapping(
        kp,
        klubpro_club_id=body.klubpro_club_id,
        klubpro_club_name=target["klubpro_club_name"],
        betterstats_organisation_id=body.betterstats_organisation_id,
        betterstats_organisation_name=org.name,
    )
    return {"status": "ok", "mapping": mapping}


# ── players: review data ─────────────────────────────────────────────────────

@router.get("/clubs/{club_mapping_id}/players")
async def player_review(
    club_mapping_id: str,
    current_user: User = Depends(require_super_admin),
    bs: AsyncSession = Depends(get_db),
    kp: AsyncSession = Depends(get_klubpro_db),
):
    _require_configured()
    cm, org_id = await _resolve_club(kp, bs, club_mapping_id)
    return {
        "club": cm,
        "betterstats_players": await svc.fetch_bs_players(bs, org_id),
        "klubpro_candidates": await svc.fetch_player_candidates(kp, cm["klubpro_club_id"]),
        "matches": await svc.fetch_match_mappings(kp, _parse_uuid(cm["id"])),
    }


class MatchDecision(BaseModel):
    betterstats_player_id: str
    betterstats_player_name: Optional[str] = None
    klubpro_player_id: Optional[str] = None
    klubpro_player_firstname: Optional[str] = None
    klubpro_player_lastname: Optional[str] = None
    klubpro_player_nickname: Optional[str] = None
    decision: str  # 'approve' | 'reject' | 'skip'
    notes: Optional[str] = None


@router.post("/clubs/{club_mapping_id}/players/match")
async def set_match(
    club_mapping_id: str,
    body: MatchDecision,
    current_user: User = Depends(require_super_admin),
    bs: AsyncSession = Depends(get_db),
    kp: AsyncSession = Depends(get_klubpro_db),
):
    _require_configured()
    cm, _ = await _resolve_club(kp, bs, club_mapping_id)
    if body.decision not in ("approve", "reject", "skip"):
        raise HTTPException(status_code=400, detail="decision must be approve|reject|skip")
    if body.decision == "approve" and not body.klubpro_player_id:
        raise HTTPException(status_code=400, detail="Approving a match needs a KlubPro player")
    await svc.upsert_match_mapping(
        kp,
        club_mapping_id=_parse_uuid(cm["id"]),
        betterstats_player_id=_parse_uuid(body.betterstats_player_id, "betterstats_player_id"),
        betterstats_player_name=body.betterstats_player_name,
        klubpro_player_id=body.klubpro_player_id if body.decision == "approve" else None,
        klubpro_player_firstname=body.klubpro_player_firstname,
        klubpro_player_lastname=body.klubpro_player_lastname,
        klubpro_player_nickname=body.klubpro_player_nickname,
        match_status=body.decision,
        approved=(body.decision == "approve"),
        notes=body.notes,
    )
    return {"ok": True}


@router.get("/clubs/{club_mapping_id}/players/dry-run")
async def player_dry_run(
    club_mapping_id: str,
    current_user: User = Depends(require_super_admin),
    bs: AsyncSession = Depends(get_db),
    kp: AsyncSession = Depends(get_klubpro_db),
):
    _require_configured()
    cm, org_id = await _resolve_club(kp, bs, club_mapping_id)
    bs_players = {p["id"]: p for p in await svc.fetch_bs_players(bs, org_id)}
    matches = await svc.fetch_match_mappings(kp, _parse_uuid(cm["id"]))
    approved = [m for m in matches if m.get("approved") and m.get("klubpro_player_id")]

    previews = []
    players_changing = 0
    field_writes = 0
    for m in approved:
        current = bs_players.get(m["betterstats_player_id"])
        if not current:
            previews.append({
                "betterstats_player_id": m["betterstats_player_id"],
                "betterstats_player_name": m.get("betterstats_player_name"),
                "error": "BetterStats player no longer exists",
                "diffs": [],
            })
            continue
        cand = await svc.fetch_player_candidate(kp, m["klubpro_player_id"])
        if not cand:
            previews.append({
                "betterstats_player_id": m["betterstats_player_id"],
                "betterstats_player_name": current["name"],
                "error": "KlubPro candidate no longer staged",
                "diffs": [],
            })
            continue
        diffs = svc.diff_player(current, cand)
        row_changes = sum(1 for d in diffs if d["change"])
        if row_changes:
            players_changing += 1
            field_writes += row_changes
        previews.append({
            "betterstats_player_id": m["betterstats_player_id"],
            "betterstats_player_name": current["name"],
            "klubpro_player_id": m["klubpro_player_id"],
            "klubpro_name": " ".join(
                x for x in [cand.get("firstname"), cand.get("lastname")] if x
            ),
            "diffs": diffs,
            "row_changes": row_changes,
        })
    return {
        "approved_count": len(approved),
        "players_changing": players_changing,
        "field_writes": field_writes,
        "previews": previews,
    }


class ConfirmBody(BaseModel):
    confirm: bool = False


@router.post("/clubs/{club_mapping_id}/players/import")
async def player_import(
    club_mapping_id: str,
    body: ConfirmBody,
    current_user: User = Depends(require_super_admin),
    bs: AsyncSession = Depends(get_db),
    kp: AsyncSession = Depends(get_klubpro_db),
):
    _require_configured()
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Import must be confirmed")
    cm, org_id = await _resolve_club(kp, bs, club_mapping_id)
    result = await svc.execute_player_import(
        bs, kp, org_id=org_id, club_mapping=cm, operator=current_user
    )
    return result


# ── sponsors ─────────────────────────────────────────────────────────────────

@router.get("/clubs/{club_mapping_id}/sponsors")
async def sponsor_review(
    club_mapping_id: str,
    current_user: User = Depends(require_super_admin),
    bs: AsyncSession = Depends(get_db),
    kp: AsyncSession = Depends(get_klubpro_db),
):
    _require_configured()
    cm, org_id = await _resolve_club(kp, bs, club_mapping_id)
    return {
        "club": cm,
        "klubpro_sponsors": await svc.fetch_sponsor_candidates(kp, cm["klubpro_club_id"]),
        "betterstats_sponsors": await svc.fetch_bs_sponsors(bs, org_id),
    }


class SponsorImportBody(BaseModel):
    selected_ids: list[str] = []
    confirm: bool = False


@router.post("/clubs/{club_mapping_id}/sponsors/dry-run")
async def sponsor_dry_run(
    club_mapping_id: str,
    body: SponsorImportBody,
    current_user: User = Depends(require_super_admin),
    bs: AsyncSession = Depends(get_db),
    kp: AsyncSession = Depends(get_klubpro_db),
):
    _require_configured()
    cm, org_id = await _resolve_club(kp, bs, club_mapping_id)
    existing = {s["klubpro_sponsor_id"] for s in await svc.fetch_bs_sponsors(bs, org_id) if s["klubpro_sponsor_id"]}
    candidates = {c["klubpro_sponsor_id"]: c for c in await svc.fetch_sponsor_candidates(kp, cm["klubpro_club_id"])}
    to_insert, dupes, missing = [], [], []
    for sid in body.selected_ids:
        if sid in existing:
            dupes.append(sid)
        elif sid in candidates:
            to_insert.append(candidates[sid])
        else:
            missing.append(sid)
    return {"to_insert": to_insert, "duplicate_skip": dupes, "missing": missing}


@router.post("/clubs/{club_mapping_id}/sponsors/import")
async def sponsor_import(
    club_mapping_id: str,
    body: SponsorImportBody,
    current_user: User = Depends(require_super_admin),
    bs: AsyncSession = Depends(get_db),
    kp: AsyncSession = Depends(get_klubpro_db),
):
    _require_configured()
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Import must be confirmed")
    if not body.selected_ids:
        raise HTTPException(status_code=400, detail="No sponsors selected")
    cm, org_id = await _resolve_club(kp, bs, club_mapping_id)
    return await svc.execute_sponsor_import(
        bs, kp, org_id=org_id, club_mapping=cm,
        selected_ids=body.selected_ids, operator=current_user,
    )


# ── image proxies (KlubPro bytea → browser <img>) ────────────────────────────

@router.get("/images/player/{klubpro_player_id}")
async def klubpro_player_image(
    klubpro_player_id: str,
    thumb: int = Query(0),
    current_user: User = Depends(require_super_admin),
    kp: AsyncSession = Depends(get_klubpro_db),
):
    _require_configured()
    img = await svc.fetch_player_image(kp, klubpro_player_id, thumb=bool(thumb))
    if not img:
        raise HTTPException(status_code=404, detail="No image")
    data, mime = img
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})


@router.get("/images/sponsor/{klubpro_sponsor_id}")
async def klubpro_sponsor_image(
    klubpro_sponsor_id: str,
    current_user: User = Depends(require_super_admin),
    kp: AsyncSession = Depends(get_klubpro_db),
):
    _require_configured()
    img = await svc.fetch_sponsor_logo(kp, klubpro_sponsor_id)
    if not img:
        raise HTTPException(status_code=404, detail="No logo")
    data, mime = img
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})


# ── audit + rollback (BetterStats-only — no KlubPro needed) ───────────────────

@router.get("/batches")
async def list_batches(
    org_id: Optional[str] = None,
    current_user: User = Depends(require_super_admin),
    bs: AsyncSession = Depends(get_db),
):
    q = select(KlubproMigrationBatch).order_by(KlubproMigrationBatch.created_at.desc())
    if org_id:
        q = q.where(KlubproMigrationBatch.organisation_id == _parse_uuid(org_id, "org_id"))
    rows = await bs.execute(q.limit(200))
    out = []
    for b in rows.scalars().all():
        out.append({
            "id": str(b.id), "kind": b.kind,
            "organisation_id": str(b.organisation_id),
            "klubpro_club_id": b.klubpro_club_id, "status": b.status,
            "counts": b.counts, "operator_name": b.operator_name,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "rolled_back_at": b.rolled_back_at.isoformat() if b.rolled_back_at else None,
        })
    return {"batches": out}


@router.post("/batches/{batch_id}/rollback")
async def rollback(
    batch_id: str,
    current_user: User = Depends(require_super_admin),
    bs: AsyncSession = Depends(get_db),
):
    batch = await bs.get(KlubproMigrationBatch, _parse_uuid(batch_id, "batch_id"))
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status == "rolled_back":
        raise HTTPException(status_code=400, detail="Batch already rolled back")
    result = await svc.rollback_batch(bs, batch)
    return {"ok": True, **result}
