from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid
import re
import io
import csv

from app.models.db import get_db

router = APIRouter(prefix="/achievements", tags=["achievements"])

CATEGORIES = [
    "Club Award",
    "Association Award",
    "Office Bearer",
    "Premiership",
    "Hall of Fame",
    "Life Membership",
    "Milestone",
]

TEMPLATE_ROWS = [
    ("2025_26", "Club Award", "1st XI", "Best & Fairest", "Matthew Edwards", ""),
    ("2025_26", "Club Award", "1st XI", "Best Batter", "Pratik Bhave", "436 runs at 39.64"),
    ("2025_26", "Club Award", "1st XI", "Best Bowler", "Will Dagg", "26 wickets at 20.54"),
    ("2025_26", "Office Bearer", "Executive Committee", "President", "Mark Hullett", ""),
    ("2025_26", "Office Bearer", "Captains", "1st XI Captain", "Matthew Edwards", ""),
    ("2025_26", "Premiership", "Women's A Grade", "Premiership", "Grace Camarda", "captain"),
    ("2025_26", "Association Award", "WASTCA", "3rd Grade Bowling Aggregate", "Chris Cooper", "25 Wickets"),
    ("2025_26", "Hall of Fame", "ACC", "Hall of Fame", "Matt Campbell", "#37"),
    ("2025_26", "Milestone", "Games", "100 Games", "Aamir Abbas", ""),
    ("2025_26", "Milestone", "Runs", "1000 Runs", "Pratik Bhave", ""),
]


def _normalise(name: str) -> str:
    name = name.strip()
    if ", " in name:
        parts = name.split(", ", 1)
        name = f"{parts[1]} {parts[0]}"
    return re.sub(r"\s+", " ", name).lower()


async def _resolve_player(db: AsyncSession, player_name: str, org_id: str) -> Optional[str]:
    """Try to match a player name to a player_id in the org."""
    norm = _normalise(player_name)
    result = await db.execute(
        text("SELECT id, name FROM players WHERE organisation_id = :org_id"),
        {"org_id": org_id},
    )
    for row in result.mappings().all():
        if _normalise(row["name"]) == norm:
            return str(row["id"])
    return None


# ─── GET list ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_achievements(
    org_id: str = Query(...),
    player_id: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = ["org_id = :org_id"]
    params: dict = {"org_id": org_id}
    if player_id:
        filters.append("player_id = :player_id")
        params["player_id"] = player_id
    if season:
        filters.append("season = :season")
        params["season"] = season

    where = " AND ".join(filters)
    rows = await db.execute(
        text(f"SELECT * FROM player_achievements WHERE {where} ORDER BY season DESC NULLS LAST, category, id"),
        params,
    )
    return [dict(r) for r in rows.mappings().all()]


# ─── POST create ──────────────────────────────────────────────────────────────

class AchievementCreate(BaseModel):
    org_id: str
    player_id: Optional[str] = None
    player_name: str
    season: Optional[str] = None
    category: str
    subcategory: Optional[str] = None
    achievement: str
    detail: Optional[str] = None


@router.post("")
async def create_achievement(body: AchievementCreate, db: AsyncSession = Depends(get_db)):
    player_id = body.player_id
    if not player_id:
        player_id = await _resolve_player(db, body.player_name, body.org_id)

    result = await db.execute(
        text("""
            INSERT INTO player_achievements
                (org_id, player_id, player_name, season, category, subcategory, achievement, detail)
            VALUES (:org_id, :player_id, :player_name, :season, :category, :subcategory, :achievement, :detail)
            RETURNING id
        """),
        {
            "org_id": body.org_id,
            "player_id": player_id,
            "player_name": body.player_name,
            "season": body.season or None,
            "category": body.category,
            "subcategory": body.subcategory or None,
            "achievement": body.achievement,
            "detail": body.detail or None,
        },
    )
    new_id = result.scalar()
    await db.commit()
    return {"id": new_id, "status": "created"}


# ─── PUT update ────────────────────────────────────────────────────────────────

class AchievementUpdate(BaseModel):
    player_name: Optional[str] = None
    player_id: Optional[str] = None
    season: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    achievement: Optional[str] = None
    detail: Optional[str] = None


@router.put("/{achievement_id}")
async def update_achievement(
    achievement_id: int,
    body: AchievementUpdate,
    db: AsyncSession = Depends(get_db),
):
    sets = []
    params: dict = {"id": achievement_id}
    for field in ["player_name", "player_id", "season", "category", "subcategory", "achievement", "detail"]:
        val = getattr(body, field)
        if val is not None:
            sets.append(f"{field} = :{field}")
            params[field] = val
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    await db.execute(
        text(f"UPDATE player_achievements SET {', '.join(sets)} WHERE id = :id"),
        params,
    )
    await db.commit()
    return {"status": "updated"}


