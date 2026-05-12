"""Admin API routes — all require authentication."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import uuid
import io
import csv
import re

from app.models.db import (
    User, Organisation, ClubMembership, Player, Season, Grade, ManualPartnershipRecord,
    PlayerSyncRequest, PhqIdSuggestion, get_db
)
from sqlalchemy import text as _text
import asyncio
import logging as _logging
from app.routers.auth import get_current_user, get_current_club, require_super_admin, _hash_password

# Keep strong references to background tasks so they aren't GC'd before completing
_background_tasks: set = set()
# Per-org scan locks to prevent concurrent PHQ suggestion scans
_phq_scan_running: set = set()
# Per-player deep sync locks
_player_sync_running: set = set()

router = APIRouter(prefix="/club-admin", tags=["club-admin"])


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

@router.get("/players")
async def list_players(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Player).where(Player.organisation_id == club.id).order_by(Player.name)
    )
    players = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "display_name": p.display_name,
            "display_name_override": p.display_name_override,
            "playhq_id": p.playhq_id,
        }
        for p in players
    ]


class PlayerPatch(BaseModel):
    display_name_override: Optional[str] = None
    playhq_id: Optional[str] = None


@router.patch("/players/{player_id}")
async def patch_player(
    player_id: str,
    data: PlayerPatch,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")

    if data.display_name_override is not None:
        player.display_name_override = data.display_name_override.strip() or None
    if data.playhq_id is not None:
        new_phq = data.playhq_id.strip() or None
        if new_phq and new_phq != player.playhq_id:
            # Check no other player in this org already holds this PHQ ID
            conflict = await db.execute(
                select(Player).where(
                    Player.organisation_id == club.id,
                    Player.playhq_id == new_phq,
                    Player.id != player.id,
                )
            )
            if conflict.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Another player already has this PlayHQ ID")
        player.playhq_id = new_phq
    await db.commit()
    return {
        "id": str(player.id),
        "display_name": player.display_name,
        "display_name_override": player.display_name_override,
        "playhq_id": player.playhq_id,
    }


# ---------------------------------------------------------------------------
# Seasons
# ---------------------------------------------------------------------------

@router.get("/seasons")
async def list_seasons(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Season)
        .where(Season.organisation_id == club.id)
        .order_by(Season.year.desc().nullslast(), Season.name.desc())
    )
    seasons = result.scalars().all()
    return [
        {"id": str(s.id), "name": s.name, "year": s.year, "synced_at": s.synced_at}
        for s in seasons
    ]


# ---------------------------------------------------------------------------
# Games (read-only list — PlayHQ is source of truth)
# ---------------------------------------------------------------------------

@router.get("/games")
async def list_games(
    season_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    query = """
        SELECT g.id, g.played_at, g.home_team, g.away_team, g.result, g.winning_team,
               gr.name AS grade_name, s.name AS season_name
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org_id
    """
    params: dict = {"org_id": str(club.id)}
    if season_id:
        query += " AND s.id = :season_id"
        params["season_id"] = season_id
    query += " ORDER BY g.played_at DESC LIMIT 200"

    rows = await db.execute(text(query), params)
    return [
        {
            "id": str(r.id),
            "played_at": r.played_at.isoformat() if r.played_at else None,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "result": r.result,
            "winning_team": r.winning_team,
            "grade": r.grade_name,
            "season": r.season_name,
        }
        for r in rows.mappings().all()
    ]


# ---------------------------------------------------------------------------
# Club settings
# ---------------------------------------------------------------------------

class SettingsPatch(BaseModel):
    name: Optional[str] = None
    contact_email: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    theme_mode: Optional[str] = None


@router.get("/settings")
async def get_settings(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
):
    return {
        "id": str(club.id),
        "slug": club.slug,
        "name": club.name,
        "short_name": club.short_name,
        "contact_email": club.contact_email,
        "primary_color": club.primary_color,
        "accent_color": club.accent_color,
        "theme_mode": club.theme_mode,
        "logo_url": club.logo_url,
        "hero_image_url": club.hero_image_url,
        "is_active": club.is_active,
        "playhq_id": club.playhq_id,
    }


@router.patch("/settings")
async def patch_settings(
    data: SettingsPatch,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if data.name is not None:
        club.name = data.name.strip()
    if data.contact_email is not None:
        club.contact_email = data.contact_email.strip() or None
    if data.primary_color is not None:
        club.primary_color = data.primary_color.strip()
    if data.accent_color is not None:
        club.accent_color = data.accent_color.strip()
    if data.theme_mode is not None and data.theme_mode in ("light", "dark", "auto"):
        club.theme_mode = data.theme_mode
    await db.commit()
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Manual partnership records
# ---------------------------------------------------------------------------

class ManualPartnershipCreate(BaseModel):
    batter1_id: Optional[str] = None
    batter1_name: str
    batter2_id: Optional[str] = None
    batter2_name: str
    grade_name: str
    season_year: int
    wicket_number: int
    runs: int
    is_not_out: bool = False
    notes: Optional[str] = None


@router.get("/partnership-records")
async def list_partnership_records(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ManualPartnershipRecord)
        .where(ManualPartnershipRecord.org_id == club.id)
        .order_by(ManualPartnershipRecord.runs.desc())
    )
    records = result.scalars().all()
    return [
        {
            "id": r.id,
            "batter1_id": str(r.batter1_id) if r.batter1_id else None,
            "batter1_name": r.batter1_name,
            "batter2_id": str(r.batter2_id) if r.batter2_id else None,
            "batter2_name": r.batter2_name,
            "grade_name": r.grade_name,
            "season_year": r.season_year,
            "wicket_number": r.wicket_number,
            "runs": r.runs,
            "is_not_out": r.is_not_out,
            "notes": r.notes,
        }
        for r in records
    ]


@router.post("/partnership-records", status_code=201)
async def create_partnership_record(
    data: ManualPartnershipCreate,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    record = ManualPartnershipRecord(
        org_id=club.id,
        batter1_id=uuid.UUID(data.batter1_id) if data.batter1_id else None,
        batter1_name=data.batter1_name.strip(),
        batter2_id=uuid.UUID(data.batter2_id) if data.batter2_id else None,
        batter2_name=data.batter2_name.strip(),
        grade_name=data.grade_name.strip(),
        season_year=data.season_year,
        wicket_number=data.wicket_number,
        runs=data.runs,
        is_not_out=data.is_not_out,
        notes=data.notes,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"id": record.id, "status": "created"}


@router.delete("/partnership-records/{record_id}", status_code=204)
async def delete_partnership_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ManualPartnershipRecord).where(
            ManualPartnershipRecord.id == record_id,
            ManualPartnershipRecord.org_id == club.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    await db.delete(record)
    await db.commit()


class ManualPartnershipPatch(BaseModel):
    batter1_id: Optional[str] = None
    batter1_name: Optional[str] = None
    batter2_id: Optional[str] = None
    batter2_name: Optional[str] = None
    grade_name: Optional[str] = None
    season_year: Optional[int] = None
    wicket_number: Optional[int] = None
    runs: Optional[int] = None
    is_not_out: Optional[bool] = None
    notes: Optional[str] = None


@router.patch("/partnership-records/{record_id}")
async def patch_partnership_record(
    record_id: int,
    data: ManualPartnershipPatch,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ManualPartnershipRecord).where(
            ManualPartnershipRecord.id == record_id,
            ManualPartnershipRecord.org_id == club.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    fields = data.model_fields_set
    if 'batter1_id' in fields:
        record.batter1_id = uuid.UUID(data.batter1_id) if data.batter1_id else None
    if 'batter1_name' in fields and data.batter1_name is not None:
        record.batter1_name = data.batter1_name.strip()
    if 'batter2_id' in fields:
        record.batter2_id = uuid.UUID(data.batter2_id) if data.batter2_id else None
    if 'batter2_name' in fields and data.batter2_name is not None:
        record.batter2_name = data.batter2_name.strip()
    if 'grade_name' in fields and data.grade_name is not None:
        record.grade_name = data.grade_name.strip()
    if 'season_year' in fields and data.season_year is not None:
        record.season_year = data.season_year
    if 'wicket_number' in fields and data.wicket_number is not None:
        record.wicket_number = data.wicket_number
    if 'runs' in fields and data.runs is not None:
        record.runs = data.runs
    if 'is_not_out' in fields:
        record.is_not_out = data.is_not_out
    if 'notes' in fields:
        record.notes = data.notes
    await db.commit()
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Partnership records — template & bulk import
# ---------------------------------------------------------------------------

_PARTNERSHIP_TEMPLATE_ROWS = [
    ("Matthew Edwards", "Pratik Bhave", "147", "3", "2024", "No", "1st XI"),
    ("Jack Barendse", "Chris Cooper", "98", "1", "2023", "Yes", "2nd XI"),
]

ORDINAL_MAP = {
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
    "6th": 6, "7th": 7, "8th": 8, "9th": 9, "10th": 10,
}


def _normalise_name(name: str) -> str:
    name = name.strip()
    if ", " in name:
        parts = name.split(", ", 1)
        name = f"{parts[1]} {parts[0]}"
    return re.sub(r"\s+", " ", name).lower()


def _parse_xlsx_partnerships(content: bytes) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip().lower().replace(" ", "_") if h else "" for h in rows[0]]
    result = []
    for row in rows[1:]:
        if not any(row):
            continue
        d = {headers[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row) if i < len(headers)}
        result.append(d)
    return result


def _parse_csv_partnerships(content: bytes) -> list[dict]:
    text_content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text_content))
    return [
        {k.strip().lower().replace(" ", "_"): (v.strip() if v else "")
         for k, v in row.items()}
        for row in reader
        if any(row.values())
    ]


@router.get("/partnership-records/template")
async def download_partnership_template(
    current_user: User = Depends(get_current_user),
):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Batter 1", "Batter 2", "Runs", "Wicket", "Season", "Not Out", "Grade"])
    writer.writerows(_PARTNERSHIP_TEMPLATE_ROWS)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=partnership_records_template.csv"},
    )


@router.post("/partnership-records/import")
async def import_partnership_records(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _do_import_partnership_records(file, club, db)
    except HTTPException:
        raise
    except Exception as exc:
        _logging.getLogger(__name__).error("Partnership import failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}")


async def _do_import_partnership_records(file, club, db):
    content = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        rows = _parse_xlsx_partnerships(content)
    else:
        rows = _parse_csv_partnerships(content)

    if not rows:
        raise HTTPException(status_code=400, detail="No data found in file")

    # Build name→id map for this org
    players_result = await db.execute(
        _text("SELECT id, name FROM players WHERE organisation_id = :org_id"),
        {"org_id": str(club.id)},
    )
    player_map: dict[str, str] = {
        _normalise_name(row["name"]): str(row["id"])
        for row in players_result.mappings().all()
    }

    created_records = []
    skipped = 0
    errors = []

    for i, row in enumerate(rows, 2):
        b1_name = (row.get("batter_1") or row.get("batter1") or "").strip()
        b2_name = (row.get("batter_2") or row.get("batter2") or "").strip()
        runs_raw = row.get("runs", "").strip()
        wicket_raw = row.get("wicket", "").strip()
        season_raw = row.get("season", "").strip()
        not_out_raw = (row.get("not_out") or row.get("not_out_(y/n)") or "").strip().lower()
        grade = row.get("grade", "").strip()

        if not b1_name or not b2_name or not runs_raw or not grade or not season_raw:
            skipped += 1
            continue

        try:
            runs = int(float(runs_raw))
            season_year = int(float(season_raw))
        except ValueError:
            errors.append(f"Row {i}: invalid runs or season value")
            skipped += 1
            continue

        # Accept ordinal strings ("1st", "3rd") or plain integers for wicket
        wicket_number = ORDINAL_MAP.get(wicket_raw.lower())
        if wicket_number is None:
            try:
                wicket_number = int(float(wicket_raw)) if wicket_raw else 0
            except ValueError:
                wicket_number = 0
        if wicket_number < 1 or wicket_number > 10:
            errors.append(f"Row {i}: wicket must be 1–10 (got '{wicket_raw}')")
            skipped += 1
            continue

        is_not_out = not_out_raw in ("yes", "y", "true", "1")

        b1_id = player_map.get(_normalise_name(b1_name))
        b2_id = player_map.get(_normalise_name(b2_name))

        # Check for potential GR duplicate (only when both IDs resolved)
        gr_duplicate = None
        if b1_id and b2_id:
            dup_res = await db.execute(_text("""
                SELECT pt.runs, pt.wicket_number,
                       EXTRACT(YEAR FROM g.played_at)::int AS season_year,
                       gr.name AS grade_name
                FROM partnerships pt
                JOIN games g ON g.id = pt.game_id
                JOIN grades gr ON gr.id = g.grade_id
                WHERE pt.runs = :runs
                  AND pt.wicket_number = :wicket
                  AND EXTRACT(YEAR FROM g.played_at)::int = :season_year
                  AND (
                    (pt.batter1_id = CAST(:b1_id AS uuid) AND pt.batter2_id = CAST(:b2_id AS uuid)) OR
                    (pt.batter1_id = CAST(:b2_id AS uuid) AND pt.batter2_id = CAST(:b1_id AS uuid))
                  )
                LIMIT 1
            """), {
                "runs": runs,
                "wicket": wicket_number,
                "season_year": season_year,
                "b1_id": b1_id,
                "b2_id": b2_id,
            })
            dup_row = dup_res.mappings().first()
            if dup_row:
                gr_duplicate = {
                    "runs": int(dup_row["runs"]) if dup_row["runs"] is not None else None,
                    "wicket_number": int(dup_row["wicket_number"]) if dup_row["wicket_number"] is not None else None,
                    "season_year": int(dup_row["season_year"]) if dup_row["season_year"] is not None else None,
                    "grade_name": str(dup_row["grade_name"]) if dup_row["grade_name"] is not None else None,
                }

        record = ManualPartnershipRecord(
            org_id=club.id,
            batter1_id=uuid.UUID(b1_id) if b1_id else None,
            batter1_name=b1_name,
            batter2_id=uuid.UUID(b2_id) if b2_id else None,
            batter2_name=b2_name,
            grade_name=grade,
            season_year=season_year,
            wicket_number=wicket_number,
            runs=runs,
            is_not_out=is_not_out,
        )
        db.add(record)
        await db.flush()

        created_records.append({
            "id": record.id,
            "batter1_name": b1_name,
            "batter1_id": b1_id,
            "batter1_unmatched": b1_id is None,
            "batter2_name": b2_name,
            "batter2_id": b2_id,
            "batter2_unmatched": b2_id is None,
            "runs": runs,
            "wicket_number": wicket_number,
            "season_year": season_year,
            "grade_name": grade,
            "is_not_out": is_not_out,
            "gr_duplicate": gr_duplicate,
        })

    await db.commit()

    return {
        "created": len(created_records),
        "skipped": skipped,
        "errors": errors,
        "records": created_records,
    }


@router.get("/grades")
async def list_grades(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        _text("""
            SELECT DISTINCT gr.name
            FROM grades gr
            JOIN seasons se ON se.id = gr.season_id
            WHERE se.organisation_id = :org_id
            ORDER BY gr.name
        """),
        {"org_id": str(club.id)},
    )
    return [r["name"] for r in result.mappings().all()]


class PartnershipGradeRename(BaseModel):
    old_name: str
    new_name: str


@router.post("/partnership-records/rename-grade")
async def rename_partnership_grade(
    data: PartnershipGradeRename,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        _text("""
            UPDATE manual_partnership_records
            SET grade_name = :new_name
            WHERE org_id = :org_id AND grade_name = :old_name
        """),
        {"new_name": data.new_name.strip(), "org_id": str(club.id), "old_name": data.old_name},
    )
    await db.commit()
    return {"updated": result.rowcount}


# ---------------------------------------------------------------------------
# Super admin — club management
# ---------------------------------------------------------------------------

class ClubCreate(BaseModel):
    name: str
    slug: str
    short_name: Optional[str] = None
    contact_email: Optional[str] = None
    primary_color: str = "#16c784"
    accent_color: str = "#243352"


@router.get("/super/clubs")
async def list_all_clubs(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organisation).order_by(Organisation.name))
    orgs = result.scalars().all()
    return [
        {
            "id": str(o.id),
            "slug": o.slug,
            "name": o.name,
            "short_name": o.short_name,
            "is_active": o.is_active,
            "contact_email": o.contact_email,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orgs
    ]


@router.post("/super/clubs", status_code=201)
async def create_club(
    data: ClubCreate,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    slug = data.slug.lower().strip()
    existing = await db.execute(select(Organisation).where(Organisation.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug already in use")

    org = Organisation(
        id=uuid.uuid4(),
        name=data.name.strip(),
        slug=slug,
        short_name=data.short_name,
        contact_email=data.contact_email,
        primary_color=data.primary_color,
        accent_color=data.accent_color,
        is_active=False,
    )
    db.add(org)
    await db.commit()
    return {"id": str(org.id), "slug": org.slug, "name": org.name}


class ClubActivePatch(BaseModel):
    is_active: bool


@router.patch("/super/clubs/{club_id}")
async def patch_club(
    club_id: str,
    data: ClubActivePatch,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(club_id))
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    org.is_active = data.is_active
    await db.commit()
    return {"id": str(org.id), "is_active": org.is_active}


# ---------------------------------------------------------------------------
# Super admin — user management
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    club_id: str
    role: str = "club_admin"


@router.get("/super/users")
async def list_users(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User, ClubMembership, Organisation)
        .join(ClubMembership, ClubMembership.user_id == User.id, isouter=True)
        .join(Organisation, Organisation.id == ClubMembership.club_id, isouter=True)
        .order_by(User.username)
    )
    rows = result.all()
    return [
        {
            "id": str(r.User.id),
            "username": r.User.username,
            "display_name": r.User.display_name,
            "role": r.ClubMembership.role if r.ClubMembership else None,
            "club_name": r.Organisation.name if r.Organisation else None,
            "club_id": str(r.ClubMembership.club_id) if r.ClubMembership else None,
            "last_login_at": r.User.last_login_at.isoformat() if r.User.last_login_at else None,
            "locked": r.User.locked_until is not None,
        }
        for r in rows
    ]


@router.post("/super/users", status_code=201)
async def create_user(
    data: UserCreate,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    username = data.username.lower().strip()
    if not username or len(username) < 3 or len(username) > 32:
        raise HTTPException(status_code=422, detail="Username must be 3-32 characters")

    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    if len(data.password) < 10:
        raise HTTPException(status_code=422, detail="Password must be at least 10 characters")

    club = await db.get(Organisation, uuid.UUID(data.club_id))
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    user = User(
        username=username,
        password_hash=_hash_password(data.password),
        display_name=data.display_name,
    )
    db.add(user)
    await db.flush()

    membership = ClubMembership(
        club_id=club.id,
        user_id=user.id,
        role=data.role if data.role in ("super_admin", "club_admin") else "club_admin",
    )
    db.add(membership)
    await db.commit()

    return {"id": str(user.id), "username": user.username, "club_id": data.club_id, "role": membership.role}


class PasswordReset(BaseModel):
    new_password: str


@router.post("/super/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    data: PasswordReset,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    if len(data.new_password) < 10:
        raise HTTPException(status_code=422, detail="Password must be at least 10 characters")

    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = _hash_password(data.new_password)
    user.failed_login_count = 0
    user.locked_until = None
    await db.commit()
    return {"status": "password_reset"}


# ---------------------------------------------------------------------------
# Player Sync Requests
# ---------------------------------------------------------------------------

@router.get("/sync-requests")
async def list_sync_requests(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        _text("""
            SELECT
                sr.id, sr.status, sr.requester_note, sr.admin_note,
                sr.created_at, sr.resolved_at,
                p.id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                p.playhq_id
            FROM player_sync_requests sr
            JOIN players p ON p.id = sr.player_id
            WHERE sr.org_id = :org_id
            ORDER BY sr.created_at DESC
            LIMIT 100
        """),
        {"org_id": str(club.id)},
    )
    rows = result.mappings().all()
    return [
        {
            "id": r["id"],
            "status": r["status"],
            "requester_note": r["requester_note"],
            "admin_note": r["admin_note"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
            "player_id": r["player_id"],
            "player_name": r["player_name"],
            "playhq_id": r["playhq_id"],
        }
        for r in rows
    ]


class SyncRequestAction(BaseModel):
    action: str  # "approve" or "dismiss"
    admin_note: Optional[str] = None


@router.post("/sync-requests/{request_id}")
async def action_sync_request(
    request_id: int,
    body: SyncRequestAction,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    req = await db.get(PlayerSyncRequest, request_id)
    if not req or str(req.org_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="Request already resolved")
    if body.action not in ("approve", "dismiss"):
        raise HTTPException(status_code=422, detail="action must be 'approve' or 'dismiss'")

    if body.action == "approve":
        player = await db.get(Player, req.player_id)

        # Pre-checks before approving
        warnings = []
        if not player:
            raise HTTPException(status_code=404, detail="Player no longer exists")
        if not player.playhq_id:
            warnings.append("no_phq_id")
        player_id_str = str(req.player_id)
        if player_id_str in _player_sync_running:
            return {"status": "already_running", "warnings": warnings,
                    "message": "A deep sync is already running for this player"}

        # Return warning to admin without approving yet so they can decide
        if "no_phq_id" in warnings and not body.admin_note:
            return {
                "status": "needs_confirmation",
                "warnings": warnings,
                "message": (
                    f"{player.display_name} has no PlayHQ ID linked — sync will rely on name matching only "
                    "and may miss historical games. Set their PHQ ID first (Admin → PHQ ID Match or Admin → Players), "
                    "then approve again. To proceed anyway, re-approve with any admin note."
                ),
            }

        req.admin_note = body.admin_note
        req.resolved_at = datetime.now(timezone.utc)
        req.status = "approved"
        await db.commit()

        from app.services.sync import deep_sync_player, start_sync_run, finish_sync_run
        _logger = _logging.getLogger(__name__)
        org_id_str = str(club.id)
        _player_sync_running.add(player_id_str)
        run_id = await start_sync_run(club.id, "player_deep", player_id=player.id)

        async def _run_and_log():
            _logger.info(f"DeepSync: background task started for player {player_id_str}")
            try:
                result = await deep_sync_player(org_id_str, player_id_str, run_id=run_id)
                _logger.info(f"DeepSync: completed for player {player_id_str}: {result}")
                await finish_sync_run(run_id, result if isinstance(result, dict) and "error" not in result else {}, result.get("error", "") if isinstance(result, dict) else "")
            except Exception as e:
                _logger.error(f"DeepSync: FAILED for player {player_id_str}: {e}", exc_info=True)
                await finish_sync_run(run_id, {}, f"Unexpected error: {e}")
            finally:
                _player_sync_running.discard(player_id_str)
                _background_tasks.discard(asyncio.current_task())

        task = asyncio.create_task(_run_and_log())
        _background_tasks.add(task)
        return {"status": "approved", "warnings": warnings, "message": "Deep sync started in background", "run_id": str(run_id)}

    req.admin_note = body.admin_note
    req.resolved_at = datetime.now(timezone.utc)
    req.status = "dismissed"
    await db.commit()
    return {"status": "dismissed"}


# ---------------------------------------------------------------------------
# PHQ ID Suggestions
# ---------------------------------------------------------------------------

@router.get("/phq-suggestions")
async def list_phq_suggestions(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        _text("""
            SELECT
                s.id, s.phq_player_id, s.phq_first_name, s.phq_last_name,
                s.confidence, s.game_count, s.status, s.created_at,
                p.id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                p.playhq_id AS player_current_phq_id
            FROM phq_id_suggestions s
            LEFT JOIN players p ON p.id = s.player_id
            WHERE s.org_id = :org_id
            ORDER BY
                CASE s.status WHEN 'pending' THEN 0 ELSE 1 END,
                s.confidence DESC,
                s.game_count DESC
            LIMIT 200
        """),
        {"org_id": str(club.id)},
    )
    rows = result.mappings().all()
    data = [
        {
            "id": r["id"],
            "phq_player_id": r["phq_player_id"],
            "phq_name": f"{r['phq_first_name'] or ''} {r['phq_last_name'] or ''}".strip(),
            "phq_first_name": r["phq_first_name"],
            "phq_last_name": r["phq_last_name"],
            "confidence": r["confidence"],
            "game_count": r["game_count"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "player_id": r["player_id"],
            "player_name": r["player_name"],
            "player_current_phq_id": r["player_current_phq_id"],
        }
        for r in rows
    ]
    return {"suggestions": data, "scanning": str(club.id) in _phq_scan_running}


@router.post("/phq-suggestions/run")
async def run_phq_suggestions(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
):
    from app.services.sync import suggest_phq_ids
    org_id_str = str(club.id)

    if org_id_str in _phq_scan_running:
        return {"status": "already_running", "message": "A scan is already in progress for this org"}

    _phq_scan_running.add(org_id_str)

    async def _run():
        _logging.getLogger(__name__).info(f"PhqSuggest: background task started for org {org_id_str}")
        try:
            result = await suggest_phq_ids(org_id_str)
            _logging.getLogger(__name__).info(f"PhqSuggest: done for org {org_id_str}: {result}")
        except Exception as e:
            _logging.getLogger(__name__).error(f"PhqSuggest: FAILED for org {org_id_str}: {e}", exc_info=True)
        finally:
            _phq_scan_running.discard(org_id_str)
            _background_tasks.discard(asyncio.current_task())

    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    return {"status": "started", "message": "PHQ ID scan running in background"}


class PhqSuggestionAction(BaseModel):
    action: str  # "approve" or "dismiss"
    player_id: Optional[str] = None  # override which player to link


@router.post("/phq-suggestions/{suggestion_id}")
async def action_phq_suggestion(
    suggestion_id: int,
    body: PhqSuggestionAction,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    sugg = await db.get(PhqIdSuggestion, suggestion_id)
    if not sugg or str(sugg.org_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if sugg.status != "pending":
        raise HTTPException(status_code=409, detail="Suggestion already resolved")
    if body.action not in ("approve", "dismiss"):
        raise HTTPException(status_code=422, detail="action must be 'approve' or 'dismiss'")

    sugg.resolved_at = datetime.now(timezone.utc)
    sugg.status = "approved" if body.action == "approve" else "dismissed"

    if body.action == "approve":
        target_player_id = body.player_id or (str(sugg.player_id) if sugg.player_id else None)
        if not target_player_id:
            raise HTTPException(status_code=422, detail="player_id required for approval")
        player = await db.get(Player, uuid.UUID(target_player_id))
        if not player or player.organisation_id != club.id:
            raise HTTPException(status_code=404, detail="Player not found")

        # Check for conflict
        conflict = await db.execute(
            select(Player).where(
                Player.organisation_id == club.id,
                Player.playhq_id == sugg.phq_player_id,
                Player.id != player.id,
            )
        )
        if conflict.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Another player already has this PlayHQ ID")

        player.playhq_id = sugg.phq_player_id
        sugg.player_id = player.id

    await db.commit()
    return {"status": sugg.status}


# ---------------------------------------------------------------------------
# Sync runs (hard refresh + history)
# ---------------------------------------------------------------------------

# Per-org hard-refresh locks
_hard_refresh_running: set = set()


@router.post("/hard-refresh", status_code=202)
async def hard_refresh_org(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
):
    """Trigger a full historical re-sync of the org.

    Wipes existing game-level data (games + cascading batting / bowling /
    fielding / FOW / partnerships) and re-runs the full sync. Used after
    sync-logic changes (innings split, FOW-vs-dismissal checks, etc.) to
    rebuild from current code rather than top up.

    Only wipes games that have batting rows — PHQ-namespace shells the GR
    API returns 204 for would be unrecoverable, but those have no batting
    rows anyway so the WHERE filter is a no-op for them. Runs in the
    background; poll GET /club-admin/sync-runs/{run_id} for progress.
    """
    from app.services.sync import sync_organisation, start_sync_run, finish_sync_run
    org_id_str = str(club.id)
    if org_id_str in _hard_refresh_running:
        return {"status": "already_running", "org_id": org_id_str}

    run_id = await start_sync_run(club.id, "org_hard_refresh")
    _hard_refresh_running.add(org_id_str)
    _logger = _logging.getLogger(__name__)

    async def _run():
        _logger.info(f"HardRefresh: starting for org {org_id_str} (run_id={run_id})")
        try:
            # Wipe phase — games with batting rows whose seasons belong to this org.
            from app.models.db import async_session_maker
            from sqlalchemy import text as _t
            async with async_session_maker() as s:
                r = await s.execute(
                    _t(
                        """
                        DELETE FROM games
                        WHERE id IN (SELECT DISTINCT game_id FROM batting_innings)
                          AND grade_id IN (
                            SELECT gr.id FROM grades gr
                            JOIN seasons se ON se.id = gr.season_id
                            WHERE se.organisation_id = :oid
                          )
                        RETURNING id
                        """
                    ),
                    {"oid": org_id_str},
                )
                wiped = len(list(r))
                await s.commit()
                _logger.info(f"HardRefresh: wiped {wiped} games (cascades cleared all child rows) for org {org_id_str}")

            stats = await sync_organisation(org_id_str, run_id=run_id, kind="org_hard_refresh")
            stats = dict(stats or {})
            stats["games_wiped_pre_sync"] = wiped
            await finish_sync_run(run_id, stats)
        except Exception as e:
            _logger.error(f"HardRefresh: failed for {org_id_str}: {e}", exc_info=True)
            await finish_sync_run(run_id, {}, f"Unexpected error: {e}")
        finally:
            _hard_refresh_running.discard(org_id_str)
            _background_tasks.discard(asyncio.current_task())

    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    return {"status": "started", "run_id": str(run_id), "org_id": org_id_str}


@router.delete("/sync-runs")
async def clear_sync_runs(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Delete completed/errored sync runs for this org. Preserves any currently-running rows."""
    res = await db.execute(
        _text("DELETE FROM sync_runs WHERE org_id = :oid AND status != 'running'"),
        {"oid": str(club.id)},
    )
    await db.commit()
    return {"deleted": res.rowcount}


