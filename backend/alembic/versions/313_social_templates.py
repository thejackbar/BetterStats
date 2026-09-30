"""BetterSocials saved templates get their own table

`social_templates` holds one row per saved template, replacing the copy that
rode inside organisations.socials_style. Defined once in
services/social_template_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 313
Revises: 312
"""
from alembic import op

from app.services.social_template_ddl import STATEMENTS, DOWNGRADE

revision = "313"
down_revision = "312"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