# ─── DELETE ────────────────────────────────────────────────────────────────────────────

@router.delete("/{achievement_id}")
async def delete_achievement(achievement_id: int, org_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("DELETE FROM player_achievements WHERE id = :id AND org_id = :org_id"),
        {"id": achievement_id, "org_id": org_id},
    )
    await db.commit()
    return {"status": "deleted"}


# ─── Excel template download ────────────────────────────────────────────────────────────

@router.get("/template")
async def download_template():
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.worksheet.datavalidation import DataValidation
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Achievements"

        headers = ["Season", "Category", "Subcategory", "Achievement", "Player Name", "Detail"]
        header_fill = PatternFill("solid", fgColor="1e3a5f")
        header_font = Font(bold=True, color="FFFFFF")

        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        col_widths = [12, 20, 25, 30, 25, 30]
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

        # Category dropdown validation (rows 2-500)
        cat_list = ",".join(f'"{c}"' for c in CATEGORIES)
        dv = DataValidation(type="list", formula1=cat_list, allow_blank=True, showDropDown=False)
        dv.sqref = "B2:B500"
        ws.add_data_validation(dv)

        # Example rows
        example_fill = PatternFill("solid", fgColor="0d1f36")
        example_font = Font(color="94a3b8", italic=True)
        for r, row in enumerate(TEMPLATE_ROWS, 2):
            for c, val in enumerate(row, 1):
                cell = ws.cell(row=r, column=c, value=val)
                cell.fill = example_fill
                cell.font = example_font

        # Ref sheet
        ref_ws = wb.create_sheet("Reference")
        ref_ws.cell(row=1, column=1, value="Valid Categories").font = Font(bold=True)
        for i, cat in enumerate(CATEGORIES, 2):
            ref_ws.cell(row=i, column=1, value=cat)
        ref_ws.cell(row=1, column=3, value="Season Format").font = Font(bold=True)
        ref_ws.cell(row=2, column=3, value="2025_26 (year underscore year)")
        ref_ws.cell(row=3, column=3, value="Leave blank for timeless achievements")

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=achievements_template.xlsx"},
        )
    except ImportError:
        # Fallback to CSV if openpyxl not available
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Season", "Category", "Subcategory", "Achievement", "Player Name", "Detail"])
        writer.writerows(TEMPLATE_ROWS)
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=achievements_template.csv"},
        )


# ─── Import (Excel or CSV) ──────────────────────────────────────────────────────────────────

def _parse_xlsx(content: bytes) -> list[dict]:
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


def _parse_csv(content: bytes) -> list[dict]:
    text_content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text_content))
    return [
        {k.strip().lower().replace(" ", "_"): (v.strip() if v else "")
         for k, v in row.items()}
        for row in reader
        if any(row.values())
    ]


@router.post("/import")
async def import_achievements(
    org_id: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        rows = _parse_xlsx(content)
    else:
        rows = _parse_csv(content)

    if not rows:
        raise HTTPException(status_code=400, detail="No data found in file")

    created = 0
    skipped = 0
    errors = []
    unmatched_players = []

    for i, row in enumerate(rows, 2):
        player_name = row.get("player_name", "").strip()
        category = row.get("category", "").strip()
        achievement = row.get("achievement", "").strip()

        if not player_name or not category or not achievement:
            skipped += 1
            continue

        season = row.get("season", "").strip() or None
        subcategory = row.get("subcategory", "").strip() or None
        detail = row.get("detail", "").strip() or None

        if category not in CATEGORIES:
            errors.append(f"Row {i}: unknown category '{category}'")
            skipped += 1
            continue

        # Handle "Not awarded" or empty player entries
        if player_name.lower() in ("not awarded", "n/a", ""):
            skipped += 1
            continue

        player_id = await _resolve_player(db, player_name, org_id)
        if not player_id:
            unmatched_players.append(player_name)

        await db.execute(
            text("""
                INSERT INTO player_achievements
                    (org_id, player_id, player_name, season, category, subcategory, achievement, detail)
                VALUES (:org_id, :player_id, :player_name, :season, :category, :subcategory, :achievement, :detail)
            """),
            {
                "org_id": org_id,
                "player_id": player_id,
                "player_name": player_name,
                "season": season,
                "category": category,
                "subcategory": subcategory,
                "achievement": achievement,
                "detail": detail,
            },
        )
        created += 1

    await db.commit()

    return {
        "status": "imported",
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "unmatched_players": list(set(unmatched_players)),
    }
