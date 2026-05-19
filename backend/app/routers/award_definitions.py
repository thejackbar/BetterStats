from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional

from app.models.db import get_db

router = APIRouter(prefix="/award-definitions", tags=["award-definitions"])

# ─── Shared award lists ───────────────────────────────────────────────────────

_GRADE = [
    'Best & Fairest', 'Best Batter', 'Best Bowler', 'Batting Aggregate',
    'Batting Average', 'Bowling Aggregate', 'Bowling Average', 'Fielding Award',
    'Player of the Finals', 'Player of the Grand Final', 'Coaches Award',
]
_T20 = ['Best & Fairest', 'Best Batter', 'Best Bowler', 'Coaches Award']
_PREM = ['Premiership', 'Player of the Grand Final', 'Captain', '12th Man', '13th Man']
_PREM_SHORT = ['Premiership', 'Player of the Grand Final', 'Captain']
_ICL = ['Best & Fairest', 'Best Batter', 'Best Bowler', 'Best Fielder', 'Coaches Award']
_WOMENS_A = ['Best & Fairest', 'Best Batter', 'Best Bowler', 'Batting Aggregate', 'Batting Average',
             'Bowling Aggregate', 'Bowling Average', 'Fielding Award', 'Coaches Award']
_COLTS = _WOMENS_A


def _assoc_office_milestone_rows():
    """Association Award, Office Bearer and Milestone rows – identical for all templates."""
    r = []

    # Association Award – WASTCA
    for a in [
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
        '8th Grade Batting Aggregate', '8th Grade Batting Average',
        '8th Grade Bowling Aggregate', '8th Grade Bowling Average',
        '9th Grade Batting', '9th Grade Bowling', '9th Grade Fielding',
        '10th Grade Batting', '10th Grade Bowling Average',
        'OD2 Batting Aggregate', 'OD2 Bowling Average', 'OD2 Fielding',
        'OD4 Batting Average', 'OD4 Champion Player',
        'OD5 Champion Cricketer', 'OD5 Bowling Aggregate',
        'OD5 Black Champion Cricketer', 'OD5 Black Bowling Aggregate',
        'One Day Division 1 Bowling Average', 'One Day Div 2 Bowling Aggregate', 'One Day Div 3 Bowling Aggregate',
        'Colts Batting', 'Colts Spirit of the Game Award',
    ]:
        r.append(('Association Award', 'WASTCA', a))
    for a in ['Batting Award', 'Bowling Award', 'Fielding Award', 'Most Improved',
              'Best New Player', 'Best Team Player', "Coach's Award", "Captain's Award",
              'Volunteer Award', 'Les Buchanan Medal', 'Mark Hullett Medal']:
        r.append(('Association Award', 'WABCC', a))
    for a in [
        'PSWL Metro: Champion Player', 'PSWL Metro: Batting Average',
        'PSWL Metro: Batting Aggregate (Runner Up)', 'PSWL Metro: Bowling Aggregate',
        'PSWL Metro: Bowling Average (Runner Up)',
        'PSWL South A - Batting Average', 'PSWL South A - Bowling Aggregate Runner Up',
        'PSWL South A - Bowling Average Runner Up', 'PSWL South B - Spirit of Cricket',
        'PSWL South Premiership', 'PSWL South Conference Runner Up Bowling Aggregate',
    ]:
        r.append(('Association Award', 'PSWL', a))
    for a in ['Hall of Fame', 'WACA Inclusion and Diversity Award']:
        r.append(('Association Award', 'ACC', a))

    # Office Bearer
    for a in ['President', 'Vice President', "Vice President - Men's Cricket",
              "Vice President - Women's Cricket", "Vice President - Junior Cricket",
              'Treasurer', 'Secretary', 'Operations']:
        r.append(('Office Bearer', 'Executive Committee', a))
    for a in ['Committee', 'Junior Committee']:
        r.append(('Office Bearer', 'General Committee', a))
    for a in ['1st XI Captain', '2nd XI Captain', '3rd XI Captain', '4th XI Captain',
              '5th XI Captain', '6th XI Captain', 'OD1 XI Captain', 'OD2 XI Captain',
              'OD3 XI Captain', 'OD4 XI Captain', 'OD5 Black XI Captain', 'OD5 XI Captain',
              'OD5 Gold XI Captain', 'T20 Div 1 Captain', 'T20 Div 2 Captain', 'T20 Div 3 Captain',
              'Colts Captain', 'ICL A Grade Captain', "Women's A Captain", "Women's B Captain"]:
        r.append(('Office Bearer', 'Captains', a))
    for a in ['Club Coach', 'Head Coach', 'Assistant Coach', 'Director of Cricket',
              "Women's Coach", "Women's Cricket Coordinator", 'Nets Coach', 'Nets Coordinator',
              'Colts Coach', 'Junior Coordinator']:
        r.append(('Office Bearer', 'Coaches', a))
    for a in ['Chairman of Selectors', 'SSRSA Representative', 'WASTCA Delegate', 'WASTCA Director',
              'Grounds Officer', 'Curator', 'Turf Curator', 'Bar Manager', 'Sponsorship Manager',
              'Social Media Manager', 'Registrar', 'Match Day Coordinator']:
        r.append(('Office Bearer', 'Other Roles', a))

    # Milestone
    for a in ['Player Number', '100 Game Number', '200 Game Number', '300 Game Number',
              '400 Game Number', '500 Game Number', '600 Game Number', '700 Game Number',
              '800 Game Number', '900 Game Number', '1000 Game Number']:
        r.append(('Milestone', 'Cap Number', a))
    for a in ['50 Games', '100 Games', '150 Games', '200 Games', '250 Games',
              '300 Games', '350 Games', '400 Games', '450 Games', '500 Games']:
        r.append(('Milestone', 'Games', a))
    for a in ['500 Runs', '1000 Runs', '2000 Runs', '3000 Runs', '4000 Runs', '5000 Runs',
              '6000 Runs', '7000 Runs', '8000 Runs', '9000 Runs', '10000 Runs']:
        r.append(('Milestone', 'Runs', a))
    for a in ['50 Wickets', '100 Wickets', '150 Wickets', '200 Wickets', '250 Wickets',
              '300 Wickets', '350 Wickets', '400 Wickets', '450 Wickets', '500 Wickets',
              '550 Wickets', '600 Wickets', '650 Wickets', '700 Wickets']:
        r.append(('Milestone', 'Wickets', a))
    for a in ['50 Catches', '100 Catches', '150 Catches', '200 Catches', '250 Catches', '300 Catches']:
        r.append(('Milestone', 'Catches', a))
    r.append(('Milestone', 'Hat Tricks', 'Hat Trick'))
    for a in ['50', '100', '150', '200']:
        r.append(('Milestone', 'Individual Score', a))
    for a in ['5 Wickets in an Innings', '10 Wickets in a Match']:
        r.append(('Milestone', 'Bowling', a))

    return r


