"""Association selection rules for BetterSelect.

A club's competition imposes rules its selectors have to hold in their heads —
Division 1 is 15 and over, Colts is under 21, one overseas player per side, a
fourteen year old quick may bowl 12 overs a day in spells of 5, four qualifying
games before a final. This is where a club writes them down once.

The rules are deliberately NOT modelled on one association's rulebook. Every
number is the club's, every rule says which grades it covers by NAME (so it
survives the season rollover that gives every grade a new id), and the date an
age is measured on is a setting rather than a constant — 1 September, 1
January, the first day of the season or the day of the match, all from the
same field.

The DDL itself lives in ``app/services/selection_rule_ddl.py`` and is shared
with ``main.py``'s lifespan mirror, so the two cannot drift.

Revision ID: 271
Revises: 270
"""
from alembic import op

from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

revision = "271"
down_revision = "270"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in SELECTION_RULE_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS selection_rule_players")
    op.execute("DROP TABLE IF EXISTS selection_rules")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS selection_rules_config")
    op.execute("ALTER TABLE fixtures DROP COLUMN IF EXISTS is_final")
