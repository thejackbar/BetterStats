"""A plan owns its themes; a theme owns its objectives.

``club_strategic_pillars.plan_id``  NOT NULL
``club_objectives.plan_id``         NOT NULL, ON DELETE CASCADE
``club_objectives.pillar_id``       NOT NULL, ON DELETE CASCADE

275 gave a theme its plan, which stopped one plan's tree leaking into another.
It left three states that still contradicted the model: a theme on no plan, an
objective on no plan, and an objective under no theme. A plan and its themes
and objectives are entirely separate from every other plan's, so none of the
three is a state the club's plan can be in.

Nothing the club wrote is deleted to get there. The unattributable is carried
into a plan named "Unfiled work" and, inside a plan, a theme named "General",
both of which a committee can see and move work out of. The one thing removed
is a theme with no plan AND no objectives, which holds nothing but a word.

The ACTIONS and MOTIONS serving an objective are untouched here and by the
cascades this adds: ``committee_tasks``/``meeting_motions`` → ``club_objectives``
stays ON DELETE SET NULL, so they are kept and simply stop being linked. That
is the one rule not to relax.

Revision ID: 276
Revises: 275
"""
from alembic import op

from app.services.plan_tree_ddl import PLAN_TREE_SQL  # noqa: E402

revision = "276"
down_revision = "275"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in PLAN_TREE_SQL:
        op.execute(stmt)


def downgrade() -> None:
    # The carried rows cannot be un-carried (there is nothing recording where
    # they came from, because they came from nowhere), so this only relaxes the
    # constraints back. A club that ran the upgrade keeps its "Unfiled work"
    # plan and its "General" themes.
    op.execute("ALTER TABLE club_objectives ALTER COLUMN pillar_id DROP NOT NULL")
    op.execute("ALTER TABLE club_objectives ALTER COLUMN plan_id DROP NOT NULL")
    op.execute("ALTER TABLE club_strategic_pillars ALTER COLUMN plan_id DROP NOT NULL")
    op.execute("ALTER TABLE club_objectives DROP CONSTRAINT IF EXISTS club_objectives_pillar_id_fkey")
    op.execute("""
        ALTER TABLE club_objectives
            ADD CONSTRAINT club_objectives_pillar_id_fkey
            FOREIGN KEY (pillar_id) REFERENCES club_strategic_pillars(id) ON DELETE SET NULL
    """)
    op.execute("ALTER TABLE club_objectives DROP CONSTRAINT IF EXISTS club_objectives_plan_id_fkey")
    op.execute("""
        ALTER TABLE club_objectives
            ADD CONSTRAINT club_objectives_plan_id_fkey
            FOREIGN KEY (plan_id) REFERENCES club_strategic_plans(id) ON DELETE SET NULL
    """)