def _numbered(rows):
    return [(cat, sub, ach, i) for i, (cat, sub, ach) in enumerate(rows)]


def _build_global_template():
    """Generic template suitable for any cricket club. Uses generic award names."""
    r = []

    # Club Award – grade subcategories (generic OD5 XI, no split Black/Gold)
    for grade in ['1st XI', '2nd XI', '3rd XI', '4th XI', '5th XI', '6th XI',
                  'OD1 XI', 'OD2 XI', 'OD3 XI', 'OD4 XI', 'OD5 XI']:
        for a in _GRADE:
            r.append(('Club Award', grade, a))
    for grade in ['T20 Div 1', 'T20 Div 2', 'T20 Div 3']:
        for a in _T20:
            r.append(('Club Award', grade, a))
    for a in _ICL:
        r.append(('Club Award', 'ICL A Grade', a))
    for a in _WOMENS_A:
        r.append(("Club Award", "Women's A Grade", a))
    for a in _T20:
        r.append(("Club Award", "Women's B Grade", a))
    for a in _COLTS:
        r.append(('Club Award', 'Colts', a))
    # Perpetual – generic names
    for a in ['Best Club Person', "President's Trophy", 'Best All Round Cricketer', 'Most Improved',
              'Best Future Prospect', 'Fielding Award', 'Most Determined', 'Leading Run Scorer',
              'Leading Wicket Taker', 'Season Highest Batting Partnership', 'Club Trip Award',
              'Best 1st Year Player', 'Wood Duck', 'Coaches Award', 'Club Debut']:
        r.append(('Club Award', 'Perpetual', a))
    for a in ['Best All Round Cricketer', 'Best Fielder', 'Best Future Prospect',
              'Coaches Award', 'Most Improved', 'Season Highest Batting Partnership', 'Spirit of Cricket']:
        r.append(("Club Award", "Women's Perpetual", a))

    # Association Award, Office Bearer, Milestone (shared)
    r += _assoc_office_milestone_rows()

    # Premiership
    for grade in ['1st XI', '2nd XI', '3rd XI', '4th XI', '5th XI', '6th XI',
                  'OD1 XI', 'OD2 XI', 'OD3 XI', 'OD4 XI', 'OD5 XI']:
        for a in _PREM:
            r.append(('Premiership', grade, a))
    for grade in ['T20 Div 1', 'T20 Div 2', 'T20 Div 3', 'ICL A Grade',
                  "Women's A Grade", "Women's B Grade", 'Colts']:
        for a in _PREM_SHORT:
            r.append(('Premiership', grade, a))

    # Hall of Fame / Life Membership – generic 'Club' subcategory
    r.append(('Hall of Fame', 'Club', 'Hall of Fame'))
    r.append(('Life Membership', 'Club', 'Life Membership'))

    return _numbered(r)


