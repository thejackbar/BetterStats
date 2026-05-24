"""Add opp_org_id and opp_club_name to games

Revision ID: 028
Revises: 027
Create Date: 2026-05-24

opp_org_id  — stable owningOrganisation UUID from the Grassroots API.
              Populated at sync time for new rows and bulk-backfilled for
              existing rows during the discovery phase of every sync run.
opp_club_name — display name for the opposition club (owningOrganisation.name
               or team displayName from the match listing). Updated alongside
               opp_org_id so we always have the most recently synced name.
"""
from alembic import op

revision = '028'
down_revision = '027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS opp_org_id TEXT")
    op.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS opp_club_name TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE games DROP COLUMN IF EXISTS opp_org_id")
    op.execute("ALTER TABLE games DROP COLUMN IF EXISTS opp_club_name")
