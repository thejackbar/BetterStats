"""Marketing club directory — per-contact outreach selection

The directory now stores a club's whole committee (not just office bearers), so a
super admin needs to choose which of those contacts actually receive an outreach
email. ``outreach_selected`` is that per-contact flag; ``export_to_comms`` only
pushes ticked contacts into the BetterComms send pipeline.

Office bearers (President / Vice-President / Secretary / Treasurer, role_rank ≤ 4)
are pre-selected so there's a sensible default; everyone else is stored unticked.
This backfill pre-selects the office bearers already in the table.

Revision ID: 097
Revises: 096
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa


revision = '097'
down_revision = '096'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('marketing_club_contacts',
                  sa.Column('outreach_selected', sa.Boolean(), nullable=False,
                            server_default='false'))
    # Pre-select the office bearers already stored (rank ≤ 4).
    op.execute("UPDATE marketing_club_contacts SET outreach_selected = TRUE "
               "WHERE role_rank <= 4")


def downgrade() -> None:
    op.drop_column('marketing_club_contacts', 'outreach_selected')
