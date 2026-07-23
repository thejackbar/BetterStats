"""Club Diary — annual/recurring compliance & maintenance task calendar.

Nothing is auto-seeded (a club adopts the starter set below, or builds its
own — see seed_starter_definitions), same opt-in posture as Committee
Administration's starter positions and Qualifications' starter types.

A definition (the recurring task) and its occurrences (one row per period —
a year, or a year+quarter for a quarterly task) are deliberately separate,
so "what did we do about this last year" is a plain query rather than
something we'd have to reconstruct from an edit history. Occurrences are
created lazily — see ensure_occurrences_for_period, called by board() —
rather than by a scheduled job, so a club visiting the diary for the first
time in a new year just sees this year's tasks appear with no cron
dependency.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import DiaryCategory, DiaryTaskDefinition, DiaryTaskOccurrence

# (title, category name, frequency, default_month, description)
STARTER_DIARY_TASKS = [
    ("Annual General Meeting", "Governance", "annual", 9,
     "Hold the AGM — committee elections, annual reports, motions."),
    ("Annual return / incorporation renewal", "Compliance", "annual", 10,
     "Lodge the club's annual return with the incorporating body (state associations register)."),
    ("Public liability insurance renewal", "Compliance", "annual", 6,
     "Renew public liability and volunteer personal accident cover."),
    ("Working With Children Check audit", "Compliance", "annual", 8,
     "Check every coach/volunteer working with children holds a current WWCC."),
    ("BAS lodgement", "Tax & Finance", "quarterly", None,
     "Lodge the quarter's Business Activity Statement."),
    ("Annual tax return / financial statements", "Tax & Finance", "annual", 9,
     "Prepare and lodge the club's annual income tax return (if applicable) and annual financial statements for member approval."),
    ("Affiliation fees — league/association", "Tax & Finance", "annual", 8,
     "Pay the club's annual affiliation fees to the league/association and Cricket Australia."),
    ("Pre-season ground preparation", "Ground & Equipment", "annual", 8,
     "Wicket/outfield renovation, top-dressing, line marking ahead of the new season."),
    ("End-of-season equipment service", "Ground & Equipment", "annual", 4,
     "Service the mower/roller, repair covers, audit training gear for replacement."),
    ("Canteen/bar liquor licence renewal", "Compliance", "annual", 5,
     "Renew the club's liquor licence and RSA compliance if the canteen/bar serves alcohol."),
    ("Ground lease / facility agreement review", "Compliance", "annual", 11,
     "Review the ground lease or facility-use agreement with the council/land owner."),
]


def _category_dict(c: DiaryCategory) -> dict:
    return {"id": str(c.id), "name": c.name, "sort_order": c.sort_order}


def _definition_dict(d: DiaryTaskDefinition) -> dict:
    return {
        "id": str(d.id), "category_id": str(d.category_id) if d.category_id else None,
        "title": d.title, "description": d.description, "frequency": d.frequency,
        "default_month": d.default_month,
        "default_assignee_position_id": str(d.default_assignee_position_id) if d.default_assignee_position_id else None,
        "default_assignee_member_id": str(d.default_assignee_member_id) if d.default_assignee_member_id else None,
        "is_active": d.is_active,
        "reminder_enabled": d.reminder_enabled,
        "reminder_days_before": d.reminder_days_before,
    }


def _occurrence_dict(o: DiaryTaskOccurrence) -> dict:
    return {
        "id": str(o.id), "definition_id": str(o.definition_id), "period_label": o.period_label,
        "due_date": o.due_date.isoformat() if o.due_date else None,
        "status": o.status,
        "assigned_to_member_id": str(o.assigned_to_member_id) if o.assigned_to_member_id else None,
        "notes": o.notes,
        "completed_at": o.completed_at.isoformat() if o.completed_at else None,
    }


def _current_period_label(frequency: str, today: date) -> str:
    if frequency == "quarterly":
        quarter = (today.month - 1) // 3 + 1
        return f"{today.year} Q{quarter}"
    return str(today.year)


# ─── Categories ───────────────────────────────────────────────────────────────

async def list_categories(session: AsyncSession, org_id) -> list[DiaryCategory]:
    stmt = select(DiaryCategory).where(DiaryCategory.organisation_id == org_id).order_by(
        DiaryCategory.sort_order, func.lower(DiaryCategory.name))
    return (await session.execute(stmt)).scalars().all()


async def get_or_create_category(session: AsyncSession, org_id, name: str) -> DiaryCategory:
    name = (name or "").strip()
    if not name:
        raise ValueError("Category name is required")
    existing = (await session.execute(
        select(DiaryCategory).where(DiaryCategory.organisation_id == org_id, func.lower(DiaryCategory.name) == name.lower())
    )).scalars().first()
    if existing is not None:
        return existing
    c = DiaryCategory(organisation_id=org_id, name=name[:120])
    session.add(c)
    await session.flush()
    return c


async def update_category(session: AsyncSession, c: DiaryCategory, **fields) -> DiaryCategory:
    for f in ("name", "sort_order"):
        if f in fields and fields[f] is not None:
            setattr(c, f, fields[f])
    return c


async def delete_category(session: AsyncSession, c: DiaryCategory) -> None:
    await session.delete(c)


# ─── Task definitions ─────────────────────────────────────────────────────────

async def list_definitions(session: AsyncSession, org_id, *, include_inactive: bool = False) -> list[DiaryTaskDefinition]:
    stmt = select(DiaryTaskDefinition).where(DiaryTaskDefinition.organisation_id == org_id)
    if not include_inactive:
        stmt = stmt.where(DiaryTaskDefinition.is_active.is_(True))
    stmt = stmt.order_by(func.lower(DiaryTaskDefinition.title))
    return (await session.execute(stmt)).scalars().all()


async def create_definition(session: AsyncSession, org_id, **fields) -> DiaryTaskDefinition:
    title = (fields.get("title") or "").strip()
    if not title:
        raise ValueError("Title is required")
    frequency = fields.get("frequency") or "annual"
    if frequency not in ("annual", "quarterly", "once"):
        raise ValueError("Invalid frequency")
    existing = (await session.execute(
        select(DiaryTaskDefinition).where(DiaryTaskDefinition.organisation_id == org_id,
                                          func.lower(DiaryTaskDefinition.title) == title.lower())
    )).scalars().first()
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            return existing
        raise ValueError(f'A task called "{title}" already exists')
    d = DiaryTaskDefinition(
        organisation_id=org_id, title=title[:300], description=fields.get("description"),
        frequency=frequency, default_month=fields.get("default_month"),
        category_id=fields.get("category_id"),
        default_assignee_position_id=fields.get("default_assignee_position_id"),
        default_assignee_member_id=fields.get("default_assignee_member_id"),
        reminder_enabled=fields.get("reminder_enabled") or False,
        reminder_days_before=fields.get("reminder_days_before") or 14,
    )
    session.add(d)
    await session.flush()
    return d


async def update_definition(session: AsyncSession, d: DiaryTaskDefinition, **fields) -> DiaryTaskDefinition:
    for f in ("title", "description", "frequency", "default_month", "category_id",
              "default_assignee_position_id", "default_assignee_member_id", "is_active",
              "reminder_enabled", "reminder_days_before"):
        if f in fields and fields[f] is not None:
            setattr(d, f, fields[f])
    return d


async def archive_definition(session: AsyncSession, d: DiaryTaskDefinition) -> None:
    d.is_active = False


async def seed_starter_definitions(session: AsyncSession, org_id) -> int:
    existing_titles = {t.lower() for t in (await session.execute(
        select(DiaryTaskDefinition.title).where(DiaryTaskDefinition.organisation_id == org_id)
    )).scalars().all()}
    seeded = 0
    for title, category_name, frequency, default_month, description in STARTER_DIARY_TASKS:
        if title.lower() in existing_titles:
            continue
        category = await get_or_create_category(session, org_id, category_name)
        session.add(DiaryTaskDefinition(
            organisation_id=org_id, category_id=category.id, title=title, description=description,
            frequency=frequency, default_month=default_month,
        ))
        seeded += 1
    if seeded:
        await session.flush()
    return seeded


# ─── Occurrences ──────────────────────────────────────────────────────────────

async def ensure_occurrences_for_period(session: AsyncSession, org_id, *, today: Optional[date] = None) -> list[DiaryTaskOccurrence]:
    """Lazily creates the current period's occurrence for every active
    definition that doesn't already have one. A 'once' definition only ever
    gets a single occurrence, regardless of period — once any occurrence
    exists for it, it's never rolled forward."""
    today = today or date.today()
    definitions = (await session.execute(
        select(DiaryTaskDefinition).where(DiaryTaskDefinition.organisation_id == org_id, DiaryTaskDefinition.is_active.is_(True))
    )).scalars().all()
    created = []
    for d in definitions:
        if d.frequency == "once":
            existing = (await session.execute(
                select(DiaryTaskOccurrence).where(DiaryTaskOccurrence.definition_id == d.id)
            )).scalars().first()
            if existing is not None:
                continue
            period = str(today.year)
        else:
            period = _current_period_label(d.frequency, today)
            existing = (await session.execute(
                select(DiaryTaskOccurrence).where(
                    DiaryTaskOccurrence.definition_id == d.id, DiaryTaskOccurrence.period_label == period)
            )).scalars().first()
            if existing is not None:
                continue
        due = None
        if d.default_month and d.frequency == "annual":
            try:
                due = date(today.year, d.default_month, 1)
            except ValueError:
                due = None
        occ = DiaryTaskOccurrence(
            organisation_id=org_id, definition_id=d.id, period_label=period, due_date=due,
            assigned_to_member_id=d.default_assignee_member_id,
        )
        session.add(occ)
        created.append(occ)
    if created:
        await session.flush()
    return created


