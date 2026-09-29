"""Which grade categories a football club counts in its stats by default.

``organisations.stats_grade_categories`` is the club's list of categories to
count (senior, colts, womens, masters, integrated). NULL, the default, counts
every category, so a club that never touches the setting reads exactly what it
always did. A club that leaves out, say, its colts gets figures summed from the
per-grade rows the rollup already writes, instead of the whole-season row that
counts every grade at once.

An imported or manual row with no grade is KEPT: it is not a row we know to be
in a category left out (cricket's grade_scope makes the same call).

A picked grade always wins; callers only apply this when no grade is picked.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.afl.grade_labels import GRADE_CATEGORIES, normalise_category, suggest_category


def clean_categories(raw) -> Optional[list[str]]:
    """The stored shape: a list of known categories, or None for "every one".
    Empty, junk, or every category at once all mean None."""
    if not isinstance(raw, (list, tuple)):
        return None
    out = [c for c in GRADE_CATEGORIES if c in {normalise_category(v) for v in raw}]
    if not out or len(out) == len(GRADE_CATEGORIES):
        return None
    return out


def category_of(name: str, stored) -> str:
    return normalise_category(stored) or suggest_category(name)


async def excluded_grade_ids(db: AsyncSession, org_id) -> list[uuid.UUID]:
    """Every grade row of this club whose category the club leaves out."""
    row = (await db.execute(text("SELECT stats_grade_categories FROM organisations WHERE id = :o"),
                            {"o": str(org_id)})).first()
    keep = clean_categories(row[0] if row else None)
    if not keep:
        return []
    rows = await db.execute(text("""
        SELECT gr.id, gr.name, gr.category FROM grades gr
        JOIN seasons s ON s.id = gr.season_id WHERE s.organisation_id = :o
    """), {"o": str(org_id)})
    return [r.id for r in rows if category_of(r.name, r.category) not in keep]


async def left_out_labels(db: AsyncSession, org_id) -> list[str]:
    """The categories the club leaves out, for a page to say so."""
    from app.services.afl.grade_labels import CATEGORY_LABELS
    row = (await db.execute(text("SELECT stats_grade_categories FROM organisations WHERE id = :o"),
                            {"o": str(org_id)})).first()
    keep = clean_categories(row[0] if row else None)
    if not keep:
        return []
    # Only name a category the club actually fields: "Masters grades are left
    # out" means nothing to a club with no masters side.
    rows = await db.execute(text("""
        SELECT gr.name, gr.category FROM grades gr
        JOIN seasons s ON s.id = gr.season_id WHERE s.organisation_id = :o
    """), {"o": str(org_id)})
    fielded = {category_of(r.name, r.category) for r in rows}
    return [CATEGORY_LABELS.get(c, c) for c in GRADE_CATEGORIES if c not in keep and c in fielded]


def synced_rows(alias: str, excluded: list) -> str:
    """Which afl_player_season_stats rows to sum: the whole-season row, or,
    when something is left out, the per-grade rows that are kept."""
    if not excluded:
        return f"{alias}.grade_id IS NULL"
    return f"{alias}.grade_id IS NOT NULL AND NOT ({alias}.grade_id = ANY(:excl))"


def other_rows(alias: str, excluded: list) -> str:
    """An imported or manual row: kept unless its grade is left out."""
    if not excluded:
        return ""
    return f" AND ({alias}.grade_id IS NULL OR NOT ({alias}.grade_id = ANY(:excl)))"


def game_rows(alias: str, excluded: list) -> str:
    """A game-level read (a game's own grade)."""
    if not excluded:
        return ""
    return f" AND NOT ({alias}.id = ANY(:excl))"