def _build_applecross_template():
    """Applecross Cricket Club template – exact achievement values matching existing player_achievements records."""
    r = []

    # Club Award – grades including Applecross OD5 Black XI and OD5 Gold XI variants
    for grade in ['1st XI', '2nd XI', '3rd XI', '4th XI', '5th XI', '6th XI',
                  'OD1 XI', 'OD2 XI', 'OD3 XI', 'OD4 XI', 'OD5 Black XI', 'OD5 Gold XI']:
        for a in _GRADE:
            r.append(('Club Award', grade, a))
    for grade in ['T20 Div 1', 'T20 Div 2', 'T20 Div 3']:
        for a in _T20:
            r.append(('Club Award', grade, a))
    for a in _ICL:
        r.append(('Club Award', 'ICL A Grade', a))
    for a in _WOMENS_A:
        r.append(("Club Award", "Women's A Grade", a))
    for a in _T20:
        r.append(("Club Award", "Women's B Grade", a))
    for a in _COLTS:
        r.append(('Club Award', 'Colts', a))
    # Perpetual – Applecross trophy names matching existing player_achievements records
    for a in [
        "The 'Al Field' Best Clubperson", "The 'Russell Kingdon' Presidents Trophy",
        'Best All Round Cricketer', 'Most Improved', 'Best Future Prospect',
        "The 'Tom Morgan' Fielding Award", "The 'Brett McGregor' Most Determined to Succeed",
        "The 'Rob Wilton' Leading Run Scorer", "The 'Ramon Fletcher' Leading Wicket Taker",
        'Season Highest Batting Partnership', "The 'Aubrey King' Club Trip Medallion",
        'Roger Weir Memorial Shield - 100 Gamers vs Presidents XI', 'Wood Duck',
        'Coaches Award', 'Best 1st Year Player',
        "The 'Greg DeCampo' ICL A Grade Coaches Award", 'ACC Debut',
    ]:
        r.append(('Club Award', 'Perpetual', a))
    for a in ['Womens - Best All Round Cricketer', 'Womens - Best Fielder',
              'Womens - Best Future Prospect', 'Womens - Coaches Award', 'Womens - Most Improved',
              'Womens - Season Highest Batting Partnership', 'Womens - Spirit of Cricket']:
        r.append(("Club Award", "Women's Perpetual", a))

    # Association Award, Office Bearer, Milestone (shared)
    r += _assoc_office_milestone_rows()

    # Premiership – includes OD5 Black/Gold variants
    for grade in ['1st XI', '2nd XI', '3rd XI', '4th XI', '5th XI', '6th XI',
                  'OD1 XI', 'OD2 XI', 'OD3 XI', 'OD4 XI', 'OD5 Black XI', 'OD5 Gold XI', 'OD5 XI']:
        for a in _PREM:
            r.append(('Premiership', grade, a))
    for grade in ['T20 Div 1', 'T20 Div 2', 'T20 Div 3', 'ICL A Grade',
                  "Women's A Grade", "Women's B Grade", 'Colts']:
        for a in _PREM_SHORT:
            r.append(('Premiership', grade, a))

    # Hall of Fame / Life Membership – ACC subcategory matching existing records
    r.append(('Hall of Fame', 'ACC', 'Hall of Fame'))
    r.append(('Life Membership', 'ACC', 'Life Membership'))

    return _numbered(r)


