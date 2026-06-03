"""Add grades.grassroots_id (raw CA grade GUID) — foundation for per-club grade ids.

Phase 1 of giving grades the same per-club identity Seasons and Players already
have. A Cricket Australia grade is a *competition-wide* entity: one grade GUID
("1st Grade", "One Day Grade 2", …) is shared by every club that fields a side in
it (the scores feed for a single grade returns matches between all ~10 clubs).
Using that shared GUID as a global primary key means only the *first* club to
sync a grade ever creates the row — every later club's sync hits the global
`session.get(Grade, guid)`, finds it already exists, and skips it, so the grade
never attaches to the later club's season. Symptom: a club that shares senior
grades with an earlier-synced club shows only the handful of grades unique to it
in the grade dropdown / BetterSelect auto-seed, and its game-level scorecards for
the shared grades are never pulled (the scores pass only discovers matches for
grades in that club's own season).

This migration is the safe, non-breaking groundwork (same shape as 062 for
players):
  * add the nullable grassroots_id column,
  * backfill it from the current id (which IS the raw CA grade GUID for every
    existing row), so the column is the stable join-key for all existing grades,
  * add a UNIQUE (season_id, grassroots_id) constraint. season_id is already a
    per-club derived id, so this enforces "one grade row per club-season per CA
    grade GUID". The backfill makes every grassroots_id == the row's (globally
    unique) id, so it can't fail on current data; sync keeps it true by looking
    a grade up by (org, grassroots_id) before creating.

No id changes and no FK rewrites happen here. The sync code (Phase 2) starts
minting per-club uuid5(org, guid) ids for a grade GUID that already belongs to
another club, and keeps the raw GUID in grassroots_id so the grassroots API
calls (grade matches / ladder / per-grade stats) still use the shared GUID.
Existing single-club grades keep their raw-GUID ids (grassroots_id == id), so
the game-level sync that matches grade.id == raw GUID is byte-for-byte
unaffected for every club already on the platform.

Revision ID: 067
Revises: 066
Create Date: 2026-06-03

"""
from alembic import op
import sqlalchemy as sa


revision = '067'
down_revision = '066'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('grades', sa.Column('grassroots_id', sa.Text(), nullable=True))
    # The existing primary key IS the raw CA grade GUID for every row.
    op.execute("UPDATE grades SET grassroots_id = id::text WHERE grassroots_id IS NULL")
    # One grade row per club-season per CA grade GUID. Backfill makes every
    # grassroots_id == the row's (globally unique) id, so this can't fail on
    # current data; sync keeps it true by looking up before creating.
    op.create_unique_constraint(
        'uq_grade_season_grassroots', 'grades', ['season_id', 'grassroots_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_grade_season_grassroots', 'grades', type_='unique')
    op.drop_column('grades', 'grassroots_id')
