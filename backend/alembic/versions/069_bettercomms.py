"""BetterComms — bulk email to the member database (BetterAdmin module).

Adds the BetterComms data layer:

  * organisations gains the per-club sender identity — ``comms_from_name`` /
    ``comms_reply_to`` (fall back to the club name / contact email) and
    ``comms_sender_footer`` (the Spam Act 2003 sender-identification line that
    every campaign appends alongside the mandatory unsubscribe link).
  * ``comms_contacts`` — the club's audience, deduped per club by email.
    ``subscribed`` is the suppression gate (one-click unsubscribe / hard bounce).
  * ``comms_campaigns`` — one email send (draft → sending → sent/error).
  * ``comms_recipients`` — per-recipient delivery audit for the history view.

Non-breaking: every existing club starts with NULL sender fields (sensible
fallbacks apply) and an empty audience.

Revision ID: 069
Revises: 068
Create Date: 2026-06-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '069'
down_revision = '068'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('organisations', sa.Column('comms_from_name', sa.Text(), nullable=True))
    op.add_column('organisations', sa.Column('comms_reply_to', sa.Text(), nullable=True))
    op.add_column('organisations', sa.Column('comms_sender_footer', sa.Text(), nullable=True))

    op.create_table(
        'comms_contacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organisation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('source', sa.Text(), nullable=False, server_default='manual'),
        sa.Column('player_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('players.id', ondelete='SET NULL'), nullable=True),
        sa.Column('member_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('fee_members.id', ondelete='SET NULL'), nullable=True),
        sa.Column('subscribed', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('unsubscribed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('bounced', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('bounced_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('tags', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('organisation_id', 'email', name='uq_comms_contact_org_email'),
    )
    op.create_index('ix_comms_contacts_org', 'comms_contacts', ['organisation_id'])

    op.create_table(
        'comms_campaigns',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organisation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False, server_default=''),
        sa.Column('preheader', sa.Text(), nullable=True),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('audience', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('status', sa.Text(), nullable=False, server_default='draft'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('sent_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('stats', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_comms_campaigns_org', 'comms_campaigns', ['organisation_id', sa.text('created_at DESC')])

    op.create_table(
        'comms_recipients',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('comms_campaigns.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organisation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('comms_contacts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='queued'),
        sa.Column('provider_message_id', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('campaign_id', 'email', name='uq_comms_recipient_campaign_email'),
    )
    op.create_index('ix_comms_recipients_campaign', 'comms_recipients', ['campaign_id'])


def downgrade() -> None:
    op.drop_index('ix_comms_recipients_campaign', table_name='comms_recipients')
    op.drop_table('comms_recipients')
    op.drop_index('ix_comms_campaigns_org', table_name='comms_campaigns')
    op.drop_table('comms_campaigns')
    op.drop_index('ix_comms_contacts_org', table_name='comms_contacts')
    op.drop_table('comms_contacts')
    op.drop_column('organisations', 'comms_sender_footer')
    op.drop_column('organisations', 'comms_reply_to')
    op.drop_column('organisations', 'comms_from_name')
