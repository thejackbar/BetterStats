from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response
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


# ─── GET list ────────────────────────────────────────────────────────────────

@router.get("")
async def list_achievements(
    org_id: str = Query(...),
    player_id: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"org_id": org_id}

    if player_id:
        # Also match unlinked rows (player_id IS NULL) where the name matches this player
        player_name_result = await db.execute(
            text("SELECT name FROM players WHERE id = :pid"),
            {"pid": player_id},
        )
        player_row = player_name_result.mappings().first()
        player_name_norm = _normalise(player_row["name"]) if player_row else None

        if player_name_norm:
            player_filter = (
                "(player_id = :player_id OR "
                "(player_id IS NULL AND lower(regexp_replace(player_name, '\\s+', ' ', 'g')) = :pname))"
            )
            params["player_id"] = player_id
            params["pname"] = player_name_norm
        else:
            player_filter = "player_id = :player_id"
            params["player_id"] = player_id

        base_filter = f"org_id = :org_id AND {player_filter}"
    else:
        base_filter = "org_id = :org_id"

    if season:
        base_filter += " AND season = :season"
        params["season"] = season

    rows = await db.execute(
        text(f"SELECT * FROM player_achievements WHERE {base_filter} ORDER BY season DESC NULLS LAST, category, id"),
        params,
    )
    return [dict(r) for r in rows.mappings().all()]


# ─── POST create ─────────────────────────────────────────────────────────────

