"""The competitions a club has played in, alongside its former names.

``organisations.competitions``
    A JSONB list of ``{"name": ..., "from_year": ..., "to_year": ...}``, the
    same shape migration 227 gave ``previous_names`` and validated by the same
    ``services/club_history.py`` rules. A club's league history is the other
    half of the story its former names tell — Hampton played the Federal
    League before the Southern Football Netball League, and nothing in the
    synced data can say so, because PlayHQ only ever knows about the seasons
    it ran.

    Both years stay optional for the reason the former names need them to be:
    a club knows which competitions it has been in far more often than it
    knows the year each one started.

Revision ID: 262
Revises: 261
"""
from alembic import op

revision = "262"
down_revision = "261"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS competitions JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS competitions")
