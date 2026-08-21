"""AFL award catalogue — the customisable per-club award types that back the
Awards page's dropdowns. Ported from cricket's award_definitions.py: the
``org_award_definitions`` schema (category/subcategory/achievement/
display_name/sort_order/active) carries zero sport-specific columns, so only
the seed *content* needed rewriting for AFL. Org is resolved from the
session (get_current_club), never a client-supplied org_id.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_AWARDS, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club, get_current_user

router = APIRouter(prefix="/award-definitions", tags=["afl-award-definitions"])


def _numbered(rows):
    return [(cat, sub, ach, i) for i, (cat, sub, ach) in enumerate(rows)]


def _build_starter_template():
    """Lean, club-agnostic AFL award set — the season awards most clubs hand
    out, a starter team block, milestone ladders, committee roles and the two
    honours. A club extends it with its own teams/trophies afterwards."""
    r = []

    for a in [
        'Best & Fairest', 'Leading Goalkicker', 'Best Team Player',
        "Coach's Award", 'Most Improved', 'Rising Star / Best First Year Player',
        'Best Clubperson', 'Trainers Award',
    ]:
        r.append(('Club Award', 'Season', a))

    for team in ['A Grade', 'B Grade', 'C Grade']:
        for a in ['Best & Fairest', 'Leading Goalkicker']:
            r.append(('Club Award', team, a))

    for a in ['Premiership', 'Captain', 'Best on Ground — Grand Final']:
        r.append(('Premiership', 'Team', a))

    for a in ['50 Games', '100 Games', '150 Games', '200 Games', '250 Games', '300 Games']:
        r.append(('Milestone', 'Games', a))
    for a in ['100 Goals', '250 Goals', '500 Goals', '1000 Goals']:
        r.append(('Milestone', 'Goals', a))

    # Office Bearer, in the same five groups cricket uses (Executive
    # Committee / General Committee / Captains / Coaches / Other Roles)
    # rather than the one flat "Committee" list this started with. The groups
    # are what the Honour Board reads: a club with every seat under one
    # heading gets one undifferentiated column, where a President board and a
    # Coaches board are what somebody is actually looking for. Roles are
    # football's own — a football club has a Runner and a Property Steward and
    # no Curator. **A club that already has definitions keeps them** — seeding
    # is a no-op once any exist, so this only changes what a NEW club starts
    # with, and the extra rows are a starting point a club edits.
    for a in ['President', 'Vice President', 'Secretary', 'Treasurer',
              'Football Operations Manager', 'Registrar']:
        r.append(('Office Bearer', 'Executive Committee', a))
    for a in ['Committee Member', 'Junior Committee', 'Womens Committee']:
        r.append(('Office Bearer', 'General Committee', a))
    for a in ['Senior Captain', 'Reserves Captain', 'Under 19s Captain',
              "Women's Captain", 'Vice Captain']:
        r.append(('Office Bearer', 'Captains', a))
    for a in ['Senior Coach', 'Club Coach', 'Assistant Coach', 'Reserves Coach',
              'Under 19s Coach', "Women's Coach", 'Development Coach']:
        r.append(('Office Bearer', 'Coaches', a))
    for a in ['Chairman of Selectors', 'Team Manager', 'Runner', 'Trainer',
              'Head Trainer', 'Property Steward', 'Ground Manager',
              'Sponsorship Manager', 'Social Media Manager',
              'Canteen Manager', 'Bar Manager', 'League Delegate']:
        r.append(('Office Bearer', 'Other Roles', a))

    r.append(('Hall of Fame', 'Club', 'Hall of Fame'))
    r.append(('Life Membership', 'Club', 'Life Membership'))

    return _numbered(r)


STARTER_TEMPLATE = _build_starter_template()
TEMPLATES = {"starter": STARTER_TEMPLATE}


async def seed_org_definitions(conn, org_id: str, template: list) -> int:
    """Insert template rows for an org. No-op if definitions already exist."""
    count_result = await conn.execute(
        text("SELECT COUNT(*) FROM org_award_definitions WHERE org_id = :org_id"), {"org_id": org_id})
    if count_result.scalar() > 0:
        return 0
    for category, subcategory, achievement, sort_order in template:
        await conn.execute(text("""
            INSERT INTO org_award_definitions
                (id, org_id, category, subcategory, achievement, sort_order)
            VALUES (gen_random_uuid(), :org_id, :category, :subcategory, :achievement, :sort_order)
        """), {"org_id": org_id, "category": category, "subcategory": subcategory,
               "achievement": achievement, "sort_order": sort_order})
    return len(template)


@router.get("")
async def list_award_definitions(
    club: Organisation = Depends(get_current_club),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(text("""
        SELECT id, org_id, category, subcategory, achievement, display_name, sort_order, active
        FROM org_award_definitions WHERE org_id = :org_id ORDER BY sort_order, id
    """), {"org_id": str(club.id)})
    return [dict(r) for r in rows.mappings().all()]


class AwardDefCreate(BaseModel):
    category: str
    subcategory: Optional[str] = None
    achievement: Optional[str] = None
    display_name: Optional[str] = None
    sort_order: int = 0
    active: bool = True


@router.post("")
async def create_award_definition(
    body: AwardDefCreate,
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        INSERT INTO org_award_definitions
            (id, org_id, category, subcategory, achievement, display_name, sort_order, active)
        VALUES (gen_random_uuid(), :org_id, :category, :subcategory, :achievement, :display_name, :sort_order, :active)
        RETURNING id
    """), {
        "org_id": str(club.id), "category": body.category,
        "subcategory": body.subcategory, "achievement": body.achievement,
        "display_name": body.display_name or None,
        "sort_order": body.sort_order, "active": body.active,
    })
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
    def_id: str,
    body: AwardDefUpdate,
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    db: AsyncSession = Depends(get_db),
):
    sets = []
    params: dict = {"id": def_id, "org_id": str(club.id)}
    for field in body.model_fields_set:
        sets.append(f"{field} = :{field}")
        params[field] = getattr(body, field)
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    await db.execute(text(
        f"UPDATE org_award_definitions SET {', '.join(sets)} WHERE id = :id AND org_id = :org_id"
    ), params)
    await db.commit()
    return {"status": "updated"}


@router.delete("/{def_id}")
async def delete_award_definition(
    def_id: str,
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(text(
        "DELETE FROM org_award_definitions WHERE id = :id AND org_id = :org_id"
    ), {"id": def_id, "org_id": str(club.id)})
    await db.commit()
    return {"status": "deleted"}


@router.post("/seed")
async def seed_definitions(
    template: str = "starter",
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    db: AsyncSession = Depends(get_db),
):
    """(Re-)seed this club's award definitions from a named template."""
    tmpl = TEMPLATES.get(template, STARTER_TEMPLATE)
    org_id = str(club.id)
    await db.execute(text("DELETE FROM org_award_definitions WHERE org_id = :org_id"), {"org_id": org_id})
    for category, subcategory, achievement, sort_order in tmpl:
        await db.execute(text("""
            INSERT INTO org_award_definitions
                (id, org_id, category, subcategory, achievement, sort_order)
            VALUES (gen_random_uuid(), :org_id, :category, :subcategory, :achievement, :sort_order)
        """), {"org_id": org_id, "category": category, "subcategory": subcategory,
               "achievement": achievement, "sort_order": sort_order})
    await db.commit()
    return {"status": "seeded", "count": len(tmpl)}
