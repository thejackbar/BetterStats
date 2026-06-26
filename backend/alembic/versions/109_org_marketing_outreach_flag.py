"""Designate the BetterCricket marketing-outreach org via a DB flag

BetterCricket runs its own BetterComms campaigns to the Clubs Directory through a
normal ``organisations`` row (the "outreach org"), kept separate from any real
club so a directory opt-out never touches a club's own audience. Until now the
only way to name that row was the ``marketing_outreach_org_slug`` setting (an env
var ⇒ redeploy).

This adds ``organisations.is_marketing_outreach`` so a super admin can designate
the outreach org from the BetterComms UI with no env change. The setting stays a
fallback; the DB flag wins. A partial unique index keeps at most one org flagged.

The backfill flips the flag on the org the configured slug already names (if any),
so a deployment that has set ``marketing_outreach_org_slug`` is unchanged.

Revision ID: 109
Revises: 108
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

from app.config.settings import settings

revision = '109'
down_revision = '108'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('organisations',
                  sa.Column('is_marketing_outreach', sa.Boolean(), nullable=False,
                            server_default='false'))
    # At most one org can be the marketing-outreach org (partial: only true rows
    # are indexed, so the many false rows don't collide).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_org_marketing_outreach "
        "ON organisations (is_marketing_outreach) WHERE is_marketing_outreach")
    # Preserve an existing env-configured outreach org: flag the row its slug names.
    slug = (settings.marketing_outreach_org_slug or "").strip()
    if slug:
        op.execute(
            sa.text("UPDATE organisations SET is_marketing_outreach = TRUE "
                    "WHERE slug = :slug").bindparams(slug=slug))


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_org_marketing_outreach")
    op.drop_column('organisations', 'is_marketing_outreach')