async def board(session: AsyncSession, org_id, *, today: Optional[date] = None) -> list[dict]:
    """Every active definition with its CURRENT period's occurrence — the
    Club Diary's main view. Ensures this period's occurrences exist first."""
    today = today or date.today()
    await ensure_occurrences_for_period(session, org_id, today=today)
    definitions = (await session.execute(
        select(DiaryTaskDefinition).where(DiaryTaskDefinition.organisation_id == org_id, DiaryTaskDefinition.is_active.is_(True))
        .order_by(func.lower(DiaryTaskDefinition.title))
    )).scalars().all()
    out = []
    for d in definitions:
        if d.frequency == "once":
            occ = (await session.execute(
                select(DiaryTaskOccurrence).where(DiaryTaskOccurrence.definition_id == d.id)
                .order_by(DiaryTaskOccurrence.created_at.desc())
            )).scalars().first()
        else:
            period = _current_period_label(d.frequency, today)
            occ = (await session.execute(
                select(DiaryTaskOccurrence).where(
                    DiaryTaskOccurrence.definition_id == d.id, DiaryTaskOccurrence.period_label == period)
            )).scalar_one_or_none()
        out.append({**_definition_dict(d), "occurrence": _occurrence_dict(occ) if occ else None})
    return out


async def history(session: AsyncSession, definition_id) -> list[dict]:
    rows = (await session.execute(
        select(DiaryTaskOccurrence).where(DiaryTaskOccurrence.definition_id == definition_id)
        .order_by(DiaryTaskOccurrence.period_label.desc())
    )).scalars().all()
    return [_occurrence_dict(o) for o in rows]


async def update_occurrence(session: AsyncSession, occ: DiaryTaskOccurrence, **fields) -> DiaryTaskOccurrence:
    for f in ("status", "notes", "assigned_to_member_id", "due_date"):
        if f in fields and fields[f] is not None:
            setattr(occ, f, fields[f])
    if "status" in fields and fields["status"] is not None:
        occ.completed_at = func.now() if fields["status"] == "done" else None
    occ.updated_at = func.now()
    return occ
