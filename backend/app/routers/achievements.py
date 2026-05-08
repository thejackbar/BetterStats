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


# ─── Excel template download ─────────────────────────────────────────────────

@router.get("/template")
async def download_template():
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.worksheet.datavalidation import DataValidation
        from openpyxl.utils import get_column_letter
        from openpyxl.workbook.defined_name import DefinedName

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Achievements"

        # ── Main sheet headers ──
        headers = ["Season", "Category", "Subcategory", "Achievement", "Player Name", "Detail"]
        header_fill = PatternFill("solid", fgColor="1e3a5f")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        inst_fill = PatternFill("solid", fgColor="0a1628")
        inst_font = Font(color="64748b", size=9, italic=True)

        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Instruction row
        instructions = [
            "e.g. 2025_26",
            "↓ Select from list",
            "↓ Depends on Category",
            "↓ Depends on Subcategory",
            "Exact player name",
            "Optional notes",
        ]
        for col, inst in enumerate(instructions, 1):
            cell = ws.cell(row=2, column=col, value=inst)
            cell.fill = inst_fill
            cell.font = inst_font
            cell.alignment = Alignment(horizontal="center")

        ws.row_dimensions[1].height = 20
        ws.row_dimensions[2].height = 16
        ws.freeze_panes = "A3"

        col_widths = [13, 22, 28, 35, 28, 32]
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

        # ── Hidden Lists sheet ──
        lists_ws = wb.create_sheet("_Lists")
        lists_ws.sheet_state = "hidden"

        cur = 1  # current row in Lists sheet

        def add_named_list(name: str, items: list[str]) -> str:
            nonlocal cur
            start = cur
            for item in items:
                lists_ws.cell(row=cur, column=1, value=item)
                cur += 1
            end = cur - 1
            cur += 1  # blank buffer row
            ref = f"'_Lists'!$A${start}:$A${end}"
            try:
                dn = DefinedName(name=name, attr_text=ref)
                wb.defined_names.add(dn)
            except Exception:
                wb.defined_names[name] = DefinedName(name=name, attr_text=ref)
            return name

        # Category lookup table: col C = exact name, col D = range name
        cat_lookup_start = 1
        sub_range_names: dict[str, str] = {}

        for cat, subcats in ACHIEVEMENT_TREE.items():
            rn_sub = f"sub_{_rn(cat)}"
            sub_range_names[cat] = add_named_list(rn_sub, list(subcats.keys()))

        # Achievement lookup: keyed by "category|subcategory"
        ach_range_names: dict[str, str] = {}
        for cat, subcats in ACHIEVEMENT_TREE.items():
            for subcat, achievements in subcats.items():
                key = f"{cat}|{subcat}"
                rn_ach = f"ach_{_rn(cat)}_{_rn(subcat)}"[:255]
                ach_range_names[key] = add_named_list(rn_ach, achievements)

        # Write category → range_name lookup into Lists col C, D
        cat_lkp_start = cur
        for i, (cat, rn) in enumerate(sub_range_names.items()):
            lists_ws.cell(row=cur + i, column=3, value=cat)
            lists_ws.cell(row=cur + i, column=4, value=rn)
        cat_lkp_end = cur + len(sub_range_names) - 1
        cur = cat_lkp_end + 2

        # Write "cat|subcat" → range_name lookup into Lists col F, G
        ach_lkp_start = cur
        for i, (key, rn) in enumerate(ach_range_names.items()):
            lists_ws.cell(row=cur + i, column=6, value=key)
            lists_ws.cell(row=cur + i, column=7, value=rn)
        ach_lkp_end = cur + len(ach_range_names) - 1

        # ── Data validations on main sheet ──
        DATA_ROWS = "3:1000"

        # Category: plain list
        cat_formula = ",".join(f'"{c}"' for c in CATEGORIES)
        dv_cat = DataValidation(type="list", formula1=cat_formula, allow_blank=True, showDropDown=False)
        dv_cat.sqref = f"B{DATA_ROWS}"
        ws.add_data_validation(dv_cat)

        # Subcategory: INDIRECT via lookup table
        sub_lkp = f"'_Lists'!$C${cat_lkp_start}:$D${cat_lkp_end}"
        dv_sub = DataValidation(
            type="list",
            formula1=f"INDIRECT(VLOOKUP(B3,{sub_lkp},2,0))",
            allow_blank=True,
            showDropDown=False,
        )
        dv_sub.sqref = f"C{DATA_ROWS}"
        ws.add_data_validation(dv_sub)

        # Achievement: INDIRECT via lookup table keyed on "category|subcategory"
        ach_lkp = f"'_Lists'!$F${ach_lkp_start}:$G${ach_lkp_end}"
        dv_ach = DataValidation(
            type="list",
            formula1=f'INDIRECT(VLOOKUP(B3&"|"&C3,{ach_lkp},2,0))',
            allow_blank=True,
            showDropDown=False,
        )
        dv_ach.sqref = f"D{DATA_ROWS}"
        ws.add_data_validation(dv_ach)

        # ── Example / starter rows ──
        example_fill = PatternFill("solid", fgColor="0d1f36")
        example_font = Font(color="64748b", italic=True, size=10)
        for r, row in enumerate(TEMPLATE_ROWS, 3):
            for c, val in enumerate(row, 1):
                cell = ws.cell(row=r, column=c, value=val)
                cell.fill = example_fill
                cell.font = example_font

        # ── Reference sheet ──
        ref_ws = wb.create_sheet("Reference")
        ref_ws.column_dimensions["A"].width = 22
        ref_ws.column_dimensions["B"].width = 28
        ref_ws.column_dimensions["C"].width = 38
        ref_ws.column_dimensions["D"].width = 6
        ref_ws.column_dimensions["E"].width = 38

        hdr_font = Font(bold=True, color="FFFFFF", size=11)
        hdr_fill = PatternFill("solid", fgColor="1e3a5f")
        subhdr_font = Font(bold=True, color="94a3b8", size=10)

        def ref_header(row, col, text):
            c = ref_ws.cell(row=row, column=col, value=text)
            c.font = hdr_font
            c.fill = hdr_fill
            c.alignment = Alignment(horizontal="center")

        ref_header(1, 1, "Season Format")
        ref_ws.cell(row=2, column=1, value="2025_26").font = Font(size=10)
        ref_ws.cell(row=3, column=1, value="(year_year, underscore)").font = Font(color="64748b", italic=True, size=9)
        ref_ws.cell(row=4, column=1, value="Leave blank = timeless").font = Font(color="64748b", italic=True, size=9)

        ref_header(1, 2, "Categories")
        for i, cat in enumerate(CATEGORIES, 2):
            ref_ws.cell(row=i, column=2, value=cat).font = Font(size=10)

        # Full category → subcategory → achievement tree
        ref_header(1, 4, "Category")
        ref_header(1, 5, "Subcategory → Achievements")
        ref_row = 2
        for cat, subcats in ACHIEVEMENT_TREE.items():
            ref_ws.cell(row=ref_row, column=4, value=cat).font = Font(bold=True, size=10, color="e2e8f0")
            ref_ws.cell(row=ref_row, column=4).fill = PatternFill("solid", fgColor="1e3a5f")
            ref_row += 1
            for subcat, achs in subcats.items():
                ref_ws.cell(row=ref_row, column=4, value=f"  {subcat}").font = Font(bold=True, size=9, color="94a3b8")
                ref_ws.cell(row=ref_row, column=5, value=", ".join(achs)).font = Font(size=9, color="64748b")
                ref_row += 1
            ref_row += 1

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=achievements_template.xlsx"},
        )
    except ImportError:
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
