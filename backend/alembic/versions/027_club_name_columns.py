"""Add home_club and away_club to games

Revision ID: 027
Revises: 026
Create Date: 2026-05-24
"""
from alembic import op

revision = '027'
down_revision = '026'
branch_labels = None
depends_on = None

# Strips common grade/team-number suffixes from a raw team displayName so that
# "North Perth 2nd XI" and "North Perth" both resolve to "North Perth".
# Covers: 1sts/2nds/3rds, 1st/2nd/3rd, 1st XI/2nd XI, standalone XI, A/B Grade.
_STRIP_SQL = r"""
    NULLIF(
        TRIM(regexp_replace(
            {col},
            ' +(\d+(st|nd|rd|th)s?( XI)?|XI|[A-Za-z] Grade)$',
            '',
            'i'
        )),
        ''
    )
"""


def upgrade() -> None:
    op.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS home_club TEXT")
    op.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS away_club TEXT")
    op.execute(f"""
        UPDATE games
        SET home_club = {_STRIP_SQL.format(col='home_team')},
            away_club = {_STRIP_SQL.format(col='away_team')}
        WHERE home_team IS NOT NULL OR away_team IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE games DROP COLUMN IF EXISTS home_club")
    op.execute("ALTER TABLE games DROP COLUMN IF EXISTS away_club")
