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

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    DiaryCategory, DiaryTaskDefinition, DiaryTaskOccurrence, DiaryTaskDependency, ClubRole,
)

_FREQUENCIES = ("annual", "quarterly", "monthly", "once")

# (name, hex colour) — a starter palette so the Gantt colour-codes by category
# out of the box.
STARTER_DIARY_CATEGORIES = [
    ("Governance", "#8b7cf6"),
    ("Compliance", "#ef4444"),
    ("Tax & Finance", "#22c55e"),
    ("Ground & Equipment", "#f59e0b"),
    ("Facilities", "#06b6d4"),
    ("Events & Fundraising", "#ec4899"),
    ("Sponsorship", "#a855f7"),
    ("Membership", "#3b82f6"),
]

# (title, category name, frequency, default_month, description)
STARTER_DIARY_TASKS = [
    ("Annual General Meeting", "Governance", "annual", 9,
     "Hold the AGM: committee elections, annual reports, motions."),
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
    ("Affiliation fees, league/association", "Tax & Finance", "annual", 8,
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


def _num(v):
    return float(v) if v is not None else None


def _category_dict(c: DiaryCategory) -> dict:
    return {"id": str(c.id), "name": c.name, "sort_order": c.sort_order, "color": c.color}


def _definition_dict(d: DiaryTaskDefinition, depends_on: Optional[list] = None) -> dict:
    return {
        "id": str(d.id), "category_id": str(d.category_id) if d.category_id else None,
        "title": d.title, "description": d.description, "frequency": d.frequency,
        "default_month": d.default_month,
        "default_assignee_position_id": str(d.default_assignee_position_id) if d.default_assignee_position_id else None,
        "default_assignee_member_id": str(d.default_assignee_member_id) if d.default_assignee_member_id else None,
        "responsibility_role_id": str(d.responsibility_role_id) if d.responsibility_role_id else None,
        "third_party": d.third_party,
        "budget_estimate": _num(d.budget_estimate),
        "is_active": d.is_active,
        "reminder_enabled": d.reminder_enabled,
        "reminder_days_before": d.reminder_days_before,
        "depends_on": depends_on if depends_on is not None else [],
    }


def _occurrence_dict(o: DiaryTaskOccurrence) -> dict:
    budget = _num(o.budget_estimate)
    spent = _num(o.actual_expenditure)
    today = date.today()
    is_done = o.status == "done"
    # Late = not done and its target end is in the past, OR the forecast
    # completion overshoots the target end. Over budget = spent > estimate.
    late = bool(not is_done and o.due_date and o.due_date < today) or \
        bool(o.estimated_completion_date and o.due_date and o.estimated_completion_date > o.due_date)
    over_budget = bool(budget is not None and spent is not None and spent > budget)
    return {
        "id": str(o.id), "definition_id": str(o.definition_id), "period_label": o.period_label,
        "start_date": o.start_date.isoformat() if o.start_date else None,
        "due_date": o.due_date.isoformat() if o.due_date else None,
        "status": o.status,
        "percent_complete": o.percent_complete or 0,
        "estimated_completion_date": o.estimated_completion_date.isoformat() if o.estimated_completion_date else None,
        "assigned_to_member_id": str(o.assigned_to_member_id) if o.assigned_to_member_id else None,
        "assigned_to_role_id": str(o.assigned_to_role_id) if o.assigned_to_role_id else None,
        "third_party": o.third_party,
        "budget_estimate": budget,
        "actual_expenditure": spent,
        "over_budget": over_budget,
        "is_late": late,
        "notes": o.notes,
        "completed_at": o.completed_at.isoformat() if o.completed_at else None,
    }


def _current_period_label(frequency: str, today: date) -> str:
    if frequency == "quarterly":
        quarter = (today.month - 1) // 3 + 1
        return f"{today.year} Q{quarter}"
    if frequency == "monthly":
        return f"{today.year}-{today.month:02d}"
    return str(today.year)


def _period_labels_for_year(frequency: str, year: int) -> list[str]:
    """Every period label a definition of this frequency has in one year."""
    if frequency == "quarterly":
        return [f"{year} Q{q}" for q in (1, 2, 3, 4)]
    if frequency == "monthly":
        return [f"{year}-{m:02d}" for m in range(1, 13)]
    return [str(year)]  # annual / once


def _due_for_period(d: DiaryTaskDefinition, period_label: str, year: int) -> Optional[date]:
    """A sensible default target-end date for a generated occurrence."""
    if d.frequency == "quarterly" and " Q" in period_label:
        q = int(period_label.rsplit("Q", 1)[1])
        month = q * 3  # end month of the quarter
        return date(year, month, 1)
    if d.frequency == "monthly" and "-" in period_label:
        month = int(period_label.split("-", 1)[1])
        return date(year, month, 1)
    if d.default_month:
        try:
            return date(year, d.default_month, 1)
        except ValueError:
            return None
    return None


# ─── Categories ───────────────────────────────────────────────────────────────

async def list_categories(session: AsyncSession, org_id) -> list[DiaryCategory]:
    stmt = select(DiaryCategory).where(DiaryCategory.organisation_id == org_id).order_by(
        DiaryCategory.sort_order, func.lower(DiaryCategory.name))
    return (await session.execute(stmt)).scalars().all()


_CATEGORY_COLORS = dict(STARTER_DIARY_CATEGORIES)
_PALETTE = ["#8b7cf6", "#ef4444", "#22c55e", "#f59e0b", "#06b6d4", "#ec4899", "#a855f7", "#3b82f6"]


async def get_or_create_category(session: AsyncSession, org_id, name: str, color: Optional[str] = None) -> DiaryCategory:
    name = (name or "").strip()
    if not name:
        raise ValueError("Category name is required")
    existing = (await session.execute(
        select(DiaryCategory).where(DiaryCategory.organisation_id == org_id, func.lower(DiaryCategory.name) == name.lower())
    )).scalars().first()
    if existing is not None:
        return existing
    # Default colour: a known starter colour for the name, else round-robin.
    if not color:
        count = (await session.execute(
            select(func.count()).select_from(DiaryCategory).where(DiaryCategory.organisation_id == org_id)
        )).scalar_one()
        color = _CATEGORY_COLORS.get(name) or _PALETTE[count % len(_PALETTE)]
    c = DiaryCategory(organisation_id=org_id, name=name[:120], color=color)
    session.add(c)
    await session.flush()
    return c


async def update_category(session: AsyncSession, c: DiaryCategory, **fields) -> DiaryCategory:
    for f in ("name", "sort_order", "color"):
        if f in fields and fields[f] is not None:
            setattr(c, f, fields[f])
    return c


async def delete_category(session: AsyncSession, c: DiaryCategory) -> None:
    await session.delete(c)


async def seed_starter_categories(session: AsyncSession, org_id) -> int:
    existing = {n.lower() for n in (await session.execute(
        select(DiaryCategory.name).where(DiaryCategory.organisation_id == org_id)
    )).scalars().all()}
    seeded = 0
    for i, (name, color) in enumerate(STARTER_DIARY_CATEGORIES):
        if name.lower() in existing:
            continue
        session.add(DiaryCategory(organisation_id=org_id, name=name, color=color, sort_order=i))
        seeded += 1
    if seeded:
        await session.flush()
    return seeded


# ─── Task definitions ─────────────────────────────────────────────────────────

async def _deps_by_definition(session: AsyncSession, org_id) -> dict:
    """definition_id -> [depends_on_definition_id, …]."""
    rows = (await session.execute(
        select(DiaryTaskDependency.definition_id, DiaryTaskDependency.depends_on_definition_id)
        .where(DiaryTaskDependency.organisation_id == org_id)
    )).all()
    out: dict = {}
    for def_id, dep_id in rows:
        out.setdefault(str(def_id), []).append(str(dep_id))
    return out


async def list_definitions(session: AsyncSession, org_id, *, include_inactive: bool = False) -> list[dict]:
    stmt = select(DiaryTaskDefinition).where(DiaryTaskDefinition.organisation_id == org_id)
    if not include_inactive:
        stmt = stmt.where(DiaryTaskDefinition.is_active.is_(True))
    stmt = stmt.order_by(func.lower(DiaryTaskDefinition.title))
    rows = (await session.execute(stmt)).scalars().all()
    deps = await _deps_by_definition(session, org_id)
    return [_definition_dict(d, deps.get(str(d.id), [])) for d in rows]


async def create_definition(session: AsyncSession, org_id, **fields) -> DiaryTaskDefinition:
    title = (fields.get("title") or "").strip()
    if not title:
        raise ValueError("Title is required")
    frequency = fields.get("frequency") or "annual"
    if frequency not in _FREQUENCIES:
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
        responsibility_role_id=fields.get("responsibility_role_id"),
        third_party=fields.get("third_party"),
        budget_estimate=fields.get("budget_estimate"),
        reminder_enabled=fields.get("reminder_enabled") or False,
        reminder_days_before=fields.get("reminder_days_before") or 14,
    )
    session.add(d)
    await session.flush()
    return d


async def update_definition(session: AsyncSession, d: DiaryTaskDefinition, **fields) -> DiaryTaskDefinition:
    if fields.get("frequency") and fields["frequency"] not in _FREQUENCIES:
        raise ValueError("Invalid frequency")
    for f in ("title", "description", "frequency", "is_active",
              "reminder_enabled", "reminder_days_before"):
        if f in fields and fields[f] is not None:
            setattr(d, f, fields[f])
    # Nullable fields may be cleared explicitly.
    for f in ("default_month", "category_id", "default_assignee_position_id", "default_assignee_member_id",
              "responsibility_role_id", "third_party", "budget_estimate"):
        if f in fields:
            setattr(d, f, fields[f])
    return d


async def archive_definition(session: AsyncSession, d: DiaryTaskDefinition) -> None:
    d.is_active = False


# ─── Dependencies ─────────────────────────────────────────────────────────────

async def _would_cycle(session: AsyncSession, org_id, definition_id, depends_on_id) -> bool:
    """True if making definition_id depend on depends_on_id creates a cycle —
    i.e. depends_on_id already (transitively) depends on definition_id."""
    edges = await _deps_by_definition(session, org_id)
    stack = [str(depends_on_id)]
    seen = set()
    target = str(definition_id)
    while stack:
        cur = stack.pop()
        if cur == target:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(edges.get(cur, []))
    return False


async def add_dependency(session: AsyncSession, org_id, definition_id, depends_on_id) -> None:
    if str(definition_id) == str(depends_on_id):
        raise ValueError("A task can't depend on itself")
    if await _would_cycle(session, org_id, definition_id, depends_on_id):
        raise ValueError("That would create a circular dependency")
    existing = (await session.execute(
        select(DiaryTaskDependency).where(
            DiaryTaskDependency.definition_id == definition_id,
            DiaryTaskDependency.depends_on_definition_id == depends_on_id)
    )).scalars().first()
    if existing is not None:
        return
    session.add(DiaryTaskDependency(
        organisation_id=org_id, definition_id=definition_id, depends_on_definition_id=depends_on_id))
    await session.flush()


async def remove_dependency(session: AsyncSession, org_id, definition_id, depends_on_id) -> None:
    await session.execute(delete(DiaryTaskDependency).where(
        DiaryTaskDependency.organisation_id == org_id,
        DiaryTaskDependency.definition_id == definition_id,
        DiaryTaskDependency.depends_on_definition_id == depends_on_id))
    await session.flush()


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
        due = _due_for_period(d, period, today.year)
        occ = DiaryTaskOccurrence(
            organisation_id=org_id, definition_id=d.id, period_label=period, due_date=due,
            assigned_to_member_id=d.default_assignee_member_id,
            assigned_to_role_id=d.responsibility_role_id,
            third_party=d.third_party, budget_estimate=d.budget_estimate,
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
    if "status" in fields and fields["status"] is not None:
        occ.status = fields["status"]
    if "percent_complete" in fields and fields["percent_complete"] is not None:
        occ.percent_complete = max(0, min(100, int(fields["percent_complete"])))
    # Nullable planning/tracking fields may be cleared explicitly.
    for f in ("notes", "assigned_to_member_id", "assigned_to_role_id", "start_date", "due_date",
              "estimated_completion_date", "third_party", "budget_estimate", "actual_expenditure"):
        if f in fields:
            setattr(occ, f, fields[f])
    if "status" in fields and fields["status"] is not None:
        occ.completed_at = func.now() if fields["status"] == "done" else None
        # Finishing a task also completes its progress bar.
        if fields["status"] == "done":
            occ.percent_complete = 100
    occ.updated_at = func.now()
    return occ


# ─── Season plan (generate + list + Gantt) ───────────────────────────────────

async def season_years(session: AsyncSession, org_id) -> list[int]:
    """Distinct calendar years present in occurrence period labels, newest
    first — the seasons a club has generated a plan for."""
    labels = (await session.execute(
        select(DiaryTaskOccurrence.period_label).where(DiaryTaskOccurrence.organisation_id == org_id).distinct()
    )).scalars().all()
    years = set()
    for lbl in labels:
        head = (lbl or "").split(" ")[0].split("-")[0]
        if head.isdigit():
            years.add(int(head))
    return sorted(years, reverse=True)


async def generate_season(session: AsyncSession, org_id, year: int) -> int:
    """Create every missing occurrence for ``year`` across all active
    definitions — the "generate this season's task list" action. Idempotent:
    a period that already has an occurrence is skipped, so re-running just
    fills gaps (e.g. after adding a new definition). Values (responsible role,
    third party, budget) are copied from the definition as starting points."""
    definitions = (await session.execute(
        select(DiaryTaskDefinition).where(DiaryTaskDefinition.organisation_id == org_id,
                                          DiaryTaskDefinition.is_active.is_(True))
    )).scalars().all()
    created = 0
    for d in definitions:
        if d.frequency == "once":
            exists = (await session.execute(
                select(DiaryTaskOccurrence.id).where(DiaryTaskOccurrence.definition_id == d.id)
            )).scalars().first()
            if exists is not None:
                continue
            periods = [str(year)]
        else:
            periods = _period_labels_for_year(d.frequency, year)
        existing_periods = set((await session.execute(
            select(DiaryTaskOccurrence.period_label).where(DiaryTaskOccurrence.definition_id == d.id)
        )).scalars().all())
        for period in periods:
            if period in existing_periods:
                continue
            session.add(DiaryTaskOccurrence(
                organisation_id=org_id, definition_id=d.id, period_label=period,
                due_date=_due_for_period(d, period, year),
                assigned_to_member_id=d.default_assignee_member_id,
                assigned_to_role_id=d.responsibility_role_id,
                third_party=d.third_party, budget_estimate=d.budget_estimate,
            ))
            created += 1
    if created:
        await session.flush()
    return created


async def season_plan(session: AsyncSession, org_id, year: int) -> dict:
    """All of a year's occurrences joined with their definition + category —
    backs the season list, calendar and Gantt views. Dependencies are returned
    at the definition level (the template's ordering) so the Gantt can draw
    the links between bars."""
    rows = (await session.execute(
        select(DiaryTaskOccurrence, DiaryTaskDefinition, DiaryCategory)
        .join(DiaryTaskDefinition, DiaryTaskDefinition.id == DiaryTaskOccurrence.definition_id)
        .outerjoin(DiaryCategory, DiaryCategory.id == DiaryTaskDefinition.category_id)
        # Every period label starts with the four-digit year ("2026",
        # "2026 Q1", "2026-07").
        .where(DiaryTaskOccurrence.organisation_id == org_id,
               DiaryTaskOccurrence.period_label.like(f"{year}%"))
        .order_by(DiaryTaskOccurrence.due_date.nullslast(), func.lower(DiaryTaskDefinition.title))
    )).all()
    deps = await _deps_by_definition(session, org_id)
    tasks = []
    for occ, d, cat in rows:
        t = _occurrence_dict(occ)
        t["title"] = d.title
        t["frequency"] = d.frequency
        t["category_id"] = str(d.category_id) if d.category_id else None
        t["category_name"] = cat.name if cat else None
        t["category_color"] = (cat.color if cat else None) or "#8b7cf6"
        t["depends_on"] = deps.get(str(occ.definition_id), [])
        tasks.append(t)
    return {"year": year, "tasks": tasks}
