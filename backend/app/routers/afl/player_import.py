"""Import Players — CSV contact-info importer.

AFL's PlayHQ sync already discovers every player automatically from game-line
stats (see docs/afl-betterstats-plan.md), so unlike cricket there's no second
roster-discovery job here. This is a **contact-details** importer: upload a
club spreadsheet of names + emails/phones, match each name against players
already in the system (``import_ingest.match_players`` — the same matcher
used site-wide), and fill in the blanks. A blank cell never overwrites a
value a player already has, and nothing is ever auto-created — an unmatched
row is just skipped (a lighter-weight flow than cricket's equivalent, which
also handles squad assignment; deliberately simplified here since AFL has no
squad concept yet).

Flow: POST /preview (upload → parsed rows + suggested matches) → POST /commit
(rows + confirmed player_id per row → write).
"""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_PLAYERS, require_cap
from app.models.db import Organisation, Player, User, get_db
from app.routers.auth import get_current_club
from app.services.import_ingest import match_players

router = APIRouter(prefix="/club-admin/player-import", tags=["afl-player-import"])

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@router.get("/template.csv")
async def download_template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Email", "Phone", "Gender"])
    writer.writerow(["Smith, John", "john.smith@example.com", "0400 000 000", "male"])
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=afl_player_contacts_template.csv"},
    )


def _parse_csv(content: bytes) -> list[dict]:
    text_content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text_content))
    return [
        {(k or "").strip().lower(): (v.strip() if v else "") for k, v in row.items()}
        for row in reader if any(row.values())
    ]


@router.post("/preview")
async def preview_import(
    file: UploadFile = File(...),
    current_user: User = Depends(require_cap(MANAGE_PLAYERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(status_code=400, detail="No data found in file")

    roster_res = await db.execute(select(Player.id, Player.name, Player.display_name_override)
                                   .where(Player.organisation_id == club.id))
    roster = [(str(r.id), r.display_name_override or r.name) for r in roster_res]

    names = [row.get("name", "").strip() for row in rows if row.get("name", "").strip()]
    matches = match_players(names, roster)

    out = []
    for row in rows:
        name = row.get("name", "").strip()
        if not name:
            continue
        m = matches.get(name, {"player_id": None, "status": "none", "candidates": []})
        out.append({
            "name": name,
            "email": row.get("email", "").strip() or None,
            "phone": row.get("phone", "").strip() or None,
            "gender": row.get("gender", "").strip() or None,
            "player_id": m.get("player_id"),
            "matched_name": m.get("matched_name"),
            "confidence": m.get("confidence"),
            "status": m.get("status"),
            "candidates": m.get("candidates", []),
        })
    return {"rows": out, "roster_size": len(roster)}


class CommitRow(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    player_id: Optional[str] = None  # None/omitted → row is skipped


class CommitRequest(BaseModel):
    rows: list[CommitRow]


@router.post("/commit")
async def commit_import(
    body: CommitRequest,
    current_user: User = Depends(require_cap(MANAGE_PLAYERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    updated = 0
    skipped = 0
    for row in body.rows:
        if not row.player_id:
            skipped += 1
            continue
        player = await db.get(Player, row.player_id)
        if not player or player.organisation_id != club.id:
            skipped += 1
            continue
        changed = False
        if row.email and not player.email:
            player.email = row.email
            changed = True
        if row.phone and not player.phone:
            player.phone = row.phone
            changed = True
        if row.gender and not player.gender:
            player.gender = row.gender
            changed = True
        if changed:
            updated += 1
    await db.commit()
    return {"status": "ok", "updated": updated, "skipped": skipped}
