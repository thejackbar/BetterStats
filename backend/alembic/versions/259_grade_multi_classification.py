"""Grades carry several classifications, not one

A grade is not one thing. "Women's T20 Grade 2" is a women's grade AND a T20
grade, and until now ``grades.category`` could only hold one answer, so the
club had to pick which half of the truth to keep.

Two array columns replace that single answer:

- ``categories`` TEXT[] — the grade TYPE(s): senior (men's) / junior / womens /
  masters / mixed. A grade can be more than one ("Girls Under 14" is junior and
  women's).
- ``match_formats`` TEXT[] — the FORMAT(s) played: two_day / one_day / t20.

``category`` is deliberately kept and kept in step (the first entry of
``categories``, in canonical order). Every existing reader — the public grade
grouping, the AFL silo's own labels, ``grade_labels.org_grade_categories`` —
keeps working untouched, and a club that never opens the Grades screen loses
nothing.

Both are NULL for every existing grade, which reads as "not classified" and
falls back to the same name-based suggestion the single column already fell
back to. Nothing changes for any club until someone ticks a box.

Additive and backward-compatible. Mirrored idempotently in main.py's lifespan
so the API boots even if alembic hasn't run yet.

Revision ID: 259
Revises: 258
Create Date: 2026-08-17
"""
from alembic import op


revision = '259'
down_revision = '258'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE grades ADD COLUMN IF NOT EXISTS categories TEXT[]")
    op.execute("ALTER TABLE grades ADD COLUMN IF NOT EXISTS match_formats TEXT[]")
    # Seed the multi column from the single one a club has already confirmed, so
    # the new screen opens showing what they set rather than an empty row they
    # have to re-answer. A grade with no confirmed category stays NULL and keeps
    # reading its name-based suggestion.
    op.execute(
        "UPDATE grades SET categories = ARRAY[category] "
        "WHERE categories IS NULL AND category IS NOT NULL AND category <> ''"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE grades DROP COLUMN IF EXISTS match_formats")
    op.execute("ALTER TABLE grades DROP COLUMN IF EXISTS categories")
