"""Per-innings meta for a hand-entered manual game

A hand-typed manual game could not say which side batted an innings, record an
innings' extras (byes/leg-byes/wides/no-balls/penalty or a total), or record the
opposition innings' own total — the photo-upload path captures all three in
`extracted_payload`, but a typed-in card had nowhere for them. So our bowling
landed in innings 1 beside our batting, drawn as the attack against our own
batters, and the club's extras went unrecorded.

`manual_innings` holds them, one row per (game, innings_number). Additive: a
game with no rows behaves exactly as before, and the photo-upload path is
untouched.

Same one-copy rule — this migration and main.py's lifespan mirror both run
services/manual_innings_ddl.STATEMENTS. Every statement is idempotent.

Revision ID: 310
Revises: 309
"""
from alembic import op

from app.services.manual_innings_ddl import STATEMENTS, DOWNGRADE

revision = "310"
down_revision = "309"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
