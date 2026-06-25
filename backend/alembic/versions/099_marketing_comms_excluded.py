"""Marketing + comms — admin exclusion flag

A super admin can exclude a club from BetterAdmin Comms outreach entirely.
``marketing_clubs.excluded`` hard-stops it from ever being exported; the matching
``comms_contacts.excluded`` (set when an already-exported club is excluded) keeps
those contacts out of every campaign audience and flags them in the comms lists.
Distinct from ``subscribed`` (recipient opt-out) and ``bounced`` — this is a
deliberate, reversible admin choice.

Revision ID: 099
Revises: 098
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa


revision = '099'
down_revision = '098'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('marketing_clubs',
                  sa.Column('excluded', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('marketing_clubs', sa.Column('excluded_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('comms_contacts',
                  sa.Column('excluded', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('comms_contacts', sa.Column('excluded_at', sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('comms_contacts', 'excluded_at')
    op.drop_column('comms_contacts', 'excluded')
    op.drop_column('marketing_clubs', 'excluded_at')
    op.drop_column('marketing_clubs', 'excluded')
