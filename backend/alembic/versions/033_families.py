"""Family relationships within an organisation.

Revision ID: 033
Revises: 032
Create Date: 2026-05-26

A `family` groups players that share a real-world family unit. The
relationship field on each member is free text (e.g. "Father", "Son",
"Cousin") — there's no fixed enum so unusual cases don't get blocked.

Surname-based suggestions are dismissable: once a Main Admin ignores a
surname group it never reappears in the suggestion list (similar to how
merge-pair ignores work).
"""
from alembic import op
import sqlalchemy as sa


revision = '033'
down_revision = '032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'families',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organisation_id', sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('organisation_id', 'name', name='uq_families_org_name'),
    )
    op.create_index('ix_families_org', 'families', ['organisation_id'])

    op.create_table(
        'family_members',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('family_id', sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('relationship', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('family_id', 'player_id', name='uq_family_member_player'),
    )
    op.create_index('ix_family_members_family', 'family_members', ['family_id'])
    op.create_index('ix_family_members_player', 'family_members', ['player_id'])

    op.create_table(
        'family_suggestions_dismissed',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organisation_id', sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('surname_key', sa.Text(), nullable=False),
        sa.Column('dismissed_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('dismissed_by_user_id', sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.UniqueConstraint('organisation_id', 'surname_key', name='uq_family_dismiss_org_surname'),
    )


def downgrade() -> None:
    op.drop_table('family_suggestions_dismissed')
    op.drop_index('ix_family_members_player', 'family_members')
    op.drop_index('ix_family_members_family', 'family_members')
    op.drop_table('family_members')
    op.drop_index('ix_families_org', 'families')
    op.drop_table('families')
