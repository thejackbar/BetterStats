"""Sponsor tiers and per-sponsor placements.

`org_sponsors.tier` (major / gold / silver / supporter, default silver),
`org_sponsors.placements` (hand-set overrides of the tier's default spots) and
`organisations.sponsor_tier_labels` (the club's own tier names). Nothing about
where a sponsor shows is stored beyond the overrides: it is derived on read.

Runs services/sponsor_tiers_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 318
Revises: 317
"""
from alembic import op

from app.services.sponsor_tiers_ddl import STATEMENTS, DOWNGRADE

revision = "318"
down_revision = "317"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
