"""Marketing club directory — emailed tracking + comms link

Two needs:

* Mark a club as already emailed (manually, e.g. via an external mailing tool, or
  automatically when a BetterAdmin Comms campaign sends to it) so it isn't emailed
  again. ``emailed_at`` / ``emailed_via`` ('manual' | 'campaign') / ``emailed_note``.
* Link an exported comms contact back to the directory club it came from, so a
  campaign send can flag the club emailed (and the opt-out/indicator can flow).
  ``comms_contacts.marketing_club_id``.

Revision ID: 098
Revises: 097
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '098'
down_revision = '097'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('marketing_clubs', sa.Column('emailed_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('marketing_clubs', sa.Column('emailed_via', sa.Text(), nullable=True))   # manual | campaign
    op.add_column('marketing_clubs', sa.Column('emailed_note', sa.Text(), nullable=True))
    op.add_column('comms_contacts',
                  sa.Column('marketing_club_id', UUID(as_uuid=True),
                            sa.ForeignKey('marketing_clubs.id', ondelete='SET NULL'), nullable=True))
    op.create_index('idx_comms_contacts_marketing_club', 'comms_contacts', ['marketing_club_id'])


def downgrade() -> None:
    op.drop_index('idx_comms_contacts_marketing_club', table_name='comms_contacts')
    op.drop_column('comms_contacts', 'marketing_club_id')
    op.drop_column('marketing_clubs', 'emailed_note')
    op.drop_column('marketing_clubs', 'emailed_via')
    op.drop_column('marketing_clubs', 'emailed_at')
