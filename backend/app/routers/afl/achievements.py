"""AFL Awards — record who actually won which award each season.

Ported from cricket's routers/achievements.py, trimmed to core CRUD + CSV
import (skips cricket's PDF/URL auto-parse convenience endpoints — a
nice-to-have, not needed for parity with what was asked). ``season`` here is
a plain free-text label (e.g. "2025") rather than a season UUID — cricket's
season-alias resolution doesn't apply to AFL, so this stays simple.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_AWARDS, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club, get_current_user
from app.services.import_ingest import match_players

router = APIRouter(prefix="/achievements", tags=["afl-achievements"])

CATEGORIES = ["Club Award", "Premiership", "Office Bearer", "Milestone", "Hall of Fame", "Life Membership"]

TEMPLATE_ROWS = [
    ("2025", "Club Award", "Season", "Best & Fairest", "Smith, John", ""),
    ("2025", "Club Award", "A Grade", "Leading Goalkicker", "Jones, Mary", "42 goals"),
    ("2025", "Premiership", "A Grade", "Premiership", "Smith, John", "captain"),
    ("2025", "Milestone", "Games", "100 Games", "Smith, John", ""),
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


async def _resolve_players_bulk(db: AsyncSession, names: list[str], org_id: str) -> dict:
    result = await db.execute(text("SELECT id, name FROM players WHERE organisation_id = :org_id"), {"org_id": org_id})
    roster = [(str(r["id"]), r["name"]) for r in result.mappings().all()]
    raw = match_players([n for n in {*names} if n], roster)
    out: dict = {}
    for name, m in raw.items():
        pid = m.get("player_id")
        conf = m.get("confidence") or 0.0
        cands = m.get("candidates") or []
        if pid:
            out[name] = {"player_id": pid, "matched_name": m.get("matched_name"),
                         "confidence": conf, "status": "exact" if conf >= 1.0 else "auto"}
        elif len(cands) == 1 and (cands[0].get("confidence") or 0) >= 0.9:
            out[name] = {"player_id": cands[0]["player_id"], "matched_name": cands[0]["name"],
                         "confidence": cands[0].get("confidence") or 0.9, "status": "auto"}
        elif cands:
            out[name] = {"player_id": None, "confidence": conf, "status": "suggest", "candidates": cands}
        else:
            out[name] = {"player_id": None, "confidence": conf, "status": "none"}
    return out


@router.get("")
async def list_achievements(
    player_id: Optional[str] = None,
    season: Optional[str] = None,
    club: Organisation = Depends(get_current_club),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = str(club.id)
    params: dict = {"org_id": org_id}
    base_filter = "org_id = :org_id"
    if player_id:
        base_filter += " AND player_id = :player_id"
        params["player_id"] = player_id
    if season:
        base_filter += " AND season = :season"
        params["season"] = season

    rows = await db.execute(text(f"""
        SELECT id, org_id, player_id, player_name, season, season_end,
               category, subcategory, achievement, detail, created_at
        FROM player_achievements
        WHERE {base_filter}
        ORDER BY season DESC NULLS LAST, category, id
    """), params)
    return [dict(r) for r in rows.mappings().all()]


class AchievementCreate(BaseModel):
    player_id: Optional[str] = None
    player_name: str
    season: Optional[str] = None
    season_end: Optional[str] = None
    category: str
    subcategory: Optional[str] = None
    achievement: str
    detail: Optional[str] = None


@router.post("")
async def create_achievement(
    body: AchievementCreate,
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    db: AsyncSession = Depends(get_db),
):
    org_id = str(club.id)
    player_id = body.player_id
    if not player_id:
        matches = await _resolve_players_bulk(db, [body.player_name], org_id)
        m = matches.get(body.player_name.strip())
        if m and m.get("status") == "exact":
            player_id = m.get("player_id")

    result = await db.execute(text("""
        INSERT INTO player_achievements
            (org_id, player_id, player_name, season, season_end, category, subcategory, achievement, detail)
        VALUES (:org_id, :player_id, :player_name, :season, :season_end, :category, :subcategory, :achievement, :detail)
        RETURNING id
    """), {
        "org_id": org_id, "player_id": player_id, "player_name": body.player_name,
        "season": body.season or None, "season_end": body.season_end or None,
        "category": body.category, "subcategory": body.subcategory or None,
        "achievement": body.achievement, "detail": body.detail or None,
    })
    new_id = result.scalar()
    await db.commit()
    return {"id": new_id, "status": "created"}


class AchievementUpdate(BaseModel):
    player_name: Optional[str] = None
    player_id: Optional[str] = None
    season: Optional[str] = None
    season_end: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    achievement: Optional[str] = None
    detail: Optional[str] = None


@router.put("/{achievement_id}")
async def update_achievement(
    achievement_id: int,
    body: AchievementUpdate,
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    db: AsyncSession = Depends(get_db),
):
    sets = []
    params: dict = {"id": achievement_id, "org_id": str(club.id)}
    for field in ["player_name", "player_id", "season", "season_end", "category", "subcategory", "achievement", "detail"]:
        val = getattr(body, field)
        if val is not None:
            sets.append(f"{field} = :{field}")
            params[field] = val
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    await db.execute(text(
        f"UPDATE player_achievements SET {', '.join(sets)} WHERE id = :id AND org_id = :org_id"
    ), params)
    await db.commit()
    return {"status": "updated"}


@router.delete("/{achievement_id}")
async def delete_achievement(
    achievement_id: int,
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(text(
        "DELETE FROM player_achievements WHERE id = :id AND org_id = :org_id"
    ), {"id": achievement_id, "org_id": str(club.id)})
    await db.commit()
    return {"status": "deleted"}


@router.get("/template")
async def download_template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Season", "Category", "Subcategory", "Achievement", "Player Name", "Detail"])
    writer.writerows(TEMPLATE_ROWS)
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=afl_achievements_template.csv"},
    )


def _parse_csv(content: bytes) -> list[dict]:
    text_content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text_content))
    return [
        {k.strip().lower().replace(" ", "_"): (v.strip() if v else "") for k, v in row.items()}
        for row in reader if any(row.values())
    ]


@router.post("/import")
async def import_achievements(
    file: UploadFile = File(...),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    db: AsyncSession = Depends(get_db),
):
    org_id = str(club.id)
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(status_code=400, detail="No data found in file")

    matches = await _resolve_players_bulk(db, [row.get("player_name", "").strip() for row in rows], org_id)
    batch_id = uuid.uuid4()
    created = 0
    skipped = 0
    errors = []

    for i, row in enumerate(rows, 2):
        player_name = row.get("player_name", "").strip()
        category = row.get("category", "").strip()
        achievement = row.get("achievement", "").strip()
        if not player_name or not category or not achievement:
            skipped += 1
            continue
        if category not in CATEGORIES:
            errors.append(f"Row {i}: unknown category '{category}'")
            skipped += 1
            continue
        m = matches.get(player_name, {})
        player_id = m.get("player_id") if m.get("status") in ("exact", "auto") else None

        await db.execute(text("""
            INSERT INTO player_achievements
                (org_id, player_id, player_name, season, category, subcategory, achievement, detail, import_batch_id)
            VALUES (:org_id, :player_id, :player_name, :season, :category, :subcategory, :achievement, :detail, :batch_id)
        """), {
            "org_id": org_id, "player_id": player_id, "player_name": player_name,
            "season": row.get("season", "").strip() or None,
            "category": category, "subcategory": row.get("subcategory", "").strip() or None,
            "achievement": achievement, "detail": row.get("detail", "").strip() or None,
            "batch_id": str(batch_id),
        })
        created += 1

    await db.execute(text("""
        INSERT INTO achievement_import_batches (id, org_id, filename, row_count, created_count, status)
        VALUES (:id, :org_id, :filename, :row_count, :created_count, 'imported')
    """), {"id": str(batch_id), "org_id": org_id, "filename": file.filename,
           "row_count": len(rows), "created_count": created})

    await db.commit()
    return {"batch_id": str(batch_id), "created": created, "skipped": skipped, "errors": errors}


@router.get("/imports")
async def list_import_batches(
    club: Organisation = Depends(get_current_club),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(text("""
        SELECT id, filename, row_count, created_count, status, created_at, undone_at
        FROM achievement_import_batches WHERE org_id = :org_id
        ORDER BY created_at DESC
    """), {"org_id": str(club.id)})
    return [dict(r) for r in rows.mappings().all()]


@router.post("/imports/{batch_id}/undo")
async def undo_import_batch(
    batch_id: str,
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    db: AsyncSession = Depends(get_db),
):
    org_id = str(club.id)
    batch = await db.execute(text(
        "SELECT id FROM achievement_import_batches WHERE id = :id AND org_id = :org_id AND undone_at IS NULL"
    ), {"id": batch_id, "org_id": org_id})
    if batch.first() is None:
        raise HTTPException(status_code=404, detail="Import batch not found or already undone")

    result = await db.execute(text(
        "DELETE FROM player_achievements WHERE import_batch_id = :batch_id AND org_id = :org_id"
    ), {"batch_id": batch_id, "org_id": org_id})
    await db.execute(text(
        "UPDATE achievement_import_batches SET undone_at = NOW(), status = 'undone' WHERE id = :id"
    ), {"id": batch_id})
    await db.commit()
    return {"status": "undone", "removed": result.rowcount}
