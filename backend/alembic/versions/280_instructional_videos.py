"""Instructional video library, managed by a Super Admin

The /videos section on the marketing site was a hardcoded list. This gives it a
table so a Super Admin can upload a video, write its title and description,
replace the file, reorder the library and delete an entry, without a deploy.

The statements live in services/instructional_video_ddl.py, the one copy this
and the lifespan mirror in main.py both run, in that order.

Revision ID: 280
Revises: 279
Create Date: 2026-08-27
"""
from alembic import op

from app.services.instructional_video_ddl import (  # noqa: E402
    DOWNGRADE_STATEMENTS,
    STATEMENTS,
)

revision = "280"
down_revision = "279"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE_STATEMENTS:
        op.execute(stmt)