class AchievementCreate(BaseModel):
    org_id: str
    player_id: Optional[str] = None
    player_name: str
    season: Optional[str] = None
    season_end: Optional[str] = None
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
                (org_id, player_id, player_name, season, season_end, category, subcategory, achievement, detail)
            VALUES (:org_id, :player_id, :player_name, :season, :season_end, :category, :subcategory, :achievement, :detail)
            RETURNING id
        """),
        {
            "org_id": body.org_id,
            "player_id": player_id,
            "player_name": body.player_name,
            "season": body.season or None,
            "season_end": body.season_end or None,
            "category": body.category,
            "subcategory": body.subcategory or None,
            "achievement": body.achievement,
            "detail": body.detail or None,
        },
    )
    new_id = result.scalar()
    await db.commit()
    return {"id": new_id, "status": "created"}


# ─── PUT update ──────────────────────────────────────────────────────────────

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
    db: AsyncSession = Depends(get_db),
):
    sets = []
    params: dict = {"id": achievement_id}
    for field in ["player_name", "player_id", "season", "season_end", "category", "subcategory", "achievement", "detail"]:
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


# ─── DELETE ──────────────────────────────────────────────────────────────────

@router.delete("/{achievement_id}")
async def delete_achievement(achievement_id: int, org_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("DELETE FROM player_achievements WHERE id = :id AND org_id = :org_id"),
        {"id": achievement_id, "org_id": org_id},
    )
    await db.commit()
    return {"status": "deleted"}


# ─── Achievement tree (mirrors frontend achievementOptions.js) ────────────────

_GRADE_AWARDS = [
    'Best & Fairest', 'Best Batter', 'Best Bowler', 'Batting Aggregate',
    'Batting Average', 'Bowling Aggregate', 'Bowling Average', 'Fielding Award',
    'Player of the Finals', 'Player of the Grand Final', 'Coaches Award',
]
_PREM_AWARDS = ['Premiership', 'Player of the Grand Final', 'Captain', '12th Man', '13th Man']

ACHIEVEMENT_TREE = {
    'Club Award': {
        '1st XI': _GRADE_AWARDS, '2nd XI': _GRADE_AWARDS, '3rd XI': _GRADE_AWARDS,
        '4th XI': _GRADE_AWARDS, '5th XI': _GRADE_AWARDS, '6th XI': _GRADE_AWARDS,
        'OD1 XI': _GRADE_AWARDS, 'OD2 XI': _GRADE_AWARDS, 'OD3 XI': _GRADE_AWARDS,
        'OD4 XI': _GRADE_AWARDS, 'OD5 Black XI': _GRADE_AWARDS, 'OD5 Gold XI': _GRADE_AWARDS,
        'T20 Div 1': ['Best & Fairest', 'Best Batter', 'Best Bowler', 'Coaches Award'],
        'T20 Div 2': ['Best & Fairest', 'Best Batter', 'Best Bowler', 'Coaches Award'],
        'T20 Div 3': ['Best & Fairest', 'Best Batter', 'Best Bowler', 'Coaches Award'],
        'ICL A Grade': ['Best & Fairest', 'Best Batter', 'Best Bowler', 'Best Fielder', 'Coaches Award'],
        "Women's A Grade": ['Best & Fairest', 'Best Batter', 'Best Bowler', 'Batting Aggregate', 'Batting Average', 'Bowling Aggregate', 'Bowling Average', 'Fielding Award', 'Coaches Award'],
        "Women's B Grade": ['Best & Fairest', 'Best Batter', 'Best Bowler', 'Coaches Award'],
        'Colts': ['Best & Fairest', 'Best Batter', 'Best Bowler', 'Batting Aggregate', 'Batting Average', 'Bowling Aggregate', 'Bowling Average', 'Fielding Award', 'Coaches Award'],
        'Perpetual': [
            "The 'Al Field' Best Clubperson", "The 'Russell Kingdon' Presidents Trophy",
            'Best All Round Cricketer', 'Most Improved', 'Best Future Prospect',
            "The 'Tom Morgan' Fielding Award", "The 'Brett McGregor' Most Determined to Succeed",
            "The 'Rob Wilton' Leading Run Scorer", "The 'Ramon Fletcher' Leading Wicket Taker",
            'Season Highest Batting Partnership', "The 'Aubrey King' Club Trip Medallion",
            'Roger Weir Memorial Shield - 100 Gamers vs Presidents XI', 'Wood Duck', 'Coaches Award',
            'Best 1st Year Player', "The 'Greg DeCampo' ICL A Grade Coaches Award", 'ACC Debut',
        ],
        "Women's Perpetual": [
            'Womens - Best All Round Cricketer', 'Womens - Best Fielder',
            'Womens - Best Future Prospect', 'Womens - Coaches Award',
            'Womens - Most Improved', 'Womens - Season Highest Batting Partnership',
            'Womens - Spirit of Cricket',
        ],
    },
    'Association Award': {
        'WASTCA': [
            'Champion Club', 'Club Championship',
            'Barry Parker Memorial Award', 'Barry Parker Memorial Award - Best Single Performance in a Match',
            'Spirit of the Game Award', 'John Ireland & Paul Pearce Spirit of the Game Award',
            '1st Grade Batting', '1st Grade Batting Average', '1st Grade Bowling Average', '1st Grade Fielding',
            '2nd Grade Batting Aggregate', '2nd Grade Batting Average', '2nd Grade Champion Cricketer',
            '2nd Grade Paul Pearce Champion Cricketer', '2nd Grade Fielding',
            '3rd Grade Batting Average', '3rd Grade Bowling Aggregate', '3rd Grade Bowling Average', '3rd Grade Fielding',
            '4th Grade Batting Average', '4th Grade Bowling Aggregate', '4th Grade Bowling Average', '4th Grade Fielding',
            '5th Grade Batting Aggregate', '5th Grade Batting Average', '5th Grade Bowling',
            '5th Grade Champion Cricketer', '5th Grade Fielding',
            '6th Grade Batting Aggregate', '6th Grade Batting Average', '6th Grade Champion Cricketer',
            '7th Grade Batting Aggregate', '7th Grade Batting Average', '7th Grade Bowling Average', '7th Grade Fielding',
            '8th Grade Batting Aggregate', '8th Grade Batting Average', '8th Grade Bowling Aggregate', '8th Grade Bowling Average',
            '9th Grade Batting', '9th Grade Bowling', '9th Grade Fielding',
            '10th Grade Batting', '10th Grade Bowling Average',
            'OD2 Batting Aggregate', 'OD2 Bowling Average', 'OD2 Fielding',
            'OD4 Batting Average', 'OD4 Champion Player',
            'OD5 Champion Cricketer', 'OD5 Bowling Aggregate',
            'OD5 Black Champion Cricketer', 'OD5 Black Bowling Aggregate',
            'One Day Division 1 Bowling Average', 'One Day Div 2 Bowling Aggregate', 'One Day Div 3 Bowling Aggregate',
            'Colts Batting', 'Colts Spirit of the Game Award',
        ],
        'WABCC': [
            'Batting Award', 'Bowling Award', 'Fielding Award', 'Most Improved', 'Best New Player',
            'Best Team Player', "Coach's Award", "Captain's Award", 'Volunteer Award', 'Les Buchanan Medal',
        ],
        'PSWL': [
            'PSWL Metro: Champion Player', 'PSWL Metro: Batting Average',
            'PSWL Metro: Batting Aggregate (Runner Up)', 'PSWL Metro: Bowling Aggregate',
            'PSWL Metro: Bowling Average (Runner Up)',
            'PSWL South A - Batting Average', 'PSWL South A - Bowling Aggregate Runner Up',
            'PSWL South A - Bowling Average Runner Up', 'PSWL South B - Spirit of Cricket',
            'PSWL South Premiership', 'PSWL South Conference Runner Up Bowling Aggregate',
        ],
        'ACC': ['Hall of Fame', 'WACA Inclusion and Diversity Award'],
    },
    'Office Bearer': {
        'Executive Committee': ['President', 'Vice President', "Vice President - Men's Cricket",
            "Vice President - Women's Cricket", "Vice President - Junior Cricket", 'Treasurer', 'Secretary', 'Operations'],
        'General Committee': ['Committee', 'Junior Committee'],
        'Captains': [
            '1st XI Captain', '2nd XI Captain', '3rd XI Captain', '4th XI Captain', '5th XI Captain', '6th XI Captain',
            'OD1 XI Captain', 'OD2 XI Captain', 'OD3 XI Captain', 'OD4 XI Captain',
            'OD5 Black XI Captain', 'OD5 XI Captain', 'OD5 Gold XI Captain',
            'T20 Div 1 Captain', 'T20 Div 2 Captain', 'T20 Div 3 Captain',
            'Colts Captain', 'ICL A Grade Captain', "Women's A Captain", "Women's B Captain",
        ],
        'Coaches': ['Club Coach', 'Head Coach', 'Assistant Coach', 'Director of Cricket',
            "Women's Coach", "Women's Cricket Coordinator", 'Nets Coach', 'Nets Coordinator',
            'Colts Coach', 'Junior Coordinator'],
        'Other Roles': ['Chairman of Selectors', 'SSRSA Representative', 'WASTCA Delegate', 'WASTCA Director',
            'Grounds Officer', 'Curator', 'Turf Curator', 'Bar Manager', 'Sponsorship Manager',
            'Social Media Manager', 'Registrar', 'Match Day Coordinator'],
    },
    'Premiership': {
        '1st XI': _PREM_AWARDS, '2nd XI': _PREM_AWARDS, '3rd XI': _PREM_AWARDS,
        '4th XI': _PREM_AWARDS, '5th XI': _PREM_AWARDS, '6th XI': _PREM_AWARDS,
        'OD1 XI': _PREM_AWARDS, 'OD2 XI': _PREM_AWARDS, 'OD3 XI': _PREM_AWARDS,
        'OD4 XI': _PREM_AWARDS, 'OD5 Black XI': _PREM_AWARDS, 'OD5 Gold XI': _PREM_AWARDS,
        'OD5 XI': _PREM_AWARDS,
        'T20 Div 1': ['Premiership', 'Player of the Grand Final', 'Captain'],
        'T20 Div 2': ['Premiership', 'Player of the Grand Final', 'Captain'],
        'T20 Div 3': ['Premiership', 'Player of the Grand Final', 'Captain'],
        'ICL A Grade': ['Premiership', 'Player of the Grand Final', 'Captain'],
        "Women's A Grade": ['Premiership', 'Player of the Grand Final', 'Captain'],
        "Women's B Grade": ['Premiership', 'Player of the Grand Final', 'Captain'],
        'Colts': ['Premiership', 'Player of the Grand Final', 'Captain'],
    },
    'Hall of Fame': {'ACC': ['Hall of Fame']},
    'Life Membership': {'ACC': ['Life Membership']},
    'Milestone': {
        'Games': ['50 Games', '100 Games', '150 Games', '200 Games', '250 Games', '300 Games', '350 Games', '400 Games', '450 Games', '500 Games'],
        'Runs': ['500 Runs', '1000 Runs', '2000 Runs', '3000 Runs', '4000 Runs', '5000 Runs', '6000 Runs', '7000 Runs', '8000 Runs', '9000 Runs', '10000 Runs'],
        'Wickets': ['50 Wickets', '100 Wickets', '150 Wickets', '200 Wickets', '250 Wickets', '300 Wickets', '350 Wickets', '400 Wickets', '450 Wickets', '500 Wickets', '550 Wickets', '600 Wickets', '650 Wickets', '700 Wickets'],
        'Catches': ['50 Catches', '100 Catches', '150 Catches', '200 Catches', '250 Catches', '300 Catches'],
        'Hat Tricks': ['Hat Trick'],
        'Individual Score': ['50', '100', '150', '200'],
        'Bowling': ['5 Wickets in an Innings', '10 Wickets in a Match'],
    },
}


def _rn(s: str) -> str:
    """Convert string to valid Excel defined name (letters/digits/underscores only)."""
    import re as _re
    out = _re.sub(r"[^A-Za-z0-9]", "_", s)
    out = _re.sub(r"_+", "_", out).strip("_")
    if out and out[0].isdigit():
        out = "x" + out
    return out[:255]


# ─── CSV template download ───────────────────────────────────────────────────

@router.get("/template")
async def download_template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Season", "Category", "Subcategory", "Achievement", "Player Name", "Detail"])
    writer.writerows(TEMPLATE_ROWS)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=achievements_template.csv"},
    )




# ─── Import (Excel or CSV) ───────────────────────────────────────────────────

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