@router.delete("/sync-requests/resolved")
async def clear_resolved_sync_requests(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Delete approved/dismissed player sync requests for this org. Preserves pending ones."""
    res = await db.execute(
        _text("DELETE FROM player_sync_requests WHERE org_id = :oid AND status != 'pending'"),
        {"oid": str(club.id)},
    )
    await db.commit()
    return {"deleted": res.rowcount}


@router.get("/sync-runs")
async def list_sync_runs(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
    limit: int = 30,
):
    from app.models.db import SyncRun
    res = await db.execute(
        select(SyncRun)
        .where(SyncRun.org_id == club.id)
        .order_by(SyncRun.started_at.desc())
        .limit(min(limit, 100))
    )
    runs = res.scalars().all()
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "status": r.status,
            "player_id": str(r.player_id) if r.player_id else None,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "stats": r.stats or {},
            "error": r.error,
        }
        for r in runs
    ]


@router.get("/sync-runs/{run_id}")
async def get_sync_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    from app.models.db import SyncRun
    run = await db.get(SyncRun, uuid.UUID(run_id))
    if not run or run.org_id != club.id:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return {
        "id": str(run.id),
        "kind": run.kind,
        "status": run.status,
        "player_id": str(run.player_id) if run.player_id else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "stats": run.stats or {},
        "error": run.error,
    }
