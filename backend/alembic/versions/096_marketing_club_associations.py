"""Marketing club directory — store the association(s) each club plays in

The directory's data source moved to the PlayHQ public discovery API (search +
main graph). The search step gives every club plus its full committee in one
pass; a second per-club call (``discoverCompetitions``) returns the
association(s) the club plays in. A club commonly plays across several
associations (e.g. a turf comp + a junior comp + a women's league), so the
single ``association_name``/``association_guid`` columns can't hold them all.

This adds an ``associations`` JSONB list — ``[{"id","name","competition"}, …]`` —
while keeping ``association_name``/``association_guid`` as the primary (first)
association for the existing display/CSV/filters. ``associations IS NULL`` marks
a club whose associations haven't been fetched yet (the enrichment frontier);
``[]`` means fetched-but-none.

Revision ID: 096
Revises: 095
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = '096'
down_revision = '095'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('marketing_clubs', sa.Column('associations', JSONB(), nullable=True))
    # Frontier for the per-club association-enrichment pass.
    op.create_index('idx_marketing_clubs_assoc_pending', 'marketing_clubs',
                    ['associations'], postgresql_where=sa.text('associations IS NULL'))


def downgrade() -> None:
    op.drop_index('idx_marketing_clubs_assoc_pending', table_name='marketing_clubs')
    op.drop_column('marketing_clubs', 'associations')
