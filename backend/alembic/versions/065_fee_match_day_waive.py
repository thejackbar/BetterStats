"""BetterFees: waive a match-day fee

Lets an admin forgive a single game's match fee without recording it as money
received. A waived row settles the game (the member reads 'Financial' and the
game shows 'Waived') but never enters the payment/income totals — that's why it
lives as flags on the match-day row, NOT as a fee_payment. Reversible by
clearing the flag.

  - waived_at         — NULL = not waived; set = waived (audit timestamp)
  - waived_by_user_id — who waived it (audit; SET NULL if the user is removed)
  - waive_reason      — optional free-text note

Revision ID: 065
Revises: 064
Create Date: 2026-06-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '065'
down_revision = '064'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('fee_match_days', sa.Column('waived_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('fee_match_days', sa.Column('waived_by_user_id', UUID(as_uuid=True), nullable=True))
    op.add_column('fee_match_days', sa.Column('waive_reason', sa.Text(), nullable=True))
    op.create_foreign_key(
        'fk_fee_match_day_waived_by_user', 'fee_match_days', 'users',
        ['waived_by_user_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_fee_match_day_waived_by_user', 'fee_match_days', type_='foreignkey')
    op.drop_column('fee_match_days', 'waive_reason')
    op.drop_column('fee_match_days', 'waived_by_user_id')
    op.drop_column('fee_match_days', 'waived_at')
