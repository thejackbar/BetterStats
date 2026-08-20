"""A history of engagement-score parameter changes.

``engagement_parameter_revisions``
    One row per save from Better HQ > CRM > Engagement Score Parameters. The
    VALUES the parameters actually resolved to at that moment, the sparse
    OVERRIDE set that produced them, who saved it and any note, plus a summary
    of what the recalculation that followed did to the platform.

    The parameter values themselves do NOT live here. They live as a sparse
    override dict in the ``platform_settings`` singleton, so an untouched knob
    keeps tracking its code default (see services/engagement_params.py). This
    table is the audit trail and the rollback source: re-applying a revision's
    ``overrides_json`` restores that configuration exactly.

    ``changed_by_user_id`` is ON DELETE SET NULL. Removing a staff account must
    not take the record of what they changed with it.

Revision ID: 270
Revises: 269
"""
from alembic import op

revision = "270"
down_revision = "269"
branch_labels = None
depends_on = None

from app.services.engagement_param_ddl import ENGAGEMENT_PARAM_STATEMENTS

# The statement list lives in services/engagement_param_ddl.py so this migration
# and main.py's lifespan mirror run the same statements in the same order.


def upgrade() -> None:
    for stmt in ENGAGEMENT_PARAM_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS engagement_parameter_revisions")
