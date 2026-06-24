"""Marketing club directory — the crawled CA/grassroots club universe for outreach

BetterCricket's own go-to-market needs a list of every cricket club in Australia
with the data we can lawfully reach: club name, PlayHQ id, association (name +
id), full postal address (postcode broken out as its own field), website, and the
single club contact the grassroots org-detail endpoint exposes
(``/orgsproducts/organisation/{guid}`` → ``contact {phone, email}``, usually a
role mailbox like ``secretary@``). The CA API does NOT expose per-person office
bearers (President/Secretary/Treasurer with names + personal mobiles), so the
contact table is built many-per-club with a ``role`` + ``role_rank`` so those can
be added later (manual enrichment), but Phase 1 stores the one API contact.

These are *prospects*, not customers, so the tables are decoupled from
``organisations`` (same precedent as ``club_onboarding_requests``). ``existing_org_id``
links a row to a club that is already a BetterStats customer so outreach can skip
them. The crawl is resumable through the table itself: a row with
``detail_fetched_at IS NULL`` is a frontier node discovered via an affiliation but
not yet detailed; each nightly batch details a capped number and enqueues their
affiliations as new frontier rows.

Sending reuses the existing BetterComms pipeline: an export bridge materialises a
filtered selection into ``comms_contacts`` under a dedicated platform org, so the
unsubscribe / suppression / audit machinery is unchanged. Unsubscribes + bounces
sync back here as a global suppression flag.

Revision ID: 095
Revises: 094
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = '095'
down_revision = '094'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'marketing_clubs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('grassroots_guid', sa.Text(), nullable=False),
        sa.Column('playhq_id', sa.Text(), nullable=True),
        sa.Column('mycricket_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('short_name', sa.Text(), nullable=True),
        # 'club' | 'association' — heuristic, so the export can skip associations.
        sa.Column('kind', sa.Text(), nullable=False, server_default='club'),
        sa.Column('association_name', sa.Text(), nullable=True),
        sa.Column('association_guid', sa.Text(), nullable=True),
        sa.Column('website_url', sa.Text(), nullable=True),
        sa.Column('contact_email', sa.Text(), nullable=True),
        sa.Column('contact_phone', sa.Text(), nullable=True),
        sa.Column('address_line1', sa.Text(), nullable=True),
        sa.Column('address_line2', sa.Text(), nullable=True),
        sa.Column('suburb', sa.Text(), nullable=True),
        sa.Column('state', sa.Text(), nullable=True),
        sa.Column('postcode', sa.Text(), nullable=True),
        sa.Column('country', sa.Text(), nullable=True),
        sa.Column('latitude', sa.Numeric(10, 6), nullable=True),
        sa.Column('longitude', sa.Numeric(10, 6), nullable=True),
        sa.Column('logo_url', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_playhq', sa.Boolean(), nullable=True),
        # new | enriched | contacted | onboarded | suppressed
        sa.Column('status', sa.Text(), nullable=False, server_default='new'),
        sa.Column('source', sa.Text(), nullable=False, server_default='grassroots_api'),
        sa.Column('raw_json', JSONB(), nullable=True),
        sa.Column('existing_org_id', UUID(as_uuid=True),
                  sa.ForeignKey('organisations.id', ondelete='SET NULL'), nullable=True),
        # NULL = discovered as a frontier node but org-detail not yet fetched.
        sa.Column('detail_fetched_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('first_seen_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_crawled_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('grassroots_guid', name='uq_marketing_club_guid'),
    )
    op.create_index('idx_marketing_clubs_frontier', 'marketing_clubs',
                    ['detail_fetched_at', 'first_seen_at'])
    op.create_index('idx_marketing_clubs_state_status', 'marketing_clubs', ['state', 'status'])

    op.create_table(
        'marketing_club_contacts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('marketing_club_id', UUID(as_uuid=True),
                  sa.ForeignKey('marketing_clubs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('full_name', sa.Text(), nullable=True),
        sa.Column('role', sa.Text(), nullable=True),
        # President=1, Secretary=2, Treasurer=3, everything else=99 → priority order.
        sa.Column('role_rank', sa.Integer(), nullable=False, server_default='99'),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('mobile', sa.Text(), nullable=True),
        sa.Column('source', sa.Text(), nullable=False, server_default='api'),  # api | website | manual
        sa.Column('subscribed', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('unsubscribed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('bounced', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('bounced_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Dedupe one email per club (only when an email is present).
    op.create_index('uq_marketing_contact_club_email', 'marketing_club_contacts',
                    ['marketing_club_id', sa.text('lower(email)')], unique=True,
                    postgresql_where=sa.text('email IS NOT NULL'))


def downgrade() -> None:
    op.drop_index('uq_marketing_contact_club_email', table_name='marketing_club_contacts')
    op.drop_table('marketing_club_contacts')
    op.drop_index('idx_marketing_clubs_state_status', table_name='marketing_clubs')
    op.drop_index('idx_marketing_clubs_frontier', table_name='marketing_clubs')
    op.drop_table('marketing_clubs')
