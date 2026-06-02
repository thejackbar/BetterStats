"""Add players.grassroots_id (raw CA participant GUID) — foundation for per-club player ids.

Phase 1 of giving players the same per-club identity Seasons already have. A CA
participant GUID is shared across every club a person plays for, so using it as a
global primary key co-mingles a dual-club player's stats onto one row (see
migration 060 for the read-side guard that masked the symptom). The real fix is
to key a player per club — id = uuid5(org, guid) — and keep the raw GUID in a
column to match scorecard participantIds.

This migration is the safe, non-breaking groundwork:
  * add the nullable grassroots_id column,
  * backfill it from the current id (which IS the raw GUID for every existing
    row), so the column is the stable join-key for all existing players,
  * add a UNIQUE (organisation_id, grassroots_id) constraint — satisfied by the
    backfill (every id is distinct) and the invariant sync will maintain going
    forward (one player per org per CA GUID).

No id changes and no FK rewrites happen here. The sync code (Phase 2) starts
looking players up by (org, grassroots_id) and minting uuid5 ids for newly-seen
(org, guid) pairs, so the second club of a shared GUID finally gets its own row.
Existing rows keep their raw-GUID ids, so URLs, merges and game-level FKs are
untouched.

Revision ID: 062
Revises: 061
Create Date: 2026-06-02

"""
from alembic import op
import sqlalchemy as sa


revision = '062'
down_revision = '061'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('players', sa.Column('grassroots_id', sa.Text(), nullable=True))
    # The existing primary key IS the raw CA participant GUID for every row.
    op.execute("UPDATE players SET grassroots_id = id::text WHERE grassroots_id IS NULL")
    # One player per org per CA GUID. Backfill makes every grassroots_id == the
    # row's (globally unique) id, so this can't fail on current data; sync keeps
    # it true by looking up before creating.
    op.create_unique_constraint(
        'uq_player_org_grassroots', 'players', ['organisation_id', 'grassroots_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_player_org_grassroots', 'players', type_='unique')
    op.drop_column('players', 'grassroots_id')