GLOBAL_TEMPLATE = _build_global_template()
APPLECROSS_TEMPLATE = _build_applecross_template()


# ─── Seeding helper (called from startup) ────────────────────────────────────

async def seed_org_definitions(conn, org_id: str, template: list) -> int:
    """Insert template rows for an org. No-op if definitions already exist. Returns count seeded."""
    count_result = await conn.execute(
        text("SELECT COUNT(*) FROM org_award_definitions WHERE org_id = :org_id"),
        {"org_id": org_id},
    )
    if count_result.scalar() > 0:
        return 0
    for category, subcategory, achievement, sort_order in template:
        await conn.execute(
            text("""
                INSERT INTO org_award_definitions
                    (id, org_id, category, subcategory, achievement, sort_order)
                VALUES (gen_random_uuid(), :org_id, :category, :subcategory, :achievement, :sort_order)
            """),
            {"org_id": org_id, "category": category, "subcategory": subcategory,
             "achievement": achievement, "sort_order": sort_order},
        )
    return len(template)


# ─── API endpoints ────────────────────────────────────────────────────────────

@router.get("")
async def list_award_definitions(
    org_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        text("""
            SELECT id, org_id, category, subcategory, achievement, display_name, sort_order, active
            FROM org_award_definitions
            WHERE org_id = :org_id
            ORDER BY sort_order, id
        """),
        {"org_id": org_id},
    )
    return [dict(r) for r in rows.mappings().all()]


class AwardDefCreate(BaseModel):
    org_id: str
    category: str
    subcategory: Optional[str] = None
    achievement: Optional[str] = None
    display_name: Optional[str] = None
    sort_order: int = 0
    active: bool = True


@router.post("")
async def create_award_definition(body: AwardDefCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("""
            INSERT INTO org_award_definitions
                (id, org_id, category, subcategory, achievement, display_name, sort_order, active)
            VALUES (gen_random_uuid(), :org_id, :category, :subcategory, :achievement, :display_name, :sort_order, :active)
            RETURNING id
        """),
        {
            "org_id": body.org_id, "category": body.category,
            "subcategory": body.subcategory, "achievement": body.achievement,
            "display_name": body.display_name or None,
            "sort_order": body.sort_order, "active": body.active,
        },
    )
    new_id = result.scalar()
    await db.commit()
    return {"id": str(new_id), "status": "created"}


class AwardDefUpdate(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    achievement: Optional[str] = None
    display_name: Optional[str] = None
    sort_order: Optional[int] = None
    active: Optional[bool] = None


@router.put("/{def_id}")
async def update_award_definition(
    def_id: str, body: AwardDefUpdate, db: AsyncSession = Depends(get_db)
):
    sets = []
    params: dict = {"id": def_id}
    for field in body.model_fields_set:
        sets.append(f"{field} = :{field}")
        params[field] = getattr(body, field)
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    await db.execute(
        text(f"UPDATE org_award_definitions SET {', '.join(sets)} WHERE id = :id"),
        params,
    )
    await db.commit()
    return {"status": "updated"}


@router.delete("/{def_id}")
async def delete_award_definition(def_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("DELETE FROM org_award_definitions WHERE id = :id"),
        {"id": def_id},
    )
    await db.commit()
    return {"status": "deleted"}


@router.post("/seed")
async def seed_definitions(
    org_id: str = Query(...),
    template: str = Query("global"),
    db: AsyncSession = Depends(get_db),
):
    """(Re-)seed an org's award definitions from the global or applecross template."""
    tmpl = APPLECROSS_TEMPLATE if template == "applecross" else GLOBAL_TEMPLATE
    await db.execute(
        text("DELETE FROM org_award_definitions WHERE org_id = :org_id"),
        {"org_id": org_id},
    )
    for category, subcategory, achievement, sort_order in tmpl:
        await db.execute(
            text("""
                INSERT INTO org_award_definitions
                    (id, org_id, category, subcategory, achievement, sort_order)
                VALUES (gen_random_uuid(), :org_id, :category, :subcategory, :achievement, :sort_order)
            """),
            {"org_id": org_id, "category": category, "subcategory": subcategory,
             "achievement": achievement, "sort_order": sort_order},
        )
    await db.commit()
    return {"status": "seeded", "count": len(tmpl)}
