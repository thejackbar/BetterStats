"""Add UNIQUE constraint on batting_innings (game_id, innings_number, player_id)

De-dupes any existing duplicate rows first (keeping the lowest id per group),
then adds the constraint so future sync bugs can't produce duplicates silently.

Revision ID: 030
Revises: 029
Create Date: 2026-05-25
"""
from alembic import op

revision = '030'
down_revision = '029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove duplicate rows, keeping the one with the smallest id in each group.
    op.execute("""
        DELETE FROM batting_innings
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM batting_innings
            GROUP BY game_id, innings_number, player_id
        )
    """)

    op.create_unique_constraint(
        "uq_batting_innings_game_inns_player",
        "batting_innings",
        ["game_id", "innings_number", "player_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_batting_innings_game_inns_player",
        "batting_innings",
        type_="unique",
    )
